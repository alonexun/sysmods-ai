# -*- coding: utf-8 -*-
"""引擎级解析锚点：全部可用手算复核（双轨测试②的本地版——独立于旧代码与外部库）。"""
import numpy as np
import pytest
from kernel.hyflow.templates.t1_offgrid import build_t1_config, synth_ghi, synth_load
from kernel.hyflow.engine import run_t1
from kernel.hyflow.modules.phys import H2_LHV_KWH_PER_KG
from kernel.hyflow.audit.guard import ConservationAuditor


def _cfg(**over):
    return build_t1_config(over)


class TestAnalyticAnchors:
    def test_anchor_all_power_to_h2(self):
        """锚点1（手工独立验算）：无负荷+满 BESS+大罐 → 全部 PV 电制氢。
        GHI=1000 恒定 24h，cap=10kW，derate=1.0，η=0.65：
        产氢 = 24×10×0.65/33.33 = 4.68 kg（m = P×η/LHV）。"""
        cfg = _cfg(**{"pv.capacity_kw": 10.0, "pv.derate": 1.0,
                     "bess.soc_init": 1.0, "bess.soc_max": 1.0,
                     "h2store.capacity_kg": 100.0, "h2store.level_init_kg": 0.0})
        ghi = np.full(24, 1000.0)
        load = np.zeros(24)
        r = run_t1(cfg, ghi, load)
        expect = 24 * 10.0 * 0.65 / H2_LHV_KWH_PER_KG
        assert r.kpi["h2_prod_kg"] == pytest.approx(expect, rel=1e-9)
        assert r.kpi["e_pem_kwh"] == pytest.approx(240.0, rel=1e-9)
        assert r.kpi["h2_prod_kg"] * H2_LHV_KWH_PER_KG <= r.kpi["e_pem_kwh"] + 1e-9
        assert r.kpi["e_unmet_kwh"] == 0.0
        assert r.kpi["e_curtail_kwh"] == 0.0
        assert r.cons_report.passed

    def test_anchor_zero_pv_full_unmet(self):
        """锚点2：零 PV+BESS 空+罐空 → 全年失电 = 负荷总量，保供率 0。"""
        cfg = _cfg(**{"bess.soc_init": 0.10, "h2store.level_init_kg": 0.0})
        n = 72
        r = run_t1(cfg, np.zeros(n), np.full(n, 5.0))
        assert r.kpi["e_unmet_kwh"] == pytest.approx(5.0 * n, rel=1e-9)
        assert r.kpi["reliability"] == pytest.approx(0.0, abs=1e-9)
        assert r.cons_report.passed   # 失电是场景信息，不是守恒违例

    def test_anchor_fc_from_prefilled_tank(self):
        """锚点3：零 PV+BESS 空+罐预装 5kg → FC 供全部负荷。
        24h×5kW，η_fc=0.5：耗氢 = 24×5/(0.5×33.33) = 7.2 kg > 罐容 5kg →
        FC 只能发到氢用尽：电 = 5×0.5×33.33 = 83.325 kWh，其余失电。"""
        cfg = _cfg(**{"bess.soc_init": 0.10, "h2store.capacity_kg": 5.0,
                      "h2store.level_init_kg": 5.0})
        n = 24
        r = run_t1(cfg, np.zeros(n), np.full(n, 5.0))
        assert r.kpi["e_fc_kwh"] == pytest.approx(5.0 * 0.5 * H2_LHV_KWH_PER_KG, rel=1e-9)
        assert r.kpi["h2_cons_kg"] == pytest.approx(5.0, rel=1e-9)
        assert r.kpi["e_unmet_kwh"] == pytest.approx(5.0 * n - 5.0 * 0.5 * H2_LHV_KWH_PER_KG, rel=1e-9)
        assert r.h2_store_level_kg[-1] == pytest.approx(0.0, abs=1e-9)

    def test_anchor_roundtrip_efficiency_upper_bound(self):
        """锚点4：FC 电/电解电之比 ≤ η_el×η_fc（罐无损）。"""
        r = run_t1(_cfg(), synth_ghi(30), synth_load(30))
        r2r = r.kpi["roundtrip_eff"]
        eta = 0.65 * 0.5
        if not np.isnan(r2r):
            assert 0.0 < r2r <= eta + 1e-9

    def test_year_run_conservation(self):
        """全年 8760h：守恒 PASS、无违例、KPI 合理区间。"""
        r = run_t1(_cfg(), synth_ghi(365), synth_load(365))
        rep = r.cons_report
        assert rep.passed, rep.summary()
        assert len(rep.violations) == 0
        assert r.kpi["h2_prod_kg"] > 0
        assert 0.0 <= r.kpi["reliability"] <= 1.0
        assert 0.0 <= r.kpi["curtail_ratio"] <= 1.0
        assert r.kpi["e_served_kwh"] > 0

    def test_soc_and_tank_bounds_all_year(self):
        """状态边界全年不越界。"""
        r = run_t1(_cfg(), synth_ghi(90), synth_load(90))
        assert r.bess_soc.min() >= 0.10 - 1e-9
        assert r.bess_soc.max() <= 0.95 + 1e-9
        assert r.h2_store_level_kg.min() >= -1e-9
        assert r.h2_store_level_kg.max() <= 10.0 + 1e-9
        assert (r.pv_kw >= -1e-9).all()
        assert (r.unmet_kw >= -1e-9).all()
        assert (r.curtail_kw >= -1e-9).all()


