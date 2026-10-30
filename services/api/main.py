# -*- coding: utf-8 -*-
"""Sysmods AI 服务层（Phase 1 本地版）：FastAPI + SQLite + 编排器 + 积分台账。

端点（V1.2 §2.6 契约）：
- POST /auth/register            手机号+验证码（测试态固定码）
- GET  /ledger/{phone}           台账对账单
- POST /session                  创建会话（grillme 参数卡+追问+盲区卡）
- POST /session/{sid}/g1         G1 参数确认（可带 overrides）
- POST /session/{sid}/run        仿真（同步执行，扣积分，失败返还）
- POST /session/{sid}/change     G4 评论 → 变更单回显
- POST /session/{sid}/change/confirm  确认变更 → 重跑
- POST /session/{sid}/g5         G5 签收 → 锁定+生成 HTML 报告
- GET  /report/{sid}             HTML 报告（自包含）
部署说明：队列化 worker/Redis/OSS 为部署环节（V1.2 §2.1），本版同步执行。
"""
import math
import os
import sys
import time
from typing import Dict, List, Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from agents.base import AgentRuntime
from agents.orchestrator import Orchestrator, OrchestratorError, State
from services.api import db
from services.api.db import Ledger, LedgerError, init_db, register_user
from services.api.llm import LLMGateway, LLMNotConfiguredError
from services.reports.render_html import render_html_report

REPORT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "output", "reports")
os.makedirs(REPORT_DIR, exist_ok=True)

app = FastAPI(title="Sysmods AI", version="0.3.0")


# ---------------- 仿真闭包（编排器注入） ----------------
def sim_fn(template: str, overrides: Dict) -> Dict:
    """template → T1/T6 内核执行；输出统一 dict（含守恒/置信度/序列）。"""
    from kernel.hyflow.templates.t1_offgrid import run_t1_scenario
    from kernel.hyflow.templates.t6_ammonia import run_t6_scenario
    t0 = time.time()
    grid_mode = None
    ov = {}
    for k, v in overrides.items():
        if k == "grid.mode_str":
            grid_mode = v
        else:
            ov[k] = v
    if template.startswith("T6"):
        if grid_mode:
            ov["grid.mode_str"] = grid_mode
        r = run_t6_scenario(ov, n_days=90)          # API 默认 90 天（快）；全年走参数
        conf = r.confidence
        return {"kpi": r.kpi, "econ": r.econ,
                "cons_passed": r.cons_report.passed,
                "cons_summary": r.cons_report.summary(),
                "confidence": {"grade": conf.grade, "attribution": conf.attribution,
                               "improvement": conf.improvement},
                "element_audit": {k: round(v, 4) for k, v in r.element_audit_annual.items()},
                "series": {k: [round(float(x), 3) for x in v[:24 * 7]]
                          for k, v in r.series.items()},   # 报告只嵌前 7 天序列
                "elapsed_s": round(time.time() - t0, 2)}
    else:
        r = run_t1_scenario(ov, n_days=90)
        conf = r.confidence
        return {"kpi": r.kpi, "econ": r.econ,
                "cons_passed": r.cons_report.passed,
                "cons_summary": r.cons_report.summary(),
                "confidence": {"grade": conf.grade, "attribution": conf.attribution,
                               "improvement": conf.improvement},
                "series": {"pv_kw": [round(float(x), 2) for x in r.pv_kw[:24 * 7]],
                           "pem_kw": [round(float(x), 2) for x in r.pem_kw[:24 * 7]],
                           "h2_store_level_kg": [round(float(x), 3) for x in r.h2_store_level_kg[:24 * 7]],
                           "bess_soc": [round(float(x), 3) for x in r.bess_soc[:24 * 7]]},
                "elapsed_s": round(time.time() - t0, 2)}


orch = Orchestrator(sim_fn)

# ---------------- LLM 网关（DEEPSEEK_API_KEY 存在则真实接入，否则规则模式） ----------------
llm_gateway = LLMGateway()


