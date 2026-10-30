# -*- coding: utf-8 -*-
"""T6 多电解路线并联调度测试：效率优先分配 / 爬坡互补 / 缺热降额 / 守恒闭合。"""
import pytest
from kernel.hyflow.modules.electrolyzers import (
    Electrolyzer, ElectrolyzerParams, ElectrolyzerFleet, ElectrolyzerError)
from kernel.hyflow.templates.t6_ammonia import run_t6_scenario, build_t6_config
from kernel.hyflow.modules.phys import H2_LHV_KWH_PER_KG


BASE = {"pv.capacity_kw": 800.0, "wind.capacity_kw": 1500.0,
        "bess.capacity_kwh": 800.0, "bess.power_kw": 400.0,
        "h2store.capacity_kg": 6000.0, "h2store.level_init_kg": 3000.0,
        "pemwe.rated_kw": 600.0, "chem.nh3.capacity_t_per_h": 0.6}


class TestFleetAllocation:
    def test_efficiency_first(self):
        """SOEC(0.86) 与 PEM(0.65) 并联：功率优先喂 SOEC。"""
        f = ElectrolyzerFleet([
            Electrolyzer(ElectrolyzerParams("pem", 500.0)),
            Electrolyzer(ElectrolyzerParams("soec", 500.0, heat_available=True))])
        used, h2, per = f.step(300.0)
        # SOEC 爬坡 5%/h → 第一步只能吃 25kW，剩余给 PEM
        assert per["soec"]["kw"] == pytest.approx(25.0)
        assert per["pem"]["kw"] == pytest.approx(275.0)
        assert used == pytest.approx(300.0)
        # 产氢 = 25×0.86/33.33 + 275×0.65/33.33
        expect_h2 = (25.0 * 0.86 + 275.0 * 0.65) / H2_LHV_KWH_PER_KG
        assert h2 == pytest.approx(expect_h2, rel=1e-9)

    def test_ramp_complementarity(self):
        """爬坡互补：第 2 小时 SOEC 继续爬、PEM 吃剩余——多小时后两者都到稳态。"""
        f = ElectrolyzerFleet([
            Electrolyzer(ElectrolyzerParams("pem", 400.0)),
            Electrolyzer(ElectrolyzerParams("soec", 400.0, heat_available=True))])
        for _ in range(25):
            used, h2, per = f.step(800.0)
        # 稳态：SOEC 满载 400kW（效率优先）+ PEM 400kW
        assert per["soec"]["kw"] == pytest.approx(400.0)
        assert per["pem"]["kw"] == pytest.approx(400.0)

    def test_empty_fleet_rejected(self):
        with pytest.raises(ElectrolyzerError):
            ElectrolyzerFleet([])

    def test_min_load_skip_to_next(self):
        """ALK min 25%：低功率时跳过 ALK 给 PEM。"""
        f = ElectrolyzerFleet([
            Electrolyzer(ElectrolyzerParams("alk", 1000.0)),
            Electrolyzer(ElectrolyzerParams("pem", 200.0))])
        used, h2, per = f.step(50.0)      # < ALK 门槛 250kW
        assert per["alk"]["kw"] == 0.0
        assert per["pem"]["kw"] == pytest.approx(50.0)


class TestT6FleetIntegration:
    def test_solo_pem_no_fleet(self):
        """默认（只有 PEM 额定>0）不建 Fleet——单机路径回归。"""
        cfg = build_t6_config(BASE)
        assert cfg.electrolyzer_fleet is None

    def test_fleet_built_when_multi_tech(self):
        cfg = build_t6_config({**BASE, "alk.rated_kw": 400.0})
        assert cfg.electrolyzer_fleet is not None
        techs = {u.tech for u in cfg.electrolyzer_fleet.units}
        assert techs == {"pem", "alk"}

    def test_multi_tech_conservation(self):
        """四路线并联 30 天：守恒 PASS + 分技术产量账闭合。"""
        ov = {**BASE, "alk.rated_kw": 300.0, "aem.rated_kw": 200.0,
              "soec.rated_kw": 250.0, "soec.heat_available": 1.0}
        r = run_t6_scenario(ov, n_days=30)
        assert r.cons_report.passed, r.cons_report.summary()
        by_tech = r.kpi["h2_by_tech_kg"]
        assert set(by_tech) == {"pem", "alk", "aem", "soec"}
        # 分技术账 == 总产氢（守恒口径闭合）
        assert sum(by_tech.values()) == pytest.approx(r.kpi["h2_prod_annual_kg"],
                                                      rel=1e-6)
        assert all(v >= 0 for v in by_tech.values())

    def test_soec_derating_reduces_output(self):
        """SOEC 缺热降额：同等配置下产氢少于热中性。"""
        ov = {**BASE, "soec.rated_kw": 400.0, "soec.heat_available": 1.0}
        hot = run_t6_scenario(ov, n_days=15)
        ov2 = {**BASE, "soec.rated_kw": 400.0, "soec.heat_available": 0.0}
        cold = run_t6_scenario(ov2, n_days=15)
        assert cold.kpi["h2_by_tech_kg"]["soec"] < hot.kpi["h2_by_tech_kg"]["soec"]

    def test_alk_capex_in_npc(self):
        """ALK 投资计入 NPC：容量>0 时 NPC 高于纯 PEM 基准。"""
        base = run_t6_scenario(BASE, n_days=15)
        with_alk = run_t6_scenario({**BASE, "alk.rated_kw": 500.0}, n_days=15)
        assert with_alk.econ["npc_gross_cny"] > base.econ["npc_gross_cny"]
