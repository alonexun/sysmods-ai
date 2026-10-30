# -*- coding: utf-8 -*-
"""化工/冶金后端模块：中国工业降碳场景（V1.2 §4.4——准稳态收率+最小负荷+爬坡）。

三个反应器（全部元素守恒审计，T2 硬门禁扩展到物料总线）：
- HaberBosch: N2 + 3H2 -> 2NH3        （合成氨，放热 -46kJ/mol NH3）
- Methanol:    CO2 + 3H2 -> CH3OH+H2O （甲醇，放热 -49.5kJ/mol MeOH）
- DRI:         Fe2O3 + 3H2 -> 2Fe+3H2O（氢冶金，还原铁）

准稳态收率模型：单位消耗按理论计量×效率；不做动力学/CFD（V1.2 明确）。
柔性约束：min_load + 每小时爬坡上限（传统 HB 不能跟随风光快速波动——
风光直连必须配储氢缓冲，这正是本平台要量化的核心工程问题）。
"""
from dataclasses import dataclass, field
from typing import Dict, List
import math

# 分子量 g/mol
M = {"H2": 2.016, "N2": 28.013, "NH3": 17.031, "CO2": 44.009,
     "CH3OH": 32.041, "H2O": 18.015, "Fe": 55.845, "Fe2O3": 159.687,
     "O2": 31.998}


class ChemError(ValueError):
    pass


# ---------------- 元素守恒审计（T2 扩展） ----------------
def element_balance(species_in: Dict[str, float], species_out: Dict[str, float]) -> Dict[str, float]:
    """元素守恒审计（C/H/N/O/Fe）。输入/输出 {物种: 质量 kg}，返回各元素不平衡量 kg。

    返回值全部≈0 是化工反应器的 T2 硬门禁；|元素误差|/总元素质量 >0.5% 为 FAIL。
    """
    ELEM = {"H2": {"H": 2}, "N2": {"N": 2}, "NH3": {"N": 1, "H": 3},
            "CO2": {"C": 1, "O": 2}, "CH3OH": {"C": 1, "H": 4, "O": 1},
            "H2O": {"H": 2, "O": 1}, "Fe": {"Fe": 1}, "Fe2O3": {"Fe": 2, "O": 3},
            "O2": {"O": 2}}
    elem_in: Dict[str, float] = {}
    elem_out: Dict[str, float] = {}
    for s, mass in species_in.items():
        if s not in ELEM:
            raise ChemError(f"未登记元素组成: {s}")
        n = mass / M[s]  # mol = 质量/摩尔质量
        for e, k in ELEM[s].items():
            elem_in[e] = elem_in.get(e, 0.0) + n * k
    for s, mass in species_out.items():
        if s not in ELEM:
            raise ChemError(f"未登记元素组成: {s}")
        n = mass / M[s]
        for e, k in ELEM[s].items():
            elem_out[e] = elem_out.get(e, 0.0) + n * k
    return {e: elem_out.get(e, 0.0) - elem_in.get(e, 0.0) for e in set(elem_in) | set(elem_out)}


# ---------------- 合成氨 ----------------
@dataclass
class HaberBoschParams:
    rated_t_per_h: float        # 额定产量 t NH3/h
    h2_per_t_kg: float = 187.0  # 实际耗氢 kg/t NH3（理论 176.9×效率 ~0.95）
    n2_per_t_kg: float = 824.0  # 理论 N2 = 1000×28.013/(2×17.031)
    lec_mwh_per_t: float = 0.35 # 循环压缩+BOP 电耗（合成回路）
    min_load: float = 0.50      # 传统 HB 最小稳定负荷
    ramp_per_h: float = 0.08    # 每小时产量爬坡（8%/h 额定——传统 HB 慢动态）


