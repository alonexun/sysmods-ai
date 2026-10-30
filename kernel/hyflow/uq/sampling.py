# -*- coding: utf-8 -*-
"""UQ 采样引擎：OAT 敏感性（龙卷风）+ LHS 分布（P50/P90）。

V1.2 §5.2 三层采样的前两层（Sobol 为远期）。
- OAT：单参数 ±delta（默认 15%），对基准值扰动 → ΔKPI 绝对/相对敏感度
- LHS：拉丁超立方（numpy rank 实现），输出 KPI 分布（P50/P90/P10）
- 参数选择默认自动：注册表 level 以 C 开头（先验）的标量参数——A级不扰动
"""
from typing import Callable, Dict, List
import numpy as np

from ..registry import load_registry


class UQError(ValueError):
    pass


def _candidate_params(registry=None, only_levels=("C",), exclude=("grid", "econ")) -> List[str]:
    reg = registry or load_registry()
    out = []
    for name, spec in reg.specs.items():
        lv = spec.level.upper()
        if not lv.startswith(only_levels):
            continue
        if any(name.startswith(p + ".") for p in exclude):
            continue
        out.append(name)
    return sorted(out)


def run_oat(sim_fn: Callable[[Dict[str, float]], Dict[str, float]],
            base_params: Dict[str, float],
            kpis: List[str],
            delta: float = 0.15,
            params: List[str] = None,
            registry=None) -> Dict[str, Dict[str, Dict[str, float]]]:
    """OAT 敏感性：每个参数 ±delta（值域裁剪）。

    返回 {param: {'minus': {kpi: v}, 'base': {...}, 'plus': {...},
                  'sensitivity': {kpi: abs(Δ+) + abs(Δ-)}}}（按 max 敏感度排序可由调用方做）。
    """
    if params is None:
        params = _candidate_params(registry)
    if not (0.0 < delta < 1.0):
        raise UQError("delta 应在 (0,1)")
    base_out = sim_fn(dict(base_params))
    reg = registry or load_registry()     # 缓存：不再逐参数重载注册表
    result = {}
    for p in params:
        if p not in base_params:
            continue
        v0 = float(base_params[p])
        lo = v0 * (1 - delta)
        hi = v0 * (1 + delta)
        spec = reg.spec(p)
        lo = max(lo, spec.range[0])
        hi = min(hi, spec.range[1])
        out_lo = sim_fn({**base_params, p: lo})
        out_hi = sim_fn({**base_params, p: hi})
        sens = {}
        for k in kpis:
            b = base_out.get(k)
            if b is None or (isinstance(b, float) and not np.isfinite(b)):
                continue
            d1 = out_lo.get(k, b) - b
            d2 = out_hi.get(k, b) - b
            sens[k] = abs(d1) + abs(d2)
        result[p] = {"minus": {k: out_lo.get(k) for k in kpis},
                     "base": {k: base_out.get(k) for k in kpis},
                     "plus": {k: out_hi.get(k) for k in kpis},
                     "sensitivity": sens,
                     "delta": delta, "v0": v0}
    return result


def tornado(oat_result: Dict, kpi: str) -> List[Dict[str, float]]:
    """龙卷风排序：按指定 KPI 的敏感度降序。"""
    rows = []
    for p, d in oat_result.items():
        s = d["sensitivity"].get(kpi)
        if s is None:
            continue
        rows.append({"param": p, "sensitivity": s,
                     "low": d["minus"].get(kpi), "base": d["base"].get(kpi),
                     "high": d["plus"].get(kpi)})
    rows.sort(key=lambda r: -r["sensitivity"])
    return rows


def latin_hypercube(n_samples: int, n_dims: int, seed: int = 42) -> np.ndarray:
    """标准 LHS（rank 法）：[0,1]^d 均匀分层。"""
    if n_samples < 2 or n_dims < 1:
        raise UQError("样本/维度过小")
    rng = np.random.default_rng(seed)
    u = np.zeros((n_samples, n_dims))
    for j in range(n_dims):
        perm = rng.permutation(n_samples)
        strat = (perm + rng.random(n_samples)) / n_samples
        u[:, j] = strat
    return u


def run_lhs(sim_fn: Callable[[Dict[str, float]], Dict[str, float]],
            base_params: Dict[str, float],
            kpis: List[str],
            n_samples: int = 200,
            params: List[str] = None,
            spread: float = 0.15,
            registry=None,
            seed: int = 42) -> Dict:
    """LHS 分布：每个候选参数 ±spread 均匀扰动 → KPI 分布统计。

    返回 {'stats': {kpi: {p10,p50,p90,mean,std}}, 'samples': {kpi: [...]}, 'n': N, 'failed': M}
    """
    if params is None:
        params = _candidate_params(registry)
    params = [p for p in params if p in base_params]
    if not params:
        raise UQError("无候选扰动参数")
    u = latin_hypercube(n_samples, len(params), seed)
    reg = registry or load_registry()
    rows: List[Dict[str, float]] = []
    failed = 0
    for i in range(n_samples):
        ov = dict(base_params)
        for j, p in enumerate(params):
            v0 = float(base_params[p])
            lo = max(v0 * (1 - spread), reg.spec(p).range[0])
            hi = min(v0 * (1 + spread), reg.spec(p).range[1])
            ov[p] = lo + u[i, j] * (hi - lo)
        try:
            rows.append(sim_fn(ov))
        except Exception:
            failed += 1   # 物理不可行样本：计入统计不中断（V1.2 §3.2 fail 二分）
    if not rows:
        raise UQError("全部样本失败——检查基准配置")
    stats = {}
    samples = {}
    for k in kpis:
        vals = np.array([r[k] for r in rows if r.get(k) is not None
                         and np.isfinite(r[k])], dtype=float)
        if len(vals) == 0:
            stats[k] = None
            continue
        samples[k] = vals
        stats[k] = {"p10": float(np.percentile(vals, 10)),
                    "p50": float(np.percentile(vals, 50)),
                    "p90": float(np.percentile(vals, 90)),
                    "mean": float(vals.mean()), "std": float(vals.std()),
                    "n": int(len(vals))}
    return {"stats": stats, "samples": samples, "n": n_samples,
            "failed": failed, "params": params, "spread": spread}
