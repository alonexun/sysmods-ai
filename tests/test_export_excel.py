# -*- coding: utf-8 -*-
"""Excel 计算书导出测试：公式存在、结构完整、可审计。"""
import os
import pytest
from openpyxl import load_workbook

from kernel.hyflow.templates.t1_offgrid import build_t1_config, synth_ghi, synth_load
from kernel.hyflow.engine import run_t1
from services.reports.export_excel import export_calcbook


@pytest.fixture(scope="module")
def short_result():
    cfg = build_t1_config()
    r = run_t1(cfg, synth_ghi(2), synth_load(2))
    assert r.cons_report.passed
    return r


def test_export_creates_calcbook(tmp_path, short_result):
    out = str(tmp_path / "calcbook.xlsx")
    export_calcbook(short_result, out)
    assert os.path.exists(out)
    wb = load_workbook(out, data_only=False)   # 读公式
    assert set(wb.sheetnames) == {"输入参数", "时序", "KPI"}


def test_input_sheet_canonical_and_sources(tmp_path, short_result):
    out = str(tmp_path / "calcbook.xlsx")
    export_calcbook(short_result, out)
    wb = load_workbook(out)
    ws = wb["输入参数"]
    names = {ws.cell(i, 1).value for i in range(2, ws.max_row + 1)}
    assert "pv.capacity_kw" in names
    assert "pemwe.eff_lhv" in names
    # 出处列非空（溯源铁律）
    for i in range(2, ws.max_row + 1):
        assert ws.cell(i, 7).value  # source


def test_kpi_sheet_has_formulas(tmp_path, short_result):
    out = str(tmp_path / "calcbook.xlsx")
    export_calcbook(short_result, out)
    wb = load_workbook(out, data_only=False)
    ws = wb["KPI"]
    kv = {ws.cell(i, 1).value: ws.cell(i, 2).value for i in range(2, ws.max_row + 1)}
    assert kv["e_pv_kwh"].startswith("=SUM(时序!")
    assert kv["reliability"].startswith("=1-")
    assert isinstance(kv["total_npc_cny"], (int, float))
    assert kv["conservation_passed"] == "True"
    assert kv["confidence_grade"] in ("A", "B", "C", "D")


def test_timeseries_rows_and_consistency(tmp_path, short_result):
    out = str(tmp_path / "calcbook.xlsx")
    export_calcbook(short_result, out)
    wb = load_workbook(out)
    ws = wb["时序"]
    n = len(short_result.hours)
    assert ws.max_row == n + 1
    # 首行数据 = 时步 0 的 pv_kw
    assert ws.cell(2, 2).value == pytest.approx(float(short_result.pv_kw[0]))
