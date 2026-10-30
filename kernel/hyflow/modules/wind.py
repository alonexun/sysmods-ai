# -*- coding: utf-8 -*-
"""风机模块：分段线性功率曲线（规划级 L3；windpowerlib 为 L1 精算后续接入）。"""
from dataclasses import dataclass
import numpy as np


@dataclass
class WindParams:
    capacity_kw: float
    cut_in_ms: float = 3.0
    rated_ms: float = 11.0
    cut_out_ms: float = 25.0


class WindError(ValueError):
    pass


def wind_power(ws_ms, params: WindParams):
    """风速 m/s → 功率 kW（逐时数组）。分段线性：cut-in~rated 线性升，rated~cut-out 恒定，cut-out 停机。"""
    if params.capacity_kw <= 0:
        raise WindError("capacity_kw 必须为正")
    ws = np.asarray(ws_ms, dtype=float)
    bad = ws < 0
    if bad.any():
        i = int(np.argmax(bad))
        raise WindError(f"风速含负值 ws[{i}]={ws[i]}（缺测数据须上游清洗，铁律3）")
    out = np.where(
        (ws < params.cut_in_ms) | (ws > params.cut_out_ms), 0.0,
        np.where(ws <= params.rated_ms,
                 params.capacity_kw * (ws - params.cut_in_ms) / (params.rated_ms - params.cut_in_ms),
                 params.capacity_kw))
    return np.asarray(out, dtype=float)


def synth_wind(n_hours: int, mean_ms: float = 7.0, scale_ms: float = 3.0,
               seed: int = 42) -> np.ndarray:
    """确定性合成风速（Weibull 近似：clip 正态 + 日变化），仅测试/演示用。"""
    rng = np.random.default_rng(seed)
    hod = np.arange(n_hours) % 24.0
    diurnal = 1.0 + 0.25 * np.sin(2 * np.pi * (hod - 15.0) / 24.0)
    ws = rng.normal(mean_ms * diurnal, scale_ms, n_hours)
    return np.clip(ws, 0.0, 30.0)
