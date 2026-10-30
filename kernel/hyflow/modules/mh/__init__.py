# -*- coding: utf-8 -*-
"""PMHT（Purdue Metal Hydride Toolbox）Python 等价移植。

来源: github.com/PurdueH2Lab/MetalHydrideToolbox（Tyler Voskuilen 2014, BSD）
移植纪律（V1.2 §6）: 以 MATLAB 原版为物理真值，禁止照搬自研简化 python_version；
验收: 337 材料全量解析 + 理论锚点（LaNi5 半充 298K 平台压）+ 能量守恒账。
"""
from .parser import parse_mh_file, list_materials, load_hydride
from .hydride import Hydride
from .bed import simulate_bed
