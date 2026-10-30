# -*- coding: utf-8 -*-
"""HTML 自包含报告渲染 v3（交付物 Agent · 标杆知识库驱动）。

知识库依据（agents/deliverable/kb/）：
- homer_report_structure.md：章节结构 / 优化表 / 五类成本 / 明细表
- ibcs_visual_rules.md：一句话结论先行 / 图表选型 / 数字格式 / SUCCESS 自检
- report_design_tokens.md：唯一视觉事实源（色板/字体/组件/打印）

视图：封面+结论卡 → 摘要KPI → 系统架构图(SVG) → 明细表 → 成本表 →
时序 → 优化表 → 参数中文表 → 变更史 → 盲区 → 声明。
所有数值来自结果 JSON；LLM 不产生任何计算结果。
"""
from typing import Dict, List
import datetime

from kb.params.cn_names import cn_name, cn_category
from .system_diagram import diagram_svg
from .device_cards import devices_data, cards_grid_html
from .report_data import logo_data_uri, build_final_plan

# ---------------- 设计 tokens（kb-tokens-v2.0：深森林绿+品牌绿点缀） ----------------
_CSS = """
:root{--brand:#173F35;--brand-dark:#0F2E27;--accent:#52C41A;--brand-tint:#EDF4EE;
--page:#F3F5F2;--surface:#FFF;--panel:#F0F3EF;--ink:#1D2723;--ink-head:#10201B;
--muted:#68746E;--hairline:#DDE4DE;--rule:#C9D3CB;
--pass:#15803D;--warn:#B45309;--fail:#B91C1C}
*{box-sizing:border-box}
body{font-family:'Microsoft YaHei','PingFang SC',system-ui,sans-serif;
background:var(--page);color:var(--ink);margin:0;font-size:13px;line-height:1.55}
.wrap{max-width:1120px;margin:0 auto;padding:24px 24px 50px}
.mono{font-family:'IBM Plex Mono',ui-monospace,Consolas,monospace}
.cover{background:var(--surface);border:1px solid var(--hairline);border-radius:12px;
border-top:4px solid var(--accent);padding:24px 32px 20px;
box-shadow:0 2px 12px rgba(15,23,42,.07)}
.cover img.logo{height:34px;width:auto;display:block;margin-bottom:12px}
.cover h1{margin:0 0 6px;font-size:24px;color:var(--ink-head);letter-spacing:.5px}
.cover .sub{color:var(--brand-dark);font-weight:600;font-size:13.5px;margin-bottom:12px}
.meta{color:var(--muted);font-size:11px;line-height:1.85}
.badges{margin:12px 0 4px}
.badge{display:inline-block;padding:3px 12px;border-radius:12px;color:#fff;font-weight:600;font-size:11px;margin-right:8px}
.b-pass{background:var(--pass)}.b-fail{background:var(--fail)}.b-a{background:var(--pass)}.b-b{background:var(--brand-dark)}
.b-c{background:var(--warn)}.b-d{background:var(--fail)}.b-ver{background:#475569}
.conclusion{background:var(--brand-tint);border-left:4px solid var(--brand);
padding:12px 16px;margin:16px 0 0;border-radius:0 8px 8px 0;font-size:13px}
.conclusion b{color:var(--brand-dark)}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:22px 0}
.kpi{background:var(--surface);border:1px solid var(--hairline);border-radius:9px;
padding:13px 15px;border-top:2.5px solid var(--accent)}
.kpi .v{font-family:'IBM Plex Mono',ui-monospace,Consolas,monospace;
font-size:21px;font-weight:700;color:var(--brand-dark);line-height:1.25}
.kpi .l{color:var(--muted);font-size:11px;margin-top:4px}
.kpi .u{color:var(--muted);font-size:10.5px}
.toc{background:var(--surface);border:1px solid var(--hairline);border-radius:8px;
padding:10px 18px;font-size:12px;margin:18px 0}
.toc a{color:var(--brand-dark);text-decoration:none;margin-right:15px;line-height:2}
h2{color:var(--brand-dark);font-size:15.5px;margin:28px 0 10px;
border-bottom:1px solid var(--rule);padding-bottom:7px}
h2 .num{font-family:'IBM Plex Mono',ui-monospace,monospace;color:var(--brand-dark);margin-right:8px}
h3{color:var(--ink-head);font-size:12.5px;margin:14px 0 6px}
table{border-collapse:collapse;width:100%;margin:10px 0;background:var(--surface);
border:1px solid var(--hairline);border-radius:8px;overflow:hidden;font-size:11px}
th{background:var(--panel);color:var(--ink-head);padding:6px 10px;text-align:left;font-size:10.5px;
font-family:'IBM Plex Mono',ui-monospace,monospace;font-weight:600;border-bottom:1px solid var(--rule)}
td{padding:5px 10px;border-bottom:1px solid var(--hairline);vertical-align:top;line-height:1.45}
tr:last-child td{border-bottom:none}
tr:nth-child(even) td{background:#FAFBFC}
td.num,th.num{text-align:right;font-family:'IBM Plex Mono',ui-monospace,monospace}
tr.total td{background:var(--brand-tint);font-weight:700;color:var(--brand-dark)}
tr.best td{background:#F0F9EB;font-weight:600}
.note{background:var(--brand-tint);border-left:3px solid var(--brand);
padding:9px 13px;margin:10px 0;font-size:12px;border-radius:0 6px 6px 0}
.warnbox{background:#FEF6E7;border-left:3px solid var(--warn);padding:10px 14px;margin:12px 0;font-size:12px}
.failbox{background:#FDECEC;border-left:4px solid var(--fail);padding:12px 16px;
margin:16px 0;font-size:13px;font-weight:600;color:var(--fail)}
.small{font-size:10.5px;color:var(--muted)}
.fig{background:var(--surface);border:1px solid var(--hairline);border-radius:10px;
padding:14px;margin:12px 0}
.figcap{font-size:10.5px;color:var(--muted);margin-top:6px;text-align:center}
.devgrid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:12px 0}
.devc{background:#fff;border:1px solid var(--hairline);border-radius:9px;
padding:10px 12px;border-top:2.5px solid var(--brand);min-width:0}
.devc .t{display:flex;justify-content:space-between;align-items:baseline}
.devc .t b{font-size:11.5px;color:var(--ink)}
.devc .t span{font-size:9px;color:#8b949e}
.devc .r{font-family:'IBM Plex Mono',monospace;font-size:14.5px;font-weight:700;
color:var(--brand-dark);margin:3px 0 5px}
.devc .s{display:flex;justify-content:space-between;font-size:10px;color:#57606a;line-height:1.5}
.tag{display:inline-block;background:var(--panel);color:var(--muted);border-radius:4px;
padding:1px 6px;font-size:9.5px;margin-left:5px;font-family:monospace}
.footer{margin-top:34px;border-top:1px solid var(--rule);padding-top:12px;font-size:10.5px;color:var(--muted)}
@media print{body{background:#fff}.wrap{max-width:100%;padding:0}
.toc{display:none}.cover{box-shadow:none}.kpi{box-shadow:none}
table{break-inside:avoid}h2{break-after:avoid}.fig{break-inside:avoid}}
"""


