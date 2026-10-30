# -*- coding: utf-8 -*-
"""T6 绿氨端到端测试：守恒 + 元素审计 + 电网四模式对比 + 柔性 HB 行为。"""
import numpy as np
import pytest
from kernel.hyflow.templates.t6_ammonia import run_t6_scenario, build_t6_config, run_t6
from kernel.hyflow.templates.t1_offgrid import synth_ghi
from kernel.hyflow.modules.wind import synth_wind
from kernel.hyflow.modules.grid import GridParams


def big_buffer_overrides():
    """绿氨需要吨级储氢缓冲（注册表默认 10kg 是哨站罐口径）。"""
    return {"h2store.capacity_kg": 8000.0, "h2store.level_init_kg": 4000.0,
            "pemwe.rated_kw": 1500.0, "bess.capacity_kwh": 2000.0,
            "bess.power_kw": 500.0, "wind.capacity_kw": 2000.0,
            "pv.capacity_kw": 1000.0, "grid.max_import_kw": 500.0}


class TestT6Conservation:
    def test_30day_conservation_pass(self):
        r = run_t6_scenario(big_buffer_overrides(), n_days=30,
                            mh_material=None)
        rep = r.cons_report
        assert rep.passed, rep.summary()
        assert len(rep.violations) == 0

    def test_element_audit_closed(self):
        r = run_t6_scenario(big_buffer_overrides(), n_days=30)
        elem = r.element_audit_annual
        assert abs(elem["N"]) < 1e-6 and abs(elem["H"]) < 1e-6
        assert elem["h2_purge_kg"] >= -1e-6   # 效率损失（弛放）非负

    def test_kpi_physical_ranges(self):
        r = run_t6_scenario(big_buffer_overrides(), n_days=30)
        k = r.kpi
        assert k["nh3_annual_t"] > 0                    # 有氨产出
        assert 0.0 <= k["hb_capacity_factor"] <= 1.0
        assert 0.0 <= k["renew_share"] <= 1.0
        # 氢总账闭合：产氢 + 初始罐存 == HB 耗氢 + 期末罐存（动态期初可净支出罐存）
        final_level = float(r.series["h2_store_level_kg"][-1])
        h2_account = k["h2_prod_annual_kg"] + 4000.0 - k["h2_to_hb_annual_kg"] - final_level
        assert abs(h2_account) < 1e-6
        assert r.econ["lcoa_cny_per_t"] > 0


class TestGridModes:
    def test_offgrid_no_import(self):
        ov = big_buffer_overrides()
        ov["grid.mode_str"] = "offgrid"
        r = run_t6_scenario(ov, n_days=15)
        assert r.kpi["grid_import_kwh"] == 0.0
        assert r.cons_report.passed

    def test_ppa_import_within_redline(self):
        ov = big_buffer_overrides()
        ov["grid.mode_str"] = "ppa"
        ov["grid.max_import_kw"] = 300.0
        r = run_t6_scenario(ov, n_days=15)
        # 红线硬约束（购电是否发生取决于动态行为——罐耗尽节奏）
        assert r.kpi["grid_import_kwh"] <= 300.0 * 24 * 15 + 1e-6
        assert r.cons_report.passed
        assert 0.0 <= r.kpi["renew_share"] <= 1.0

    def test_tou_mode_runs_and_charges(self):
        ov = big_buffer_overrides()
        ov["grid.mode_str"] = "tou"
        r = run_t6_scenario(ov, n_days=15)
        assert r.cons_report.passed
        assert r.kpi["unmet_kwh"] == 0.0    # 分时购电补缺口


class TestHBFlex:
    def test_ramp_limits_output_growth(self):
        """HB 慢动态：第 1 步产量 ≤ 8% 额定（即使氢无限）。"""
        cfg = build_t6_config(big_buffer_overrides())
        r = run_t6(cfg, synth_ghi(5), synth_wind(120))
        nh3_series = r.series["nh3_t_per_h"]
        rated = cfg.hb.rated_t_per_h
        assert nh3_series[0] <= 0.08 * rated + 1e-9   # 1h 内只能爬 8%

    def test_carbon_economics_positive_abatement(self):
        ov = big_buffer_overrides()
        ov["grid.mode_str"] = "ppa"
        r = run_t6_scenario(ov, n_days=15)
        e = r.econ
        assert e["co2_abatement_t_per_year"] > 0     # 工业降碳收益口径
        assert e["grey_nh3_co2_t_per_t"] == pytest.approx(1.775, rel=2e-3)
        assert e["npc_net_cny"] < e["npc_gross_cny"]  # 收益冲减
