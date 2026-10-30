# -*- coding: utf-8 -*-
"""SOFC 固体氧化物燃料电池（高温 600-800℃，与 PEMFC 并列的第二条 FC 路线）。

规划级模型（L3）：LHV 效率 + 最小负荷 + 热循环爬坡（慢于 PEMFC 一个量级）+ 高品位余热。
锚点：eff 0.55-0.65（电效率高于 PEMFC 5-10 个百分点）；余热 25-35% 可热电联供；
燃料灵活（H2/NH3 重整/CH4）——本模型按纯氢口径，燃料灵活性在报告层标注。
"""
from dataclasses import dataclass
from .phys import H2_LHV_KWH_PER_KG


class SofcError(ValueError):
    pass


@dataclass
class SofcParams:
    rated_kw: float
    eff_lhv: float = 0.58           # 规划先验 0.55-0.65
    min_load_ratio: float = 0.30   # 高温电池堆最低稳定运行负荷
    ramp_frac_per_h: float = 0.10  # 热循环约束：每小时爬坡 5-15% 额定
    heat_to_power_ratio: float = 0.45   # 余热/发电比值（CHP 口径先验）


class SOFC:
    def __init__(self, p: SofcParams):
        if p.rated_kw <= 0:
            raise SofcError("rated_kw 必须为正")
        if not (0.3 <= p.eff_lhv <= 0.75):
            raise SofcError(f"eff_lhv={p.eff_lhv} 越界 [0.3,0.75]（SOFC 电效率区间）")
        self.p = p
        self.p_last_kw = 0.0

    def step(self, demand_kw: float) -> tuple:
        """返回 (实际发电 kW, 氢耗 kg/h, 余热 kW)。"""
        if demand_kw < -1e-9:
            raise SofcError("demand 为负")
        d = max(0.0, demand_kw)
        threshold = self.p.rated_kw * self.p.min_load_ratio
        max_by_ramp = min(self.p_last_kw + self.p.ramp_frac_per_h * self.p.rated_kw,
                          self.p.rated_kw)
        if d < threshold or d <= 0.0:
            self.p_last_kw = 0.0
            return 0.0, 0.0, 0.0
        p_out = min(d, max_by_ramp)
        self.p_last_kw = p_out
        h2 = p_out / (self.p.eff_lhv * H2_LHV_KWH_PER_KG)
        heat = p_out * self.p.heat_to_power_ratio
        return p_out, h2, heat

    def summary(self) -> str:
        return (f"[SOFC] {self.p.rated_kw}kW eff={self.p.eff_lhv:.2f} "
                f"CHP余热比={self.p.heat_to_power_ratio:.2f} min={self.p.min_load_ratio:.0%}")