# ---------------- 数字格式（IBCS UNIFY） ----------------
def money(v) -> str:
    if v is None:
        return "—"
    try:
        v = float(v)
    except (TypeError, ValueError):
        return str(v)
    if v != v:
        return "NaN"
    av = abs(v)
    if av >= 1e8:
        return f"{v/1e8:,.2f} 亿元"
    if av >= 1e4:
        return f"{v/1e4:,.1f} 万元"
    return f"{v:,.0f} 元"


def num(v, nd=1) -> str:
    if v is None:
        return "—"
    try:
        v = float(v)
    except (TypeError, ValueError):
        return str(v)
    if v != v:
        return "NaN"
    return f"{v:,.{nd}f}"


def pct(v, nd=1) -> str:
    if v is None:
        return "—"
    try:
        return f"{float(v)*100:.{nd}f}%"
    except (TypeError, ValueError):
        return str(v)


def _kpi_table(kpi: Dict) -> str:
    rows = "".join(
        f"<tr><td>{k}</td><td class='num'>{num(v,2) if isinstance(v,(int,float)) else v}</td></tr>"
        for k, v in kpi.items() if not isinstance(v, dict))
    return f"<table><tr><th>指标</th><th class='num'>值</th></tr>{rows}</table>"


def _econ_table(econ: Dict) -> str:
    rows = ""
    for k, v in econ.items():
        if isinstance(v, (int, float)):
            val = money(v) if ("cny" in k or "cost" in k) else num(v, 2)
            rows += f"<tr><td>{k}</td><td class='num'>{val}</td></tr>"
    return f"<table><tr><th>经济指标</th><th class='num'>值</th></tr>{rows}</table>"


