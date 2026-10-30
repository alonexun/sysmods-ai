# -*- coding: utf-8 -*-
"""T6 绿氨模板：风光绿电 → 电解制氢 → 储氢缓冲 → ASU 制氮 → 合成氨。

中国工业降碳旗舰场景（V1.2 §1.3.2/§4.4）：
- 风光波动 → 储氢缓冲 → HB 稳定进料（最小负荷 50% + 爬坡 8%/h 慢动态）
- 电网四模式：offgrid / ppa 绿电直连 / tou 分时 / spot 现货（市场化交易）
- 经济：Total NPC − 氨收入现值 − 减碳收益现值；LCOA
- 守恒：逐步电/氢平衡 + 年度元素审计（理论计量闭合）
"""
from dataclasses import dataclass, field
from typing import Dict
import numpy as np

from ..modules.pv import PvParams, pv_power_simple
from ..modules.wind import WindParams, wind_power
from ..modules.bess import Bess, BessParams
from ..modules.pemwe import Pemwe, PemweParams
from ..modules.h2store import H2Store
from ..modules.grid import Grid, GridParams
from ..modules.chemical import HaberBosch, HaberBoschParams, ASU, ASUParams
from ..modules.electrolyzers import (Electrolyzer, ElectrolyzerParams,
                                     ElectrolyzerFleet)
from ..modules.phys import H2_LHV_KWH_PER_KG
from ..audit.guard import ConservationAuditor, check_energy_directions
from ..uq.confidence import assess, ConfidenceInput
from ..econ.npc import total_npc, crf
from ..registry import load_registry


@dataclass
class T6Config:
    pv: PvParams
    wind: WindParams
    bess: BessParams
    pemwe: PemweParams
    hb: HaberBoschParams
    asu: ASUParams
    grid: GridParams
    h2store_capacity_kg: float
    h2store_init_kg: float
    mh_store: object = None          # 可选：PMHT 固态储氢（接口兼容）
    electrolyzer_fleet: object = None  # 可选：多路线并联 Fleet（None 时仅 PEM）
    econ: Dict = field(default_factory=dict)


@dataclass
class T6Result:
    kpi: Dict = field(default_factory=dict)
    cons_report: object = None
    element_audit_annual: Dict = field(default_factory=dict)
    confidence: object = None
    econ: Dict = field(default_factory=dict)
    series: Dict = field(default_factory=dict)   # 关键时序（pv/wind/load_pem/h2_level/nh3_rate/import_kw）


