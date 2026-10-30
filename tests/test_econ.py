# -*- coding: utf-8 -*-
"""经济模块手算锚点（HOMER Total NPC 公开口径）。"""
import pytest
from kernel.hyflow.econ.npc import crf, capital_recovery_cost, total_npc, lcoe, EconError


def test_crf_anchor():
    """锚点：r=6%, n=20 → CRF = 0.06×1.06^20/(1.06^20-1) = 0.087185。"""
    v = crf(0.06, 20)
    assert v == pytest.approx(0.0871845, rel=1e-5)


def test_crf_zero_rate():
    assert crf(0.06, 1) == pytest.approx(1.06)
    with pytest.raises(EconError):
        crf(0.0, 20)
    with pytest.raises(EconError):
        crf(0.6, 20)


def test_capital_recovery_with_replacement():
    """锚点：capex=1000, life=10, project=20, r=6%
    → 一次替换：PV = 1000 + 1000/1.06^10 = 1000 + 558.3948 = 1558.39。"""
    v = capital_recovery_cost(1000.0, 10, 20, 0.06)
    assert v == pytest.approx(1558.3948, rel=1e-5)


def test_capital_recovery_no_replacement():
    v = capital_recovery_cost(1000.0, 25, 20, 0.06)
    assert v == pytest.approx(1000.0)


def test_total_npc_opex_annuity():
    """OPEX 年金：100/年 × Σ(1/1.06^t, t=1..20) = 100×11.4699 = 1146.99。"""
    items = [{"capex": 0.0, "life_years": 20, "opex_annual": 100.0}]
    v = total_npc(items, 20, 0.06)
    assert v == pytest.approx(1146.992, rel=1e-4)


def test_lcoe_anchor():
    v = lcoe(1558.3948, 1000.0, 0.06, 20)
    assert v == pytest.approx(1558.3948 * 0.0871845 / 1000.0, rel=1e-4)


def test_lcoe_zero_energy_raises():
    with pytest.raises(EconError):
        lcoe(1000.0, 0.0, 0.06, 20)   # 铁律3：不静默返回 0