def _cost_breakdown(econ: Dict) -> str:
    """HOMER 口径成本明细：组件 × 投资/寿命/年运维 + 合计与收益。"""
    items: List[Dict] = econ.get("capex_items") or []
    if not items:
        return "<p class='small'>本场景无组件级投资明细（见经济性汇总表）。</p>"
    body = ""
    for it in items:
        body += (f"<tr><td>{it['label']}</td>"
                 f"<td class='num'>{money(it['capex'])}</td>"
                 f"<td class='num'>{num(it['life_years'],0)} 年</td>"
                 f"<td class='num'>{money(it['opex_annual'])}</td></tr>")
    capex_total = sum(float(it["capex"]) for it in items)
    opex_total = sum(float(it["opex_annual"]) for it in items)
    body += (f"<tr class='total'><td>合计（投资现值含替换）</td>"
             f"<td class='num'>{money(capex_total)}</td><td></td>"
             f"<td class='num'>{money(opex_total)}</td></tr>")
    rev = ""
    if econ.get("nh3_revenue_pv_cny") is not None:
        rev += (f"<tr><td>氨收入现值（抵减）</td><td class='num'>−{money(econ['nh3_revenue_pv_cny'])}</td>"
                f"<td></td><td></td></tr>")
    if econ.get("carbon_revenue_pv_cny") is not None:
        rev += (f"<tr><td>减碳收益现值（抵减）</td><td class='num'>−{money(econ['carbon_revenue_pv_cny'])}</td>"
                f"<td></td><td></td></tr>")
    return (f"<table><tr><th>组件</th><th class='num'>初始投资</th>"
            f"<th class='num'>寿命</th><th class='num'>年运维</th></tr>{body}{rev}</table>"
            "<p class='small'>口径：HOMER 五类成本（初始投资/替换/残值/运维/燃料）中的组件明细；"
            "替换与残值已计入 NPC 现值。净 NPC = 总成本现值 − 各项收益现值。</p>")


def _h2_breakdown(kpi: Dict) -> str:
    """发电/制氢明细表（HOMER Simulation Results 风格）。"""
    rows = ""
    renew = kpi.get("e_renew_kwh")
    if renew:
        rows += (f"<tr><td>可再生发电量合计</td><td class='num'>{num(renew,0)} kWh</td>"
                 f"<td class='num'>100%</td></tr>")
    by_tech = kpi.get("h2_by_tech_kg") or {}
    if by_tech:
        total = sum(by_tech.values())
        for tech, v in by_tech.items():
            share = (v / total * 100) if total > 0 else 0.0
            rows += (f"<tr><td>{tech.upper()} 电解产氢</td>"
                     f"<td class='num'>{num(v,1)} kg</td>"
                     f"<td class='num'>{share:.1f}%</td></tr>")
        rows += (f"<tr class='total'><td>总产氢（入罐口径）</td>"
                 f"<td class='num'>{num(total,1)} kg</td><td class='num'>100%</td></tr>")
    if kpi.get("nh3_annual_t") is not None:
        rows += (f"<tr><td>合成氨产量</td><td class='num'>{num(kpi['nh3_annual_t'],1)} t</td>"
                 f"<td class='num'>HB 利用率 {pct(kpi.get('hb_capacity_factor',0))}</td></tr>")
    if kpi.get("grid_import_kwh") is not None:
        rows += (f"<tr><td>电网购电 / 售电</td>"
                 f"<td class='num'>{num(kpi.get('grid_import_kwh',0),0)} / "
                 f"{num(kpi.get('grid_export_kwh',0),0)} kWh</td>"
                 f"<td class='num'>失电 {num(kpi.get('unmet_kwh',0),1)} kWh</td></tr>")
    return (f"<table><tr><th>项目</th><th class='num'>数量</th>"
            f"<th class='num'>占比/备注</th></tr>{rows}</table>")


