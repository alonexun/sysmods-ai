# -*- coding: utf-8 -*-
"""系统架构示意图（SVG 动态生成）：按参数卡渲染当前方案的设备拓扑。

知识库依据：agents/deliverable/kb/report_design_tokens.md（组件色板/总线色）
与 homer_report_structure.md §1（系统架构视图）。
- 组件圆角块：中文设备名 + 额定值（仅绘制启用设备）；
- 总线色：电 #2563EB / 氢 #16A34A / 热 #EA580C / 物料 #64748B；
- T1（离网电氢电）与 T6（风光绿氨）两套布局；其他模板回退 T6。
纯 SVG 字符串：自包含、可打印、无外部依赖。
"""
from typing import Dict

E, H2, TH, MT = "#2563EB", "#16A34A", "#EA580C", "#64748B"
CAT_COLOR = {"src": "#DBEAFE", "elec": "#DCFCE7", "store": "#FEF3C7",
             "chem": "#FCE7F3", "end": "#F1F5F9"}


def _fmt(v, unit=""):
    try:
        v = float(v)
        if v >= 10000:
            return f"{v/10000:.0f}万{unit}"
        if v == int(v):
            return f"{int(v)}{unit}"
        return f"{v:.3g}{unit}"
    except (TypeError, ValueError):
        return f"{v}{unit}"


def _box(x, y, w, h, title, sub, cat):
    fc = CAT_COLOR.get(cat, "#F1F5F9")
    return (
        f'<g><rect x="{x}" y="{y}" width="{w}" height="{h}" rx="9" fill="{fc}" '
        f'stroke="#94A3B8" stroke-width="1.1"/>'
        f'<text x="{x+w/2}" y="{y+17}" text-anchor="middle" font-size="11" '
        f'font-weight="600" fill="#0F172A">{title}</text>'
        f'<text x="{x+w/2}" y="{y+32}" text-anchor="middle" font-size="9.5" '
        f'fill="#475569">{sub}</text></g>')


def _arrow(x1, y1, x2, y2, color=E, dash="", label=None, ly=None):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    s = (f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" '
         f'stroke-width="2.2"{d} marker-end="url(#ah)"/>')
    if label:
        lx = (x1 + x2) / 2
        yy = (y1 + y2) / 2 + (ly if ly is not None else -5)
        s += (f'<text x="{lx}" y="{yy}" text-anchor="middle" font-size="9" '
              f'fill="{color}">{label}</text>')
    return s


def _legend(x, y):
    items = [("电 kW", E, ""), ("氢 kg/h", H2, ""), ("热 kW", TH, "5,3"),
             ("物料", MT, "2,3")]
    out = []
    for i, (name, color, dash) in enumerate(items):
        yy = y + i * 15
        d = f' stroke-dasharray="{dash}"' if dash else ""
        out.append(f'<line x1="{x}" y1="{yy}" x2="{x+26}" y2="{yy}" '
                   f'stroke="{color}" stroke-width="2.4"{d}/>'
                   f'<text x="{x+32}" y="{yy+3}" font-size="9.5" fill="#475569">{name}</text>')
    return "".join(out)


