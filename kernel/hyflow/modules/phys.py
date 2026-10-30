# -*- coding: utf-8 -*-
"""物理常量与通用工具（单位约定唯一来源）。"""

# H2 低热值（LHV）——注册表 conventions 与此处必须一致（测试互查）
H2_LHV_KWH_PER_KG = 33.33  # kWh/kg
H2_KG_PER_NM3 = 0.0899     # 0°C, 101.325kPa


def to_kg_from_nm3(nm3: float) -> float:
    return nm3 * H2_KG_PER_NM3
