# -*- coding: utf-8 -*-
"""T1 时序执行引擎（离网光储氢电，1h 步长）。

调度规则（离网、保供优先）：
  1. PV 优先供负荷
  2. 盈余 → BESS 充电（功率/容量边界）→ PEM 制氢（min-load/额定/罐容边界）→ 弃电
  3. 缺口 → BESS 放电 → FC 发电（罐有氢）→ 失电（记录，不静默）
每步电/氢守恒审计；年误差 >0.5% → FAIL。
"""
from dataclasses import dataclass, field
from typing import Dict
import numpy as np

from .modules.pv import PvParams, pv_power_simple
from .modules.pemwe import Pemwe, PemweParams
from .modules.bess import Bess, BessParams
from .modules.h2store import H2Store
from .modules.fuelcell import FuelCell, FcParams
from .modules.phys import H2_LHV_KWH_PER_KG
from .audit.guard import ConservationAuditor, check_energy_directions
from .uq.confidence import assess, ConfidenceInput
from .econ.npc import total_npc, lcoe, crf


@dataclass
class T1Config:
    pv: PvParams
    bess: BessParams
    pemwe: PemweParams
    fc: FcParams
    h2store_capacity_kg: float
    h2store_init_kg: float
    econ: Dict            # econ.* 键值
    mh_store: object = None   # MHStore 实例（固态储氢模式；None=线性罐）
    comp: object = None       # Compressor 实例（高压储氢路径逐时耦合；None=未启用）


@dataclass
class T1Result:
    hours: np.ndarray = None
    pv_kw: np.ndarray = None
    load_kw: np.ndarray = None
    bess_chg_kw: np.ndarray = None
    bess_dis_kw: np.ndarray = None
    bess_soc: np.ndarray = None
    pem_kw: np.ndarray = None
    h2_prod_kg_per_h: np.ndarray = None
    h2_store_level_kg: np.ndarray = None
    h2_cons_kg_per_h: np.ndarray = None
    fc_kw: np.ndarray = None
    curtail_kw: np.ndarray = None
    unmet_kw: np.ndarray = None
    cons_report: object = None
    kpi: Dict = field(default_factory=dict)
    confidence: object = None
    econ: Dict = field(default_factory=dict)
    mh_t_bed_k: object = None    # 固态储氢床温序列（MH 模式）
    mh_q_rxn_w: object = None    # 固态储氢反应热账序列（正=吸氢放热）
    comp_kw: object = None       # 压缩机电耗序列（高压储氢路径；kW）


