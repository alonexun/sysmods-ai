# -*- coding: utf-8 -*-
"""电解槽族：PEM / ALK / AEM / SOEC 四技术路线统一模型（V1.2 §4.1 模块梯队）。

规划级准稳态模型（L3）：线性效率 + 最小负荷 + 爬坡约束 + SOEC 热中性分支。
物理锚点（电耗 kWh/kg = LHV/eff，文献区间核对）：
- PEM : eff 0.60-0.70 → 电耗 47.6-55.6 kWh/kg（HyGen-PEM 产品口径）
- ALK : eff 0.60-0.66 → 50.5-55.6；min负荷宽(20-40%)，启停爬坡慢，CAPEX 低
- AEM : eff 0.60-0.67 → 49.8-55.6；非贵金属催化，介于 PEM/ALK 之间
- SOEC: 热中性 eff 0.80-0.90 → 37.0-41.7；高温 700-850℃，缺热降额，热循环爬坡最慢
铁律1：eff_lhv 一律小数 0-1；铁律3：负输入拒绝、缺热降额显式标注。
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from .phys import H2_LHV_KWH_PER_KG


class ElectrolyzerError(ValueError):
    pass


# 各技术路线内置先验（C1 级，出处：IEA/IRENA 电解槽技术简报与市场区间；
# 客户实测值可经注册表覆盖升 A 级）
TECH_DEFAULTS = {
    "pem":  {"eff_lhv": 0.65, "min_load_ratio": 0.10, "ramp_frac_per_h": 1.0},
    "alk":  {"eff_lhv": 0.63, "min_load_ratio": 0.25, "ramp_frac_per_h": 0.15},
    "aem":  {"eff_lhv": 0.64, "min_load_ratio": 0.15, "ramp_frac_per_h": 0.50},
    "soec": {"eff_lhv": 0.86, "min_load_ratio": 0.40, "ramp_frac_per_h": 0.05},
}


@dataclass
class ElectrolyzerParams:
    tech: str
    rated_kw: float
    eff_lhv: float = None           # None → 按 TECH_DEFAULTS
    min_load_ratio: float = None
    ramp_frac_per_h: float = None   # 每小时功率爬坡占额定比例（1.0=不限）
    heat_available: bool = False     # SOEC：是否有外部余热（热中性口径）
    eff_lhv_no_heat: float = 0.74   # SOEC 缺热时的效率（电耗惩罚）


class Electrolyzer:
    """统一电解槽（接口与 modules.pemwe.Pemwe 对齐：step→(used_kw, h2_kg_per_h)）。"""

    def __init__(self, p: ElectrolyzerParams):
        t = p.tech.lower()
        if t not in TECH_DEFAULTS:
            raise ElectrolyzerError(f"未知电解技术 {p.tech}（可选 pem/alk/aem/soec）")
        if p.rated_kw <= 0:
            raise ElectrolyzerError("rated_kw 必须为正")
        d = TECH_DEFAULTS[t]
        self.p = p
        self.tech = t
        self.eff_lhv = p.eff_lhv if p.eff_lhv is not None else d["eff_lhv"]
        self.min_load_ratio = (p.min_load_ratio if p.min_load_ratio is not None
                               else d["min_load_ratio"])
        self.ramp_frac = (p.ramp_frac_per_h if p.ramp_frac_per_h is not None
                          else d["ramp_frac_per_h"])
        if not (0.0 < self.eff_lhv <= 1.0):
            raise ElectrolyzerError(f"eff_lhv={self.eff_lhv} 越界 (0,1]（铁律1）")
        if not (0.0 <= self.min_load_ratio <= 0.8):
            raise ElectrolyzerError("min_load_ratio 越界 [0,0.8]")
        self.p_last_kw = 0.0        # 爬坡记忆
        self.derated = (t == "soec" and not p.heat_available)

    @property
    def eff_current(self) -> float:
        """当前运行效率（SOEC 缺热降额显式化）。"""
        if self.derated:
            return self.p.eff_lhv_no_heat
        return self.eff_lhv

    @property
    def specific_kwh_per_kg(self) -> float:
        return H2_LHV_KWH_PER_KG / self.eff_current

    def step(self, power_available_kw: float) -> tuple:
        """返回 (实际耗电 kW, 产氢 kg/h)。含 min 负荷门与爬坡约束。"""
        if power_available_kw < -1e-9:
            raise ElectrolyzerError("power_available 为负（上游数据错误）")
        pa = max(0.0, power_available_kw)
        threshold = self.p.rated_kw * self.min_load_ratio
        # 爬坡上限：本步最大功率 = 上一步 + ramp×额定（1h 步长）
        max_by_ramp = self.p_last_kw + self.ramp_frac * self.p.rated_kw
        max_by_ramp = min(max_by_ramp, self.p.rated_kw)
        if pa < threshold or pa <= 0.0:
            self.p_last_kw = 0.0    # 低于最小负荷 → 停机（爬坡记忆归零）
            return 0.0, 0.0
        p_used = min(pa, max_by_ramp)
        self.p_last_kw = p_used
        h2 = p_used * self.eff_current / H2_LHV_KWH_PER_KG
        return p_used, h2

    def summary(self) -> str:
        return (f"[{self.tech.upper()}] {self.p.rated_kw}kW eff={self.eff_current:.2f} "
                f"({self.specific_kwh_per_kg:.1f}kWh/kg) min={self.min_load_ratio:.0%} "
                f"ramp={self.ramp_frac:.0%}/h" +
                (" [SOEC 缺热降额运行]" if self.derated else ""))


class ElectrolyzerFleet:
    """多技术路线并联调度（T6 多点解）：功率在机组间分配。

    分配策略（务实规划级）：
    1. 效率优先——eff_current 高者先填（SOEC 热中性 > PEM/AEM/ALK 按参数）；
    2. min 负荷门与爬坡约束由各机组自带——高效机组爬坡吃满后剩余功率交给下一台；
    3. 分配结果用于守恒审计与分技术产量报表（h2_by_tech）。
    """

    def __init__(self, units: List[Electrolyzer]):
        if not units:
            raise ElectrolyzerError("Fleet 至少需要一台电解槽")
        # 效率降序，效率并列时爬坡快者优先（快速吸收波动）
        self.units = sorted(
            units, key=lambda u: (-u.eff_current, u.ramp_frac))
        self.annual_h2_kg: Dict[str, float] = {u.tech: 0.0 for u in units}

    @property
    def rated_kw(self) -> float:
        return sum(u.p.rated_kw for u in self.units)

    def step(self, power_available_kw: float, dt_h: float = 1.0) -> tuple:
        """并联步进。返回 (总耗电 kW, 总产氢 kg/h, 各机组明细)。"""
        remaining = max(0.0, power_available_kw)
        total_used = 0.0
        total_h2 = 0.0
        per_unit: Dict[str, Dict[str, float]] = {}
        for u in self.units:
            if remaining <= 0.0:
                u.step(0.0)          # 维持爬坡状态机（停机语义）
                per_unit[u.tech] = {"kw": 0.0, "h2_kg_per_h": 0.0}
                continue
            used, h2 = u.step(remaining)
            remaining -= used
            total_used += used
            total_h2 += h2
            self.annual_h2_kg[u.tech] += h2 * dt_h
            per_unit[u.tech] = {"kw": used, "h2_kg_per_h": h2}
        return total_used, total_h2, per_unit

    def summary(self) -> str:
        return " || ".join(u.summary() for u in self.units)

