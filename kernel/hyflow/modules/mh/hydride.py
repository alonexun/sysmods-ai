# -*- coding: utf-8 -*-
"""Hydride 类：PMHT @MetalHydride/Peq.m 逐段移植 + KineticsModel 等价。

Peq: 多平台 van't Hoff + 滞后(abs/des) + 正则溶液边缘 + 平台间三次多项式平滑
     + 临界温度 Tc 上下参数混合。返回 Pa。
dwdt: Ca·exp(-Ea/RT)·wFcn·pFcn，kg_H/(kg_M·s)，吸正放负。
dEdt: |dH|·dwdt，W/kg_M（吸氢放热为正——mt_abs 供氢放热、mt_des 放氢吸热）。
Cp:   Cp_metal·(1 + (w/wMax)·HM)  [Dadson & Fluckiger]
"""
import math
import numpy as np

from .parser import (HydrideSpec, R_GAS, MH2_KG_PER_MOL)

P0 = 101325.0  # Pa


class HydrideError(ValueError):
    pass


_PFCN = {
    "log": lambda p, peq: math.log(p / peq),
    "linear": lambda p, peq: p - peq,
    "normalized linear": lambda p, peq: (p - peq) / peq,
}


class Hydride:
    def __init__(self, spec: HydrideSpec):
        self.s = spec
        self.name = spec.name
        self.wMax = spec.w_max                       # kg_H/kg_M
        self.HM = spec.hm
        self.n = spec.n_plateaus
        self._last_curve_cache = {}

    # ---------------- Peq（Peq.m 逐段） ----------------
    def Peq(self, T: float, w: float, mode: str) -> float:
        """平衡压 Pa。mode: 'abs'/'des'。标量实现（引擎逐步调用）。"""
        if mode.lower().startswith("abs"):
            th_abs = True
        elif mode.lower().startswith("des"):
            th_abs = False
        else:
            raise HydrideError(f"mode 必须为 'abs'/'des'，得到 {mode!r}")
        x = w / self.wMax

        centers, widths = self.s.centers, self.s.widths
        n = self.n
        # 截断避免 log 项发散（Peq.m L90-91）
        xlo = centers[0] - widths[0] / 2 + 1e-4
        xhi = centers[-1] + widths[-1] / 2 - 1e-4
        x = min(max(x, xlo), xhi)

        # 平台参数（超 Tc 用 abs/des 平均，Peq.m L95-106）
        dHs, dSs, As = [], [], []
        for p in range(n):
            subcrit = T < self.s.Tc[p]
            if subcrit:
                dH = self.s.abss.dH[p] if th_abs else self.s.des.dH[p]
                dS = self.s.abss.dS[p] if th_abs else self.s.des.dS[p]
                A = self.s.A[p]
            else:
                dH = 0.5 * (self.s.abss.dH[p] + self.s.des.dH[p])
                dS = 0.5 * (self.s.abss.dS[p] + self.s.des.dS[p])
                A = self.s.A[p]
            dHs.append(dH); dSs.append(dS); As.append(A)

        # 两相区边界（Peq.m L110-119）
        xL, xR = [], []
        for p in range(n):
            denom = As[p] + 2.0 * self.s.omega[p]
            D = 1.0 - 4.0 * R_GAS * T / denom if denom > 0 else -1.0
            if D < 0:
                D = 0.0
            sq = math.sqrt(D)
            xpL = (1 - sq) / 2
            xpR = (1 + sq) / 2
            xL.append((xpL - 0.5) * widths[p] + centers[p])
            xR.append((xpR - 0.5) * widths[p] + centers[p])

        # mu0（Peq.m L122）
        mu0 = [dHs[p] - T * dSs[p] for p in range(n)]

        # 平台边界与过渡（Peq.m L129-176）
        mu = None
        minSpans = self.s.min_spans

        def span(p):  # 平台间过渡宽度
            return max(minSpans[p - 1] if p - 1 < len(minSpans) else 0.0,
                       xL[p] - xR[p - 1]) if p - 1 < len(minSpans) else \
                   max(0.0, xL[p] - xR[p - 1])

        for p in range(n):
            # xLlim / xRlim
            if p > 0:
                xMid = 0.5 * (xL[p] + xR[p - 1])
                xSpan = (max(minSpans[p - 1], xL[p] - xR[p - 1])
                         if p - 1 < len(minSpans) else max(0.0, xL[p] - xR[p - 1]))
                xLlim = xMid + xSpan / 2
            else:
                xLlim = xL[p]
            if p < n - 1:
                xMid = 0.5 * (xR[p] + xL[p + 1])
                xSpan = (max(minSpans[p], xL[p + 1] - xR[p])
                         if p < len(minSpans) else max(0.0, xL[p + 1] - xR[p]))
                xRlim = xMid - xSpan / 2
            else:
                xRlim = xR[p]

            if x >= xLlim and x <= xRlim:
                mu = mu0[p] + As[p] * ((x - centers[p]) / widths[p])
                break
            # 过渡多项式（平台 p → p+1）
            if p < n - 1:
                x1 = xRlim
                xMean = 0.5 * (xL[p + 1] + xR[p])
                xSpan = (max(minSpans[p], xL[p + 1] - xR[p])
                         if p < len(minSpans) else max(0.0, xL[p + 1] - xR[p]))
                x2 = xMean + xSpan / 2
                if x1 < x < x2:
                    mu1 = mu0[p] + As[p] * (x1 - centers[p]) / widths[p]
                    mu2 = mu0[p + 1] + As[p + 1] * (x2 - centers[p + 1]) / widths[p + 1]
                    A_ = np.array([[x1**3, x1**2, x1, 1.0],
                                   [x2**3, x2**2, x2, 1.0],
                                   [3 * x1**2, 2 * x1, 1.0, 0.0],
                                   [3 * x2**2, 2 * x2, 1.0, 0.0]])
                    b_ = np.array([mu1, mu2, As[p] / widths[p], As[p + 1] / widths[p + 1]])
                    pf = np.linalg.solve(A_, b_)
                    mu = float(np.polyval(pf, x))
                    break
        if mu is None:
            # 边缘：正则溶液模型（Peq.m L180-193）
            denom0 = As[0] + 2.0 * self.s.omega[0]
            D0 = max(0.0, 1.0 - 4.0 * R_GAS * T / denom0)
            xpL0 = (1 - math.sqrt(D0)) / 2
            denomE = As[-1] + 2.0 * self.s.omega[-1]
            DE = max(0.0, 1.0 - 4.0 * R_GAS * T / denomE)
            xpR0 = (1 + math.sqrt(DE)) / 2
            muL_plateau = mu0[0] + As[0] * (xL[0] - centers[0]) / widths[0]
            muR_plateau = mu0[-1] + As[-1] * (xR[-1] - centers[-1]) / widths[-1]
            muRSL0 = muL_plateau - (1 - 2 * xpL0) * self.s.omega[0] \
                - R_GAS * T * math.log(xpL0 / (1 - xpL0))
            muRSH0 = muR_plateau - (1 - 2 * xpR0) * self.s.omega[-1] \
                - R_GAS * T * math.log(xpR0 / (1 - xpR0))
            if x < xL[0]:
                xpLx = (x - centers[0]) / widths[0] + 0.5
                if xpLx <= 1e-6:
                    # 数据卡适用域之外（α 固溶体外推无意义）：返回平台边缘平衡压
                    mu = mu0[0] + As[0] * ((xL[0] - centers[0]) / widths[0])
                else:
                    xpLx = min(xpLx, 1 - 1e-9)
                    mu = muRSL0 + (1 - 2 * xpLx) * self.s.omega[0] \
                        + R_GAS * T * math.log(xpLx / (1 - xpLx))
            else:  # x > xR[-1]
                xpRx = (x - centers[-1]) / widths[-1] + 0.5
                if xpRx >= 1 - 1e-6:
                    mu = mu0[-1] + As[-1] * ((xR[-1] - centers[-1]) / widths[-1])
                else:
                    xpRx = max(xpRx, 1e-9)
                    mu = muRSH0 + (1 - 2 * xpRx) * self.s.omega[-1] \
                        + R_GAS * T * math.log(xpRx / (1 - xpRx))

        return P0 * math.exp(mu / (R_GAS * T))

    # ---------------- 动力学（KineticsModel.dwdt 等价） ----------------
    def dwdt(self, T: float, P: float, w: float) -> float:
        """kg_H/(kg_M·s)。吸正放负。"""
        Peq_abs = self.Peq(T, w, "abs")
        Peq_des = self.Peq(T, w, "des")
        ka, kd = self.s.kin_abs, self.s.kin_des
        if P > Peq_abs and w < self.wMax:
            pf = _PFCN.get(ka.pFcn, _PFCN["log"])
            wf = (self.wMax - w) if "1st" in ka.wFcn else self.wMax
            return ka.Ca * math.exp(-ka.Ea / (R_GAS * T)) * wf * pf(P, Peq_abs)
        elif P < Peq_des and w > 0.0:
            pf = _PFCN.get(kd.pFcn, _PFCN["log"])
            wf = w if "1st" in kd.wFcn else self.wMax
            return kd.Ca * math.exp(-kd.Ea / (R_GAS * T)) * wf * pf(P, Peq_des)
        return 0.0

    # ---------------- 反应焓（MetalHydride.dH 等价，绝对值 J/kg_H） ----------------
    def dH(self, arg, w=None) -> float:
        """arg: 'abs'/'des' 或 dwdt 值（按符号定向）。返回 |ΔH| J/kg_H。"""
        if isinstance(arg, str):
            mode = arg.lower()
            absorbing = mode.startswith("abs")
        else:
            absorbing = arg > 0
        src = self.s.abss if absorbing else self.s.des
        if w is not None and self.n > 1:
            x = w / self.wMax
            # 找所在平台（按宽度加权 fallback）
            for p in range(self.n):
                if self.s.centers[p] - self.s.widths[p] / 2 <= x <= \
                   self.s.centers[p] + self.s.widths[p] / 2:
                    return abs(src.dH[p]) / MH2_KG_PER_MOL
        if self.n > 1:
            total_w = sum(self.s.widths)
            dh = sum(abs(h) * wd for h, wd in zip(src.dH, self.s.widths)) / total_w
            return dh / MH2_KG_PER_MOL
        return abs(src.dH[0]) / MH2_KG_PER_MOL

    def dEdt(self, T: float, P: float, w: float) -> float:
        """W/kg_M。吸氢放热为正（mt_abs），放氢吸热为负（mt_des）。"""
        r = self.dwdt(T, P, w)
        return self.dH(r, w) * r

    # ---------------- Cp（Dadson & Fluckiger） ----------------
    def Cp(self, w: float = 0.0) -> float:
        F = w / self.wMax if self.wMax > 0 else 0.0
        if F > 1.1:
            raise HydrideError("Input weight fraction is too high for this hydride")
        return self.s.Cp * (1.0 + F * self.HM)

    # ---------------- 便捷 ----------------
    @property
    def level_kg(self):
        return None

    def summary(self) -> str:
        s = self.s
        return (f"{self.name} [{s.hydride_type}] wMax={self.wMax*100:.2f}wt% "
                f"plateaus={self.n} Tc={s.Tc[0]:.0f}K "
                f"kin_abs_assumed={s.kin_abs.assumed} kin_des_assumed={s.kin_des.assumed} "
                f"thermo_level={s.thermo_level} refs={len(s.references)}")
