# -*- coding: utf-8 -*-
"""T1 离网光储氢电模板：合成数据 + canonical 注册表构建。

合成辐照：正弦日循环（含日出日落窗口），年幅值带季节因子；
哨站负荷：昼/夜两级恒功率。
合成数据仅用于引擎/守恒/结构的确定性测试——真实气象走 pvlib/NASA 管线（Phase 1）。
"""
import numpy as np

from ..registry import load_registry
from ..modules.pv import PvParams
from ..modules.bess import BessParams
from ..modules.pemwe import PemweParams
from ..modules.fuelcell import FcParams
from ..engine import T1Config


def synth_ghi(n_days: int = 365, peak_wm2: float = 800.0, lat_deg: float = 29.65) -> np.ndarray:
    """确定性合成 GHI：日正弦 + 季节因子。负值截 0（合成器保证非负——与真实数据清洗区分，
    真实数据负值由 pv.validate_ghi 拦截）。"""
    hours = np.arange(n_days * 24, dtype=float)
    hod = hours % 24.0
    doy = hours // 24.0
    # 日内：6-18 时余弦
    day_shape = np.clip(np.sin(np.pi * (hod - 6.0) / 12.0), 0.0, None)
    day_shape[(hod < 6.0) | (hod > 18.0)] = 0.0
    # 季节：纬度正弦（简化，冬至最弱）
    season = 0.75 + 0.25 * np.sin(2 * np.pi * (doy - 80.0) / 365.0)
    return peak_wm2 * day_shape * season


def synth_load(n_days: int = 365, avg_kw: float = 5.0, night_ratio: float = 0.8) -> np.ndarray:
    hours = np.arange(n_days * 24, dtype=float)
    hod = hours % 24.0
    day = avg_kw * 1.2          # 白天平均抬到 1.2x 使总平均≈avg
    night = avg_kw * night_ratio * (2.0 - night_ratio)
    day_mask = (hod >= 6.0) & (hod < 18.0)
    load = np.where(day_mask, day, night)
    return load


def build_t1_config(overrides: dict = None) -> T1Config:
    """从 canonical 注册表构建 T1 配置；overrides 显式覆盖（铁律2：键必须在注册表）。"""
    reg = load_registry()
    d = reg.defaults()
    if overrides:
        for k, v in overrides.items():
            reg.validate(k, v)
            d[k] = float(v)
    # 显式断言所需键齐全（缺参 fail，不静默）
    required = ["pv.capacity_kw", "pv.derate", "bess.capacity_kwh", "bess.power_kw",
                "bess.eff_roundtrip", "bess.soc_min", "bess.soc_max", "bess.soc_init",
                "pemwe.rated_kw", "pemwe.eff_lhv", "pemwe.min_load_ratio",
                "h2store.capacity_kg", "h2store.level_init_kg",
                "fc.rated_kw", "fc.eff_lhv",
                "load.avg_kw", "load.night_ratio", "site.latitude_deg"]
    for k in required:
        if k not in d:
            raise KeyError(f"注册表缺少必填参数 {k}")
    econ_keys = [k for k in d if k.startswith("econ.")]
    cfg = T1Config(
        pv=PvParams(capacity_kw=d["pv.capacity_kw"], derate=d["pv.derate"]),
        bess=BessParams(capacity_kwh=d["bess.capacity_kwh"], power_kw=d["bess.power_kw"],
                        eff_roundtrip=d["bess.eff_roundtrip"], soc_min=d["bess.soc_min"],
                        soc_max=d["bess.soc_max"], soc_init=d["bess.soc_init"]),
        pemwe=PemweParams(rated_kw=d["pemwe.rated_kw"], eff_lhv=d["pemwe.eff_lhv"],
                          min_load_ratio=d["pemwe.min_load_ratio"]),
        fc=FcParams(rated_kw=d["fc.rated_kw"], eff_lhv=d["fc.eff_lhv"]),
        h2store_capacity_kg=d["h2store.capacity_kg"],
        h2store_init_kg=d["h2store.level_init_kg"],
        econ={k: d[k] for k in econ_keys},
    )
    return cfg


def run_t1_scenario(overrides: dict = None, n_days: int = 365,
                    storage: str = "linear",
                    mh_material: str = "Ti[0.95]Zr[0.05]Mn[1.55]V[0.45]Fe[0.09]"):
    """一键端到端：注册表→配置→合成数据→仿真。
    storage='mh' 时用 PMHT 固态储氢（Peq 门控+床温演化+热账）。"""
    reg = load_registry()
    d = dict(reg.defaults())
    if overrides:
        for k, v in overrides.items():
            reg.validate(k, v)
            d[k] = float(v)
    cfg = build_t1_config(overrides)
    if storage == "mh":
        from ..modules.mh import load_hydride
        from ..modules.mh.store import MHStore
        hyd = load_hydride(mh_material)
        init_ratio = d["h2store.level_init_kg"] / cfg.h2store_capacity_kg \
            if cfg.h2store_capacity_kg > 0 else 0.5
        cfg.mh_store = MHStore(
            hydride=hyd, mass_kg=d["mh.bed_mass_kg"],
            t_init_k=d["mh.t_ambient_k"], t_ambient_k=d["mh.t_ambient_k"],
            uth_w_per_k=d["mh.uth_w_per_k"], p_supply_pa=d["mh.p_supply_pa"],
            p_bus_pa=d["mh.p_bus_pa"], w_init_ratio=max(0.0, min(1.0, init_ratio)))
    elif storage == "linear":
        # 高压储氢路径：压缩机逐时耦合（V1.3 §6.1）；固态/液氢路径不启用
        from ..modules.compressor import Compressor, CompressorParams
        cfg.comp = Compressor(CompressorParams(
            p_in_bar=d["comp.p_in_bar"], p_out_bar=d["comp.p_out_bar"],
            eta_iso=d["comp.eta_iso"]))
    ghi = synth_ghi(n_days=n_days, lat_deg=d["site.latitude_deg"])
    load = synth_load(n_days=n_days, avg_kw=d["load.avg_kw"],
                      night_ratio=d["load.night_ratio"])
    from ..engine import run_t1
    return run_t1(cfg, ghi, load)
