# -*- coding: utf-8 -*-
"""Excel 计算书导出（V1.2 §8.1：带公式可审计——专家可逐格验算）。

三张表：输入参数(canonical+出处) / 时序 / KPI(核心量用 SUM 公式引用时序)。
导出后客户在 Excel 中改输入参数即可自行验算核心能量账。
"""
from openpyxl import Workbook
from openpyxl.utils import get_column_letter

from kernel.hyflow.registry import load_registry


def export_calcbook(result, out_path: str, param_overrides: dict = None) -> str:
    """result: kernel.hyflow.engine.T1Result"""
    reg = load_registry()
    values = reg.defaults()
    if param_overrides:
        for k, v in param_overrides.items():
            reg.validate(k, v)
            values[k] = float(v)

    wb = Workbook()

    # —— Sheet1 输入参数 ——
    ws_in = wb.active
    ws_in.title = "输入参数"
    headers = ["canonical 参数名", "值", "单位", "取值范围", "数据等级", "裁决链", "出处", "说明"]
    for c, h in enumerate(headers, 1):
        ws_in.cell(1, c, h)
    for i, (name, spec) in enumerate(reg.specs.items(), start=2):
        ws_in.cell(i, 1, name)
        ws_in.cell(i, 2, values[name])
        ws_in.cell(i, 3, spec.unit)
        ws_in.cell(i, 4, f"[{spec.range[0]}, {spec.range[1]}]")
        ws_in.cell(i, 5, spec.level)
        ws_in.cell(i, 6, spec.chain)
        ws_in.cell(i, 7, spec.source)
        ws_in.cell(i, 8, spec.desc)
    ws_in.column_dimensions["A"].width = 26
    for col in "BCDEFGH":
        ws_in.column_dimensions[col].width = 14
    ws_in.column_dimensions["G"].width = 40
    ws_in.column_dimensions["H"].width = 34

    # —— Sheet2 时序 ——
    ws_ts = wb.create_sheet("时序")
    cols = ["hour", "pv_kw", "load_kw", "bess_chg_kw", "bess_dis_kw", "bess_soc",
            "pem_kw", "h2_prod_kg_per_h", "h2_store_level_kg", "h2_cons_kg_per_h",
            "fc_kw", "curtail_kw", "unmet_kw"]
    series = [result.hours, result.pv_kw, result.load_kw, result.bess_chg_kw,
              result.bess_dis_kw, result.bess_soc, result.pem_kw,
              result.h2_prod_kg_per_h, result.h2_store_level_kg,
              result.h2_cons_kg_per_h, result.fc_kw, result.curtail_kw,
              result.unmet_kw]
    for c, h in enumerate(cols, 1):
        ws_ts.cell(1, c, h)
    n = len(result.hours)
    for t in range(n):
        for c, arr in enumerate(series, 1):
            v = arr[t]
            ws_ts.cell(t + 2, c, float(v))

    # —— Sheet3 KPI（公式可审计） ——
    ws_kpi = wb.create_sheet("KPI")
    ws_kpi.cell(1, 1, "指标")
    ws_kpi.cell(1, 2, "值")
    ws_kpi.cell(1, 3, "说明")
    rng = lambda col: f"时序!{get_column_letter(col)}2:{get_column_letter(col)}{n + 1}"
    r2, r3, r4 = 2, 3, 4  # SUM 范围行号（sheet 行 2..n+1）
    kpi_rows = [
        ("e_pv_kwh", f"=SUM({rng(2)})", "光伏年发电量(kWh)=时序 pv_kw 之和"),
        ("e_load_kwh", f"=SUM({rng(3)})", "负荷年需求(kWh)"),
        ("e_unmet_kwh", f"=SUM({rng(13)})", "年失电量(kWh)"),
        ("e_served_kwh", f"=B3-B4", "年供给电量=负荷-失电"),
        ("reliability", f"=1-B4/B3", "保供率=1-失电/负荷"),
        ("h2_prod_kg", f"=SUM({rng(8)})", "年制氢量(kg)"),
        ("h2_cons_kg", f"=SUM({rng(10)})", "年耗氢量(kg)"),
        ("e_fc_kwh", f"=SUM({rng(11)})", "FC 年发电量(kWh)"),
        ("e_curtail_kwh", f"=SUM({rng(12)})", "年弃电量(kWh)"),
        ("total_npc_cny", result.econ.get("total_npc_cny"),
         "总净现值成本(CNY, HOMER 口径, kernel/hyflow/econ/npc.py 计算)"),
        ("lcoe_cny_per_kwh", result.econ.get("lcoe_cny_per_kwh"),
         "度电成本(CNY/kWh)=NPC×CRF/年供给电量"),
        ("lcoh_cny_per_kg", result.econ.get("lcoh_cny_per_kg"),
         "度氢成本(CNY/kg)=NPC/年制氢量(简化口径, 未扣电力外售价值)"),
        ("conservation_passed", str(result.cons_report.passed),
         "守恒审计: " + result.cons_report.summary()),
        ("confidence_grade", result.confidence.grade,
         f"置信度: {result.confidence.attribution}; 提升: {result.confidence.improvement}"),
    ]
    for i, (name, val, note) in enumerate(kpi_rows, start=2):
        ws_kpi.cell(i, 1, name)
        ws_kpi.cell(i, 2, val)
        ws_kpi.cell(i, 3, note)
    ws_kpi.column_dimensions["A"].width = 22
    ws_kpi.column_dimensions["B"].width = 18
    ws_kpi.column_dimensions["C"].width = 70

    wb.save(out_path)
    return out_path
