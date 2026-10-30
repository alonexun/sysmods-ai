# -*- coding: utf-8 -*-
"""BESS 锂电储能模块（SOC 状态机）。

约定：eff_roundtrip 为往返效率；单侧效率 η_side = sqrt(eff_roundtrip)。
充电：入电池能量 = P_in × η_side；放电：输出 = 从 SOC 取出 / η_side。
SOC 硬边界 [soc_min, soc_max]——越界请求被截断并如实返回实际值（截断不是兜底，
是物理容量边界；调用方按返回值做守恒）。
"""
import math
from dataclasses import dataclass


@dataclass
class BessParams:
    capacity_kwh: float
    power_kw: float
    eff_roundtrip: float    # 0-1
    soc_min: float
    soc_max: float
    soc_init: float


class BessError(ValueError):
    pass


class Bess:
    def __init__(self, p: BessParams):
        if not (0.0 < p.eff_roundtrip <= 1.0):
            raise BessError(f"bess.eff_roundtrip={p.eff_roundtrip} 必须在 (0,1]")
        if not (0.0 <= p.soc_min < p.soc_max <= 1.0):
            raise BessError(f"SOC 边界非法: [{p.soc_min},{p.soc_max}]")
        if p.capacity_kwh <= 0 or p.power_kw <= 0:
            raise BessError("容量与功率必须为正")
        if not (p.soc_min <= p.soc_init <= p.soc_max):
            raise BessError(f"soc_init={p.soc_init} 超出 [{p.soc_min},{p.soc_max}]")
        self.p = p
        self.eta_side = math.sqrt(p.eff_roundtrip)
        self.soc_kwh = p.soc_init * p.capacity_kwh  # 当前存能 kWh

    @property
    def soc(self) -> float:
        return self.soc_kwh / self.p.capacity_kwh

    def charge(self, offer_kw: float, dt_h: float = 1.0) -> float:
        """按电网侧计量的实际充电功率 kW（受 power/soc_max 限制）。"""
        if offer_kw < 0:
            raise BessError("charge offer 为负")
        headroom_kwh = (self.p.soc_max * self.p.capacity_kwh - self.soc_kwh)
        if headroom_kwh <= 0:
            return 0.0
        # 电网侧可充 P = headroom(电池侧)/η/dt
        p_by_soc = headroom_kwh / self.eta_side / dt_h
        p = min(offer_kw, self.p.power_kw, p_by_soc)
        p = max(0.0, p)
        self.soc_kwh += p * dt_h * self.eta_side
        # 浮点保护：不越过硬边界
        self.soc_kwh = min(self.soc_kwh, self.p.soc_max * self.p.capacity_kwh)
        return p

    def discharge(self, demand_kw: float, dt_h: float = 1.0) -> float:
        """实际放电功率 kW（受 power/soc_min 限制）。"""
        if demand_kw < 0:
            raise BessError("discharge demand 为负")
        available_kwh = (self.soc_kwh - self.p.soc_min * self.p.capacity_kwh)
        if available_kwh <= 0:
            return 0.0
        p_by_soc = available_kwh * self.eta_side / dt_h  # 电网侧可放
        p = min(demand_kw, self.p.power_kw, p_by_soc)
        p = max(0.0, p)
        self.soc_kwh -= p * dt_h / self.eta_side
        self.soc_kwh = max(self.soc_kwh, self.p.soc_min * self.p.capacity_kwh)
        return p
