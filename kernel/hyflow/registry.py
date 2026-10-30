# -*- coding: utf-8 -*-
"""canonical 参数注册表加载与校验（铁律 1/2/3 的执行点）。

- 参数必须存在于注册表（禁止悄悄用默认值——缺参必须显式传 default_policy）
- 单位/值域在注册表定义，入口校验
- 命名 `域.量_单位`
"""
import json
import os
from dataclasses import dataclass
from typing import Dict, Optional

REGISTRY_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "kb", "params", "canonical_registry.json")


@dataclass
class ParamSpec:
    name: str
    unit: str
    range: list
    default: object
    level: str
    chain: int
    source: str
    desc: str


class Registry:
    def __init__(self, path: Optional[str] = None):
        p = os.path.abspath(path or REGISTRY_PATH)
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.conventions = data["conventions"]
        self.specs: Dict[str, ParamSpec] = {}
        for item in data["params"]:
            spec = ParamSpec(**item)
            assert "." in spec.name, f"命名规则违规(缺域前缀): {spec.name}"
            self.specs[spec.name] = spec

    def spec(self, name: str) -> ParamSpec:
        if name not in self.specs:
            raise KeyError(f"参数不在 canonical 注册表: {name}（铁律2：禁止未注册参数）")
        return self.specs[name]

    def defaults(self) -> Dict[str, float]:
        return {k: s.default for k, s in self.specs.items()}

    def validate(self, name: str, value) -> None:
        """铁律3执行点：越界/类型错误直接抛异常，绝不静默截断。"""
        s = self.spec(name)
        try:
            v = float(value)
        except (TypeError, ValueError):
            raise ValueError(f"参数 {name}={value!r} 不是数值（铁律3：禁止静默兜底）")
        lo, hi = s.range
        if not (lo <= v <= hi):
            raise ValueError(f"参数 {name}={v} 越界 [{lo}, {hi}]（单位 {s.unit}；物理或市场合理范围）")

    def validated(self, params: Dict[str, float]) -> Dict[str, float]:
        """批量校验并返回（仅保留注册表内的键；缺失键由调用方决定显式策略）。"""
        out = {}
        for k, v in params.items():
            if k not in self.specs:
                raise KeyError(f"参数不在 canonical 注册表: {k}")
            self.validate(k, v)
            out[k] = float(v)
        return out


def load_registry(path: Optional[str] = None) -> Registry:
    return Registry(path)
