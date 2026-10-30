# -*- coding: utf-8 -*-
"""Phase 1 演示：绿氨（工业降碳）+ 四电网模式对比 + UQ 敏感性 + API 冒烟。
运行: python scripts/run_phase1_demo.py
"""
import os
import sys
import time as time_mod

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def main():
    from kernel.hyflow.templates.t6_ammonia import run_t6_scenario
    from kernel.hyflow.uq.sampling import run_oat, tornado

    ov = {"pv.capacity_kw": 1000.0, "wind.capacity_kw": 2000.0,
          "pemwe.rated_kw": 1500.0, "bess.capacity_kwh": 2000.0, "bess.power_kw": 500.0,
          "h2store.capacity_kg": 8000.0, "h2store.level_init_kg": 4000.0}
    print("=" * 64)
    print("Sysmods AI · Phase 1 · 绿氨场景（中国工业降碳：风光→氢→合成氨）")
    print("=" * 64)
    t0 = time_mod.time()
    r = run_t6_scenario(ov, n_days=90)
    dt = time_mod.time() - t0
    print(f"守恒审计 : {r.cons_report.summary()}")
    print(f"置信度   : {r.confidence.grade} 级 —— {r.confidence.attribution}")
    e = r.element_audit_annual
    print(f"元素审计 : N={e['N']:.2e} H={e['H']:.2e}（理论计量闭合）")
    print("-" * 64)
    k = r.kpi
    print(f"90 天合成氨   : {k['nh3_annual_t']:>10.1f} t   (HB 装机利用率 {k['hb_capacity_factor']*100:.1f}%)")
    print(f"年化绿氢      : {k['h2_prod_annual_kg']*4:>10.0f} kg  →  耗于合成 {k['h2_to_hb_annual_kg']*4:.0f} kg")
    print(f"绿电自给率    : {k['renew_share']*100:>10.1f}%")
    print("-" * 64)
    ec = r.econ
    print(f"Total NPC     : CNY {ec['npc_gross_cny']:>12,.0f}")
    print(f"氨收入现值    : CNY {ec['nh3_revenue_pv_cny']:>12,.0f}")
    print(f"减碳收益现值  : CNY {ec['carbon_revenue_pv_cny']:>12,.0f}  "
          f"(吨氨降碳 {ec['grey_nh3_co2_t_per_t']:.2f} t，年减排 {ec['co2_abatement_t_per_year']:,.0f} t)")
    print(f"LCOA          : CNY {ec['lcoa_cny_per_t']:>12,.0f}/t  (灰氨基准 ~2400-2800)")
    print(f"耗时          : {dt:.2f}s / 2160h")

    print("=" * 64)
    print("电网模式对比（90 天）：offgrid / ppa 绿电直连 / tou 分时 / spot 现货")
    print("=" * 64)
    rows = []
    for mode, extra in [("offgrid", {}), ("ppa", {"grid.max_import_kw": 300.0}),
                        ("tou", {"grid.max_import_kw": 300.0}),
                        ("spot", {"grid.max_import_kw": 300.0})]:
        o2 = dict(ov)
        o2.update(extra)
        if mode == "spot":
            # 现货模式：构造合成现货价格（双峰日曲线），直接注入 GridParams
            import numpy as np
            from kernel.hyflow.templates.t6_ammonia import build_t6_config
            from kernel.hyflow.templates.t1_offgrid import synth_ghi
            from kernel.hyflow.modules.wind import synth_wind
            from kernel.hyflow.templates.t6_ammonia import run_t6
            cfg2 = build_t6_config(o2)
            hod = np.arange(90 * 24) % 24
            spot = 0.3 + 0.4 * np.exp(-((hod - 10.5) ** 2) / 8) \
                + 0.5 * np.exp(-((hod - 19) ** 2) / 6)
            cfg2.grid.spot_price_cny_kwh = spot
            rr = run_t6(cfg2, synth_ghi(n_days=90), synth_wind(90 * 24))
        elif mode == "offgrid":
            rr = run_t6_scenario(o2, n_days=90)
        else:
            o2["grid.mode_str"] = mode
            rr = run_t6_scenario(o2, n_days=90)
        rows.append((mode, rr.kpi["grid_import_kwh"], rr.cons_report.passed,
                     rr.econ["lcoa_cny_per_t"]))
    print(f"{'模式':<10}{'购电 kWh':>12}{'守恒':>7}{'LCOA CNY/t':>12}")
    for m, imp, ok, lcoa in rows:
        print(f"{m:<10}{imp:>12,.0f}{'PASS' if ok else 'FAIL':>7}{lcoa:>12,.0f}")
    print("\n注: 本演示配置未优化（电解 1.5MW vs HB 满负荷需氢 4.5t/d，错配导致 HB 利用率低）——")
    print("    穷举+NPC 排序的容量配置优化（HOMER 口径）是下一步工作。")

    print("=" * 64)
    print("UQ 敏感性（OAT 龙卷风 Top-5：LCOA 对 C 级参数）")
    print("=" * 64)
    from kernel.hyflow.registry import load_registry
    d = dict(load_registry().defaults())
    d.update(ov)

    def sim(o):
        if "grid.mode_str" in o:
            o = {k: v for k, v in o.items() if k != "grid.mode_str"}
        rr = run_t6_scenario(o, n_days=30)
        return {"lcoa": rr.econ["lcoa_cny_per_t"], "nh3": rr.kpi["nh3_annual_t"]}

    oat = run_oat(sim, d, kpis=["lcoa"], params=[
        "pemwe.eff_lhv", "pv.derate", "chem.nh3.h2_per_t_kg",
        "chem.nh3.min_load", "econ.nh3_price_cny_per_t"], delta=0.15)
    for row in tornado(oat, "lcoa")[:5]:
        print(f"  {row['param']:<28} 敏感度 {row['sensitivity']:>10,.0f} CNY/t "
              f"(低 {row['low']:.0f} ← 基准 {row['base']:.0f} → 高 {row['high']:.0f})")
    print("\n注: 参数名后缀即 canonical 注册表出处；LLM 联网补参将按裁决链①→④更新这些先验。")


if __name__ == "__main__":
    main()
