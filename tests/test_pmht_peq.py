# -*- coding: utf-8 -*-
"""Peq 移植验证：LaNi5 手算锚点 + van't Hoff 线性回归 + 滞后 + 边缘行为。"""
import math
import pytest
from kernel.hyflow.modules.mh import load_hydride

R = 8.314


@pytest.fixture(scope="module")
def lani5():
    return load_hydride("La[1]Ni[5]")


class TestPeqAnchors:
    def test_half_charge_298k_anchor(self, lani5):
        """手算锚点（多平台 Peq 全链）：
        abs: mu0 = -31168 + 298×111.4 = 2029 J/mol
             Peq = 101325×exp(2029/(8.314×298)) ≈ 2.27 bar
        des: mu0 = -32151 + 298×112.8 = 1463 → Peq ≈ 1.86 bar
        文献 LaNi5 室温平台 ≈ 1.7-2.7 bar。"""
        w_half = 0.5 * lani5.wMax
        p_abs = lani5.Peq(298.0, w_half, "abs")
        p_des = lani5.Peq(298.0, w_half, "des")
        expect_abs = 101325 * math.exp(2029.0 / (R * 298.0))
        expect_des = 101325 * math.exp(1462.6 / (R * 298.0))
        assert p_abs == pytest.approx(expect_abs, rel=0.02)
        assert p_des == pytest.approx(expect_des, rel=0.02)
        assert 1.5e5 < p_des < p_abs < 4e5    # 1.5-4 bar 量级

    def test_hysteresis_abs_above_des(self, lani5):
        """滞后：吸氢平台压 > 放氢平台压（全域）。"""
        for f in (0.3, 0.5, 0.7):
            w = f * lani5.wMax
            assert lani5.Peq(300.0, w, "abs") > lani5.Peq(300.0, w, "des")

    def test_temperature_monotonic(self, lani5):
        """温度↑ 平台压↑（van't Hoff 方向）。"""
        w = 0.5 * lani5.wMax
        ps = [lani5.Peq(T, w, "des") for T in (273, 298, 323, 353)]
        assert ps == sorted(ps)

    def test_vanthoff_slope_recovers_dH(self, lani5):
        """ln(Peq) vs 1/T 的回归斜率应复原 dH_des/R（两平台中点线性区域）。"""
        w = 0.5 * lani5.wMax
        T1, T2 = 298.0, 353.0
        p1 = lani5.Peq(T1, w, "des")
        p2 = lani5.Peq(T2, w, "des")
        slope = (math.log(p2) - math.log(p1)) / (1.0 / T2 - 1.0 / T1)
        expect = lani5.s.des.dH[0] / R       # = -dS 侧消失后 ln(P)=dH/RT-dS/R → 斜率= dH/R
        assert slope == pytest.approx(expect, rel=0.05)

    def test_edges_finite_positive(self, lani5):
        """x→0/x→wMax 边缘正则溶液行为：有限正值。"""
        assert lani5.Peq(300.0, 0.0, "des") > 0
        assert lani5.Peq(300.0, lani5.wMax, "abs") > 0
        # 越界调用被截断（不崩）
        assert lani5.Peq(300.0, 1.5 * lani5.wMax, "abs") > 0

    def test_mode_validation(self, lani5):
        with pytest.raises(Exception):
            lani5.Peq(300.0, 0.005, "wrong")
