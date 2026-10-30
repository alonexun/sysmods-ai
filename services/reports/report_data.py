# -*- coding: utf-8 -*-
"""报告数据组装层（React 报告视图与 HTML 导出的同一数据源）。

核心新增（用户决策）：**需求回顾 Recall** —— 报告正文之前，必须小结：
① 用户提供的项目目标主旨；② 客户确认的关键参数（A 级）；
③ 平台先验参数（C 级）使用情况；④ 会话中的变更历史；⑤ 优化目标与约束。
这是"用户需求被正确理解"的回执（recall），签收前的人工校对锚点。
"""
import base64
import datetime
import os
from typing import Dict, List

from kb.params.cn_names import cn_name, cn_category
from agents.kb_loader import kb_manifest
from .system_diagram import diagram_svg
from .device_cards import devices_data

_LOGO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "logo_small.png")


def logo_data_uri() -> str:
    """logo 内嵌 data-URI（白底黑字 sysmods+绿 AI，原比例；仅以图片形式出现）。"""
    if not os.path.isfile(_LOGO_PATH):
        return ""
    with open(_LOGO_PATH, "rb") as f:
        return "data:image/png;base64," + base64.b64encode(f.read()).decode("ascii")


def build_final_plan(params: Dict, kpi: Dict, template: str,
                     opt_rows: List[Dict] = None) -> Dict:
    """生成最终方案视图：签收工况，或优化器排名第一的推荐候选。

    优化候选只改变设备参数与架构；NPC/保供率等候选指标来自优化器复核。
    其余时序与工况 KPI 仍属于签收仿真，禁止混写为候选已重算结果。
    """
    base = dict(params or {})
    final_params = dict(base)
    opt_rows = opt_rows or []
    best = next((r for r in opt_rows if r.get("rank") == 1),
                opt_rows[0] if opt_rows else None)
    source = "optimization" if best else "signed"
    changed = []
    if best:
        for key, value in best.items():
            if key not in base or not isinstance(value, (int, float)) or isinstance(value, bool):
                continue
            old = base[key]
            if old != value:
                changed.append({"canonical": key, "cn": cn_name(key),
                                "from": old, "to": value})
            final_params[key] = value
    plan_kpi = dict(kpi or {})
    if best:
        for key in list(plan_kpi):
            if key in best and isinstance(best[key], (int, float)):
                plan_kpi[key] = best[key]
    return {
        "source": source,
        "label": "优化推荐方案" if best else "签收方案",
        "params": final_params,
        "devices": devices_data(final_params, plan_kpi, template),
        "diagram_svg": diagram_svg(final_params, template),
        "changed": changed,
        "metrics": {
            "npc_cny": best.get("npc_cny") if best else None,
            "reliability": best.get("reliability") if best else None,
            "note": best.get("note") if best else None,
        },
        "note": ("设备参数与架构按优化器第一名候选展示；NPC/保供率来自优化器复核。"
                 "其余时序和工况 KPI 仍为当前签收仿真，采纳候选后须通过变更单重算。"
                 if best else "设备参数、架构与全部 KPI 均对应当前签收工况。"),
    }