def build_t6_config(overrides: dict = None) -> T6Config:
    reg = load_registry()
    d = dict(reg.defaults())
    grid_mode = "offgrid"
    if overrides:
        for k, v in overrides.items():
            if k == "grid.mode_str":
                grid_mode = str(v).lower()      # 字符串模式键：不入数值注册表
                continue
            reg.validate(k, v)
            d[k] = float(v)
    gp = GridParams(
        mode=grid_mode,
        max_import_kw=d["grid.max_import_kw"],
        ppa_price_cny_kwh=d["grid.ppa_price_cny_kwh"],
        buy_peak_cny_kwh=d["grid.buy_peak_cny_kwh"],
        buy_flat_cny_kwh=d["grid.buy_flat_cny_kwh"],
        buy_valley_cny_kwh=d["grid.buy_valley_cny_kwh"],
        sell_price_cny_kwh=d["grid.sell_price_cny_kwh"],
    )
    econ_keys = [k for k in d if k.startswith("econ.")]
    # 多路线并联 Fleet：pemwe 恒在；alk/aem/soec 额定>0 即加入（0=不启用）
    fleet_units = [Electrolyzer(ElectrolyzerParams(
        "pem", d["pemwe.rated_kw"], eff_lhv=d["pemwe.eff_lhv"],
        min_load_ratio=d["pemwe.min_load_ratio"]))]
    for tech in ("alk", "aem", "soec"):
        if d[f"{tech}.rated_kw"] > 0:
            kw = dict(tech=tech, rated_kw=d[f"{tech}.rated_kw"],
                      eff_lhv=d[f"{tech}.eff_lhv"],
                      min_load_ratio=d[f"{tech}.min_load_ratio"])
            if tech == "soec":
                kw["heat_available"] = d["soec.heat_available"] > 0.5
                kw["eff_lhv_no_heat"] = d["soec.eff_lhv_no_heat"]
            fleet_units.append(Electrolyzer(ElectrolyzerParams(**kw)))
    fleet = ElectrolyzerFleet(fleet_units) if len(fleet_units) > 1 else None
    return T6Config(
        pv=PvParams(d["pv.capacity_kw"], d["pv.derate"]),
        wind=WindParams(d["wind.capacity_kw"], d["wind.cut_in_ms"],
                        d["wind.rated_ms"], d["wind.cut_out_ms"]),
        bess=BessParams(d["bess.capacity_kwh"], d["bess.power_kw"],
                        d["bess.eff_roundtrip"], d["bess.soc_min"],
                        d["bess.soc_max"], d["bess.soc_init"]),
        pemwe=PemweParams(d["pemwe.rated_kw"], d["pemwe.eff_lhv"], d["pemwe.min_load_ratio"]),
        hb=HaberBoschParams(d["chem.nh3.capacity_t_per_h"], d["chem.nh3.h2_per_t_kg"],
                            lec_mwh_per_t=d["chem.nh3.lec_mwh_per_t"],
                            min_load=d["chem.nh3.min_load"],
                            ramp_per_h=d["chem.nh3.ramp_per_h"]),
        asu=ASUParams(d["chem.asu.lec_kwh_per_kg_n2"]),
        grid=gp,
        h2store_capacity_kg=d["h2store.capacity_kg"],
        h2store_init_kg=d["h2store.level_init_kg"],
        electrolyzer_fleet=fleet,
        econ={k: d[k] for k in econ_keys},
    )


