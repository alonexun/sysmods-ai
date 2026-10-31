# -*- coding: utf-8 -*-
"""SysMods MCP server（S1）—— DSH/外部 Agent 受控工具接入层。

工具（V1.3 §2.6.1 契约 / §11 S1 范围，名称即 DSH 侧 mcp__sysmods__<tool>）：
- create_project               创建项目（完整参数卡 + 首问清单）
- submit_requirement_answer    对话补参（逐项过 canonical 注册表 validate，非法值不写入）
- run_simulation               仿真（KPI/守恒/置信度；时长计费 2 积分/分钟）
- get_param_card               只读参数卡（无副作用、不计费）

职责边界（V1.3 §2.0.1）：
- 复用 FastAPI 同一领域服务（services/api/main.py 的 Orchestrator/Ledger/LLM 网关），
  MCP 与 REST 不另设计算与计费口径；本层只做封套、鉴权、幂等与错误翻译；
- 单写者：只有 Orchestrator 推进领域状态；expected_version 过期返回 VERSION_CONFLICT；
- 幂等：idempotency_key + 工具名 + session_id 去重，重试不重复扣费（V1.3 §2.6.2）。

统一响应封套：{ok, session_id, state, data, error{code,message,retryable}, usage_ref}。
错误只返回可行动信息，不暴露堆栈/数据库细节。

启动（stdio，DSH mcp-client 本地程序模式）：python -m services.mcp_server
"""
import json
import os
import sys
import time
from typing import Dict, Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi import HTTPException

from mcp.server.fastmcp import FastMCP

# 复用 FastAPI 同一服务对象——禁止在本层重算口径（V1.3 §2.5）
from services.api import db
from services.api.db import LedgerError
from services.api.main import (
    _apply_llm_runtime, _charge_sim, _llm_charge, _persist, _session_auto,
    llm_gateway, orch,
)
from agents.orchestrator import OrchestratorError, State

mcp = FastMCP("sysmods")


# ---------------- 幂等存储（MCP 接入层自有；SQLite 同库，IF NOT EXISTS 幂等建表） ----------------
_IDEM_DDL = """
CREATE TABLE IF NOT EXISTS mcp_idempotency (
    tool TEXT NOT NULL,
    session_id TEXT NOT NULL,
    idem_key TEXT NOT NULL,
    response TEXT NOT NULL,
    ts REAL NOT NULL,
    PRIMARY KEY (tool, session_id, idem_key)
)
"""


def _idem_connect():
    con = db.connect()
    con.execute(_IDEM_DDL)
    con.commit()
    return con


def _idem_get(tool: str, sid: str, key: str) -> Optional[dict]:
    if not key:
        return None
    con = _idem_connect()
    try:
        row = con.execute(
            "SELECT response FROM mcp_idempotency WHERE tool=? AND session_id=? AND idem_key=?",
            (tool, sid, key)).fetchone()
        return json.loads(row["response"]) if row else None
    finally:
        con.close()


def _idem_put(tool: str, sid: str, key: str, response: dict) -> None:
    if not key:
        return
    con = _idem_connect()
    try:
        con.execute(
            "INSERT OR REPLACE INTO mcp_idempotency(tool, session_id, idem_key, response, ts) "
            "VALUES(?,?,?,?,?)", (tool, sid, key, json.dumps(response, ensure_ascii=False), time.time()))
        con.commit()
    finally:
        con.close()


# ---------------- 封套与错误翻译 ----------------
def _err(code: str, message: str, retryable: bool, sid: str = "") -> dict:
    return {"ok": False, "session_id": sid, "state": None, "data": None,
            "error": {"code": code, "message": message, "retryable": retryable},
            "usage_ref": None}


