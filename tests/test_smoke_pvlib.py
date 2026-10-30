# -*- coding: utf-8 -*-
"""pvlib 调用正确性冒烟（双轨测试①——L1 权威库模式能跑通且输出物理合理）。
未安装 pvlib 时自动跳过（requirements 中为可选依赖）。"""
import numpy as np
import pandas as pd
import pytest

pvlib = pytest.importorskip("pvlib", reason="pvlib 未安装")

from kernel.hyflow.modules.pv import pv_power_pvlib


def test_pvlib_smoke_basic_shape():
    """合成晴天 24h：输出非负、有限、白昼有出力。"""
    idx = pd.date_range("2025-06-01", periods=24, freq="h", tz="Asia/Shanghai")
    hod = np.arange(24)
    ghi = np.clip(np.sin(np.pi * (hod - 6.0) / 12.0), 0, None) * 800.0
    temp = np.full(24, 20.0)
    out = pv_power_pvlib(idx, ghi, temp, capacity_kw=50.0,
                         latitude_deg=29.65, derate=1.0)
    assert len(out) == 24
    assert np.isfinite(out).all()
    assert (out >= -1e-9).all()
    assert out.max() > 0.0            # 白天必须有出力
    assert out[int(np.argmax(ghi))] > 0.0
