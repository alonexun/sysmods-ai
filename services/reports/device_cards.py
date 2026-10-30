# -*- coding: utf-8 -*-
"""设备卡片组件库（模块化）：报告/前端出现哪些设备，就渲染哪些设备卡片。

知识库依据：agents/deliverable/kb/device_card_library.md（每设备的卡片字段定义）
+ report_design_tokens.md v1.1（紧凑密度/品牌绿/logo 规则）。

- 注册表 DEVICE_SPECS：每设备的中英文名、图标、额定参数、specs 槽位
  （source: param=参数卡值 / kpi=仿真结果值；取不到的行自动省略）；
- devices_data()：按参数卡判定启用设备 → 结构化 JSON（React 卡片网格数据源）；
- cards_grid_html()：HTML 紧凑网格（4 列小卡，自包含，用于导出报告）。
"""
from typing import Dict, List

BRAND_GREEN = "#52C41A"          # 品牌亮绿：只用于顶边/小面积点缀，不作正文色
BRAND_GREEN_DARK = "#173F35"     # 深森林绿：正文强调/关键值，白底高对比
INK = "#1D2723"

# 设备类别色只用于图标与小面积识别，正文始终保持墨色。
DEVICE_TONES = {
    "pv": "solar", "wind": "wind", "bess": "storage", "h2store": "storage",
    "mh": "storage", "pemwe": "hydrogen", "alk": "hydrogen",
    "aem": "hydrogen", "soec": "hydrogen", "fc": "hydrogen",
    "sofc": "hydrogen", "hb": "chemical", "asu": "chemical", "grid": "grid",
}
DEVICE_CODES = {
    "pv": "PV", "wind": "WT", "bess": "BAT", "pemwe": "PEM", "alk": "ALK",
    "aem": "AEM", "soec": "SOEC", "h2store": "H2", "mh": "MH",
    "fc": "FC", "sofc": "SOFC", "hb": "HB", "asu": "ASU", "grid": "GRID",
}
TONE_COLORS = {
    "solar": "#B7791F", "wind": "#2B6CB0", "storage": "#7257A8",
    "hydrogen": "#0E7C86", "chemical": "#A7513C", "grid": "#52606D",
}