def _apply_llm_runtime():
    """把 LLM 网关注入三个 Agent（grillme/change/gaps）。无 key 时保持规则模式。"""
    if llm_gateway.configured:
        rt = AgentRuntime(llm_client=llm_gateway, model_name=f"deepseek:{llm_gateway.model}")
        orch.grillme.runtime = rt
        orch.change.runtime = rt
        orch.gaps.runtime = rt


def _llm_charge(phone: str, usage_before: int, ref: str) -> int:
    """LLM tokens 计量扣费：0.5 积分/万 tokens（不足 1 积分不收）。"""
    used = llm_gateway.usage.total_tokens - usage_before
    credits = math.floor(used / 10000.0 * 0.5)
    if credits >= 1:
        con = db.connect()
        try:
            Ledger(con).charge(phone, credits, reason=f"LLM tokens({used})", ref=ref)
        finally:
            con.close()
    return used


def _opt_sim(template: str, overrides: Dict, n_days: int) -> Dict:
    """优化器仿真闭包：返回 npc/reliability/kpis（HOMER 穷举排序口径）。"""
    grid_mode = None
    ov = {}
    for k, v in overrides.items():
        if k == "grid.mode_str":
            grid_mode = v
        else:
            ov[k] = v
    if (template or "T1").startswith("T6"):
        if grid_mode:
            ov["grid.mode_str"] = grid_mode
        from kernel.hyflow.templates.t6_ammonia import run_t6_scenario
        r = run_t6_scenario(ov, n_days=n_days)
        # 保供率 = 1 - 失电/(绿电+购电总供给)（修正：此前误用绿电自给率 renew_share 作可靠性）
        total_supply = r.kpi["e_renew_kwh"] + r.kpi["grid_import_kwh"]
        reliability = 1.0 - r.kpi["unmet_kwh"] / total_supply if total_supply > 0 else 1.0
        return {"npc": r.econ["npc_net_cny"], "reliability": reliability,
                "kpis": {"nh3_t": round(r.kpi["nh3_annual_t"], 2),
                         "hb_cf": round(r.kpi["hb_capacity_factor"], 3),
                         "lcoa": round(r.econ["lcoa_cny_per_t"], 0)}}
    else:
        from kernel.hyflow.templates.t1_offgrid import run_t1_scenario
        r = run_t1_scenario(ov, n_days=n_days)
        return {"npc": r.econ["total_npc_cny"], "reliability": r.kpi["reliability"],
                "kpis": {"h2_prod_kg": round(r.kpi["h2_prod_kg"], 2),
                         "curtail": round(r.kpi["curtail_ratio"], 3),
                         "lcoe": round(r.econ["lcoe_cny_per_kwh"], 3)}}


# ---------------- 模型 ----------------
class RegisterReq(BaseModel):
    phone: str
    code: str = "000000"


class SessionReq(BaseModel):
    phone: str
    description: str
    use_llm: bool = False          # LLM 抽取（tokens 计费），默认规则模式


class G1Req(BaseModel):
    overrides: Optional[Dict[str, float]] = None
    phone: str = None                  # 提供时持久化 G1 checkpoint（修复此前漏存）


class ChangeReq(BaseModel):
    phone: str
    text: str
    use_llm: bool = False


class RunReq(BaseModel):
    phone: str


class OptimizeReq(BaseModel):
    phone: str
    candidates: Dict[str, List[float]]   # {"pv.capacity_kw": [25,50], ...}
    n_days: int = 30
    refine_days: int = 90
    template: str = None                 # None → 会话模板


def _ledger(phone: str) -> Ledger:
    return Ledger(db.connect())


def _auth(phone: str, x_token: Optional[str]) -> None:
    """会话鉴权：受保护操作必须带与手机号匹配的 X-Token。"""
    if not phone or not db.verify_token(phone, x_token):
        raise HTTPException(401, "未授权：请携带有效 X-Token（注册/登录后签发）")


