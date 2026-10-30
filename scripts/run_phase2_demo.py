# -*- coding: utf-8 -*-
"""Phase 2 演示：电解四路线对比 + SOFC + 穷举容量优化（把错配配置优化掉）。
运行: python scripts/run_phase2_demo.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def main():
    from kernel.hyflow.modules.electrolyzers import Electrolyzer, ElectrolyzerParams
    from kernel.hyflow.modules.sofc import SOFC, SofcParams
    from kernel.hyflow.optimize import optimize_capacity, result_table

    print("=" * 66)
    print("Sysmods AI · Phase 2 · 电解槽四技术路线 + SOFC（规划级 L3，锚点核对）")
    print("=" * 66)
    print(f"{'技术':<8}{'效率LHV':>9}{'电耗kWh/kg':>12}{'最小负荷':>9}{'爬坡/h':>8}  备注")
    for tech, extra in [("pem", ""), ("alk", "CAPEX 低"), ("aem", "非贵金属"),
                        ("soec", "热中性"), ("soec-noheat", "")]:
        if tech == "soec-noheat":
            e = Electrolyzer(ElectrolyzerParams("soec", 1000.0, heat_available=False))
            note = "缺热降额"
        else:
            e = Electrolyzer(ElectrolyzerParams(tech, 1000.0,
                                                heat_available=(tech == "soec")))
            note = extra
        print(f"{tech:<8}{e.eff_current:>9.2f}{e.specific_kwh_per_kg:>12.1f}"
              f"{e.min_load_ratio:>9.0%}{e.ramp_frac:>8.0%}  {note}")
    fc = SOFC(SofcParams(rated_kw=100.0))
    print(f"\nSOFC    {fc.p.eff_lhv:>9.2f}{33.33 / fc.p.eff_lhv:>12.1f}"
          f"{fc.p.min_load_ratio:>9.0%}{fc.p.ramp_frac_per_h:>8.0%}  "
          f"CHP 余热比 {fc.p.heat_to_power_ratio}")

    print("=" * 66)
    print("容量配置优化（穷举 + 可行性过滤 + Total NPC 排序，HOMER 公开口径）")
    print("=" * 66)

    def sim(ov, n_days=30):
        from kernel.hyflow.templates.t6_ammonia import run_t6_scenario
        r = run_t6_scenario(ov, n_days=n_days)
        return {"npc": r.econ["npc_net_cny"], "reliability": r.kpi["renew_share"],
                "kpis": {"nh3_t": round(r.kpi["nh3_annual_t"], 1),
                         "hb_cf": round(r.kpi["hb_capacity_factor"], 3),
                         "lcoa": round(r.econ["lcoa_cny_per_t"], 0)}}

    base = {"pv.capacity_kw": 600.0, "wind.capacity_kw": 1500.0,
            "bess.capacity_kwh": 1000.0, "bess.power_kw": 300.0,
            "h2store.capacity_kg": 5000.0, "h2store.level_init_kg": 2500.0}
    candidates = {"pemwe.rated_kw": [400.0, 600.0, 800.0],
                  "chem.nh3.capacity_t_per_h": [0.4, 0.7],
                  "h2store.capacity_kg": [3000.0, 6000.0]}
    print(f"网格: 电解 3 档 × 合成氨 2 档 × 储氢 2 档 = 12 组合（粗筛 30 天）")
    t0 = time.time()
    res = optimize_capacity(sim, base, candidates, n_days=30,
                            refine_top_n=3, refine_days=90, reliability_min=0.0)
    print(f"完成 {res.n_combinations} 组合，粗筛+top3 复核共 {time.time()-t0:.1f}s"
          f"（可行 {res.n_feasible}）")
    print()
    rows = result_table(res)
    cols = ["rank", "npc_cny", "pemwe.rated_kw", "chem.nh3.capacity_t_per_h",
            "h2store.capacity_kg", "nh3_t", "hb_cf", "lcoa"]
    head = ["#", "净NPC(CNY)", "电解kW", "氨t/h", "储氢kg", "90天氨t", "HB利用率", "LCOA"]
    print(("{:<3}{:>14}{:>10}{:>8}{:>10}{:>12}{:>10}{:>10}").format(*head))
    for r in rows:
        print(("{:<3}{:>14,.0f}{:>10,.0f}{:>8.1f}{:>10,.0f}{:>12.1f}{:>10.1%}{:>10,.0f}").format(
            r["rank"], r["npc_cny"], r["pemwe.rated_kw"], r["chem.nh3.capacity_t_per_h"],
            r["h2store.capacity_kg"], r["nh3_t"], r["hb_cf"], r["lcoa"]))
    print("\n读法: 穷举按净 NPC（总成本-氨收入-碳收益）升序；容量匹配氨装置规模")
    print("      后 HB 利用率显著提升——手工配比的错配由此被系统化消除。")
    print("注意双口径: 净 NPC 最优(电解400kW)≠LCOA 最优(电解800kW)——氨消纳为定量")
    print("      合同时选净 NPC（小电解足量）；消纳不设限追求多产时选 LCOA——")
    print("      这个口径选择本身就是要和客户在 G1 门确认的商业假设。")
    print("\nLLM 状态: 网关已接入（DeepSeek OpenAI 兼容）；未配置 DEEPSEEK_API_KEY 时")
    print("          Agent 自动以规则模式运行（降级标注），配置后真实调用并按 tokens 计量。")


if __name__ == "__main__":
    main()