def run_t6(config: T6Config, ghi_wm2, wind_ms, model_level: str = "L3",
           verified: str = "自证") -> T6Result:
    ghi = np.asarray(ghi_wm2, dtype=float)
    ws = np.asarray(wind_ms, dtype=float)
    if not (len(ghi) == len(ws)):
        raise ValueError("辐照与风速长度不一致")
    n = len(ghi)

    pv = pv_power_simple(ghi, config.pv)
    wp = wind_power(ws, config.wind)
    renew = pv + wp
    bess = Bess(config.bess)
    pem = Pemwe(config.pemwe)
    # 多路线并联：fleet 存在时替代单 PEM（效率优先分配+各自爬坡/min门）
    fleet = config.electrolyzer_fleet
    hb = HaberBosch(config.hb)
    asu = ASU(config.asu)
    grid = Grid(config.grid)
    store = config.mh_store if config.mh_store is not None else \
        H2Store(config.h2store_capacity_kg, config.h2store_init_kg)
    h2_init_level_kg = float(store.level_kg)
    auditor = ConservationAuditor()

    arrays = dict(pv_kw=[], wind_kw=[], bess_soc=[], pem_kw=[],
                  h2_prod_kg_per_h=[],
                  h2_store_level_kg=[], nh3_t_per_h=[], import_kw=[],
                  export_kw=[], unmet_kw=[], hb_h2_avail=[])

    for t in range(n):
        gen = float(renew[t])
        # —— HB 按罐可放氢运行（慢动态：min负荷+爬坡；放多的氢回罐保守恒） ——
        want_h2 = config.hb.rated_t_per_h * config.hb.h2_per_t_kg
        h2_avail = store.discharge(want_h2)
        n2_avail = h2_avail / config.hb.h2_per_t_kg * config.hb.n2_per_t_kg
        nh3 = hb.step(h2_avail, n2_avail)
        give_back = max(0.0, h2_avail - nh3["h2_used_kg"])   # HB 未能消化的氢回罐
        if give_back > 0:
            store.charge(give_back)   # 罐刚腾出空间，回充必收——氢守恒闭合
        asu_out = asu.make_n2(nh3["n2_used_kg"])
        load_t = nh3["elec_mwh"] * 1000.0 + asu_out["elec_mwh"] * 1000.0

        # —— 电平衡 ——
        surplus = gen - load_t
        bess_chg = bess_dis = grid_imp = grid_exp = pem_t = 0.0
        unmet = curtail = 0.0
        if surplus > 0:
            bess_chg = bess.charge(surplus)
            rest = surplus - bess_chg
            if fleet is not None:
                fleet_used, h2p, _per_unit = fleet.step(rest)
            else:
                pem_used, h2p = pem.step(rest)
                fleet_used = pem_used
            accepted = store.charge(h2p)
            pem_t = fleet_used * (accepted / h2p) if h2p > 0 else 0.0
            h2_acc_this_step = accepted
            rest -= pem_t
            grid_exp = grid.export_power(rest, t)
            curtail = rest - grid_exp
        else:
            deficit = -surplus
            bess_dis = bess.discharge(deficit)
            rest = deficit - bess_dis
            grid_imp = grid.import_power(rest, t)
            unmet = rest - grid_imp
            h2_acc_this_step = 0.0

        supply = gen + bess_dis + grid_imp + unmet
        demand = load_t + bess_chg + pem_t + grid_exp + curtail
        auditor.step_elec(t, supply, demand)

        # 实际入罐产氢（罐拒收的溢出不计入产氢账——与电侧 pem_t 同比例缩放）
        arrays["h2_prod_kg_per_h"].append(h2_acc_this_step)
        arrays["bess_soc"].append(bess.soc)

        arrays["pv_kw"].append(float(pv[t]))
        arrays["wind_kw"].append(float(wp[t]))
        arrays["bess_soc"].append(bess.soc)
        arrays["pem_kw"].append(pem_t)
        arrays["h2_store_level_kg"].append(store.level_kg)
        arrays["nh3_t_per_h"].append(nh3["nh3_t"])
        arrays["import_kw"].append(grid_imp)
        arrays["export_kw"].append(grid_exp)
        arrays["unmet_kw"].append(unmet)

    # —— 氢守恒重审（逐步真值：h2_prod_kg_per_h = 实际入罐产氢） ——
    levels = np.array([h2_init_level_kg] + arrays["h2_store_level_kg"])
    pem_arr = np.asarray(arrays["pem_kw"])
    prod = np.asarray(arrays["h2_prod_kg_per_h"])   # 逐步入罐产氢（守恒账）
    if fleet is not None:
        # 分技术产量：fleet 累计为总产氢（含罐拒收溢出），按入罐比例缩放闭合总账
        fleet_total = sum(fleet.annual_h2_kg.values())
        prod_total = float(prod.sum())
        scale = (prod_total / fleet_total) if fleet_total > 0 else 0.0
        h2_by_tech = {k: v * scale for k, v in fleet.annual_h2_kg.items()}
    else:
        h2_by_tech = {"pem": float(prod.sum())}
    h2_to_hb = np.asarray(arrays["nh3_t_per_h"]) * config.hb.h2_per_t_kg
    dstore = levels[1:] - levels[:-1]
    h2_aud = ConservationAuditor()
    for t in range(n):
        h2_aud.step_h2(t, prod[t], h2_to_hb[t], dstore[t])
    rep_h2 = h2_aud.finish()
    rep = auditor.finish()
    if not rep_h2.passed:
        rep.passed = False
    rep.h2_err_rel_annual = rep_h2.h2_err_rel_annual
    rep.violations.extend(rep_h2.violations)

    # —— 年度汇总 ——
    nh3_annual = float(np.sum(arrays["nh3_t_per_h"]))
    h2_prod_annual = float(np.sum(prod))
    e_pem = float(np.sum(pem_arr))
    h2_to_hb_annual = float(np.sum(h2_to_hb))
    import_kwh = float(np.sum(arrays["import_kw"]))
    export_kwh = float(np.sum(arrays["export_kw"]))
    renew_kwh = float(np.sum(pv) + np.sum(wp))
    unmet_kwh = float(np.sum(arrays["unmet_kw"]))
    grid_cost = grid.net_cost_cny

    # 能量方向审计（电解/全链）
    dir_v = check_energy_directions(e_pem, h2_prod_annual, 0.0, h2_to_hb_annual * 0.0)
    if dir_v:
        rep.passed = False
        rep.violations.extend(dir_v)

    # —— 元素审计（年度，理论计量闭合） ——
    n2_used_annual = nh3_annual * config.hb.n2_per_t_kg
    elem = hb.element_audit(nh3_annual, h2_to_hb_annual, n2_used_annual)

    # —— 经济：NPC − 收益现值 ——
    ec = config.econ
    years = int(ec["econ.project_years"])
    r = ec["econ.discount_rate"]
    ann_f = sum(1.0 / (1 + r) ** t for t in range(1, years + 1))
    items = [
        {"capex": ec["econ.pv_capex_per_kw"] * config.pv.capacity_kw,
         "life_years": ec["econ.pv_life_years"],
         "opex_annual": ec["econ.pv_capex_per_kw"] * config.pv.capacity_kw * ec["econ.pv_opex_ratio"]},
        # 风电专用经济参数（修正：此前借用光伏造价/寿命/费率）
        {"capex": ec["econ.wind_capex_per_kw"] * config.wind.capacity_kw,
         "life_years": ec["econ.wind_life_years"],
         "opex_annual": ec["econ.wind_capex_per_kw"] * config.wind.capacity_kw * ec["econ.wind_opex_ratio"]},
        {"capex": ec["econ.bess_capex_per_kwh"] * config.bess.capacity_kwh,
         "life_years": ec["econ.bess_life_years"],
         "opex_annual": ec["econ.bess_capex_per_kwh"] * config.bess.capacity_kwh * ec["econ.bess_opex_ratio"]},
        {"capex": ec["econ.pemwe_capex_per_kw"] * config.pemwe.rated_kw,
         "life_years": ec["econ.pemwe_life_years"],
         "opex_annual": ec["econ.pemwe_capex_per_kw"] * config.pemwe.rated_kw * 0.02},
    ]
    capex_items = [
        {"label": "光伏阵列", "capex": items[0]["capex"],
         "life_years": items[0]["life_years"], "opex_annual": items[0]["opex_annual"]},
        {"label": "风电机组", "capex": items[1]["capex"],
         "life_years": items[1]["life_years"], "opex_annual": items[1]["opex_annual"]},
        {"label": "锂电池储能", "capex": items[2]["capex"],
         "life_years": items[2]["life_years"], "opex_annual": items[2]["opex_annual"]},
        {"label": "PEM 电解槽", "capex": items[3]["capex"],
         "life_years": items[3]["life_years"], "opex_annual": items[3]["opex_annual"]},
    ]
    # 多电解路线并联投资（各技术独立 capex/寿命；fleet 里除 pem 外的机组）
    if fleet is not None:
        for u in fleet.units:
            if u.tech == "pem":
                continue
            items.append({
                "capex": ec[f"econ.{u.tech}_capex_per_kw"] * u.p.rated_kw,
                "life_years": ec[f"econ.{u.tech}_life_years"],
                "opex_annual": ec[f"econ.{u.tech}_capex_per_kw"] * u.p.rated_kw * 0.02})
            capex_items.append({
                "label": f"{u.tech.upper()} 电解槽", "capex": items[-1]["capex"],
                "life_years": items[-1]["life_years"],
                "opex_annual": items[-1]["opex_annual"]})
    items += [
        {"capex": ec["econ.h2store_capex_per_kg"] * (config.mh_store.capacity_kg if config.mh_store is not None else config.h2store_capacity_kg),
         "life_years": ec["econ.h2store_life_years"], "opex_annual": 0.0},
        # 合成氨装置（含 ASU+合成回路+公辅）——单位投资 CNY/(t/h)
        {"capex": ec["econ.nh3_capex_cny_per_t_per_h"] * config.hb.rated_t_per_h,
         "life_years": ec["econ.nh3_life_years"],
         "opex_annual": ec["econ.nh3_capex_cny_per_t_per_h"] * config.hb.rated_t_per_h * ec["econ.nh3_opex_ratio"]},
    ]
    capex_items += [
        {"label": "储氢设施", "capex": items[-2]["capex"],
         "life_years": items[-2]["life_years"], "opex_annual": 0.0},
        {"label": "合成氨装置(含ASU)", "capex": items[-1]["capex"],
         "life_years": items[-1]["life_years"], "opex_annual": items[-1]["opex_annual"]},
    ]
    npc = total_npc(items, years, r)
    # 运行期电费/电收入
    npc += grid_cost * ann_f
    # 收益：氨 + 减碳（绿氨 vs 灰氨：灰氨碳强度按吨氨含氢 177.5kg×grey_h2_co2）
    nh3_rev_pv = nh3_annual * ec["econ.nh3_price_cny_per_t"] * ann_f
    grey_co2_per_nh3 = 177.5 * ec["econ.grey_h2_co2_t_per_t"] / 1000.0   # t CO2/t NH3
    carbon_rev_pv = nh3_annual * grey_co2_per_nh3 * ec["econ.co2_price_cny_per_t"] * ann_f
    lcoa = npc * crf(r, years) / nh3_annual if nh3_annual > 0 else float("nan")
    econ_out = {
        "npc_gross_cny": npc, "nh3_revenue_pv_cny": nh3_rev_pv,
        "carbon_revenue_pv_cny": carbon_rev_pv,
        "npc_net_cny": npc - nh3_rev_pv - carbon_rev_pv,
        "lcoa_cny_per_t": lcoa,
        "grey_nh3_co2_t_per_t": grey_co2_per_nh3,
        "co2_abatement_t_per_year": nh3_annual * grey_co2_per_nh3,
        "capex_items": capex_items,       # 组件级投资明细（报告成本表）
        "grid_net_cost_cny_per_year": grid_cost,
        "project_years": years, "discount_rate": r,
    }

    result = T6Result()
    result.cons_report = rep
    result.element_audit_annual = elem
    result.econ = econ_out
    result.kpi = {
        "nh3_annual_t": nh3_annual, "h2_prod_annual_kg": h2_prod_annual,
        "h2_to_hb_annual_kg": h2_to_hb_annual,
        "h2_by_tech_kg": h2_by_tech,
        "e_renew_kwh": renew_kwh, "e_pem_kwh": e_pem,
        "grid_import_kwh": import_kwh, "grid_export_kwh": export_kwh,
        "unmet_kwh": unmet_kwh,
        "hb_capacity_factor": nh3_annual / (config.hb.rated_t_per_h * n) if n > 0 else 0.0,
        "renew_share": 1.0 - import_kwh / (renew_kwh + import_kwh) if (renew_kwh + import_kwh) > 0 else 1.0,
        "h2_buffer_util_kg": float(np.ptp(levels)),
    }
    result.confidence = assess(ConfidenceInput(
        data_level="B", model_level=model_level, verified=verified,
        cons_passed=rep.passed))
    result.series = {k: np.asarray(v) for k, v in arrays.items()}
    return result