def _session_auto(sid: str):
    """获取会话；内存不存在时从 DB checkpoint 自动恢复（服务重启/跨进程不丢）。"""
    try:
        return orch.session(sid)
    except OrchestratorError:
        cp = db.load_checkpoint(sid)
        if cp is None:
            raise HTTPException(404, f"会话不存在: {sid}")
        return orch.restore(cp)


def _persist(sid: str, phone: str):
    db.save_checkpoint(sid, phone, orch.session(sid).checkpoint())


def _charge_sim(phone: str, sid: str, elapsed_s: float) -> int:
    """双重计量：时长积分（2 积分/分钟，不足 1 分钟按 1 分钟）+ LLM tokens（规则版=0）。"""
    minutes = max(1, math.ceil(elapsed_s / 60.0))
    con = db.connect()
    try:
        return Ledger(con).charge(phone, int(minutes * 2), reason="仿真", ref=sid)
    finally:
        con.close()


# ---------------- 端点 ----------------
@app.post("/auth/register")
def register(req: RegisterReq):
    if not req.phone or len(req.phone) < 6:
        raise HTTPException(400, "手机号非法")
    if not register_user(req.phone, req.code):
        raise HTTPException(401, "验证码错误（测试态为 000000）")
    b = _ledger(req.phone).balance(req.phone)
    token = db.issue_token(req.phone)     # 注册/登录签发会话 token
    return {"phone": req.phone, "credits": b, "free_monthly": 50, "token": token}


@app.get("/ledger/{phone}")
def ledger(phone: str, x_token: Optional[str] = Header(None)):
    _auth(phone, x_token)
    lg = _ledger(phone)
    return {"balance": lg.balance(phone), "statement": lg.statement(phone)}


@app.post("/session")
def create_session(req: SessionReq, x_token: Optional[str] = Header(None)):
    _auth(req.phone, x_token)
    tok0 = llm_gateway.usage.total_tokens
    s = orch.create_session(f"S{int(time.time()*1000)}", req.description)
    if req.use_llm and s.param_card.get("llm_mode", "off") == "off":
        # 规则路径未消费 LLM——按 LLM 模式重建参数卡（grillme 内部降级保护）
        from agents.grillme import GrillmeAgent
        card = orch.grillme.build_param_card(req.description, None, use_llm=True)
        s.param_card = card
    used_tokens = _llm_charge(req.phone, tok0, s.sid) if req.use_llm else 0
    _persist(s.sid, req.phone)
    return {"sid": s.sid, "state": s.state.value,
            "param_card": {"scenario": s.param_card["scenario"],
                            "template": s.param_card["template"],
                            "completeness": s.param_card["completeness"],
                            "questions": s.param_card["questions"],
                            "required": s.param_card["required"],
                            "llm_mode": s.param_card.get("llm_mode", "off"),
                            "llm_note": s.param_card.get("llm_note", "")},
            "gap_cards": s.gap_report["cards"],
            "llm_tokens_used": used_tokens}


@app.post("/session/{sid}/g1")
def confirm_g1(sid: str, req: G1Req, x_token: Optional[str] = Header(None)):
    if req.phone:
        _auth(req.phone, x_token)
    try:
        s = orch.confirm_g1(sid, req.overrides or {})
        if req.phone:
            _persist(sid, req.phone)
        return {"sid": sid, "state": s.state.value, "version": s.version}
    except OrchestratorError as e:
        raise HTTPException(409, str(e))


@app.post("/session/{sid}/run")
def run(sid: str, req: RunReq, x_token: Optional[str] = Header(None)):
    _auth(req.phone, x_token)
    s = _session_auto(sid)
    t0 = time.time()
    try:
        s = orch.run_simulation(sid)
    except OrchestratorError as e:
        raise HTTPException(409, str(e))
    if s.state == State.G4_PENDING:
        try:
            _charge_sim(req.phone, sid, time.time() - t0)
        except LedgerError as e:
            raise HTTPException(402, str(e))
        _persist(sid, req.phone)
        return {"sid": sid, "state": s.state.value, "result": s.result}
    # G3 异常（守恒 FAIL）
    _persist(sid, req.phone)
    return {"sid": sid, "state": s.state.value, "g3": s.result.get("g3_options"),
            "cons_summary": s.result.get("cons_summary")}