def _opt_table(opt_rows):
    if not opt_rows:
        return "<p class='small'>未执行容量优化</p>"
    cols = list(opt_rows[0].keys())
    head = "".join(f"<th>{c}</th>" for c in cols)
    body_rows = []
    for i, r in enumerate(opt_rows):
        tds = "".join(
            f"<td>{f'{r[c]:,.0f}' if isinstance(r[c], (int, float)) and abs(r[c]) > 100 else r[c]}</td>"
            for c in cols)
        cls = " class='best'" if i == 0 else ""
        body_rows.append(f"<tr{cls}>{tds}</tr>")
    return (f"<table><tr>{head}</tr>{''.join(body_rows)}</table>"
            "<p class='small'>穷举+可行性过滤+Total NPC 升序（HOMER 口径）；首行为最优配置（高亮）。"
            "复核列为长周期复核结果。应用最优配置请提交对应变更单。</p>")


def _param_table(param_card: Dict) -> str:
    from kernel.hyflow.registry import load_registry
    reg = load_registry()
    levels = param_card.get("levels", {})
    groups: Dict[str, List] = {}
    for k, v in sorted(param_card.get("params", {}).items()):
        groups.setdefault(cn_category(k) or "其他", []).append((k, v))
    out = []
    for cat, items in groups.items():
        out.append(f"<h3>{cat}</h3>")
        rows = ""
        for k, v in items:
            unit = reg.spec(k).unit if k in reg.specs else ""
            lv = levels.get(k, "")
            lv_badge = f"<span class='tag'>{lv}</span>" if lv else ""
            rows += (f"<tr><td>{cn_name(k)}<br><span class='small'>{k}</span></td>"
                     f"<td class='num'>{num(v,3) if isinstance(v,(int,float)) else v}</td>"
                     f"<td>{unit}</td><td>{lv_badge}</td></tr>")
        out.append(f"<table><tr><th>参数（中文 / canonical）</th>"
                   f"<th class='num'>值</th><th>单位</th><th>等级</th></tr>{rows}</table>")
    return "".join(out)


def _plot_divs(series: Dict) -> str:
    if not series or all(len(v) == 0 for v in series.values()):
        return "<p class='small'>本报告未嵌入逐时序列（快速模式）。</p>"
    try:
        import plotly.graph_objects as go
        import plotly.io as pio
    except ImportError:
        return "<div class='note'>Plotly 未安装——图表省略（表格数据完整）</div>"
    html_parts = []
    for key, label in [("pv_kw", "光伏出力 kW"), ("wind_kw", "风电出力 kW"),
                       ("pem_kw", "电解总功率 kW"), ("h2_store_level_kg", "储氢罐位 kg"),
                       ("nh3_t_per_h", "合成氨产量 t/h")]:
        if key not in series or len(series[key]) == 0:
            continue
        fig = go.Figure(go.Scatter(x=list(range(len(series[key]))),
                                   y=list(series[key]), name=label,
                                   line=dict(width=1.1, color="#16489D")))
        fig.update_layout(title=f"{label}（逐时，{len(series[key])}h）", height=250,
                          margin=dict(l=46, r=16, t=38, b=30),
                          xaxis_title="小时", template="plotly_white",
                          font=dict(family="Microsoft YaHei", size=11))
        html_parts.append(pio.to_html(fig, include_plotlyjs=("cdn" if not html_parts else False),
                                      full_html=False, config={"displayModeBar": False}))
    return "".join(html_parts)


