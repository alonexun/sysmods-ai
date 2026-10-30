# -*- coding: utf-8 -*-
"""0D 集总参数床仿真（mt_abs.m / mt_des.m 等价 + 能量账 ODE 状态化）。

状态: [w (kg_H/kg_M), T (K), e_rxn (J/kg_M), e_amb (J/kg_M), h2_int (kg/kg)]
ODE:  dw/dt    = hydride.dwdt(T, P, w)
      dT/dt    = (dEdt + Uth/m·(Ti−T)) / Cp(w)
      de_rxn/dt= dEdt(T, P, w)             [反应热，吸氢放热为正]
      de_amb/dt= Uth/m·(Ti−T)              [环境换热，床得热为正]
      dh2_int/dt= dwdt                     [氢累计（质量账）]
能量账为 ODE 状态的一部分（BDF 内部精度）——dense 重积分在秒级动力学阶跃区
会因插值超调失真（实测 2 倍），故弃用。
注: mt_abs.m 的 Uth/A.rho 疑为"Uth/床质量"笔误——本版按能量守恒直写。
"""
from dataclasses import dataclass
import numpy as np
from scipy.integrate import solve_ivp


class BedError(ValueError):
    pass


@dataclass
class BedResult:
    t: np.ndarray
    w: np.ndarray
    T: np.ndarray
    e_rxn_kj: float        # 反应热累计 kJ（正=放热）——ODE 状态
    e_ambient_kj: float     # 环境换热累计 kJ（正=床从环境得热）——ODE 状态
    e_stored_kj: float     # = e_rxn + e_ambient（0D 显热框架下按定义恒等，供报告）
    h2_int_kg_per_kg: float  # ∫dwdt dt（氢质量账）——ODE 状态


def simulate_bed(hydride, w0: float, T0: float, Ti: float, P: float,
                 uth_w_per_k: float, mass_kg: float, t_span=(0.0, 1500.0),
                 n_out: int = 300) -> BedResult:
    """恒压供/放氢仿真。P 恒定（mt_abs: P=4×Peq_abs@Ti；mt_des: P=0.2×Peq_des@Ti）。"""
    if not (0.0 <= w0 <= hydride.wMax + 1e-12):
        raise BedError(f"w0={w0} 超出 [0,{hydride.wMax}]")
    if mass_kg <= 0 or uth_w_per_k < 0:
        raise BedError("床质量/传热系数非法")
    if t_span[1] <= t_span[0]:
        raise BedError("时间区间非法")

    y0 = [w0, T0, 0.0, 0.0, 0.0]

    def rhs(t, y):
        w, T, e_rxn, e_amb, h2_int = y
        w = min(max(w, 0.0), hydride.wMax)
        dwdt = hydride.dwdt(T, P, w)
        dEdt = hydride.dEdt(T, P, w)                     # W/kg_M
        d_amb = uth_w_per_k / mass_kg * (Ti - T)         # W/kg_M
        dTdt = (dEdt + d_amb) / hydride.Cp(w)
        return [dwdt, dTdt, dEdt, d_amb, dwdt]

    sol = solve_ivp(rhs, t_span, y0, method="BDF",
                    t_eval=np.linspace(t_span[0], t_span[1], n_out),
                    rtol=1e-7, atol=[1e-10, 1e-7, 1e-6, 1e-6, 1e-12])
    if not sol.success:
        raise BedError(f"ODE 求解失败: {sol.message}")

    w = np.clip(sol.y[0], 0.0, hydride.wMax)
    T = sol.y[1]
    e_rxn_kj = mass_kg * sol.y[2, -1] / 1000.0
    e_amb_kj = mass_kg * sol.y[3, -1] / 1000.0
    return BedResult(t=sol.t, w=w, T=T,
                     e_rxn_kj=e_rxn_kj, e_ambient_kj=e_amb_kj,
                     e_stored_kj=e_rxn_kj + e_amb_kj,
                     h2_int_kg_per_kg=float(sol.y[4, -1]))
