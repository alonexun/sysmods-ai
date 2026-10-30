# -*- coding: utf-8 -*-
"""液氢储罐 LH2Store（规划级）测试：接口对齐 H2Store + Boil-off/液化电耗显式账。

V1.3 §6.3：三型储氢统一充放接口；损耗禁止静默——Boil-off 进氢账、
液化电耗可从 liquefaction_kwh_total 取数（规划级后处理入账）。
"""
import pytest

from kernel.hyflow.modules.h2store import H2Store
from kernel.hyflow.modules.lh2 import LH2Store, LH2StoreError


class TestInit:
    def test_basic_fields(self):
        s = LH2Store(100.0, 50.0)
        assert s.capacity_kg == 100.0
        assert s.level_kg == 50.0
        assert s.soc == pytest.approx(0.5)
        assert s.boil_off_loss_kg == 0.0
        assert s.liquefaction_kwh_total == 0.0

    def test_invalid_inputs(self):
        with pytest.raises(LH2StoreError):
            LH2Store(0.0, 0.0)
        with pytest.raises(LH2StoreError):
            LH2Store(10.0, 11.0)
        with pytest.raises(LH2StoreError):
            LH2Store(10.0, 5.0, liquefaction_kwh_per_kg=-1.0)
        with pytest.raises(LH2StoreError):
            LH2Store(10.0, 5.0, boil_off_ratio_per_day=0.6)


class TestChargeDischarge:
    def test_charge_caps_at_capacity(self):
        s = LH2Store(10.0, 9.0, liquefaction_kwh_per_kg=10.0)
        got = s.charge(5.0, dt_h=1.0)
        assert got == pytest.approx(1.0)
        assert s.level_kg == pytest.approx(10.0)
        # 液化电耗按实际入罐量计（1 kg × 10 kWh/kg）
        assert s.liquefaction_kwh_total == pytest.approx(10.0)
        assert s.last_liquefaction_kwh == pytest.approx(10.0)

    def test_charge_full_returns_zero_energy(self):
        s = LH2Store(10.0, 10.0)
        assert s.charge(5.0) == 0.0
        assert s.liquefaction_kwh_total == 0.0

    def test_discharge_limited_by_level(self):
        s = LH2Store(10.0, 4.0)
        assert s.discharge(10.0, dt_h=2.0) == pytest.approx(2.0)
        assert s.level_kg == pytest.approx(0.0)
        assert s.discharge(1.0) == 0.0

    def test_negative_rejected(self):
        s = LH2Store(10.0, 5.0)
        with pytest.raises(LH2StoreError):
            s.charge(-1.0)
        with pytest.raises(LH2StoreError):
            s.discharge(-1.0)


class TestBoilOff:
    def test_step_evaporates_and_accumulates(self):
        s = LH2Store(100.0, 48.0, boil_off_ratio_per_day=0.01)
        loss = s.step(dt_h=24.0)
        assert loss == pytest.approx(0.48)
        assert s.level_kg == pytest.approx(47.52)
        assert s.boil_off_loss_kg == pytest.approx(0.48)

    def test_zero_ratio_no_loss(self):
        s = LH2Store(100.0, 50.0, boil_off_ratio_per_day=0.0)
        assert s.step(24.0) == 0.0
        assert s.level_kg == pytest.approx(50.0)


class TestInterfaceParityAndConservation:
    def test_parity_with_h2store_when_no_losses(self):
        """Boil-off=0 时充放行为与高压线性罐一致（三型接口统一）。"""
        hp, lh2 = H2Store(50.0, 10.0), LH2Store(50.0, 10.0, boil_off_ratio_per_day=0.0)
        for offer in (3.0, 30.0, 0.0):
            assert lh2.charge(offer) == pytest.approx(hp.charge(offer))
        for demand in (5.0, 100.0):
            assert lh2.discharge(demand) == pytest.approx(hp.discharge(demand))
        assert lh2.level_kg == pytest.approx(hp.level_kg)

    def test_mass_closure_with_boil_off(self):
        """质量闭合：充入 = 放出 + Boil-off + Δ存量（守恒纪律 §6.3）。"""
        s = LH2Store(100.0, 20.0, boil_off_ratio_per_day=0.006)
        charged = discharged = 0.0
        for _ in range(48):
            charged += s.charge(2.0, dt_h=1.0) * 1.0
            s.step(1.0)
            discharged += s.discharge(1.5, dt_h=1.0) * 1.0
        assert charged == pytest.approx(
            discharged + s.boil_off_loss_kg + (s.level_kg - 20.0), rel=1e-9)
