# -*- coding: utf-8 -*-
"""canonical 注册表与三铁律测试。"""
import pytest
from kernel.hyflow.registry import load_registry
from kernel.hyflow.modules.phys import H2_LHV_KWH_PER_KG


def test_registry_loads_and_naming():
    reg = load_registry()
    assert len(reg.specs) >= 30
    for name in reg.specs:
        assert "." in name, f"命名规则违规: {name}"


def test_defaults_all_pass_validation():
    reg = load_registry()
    reg.validated(reg.defaults())  # 全量默认值必须合法（注册表自洽）


def test_out_of_range_raises():
    reg = load_registry()
    with pytest.raises(ValueError):
        reg.validate("pv.capacity_kw", -1.0)          # 越界
    with pytest.raises(ValueError):
        reg.validate("bess.eff_roundtrip", 1.5)      # 效率>1（铁律1）
    with pytest.raises(KeyError):
        reg.validate("unknown.param", 1.0)           # 未注册


def test_non_numeric_raises():
    reg = load_registry()
    with pytest.raises(ValueError):
        reg.validate("pv.capacity_kw", "五十千瓦")    # 铁律3：禁止静默兜底


def test_efficiency_params_are_fraction():
    """铁律1：所有效率/比例类参数值域 ⊆ (0,1] 或 [0,1]。"""
    reg = load_registry()
    for name in ["pemwe.eff_lhv", "fc.eff_lhv", "bess.eff_roundtrip",
                 "pv.derate", "pemwe.min_load_ratio", "load.night_ratio"]:
        lo, hi = reg.spec(name).range
        assert lo >= 0.0 and hi <= 1.0, f"{name} 值域应限于 0-1 小数"


def test_lhv_convention_consistency():
    reg = load_registry()
    assert abs(reg.conventions["h2_energy_lhv_kwh_per_kg"] - H2_LHV_KWH_PER_KG) < 1e-9