# 设备卡片注册表（模块化：新设备=新条目）
DEVICE_SPECS: Dict[str, Dict] = {
    "pv": {
        "cn": "光伏阵列", "en": "PV Array", "icon": "☀",
        "param": "pv.capacity_kw", "unit": "kW",
        "specs": [("综合折减", "pv.derate", "", "param"),
                  ("年发电量", "e_pv_kwh", "kWh", "kpi"),
                  ("可再生发电(风光合计)", "e_renew_kwh", "kWh", "kpi")],
    },
    "wind": {
        "cn": "风电机组", "en": "Wind Turbine", "icon": "🌀",
        "param": "wind.capacity_kw", "unit": "kW",
        "specs": [("切入/额定风速", "wind.cut_in_ms", "m/s", "param"),
                  ("切出风速", "wind.cut_out_ms", "m/s", "param"),
                  ("可再生发电(风光合计)", "e_renew_kwh", "kWh", "kpi")],
    },
    "bess": {
        "cn": "锂电池储能", "en": "Battery Storage", "icon": "🔋",
        "param": "bess.capacity_kwh", "unit": "kWh",
        "specs": [("额定功率", "bess.power_kw", "kW", "param"),
                  ("往返效率", "bess.eff_roundtrip", "", "param"),
                  ("SOC 窗口", "bess.soc_min", "-", "param")],
    },
    "pemwe": {
        "cn": "PEM 电解槽", "en": "PEM Electrolyzer", "icon": "💧",
        "param": "pemwe.rated_kw", "unit": "kW",
        "specs": [("效率(LHV)", "pemwe.eff_lhv", "", "param"),
                  ("最小负荷", "pemwe.min_load_ratio", "", "param"),
                  ("年产氢", "h2_prod_annual_kg", "kg", "kpi")],
    },
    "alk": {
        "cn": "碱性电解槽", "en": "ALK Electrolyzer", "icon": "💧",
        "param": "alk.rated_kw", "unit": "kW",
        "specs": [("效率(LHV)", "alk.eff_lhv", "", "param"),
                  ("最小负荷", "alk.min_load_ratio", "", "param"),
                  ("年产氢", "h2_prod_annual_kg", "kg", "kpi")],
    },
    "aem": {
        "cn": "AEM 电解槽", "en": "AEM Electrolyzer", "icon": "💧",
        "param": "aem.rated_kw", "unit": "kW",
        "specs": [("效率(LHV)", "aem.eff_lhv", "", "param"),
                  ("最小负荷", "aem.min_load_ratio", "", "param"),
                  ("年产氢", "h2_prod_annual_kg", "kg", "kpi")],
    },
    "soec": {
        "cn": "SOEC 高温电解", "en": "SOEC Electrolyzer", "icon": "🔥",
        "param": "soec.rated_kw", "unit": "kW",
        "specs": [("热中性效率", "soec.eff_lhv", "", "param"),
                  ("缺热降额效率", "soec.eff_lhv_no_heat", "", "param"),
                  ("最小负荷", "soec.min_load_ratio", "", "param")],
    },
    "h2store": {
        "cn": "储氢单元", "en": "H2 Storage", "icon": "🫙",
        "param": "h2store.capacity_kg", "unit": "kg",
        "specs": [("初始存量", "h2store.level_init_kg", "kg", "param"),
                  ("耗氢(合成/FC)", "h2_to_hb_annual_kg", "kg", "kpi"),
                  ("罐位波动", "h2_buffer_util_kg", "kg", "kpi")],
    },
    "mh": {
        "cn": "固态储氢床", "en": "Metal Hydride Bed", "icon": "🧱",
        "param": "mh.bed_mass_kg", "unit": "kg",
        "specs": [("传热系数", "mh.uth_w_per_k", "W/K", "param"),
                  ("供氢压力", "mh.p_supply_pa", "Pa", "param"),
                  ("母线压力", "mh.p_bus_pa", "Pa", "param")],
    },
    "fc": {
        "cn": "燃料电池", "en": "Fuel Cell (PEM)", "icon": "⚡",
        "param": "fc.rated_kw", "unit": "kW",
        "specs": [("效率(LHV)", "fc.eff_lhv", "", "param"),
                  ("年发电", "e_fc_kwh", "kWh", "kpi")],
    },
    "sofc": {
        "cn": "SOFC 燃料电池", "en": "SOFC", "icon": "⚡",
        "param": "sofc.rated_kw", "unit": "kW",
        "specs": [("效率(LHV)", "sofc.eff_lhv", "", "param"),
                  ("余热/发电比", "sofc.heat_to_power_ratio", "", "param"),
                  ("最小负荷", "sofc.min_load_ratio", "", "param")],
    },
    "hb": {
        "cn": "合成氨装置", "en": "Haber-Bosch (NH3)", "icon": "🧪",
        "param": "chem.nh3.capacity_t_per_h", "unit": "t/h",
        "specs": [("吨氨耗氢", "chem.nh3.h2_per_t_kg", "kg", "param"),
                  ("最小负荷", "chem.nh3.min_load", "", "param"),
                  ("年产量", "nh3_annual_t", "t", "kpi")],
    },
    "asu": {
        "cn": "空分制氮", "en": "ASU (N2)", "icon": " ❄",
        "param": "chem.asu.lec_kwh_per_kg_n2", "unit": "kWh/kg",
        "specs": [("氮需求(随氨)", "n2_used_annual_kg", "kg", "kpi")],
    },
    "grid": {
        "cn": "电网接口", "en": "Grid Interface", "icon": "🔌",
        "param": "grid.max_import_kw", "unit": "kW",
        "specs": [("购电/售电", "grid_import_kwh", "kWh", "kpi"),
                  ("失电", "unmet_kwh", "kWh", "kpi")],
    },
}

