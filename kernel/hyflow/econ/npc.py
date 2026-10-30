# -*- coding: utf-8 -*-
"""经济简算：Total NPC 与 LCOE（HOMER 公开口径，V1.2 §4.6）。

Total NPC = Σ_设备 [CAPEX + Σ_k OPEX_k×(1/(1+r)^k) + Σ_替换 (1/(1+r)^(y×k))]（残值 0 简化）
LCOE = TotalNPC × CRF / 年供给电量，CRF = r(1+r)^n / ((1+r)^n - 1)
"""


class EconError(ValueError):
    pass


def crf(discount_rate: float, years: int) -> float:
    if not (0.0 < discount_rate < 0.5):
        raise EconError(f"discount_rate={discount_rate} 非法 (0,0.5)")
    if years < 1:
        raise EconError("years>=1")
    r, n = discount_rate, years
    return r * (1 + r) ** n / ((1 + r) ** n - 1)


def capital_recovery_cost(capex: float, life_years: int, project_years: int,
                          discount_rate: float) -> float:
    """设备全周期成本现值：CAPEX + 期间内整备替换 + 年 OPEX 现值（OPEX 由调用方另行计）。"""
    life_years = int(life_years)          # 注册表值为 float——入口强制 int（铁律3：显式而非静默）
    project_years = int(project_years)
    if life_years < 1 or project_years < 1:
        raise EconError("寿命/期数 >=1")
    r = discount_rate
    n_repl = max(0, (project_years - 1) // life_years)
    pv = capex
    for k in range(1, n_repl + 1):
        pv += capex / (1 + r) ** (k * life_years)
    return pv


def total_npc(items: list, project_years: int, discount_rate: float) -> float:
    """items = [{'capex': C, 'life_years': L, 'opex_annual': O}, ...]"""
    r = discount_rate
    project_years = int(project_years)
    npc = 0.0
    for it in items:
        c = it["capex"]
        life = int(it["life_years"])
        opex = it.get("opex_annual", 0.0)
        if c < 0 or life < 1 or opex < 0:
            raise EconError(f"非法经济输入: {it}")
        npc += capital_recovery_cost(c, life, project_years, r)
        # OPEX 年金现值
        if opex > 0:
            ann = sum(1.0 / (1 + r) ** t for t in range(1, project_years + 1))
            npc += opex * ann
    return npc


def lcoe(npc_total: float, annual_served_kwh: float, discount_rate: float, years: int) -> float:
    if annual_served_kwh <= 0:
        raise EconError("年供给电量为 0——LCOE 无定义（铁律3：不静默返回 0）")
    return npc_total * crf(discount_rate, years) / annual_served_kwh