def diagram_svg(params: Dict, template: str = "T6") -> str:
    """按参数卡生成 SVG。params 为 canonical 注册表值。"""
    p = params or {}
    t6 = (template or "T6").startswith("T6")
    W, H = 1060, 300 if t6 else 260
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
             f'width="100%" role="img" aria-label="系统架构示意图">'
             f'<defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" '
             f'markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
             f'<path d="M0,0 L10,5 L0,10 z" fill="#64748B"/></marker></defs>']

    if t6:
        # 电源 → 电总线（汇流排）
        parts.append(_box(20, 40, 130, 46, "光伏", _fmt(p.get("pv.capacity_kw", 0), " kW"), "src"))
        parts.append(_box(20, 110, 130, 46, "风电", _fmt(p.get("wind.capacity_kw", 0), " kW"), "src"))
        parts.append(_box(20, 180, 130, 46, "锂电池", _fmt(p.get("bess.capacity_kwh", 0), " kWh"), "store"))
        parts.append(_arrow(150, 63, 215, 95, E))
        parts.append(_arrow(150, 133, 215, 105, E))
        parts.append(_arrow(150, 203, 215, 120, E, label="充放"))
        parts.append(f'<rect x="215" y="80" width="16" height="60" rx="4" fill="{E}"/>'
                     f'<text x="223" y="155" text-anchor="middle" font-size="10" fill="{E}">电总线</text>')
        # 电解群（每条技术路线一个块）
        techs = [("pem", "PEM 电解", p.get("pemwe.rated_kw", 0)),
                 ("alk", "ALK 电解", p.get("alk.rated_kw", 0)),
                 ("aem", "AEM 电解", p.get("aem.rated_kw", 0)),
                 ("soec", "SOEC 电解", p.get("soec.rated_kw", 0))]
        techs = [(k, n, v) for k, n, v in techs if float(v or 0) > 0]
        y0 = 40
        for i, (k, name, v) in enumerate(techs):
            y = y0 + i * 52
            parts.append(_box(275, y, 130, 44, name, _fmt(v, " kW"), "elec"))
            parts.append(_arrow(231, 95 if i == 0 else 110, 275, y + 22, E))
        last_y = y0 + max(0, len(techs) - 1) * 52
        # 储氢 → ASU/HB
        parts.append(_box(455, 80, 130, 46, "储氢缓冲", _fmt(p.get("h2store.capacity_kg", 0), " kg"), "store"))
        for i in range(len(techs)):
            parts.append(_arrow(405, y0 + i * 52 + 22, 455, 103, H2))
        parts.append(_box(630, 30, 130, 42, "ASU 空分", "制氮 N2", "chem"))
        parts.append(_box(630, 110, 130, 46, "合成氨 HB", _fmt(p.get("chem.nh3.capacity_t_per_h", 0), " t/h"), "chem"))
        parts.append(_arrow(585, 103, 630, 133, H2, label="氢", ly=-4))
        parts.append(_arrow(695, 72, 695, 110, MT, dash="2,3", label="N2", ly=-4))
        parts.append(_box(810, 110, 110, 46, "绿氨产品", _fmt(p.get("chem.nh3.capacity_t_per_h", 0), " t/h"), "end"))
        parts.append(_arrow(760, 133, 810, 133, MT, dash="2,3", label="NH3", ly=-4))
        # 电网
        parts.append(_box(275, 220, 130, 40, "电网", "PPA/分时/现货", "src"))
        parts.append(_arrow(275, 240, 223, 140, E, dash="5,3"))
        parts.append(_legend(940, 30))
    else:
        parts.append(_box(20, 40, 130, 46, "光伏", _fmt(p.get("pv.capacity_kw", 0), " kW"), "src"))
        parts.append(_box(20, 110, 130, 46, "锂电池", _fmt(p.get("bess.capacity_kwh", 0), " kWh"), "store"))
        parts.append(_box(230, 40, 130, 46, "PEM 电解", _fmt(p.get("pemwe.rated_kw", 0), " kW"), "elec"))
        parts.append(_box(440, 40, 130, 46, "储氢", _fmt(p.get("h2store.capacity_kg", 0), " kg"), "store"))
        parts.append(_box(650, 40, 130, 46, "燃料电池", _fmt(p.get("fc.rated_kw", 0), " kW"), "elec"))
        parts.append(_box(650, 140, 130, 46, "负载", _fmt(p.get("load.avg_kw", 0), " kW"), "end"))
        parts.append(_arrow(150, 63, 230, 63, E))
        parts.append(_arrow(360, 63, 440, 63, H2))
        parts.append(_arrow(570, 63, 650, 63, H2))
        parts.append(_arrow(715, 86, 715, 140, E))
        parts.append(_arrow(150, 133, 230, 80, E, label="充放", ly=-4))
        parts.append(_arrow(295, 86, 295, 200, E, dash="5,3"))
        parts.append(_box(230, 200, 130, 40, "负载供电", "", "end"))
        parts.append(_legend(850, 40))

    parts.append("</svg>")
    return "".join(parts)