def run_t6_scenario(overrides: dict = None, n_days: int = 365,
                    mh_material: str = None):
    """一键绿氨端到端。mh_material 提供时用 PMHT 固态储氢。"""
    cfg = build_t6_config(overrides)
    reg = load_registry()
    d = dict(reg.defaults())
    if overrides:
        for k, v in overrides.items():
            if k == "grid.mode_str":
                continue
            reg.validate(k, v)
            d[k] = float(v)
    if mh_material:
        from ..modules.mh import load_hydride
        from ..modules.mh.store import MHStore
        hyd = load_hydride(mh_material)
        cfg.mh_store = MHStore(hyd, mass_kg=d["mh.bed_mass_kg"],
                               t_init_k=d["mh.t_ambient_k"],
                               t_ambient_k=d["mh.t_ambient_k"],
                               uth_w_per_k=d["mh.uth_w_per_k"],
                               p_supply_pa=d["mh.p_supply_pa"],
                               p_bus_pa=d["mh.p_bus_pa"],
                               w_init_ratio=d["h2store.level_init_kg"] / d["h2store.capacity_kg"]
                               if d["h2store.capacity_kg"] > 0 else 0.5)
    from .t1_offgrid import synth_ghi
    from ..modules.wind import synth_wind
    hours = n_days * 24
    ghi = synth_ghi(n_days=n_days, lat_deg=d["site.latitude_deg"])
    ws = synth_wind(hours)
    return run_t6(cfg, ghi, ws)
