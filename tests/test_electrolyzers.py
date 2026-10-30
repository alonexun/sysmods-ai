# -*- coding: utf-8 -*-
"""电解槽族（PEM/ALK/AEM/SOEC）与 SOFC 测试：技术路线锚点 + 爬坡 + 降额。"""
import pytest
from kernel.hyflow.modules.electrolyzers import (
    Electrolyzer, ElectrolyzerParams, TECH_DEFAULTS, ElectrolyzerError)
from kernel.hyflow.modules.sofc import SOFC, SofcParams, SofcError
from kernel.hyflow.modules.phys import H2_LHV_KWH_PER_KG


class TestElectrolyzerFamily:
    def test_specific_energy_anchors(self):
        """电耗锚点（kWh/kg = 33.33/eff）：ALK 52.9 / AEM 52.1 / SOEC 热中性 38.8。"""
        alk = Electrolyzer(ElectrolyzerParams("alk", 1000.0))
        assert alk.specific_kwh_per_kg == pytest.approx(33.33 / 0.63, rel=1e-3)
        aem = Electrolyzer(ElectrolyzerParams("aem", 1000.0))
        assert aem.specific_kwh_per_kg == pytest.approx(33.33 / 0.64, rel=1e-3)
        soec = Electrolyzer(ElectrolyzerParams("soec", 1000.0, heat_available=True))
        assert soec.specific_kwh_per_kg == pytest.approx(33.33 / 0.86, rel=1e-3)
        assert 36.0 < soec.specific_kwh_per_kg < 42.0   # 文献区间 37-41

    def test_min_load_gates_differ(self):
        """三条路线 min 负荷门不同：ALK 0.25 > AEM 0.15 > SOEC 0.40。"""
        alk = Electrolyzer(ElectrolyzerParams("alk", 100.0))
        aem = Electrolyzer(ElectrolyzerParams("aem", 100.0))
        soec = Electrolyzer(ElectrolyzerParams("soec", 100.0))
        assert alk.step(20.0) == (0.0, 0.0)      # 20% < 25% 停机
        assert aem.step(20.0)[0] == pytest.approx(20.0)   # 20% > 15% 运行
        assert soec.step(30.0) == (0.0, 0.0)     # 30% < 40% 停机

    def test_ramp_limits(self):
        """爬坡约束：SOEC 5%/h、ALK 15%/h——从 0 起 1h 只能到各自比例。"""
        soec = Electrolyzer(ElectrolyzerParams("soec", 100.0))
        used, h2 = soec.step(100.0)
        assert used == pytest.approx(5.0)
        alk = Electrolyzer(ElectrolyzerParams("alk", 100.0))
        used, _ = alk.step(100.0)
        assert used == pytest.approx(15.0)

    def test_soec_heat_derating_explicit(self):
        """SOEC 缺热降额：eff 0.86→0.74，且 summary 显式标注（禁止静默降级）。"""
        with_heat = Electrolyzer(ElectrolyzerParams("soec", 100.0, heat_available=True))
        no_heat = Electrolyzer(ElectrolyzerParams("soec", 100.0, heat_available=False))
        assert with_heat.eff_current == pytest.approx(0.86)
        assert no_heat.eff_current == pytest.approx(0.74)
        assert "缺热降额" in no_heat.summary()
        assert "缺热" not in with_heat.summary()
        # 降额下产氢减少
        used1, h2_1 = Electrolyzer(ElectrolyzerParams("soec", 100.0)).step(100.0)
        used2, h2_2 = Electrolyzer(ElectrolyzerParams("soec", 100.0, heat_available=True)).step(100.0)
        assert h2_2 > h2_1

    def test_output_consistency(self):
        """产氢 = used×eff/LHV（四路线一致公式；慢路线预热到满功率后断言）。"""
        for tech in ("pem", "alk", "aem", "soec"):
            e = Electrolyzer(ElectrolyzerParams(tech, 500.0))
            used = 0.0
            for _ in range(30):          # 爬坡预热（SOEC 5%/h 需 ~20 步）
                used, h2 = e.step(500.0)
            assert used == pytest.approx(500.0)
            assert h2 == pytest.approx(500.0 * e.eff_current / H2_LHV_KWH_PER_KG, rel=1e-9)

    def test_invalid_inputs(self):
        with pytest.raises(ElectrolyzerError):
            Electrolyzer(ElectrolyzerParams("smr", 100.0))      # 未知技术
        with pytest.raises(ElectrolyzerError):
            Electrolyzer(ElectrolyzerParams("alk", 100.0, eff_lhv=120))  # 百分数拒绝


class TestSOFC:
    def test_efficiency_and_heat(self):
        """锚点：58% 效率 → 氢耗=P/(0.58×33.33)；CHP 余热 0.45×P（预热后满功率）。"""
        fc = SOFC(SofcParams(rated_kw=100.0))
        p = 0.0
        for _ in range(15):         # 爬坡预热（10%/h → 10 步满）
            p, h2, heat = fc.step(100.0)
        assert p == pytest.approx(100.0)
        assert h2 == pytest.approx(100.0 / (0.58 * H2_LHV_KWH_PER_KG), rel=1e-9)
        assert heat == pytest.approx(45.0)

    def test_min_load_and_ramp(self):
        """SOFC min 30%、爬坡 10%/h——高温堆的慢动态。"""
        fc = SOFC(SofcParams(rated_kw=100.0))
        assert fc.step(25.0) == (0.0, 0.0, 0.0)      # <30% 停机
        p, _, _ = fc.step(100.0)
        assert p == pytest.approx(10.0)              # 第一小时爬坡上限

    def test_efficiency_bounds(self):
        with pytest.raises(SofcError):
            SOFC(SofcParams(rated_kw=100.0, eff_lhv=0.95))   # 超 SOFC 物理区间
        with pytest.raises(SofcError):
            SOFC(SofcParams(rated_kw=100.0, eff_lhv=0.20))
