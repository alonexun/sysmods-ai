# -*- coding: utf-8 -*-
"""氢压缩机测试（V1.3 §6.1）：等温理想+η 锚点、错误拒绝、T1 高压路径耦合。"""
import numpy as np
import pytest

from kernel.hyflow.modules.compressor import (
    Compressor, CompressorError, CompressorParams,
)
from kernel.hyflow.templates.t1_offgrid import (
    build_t1_config, synth_ghi, synth_load,
)
from kernel.hyflow.engine import run_t1


class TestCompressor:
    def test_spec_anchor_30_to_350_eta07(self):
        """锚点（独立验算）：理想等温 = (R·T/M)·ln(350/30)/3.6e6
        = 0.3301×2.4567 ≈ 0.811 kWh/kg；÷η0.70 ≈ 1.158 kWh/kg。"""
        c = Compressor(CompressorParams(p_in_bar=30.0, p_out_bar=350.0, eta_iso=0.70))
        assert c.spec_kwh_per_kg == pytest.approx(1.158, rel=2e-3)

    def test_ideal_isothermal_coefficient(self):
        """η=1、压比= e（1→e bar）时单位理想等温功 = RT/M/3.6e6 ≈0.330 kWh/kg。"""
        import math
        c = Compressor(CompressorParams(p_in_bar=1.0, p_out_bar=math.e, eta_iso=1.0))
        assert c.spec_kwh_per_kg == pytest.approx(0.330, rel=5e-3)

    def test_energy_and_power(self):
        c = Compressor(CompressorParams())
        assert c.energy_kwh(10.0) == pytest.approx(10.0 * c.spec_kwh_per_kg)
        assert c.power_kw_for_flow(2.0) == pytest.approx(2.0 * c.spec_kwh_per_kg)
        assert c.energy_kwh(-1.0) if False else True  # 负流量在 energy 内抛错：
        with pytest.raises(CompressorError):
            c.energy_kwh(-1.0)

    def test_invalid_params(self):
        with pytest.raises(CompressorError):
            Compressor(CompressorParams(p_out_bar=30.0, p_in_bar=350.0))
        with pytest.raises(CompressorError):
            Compressor(CompressorParams(eta_iso=1.2))
        with pytest.raises(CompressorError):
            Compressor(CompressorParams(t_in_k=0.0))


class TestT1HighPressureCoupling:
    """高压路径：压缩电耗逐时进电平衡（自限公式 PEM+压缩共享盈余母线）。"""

    @staticmethod
    def _run(with_comp: bool):
        cfg = build_t1_config({"pv.capacity_kw": 150.0,        # BESS 饱和后盈余进入 PEM
                               "h2store.capacity_kg": 500.0,   # 罐不先饱和——否则压缩只改变到达上限的速度
                               "h2store.level_init_kg": 250.0})
        if with_comp:
            from kernel.hyflow.modules.compressor import Compressor, CompressorParams
            cfg.comp = Compressor(CompressorParams())
        ghi = synth_ghi(n_days=30, lat_deg=33.0)
        load = synth_load(n_days=30, avg_kw=5.0, night_ratio=0.8)
        return run_t1(cfg, ghi, load)

    def test_compression_reduces_h2_and_conservation_holds(self):
        r0 = self._run(with_comp=False)
        r1 = self._run(with_comp=True)
        # 产氢下降（压缩寄生），压缩电耗为正
        assert r1.kpi["h2_prod_kg"] < r0.kpi["h2_prod_kg"]
        assert r1.kpi["e_comp_kwh"] > 0.0
        assert r0.kpi["e_comp_kwh"] == 0.0
        # 压缩电耗来自"PEM 减载 + 原本会弃的电"：总量不超过旧 PEM+旧弃电（能量来源守恒）
        assert r1.kpi["e_pem_kwh"] <= r0.kpi["e_pem_kwh"] + 1e-6
        assert (r1.kpi["e_pem_kwh"] + r1.kpi["e_comp_kwh"]
                <= r0.kpi["e_pem_kwh"] + r0.kpi["e_curtail_kwh"] + 1e-6)
        # 两条路径守恒都必须 PASS
        assert r0.cons_report.passed and r1.cons_report.passed
        # 供氢方向：压缩后单位产氢的 PEM+压缩总电耗上升
        u0 = r0.kpi["e_pem_kwh"] / r0.kpi["h2_prod_kg"]
        u1 = (r1.kpi["e_pem_kwh"] + r1.kpi["e_comp_kwh"]) / r1.kpi["h2_prod_kg"]
        assert u1 > u0

    def test_series_present(self):
        r1 = self._run(with_comp=True)
        assert isinstance(r1.comp_kw, np.ndarray)
        assert len(r1.comp_kw) == 30 * 24
