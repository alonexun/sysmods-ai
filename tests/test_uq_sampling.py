# -*- coding: utf-8 -*-
"""UQ 采样引擎测试：OAT 敏感性与 LHS 分布（P50/P90 + 失败样本计入统计）。"""
import numpy as np
import pytest
from kernel.hyflow.uq.sampling import (run_oat, tornado, run_lhs,
                                        latin_hypercube, _candidate_params)
from kernel.hyflow.registry import load_registry


def t1_sim(overrides):
    """仿真闭包：T1 三天快速场景（UQ 用小场景控制耗时）。
    选 e_pv（必为正、对 C 级参数线性）与 reliability 做稳健 KPI。"""
    from kernel.hyflow.templates.t1_offgrid import run_t1_scenario
    r = run_t1_scenario(overrides, n_days=3)
    return {"e_pv_kwh": r.kpi["e_pv_kwh"], "reliability": r.kpi["reliability"],
            "lcoe": r.econ["lcoe_cny_per_kwh"]}


class TestOAT:
    def test_candidates_are_c_level(self):
        cands = _candidate_params()
        reg = load_registry()
        assert len(cands) >= 5
        for p in cands:
            assert reg.spec(p).level.upper().startswith("C")

    def test_pv_capacity_sensitivity_dominant(self):
        reg = load_registry()
        d = dict(reg.defaults())
        oat = run_oat(t1_sim, d, kpis=["e_pv_kwh", "h2_prod_kg"],
                      params=["pv.capacity_kw", "pv.derate", "bess.soc_max"])
        t = tornado(oat, "e_pv_kwh")
        # 容量与 derate 对电量同为线性敏感（±15% 对称）；bess.soc_max 几乎无影响
        assert t[0]["param"] in ("pv.capacity_kw", "pv.derate")
        assert t[0]["sensitivity"] > 0
        soc_row = [r for r in t if r["param"] == "bess.soc_max"][0]
        assert soc_row["sensitivity"] < t[0]["sensitivity"]

    def test_base_matches_nominal(self):
        reg = load_registry()
        d = dict(reg.defaults())
        oat = run_oat(t1_sim, d, kpis=["reliability"], params=["pv.derate"])
        b = oat["pv.derate"]["base"]["reliability"]
        assert b == pytest.approx(t1_sim({})["reliability"], rel=1e-12)


class TestLHS:
    def test_lhs_shape_and_stratification(self):
        u = latin_hypercube(50, 4, seed=1)
        assert u.shape == (50, 4)
        assert ((u >= 0) & (u <= 1)).all()
        for j in range(4):
            # 分层性：每列的 50 个区间各落入一个样本（bin 计数恒 1）
            bins = np.floor(u[:, j] * 50).astype(int)
            assert sorted(bins.tolist()) == list(range(50))

    def test_run_lhs_stats(self):
        reg = load_registry()
        d = dict(reg.defaults())
        out = run_lhs(t1_sim, d, kpis=["e_pv_kwh", "reliability"],
                      n_samples=12, params=["pv.capacity_kw", "pv.derate",
                                            "pemwe.eff_lhv"], seed=3)
        s = out["stats"]["e_pv_kwh"]
        assert s["n"] == 12
        assert s["p10"] <= s["p50"] <= s["p90"]
        assert out["failed"] == 0
        # P50 应落在基准 ±50% 内（对称扰动小样本）
        base = t1_sim({})["e_pv_kwh"]
        assert 0.5 * base < s["p50"] < 1.5 * base

    def test_failed_samples_counted_not_fatal(self):
        """物理不可行样本计入统计（fail 二分：不整批失败）。"""
        def bad_sim(ov):
            if ov.get("pv.capacity_kw", 50) > 52.0:   # LHS±15% → 约 40% 样本不可行
                raise ValueError("构造的不可行样本")
            return {"h2_prod_kg": 1.0}
        reg = load_registry()
        d = dict(reg.defaults())
        out = run_lhs(bad_sim, d, kpis=["h2_prod_kg"], n_samples=20,
                      params=["pv.capacity_kw"], seed=7)
        assert 0 < out["failed"] < out["n"]
        assert out["stats"]["h2_prod_kg"]["n"] == out["n"] - out["failed"]