class HaberBosch:
    """放热反应：N2+3H2->2NH3，ΔH=−46 kJ/mol NH3 → 2.70 GJ/t NH3（高位近似）。"""

    def __init__(self, p: HaberBoschParams):
        if p.rated_t_per_h <= 0:
            raise ChemError("rated_t_per_h 必须为正")
        if not (0.0 <= p.min_load < 1.0):
            raise ChemError("min_load 越界")
        self.p = p
        self.output_t_per_h = 0.0   # 冷启动（连续厂语义由调用者预热；ramp 记忆从此起）
        self.heat_gj_per_t = 46.0 * (1000.0 / 17.031) / 1000.0  # GJ/t NH3 放热（可热回收）

    def step(self, h2_available_kg_per_h: float, n2_available_kg_per_h: float,
             demand_t_per_h: float = None) -> Dict[str, float]:
        """按可用氢/氮与需求运行（准稳态收率+爬坡+最小负荷）。
        返回 {nh3_t, h2_used_kg, n2_used_kg, elec_mwh, heat_gj, rejected_kg}。"""
        p = self.p
        demand = demand_t_per_h if demand_t_per_h is not None else p.rated_t_per_h
        # 氢限制的产量
        by_h2 = h2_available_kg_per_h / p.h2_per_t_kg
        by_n2 = n2_available_kg_per_h / p.n2_per_t_kg
        by_min = p.rated_t_per_h * p.min_load
        target = min(demand, by_h2, by_n2)
        target = max(target, 0.0)
        if target < by_min and by_h2 < by_min:
            # 氢不足以维持最小稳定负荷 → 安全停机（停机不受爬坡下限约束）
            self.output_t_per_h = 0.0
            return {"nh3_t": 0.0, "h2_used_kg": 0.0, "n2_used_kg": 0.0,
                    "elec_mwh": 0.0, "heat_gj": 0.0,
                    "rejected_kg": max(0.0, h2_available_kg_per_h)}
        if target < by_min:
            target = by_min
        # 爬坡约束（下限须 clamp 到氢可用量——罐断供时被迫降负荷，不凭空用氢）
        lo = max(0.0, min(self.output_t_per_h - p.ramp_per_h * p.rated_t_per_h, by_h2))
        hi = self.output_t_per_h + p.ramp_per_h * p.rated_t_per_h
        target = min(target, hi, p.rated_t_per_h)
        target = max(target, lo)
        h2_used = target * p.h2_per_t_kg
        n2_used = target * p.n2_per_t_kg
        self.output_t_per_h = target
        return {"nh3_t": target, "h2_used_kg": h2_used, "n2_used_kg": n2_used,
                "elec_mwh": target * p.lec_mwh_per_t,
                "heat_gj": target * self.heat_gj_per_t,
                "rejected_kg": max(0.0, h2_available_kg_per_h - h2_used)}

    def element_audit(self, nh3_t: float, h2_used_kg: float, n2_used_kg: float) -> Dict[str, float]:
        """理论计量守恒审计（效率损失以弛放气计，不污染守恒账）：
        由实际输出反推理论输入 N2+H2，校验 3H2+N2→2NH3 的 N/H 原子闭合。"""
        n_nh3_kmol = nh3_t * 1000.0 / M["NH3"]            # kmol
        theo_h2 = n_nh3_kmol * 1.5 * M["H2"]               # kg（1.5 mol H2/mol NH3）
        theo_n2 = n_nh3_kmol * 0.5 * M["N2"]
        # 理论输入 vs 化学计量的守恒账（应精确为 0）
        bal = element_balance({"H2": theo_h2, "N2": theo_n2},
                              {"NH3": nh3_t * 1000.0})
        # 实际效率损失（h2_used ≥ theo_h2；差值即弛放/损失，另报）
        bal["h2_purge_kg"] = h2_used_kg - theo_h2
        bal["n2_purge_kg"] = n2_used_kg - theo_n2
        return bal


# ---------------- 甲醇 ----------------
@dataclass
class MethanolParams:
    rated_t_per_h: float
    h2_per_t_kg: float = 193.0   # 理论 189.1×效率
    co2_per_t_kg: float = 1376.0 # 理论 1374×效率
    lec_mwh_per_t: float = 0.20
    min_load: float = 0.40
    ramp_per_h: float = 0.10
    h2o_per_t_kg: float = 564.0 # 副产水（理论 561）


class Methanol:
    def __init__(self, p: MethanolParams):
        if p.rated_t_per_h <= 0:
            raise ChemError("rated_t_per_h 必须为正")
        self.p = p
        self.output_t_per_h = 0.0
        self.heat_gj_per_t = 49.5 * (1000.0 / 32.041) / 1000.0  # GJ/t

    def step(self, h2_available_kg_per_h, co2_available_kg_per_h, demand_t_per_h=None):
        p = self.p
        demand = demand_t_per_h if demand_t_per_h is not None else p.rated_t_per_h
        by_h2 = h2_available_kg_per_h / p.h2_per_t_kg
        by_co2 = co2_available_kg_per_h / p.co2_per_t_kg
        by_min = p.rated_t_per_h * p.min_load
        target = max(0.0, min(demand, by_h2, by_co2))
        if target < by_min and by_h2 < by_min:
            self.output_t_per_h = 0.0
            return {"meoh_t": 0.0, "h2_used_kg": 0.0, "co2_used_kg": 0.0,
                    "h2o_produced_kg": 0.0, "elec_mwh": 0.0, "heat_gj": 0.0,
                    "rejected_kg": max(0.0, h2_available_kg_per_h)}
        if target < by_min:
            target = by_min
        lo = max(0.0, min(self.output_t_per_h - p.ramp_per_h * p.rated_t_per_h, by_h2))
        hi = self.output_t_per_h + p.ramp_per_h * p.rated_t_per_h
        target = min(target, hi, p.rated_t_per_h)
        target = max(target, lo)
        self.output_t_per_h = target
        h2_used = target * p.h2_per_t_kg
        co2_used = target * p.co2_per_t_kg
        return {"meoh_t": target, "h2_used_kg": h2_used, "co2_used_kg": co2_used,
                "h2o_produced_kg": target * p.h2o_per_t_kg,
                "elec_mwh": target * p.lec_mwh_per_t,
                "heat_gj": target * self.heat_gj_per_t,
                "rejected_kg": max(0.0, h2_available_kg_per_h - h2_used)}

    def element_audit(self, meoh_t, h2_used, co2_used, h2o_out):
        """理论计量守恒审计（CO2+3H2→CH3OH+H2O 的 C/H/O 闭合）。"""
        n_meoh_kmol = meoh_t * 1000.0 / M["CH3OH"]
        theo_h2 = n_meoh_kmol * 3.0 * M["H2"]
        theo_co2 = n_meoh_kmol * 1.0 * M["CO2"]
        theo_h2o = n_meoh_kmol * 1.0 * M["H2O"]
        bal = element_balance({"H2": theo_h2, "CO2": theo_co2},
                              {"CH3OH": meoh_t * 1000.0, "H2O": theo_h2o})
        bal["h2_purge_kg"] = h2_used - theo_h2
        bal["co2_purge_kg"] = co2_used - theo_co2
        bal["h2o_note_kg"] = h2o_out - theo_h2o
        return bal


