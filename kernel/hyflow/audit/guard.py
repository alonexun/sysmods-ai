# -*- coding: utf-8 -*-
"""守恒审计器（T2 硬门禁）——框架级强制，非模块自觉。

每步：电平衡 / 氢平衡。年累计相对误差 > 0.5% → 报告 FAIL（结果不出、报告不生成）。
fail 二分（V1.2 §3.2）：
- 数值守恒误差 = bug 拦截（报 Violation）
- 场景物理不可行（失电/弃电/罐满）= 有效信息，计入统计不拦截
"""
from dataclasses import dataclass, field
from typing import List


@dataclass
class Violation:
    step: int
    kind: str        # 'elec' / 'h2'
    err: float
    detail: str


@dataclass
class ConservationReport:
    passed: bool
    elec_err_rel_annual: float
    h2_err_rel_annual: float
    violations: List[Violation] = field(default_factory=list)
    tol_step: float = 1e-6
    tol_annual_rel: float = 0.005

    def summary(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        return (f"守恒审计[{status}] 电平衡年误差={self.elec_err_rel_annual:.3e} "
                f"氢平衡年误差={self.h2_err_rel_annual:.3e} 违例步数={len(self.violations)}")


class ConservationAuditor:
    """逐步累计+终检。step_* 返回该步误差（供测试断言）；finish 出报告。"""

    def __init__(self, tol_step: float = 1e-6, tol_annual_rel: float = 0.005):
        self.tol_step = tol_step
        self.tol_annual_rel = tol_annual_rel
        self.violations: List[Violation] = []
        self._elec_abs = 0.0
        self._elec_scale = 0.0
        self._h2_abs = 0.0
        self._h2_scale = 0.0

    def step_elec(self, t: int, supply_kw, demand_kw) -> float:
        """supply = pv+fc+bess_dis+unmet(缺供计入供给侧使平衡式闭合)；
        demand = load+bess_chg+pem+curtail。返回误差(绝对 kW)。"""
        err = supply_kw - demand_kw
        scale = max(abs(supply_kw), abs(demand_kw), 1e-9)
        if abs(err) > self.tol_step + 1e-3 * scale:
            self.violations.append(Violation(t, "elec", err,
                f"supply={supply_kw:.6f} demand={demand_kw:.6f}"))
        self._elec_abs += abs(err)
        self._elec_scale += scale
        return err

    def step_h2(self, t: int, produced_kg_per_h, consumed_kg_per_h, store_delta_kg_per_h) -> float:
        """produced - consumed - Δstore = 0。"""
        err = produced_kg_per_h - consumed_kg_per_h - store_delta_kg_per_h
        scale = max(abs(produced_kg_per_h), abs(consumed_kg_per_h),
                    abs(store_delta_kg_per_h), 1e-9)
        if abs(err) > self.tol_step + 1e-3 * scale:
            self.violations.append(Violation(t, "h2", err,
                f"prod={produced_kg_per_h:.9f} cons={consumed_kg_per_h:.9f} dstore={store_delta_kg_per_h:.9f}"))
        self._h2_abs += abs(err)
        self._h2_scale += scale
        return err

    def finish(self) -> ConservationReport:
        elec_rel = self._elec_abs / max(self._elec_scale, 1e-12)
        h2_rel = self._h2_abs / max(self._h2_scale, 1e-12)
        passed = (elec_rel <= self.tol_annual_rel and h2_rel <= self.tol_annual_rel
                  and len(self.violations) == 0)
        return ConservationReport(passed=passed,
                                  elec_err_rel_annual=elec_rel,
                                  h2_err_rel_annual=h2_rel,
                                  violations=list(self.violations),
                                  tol_step=self.tol_step)


def check_energy_directions(e_pem_kwh: float, h2_prod_kg: float,
                            e_fc_kwh: float, h2_cons_kg: float,
                            lvh_kwh_per_kg: float = 33.33) -> List[Violation]:
    """能量方向审计（守恒查平衡，方向查物理——修复产氢公式反向错误后新增）。

    - 电解：产氢能量 ≤ 输入电能（否则"效率>100%"物理违例）
    - FC：发电 ≤ 耗氢能量
    """
    out = []
    tol = 1e-6 * max(1.0, e_pem_kwh)
    if h2_prod_kg * lvh_kwh_per_kg > e_pem_kwh + tol:
        out.append(Violation(
            step=-1, kind="phys",
            err=h2_prod_kg * lvh_kwh_per_kg - e_pem_kwh,
            detail=(f"电解方向违例: 产氢能量 {h2_prod_kg * lvh_kwh_per_kg:.3f} kWh"
                    f" > 耗电 {e_pem_kwh:.3f} kWh（效率>100%，产氢公式方向疑似错误）")))
    tol2 = 1e-6 * max(1.0, e_fc_kwh)
    if e_fc_kwh > h2_cons_kg * lvh_kwh_per_kg + tol2:
        out.append(Violation(
            step=-1, kind="phys",
            err=e_fc_kwh - h2_cons_kg * lvh_kwh_per_kg,
            detail=(f"FC 方向违例: 发电 {e_fc_kwh:.3f} kWh"
                    f" > 耗氢能量 {h2_cons_kg * lvh_kwh_per_kg:.3f} kWh（效率>100%）")))
    return out


# 模块级常量供报告引用
TOL_ANNUAL_REL = 0.005
