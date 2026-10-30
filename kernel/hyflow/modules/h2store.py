# -*- coding: utf-8 -*-
"""高压气态储氢罐（线性容量罐，储氢三型之一——V1.3 §6.1）。

Phase 0 为线性质量罐（容量/液位/充放），压力等级 35/45MPa 规划级参数化（先验 C1，
压力分档与压缩机电耗由压缩机模块后续接入）。固态 MH 为 PMHT 等价移植独立线
（MATLAB golden ±0.5% 验收），液氢见 lh2.py（V1.3 §6.3）；三型接口统一：
charge/discharge/level/capacity。
"""


class H2StoreError(ValueError):
    pass


class H2Store:
    def __init__(self, capacity_kg: float, level_init_kg: float):
        if capacity_kg <= 0:
            raise H2StoreError("储氢容量必须为正")
        if not (0.0 <= level_init_kg <= capacity_kg):
            raise H2StoreError(f"初始氢量 {level_init_kg} 超出 [0,{capacity_kg}]")
        self.capacity_kg = capacity_kg
        self.level_kg = level_init_kg

    @property
    def soc(self) -> float:
        return self.level_kg / self.capacity_kg

    def charge(self, offer_kg_per_h: float, dt_h: float = 1.0) -> float:
        """实际充入 kg/h（受罐容限制）。"""
        if offer_kg_per_h < 0:
            raise H2StoreError("charge offer 为负")
        room = self.capacity_kg - self.level_kg
        if room <= 0:
            return 0.0
        actual = min(offer_kg_per_h, room / dt_h)
        actual = max(0.0, actual)
        self.level_kg += actual * dt_h
        self.level_kg = min(self.level_kg, self.capacity_kg)
        return actual

    def discharge(self, demand_kg_per_h: float, dt_h: float = 1.0) -> float:
        """实际放出 kg/h（受存量限制）。"""
        if demand_kg_per_h < 0:
            raise H2StoreError("discharge demand 为负")
        avail = self.level_kg
        if avail <= 0:
            return 0.0
        actual = min(demand_kg_per_h, avail / dt_h)
        actual = max(0.0, actual)
        self.level_kg -= actual * dt_h
        self.level_kg = max(self.level_kg, 0.0)
        return actual