@app.post("/session/{sid}/change")
def propose_change(sid: str, req: ChangeReq, x_token: Optional[str] = Header(None)):
    _auth(req.phone, x_token)
    tok0 = llm_gateway.usage.total_tokens
    try:
        order = orch.propose_change(sid, req.text, use_llm=req.use_llm)
    except OrchestratorError as e:
        raise HTTPException(409, str(e))
    used_tokens = _llm_charge(req.phone, tok0, sid) if req.use_llm else 0
    order["llm_tokens_used"] = used_tokens
    _persist(sid, req.phone)
    return order


@app.post("/session/{sid}/optimize")
def optimize(sid: str, req: OptimizeReq, x_token: Optional[str] = Header(None)):
    """穷举+NPC 排序的容量配置优化（HOMER 口径）。扣时长积分（2 积分/分钟）。"""
    _auth(req.phone, x_token)
    s = _session_auto(sid)
    template = req.template or s.param_card.get("template", "T1")
    base = {k: v for k, v in s.param_card.get("params", {}).items()
            if not str(k).startswith("grid.mode")}
    from kernel.hyflow.optimize import optimize_capacity, result_table
    fn = lambda ov, n_days=req.n_days: _opt_sim(template, ov, n_days)
    try:
        t0 = time.time()
        result = optimize_capacity(fn, base, req.candidates,
                                    n_days=req.n_days,
                                    refine_top_n=min(5, int(base.get("opt.top_n", 5))),
                                    refine_days=req.refine_days)
    except (ValueError, KeyError) as e:
        raise HTTPException(400, f"候选集非法: {e}")
    try:
        _charge_sim(req.phone, sid, result.elapsed_s)
    except LedgerError as e:
        raise HTTPException(402, str(e))
    s.result.setdefault("opt_table", result_table(result))
    _persist(sid, req.phone)
    return {"sid": sid, "n_combinations": result.n_combinations,
            "n_feasible": result.n_feasible,
            "n_infeasible_reliability": result.n_infeasible_reliability,
            "grid_thinned": result.grid_thinned,
            "elapsed_s": round(result.elapsed_s, 1),
            "top": result_table(result)}


@app.post("/session/{sid}/change/confirm")
def confirm_change(sid: str, req: ChangeReq, x_token: Optional[str] = Header(None)):
    _auth(req.phone, x_token)
    t0 = time.time()
    try:
        s = orch.confirm_change(sid)
    except OrchestratorError as e:
        raise HTTPException(409, str(e))
    try:
        _charge_sim(req.phone, sid, time.time() - t0)
    except LedgerError as e:
        raise HTTPException(402, str(e))
    _persist(sid, req.phone)
    return {"sid": sid, "state": s.state.value, "rounds": s.change_rounds,
            "result": s.result}