def _http_to_err(e: HTTPException, sid: str = "") -> dict:
    code = {401: "UNAUTHORIZED", 402: "INSUFFICIENT_CREDITS", 404: "NOT_FOUND"}.get(e.status_code, "BAD_REQUEST")
    # 402（积分不足）补充值后可重试；401/404 重试同参数无意义
    return _err(code, str(e.detail), retryable=(e.status_code == 402), sid=sid)


def _check_version(sid: str, expected_version: Optional[int]):
    """expected_version 过期 → 409 语义（重新读取后再提交），禁止以旧快照覆盖新方案。"""
    if expected_version is None:
        return None
    s = _session_auto(sid)
    if s.version != expected_version:
        return _err("VERSION_CONFLICT",
                    f"expected_version={expected_version} 已过期（当前 {s.version}）——请重新读取参数卡后再提交",
                    retryable=True, sid=sid)
    return None


# ---------------- 工具 ----------------
@mcp.tool()
def create_project(phone: str, actor_token: str, description: str,
                   use_llm: bool = False, idempotency_key: str = "") -> dict:
    """创建氢能方案项目：返回完整参数卡（canonical 参数+等级+取值）与首问清单。

    写操作：携带 actor_token（注册签发）；可选 idempotency_key 供重试去重。
    """
    stored = _idem_get("create_project", "", idempotency_key)
    if stored is not None:
        return stored
    sid = f"S{int(time.time() * 1000)}"
    try:
        if not phone or not db.verify_token(phone, actor_token):
            return _err("UNAUTHORIZED", "未授权：请携带有效 actor_token（注册/登录后签发）", retryable=False)
        tok0 = llm_gateway.usage.total_tokens
        s = orch.create_session(sid, description)
        if use_llm and s.param_card.get("llm_mode", "off") == "off":
            card = orch.grillme.build_param_card(description, None, use_llm=True)
            s.param_card = card
        used_tokens = _llm_charge(phone, tok0, sid) if use_llm else 0
        _persist(sid, phone)
        card = s.param_card
        resp = {"ok": True, "session_id": sid, "state": s.state.value,
                "data": {"param_card": {"scenario": card["scenario"], "template": card["template"],
                                         "completeness": card["completeness"],
                                         "questions": card["questions"], "required": card["required"],
                                         "llm_mode": card.get("llm_mode", "off"),
                                         "llm_note": card.get("llm_note", "")},
                          "gap_cards": s.gap_report["cards"],
                          "llm_tokens_used": used_tokens},
                "error": None, "usage_ref": sid}
        _idem_put("create_project", "", idempotency_key, resp)
        return resp
    except HTTPException as e:
        return _http_to_err(e, sid)
    except LedgerError as e:
        return _err("INSUFFICIENT_CREDITS", str(e), retryable=True, sid=sid)
    except OrchestratorError as e:
        return _err("STATE_ERROR", str(e), retryable=False, sid=sid)


@mcp.tool()
def submit_requirement_answer(session_id: str, phone: str, actor_token: str,
                              answers: Dict[str, float],
                              expected_version: Optional[int] = None,
                              idempotency_key: str = "") -> dict:
    """提交需求补充回答（对话补参）：answers 逐项过 canonical 注册表校验，非法值不写入。

    写操作：携带 actor_token 与 expected_version（当前参数卡版本，冲突需重读）；
    idempotency_key 供重试去重（重试不重复扣费）。
    """
    stored = _idem_get("submit_requirement_answer", session_id, idempotency_key)
    if stored is not None:
        return stored
    try:
        if not db.verify_token(phone, actor_token):
            return _err("UNAUTHORIZED", "未授权：请携带有效 actor_token", retryable=False, sid=session_id)
        vc = _check_version(session_id, expected_version)
        if vc is not None:
            return vc
        try:
            s = orch.confirm_g1(session_id, answers)   # 内部 build_param_card→registry.validate
        except ValueError as e:
            # 注册表校验失败：参数卡未被触碰（非法值不写入）
            return _err("INVALID_PARAM",
                        f"参数未通过注册表校验，未写入：{e}。请修正后重新提交",
                        retryable=False, sid=session_id)
        except OrchestratorError as e:
            return _err("STATE_ERROR", str(e), retryable=False, sid=session_id)
        _persist(session_id, phone)
        card = s.param_card
        resp = {"ok": True, "session_id": session_id, "state": s.state.value,
                "data": {"version": s.version,
                          "param_card": {"scenario": card["scenario"], "template": card["template"],
                                         "completeness": card["completeness"],
                                         "questions": card["questions"], "required": card["required"]}},
                "error": None, "usage_ref": session_id}
        _idem_put("submit_requirement_answer", session_id, idempotency_key, resp)
        return resp
    except HTTPException as e:
        return _http_to_err(e, session_id)


