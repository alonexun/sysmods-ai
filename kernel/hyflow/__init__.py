# -*- coding: utf-8 -*-
"""Sysmods AI 物理内核（HyFlow）——数值唯一来源。

铁律（V1.2 方案 §12）：
1. 参数 Schema 带单位强制；2. canonical 单一权威源；
3. 禁止静默兜底；4. 每步守恒审计，年误差>0.5% FAIL。
"""
__version__ = "0.1.0"
