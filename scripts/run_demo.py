# -*- coding: utf-8 -*-
"""Phase 0 演示：高原示范站默认参数全年 8760h 端到端 + Excel 计算书导出。
运行: python scripts/run_demo.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from kernel.hyflow.templates.t1_offgrid import run_t1_scenario
from services.reports.export_excel import export_calcbook

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output")


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    t0 = time.time()
    result = run_t1_scenario()  # 8760h，canonical 注册表默认参数
    dt = time.time() - t0

    k = result.kpi
    print("=" * 62)
    print("Sysmods AI · Phase 0 内核切片 · T1 离网光储氢电 全年运行")
    print("=" * 62)
    print(f"守恒审计 : {result.cons_report.summary()}")
    print(f"置信度   : {result.confidence.grade} 级 —— {result.confidence.attribution}")
    print(f"         提升: {result.confidence.improvement}")
    print("-" * 62)
    print(f"年光伏发电   e_pv      = {k['e_pv_kwh']:>12.1f} kWh")
    print(f"年负荷需求   e_load    = {k['e_load_kwh']:>12.1f} kWh")
    print(f"年供给       e_served  = {k['e_served_kwh']:>12.1f} kWh  (保供率 {k['reliability']*100:.2f}%)")
    print(f"年失电       e_unmet   = {k['e_unmet_kwh']:>12.1f} kWh")
    print(f"年弃电       e_curtail = {k['e_curtail_kwh']:>12.1f} kWh  (弃电率 {k['curtail_ratio']*100:.1f}%)")
    print(f"年制氢       h2_prod   = {k['h2_prod_kg']:>12.2f} kg")
    print(f"年耗氢(FC)   h2_cons   = {k['h2_cons_kg']:>12.2f} kg   (FC 年发电 {k['e_fc_kwh']:.1f} kWh)")
    r2r = k['roundtrip_eff']
    if r2r != r2r:  # NaN
        print(f"电→氢→电往返效率       = 不适用（{k['roundtrip_note']}）")
    else:
        print(f"电→氢→电往返效率       = {r2r*100:.1f}%")
    print("-" * 62)
    e = result.econ
    print(f"Total NPC   = CNY {e['total_npc_cny']:,.0f}")
    print(f"LCOE        = CNY {e['lcoe_cny_per_kwh']:.3f}/kWh   (对标柴油发电 1.5-2.5 元/kWh)")
    print(f"LCOH        = CNY {e['lcoh_cny_per_kg']:,.0f}/kg     ({e['lcoh_note']})")
    print("-" * 62)
    print(f"8760h 仿真耗时: {dt:.2f}s（含守恒审计与置信度评级）")

    out = os.path.join(OUT_DIR, "高原示范站_T1_计算书.xlsx")
    export_calcbook(result, out)
    print(f"Excel 计算书已导出: {os.path.abspath(out)}")
    print(f"  - 输入参数表: canonical 名/值/单位/等级/裁决链/出处")
    print(f"  - 时序表: 8760h × 13 列")
    print(f"  - KPI 表: 核心量带 SUM 公式(可审计)，置信度与守恒结论在列")

    # —— PMHT 固态储氢模式对照 ——
    print("=" * 62)
    print("PMHT 固态储氢模式（Peq 门控 · 床温演化 · 吸放氢热账）")
    print("=" * 62)
    t1 = time.time()
    rm = run_t1_scenario(storage="mh")
    dtm = time.time() - t1
    rep = rm.cons_report
    print(f"守恒审计 : {rep.summary()}")
    print(f"年制氢   : {rm.kpi['h2_prod_kg']:.2f} kg（线性罐: {k['h2_prod_kg']:.2f} kg）")
    print(f"年耗氢   : {rm.kpi['h2_cons_kg']:.2f} kg（线性罐: {k['h2_cons_kg']:.2f} kg）")
    print(f"失电     : {rm.kpi['e_unmet_kwh']:.1f} kWh（线性罐: {k['e_unmet_kwh']:.1f} kWh）")
    print(f"床温范围 : {min(rm.mh_t_bed_k):.2f} ~ {max(rm.mh_t_bed_k):.2f} K（环境 283.15K）")
    q = rm.mh_q_rxn_w
    print(f"反应热账 : 峰值放热 {q.max():.0f} W / 峰值吸热 {q.min():.0f} W")
    print(f"（Peq 门控：3MPa 供氢下平衡容量≈96% 罐容，电解在近满时被热力学拒收→弃电）")
    print(f"耗时     : {dtm:.2f}s（含 Peq 二分与床温解析推进）")


if __name__ == "__main__":
    main()
