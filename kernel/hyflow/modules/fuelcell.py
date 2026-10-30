# -*- coding: utf-8 -*-
"""PEMFC 燃料电池模块。

氢耗 = P / (η_lhv × LHV)；最小负荷同电解（可选）。
罐侧接口：给定需求电功率→返回(实际电功率, 氢需求 kg/h)；调用方用 H2Store.discharge 取氢。
"""
from dataclasses import dataclass
from .phys import H2_LHV_KWH_PER_KG


@dataclass
class FcParams:
    rated_kw: float
    eff_lhv: float        # 0-1
    min_load_ratio: float = 0.0


class FcError(ValueError):
    pass


class FuelCell:
    def __init__(self, p: FcParams):
        if not (0.0 < p.eff_lhv <= 1.0):
            raise FcError(f"fc.eff_lhv={p.eff_lhv} 必须在 (0,1]（铁律1）")
        if not (0.0 <= p.min_load_ratio <= 0.5):
            raise FcError("fc.min_load_ratio 越界")
        if p.rated_kw <= 0:
            raise FcError("fc.rated_kw 必须为正")
        self.p = p

    def step(self, demand_kw: float) -> tuple:
        """返回 (实际发电 kW, 氢耗需求 kg/h)。"""
        if demand_kw < -1e-9:
            raise FcError(f"demand={demand_kw} 为负")
        d = max(0.0, demand_kw)
        threshold = self.p.rated_kw * self.p.min_load_ratio
        if d < threshold or d <= 0.0:
            return 0.0, 0.0
        p_out = min(d, self.p.rated_kw)
        h2_kg_per_h = p_out / (self.p.eff_lhv * H2_LHV_KWH_PER_KG)
        return p_out, h2_kg_per_h