@app.post("/session/{sid}/g5")
def sign_g5(sid: str, req: RunReq, x_token: Optional[str] = Header(None)):
    _auth(req.phone, x_token)
    try:
        s = orch.sign_g5(sid)
    except OrchestratorError as e:
        raise HTTPException(409, str(e))
    # 签收 → 生成 HTML 报告（导出固定费）
    try:
        con = db.connect()
        try:
            Ledger(con).charge(req.phone, 200, reason="报告导出(HTML)", ref=sid)
        finally:
            con.close()
    except LedgerError as e:
        raise HTTPException(402, str(e))
    s_sess = orch.session(sid)
    llm_model = f"{llm_gateway.model}（DeepSeek API）" if llm_gateway.configured \
        else "规则模式（未接入 LLM）"
    html = render_html_report(sid, s_sess.description, s_sess.result,
                              {**s_sess.param_card, "version": s_sess.version},
                              s_sess.gap_report, s_sess.orders,
                              econ=s_sess.result.get("econ"),
                              opt_table=s_sess.result.get("opt_table"),
                              llm_model=llm_model)
    path = os.path.join(REPORT_DIR, f"{sid}.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    _persist(sid, req.phone)
    return {"sid": sid, "state": s.state.value, "report_url": f"/report/{sid}"}


@app.get("/report/{sid}", response_class=HTMLResponse)
def report(sid: str):
    path = os.path.join(REPORT_DIR, f"{sid}.html")
    if not os.path.isfile(path):
        raise HTTPException(404, "报告未生成（需 G5 签收）")
    with open(path, "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())


_WEB_DIST = os.path.join(os.path.dirname(__file__), "..", "..", "apps", "web", "dist")
_WEB_ASSETS = os.path.join(_WEB_DIST, "assets")
if os.path.isdir(_WEB_ASSETS):
    app.mount("/assets", StaticFiles(directory=_WEB_ASSETS), name="assets")

from fastapi import Response as _Response


@app.get("/logo.png")
def logo_png():
    """品牌 logo（原比例图片，前端页头使用）。"""
    p = os.path.join(_WEB_DIST, "logo.png")
    if not os.path.isfile(p):
        raise HTTPException(404, "logo 未构建")
    with open(p, "rb") as f:
        return _Response(content=f.read(), media_type="image/png")


@app.get("/", response_class=HTMLResponse)
def index():
    """React 前端（apps/web/dist 构建产物；未构建时提示）。"""
    p = os.path.join(_WEB_DIST, "index.html")
    if os.path.isfile(p):
        with open(p, "r", encoding="utf-8") as f:
            return HTMLResponse(f.read())
    return HTMLResponse(
        "<h3>Sysmods AI</h3><p>前端未构建：请执行 "
        "<code>cd apps/web && npm install && npm run build</code> 后刷新。</p>")


@app.get("/session/{sid}/diagram")
def session_diagram(sid: str):
    """当前参数卡的系统架构 SVG（前端工作面板/预览用）。"""
    from fastapi import Response
    from services.reports.system_diagram import diagram_svg
    s = _session_auto(sid)
    svg = diagram_svg(s.param_card.get("params", {}),
                      s.param_card.get("template", "T6"))
    return Response(content=svg, media_type="image/svg+xml")


@app.get("/session/{sid}/report_data")
def session_report_data(sid: str, x_token: Optional[str] = Header(None)):
    """结构化报告数据（React 报告视图数据源；含需求 Recall）。

    访问策略：G5 已签收的报告=已锁定交付物，可分享（免 token——与导出 HTML 一致）；
    未签收会话仅限属主（属主 token 校验）。服务重启后自动从 checkpoint 恢复。
    """
    s = _session_auto(sid)
    if s.state.value == "G5_SIGNED":
        llm_model = f"{llm_gateway.model}（DeepSeek API）" if llm_gateway.configured \
            else "规则模式（未接入 LLM）"
        from services.reports.report_data import build_report_data
        return build_report_data(sid, s.description, s.result,
                                 {**s.param_card, "version": s.version},
                                 s.gap_report, s.orders, llm_model)
    phone_row = None
    con = db.connect()
    try:
        phone_row = con.execute("SELECT phone FROM sessions WHERE sid=?",
                                (sid,)).fetchone()
    finally:
        con.close()
    if phone_row:
        _auth(phone_row["phone"], x_token)
    llm_model = f"{llm_gateway.model}（DeepSeek API）" if llm_gateway.configured \
        else "规则模式（未接入 LLM）"
    from services.reports.report_data import build_report_data
    return build_report_data(sid, s.description, s.result,
                             {**s.param_card, "version": s.version},
                             s.gap_report, s.orders, llm_model)


@app.on_event("startup")
def startup():
    init_db()
    _apply_llm_runtime()          # 有 DEEPSEEK_API_KEY 即真实接入，Agent 走 LLM 路径