def build_report_data(session_id: str, description: str, result: Dict,
                      param_card: Dict, gap_report: Dict,
                      orders: List[Dict] = None,
                      llm_model: str = "规则模式（未接入 LLM）") -> Dict:
    """组装结构化报告数据。result 需含 kpi/econ/cons_passed/confidence/series。"""
    orders = orders or []
    kpi = result.get("kpi", {})
    econ = result.get("econ", {})
    params: Dict = param_card.get("params", {})
    levels: Dict = param_card.get("levels", {})
    template = param_card.get("template", "-")
    conf = result.get("confidence", {})
    conf_grade = conf.get("grade", "C") if isinstance(conf, dict) else "C"

    from kernel.hyflow.registry import load_registry
    reg = load_registry()
    defaults = reg.defaults()

    # ---- Recall：需求回顾 ----
    client_params, priori_params = [], []
    for k, v in sorted(params.items()):
        lv = levels.get(k, "C1")
        spec = reg.specs[k] if k in reg.specs else None
        entry = {
            "cn": cn_name(k), "canonical": k, "value": round(float(v), 4),
            "unit": spec.unit if spec else "", "level": lv,
            "category": cn_category(k),
            "is_default": spec is not None and abs(float(v) - defaults.get(k, v)) < 1e-12,
        }
        if lv == "A" and not entry["is_default"]:
            client_params.append(entry)
        elif lv == "A" and entry["is_default"]:
            priori_params.append(entry)
    if not client_params:   # 全默认时：从注册表 B 级标明基准
        client_params = [e for e in ([{
            "cn": cn_name(k), "canonical": k, "value": round(float(v), 4),
            "unit": reg.spec(k).unit, "level": levels.get(k, "B1"),
            "category": cn_category(k), "is_default": True}
            for k, v in sorted(params.items()) if k in (
                "pv.capacity_kw", "wind.capacity_kw", "pemwe.rated_kw",
                "h2store.capacity_kg", "chem.nh3.capacity_t_per_h",
                "load.avg_kw")]) if k in params]

    from agents.grillme import GrillmeAgent
    questions = GrillmeAgent().build_param_card(description, use_llm=False)["questions"]

    recall = {
        "goal": description,
        "scenario": param_card.get("scenario", "-"),
        "template": template,
        "completeness": param_card.get("completeness", 0),
        "client_params": client_params,
        "priori_count": max(0, len(params) - len(client_params)),
        "priori_examples": [e for e in priori_params][:8],
        "changes": [{"echo": o.get("echo", o.get("msg", "")),
                     "confirmed": bool(o.get("confirmed"))} for o in orders],
        "objective": ("可靠性约束下全周期净现值成本（NPC）最优；"
                       "经济口径含氨产品收入与减碳收益现值。"
                       if template.startswith("T6")
                       else "保供率硬约束下总 NPC 最优（离网优先保障供电）。"),
        "unconfirmed_questions": questions[:3],
        "note": "以上为平台对您需求的复述（Recall）。如与您的意图不符，请在签收（G5）前提交变更。",
    }

    # ---- KPI 摘要卡 ----
    def money(v):
        try:
            v = float(v)
        except (TypeError, ValueError):
            return "—"
        av = abs(v)
        if av >= 1e8:
            return f"{v/1e8:.2f} 亿元"
        if av >= 1e4:
            return f"{v/1e4:.1f} 万元"
        return f"{v:,.0f} 元"
    if template.startswith("T6"):
        kpi_cards = [
            {"label": "净 NPC（全周期）", "value": money(econ.get("npc_net_cny")), "unit": "", "sub": "含氨收入与减碳收益抵减"},
            {"label": "LCOA 平准化氨成本", "value": money(econ.get("lcoa_cny_per_t")), "unit": "/t", "sub": "NPC×CRF ÷ 年产氨"},
            {"label": "仿真期绿氨产量", "value": f"{kpi.get('nh3_annual_t', 0):,.1f}", "unit": "t", "sub": f"HB 利用率 {kpi.get('hb_capacity_factor', 0)*100:.1f}%"},
            {"label": "绿电自给率", "value": f"{kpi.get('renew_share', 1)*100:.1f}%", "unit": "", "sub": f"失电 {kpi.get('unmet_kwh', 0):,.1f} kWh"},
        ]
    else:
        kpi_cards = [
            {"label": "保供率", "value": f"{kpi.get('reliability', 1)*100:.2f}%", "unit": "", "sub": "可靠性硬约束"},
            {"label": "LCOE", "value": money(econ.get("lcoe_cny_per_kwh")), "unit": "/kWh", "sub": "平准化度电成本"},
            {"label": "年制氢量", "value": f"{kpi.get('h2_prod_kg', 0):,.1f}", "unit": "kg", "sub": "入罐口径"},
            {"label": "总 NPC", "value": money(econ.get("total_npc_cny")), "unit": "", "sub": "全周期净现值成本"},
        ]

    # ---- 参数清单（中英对照） ----
    param_rows = []
    for k, v in sorted(params.items()):
        spec = reg.specs[k] if k in reg.specs else None
        param_rows.append({
            "cn": cn_name(k), "canonical": k,
            "value": round(float(v), 4) if isinstance(v, (int, float)) else v,
            "unit": spec.unit if spec else "",
            "level": levels.get(k, ""),
            "category": cn_category(k),
            "source": (spec.source[:40] + "…") if spec and len(spec.source) > 40
                      else (spec.source if spec else ""),
        })

    # ---- 明细表 ----
    by_tech = kpi.get("h2_by_tech_kg") or {}
    generation_detail = []
    if kpi.get("e_renew_kwh") is not None:
        generation_detail.append({"name": "可再生发电量 Renewable Generation",
                                  "value": f"{kpi['e_renew_kwh']:,.0f}", "unit": "kWh",
                                  "note": "光伏 + 风电"})
    if by_tech:
        total = sum(by_tech.values())
        for tech, v in by_tech.items():
            generation_detail.append({
                "name": f"{tech.upper()} 电解产氢 H2 Production",
                "value": f"{v:,.1f}", "unit": "kg",
                "note": f"占 {v/total*100:.1f}%"})
        generation_detail.append({"name": "总产氢（入罐） Total H2",
                                  "value": f"{total:,.1f}", "unit": "kg", "note": "守恒口径"})
    if kpi.get("nh3_annual_t") is not None:
        generation_detail.append({
            "name": "合成氨 Green Ammonia", "value": f"{kpi['nh3_annual_t']:,.1f}",
            "unit": "t", "note": f"HB 利用率 {kpi.get('hb_capacity_factor',0)*100:.1f}%"})
    if kpi.get("grid_import_kwh") is not None:
        generation_detail.append({
            "name": "电网购电/售电 Grid Import/Export",
            "value": f"{kpi.get('grid_import_kwh',0):,.0f} / {kpi.get('grid_export_kwh',0):,.0f}",
            "unit": "kWh", "note": f"失电 {kpi.get('unmet_kwh',0):,.1f} kWh"})

    # ---- 经济性 ----
    econ_rows = [{"name": k, "value": money(v) if ("cny" in k or "cost" in k)
                  else (f"{v:,.2f}" if isinstance(v, (int, float)) else str(v)),
                  "unit": ""}
                 for k, v in econ.items() if isinstance(v, (int, float))]
    return {
        "meta": {
            "session_id": session_id,
            "generated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            "version": param_card.get("version", 1),
            "llm_model": llm_model,
            "cons_passed": bool(result.get("cons_passed")),
            "cons_summary": result.get("cons_summary", ""),
            "confidence": {"grade": conf_grade,
                           "attribution": conf.get("attribution", "") if isinstance(conf, dict) else ""},
            "description": description,
        },
        "logo_uri": logo_data_uri(),
        "devices": devices_data(params, kpi, template),
        "final_plan": build_final_plan(params, kpi, template, result.get("opt_table")),
        "recall": recall,
        "kpi_cards": kpi_cards,
        "kpi_table": {k: v for k, v in kpi.items() if not isinstance(v, dict)},
        "diagram_svg": diagram_svg(params, template),
        "generation_detail": generation_detail,
        "economics": {"rows": econ_rows,
                      "cost_items": econ.get("capex_items", []),
                      "note": "口径：HOMER 五类成本（初始投资/替换/残值/运维/燃料）；净 NPC=总成本现值−收益现值。"},
        "optimization": result.get("opt_table"),
        "timeseries": {k: [round(float(x), 3) for x in v[:24 * 14]]
                      for k, v in (result.get("series") or {}).items()},
        "params": param_rows,
        "orders": [{"echo": o.get("echo", o.get("msg", "")),
                    "confirmed": bool(o.get("confirmed"))} for o in orders],
        "gaps": gap_report.get("cards", []),
        "unresolved": result.get("unresolved", []),
        "kb_manifest": kb_manifest(),
    }