def run_t1(config: T1Config, ghi_wm2, load_kw, model_level: str = "L3",
           verified: str = "自证") -> T1Result:
    ghi = np.asarray(ghi_wm2, dtype=float)
    load = np.asarray(load_kw, dtype=float)
    if len(ghi) != len(load):
        raise ValueError(f"辐照({len(ghi)})与负荷({len(load)})长度不一致")
    n = len(ghi)

    pv = pv_power_simple(ghi, config.pv)
    bess = Bess(config.bess)
    pem = Pemwe(config.pemwe)
    fc = FuelCell(config.fc)
    mh_mode = config.mh_store is not None
    if mh_mode:
        store = config.mh_store              # MHStore（接口兼容 H2Store）
    else:
        store = H2Store(config.h2store_capacity_kg, config.h2store_init_kg)
    # 高压储氢路径：压缩机逐时耦合（固态 MH 低压直供不启用；V1.3 §6.1）
    comp = config.comp if (config.comp is not None and not mh_mode) else None
    pem_yield_kg_per_kwh = config.pemwe.eff_lhv / H2_LHV_KWH_PER_KG
    h2_capacity_kg = store.capacity_kg        # 罐容：MH 模式=床质量×wMax
    h2_init_level_kg = float(store.level_kg)  # 氢重审初值取实际罐（MH 初位来自材料比率）
    auditor = ConservationAuditor()

    r = T1Result()
    r.hours = np.arange(n, dtype=float)
    arrays = dict(pv_kw=pv, load_kw=load, bess_chg_kw=[], bess_dis_kw=[],
                  bess_soc=[], pem_kw=[], h2_prod_kg_per_h=[], h2_store_level_kg=[],
                  h2_cons_kg_per_h=[], fc_kw=[], curtail_kw=[], unmet_kw=[],
                  comp_kw=[], mh_t_bed_k=[], mh_q_rxn_w=[])

    for t in range(n):
        pv_t, load_t = float(pv[t]), float(load[t])
        # —— 盈余/缺口 ——
        surplus = pv_t - load_t
        bess_chg = bess_dis = pem_t = 0.0
        h2_prod = h2_cons = 0.0
        h2_demand = fc_t = 0.0
        comp_kw = 0.0
        curtail = unmet = 0.0

        if surplus > 0:
            # 1) BESS 充电
            bess_chg = bess.charge(surplus)
            rest = surplus - bess_chg
            # 2) PEM 制氢（高压路径：为压缩预留电耗——PEM+压缩机共享盈余母线）
            if rest > 0:
                pa_eff = rest
                if comp is not None:
                    # 自限：pem_used + used×yield×spec ≤ rest（守恒恒成立的闭式上界）
                    pa_eff = rest / (1.0 + comp.spec_kwh_per_kg * pem_yield_kg_per_kwh)
                pem_used, h2p = pem.step(pa_eff)
                accepted = store.charge(h2p)          # 罐满则拒收
                pem_t = pem_used * (accepted / h2p) if h2p > 0 else 0.0
                h2_prod = accepted
                if comp is not None:
                    comp_kw = accepted * comp.spec_kwh_per_kg   # kWh/kg × kg/h = kW
                # PEM 产氢被罐拒收部分视为电解降功率? —— 处理：拒收意味着电解不应按全功率运行。
                # 保守正确的做法：若罐拒绝了一部分，等效电解按接受比例降功率（可运行范围）。
                rest -= (pem_t + comp_kw)
            # 3) 弃电
            curtail = max(0.0, rest)
        else:
            deficit = -surplus
            # 1) BESS 放电
            bess_dis = bess.discharge(deficit)
            rest = deficit - bess_dis
            # 2) FC 发电（先算氢需求，罐实际放出）
            if rest > 0:
                fc_t, h2_demand = fc.step(rest)
                h2_cons = store.discharge(h2_demand)
                # 罐没给够 → FC 实际只能按给到的氢发电
                if h2_cons < h2_demand - 1e-12 and h2_demand > 0:
                    fc_t = fc_t * (h2_cons / h2_demand)
            # 3) 失电
            unmet = max(0.0, rest - fc_t)

        # —— 守恒审计（电） ——
        supply = pv_t + bess_dis + fc_t + unmet
        demand = load_t + bess_chg + pem_t + comp_kw + curtail
        auditor.step_elec(t, supply, demand)
        # 氢守恒：循环结束后用罐位序列数组统一逐步重审（见下）

        arrays["bess_chg_kw"].append(bess_chg)
        arrays["bess_dis_kw"].append(bess_dis)
        arrays["bess_soc"].append(bess.soc)
        arrays["pem_kw"].append(pem_t)
        arrays["h2_prod_kg_per_h"].append(h2_prod)
        arrays["h2_store_level_kg"].append(store.level_kg)
        arrays["h2_cons_kg_per_h"].append(h2_cons)
        arrays["fc_kw"].append(fc_t)
        arrays["curtail_kw"].append(curtail)
        arrays["unmet_kw"].append(unmet)
        arrays["comp_kw"].append(comp_kw)
        if mh_mode:
            arrays["mh_t_bed_k"].append(store.T_bed)
            arrays["mh_q_rxn_w"].append(store.q_rxn_w)

    # —— 氢守恒重审（用数组做，避免逐步状态复杂化） ——
    # produced - consumed == Δstore 逐步核对：
    levels = np.array([h2_init_level_kg] + arrays["h2_store_level_kg"])  # n+1
    prod = np.array(arrays["h2_prod_kg_per_h"])
    cons = np.array(arrays["h2_cons_kg_per_h"])
    dstore = levels[1:] - levels[:-1]
    h2_aud = ConservationAuditor()
    for t in range(n):
        h2_aud.step_h2(t, prod[t], cons[t], dstore[t])
    rep_h2 = h2_aud.finish()

    rep = auditor.finish()
    # 合并氢违例到主报告（电审计器已逐步跑过；氢用专用审计器结果）
    if not rep_h2.passed:
        rep.passed = False
    rep.h2_err_rel_annual = rep_h2.h2_err_rel_annual
    rep.violations.extend(rep_h2.violations)

    # —— KPI（先算再补能量方向审计——方向检查需要年度量） ——
    pv_arr = np.asarray(arrays["pv_kw"]); load_arr = np.asarray(arrays["load_kw"])
    unmet_arr = np.asarray(arrays["unmet_kw"]); curt_arr = np.asarray(arrays["curtail_kw"])
    fc_arr = np.asarray(arrays["fc_kw"]); bess_dis_arr = np.asarray(arrays["bess_dis_kw"])
    pem_arr = np.asarray(arrays["pem_kw"])
    comp_arr = np.asarray(arrays["comp_kw"])
    dt = 1.0
    e_pv = float(pv_arr.sum() * dt)
    e_load = float(load_arr.sum() * dt)
    e_unmet = float(unmet_arr.sum() * dt)
    e_curtail = float(curt_arr.sum() * dt)
    e_fc = float(fc_arr.sum() * dt)
    e_served = e_load - e_unmet
    h2_prod_annual = float(prod.sum() * dt)
    h2_cons_annual = float(cons.sum() * dt)
    # 电→氢→电 往返效率：仅当年内耗氢≤年制氢（未动用初始库存）才有意义，否则 NaN+说明
    e_pem = float(pem_arr.sum() * dt)
    if e_pem > 0 and h2_cons_annual <= h2_prod_annual + 1e-9:
        r2r = e_fc / e_pem
        r2r_note = ""
    else:
        r2r = float("nan")
        r2r_note = ("本年 FC 动用了初始罐存(耗氢>年制氢)，e_fc/e_pem 比值不适用;"
                    "理论往返上限 = pemwe.eff_lhv × fc.eff_lhv")

    # —— 能量方向审计（守恒查平衡，方向查物理） ——
    e_comp = float(comp_arr.sum() * dt)
    dir_violations = check_energy_directions(e_pem, h2_prod_annual, e_fc, h2_cons_annual,
                                             H2_LHV_KWH_PER_KG)
    if dir_violations:
        rep.passed = False
        rep.violations.extend(dir_violations)
    r.cons_report = rep
    reliability = (1.0 - e_unmet / e_load) if e_load > 0 else 1.0
    r.kpi = {
        "e_pv_kwh": e_pv, "e_load_kwh": e_load, "e_served_kwh": e_served,
        "e_unmet_kwh": e_unmet, "e_curtail_kwh": e_curtail, "e_fc_kwh": e_fc,
        "e_pem_kwh": e_pem, "e_comp_kwh": e_comp,
        "h2_prod_kg": h2_prod_annual, "h2_cons_kg": h2_cons_annual,
        "roundtrip_eff": r2r, "roundtrip_note": r2r_note,
        "reliability": reliability,
        "curtail_ratio": e_curtail / e_pv if e_pv > 0 else 0.0,
    }

    # —— 经济（HOMER Total NPC 口径） ——
    ec = config.econ
    items = [
        {"capex": pv_kw_capex(config, ec), "life_years": ec["econ.pv_life_years"],
         "opex_annual": ec["econ.pv_capex_per_kw"] * ec["econ.pv_opex_ratio"] * config.pv.capacity_kw},
        {"capex": ec["econ.bess_capex_per_kwh"] * config.bess.capacity_kwh,
         "life_years": ec["econ.bess_life_years"],
         "opex_annual": ec["econ.bess_capex_per_kwh"] * config.bess.capacity_kwh * ec["econ.bess_opex_ratio"]},
        {"capex": ec["econ.pemwe_capex_per_kw"] * config.pemwe.rated_kw,
         "life_years": ec["econ.pemwe_life_years"], "opex_annual": 0.0},
        {"capex": ec["econ.h2store_capex_per_kg"] * h2_capacity_kg,
         "life_years": ec["econ.h2store_life_years"], "opex_annual": 0.0},
        {"capex": ec["econ.fc_capex_per_kw"] * config.fc.rated_kw,
         "life_years": ec["econ.fc_life_years"],
         "opex_annual": ec["econ.fc_capex_per_kw"] * config.fc.rated_kw * ec["econ.fc_opex_ratio"]},
    ]
    npc_total = total_npc(items, int(ec["econ.project_years"]), ec["econ.discount_rate"])
    # LCOE/LCOH：零供给/零产氢时显式 NaN 并注明原因（铁律3：不静默返回 0，也不中断守恒流程）
    if e_served > 0:
        lcoe_val = lcoe(npc_total, e_served, ec["econ.discount_rate"], int(ec["econ.project_years"]))
        lcoe_note = ""
    else:
        lcoe_val, lcoe_note = float("nan"), "年供给电量为0(全失电或零负荷场景)"
    if h2_prod_annual > 0:
        # LCOH = 年化总成本(NPC×CRF)/年产氢——与 LCOE 同一口径（修正：此前漏乘 CRF）
        lcoh_val = (npc_total * crf(ec["econ.discount_rate"], int(ec["econ.project_years"]))
                    / h2_prod_annual)
        lcoh_note = "年化口径(NPC×CRF/年产氢)；未扣电力外售价值"
    else:
        lcoh_val, lcoh_note = float("nan"), "年制氢量为0"
    r.econ = {
        "total_npc_cny": npc_total,
        "lcoe_cny_per_kwh": lcoe_val,
        "lcoe_note": lcoe_note,
        "lcoh_cny_per_kg": lcoh_val,
        "lcoh_note": lcoh_note,
    }

    # —— 置信度（v0：切片级评估） ——
    data_level = "B"  # 切片默认参数多数 B/C1 级
    r.confidence = assess(ConfidenceInput(
        data_level=data_level, model_level=model_level,
        verified=verified, cons_passed=rep.passed))

    # —— 组装时序 ——
    r.pv_kw = pv; r.load_kw = load
    for k in ["bess_chg_kw", "bess_dis_kw", "bess_soc", "pem_kw", "h2_prod_kg_per_h",
              "h2_store_level_kg", "h2_cons_kg_per_h", "fc_kw", "curtail_kw", "unmet_kw",
              "comp_kw"]:
        setattr(r, k, np.asarray(arrays[k]))
    if mh_mode:
        r.mh_t_bed_k = np.asarray(arrays["mh_t_bed_k"])
        r.mh_q_rxn_w = np.asarray(arrays["mh_q_rxn_w"])
    return r


def pv_kw_capex(config: T1Config, ec: Dict) -> float:
    return ec["econ.pv_capex_per_kw"] * config.pv.capacity_kw
