# -*- coding: utf-8 -*-
"""电网模块：绿电直连（PPA）与市场化交易（分时/现货/购售双向）。

中国工业绿氢场景的三个电网语境（V1.2 §1.3 分布式中心+工业降碳扩展）：
- offgrid: 离网（无购售）
- ppa: 绿电直连专线（合同价+容量上限）——专线容量 max_import_kw 同时是物理红线
- tou: 分时电价购电（峰/平/谷三段）+ 可选上网售电
- spot: 现货价格时序（市场化交易输入）
"""
from dataclasses import dataclass
from typing import Optional
import numpy as np


class GridError(ValueError):
    pass


@dataclass
class GridParams:
    mode: str                     # offgrid | ppa | tou | spot
    max_import_kw: float = 0.0    # 购电容量红线 kW（专线/变压器容量）
    ppa_price_cny_kwh: float = 0.38
    buy_peak_cny_kwh: float = 1.0
    buy_flat_cny_kwh: float = 0.6
    buy_valley_cny_kwh: float = 0.3
    peak_hours: tuple = (8, 9, 10, 11, 18, 19, 20, 21)      # 峰时段(时)
    valley_hours: tuple = (23, 0, 1, 2, 3, 4, 5, 6, 7)      # 谷时段
    sell_price_cny_kwh: float = 0.35
    spot_price_cny_kwh: Optional[np.ndarray] = None         # 现货逐时电价


class Grid:
    def __init__(self, p: GridParams):
        m = p.mode.lower()
        if m not in ("offgrid", "ppa", "tou", "spot"):
            raise GridError(f"未知电网模式 {p.mode}")
        if m != "offgrid" and p.max_import_kw < 0:
            raise GridError("购电容量红线不能为负")
        if m == "spot":
            if p.spot_price_cny_kwh is None:
                raise GridError("现货模式必须提供逐时电价序列（铁律3）")
            if (np.asarray(p.spot_price_cny_kwh) < 0).any():
                raise GridError("现货电价含负值——缺测须上游清洗")
        self.p = p
        self._cost_cny = 0.0
        self._revenue_cny = 0.0

    # ---------------- 价格 ----------------
    def buy_price(self, hour_index: int) -> float:
        m = self.p.mode
        if m == "ppa":
            return self.p.ppa_price_cny_kwh
        if m == "tou":
            h = hour_index % 24
            if h in self.p.peak_hours:
                return self.p.buy_peak_cny_kwh
            if h in self.p.valley_hours:
                return self.p.buy_valley_cny_kwh
            return self.p.buy_flat_cny_kwh
        if m == "spot":
            return float(self.p.spot_price_cny_kwh[hour_index % len(self.p.spot_price_cny_kwh)])
        raise GridError("offgrid 无购电价")

    def sell_price(self, hour_index: int) -> float:
        if self.p.mode == "spot":
            return self.buy_price(hour_index)  # 市场化下售电同价（简化口径，注明）
        return self.p.sell_price_cny_kwh

    # ---------------- 购/售 ----------------
    def import_power(self, deficit_kw: float, hour_index: int, dt_h: float = 1.0) -> float:
        """缺口购电：受容量红线限制。返回实际购电 kW。"""
        if self.p.mode == "offgrid":
            return 0.0
        if deficit_kw <= 0:
            return 0.0
        p = min(deficit_kw, self.p.max_import_kw)
        self._cost_cny += p * dt_h * self.buy_price(hour_index)
        return p

    def export_power(self, surplus_kw: float, hour_index: int, dt_h: float = 1.0) -> float:
        """盈余上网售电（市场化/PPA 专线按合同；offgrid 不售）。返回实际售电 kW。"""
        if self.p.mode == "offgrid" or surplus_kw <= 0:
            return 0.0
        p = min(surplus_kw, self.p.max_import_kw)  # 专线双向容量简化同值
        self._revenue_cny += p * dt_h * self.sell_price(hour_index)
        return p

    # ---------------- 账目 ----------------
    @property
    def net_cost_cny(self) -> float:
        return self._cost_cny - self._revenue_cny