# 模板 → 基础启用集（额外设备按 param>0 判定）
_TEMPLATE_BASE = {
    "T1": ["pv", "bess", "pemwe", "h2store", "fc"],
    "T2": ["pv", "pemwe", "h2store"],
    "T6": ["pv", "wind", "bess", "pemwe", "h2store", "hb", "asu"],
}


def _val(source: Dict, key: str):
    return source.get(key)


def _fmt_val(v, unit=""):
    if v is None:
        return None
    try:
        v = float(v)
        if v != v:  # NaN
            return None
        s = f"{v:,.0f}" if abs(v) >= 100 else (f"{v:.3g}" if abs(v) < 10 else f"{v:,.1f}")
        return s + (f" {unit}" if unit else "")
    except (TypeError, ValueError):
        return str(v)


def devices_data(params: Dict, kpi: Dict, template: str = "T6") -> List[Dict]:
    """按参数卡判定启用设备 → 结构化卡片数据（React 网格数据源）。"""
    p = params or {}
    k = kpi or {}
    base = _TEMPLATE_BASE.get((template or "T6").split("(")[0].strip(), _TEMPLATE_BASE["T1"])
    out = []
    for key, spec in DEVICE_SPECS.items():
        rated = _val(p, spec["param"])
        if key in base:
            enabled = True
        elif rated is not None:
            try:
                enabled = float(rated) > 0
            except (TypeError, ValueError):
                enabled = False
        else:
            enabled = False
        if not enabled:
            continue
        specs = []
        for label, skey, unit, src in spec["specs"]:
            v = _val(k if src == "kpi" else p, skey)
            if src == "param" and v is None and skey in k:
                v = _val(k, skey)
            fv = _fmt_val(v, unit)
            if fv is not None:
                specs.append({"name": label, "value": fv})
        out.append({
            "key": key, "cn": spec["cn"], "en": spec["en"],
            "icon": DEVICE_CODES.get(key, key.upper()),
            "tone": DEVICE_TONES.get(key, "grid"),
            "rated": _fmt_val(rated, spec["unit"]) if rated is not None else "—",
            "specs": specs,
        })
    return out


def cards_grid_html(devices: List[Dict], cols: int = 4) -> str:
    """紧凑设备卡片网格（HTML 导出用；样式内联，遵循 design tokens v1.1）。"""
    if not devices:
        return "<p class='small'>无启用设备</p>"
    cards = []
    for d in devices:
        tone = TONE_COLORS.get(d.get("tone"), TONE_COLORS["grid"])
        spec_rows = "".join(
            f"<div style='display:flex;justify-content:space-between;font-size:10px;"
            f"color:#68746e;line-height:1.5'>"
            f"<span>{s['name']}</span><span style='font-family:monospace;color:{INK}'>{s['value']}</span></div>"
            for s in d["specs"][:3])
        cards.append(
            f"<div style='background:#fff;border:1px solid #DDE4DE;border-radius:10px;"
            f"padding:10px 12px;border-top:3px solid {tone};min-width:0'>"
            f"<div style='display:flex;justify-content:space-between;align-items:baseline;gap:6px'>"
            f"<b style='font-size:11.5px;color:{INK}'>{d['icon']} · {d['cn']}</b>"
            f"<span style='font-size:9px;color:#68746e'>{d['en']}</span></div>"
            f"<div style='font-family:monospace;font-size:15px;font-weight:700;"
            f"color:{INK};margin:3px 0 6px'>{d['rated']}</div>"
            f"{spec_rows}</div>")
    return (f"<div style='display:grid;grid-template-columns:repeat({cols},1fr);"
            f"gap:10px'>{''.join(cards)}</div>")
