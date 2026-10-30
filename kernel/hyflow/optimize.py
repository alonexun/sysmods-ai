# -*- coding: utf-8 -*-
"""容量配置优化器：穷举 + 可行性过滤 + Total NPC 排序（HOMER 公开口径，V1.2 §4.6）。

方法（Lambert 2005 公开论文所述 HOMER 方法）：
  离散候选容量组合枚举 → 每组合仿真 → 保供率硬约束过滤 → NPC 升序排序 → top-N。
不使用求解器——分布式场景组合数有限（设计上保证 < opt.max_combinations）。

降维策略（算力预算）：
- 粗筛阶段用短周期（默认 30 天代表季度）跑全部组合；
- 对 top-N 再用长周期（如 90/365 天）复核——复核结果可能改变排序，最终表以复核为准。
- 组合数超上限：自动等距抽稀每个参数的候选值。
"""
from dataclasses import dataclass, field
from typing import Callable, Dict, List
import itertools
import time

from .registry import load_registry


class OptimizerError(ValueError):
    pass


@dataclass
class OptRow:
    overrides: Dict[str, float]
    npc_cny: float = None
    reliability: float = None
    feasible: bool = None
    kpis: Dict = field(default_factory=dict)
    note: str = ""


@dataclass
class OptResult:
    rows: List[OptRow]                       # 全部组合行（含不可行，feasible 标记）
    top: List[OptRow]                        # 可行且按 NPC 升序的前 N 行（复核后）
    n_combinations: int = 0
    n_feasible: int = 0
    n_infeasible_reliability: int = 0
    n_failed_sim: int = 0
    grid_thinned: bool = False
    refine_days: int = None
    elapsed_s: float = 0.0


def _thin_grid(candidates: Dict[str, List[float]], max_comb: int) -> (Dict, bool):
    """组合数超限 → 等距抽稀各参数候选（保序）。"""
    n = 1
    for v in candidates.values():
        n *= len(v)
    if n <= max_comb:
        return candidates, False
    thinned = {}
    # 目标：把每个维度缩到约 (max_comb)^(1/k)
    k = len(candidates)
    per = max(2, int(round(max_comb ** (1.0 / k))))
    for name, vals in candidates.items():
        vals_sorted = sorted(set(float(v) for v in vals))
        if len(vals_sorted) <= per:
            thinned[name] = vals_sorted
        else:
            step = (len(vals_sorted) - 1) / (per - 1)
            idx = [int(round(i * step)) for i in range(per)]
            thinned[name] = [vals_sorted[i] for i in sorted(set(idx))]
    return thinned, True


def optimize_capacity(sim_fn: Callable[[Dict], Dict],
                      base_overrides: Dict[str, float],
                      candidates: Dict[str, List[float]],
                      n_days: int = 30,
                      refine_top_n: int = None,
                      refine_days: int = 90,
                      top_n: int = None,
                      reliability_min: float = None,
                      max_combinations: int = None) -> OptResult:
    """穷举优化。sim_fn(overrides) → {'npc':…, 'reliability':…, 'kpis':{…}}。

    candidates: {"pv.capacity_kw": [25, 50, 75], "pemwe.rated_kw": [10, 25], ...}
    返回 top-N（默认经长周期复核后按 NPC 排序）。
    """
    reg = load_registry()
    d = dict(reg.defaults())
    d.update({k: float(v) for k, v in base_overrides.items()})
    if reliability_min is None:
        reliability_min = d["opt.reliability_target"]
    if top_n is None:
        top_n = int(d["opt.top_n"])
    if max_combinations is None:
        max_combinations = int(d["opt.max_combinations"])
    if not candidates:
        raise OptimizerError("候选容量集为空")
    for name, vals in candidates.items():
        reg.spec(name)          # 必须是注册表参数（铁律2）
        if not vals:
            raise OptimizerError(f"{name} 候选集为空")

    grid, thinned = _thin_grid(candidates, max_combinations)
    keys = list(grid.keys())
    combos = list(itertools.product(*[grid[k] for k in keys]))
    t0 = time.time()
    rows: List[OptRow] = []
    n_infeas = n_fail = 0
    for combo in combos:
        ov = dict(base_overrides)
        ov.update({k: float(v) for k, v in zip(keys, combo)})
        row = OptRow(overrides=dict(zip(keys, map(float, combo))))
        try:
            out = sim_fn(ov)
            row.npc_cny = out.get("npc")
            row.reliability = out.get("reliability")
            row.kpis = out.get("kpis", {})
            if row.reliability is not None and row.reliability < reliability_min:
                row.feasible = False
                row.note = f"保供率 {row.reliability:.2%} < {reliability_min:.2%}"
                n_infeas += 1
            else:
                row.feasible = True
        except Exception as e:
            row.feasible = False
            row.note = f"仿真失败: {type(e).__name__}"
            n_fail += 1
        rows.append(row)

    feas = [r for r in rows if r.feasible and r.npc_cny is not None]
    feas.sort(key=lambda r: r.npc_cny)

    # 长周期复核 top-N（复核可能改变排序——以复核为准）
    if refine_top_n is None:
        refine_top_n = min(top_n, len(feas))
    refined: List[OptRow] = []
    for r in feas[:refine_top_n]:
        row2 = OptRow(overrides=r.overrides)
        try:
            out = sim_fn({**base_overrides, **r.overrides}, n_days=refine_days)
            row2.npc_cny = out.get("npc")
            row2.reliability = out.get("reliability")
            row2.kpis = out.get("kpis", {})
            row2.feasible = (row2.reliability is None or
                              row2.reliability >= reliability_min)
            row2.note = f"复核 {refine_days} 天"
        except Exception:
            row2 = r           # 复核失败退回粗筛结果（标注）
            row2.note = "复核失败，用粗筛值"
        refined.append(row2)
    refined.sort(key=lambda r: r.npc_cny)
    return OptResult(rows=rows, top=refined[:top_n],
                     n_combinations=len(combos),
                     n_feasible=len(feas), n_infeasible_reliability=n_infeas,
                     n_failed_sim=n_fail, grid_thinned=thinned,
                     refine_days=refine_days, elapsed_s=time.time() - t0)


def result_table(result: OptResult) -> List[Dict]:
    """top-N 排序表（报告渲染用）。"""
    out = []
    for i, r in enumerate(result.top, 1):
        row = {"rank": i, "npc_cny": round(r.npc_cny, 0) if r.npc_cny else None,
               "reliability": round(r.reliability, 4) if r.reliability is not None else None,
               "note": r.note}
        row.update({k: round(v, 2) for k, v in r.overrides.items()})
        row.update({k: (round(v, 2) if isinstance(v, (int, float)) else v)
                    for k, v in list(r.kpis.items())[:6]})
        out.append(row)
    return out
