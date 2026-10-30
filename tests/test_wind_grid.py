# -*- coding: utf-8 -*-
"""风机与电网模块测试（功率曲线锚点 + 四模式电价账 + 红线约束）。"""
import numpy as np
import pytest
from kernel.hyflow.modules.wind import WindParams, wind_power, synth_wind, WindError
from kernel.hyflow.modules.grid import GridParams, Grid, GridError


class TestWind:
    def test_power_curve_anchor(self):
        p = WindParams(capacity_kw=100.0)
        ws = np.array([0, 3, 7, 11, 25, 26])
        out = wind_power(ws, p)
        assert out[0] == 0.0          # 低于切入
        assert out[1] == 0.0          # 恰在切入
        assert out[3] == pytest.approx(100.0)   # 额定风速→满功率
        assert out[4] == pytest.approx(100.0)   # 切出前
        assert out[5] == 0.0          # 超切出停机
        # 中点线性：7m/s → 100×(7−3)/(11−3)=50
        assert out[2] == pytest.approx(50.0)

    def test_negative_ws_rejected(self):
        with pytest.raises(WindError):
            wind_power(np.array([-1.0]), WindParams(100.0))

    def test_synth_wind_finite(self):
        ws = synth_wind(8760)
        assert (ws >= 0).all() and np.isfinite(ws).all()


class TestGrid:
    def test_offgrid_no_trade(self):
        g = Grid(GridParams(mode="offgrid"))
        assert g.import_power(10.0, 0) == 0.0
        assert g.export_power(10.0, 0) == 0.0
        assert g.net_cost_cny == 0.0

    def test_tou_prices(self):
        g = Grid(GridParams(mode="tou", max_import_kw=100.0))
        assert g.buy_price(9) == pytest.approx(1.0)    # 峰
        assert g.buy_price(12) == pytest.approx(0.6)   # 平
        assert g.buy_price(3) == pytest.approx(0.3)     # 谷

    def test_ppa_import_and_redline(self):
        g = Grid(GridParams(mode="ppa", max_import_kw=50.0, ppa_price_cny_kwh=0.38))
        got = g.import_power(80.0, 0)
        assert got == pytest.approx(50.0)               # 红线截断
        assert g.net_cost_cny == pytest.approx(50.0 * 0.38)

    def test_spot_series(self):
        prices = np.full(48, 0.5)
        prices[10] = 2.0
        g = Grid(GridParams(mode="spot", max_import_kw=100.0, spot_price_cny_kwh=prices))
        g.import_power(10.0, 10)
        g.import_power(10.0, 11)
        assert g.net_cost_cny == pytest.approx(10 * 2.0 + 10 * 0.5)

    def test_spot_negative_price_rejected(self):
        with pytest.raises(GridError):
            Grid(GridParams(mode="spot", max_import_kw=10,
                            spot_price_cny_kwh=np.array([0.5, -0.2])))

    def test_export_revenue(self):
        g = Grid(GridParams(mode="tou", max_import_kw=100.0, sell_price_cny_kwh=0.35))
        g.export_power(30.0, 0)
        assert g.net_cost_cny == pytest.approx(-30.0 * 0.35)

    def test_invalid_mode(self):
        with pytest.raises(GridError):
            Grid(GridParams(mode="free"))
