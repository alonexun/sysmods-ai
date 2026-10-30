# -*- coding: utf-8 -*-
"""液氢储罐 LH2Store（规划级 L3，V1.3 §6.3 储氢三型之一）。

与 H2Store（高压）/ MHStore（固态）同充放接口（charge/discharge/level/capacity），
另含三型差异项（守恒纪律：损耗必须显式入账，禁止静默）：
- Boil-off 蒸发损：step(dt_h) 按日蒸发率折算扣减液位，累计 boil_off_loss_kg；
- 液化电耗：charge 时按 liquefaction_kwh_per_kg × 实际充入量累计（规划级后处理
  入账——调用方从 liquefaction_kwh_total 取数进 KPI/经济性，暂不进逐时母线调度）；
- 汽化供给：discharge 视为取用即汽化，汽化能耗忽略（后置精算项）。

锚点（C2 先验，须厂商/实测回填升级）：
- 液化能耗 ≈ LHV 的 30-40%（行业常见约 10-13 kWh/kg）；
- Boil-off ≈ 0.1-1%/天（随储罐规模/取用模式变化）。

模板接线（storage='lh2' 进 T1/T6、压缩/汽化精算）为后续里程碑，见 V1.3 §6.3。
"""


class LH2StoreError(ValueError):
    pass


class LH2Store:
    """液氢储罐：质量账（kg）+ 液化电耗账（kWh）+ Boil-off 损耗账（kg）。"""

    def __init__(self, capacity_kg: float, level_init_kg: float,
                 liquefaction_kwh_per_kg: float = 12.0,
                 boil_off_ratio_per_day: float = 0.003):
        if capacity_kg <= 0:
            raise LH2StoreError("液氢储罐容量必须为正")
        if not (0.0 <= level_init_kg <= capacity_kg):
            raise LH2StoreError(f"初始氢量 {level_init_kg} 超出 [0,{capacity_kg}]")
        if liquefaction_kwh_per_kg < 0:
            raise LH2StoreError("液化电耗系数为负")
        if not (0.0 <= boil_off_ratio_per_day <= 0.5):
            raise LH2StoreError("日蒸发率越界 [0, 0.5]")
        self.capacity_kg = capacity_kg
        self.level_kg = level_init_kg
        self.liquefaction_kwh_per_kg = float(liquefaction_kwh_per_kg)
        self.boil_off_ratio_per_day = float(boil_off_ratio_per_day)
        # 显式损耗/能耗账（报告与守恒审计取数点）
        self.boil_off_loss_kg = 0.0
        self.liquefaction_kwh_total = 0.0
        self.last_liquefaction_kwh = 0.0

    @property
    def soc(self) -> float:
        return self.level_kg / self.capacity_kg

    def step(self, dt_h: float = 1.0) -> float:
        """推进 Boil-off（按 dt_h 占全天的比例），返回本步蒸发损 kg。"""
        if dt_h < 0:
            raise LH2StoreError("dt_h 为负")
        loss = self.level_kg * self.boil_off_ratio_per_day * (dt_h / 24.0)
        self.level_kg -= loss
        self.boil_off_loss_kg += loss
        return loss

    def charge(self, offer_kg_per_h: float, dt_h: float = 1.0) -> float:
        """实际充入 kg/h（受罐容限制）；同步累计液化电耗。"""
        if offer_kg_per_h < 0:
            raise LH2StoreError("charge offer 为负")
        room = self.capacity_kg - self.level_kg
        if room <= 0:
            self.last_liquefaction_kwh = 0.0
            return 0.0
        actual = max(0.0, min(offer_kg_per_h, room / dt_h))
        self.level_kg += actual * dt_h
        self.level_kg = min(self.level_kg, self.capacity_kg)
        self.last_liquefaction_kwh = actual * dt_h * self.liquefaction_kwh_per_kg
        self.liquefaction_kwh_total += self.last_liquefaction_kwh
        return actual

    def discharge(self, demand_kg_per_h: float, dt_h: float = 1.0) -> float:
        """实际放出 kg/h（受存量限制；汽化能耗后置精算）。"""
        if demand_kg_per_h < 0:
            raise LH2StoreError("discharge demand 为负")
        avail = self.level_kg
        if avail <= 0:
            return 0.0
        actual = max(0.0, min(demand_kg_per_h, avail / dt_h))
        self.level_kg -= actual * dt_h
        self.level_kg = max(self.level_kg, 0.0)
        return actual
