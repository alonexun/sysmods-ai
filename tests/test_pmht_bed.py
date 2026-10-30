# -*- coding: utf-8 -*-
"""0D 集总床仿真测试（mt_abs/mt_des 场景等价 + 能量守恒账）。"""
import math
import pytest
from kernel.hyflow.modules.mh import load_hydride, simulate_bed


@pytest.fixture(scope="module")
def timnvfe():
    return load_hydride("Ti[0.95]Zr[0.05]Mn[1.55]V[0.45]Fe[0.09]")


class TestAbsorptionBed:
    """mt_abs.m 场景：TiMnVFe、Ti=283.15K(10℃)、P=4×Peq_abs(半充)、Uth=1e5 W/K、1500s。"""

    def test_absorption_physics(self, timnvfe):
        Ti = 273.15 + 10
        P = 4 * timnvfe.Peq(Ti, 0.5 * timnvfe.wMax, "abs")
        res = simulate_bed(timnvfe, w0=0.02 * timnvfe.wMax, T0=Ti, Ti=Ti,
                            P=P, uth_w_per_k=1e5, mass_kg=200.0, t_span=(0, 1500))
        assert res.w[-1] > res.w[0]              # 吸氢
        assert res.T.max() > Ti                  # 放热升温
        assert res.T[-1] < res.T.max()           # 后期向环境温度回落
        assert res.w[-1] <= timnvfe.wMax + 1e-9

    def test_energy_balance(self, timnvfe):
        """能量账三断言（能量/氢账均为 ODE 状态，BDF 内部精度）：
        ① 氢质量账：∫dwdt·dt == 终态 Δw（质量守恒核心闭环）
        ② 化学计量热：反应热 ≈ dH_abs × 床质量 × Δw
        ③ 方向：吸氢放热使床向环境净放热（e_ambient<0）"""
        Ti = 273.15 + 10
        P = 4 * timnvfe.Peq(Ti, 0.5 * timnvfe.wMax, "abs")
        res = simulate_bed(timnvfe, w0=0.02 * timnvfe.wMax, T0=Ti, Ti=Ti,
                            P=P, uth_w_per_k=1e5, mass_kg=200.0, t_span=(0, 1500))
        dw = res.w[-1] - res.w[0]
        assert res.h2_int_kg_per_kg == pytest.approx(dw, rel=1e-6), \
            f"氢质量账失衡: ∫dwdt={res.h2_int_kg_per_kg:.6f} vs Δw={dw:.6f}"
        expect_kj = timnvfe.dH("abs") * 200.0 * dw / 1000.0
        assert res.e_rxn_kj == pytest.approx(expect_kj, rel=0.15), \
            f"反应热 {res.e_rxn_kj:.0f} kJ vs 化学计量 {expect_kj:.0f} kJ"
        assert res.e_ambient_kj < 0

    def test_strong_cooling_keeps_bed_cold(self, timnvfe):
        """大 Uth（高原站液冷等效）→ 床温几乎不升，吸氢全程不受热限。"""
        Ti = 273.15 + 10
        P = 4 * timnvfe.Peq(Ti, 0.5 * timnvfe.wMax, "abs")
        res_hot = simulate_bed(timnvfe, w0=0.02 * timnvfe.wMax, T0=Ti, Ti=Ti,
                               P=P, uth_w_per_k=1e5, mass_kg=200.0, t_span=(0, 1500))
        res_cold = simulate_bed(timnvfe, w0=0.02 * timnvfe.wMax, T0=Ti, Ti=Ti,
                                P=P, uth_w_per_k=1e7, mass_kg=200.0, t_span=(0, 1500))
        assert res_cold.T.max() < res_hot.T.max()
        assert res_cold.w[-1] > res_hot.w[-1]    # 冷却充分→平衡容量更高→吸更多氢


class TestDesorptionBed:
    """mt_des 场景：P=0.2×Peq_des、w0=0.9wMax → 放氢吸热、床温先降后回升。"""

    def test_desorption_physics(self, timnvfe):
        Ti = 273.15 + 40
        P = 0.2 * timnvfe.Peq(Ti, 0.5 * timnvfe.wMax, "des")
        res = simulate_bed(timnvfe, w0=0.9 * timnvfe.wMax, T0=Ti, Ti=Ti,
                           P=P, uth_w_per_k=1e4, mass_kg=200.0, t_span=(0, 1800))
        assert res.w[-1] < res.w[0]              # 放氢
        assert res.T.min() < Ti                  # 吸热降温（放氢需补热——高原站热管理依据）
        assert res.T[-1] > res.T.min()          # 环境补热后回升


class TestBedErrors:
    def test_invalid_inputs(self, timnvfe):
        with pytest.raises(Exception):
            simulate_bed(timnvfe, w0=-0.1, T0=300, Ti=300, P=1e6,
                         uth_w_per_k=100, mass_kg=1.0)
        with pytest.raises(Exception):
            simulate_bed(timnvfe, w0=0.5 * timnvfe.wMax, T0=300, Ti=300, P=1e6,
                         uth_w_per_k=100, mass_kg=0.0)
        with pytest.raises(Exception):
            simulate_bed(timnvfe, w0=0.5 * timnvfe.wMax, T0=300, Ti=300, P=1e6,
                         uth_w_per_k=100, mass_kg=1.0, t_span=(10, 0))