@mcp.tool()
def run_simulation(session_id: str, phone: str, actor_token: str,
                   expected_version: Optional[int] = None,
                   idempotency_key: str = "") -> dict:
    """执行仿真：返回 KPI/经济/守恒审计/置信度（G1 确认后可跑；时长计费 2 积分/分钟）。

    写操作：携带 actor_token；idempotency_key 供重试去重（重试不重复扣费）。
    """
    stored = _idem_get("run_simulation", session_id, idempotency_key)
    if stored is not None:
        return stored
    import time as _t
    try:
        if not db.verify_token(phone, actor_token):
            return _err("UNAUTHORIZED", "未授权：请携带有效 actor_token", retryable=False, sid=session_id)
        vc = _check_version(session_id, expected_version)
        if vc is not None:
            return vc
        t0 = _t.time()
        try:
            s = orch.run_simulation(session_id)
        except OrchestratorError as e:
            return _err("STATE_ERROR", str(e), retryable=False, sid=session_id)
        if s.state == State.G4_PENDING:
            try:
                _charge_sim(phone, session_id, _t.time() - t0)
            except LedgerError as e:
                return _err("INSUFFICIENT_CREDITS", str(e), retryable=True, sid=session_id)
            _persist(session_id, phone)
            resp = {"ok": True, "session_id": session_id, "state": s.state.value,
                    "data": {"result": s.result}, "error": None, "usage_ref": session_id}
            _idem_put("run_simulation", session_id, idempotency_key, resp)
            return resp
        # G3 异常（守恒 FAIL）——不扣费
        _persist(session_id, phone)
        return {"ok": True, "session_id": session_id, "state": s.state.value,
                "data": {"g3": s.result.get("g3_options"), "cons_summary": s.result.get("cons_summary")},
                "error": None, "usage_ref": session_id}
    except HTTPException as e:
        return _http_to_err(e, session_id)


@mcp.tool()
def get_param_card(session_id: str, phone: str, actor_token: str) -> dict:
    """只读获取参数卡（canonical 参数+等级+完整性+追问状态）。无副作用、不计费。

    读操作：携带 actor_token；无需 expected_version / idempotency_key。
    """
    try:
        if not db.verify_token(phone, actor_token):
            return _err("UNAUTHORIZED", "未授权：请携带有效 actor_token", retryable=False, sid=session_id)
        s = _session_auto(session_id)
        card = s.param_card
        return {"ok": True, "session_id": session_id, "state": s.state.value,
                "data": {"version": s.version,
                          "param_card": {"scenario": card["scenario"], "template": card["template"],
                                         "completeness": card["completeness"],
                                         "questions": card["questions"],
                                         "required": card["required"],
                                         "params": card.get("params", {}),
                                         "llm_mode": card.get("llm_mode", "off"),
                                         "llm_note": card.get("llm_note", "")}},
                "error": None, "usage_ref": None}
    except HTTPException as e:
        return _http_to_err(e, session_id)


if __name__ == "__main__":
    _apply_llm_runtime()          # 有 key 则真实 LLM，无 key 规则模式（与 REST 一致）
    mcp.run()                      # stdio