def _conclusion(result: Dict, econ: Dict, template: str) -> str:
    k = result.get("kpi", {})
    if template.startswith("T6"):
        return (f"本方案 <b>绿氨 {num(k.get('nh3_annual_t',0),1)} t</b>（仿真期），"
                f"净 NPC <b>{money(econ.get('npc_net_cny'))}</b>，"
                f"LCOA <b>{money(econ.get('lcoa_cny_per_t'))}/t</b>，"
                f"绿电自给率 {pct(k.get('renew_share',1))}；"
                f"合成氨装置利用率 {pct(k.get('hb_capacity_factor',0))}。"
                f"容量匹配与储氢缓冲是该场景经济性的决定因素。")
    return (f"保供率 <b>{pct(k.get('reliability',1))}</b>，"
            f"年制氢 <b>{num(k.get('h2_prod_kg',0),1)} kg</b>，"
            f"LCOE <b>{money(econ.get('lcoe_cny_per_kwh'))}/kWh</b>，"
            f"总 NPC {money(econ.get('total_npc_cny'))}。")


def _recall_html(description: str, param_card: Dict, orders, devices=None) -> str:
    """需求回顾 Recall（导出文件 §0）：用户目标 / 设备卡片 / 确认参数 / 先验 / 变更 / 目标口径。"""
    params = param_card.get("params", {})
    levels = param_card.get("levels", {})
    from kernel.hyflow.registry import load_registry
    reg = load_registry()
    defaults = reg.defaults()
    client_rows, priori_n = [], 0
    for k, v in sorted(params.items()):
        if k not in reg.specs:
            continue
        spec = reg.spec(k)
        is_default = abs(float(v) - defaults.get(k, float(v))) < 1e-12
        if levels.get(k, "").startswith("A") and not is_default:
            client_rows.append(
                f"<tr><td>{cn_name(k)}<br><span class='small'>{k}</span></td>"
                f"<td class='num'>{num(v, 3)} {spec.unit}</td></tr>")
        else:
            priori_n += 1
    dev_grid = cards_grid_html(devices) if devices else ""
    changes = "".join(f"<li>{o.get('echo', o.get('msg', ''))}"
                      f" {'✅' if o.get('confirmed') else '（未确认）'}</li>"
                      for o in (orders or [])) or "<li>无</li>"
    objective = ("可靠性约束下全周期净现值成本（NPC）最优，经济口径含氨收入与减碳收益现值。"
                 if (param_card.get("template", "") or "").startswith("T6")
                 else "保供率硬约束下总 NPC 最优（离网优先保障供电）。")
    return f"""
<div class="note">⚠️ 以下为平台对您需求的复述（Requirements Recall）。如与您的意图不符，请在签收（G5）前提交变更。</div>
<h3>您提供的项目目标</h3>
<p style="font-size:14px">{description}</p>
<div class="small mono">场景 {param_card.get('scenario', '-')} · 模板
{param_card.get('template', '-')} · 参数完整度
{round((param_card.get('completeness') or 0) * 100)}%</div>
<h3>您确认的关键参数（A 级 · 客户提供）</h3>
<table><tr><th>参数（中文 / canonical）</th><th class='num'>值（单位）</th></tr>
{''.join(client_rows)}</table>
<p class='small'>其余 {priori_n} 项采用平台先验/注册表默认（等级与出处见参数清单章节）。</p>
<h3>方案目标与约束</h3><p>{objective}</p>
<h3>会话中的变更</h3><ul>{changes}</ul>
"""


