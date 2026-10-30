# -*- coding: utf-8 -*-
"""PMHT 解析器测试：337 材料全量冒烟 + 具体材料锚点 + 多平台合成案例。"""
import os
import pytest
from kernel.hyflow.modules.mh import parse_mh_file, list_materials, load_hydride

DATA = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "kb", "materials", "pmht"))


def test_337_materials_smoke():
    """全库解析冒烟：每张卡可解析、wMax 合法、Peq 可调用、出处引用在。"""
    files = list_materials(DATA)
    assert len(files) >= 330, f"预期 337 材料，得到 {len(files)}"
    parsed = 0
    for f in files:
        spec = parse_mh_file(os.path.join(DATA, f))
        assert 0.0 < spec.w_max < 0.1, f"{f}: wMax={spec.w_max} 非法"
        assert spec.des.dH, f"{f}: Dehydriding dH 缺失"
        assert all(h < 0 for h in spec.des.dH), f"{f}: dH 应为负（文件约定）"
        h = load_hydride(os.path.join(DATA, f))
        p = h.Peq(298.0, 0.5 * h.wMax, "des")
        assert p > 0 and p == p, f"{f}: Peq 非法 {p}"
        parsed += 1
    assert parsed >= 330


def test_lani5_anchor_values():
    """LaNi5 卡锚点：wt% 1.49、AB5、吸/放氢 dH、参考文献齐全。"""
    h = load_hydride("La[1]Ni[5]", DATA)
    assert h.s.hydride_type.upper() == "AB5"
    assert h.wMax == pytest.approx(0.0149, rel=1e-3)
    assert h.s.des.dH[0] == pytest.approx(-32151, rel=1e-6)
    assert h.s.des.dS[0] == pytest.approx(-112.8, rel=1e-6)
    assert h.s.abss.dH[0] == pytest.approx(-31168, rel=1e-6)
    assert len(h.s.references) >= 5       # Laurencelle/Sekhar/Walker/Sandrock/Zhang/Luo
    assert not h.s.kin_abs.assumed        # LaNi5 卡给全了动力学
    # Tc = (dH_abs−dH_des)/(dS_abs−dS_des) = 983/1.4 ≈ 702 K
    assert h.s.Tc[0] == pytest.approx(983.0 / 1.4, rel=2e-2)


def test_timnvfe_hm_capacity():
    """mt_abs 所用材料：H/M 3.09 → wt% ≈ 3.09×1.008/(3.09×1.008+162.74)。"""
    h = load_hydride("Ti[0.95]Zr[0.05]Mn[1.55]V[0.45]Fe[0.09]", DATA)
    w_metal = 0.95 * 47.867 + 0.05 * 91.224 + 1.55 * 54.938 + 0.45 * 50.942 + 0.09 * 55.845
    expect_wt = 3.09 * 1.008 / (3.09 * 1.008 + w_metal)
    assert h.wMax == pytest.approx(expect_wt, rel=1e-3)
    assert h.wMax * 100 == pytest.approx(1.88, abs=0.05)  # 与产品口径 1.5-1.8wt% 同量级


def test_multiplateau_synthetic():
    """多平台解析与 Peq 平滑性（合成卡：双平台 dH/dS + centers/widths/minSpans）。"""
    content = """Elements: [Ca: 1, Ni: 5]
Type: AB5

Thermodynamics
{
    Weight Percent: 1.4

    Dehydriding
    {
        DH: [-30000 -26000]
        DS: [-110 -100]

        centers: [0.3 0.7]
        widths: [0.4 0.4]
        minSpans: [0.05]

        From isotherms: true
    }
    Hydriding
    {
        DH: [-29000 -25000]
        DS: [-108 -98]

        From isotherms: true
    }
}

Properties
{
    keff: 1.5
    Cp: 400
    rho: 8000
}

Kinetics
{
    Hydriding
    {
        Ca: 100
        Ea: 25000
        pFcn: log
        wFcn: 1st Order
    }
    Dehydriding
    {
        Ca: 50
        Ea: 20000
        pFcn: log
        wFcn: 1st Order
    }
}
"""
    p = os.path.join(DATA, "__test_multiplateau__.mh")
    with open(p, "w", encoding="utf-8") as f:
        f.write(content)
    try:
        h = load_hydride(p)
        assert h.n == 2
        assert h.s.centers == [0.3, 0.7]
        # 连续性只验平台+过渡区（x∈[0.17,0.85]，RSL 边缘 α 相区压强骤降是真实物理）
        xs = [0.17 + 0.68 * i / 300 for i in range(301)]
        ps = [h.Peq(300.0, x * h.wMax, "des") for x in xs]
        for i in range(1, len(ps)):
            assert ps[i] > 0
            jump = abs(ps[i] - ps[i - 1]) / max(ps[i - 1], 1e-12)
            assert jump < 0.5, f"Peq 跳变 {jump:.0%} @x={xs[i]:.3f}（平台间多项式失效）"
    finally:
        os.remove(p)


def test_missing_capacity_raises():
    """铁律3 等价：容量缺失必须抛错而非静默。"""
    content = """Elements: [La: 1, Ni: 5]
Type: AB5

Thermodynamics
{
    Dehydriding
    {
        DH: -30000
        DS: -110
    }
}
"""
    p = os.path.join(DATA, "__test_nocap__.mh")
    with open(p, "w", encoding="utf-8") as f:
        f.write(content)
    try:
        with pytest.raises(ValueError):
            parse_mh_file(p)
    finally:
        os.remove(p)