# ---------------- 氢冶金 DRI ----------------
@dataclass
class DRIParams:
    rated_t_per_h: float          # t 铁/h
    h2_per_t_fe_kg: float = 55.0  # 理论 54.2×损耗
    ore_per_t_fe_kg: float = 1430.0  # Fe2O3 理论 1430.9×品位
    lec_mwh_per_t: float = 0.15
    min_load: float = 0.60        # 竖炉连续还原
    ramp_per_h: float = 0.05


class DRI:
    """Fe2O3 + 3H2 -> 2Fe + 3H2O（吨铁降碳 ~1.6-1.9 t CO2 vs 长流程）。"""

    def __init__(self, p: DRIParams):
        if p.rated_t_per_h <= 0:
            raise ChemError("rated_t_per_h 必须为正")
        self.p = p
        self.output_t_per_h = 0.0
        self.endo_gj_per_t = 0.0   # 还原净吸热小，忽略（准稳态口径注明）

    def step(self, h2_available_kg_per_h, demand_t_per_h=None):
        p = self.p
        demand = demand_t_per_h if demand_t_per_h is not None else p.rated_t_per_h
        by_h2 = h2_available_kg_per_h / p.h2_per_t_fe_kg
        by_min = p.rated_t_per_h * p.min_load
        target = max(0.0, min(demand, by_h2))
        if target < by_min and by_h2 < by_min:
            self.output_t_per_h = 0.0
            return {"fe_t": 0.0, "h2_used_kg": 0.0, "ore_used_kg": 0.0,
                    "h2o_produced_kg": 0.0, "elec_mwh": 0.0,
                    "rejected_kg": max(0.0, h2_available_kg_per_h)}
        if target < by_min:
            target = by_min
        lo = max(0.0, min(self.output_t_per_h - p.ramp_per_h * p.rated_t_per_h, by_h2))
        hi = self.output_t_per_h + p.ramp_per_h * p.rated_t_per_h
        target = min(target, hi, p.rated_t_per_h)
        target = max(target, lo)
        self.output_t_per_h = target
        h2_used = target * p.h2_per_t_fe_kg
        return {"fe_t": target, "h2_used_kg": h2_used,
                "ore_used_kg": target * p.ore_per_t_fe_kg,
                "h2o_produced_kg": target * p.ore_per_t_fe_kg * 27.0 / 159.687,  # 3H2O/Fe2O3
                "elec_mwh": target * p.lec_mwh_per_t,
                "rejected_kg": max(0.0, h2_available_kg_per_h - h2_used)}

    def element_audit(self, fe_t, h2_used, ore_used, h2o_out):
        """理论计量守恒审计（Fe2O3+3H2→2Fe+3H2O 的 Fe/O/H 闭合）。"""
        n_fe_kmol = fe_t * 1000.0 / M["Fe"]
        theo_h2 = n_fe_kmol * 1.5 * M["H2"]          # 3H2/2Fe = 1.5
        theo_ore = n_fe_kmol * 0.5 * M["Fe2O3"]      # Fe2O3/2Fe = 0.5
        theo_h2o = n_fe_kmol * 1.5 * M["H2O"]        # 3H2O/2Fe = 1.5
        bal = element_balance({"Fe2O3": theo_ore, "H2": theo_h2},
                              {"Fe": fe_t * 1000.0, "H2O": theo_h2o})
        bal["h2_purge_kg"] = h2_used - theo_h2
        bal["ore_note_kg"] = ore_used - theo_ore
        return bal


# ---------------- ASU 空分 ----------------
@dataclass
class ASUParams:
    lec_kwh_per_kg_n2: float = 0.35
    o2_coproduct_kg_per_kg_n2: float = 0.27  # 空气 21%O2/78%N2≈0.27 kg O2/kg N2


class ASU:
    def __init__(self, p: ASUParams):
        self.p = p

    def make_n2(self, n2_kg_per_h: float) -> Dict[str, float]:
        if n2_kg_per_h < 0:
            raise ChemError("N2 需求为负")
        return {"elec_mwh": n2_kg_per_h * self.p.lec_kwh_per_kg_n2 / 1000.0,
                "o2_kg": n2_kg_per_h * self.p.o2_coproduct_kg_per_kg_n2}
