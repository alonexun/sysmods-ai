# -*- coding: utf-8 -*-
"""氢压缩机（规划级 L3，等温理想 + 等温效率）——V1.3 §6.1。

物理锚点（C2 先验，须厂商数据回填升级）：
- 理想等温功 w_ideal = (R·T/M)·ln(p2/p1)；H2 在 288K 下 ≈ 0.330 kWh/kg 每 ln 单位压比；
- 实际电耗 = w_ideal / η_iso（等温效率，行业 0.6-0.8）；
- 30→350 bar、η=0.70 时 ≈ 1.16 kWh/kg（高压储氢路径的典型量级）。

耦合纪律（V1.3 §6.1）：压缩电耗逐时进电平衡（有满充尖峰，禁止常数摊销）；
固态 MH 低压直供 FC 不需要压缩；MH→35MPa 加注（T2）为后续模板接线。
"""
from dataclasses import dataclass
import math

R_J_PER_MOL_K = 8.314462618
M_H2_KG_PER_MOL = 0.00201588


class CompressorError(ValueError):
    pass


@dataclass
class CompressorParams:
    p_in_bar: float = 30.0        # 电解出口压力（PEM 典型 30 bar）
    p_out_bar: float = 350.0      # 35MPa 储氢/加注（45MPa=450 后续分档）
    eta_iso: float = 0.70         # 等温效率（实际电耗 = 理想等温 / η）
    t_in_k: float = 288.15        # 入口气温（K）


class Compressor:
    """定压比压缩机：单位电耗 spec_kwh_per_kg = 理想等温 / (η_iso × 3600)。"""

    def __init__(self, p: CompressorParams):
        if p.p_in_bar <= 0 or p.p_out_bar <= 0:
            raise CompressorError("压缩机入口/出口压力必须为正")
        if p.p_out_bar <= p.p_in_bar:
            raise CompressorError(f"出口压力 {p.p_out_bar} 必须大于入口 {p.p_in_bar}")
        if not (0.0 < p.eta_iso <= 1.0):
            raise CompressorError(f"eta_iso={p.eta_iso} 越界 (0,1]")
        if p.t_in_k <= 0:
            raise CompressorError("入口温度必须为正")
        self.p = p
        self._spec = None

    @property
    def spec_kwh_per_kg(self) -> float:
        """单位质量压缩电耗（kWh/kg），缓存。"""
        if self._spec is None:
            w_ideal_kwh = (R_J_PER_MOL_K * self.p.t_in_k / M_H2_KG_PER_MOL
                           * math.log(self.p.p_out_bar / self.p.p_in_bar) / 3.6e6)
            self._spec = w_ideal_kwh / self.p.eta_iso
        return self._spec

    def energy_kwh(self, flow_kg: float) -> float:
        """压缩 flow_kg 氢的电耗（kWh）。"""
        if flow_kg < 0:
            raise CompressorError("压缩流量为负")
        return flow_kg * self.spec_kwh_per_kg

    def power_kw_for_flow(self, flow_kg_per_h: float) -> float:
        """给定质量流量（kg/h）的压缩功率（kW，1h 步长口径）。"""
        if flow_kg_per_h < 0:
            raise CompressorError("压缩流量为负")
        return flow_kg_per_h * self.spec_kwh_per_kg
