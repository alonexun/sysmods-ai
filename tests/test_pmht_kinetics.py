# -*- coding: utf-8 -*-
"""PMHT 动力学与热效应测试（KineticsModel.dwdt 等价）。"""
import math
import pytest
from kernel.hyflow.modules.mh import load_hydride

R = 8.314


@pytest.fixture(scope="module")
def lani5():
    return load_hydride("La[1]Ni[5]")


class TestDwdt:
    def test_absorption_rate_anchor(self, lani5):
        """手算锚点：300K、P=10bar、w=0.5wMax、Ca=50、Ea=20000、pFcn=log。
        r = 50·exp(-20000/(8.314·300))·(wMax−w)·ln(P/Peq_abs) ≈ 1.7e-4 kg/(kg·s)。"""
        w = 0.5 * lani5.wMax
        Peq_abs = lani5.Peq(300.0, w, "abs")
        expect = 50 * math.exp(-20000 / (R * 300)) * (lani5.wMax - w) * math.log(1e6 / Peq_abs)
        r = lani5.dwdt(300.0, 1e6, w)
        assert r == pytest.approx(expect, rel=1e-6)
        assert 1e-5 < r < 1e-3

    def test_desorption_negative(self, lani5):
        w = 0.9 * lani5.wMax
        p_des = lani5.Peq(300.0, w, "des")
        r = lani5.dwdt(300.0, 0.2 * p_des, w)
        assert r < 0

    def test_dead_zone_zero(self, lani5):
        """P 介于 Peq_des 与 Peq_abs 之间 → 不反应（KineticsModel 语义）。"""
        w = 0.5 * lani5.wMax
        mid = 0.5 * (lani5.Peq(300.0, w, "des") + lani5.Peq(300.0, w, "abs"))
        assert lani5.dwdt(300.0, mid, w) == 0.0

    def test_full_no_absorption(self, lani5):
        """w=wMax 时不再吸氢（死区语义：P 介于两平衡压之间 r=0）。"""
        w = lani5.wMax
        p_abs = lani5.Peq(300.0, w, "abs")
        p_des = lani5.Peq(300.0, w, "des")
        mid = 0.5 * (p_abs + p_des)
        assert lani5.dwdt(300.0, mid, w) == 0.0


class TestThermal:
    def test_dEdt_sign_and_magnitude(self, lani5):
        """吸氢放热为正；|dEdt| = |dH[J/kgH]|·|dwdt|。"""
        w = 0.5 * lani5.wMax
        Peq_abs = lani5.Peq(300.0, w, "abs")
        r = lani5.dwdt(300.0, 1e6, w)
        q = lani5.dEdt(300.0, 1e6, w)
        assert q > 0
        dh_j_per_kgh = lani5.dH("abs", w)
        assert q == pytest.approx(dh_j_per_kgh * r, rel=1e-6)

    def test_desorption_endothermic(self, lani5):
        w = 0.9 * lani5.wMax
        p_des = lani5.Peq(300.0, w, "des")
        assert lani5.dEdt(300.0, 0.2 * p_des, w) < 0

    def test_dH_anchors(self, lani5):
        """|dH| J/kg_H = |dH_mol|/2.016e-3。LaNi5 des: 32151/0.002016 ≈ 15.95 MJ/kgH。"""
        assert lani5.dH("des") == pytest.approx(32151 / 0.002016, rel=1e-3)
        assert lani5.dH("abs") == pytest.approx(31168 / 0.002016, rel=1e-3)

    def test_cp_dadson(self, lani5):
        """Cp = 355·(1+F·HM)，F=w/wMax。全吸时显著高于空床。"""
        assert lani5.Cp(0.0) == pytest.approx(355, rel=1e-9)
        cp_full = lani5.Cp(lani5.wMax)
        assert cp_full == pytest.approx(355 * (1 + lani5.HM), rel=1e-9)
        assert cp_full > 355
        with pytest.raises(Exception):
            lani5.Cp(1.5 * lani5.wMax)   # MATLAB 同款越界保护
