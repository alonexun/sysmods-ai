# -*- coding: utf-8 -*-
"""化工/冶金模块测试：理论计量锚点 + 元素守恒 + 柔性约束（min负荷/爬坡）。"""
import pytest
from kernel.hyflow.modules.chemical import (
    element_balance, HaberBosch, HaberBoschParams, Methanol, MethanolParams,
    DRI, DRIParams, ASU, ASUParams, ChemError)


class TestElementBalance:
    def test_haber_bosch_closed(self):
        bal = element_balance({"H2": 3 * 2.016, "N2": 28.013},
                              {"NH3": 2 * 17.031})
        assert abs(bal["N"]) < 1e-9 and abs(bal["H"]) < 1e-9

    def test_methanol_closed(self):
        bal = element_balance({"CO2": 44.009, "H2": 3 * 2.016},
                              {"CH3OH": 32.041, "H2O": 18.015})
        assert abs(bal["C"]) < 1e-9 and abs(bal["H"]) < 1e-9 and abs(bal["O"]) < 1e-9

    def test_dri_closed(self):
        bal = element_balance({"Fe2O3": 159.687, "H2": 3 * 2.016},
                              {"Fe": 2 * 55.845, "H2O": 3 * 18.015})
        for e in ("Fe", "O", "H"):
            assert abs(bal[e]) < 1e-9

    def test_unknown_species(self):
        with pytest.raises(ChemError):
            element_balance({"Xe": 1.0}, {})


class TestHaberBosch:
    def test_yield_anchor(self):
        """锚点：1t/h 满负荷 → 耗氢 187kg/h、N2 824kg/h、电 0.35MWh/h。"""
        hb = HaberBosch(HaberBoschParams(rated_t_per_h=1.0))
        # 预热爬坡：从 min 负荷逐步升到满负荷（1/0.08=12.5h）
        out = None
        for _ in range(50):
            out = hb.step(10000.0, 5000.0)
        assert out["nh3_t"] == pytest.approx(1.0, abs=1e-9)
        assert out["h2_used_kg"] == pytest.approx(187.0)
        assert out["n2_used_kg"] == pytest.approx(824.0)
        assert out["elec_mwh"] == pytest.approx(0.35)

    def test_min_load_shutdown(self):
        """可用氢 < 最小负荷需求 → 停机（传统 HB 不允许 20% 负荷运行）。"""
        hb = HaberBosch(HaberBoschParams(rated_t_per_h=1.0))
        out = hb.step(50.0, 500.0)     # 50kg H2 → 0.27t/h < min 0.5t/h
        assert out["nh3_t"] == 0.0

    def test_ramp_limit(self):
        """爬坡 8%/h：从 0 起 1h 内产量 ≤ 0.08t/h。"""
        hb = HaberBosch(HaberBoschParams(rated_t_per_h=1.0))
        hb.output_t_per_h = 0.0
        out = hb.step(10000.0, 5000.0)
        assert out["nh3_t"] <= 0.08 + 1e-9

    def test_element_audit_purge_positive(self):
        hb = HaberBosch(HaberBoschParams(rated_t_per_h=1.0))
        out = hb.step(10000.0, 5000.0)
        audit = hb.element_audit(out["nh3_t"], out["h2_used_kg"], out["n2_used_kg"])
        assert abs(audit["N"]) < 1e-6      # 理论计量闭合
        assert abs(audit["H"]) < 1e-6
        assert audit["h2_purge_kg"] >= -1e-9   # 效率损失（弛放）非负


class TestMethanol:
    def test_yield_anchor(self):
        m = Methanol(MethanolParams(rated_t_per_h=1.0))
        for _ in range(50):
            out = m.step(20000.0, 100000.0)
        assert out["meoh_t"] == pytest.approx(1.0)
        assert out["h2_used_kg"] == pytest.approx(193.0)
        assert out["co2_used_kg"] == pytest.approx(1376.0)
        audit = m.element_audit(out["meoh_t"], out["h2_used_kg"],
                                 out["co2_used_kg"], out["h2o_produced_kg"])
        for e in ("C", "H", "O"):
            assert abs(audit[e]) < 1e-6


class TestDRI:
    def test_yield_anchor(self):
        """锚点：吨铁耗氢 55kg、矿石 1430kg、副产水 3×18.015/159.687×1430=483kg。"""
        d = DRI(DRIParams(rated_t_per_h=1.0))
        for _ in range(50):
            out = d.step(100000.0)
        assert out["fe_t"] == pytest.approx(1.0)
        assert out["h2_used_kg"] == pytest.approx(55.0)
        assert out["ore_used_kg"] == pytest.approx(1430.0, rel=1e-3)
        audit = d.element_audit(out["fe_t"], out["h2_used_kg"],
                                 out["ore_used_kg"], out["h2o_produced_kg"])
        for e in ("Fe", "O", "H"):
            assert abs(audit[e]) < 1e-6


class TestASU:
    def test_elec_and_o2(self):
        a = ASU(ASUParams())
        out = a.make_n2(824.0)
        assert out["elec_mwh"] == pytest.approx(824.0 * 0.35 / 1000.0)
        assert out["o2_kg"] == pytest.approx(824.0 * 0.27)
