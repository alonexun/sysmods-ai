# -*- coding: utf-8 -*-
"""模块级测试：物理锚点全部手工可验算。"""
import pytest
import numpy as np
from kernel.hyflow.modules.pv import PvParams, pv_power_simple, PvError
from kernel.hyflow.modules.pemwe import Pemwe, PemweParams
from kernel.hyflow.modules.bess import Bess, BessParams
from kernel.hyflow.modules.h2store import H2Store
from kernel.hyflow.modules.fuelcell import FuelCell, FcParams
from kernel.hyflow.modules.phys import H2_LHV_KWH_PER_KG


class TestPv:
    def test_stc_anchor(self):
        p = PvParams(capacity_kw=10.0, derate=1.0)
        assert pv_power_simple(np.array([1000.0]), p)[0] == pytest.approx(10.0)

    def test_zero_ghi(self):
        p = PvParams(capacity_kw=10.0, derate=0.85)
        assert pv_power_simple(np.array([0.0]), p)[0] == 0.0

    def test_negative_ghi_rejected(self):
        """旧内核 B9 教训：-999 缺测值必须拦截，绝不静默置零。"""
        p = PvParams(capacity_kw=10.0, derate=0.85)
        with pytest.raises(PvError):
            pv_power_simple(np.array([800.0, -999.0]), p)

    def test_bad_derate(self):
        with pytest.raises(PvError):
            pv_power_simple(np.array([1000.0]), PvParams(10.0, 1.5))


class TestPemwe:
    def test_eff_conversion_anchor(self):
        """锚点（手工独立验算）：25kW 电 × η0.65 → 氢能 16.25 kWh/h
        ÷ LHV 33.33 = 0.4875 kg/h。注意方向：m = P×η/LHV（不是 P/(η×LHV)）。"""
        pem = Pemwe(PemweParams(rated_kw=25.0, eff_lhv=0.65, min_load_ratio=0.1))
        used, h2 = pem.step(25.0)
        assert used == pytest.approx(25.0)
        assert h2 == pytest.approx(25.0 * 0.65 / H2_LHV_KWH_PER_KG, rel=1e-9)
        # 能量方向守恒：产氢能量 ≤ 耗电能量
        assert h2 * H2_LHV_KWH_PER_KG <= used + 1e-9

    def test_specific_energy(self):
        pem = Pemwe(PemweParams(25.0, 0.65, 0.1))
        assert pem.specific_kwh_per_kg == pytest.approx(H2_LHV_KWH_PER_KG / 0.65, rel=1e-9)

    def test_min_load_gate(self):
        pem = Pemwe(PemweParams(rated_kw=25.0, eff_lhv=0.65, min_load_ratio=0.1))
        used, h2 = pem.step(2.0)          # < 2.5kW 门槛 → 停机
        assert (used, h2) == (0.0, 0.0)
        used, h2 = pem.step(3.0)          # ≥门槛 → 运行
        assert used == pytest.approx(3.0)

    def test_over_rated_clipped(self):
        pem = Pemwe(PemweParams(25.0, 0.65, 0.1))
        used, _ = pem.step(100.0)
        assert used == pytest.approx(25.0)

    def test_eff_must_be_fraction(self):
        """铁律1：95(百分数) 必须被拒。"""
        with pytest.raises(Exception):
            Pemwe(PemweParams(25.0, 95.0, 0.1))


class TestBess:
    def test_charge_clip_at_soc_max(self):
        b = Bess(BessParams(capacity_kwh=100.0, power_kw=50.0, eff_roundtrip=0.81,
                            soc_min=0.1, soc_max=0.9, soc_init=0.85))
        charged = b.charge(50.0)          # 只能充到 soc_max
        assert charged > 0
        assert b.soc <= 0.9 + 1e-9
        assert b.charge(50.0) == 0.0      # 满了拒充

    def test_discharge_clip_at_soc_min(self):
        b = Bess(BessParams(100.0, 50.0, 0.81, 0.1, 0.9, 0.15))
        d1 = b.discharge(10.0)
        assert d1 > 0
        b2 = Bess(BessParams(100.0, 50.0, 0.81, 0.1, 0.9, 0.1))
        assert b2.discharge(10.0) == 0.0  # 空(下限)拒放

    def test_roundtrip_energy_account(self):
        """往返账：充入 10kWh(电网侧) → 电池存 10×0.9=9kWh(η_rt=0.81,η_side=0.9)
        → 可放出 9×0.9=8.1kWh。"""
        b = Bess(BessParams(capacity_kwh=100.0, power_kw=50.0, eff_roundtrip=0.81,
                            soc_min=0.0, soc_max=1.0, soc_init=0.0))
        p_in = b.charge(10.0)             # dt=1h
        assert p_in == pytest.approx(10.0)
        assert b.soc_kwh == pytest.approx(9.0, abs=1e-9)
        p_out = b.discharge(50.0)
        assert p_out == pytest.approx(8.1, abs=1e-9)

    def test_invalid_params_rejected(self):
        with pytest.raises(Exception):
            Bess(BessParams(100.0, 50.0, 1.5, 0.1, 0.9, 0.5))   # η>1
        with pytest.raises(Exception):
            Bess(BessParams(100.0, 50.0, 0.9, 0.8, 0.2, 0.5))   # soc_min>max
        with pytest.raises(Exception):
            Bess(BessParams(100.0, 50.0, 0.9, 0.1, 0.9, 0.95))  # init 越界


class TestH2Store:
    def test_full_reject_and_empty_reject(self):
        s = H2Store(capacity_kg=10.0, level_init_kg=10.0)
        assert s.charge(1.0) == 0.0
        s2 = H2Store(capacity_kg=10.0, level_init_kg=0.0)
        assert s2.discharge(1.0) == 0.0

    def test_partial_accept(self):
        s = H2Store(capacity_kg=10.0, level_init_kg=9.5)
        got = s.charge(2.0)
        assert got == pytest.approx(0.5)
        assert s.level_kg == pytest.approx(10.0)

    def test_invalid(self):
        with pytest.raises(Exception):
            H2Store(10.0, 11.0)


class TestFuelCell:
    def test_h2_consumption_anchor(self):
        """锚点：10kW × η0.5 → h2 = 10/(0.5×33.33) = 0.60006 kg/h。"""
        fc = FuelCell(FcParams(rated_kw=10.0, eff_lhv=0.5))
        p, h2 = fc.step(10.0)
        assert p == pytest.approx(10.0)
        assert h2 == pytest.approx(10.0 / (0.5 * H2_LHV_KWH_PER_KG), rel=1e-9)

    def test_clip_rated(self):
        fc = FuelCell(FcParams(10.0, 0.5))
        p, _ = fc.step(50.0)
        assert p == pytest.approx(10.0)
