# -*- coding: utf-8 -*-
"""PEM 电解制氢——兼容壳（唯一物理实现在 electrolyzers.py，V1.3 去重）。

历史接口 Pemwe / PemweParams / PemweError 原样保留：engine、T6 模板、既有测试
无需改动。PEM 物理（效率/最小负荷/爬坡）与 ALK/AEM/SOEC 统一由
Electrolyzer/ElectrolyzerFleet 提供（pem ramp=1.0/h 等价瞬时，行为与旧实现一致）。
"""
from dataclasses import dataclass

from .electrolyzers import Electrolyzer, ElectrolyzerParams, ElectrolyzerError

PemweError = ElectrolyzerError      # 兼容旧异常名


@dataclass
class PemweParams:
    rated_kw: float
    eff_lhv: float          # 0-1（铁律1：小数）
    min_load_ratio: float   # 0-0.5


class Pemwe(Electrolyzer):
    """PEM 电解槽 = Electrolyzer(tech="pem")。"""

    def __init__(self, p: PemweParams):
        super().__init__(ElectrolyzerParams(
            tech="pem", rated_kw=p.rated_kw,
            eff_lhv=p.eff_lhv, min_load_ratio=p.min_load_ratio))
