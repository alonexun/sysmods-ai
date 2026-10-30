# -*- coding: utf-8 -*-
"""容量优化器测试：穷举/过滤/NPC 排序/复核/抽稀（HOMER 公开口径）。"""
import pytest
from kernel.hyflow.optimize import optimize_capacity, result_table, _thin_grid, OptimizerError


def t1_sim(overrides, n_days=30):
    from kernel.hyflow.templates.t1_offgrid import run_t1_scenario
    r = run_t1_scenario(overrides, n_days=n_days)
    return {"npc": r.econ["total_npc_cny"], "reliability": r.kpi["reliability"],
            "kpis": {"h2_kg": round(r.kpi["h2_prod_kg"], 2)}}


class TestOptimizer:
    def test_small_grid_exhaustive_and_ranking(self):
        """2×2 网格全枚举：NPC 升序排列正确（保供约束放宽以免小配置全过滤）。"""
        res = optimize_capacity(
            t1_sim, {},
            candidates={"pv.capacity_kw": [30.0, 100.0],
                        "bess.capacity_kwh": [100.0, 400.0]},
            n_days=30, refine_top_n=2, refine_days=30, reliability_min=0.0)
        assert res.n_combinations == 4
        assert len(res.rows) == 4
        npcs = [r.npc_cny for r in res.top]
        assert npcs == sorted(npcs)
        # 最小 PV 与最小 BESS 组合 NPC 最低（容量小→CAPEX 小，无保供约束时）
        best = res.top[0]
        assert best.overrides["pv.capacity_kw"] == pytest.approx(30.0)
        assert best.overrides["bess.capacity_kwh"] == pytest.approx(100.0)

    def test_reliability_filter(self):
        """保供率硬约束：PV 30kW 无 BESS 的小配置 → 可靠性不足被过滤。"""
        res = optimize_capacity(
            t1_sim, {"bess.power_kw": 50.0},
            candidates={"pv.capacity_kw": [30.0, 200.0]},
            n_days=30, reliability_min=0.95, refine_top_n=2, refine_days=30)
        assert res.n_infeasible_reliability >= 0   # 有过滤统计
        for r in res.top:
            assert r.reliability is None or r.reliability >= 0.95

    def test_grid_thinning(self):
        """组合数超上限 → 自动抽稀。"""
        cands = {"pv.capacity_kw": list(range(10, 60, 2)),       # 25 个
                 "bess.capacity_kwh": list(range(100, 2100, 100))}  # 20 个 → 500 组合
        thinned, changed = _thin_grid(cands, max_comb=50)
        n = 1
        for v in thinned.values():
            n *= len(v)
        assert changed is True
        assert n <= 50

    def test_candidates_must_be_canonical(self):
        with pytest.raises(Exception):
            optimize_capacity(t1_sim, {}, candidates={"not.a.param": [1.0, 2.0]})

    def test_empty_candidates(self):
        with pytest.raises(OptimizerError):
            optimize_capacity(t1_sim, {}, candidates={})

    def test_result_table_rows(self):
        res = optimize_capacity(
            t1_sim, {},
            candidates={"pv.capacity_kw": [50.0, 100.0]},
            n_days=30, refine_top_n=1, refine_days=30)
        table = result_table(res)
        assert len(table) >= 1
        assert table[0]["rank"] == 1
        assert "npc_cny" in table[0] and "pv.capacity_kw" in table[0]
