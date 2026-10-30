# -*- coding: utf-8 -*-
"""MHStore：把 PMHT 物理接入 T1 时序引擎（接口兼容线性 H2Store）。

规划级准稳态假设（1h 步 >> 动力学 τ 秒级，V1.2 §6.2 的"1h 步准稳态"路线）：
- 充氢上限由 Peq_abs(T_bed, ·) 反解的平衡容量 w_eq 决定（供氢压力 p_supply）
- 放氢下限由 Peq_des(T_bed, ·) 平衡 w_eq 决定（母线压力 p_bus）
- 床温每步显式推进：吸氢放热升温（抬高 Peq → 充氢自限）、放氢吸热降温（压低 Peq → 放氢衰减）
  ——高原站"冬季放氢需补热"的核心物理由此进入系统仿真
- q_rxn_w 热账输出：吸氢放热为正、放氢吸热为负（进引擎热总线账）
"""
from .hydride import Hydride


class MHStoreError(ValueError):
    pass


class MHStore:
    def __init__(self, hydride: Hydride, mass_kg: float, t_init_k: float,
                 t_ambient_k: float, uth_w_per_k: float,
                 p_supply_pa: float, p_bus_pa: float, w_init_ratio: float = 0.5):
        if mass_kg <= 0 or uth_w_per_k < 0:
            raise MHStoreError("床质量/传热系数非法")
        if p_supply_pa <= 0 or p_bus_pa <= 0:
            raise MHStoreError("供/母线压力必须为正")
        self.hydride = hydride
        self.mass_kg = mass_kg
        self.capacity_kg = mass_kg * hydride.wMax
        self.T_bed = t_init_k
        self.T_ambient = t_ambient_k
        self.uth = uth_w_per_k
        self.p_supply = p_supply_pa
        self.p_bus = p_bus_pa
        self.level_kg = w_init_ratio * self.capacity_kg
        self.q_rxn_w = 0.0          # 当前步反应热功率 W（正=床放热）
        self.charge_rejects = 0     # 热力学拒绝（Peq 门控）计数——有效信息

    # ---------------- 与 H2Store 兼容的接口 ----------------
    @property
    def soc(self) -> float:
        return self.level_kg / self.capacity_kg if self.capacity_kg > 0 else 0.0

    def _w(self) -> float:
        return self.level_kg / self.mass_kg       # kg_H/kg_M

    def _w_eq(self, P: float, mode: str) -> float:
        """二分反解 Peq(T_bed, w_eq, mode) = P。P 高于全平台时返回 wMax，低于时 0。"""
        h = self.hydride
        lo, hi = 0.0, h.wMax
        p_lo = h.Peq(self.T_bed, lo, mode)
        p_hi = h.Peq(self.T_bed, hi, mode)
        if P >= p_hi:
            return h.wMax
        if P <= p_lo:
            return 0.0
        for _ in range(60):
            mid = 0.5 * (lo + hi)
            if h.Peq(self.T_bed, mid, mode) < P:
                lo = mid
            else:
                hi = mid
        return 0.5 * (lo + hi)

    def _step_thermal(self, dm_kg: float, dt_h: float, absorbing: bool):
        """床温步内解析解（1h 步 >> 热时间常数 τ，显式欧拉会发散——必须用解析解）。

        d(T−T_amb)/dt = q/(m·Cp) − (T−T_amb)/τ,  τ = m·Cp/Uth
        精确解: T(t) = T_amb + q/Uth·(1−e^(−t/τ)) + (T0−T_amb)·e^(−t/τ)
        （q 为步内平均反应热功率，恒定近似）"""
        dt = dt_h * 3600.0
        dH = self.hydride.dH("abs" if absorbing else "des")
        q_abs = dH * dm_kg / dt if dt > 0 else 0.0     # W（绝对值）
        self.q_rxn_w = q_abs if absorbing else -q_abs
        cp = self.hydride.Cp(self._w())
        tau = self.mass_kg * cp / self.uth if self.uth > 0 else float("inf")
        decay = __import__("math").exp(-dt / tau) if tau > 0 else 0.0
        self.T_bed = self.T_ambient \
            + (self.q_rxn_w / self.uth if self.uth > 0 else 0.0) * (1.0 - decay) \
            + (self.T_bed - self.T_ambient) * decay
        # q/Uth 项在 q=0 时为 0；Uth=0（绝热）时退化为恒 q 升温
        if self.uth <= 0:
            self.T_bed = self.T_bed + self.q_rxn_w * dt / (self.mass_kg * cp)

    def charge(self, offer_kg_per_h: float, dt_h: float = 1.0) -> float:
        """电解供氢 offer kg/h @ p_supply。受 Peq 平衡容量门控。"""
        if offer_kg_per_h < 0:
            raise MHStoreError("charge offer 为负")
        w = self._w()
        w_eq = self._w_eq(self.p_supply, "abs")
        headroom_kg = max(0.0, (w_eq - w)) * self.mass_kg
        if headroom_kg <= 0:
            self.charge_rejects += 1
            self._step_thermal(0.0, dt_h, absorbing=True)  # 仍与环境换热
            return 0.0
        actual = min(offer_kg_per_h * dt_h, headroom_kg)
        self.level_kg += actual
        self._step_thermal(actual, dt_h, absorbing=True)
        return actual / dt_h

    def discharge(self, demand_kg_per_h: float, dt_h: float = 1.0) -> float:
        """FC 需氢 demand kg/h @ p_bus。低于平衡压 Peq_des 的部分无法放出。"""
        if demand_kg_per_h < 0:
            raise MHStoreError("discharge demand 为负")
        w = self._w()
        w_eq = self._w_eq(self.p_bus, "des")
        releasable_kg = max(0.0, (w - w_eq)) * self.mass_kg
        if releasable_kg <= 0:
            self._step_thermal(0.0, dt_h, absorbing=False)
            return 0.0
        actual = min(demand_kg_per_h * dt_h, releasable_kg)
        self.level_kg -= actual
        self._step_thermal(actual, dt_h, absorbing=False)
        return actual / dt_h

    # 引擎兼容别名（bed temperature 供结果序列）
    @property
    def t_bed_k(self) -> float:
        return self.T_bed