class TestAuditorSensitivity:
    """守恒器不是恒真——注入不平衡必须 FAIL（防审计器形同虚设）。"""

    def test_injected_imbalance_fails(self):
        aud = ConservationAuditor()
        for t in range(100):
            aud.step_elec(t, supply_kw=11.0, demand_kw=10.0)   # 恒差 1kW
        rep = aud.finish()
        assert not rep.passed
        assert len(rep.violations) > 0

    def test_injected_h2_imbalance_fails(self):
        aud = ConservationAuditor()
        for t in range(100):
            aud.step_h2(t, produced_kg_per_h=1.0, consumed_kg_per_h=0.5,
                        store_delta_kg_per_h=0.4)               # 差 0.1
        rep = aud.finish()
        assert not rep.passed

    def test_clean_balance_passes(self):
        aud = ConservationAuditor()
        for t in range(8760):
            aud.step_elec(t, 10.0, 10.0)
            aud.step_h2(t, 1.0, 0.6, 0.4)
        rep = aud.finish()
        assert rep.passed
        assert rep.elec_err_rel_annual < 1e-12


class TestEnergyDirections:
    """守恒查平衡，方向查物理——产氢公式反向 bug 的回归防线。"""

    def test_direction_electrolysis_overunity_rejected(self):
        from kernel.hyflow.audit.guard import check_energy_directions
        # 100kWh 电"产"出 6kg 氢(200kWh) —— 效率 200%，必须拦截
        v = check_energy_directions(e_pem_kwh=100.0, h2_prod_kg=6.0,
                                    e_fc_kwh=0.0, h2_cons_kg=0.0,
                                    lvh_kwh_per_kg=33.33)
        assert any(x.kind == "phys" for x in v)

    def test_direction_fc_overunity_rejected(self):
        from kernel.hyflow.audit.guard import check_energy_directions
        v = check_energy_directions(e_pem_kwh=100.0, h2_prod_kg=1.0,
                                    e_fc_kwh=50.0, h2_cons_kg=0.5,
                                    lvh_kwh_per_kg=33.33)
        assert any(x.kind == "phys" for x in v)

    def test_direction_physical_case_passes(self):
        from kernel.hyflow.audit.guard import check_energy_directions
        # 100kWh 电 × η0.65 → 65kWh 氢 = 1.95kg；FC 用 1kg 发 16.665kWh
        v = check_energy_directions(e_pem_kwh=100.0, h2_prod_kg=100.0 * 0.65 / 33.33,
                                    e_fc_kwh=0.5 * 33.33, h2_cons_kg=1.0,
                                    lvh_kwh_per_kg=33.33)
        assert v == []
