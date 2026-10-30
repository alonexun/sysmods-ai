# -*- coding: utf-8 -*-
"""PV 光伏模块。

模型分层（置信度引擎的输入）：
- MODEL_SIMPLE(L3): P = GHI/1000 × capacity_kw × derate —— Phase 0 切片默认
- MODEL_PVLIB(L1): pvlib ModelChain（权威库调用，Phase 1 接入精算）

铁律3：辐照为负（缺测-999等）直接抛异常，绝不静默置零（旧内核 B9 教训）。
"""
from dataclasses import dataclass
import numpy as np

MODEL_SIMPLE = "L3_simple"
MODEL_PVLIB = "L1_pvlib"


@dataclass
class PvParams:
    capacity_kw: float   # STC 峰值
    derate: float        # 系统综合折损 0.5-1.0


class PvError(ValueError):
    pass


def validate_ghi(ghi_wm2):
    arr = np.asarray(ghi_wm2, dtype=float)
    bad = arr < 0
    if bad.any():
        i = int(np.argmax(bad))  # 第一个 True
        raise PvError(
            f"辐照数据含负值 ghi[{i}]={arr[i]:.2f} W/m2 —— 疑似缺测占位值(-999 类)。"
            "铁律3：禁止静默置零，请在上游清洗并留痕（旧内核 B9 教训）"
        )
    return arr


def pv_power_simple(ghi_wm2, params: PvParams):
    """L3 简化模型。输入 W/m2，输出 kW（逐时数组或标量）。"""
    ghi = validate_ghi(ghi_wm2)
    if not (0.5 <= params.derate <= 1.0):
        raise PvError(f"pv.derate={params.derate} 越界 [0.5,1.0]")
    if params.capacity_kw <= 0:
        raise PvError(f"pv.capacity_kw={params.capacity_kw} 必须为正")
    return ghi / 1000.0 * params.capacity_kw * params.derate


def pv_power_pvlib(times, ghi_wm2, temp_air_c, capacity_kw, latitude_deg, derate,
                   surface_tilt=30.0, surface_azimuth=180.0):
    """L1 权威库模式（pvlib ModelChain）。供精算层与调用正确性测试。

    返回逐时交流出力 kW。调用方负责气象数据质量。
    """
    try:
        import pvlib
    except ImportError as e:  # pragma: no cover
        raise PvError("pvlib 未安装（requirements 可选项）：精算模式不可用") from e
    import pandas as pd

    idx = pd.DatetimeIndex(times)
    ghi = validate_ghi(ghi_wm2)
    weather = pd.DataFrame({"ghi": ghi, "dni": np.nan, "dhi": np.nan,
                            "temp_air": np.asarray(temp_air_c, dtype=float),
                            "wind_speed": 0.0}, index=idx)
    # Erbs 分解（权威库内置模型）
    solarpos = pvlib.solarposition.get_solarposition(idx, latitude_deg, 92.0)
    cs = pvlib.irradiance.erbs(ghi, solarpos["apparent_zenith"], idx)
    weather["dni"] = cs["dni"].values
    weather["dhi"] = cs["dhi"].values
    loc = pvlib.location.Location(latitude_deg, 92.0)
    # PVWatts 模型链（NREL 口径，与本模块 derate 概念同源；不依赖 SAM 数据库列名）
    module_params = {"pdc0": capacity_kw * 1000.0, "gamma_pdc": -0.004}
    inverter_params = {"pdc0": capacity_kw * 1000.0}
    sys_arr = pvlib.pvsystem.Array(
        mount=pvlib.pvsystem.FixedMount(surface_tilt=surface_tilt,
                                        surface_azimuth=surface_azimuth),
        albedo=0.2,
        module_parameters=module_params,
        temperature_model_parameters=pvlib.temperature.TEMPERATURE_MODEL_PARAMETERS[
            "sapm"]["open_rack_glass_glass"],
    )
    system = pvlib.pvsystem.PVSystem(arrays=[sys_arr],
                                      inverter_parameters=inverter_params)
    mc = pvlib.modelchain.ModelChain.with_pvwatts(system, location=loc,
                                                 aoi_model="no_loss",
                                                 spectral_model="no_loss")
    mc.run_model(weather)
    ac = mc.results.ac.astype(float).fillna(0.0).clip(lower=0.0)
    # PVWatts 模式下 pdc0 已按目标容量设定(W)，输出(W)→kW 并乘 derate
    return np.asarray(ac * derate / 1000.0, dtype=float)  # kW