def render_html_report(session_id: str, description: str, result: Dict,
                       param_card: Dict, gap_report: Dict,
                       orders=None, econ: Dict = None,
                       opt_table=None,
                       llm_model: str = "规则模式（未接入 LLM）") -> str:
    """自包含 HTML 报告 v3（知识库驱动，含需求 Recall）。"""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    cons = result.get("cons_passed", False)
    cons_badge = "PASS" if cons else "FAIL"
    cons_cls = "b-pass" if cons else "b-fail"
    conf = result.get("confidence", {})
    conf_grade = conf.get("grade", "C") if isinstance(conf, dict) else getattr(conf, "grade", "C")
    conf_attr = conf.get("attribution", "") if isinstance(conf, dict) else getattr(conf, "attribution", "")
    econ = econ or result.get("econ", {})
    series = result.get("series", {})
    gaps = gap_report.get("cards", [])
    unresolved = result.get("unresolved", [])
    orders = orders or []
    opt_rows = opt_table or result.get("opt_table")
    version = param_card.get("version", 1)
    scenario = param_card.get("scenario", "-")
    template = param_card.get("template", "-")
    kpi = result.get("kpi", {})
    logo_uri = logo_data_uri()
    devices = devices_data(param_card.get("params", {}), kpi, template)
    final_plan = build_final_plan(param_card.get("params", {}), kpi, template, opt_rows)

    # 摘要 KPI 卡（按场景选四项）
    if template.startswith("T6"):
        cards = [("净 NPC", money(econ.get("npc_net_cny")), "全周期净现值成本"),
                 ("LCOA", f"{money(econ.get('lcoa_cny_per_t'))}/t", "平准化氨成本"),
                 (f"{num(kpi.get('nh3_annual_t',0),1)} t", "仿真期绿氨产量",
                  f"HB 利用率 {pct(kpi.get('hb_capacity_factor',0))}"),
                 (pct(kpi.get("renew_share",1)), "绿电自给率",
                  f"失电 {num(kpi.get('unmet_kwh',0),1)} kWh")]
    else:
        cards = [(pct(kpi.get("reliability",1)), "保供率", "可靠性约束优先"),
                 (f"{money(econ.get('lcoe_cny_per_kwh'))}/kWh", "LCOE", "平准化度电成本"),
                 (f"{num(kpi.get('h2_prod_kg',0),1)} kg", "年制氢量", "入罐口径"),
                 (money(econ.get("total_npc_cny")), "总 NPC", "全周期净现值成本")]
    kpi_html = "".join(
        f"<div class='kpi'><div class='v'>{v}</div><div class='l'>{l}</div>"
        f"<div class='u'>{u}</div></div>" for v, l, u in cards)
    final_changes = "".join(
        f"<span class='tag'>{c['cn']}：{num(c['from'], 2)} → <b>{num(c['to'], 2)}</b></span>"
        for c in final_plan["changed"])
    final_metrics = final_plan["metrics"]
    final_summary = (
        f"复核净 NPC <b>{money(final_metrics['npc_cny'])}</b>"
        f" ｜ 保供率 <b>{pct(final_metrics['reliability'])}</b>"
        if final_plan["source"] == "optimization" else "当前签收工况"
    )

    return f"""<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sysmods AI 计算报告 {session_id}</title><style>{_CSS}</style></head><body>
<div class="wrap">

<div class="cover">
<img class="logo" src="{logo_uri}" alt="Sysmods AI">
<div class="sub">分布式氢能方案引擎 · <span style="color:var(--brand)">AI</span></div>
<h1>分布式氢能方案计算报告</h1>
<div class="meta mono">
会话 {session_id} ｜ 生成 {now} ｜ 版本 V{version}（已签收锁定）<br>
{description}<br>
场景 {scenario} ｜ 模板 {template} ｜ 参数完整度 {param_card.get('completeness','-')}<br>
交互与编排：{llm_model} ｜ 全部物理数值由 Sysmods AI 服务端确定性内核计算产生
</div>
<div class="badges">
<span class="badge {cons_cls}">守恒审计 {cons_badge}</span>
<span class="badge b-{conf_grade.lower()}">置信度 {conf_grade}</span>
<span class="badge b-ver">置信度归因：{conf_attr}</span>
</div>
<div class="conclusion">{_conclusion(result, econ, template)}</div>
</div>

{'' if cons else "<div class='failbox'>守恒审计未通过——本报告结果不可用，请先完成异常处置（G3）。</div>"}

<div class="kpis">{kpi_html}</div>

<div class="toc">目录：
<a href="#s0">0 需求回顾</a><a href="#s1">1 项目</a><a href="#s2">2 最终方案</a><a href="#s3">3 明细</a>
<a href="#s4">4 经济性</a><a href="#s5">5 优化</a><a href="#s6">6 时序</a>
<a href="#s7">7 参数</a><a href="#s8">8 变更史</a><a href="#s9">9 盲区</a><a href="#s10">10 声明</a>
</div>

<h2 id="s0"><span class="num">0.</span>需求回顾 Requirements Recall</h2>
{_recall_html(description, param_card, orders, devices)}
<h3>当前输入设备（需求参数）</h3>
<div class="devgrid">{cards_grid_html(devices)}</div>

<h2 id="s1"><span class="num">1.</span>项目描述</h2>
<p>{description}</p>
<p class="small">场景识别：{scenario} ｜ 模板：{template} ｜ 参数完整度：{param_card.get('completeness','-')}</p>

<h2 id="s2"><span class="num">2.</span>最终方案与系统架构 Final Scheme & Architecture</h2>
<div class="note"><b>{final_plan['label']}</b> ｜ {final_summary}<br>
{final_changes or '设备参数与当前签收工况一致。'}<br>
<span class="small">{final_plan['note']}</span></div>
<h3>最终方案设备卡（出现哪些设备就渲染哪些卡片）</h3>
<div class="devgrid">{cards_grid_html(final_plan['devices'])}</div>
<div class="fig">{final_plan['diagram_svg']}<div class="figcap">图 1 · 最终方案系统架构（按最终方案参数动态生成；电=蓝 / 氢=绿 / 热=橙 / 物料=灰）</div></div>
<h3>签收工况 KPI</h3>
{_kpi_table({k: v for k, v in kpi.items() if k != 'h2_by_tech_kg'})}

<h2 id="s3"><span class="num">3.</span>发电 / 制氢明细</h2>
{_h2_breakdown(kpi)}

<h2 id="s4"><span class="num">4.</span>经济性</h2>
{_econ_table({k: v for k, v in econ.items() if isinstance(v,(int,float))})}
<h3>成本明细（组件 × 投资 / 寿命 / 年运维）</h3>
{_cost_breakdown(econ)}

<h2 id="s5"><span class="num">5.</span>容量配置优化（穷举 + NPC 排序）</h2>
{_opt_table(opt_rows)}

<h2 id="s6"><span class="num">6.</span>逐时序列</h2>
{_plot_divs(series)}

<h2 id="s7"><span class="num">7.</span>关键参数（中文 / canonical / 单位 / 等级）</h2>
{_param_table(param_card)}
<p class="small">完整带出处/裁决链的参数表见 Excel 计算书（输入参数表）。等级：A=客户确认+校验通过；B=可靠来源；C=先验（需关注）。</p>

<h2 id="s8"><span class="num">8.</span>变更记录（版本链）</h2>
<table><tr><th>#</th><th>变更</th><th>状态</th></tr>
{"".join(f"<tr><td>{i+1}</td><td>{o.get('echo', o.get('msg',''))}</td><td>{'已确认' if o.get('confirmed') else '待确认'}</td></tr>" for i, o in enumerate(orders)) or "<tr><td colspan=3>无变更记录</td></tr>"}</table>

<h2 id="s9"><span class="num">9.</span>模型盲区提示（外挂建议卡）</h2>
<div class="note">以下因素在仿真边界外——影响方向已标注，数值须人工确认后回填（转 C 级先验）。</div>
<table><tr><th>主题</th><th>模型覆盖</th><th>影响</th><th>建议</th></tr>
{"".join(f"<tr><td>{c['topic']}</td><td>{c['covered_by_model']}</td><td>{c['impact']}</td><td>{c['advice']}</td></tr>" for c in gaps) or "<tr><td colspan=4>无</td></tr>"}</table>

<h2 id="s10"><span class="num">10.</span>未决问题与声明</h2>
{"".join(f"<li>{q}</li>" for q in unresolved) or "<p class='small'>无未决问题（全部参数达决策精度或按先验标注）。</p>"}
<p class="small">本报告全部数值由 Sysmods AI 服务端确定性内核计算产生（LLM 不产生任何计算结果）；
结果供投资决策参考，详细设计须注册工程师复核。守恒审计：电/氢平衡年误差门限 0.5%，
本报告结论 {'通过' if cons else '未通过（结果不可用，见守恒报告）'}。
导出格式：本 HTML 自包含文件可直接浏览器打开/打印为 PDF；Excel 计算书（带公式可审计）另行下载。</p>
<div class="footer">Sysmods AI · kb-homer-v1.0 / kb-ibcs-v1.0 / kb-tokens-v1.0 ｜ 报告由交付物 Agent 按知识库渲染</div>
</div>
</body></html>"""
