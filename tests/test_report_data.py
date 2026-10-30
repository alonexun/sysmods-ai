# -*- coding: utf-8 -*-
"""报告数据层测试：需求 Recall 组装（React 报告与 HTML 导出同源）。"""
import pytest
from services.reports.report_data import build_report_data
from kernel.hyflow.templates.t6_ammonia import run_t6_scenario


@pytest.fixture(scope="module")
def t6_result():
    ov = {"pv.capacity_kw": 800.0, "wind.capacity_kw": 1500.0,
          "pemwe.rated_kw": 600.0, "h2store.capacity_kg": 6000.0,
          "h2store.level_init_kg": 3000.0, "chem.nh3.capacity_t_per_h": 0.6}
    r = run_t6_scenario(ov, n_days=30)
    return {"kpi": r.kpi, "econ": r.econ, "cons_passed": r.cons_report.passed,
            "cons_summary": r.cons_report.summary(),
            "confidence": {"grade": r.confidence.grade,
                           "attribution": r.confidence.attribution},
            "series": {k: list(v[:24]) for k, v in r.series.items()}}


class TestRecall:
    def test_recall_contains_goal_and_client_params(self, t6_result):
        """Recall 必须复述用户目标与 A 级客户参数（需求被正确理解的回执）。"""
        ov = {"pv.capacity_kw": 800.0, "chem.nh3.capacity_t_per_h": 0.6}
        data = build_report_data(
            "S1", "内蒙古风光绿氨项目目标", t6_result,
            {"scenario": "绿氨", "template": "T6", "completeness": 0.9,
             "params": {**t6_result["kpi"].get("_", {}), **ov,
                        "pemwe.rated_kw": 600.0},
             "levels": {"pv.capacity_kw": "A", "chem.nh3.capacity_t_per_h": "A",
                        "pemwe.rated_kw": "B1"}},
            {"cards": []})
        rc = data["recall"]
        assert "内蒙古" in rc["goal"] and "绿氨" in rc["goal"]
        # 客户提供的 A 级非默认参数进 recall 清单
        names = [p["canonical"] for p in rc["client_params"]]
        assert "pv.capacity_kw" in names and "chem.nh3.capacity_t_per_h" in names
        # 中文参数名
        cn = {p["cn"] for p in rc["client_params"]}
        assert any("光伏" in c for c in cn)
        assert rc["objective"]  # 优化目标口径必填
        assert "签收" in rc["note"]  # Recall 的核对提示
        assert rc["priori_count"] >= 0

    def test_recall_includes_changes(self, t6_result):
        data = build_report_data(
            "S2", "哨站项目", t6_result,
            {"scenario": "哨站/离网", "template": "T1", "completeness": 1.0,
             "params": {"pv.capacity_kw": 50.0},
             "levels": {"pv.capacity_kw": "A"}},
            {"cards": []},
            orders=[{"echo": "将 pemwe.rated_kw 设为 60.0 kW。确认执行？",
                     "confirmed": True}])
        rc = data["recall"]
        assert len(rc["changes"]) == 1
        assert rc["changes"][0]["confirmed"] is True


class TestReportDataStructure:
    def test_full_structure(self, t6_result):
        data = build_report_data(
            "S3", "绿氨", t6_result,
            {"scenario": "绿氨", "template": "T6", "completeness": 0.8,
             "params": {"pv.capacity_kw": 800.0, "wind.capacity_kw": 1500.0},
             "levels": {"pv.capacity_kw": "A", "wind.capacity_kw": "A"}},
            {"cards": [{"topic": "碳市场", "covered_by_model": "部分",
                        "impact": "影响减碳收益", "advice": "核验"}]})
        # React 视图所需的全部键
        for key in ("meta", "recall", "kpi_cards", "kpi_table", "diagram_svg",
                    "generation_detail", "economics", "optimization", "timeseries",
                    "params", "orders", "gaps", "unresolved", "kb_manifest"):
            assert key in data, f"缺键: {key}"
        assert data["diagram_svg"].startswith("<svg")
        assert len(data["kpi_cards"]) == 4
        assert data["params"][0]["cn"]            # 中文参数名
        assert data["kb_manifest"]["deliverable"]["version"]

    def test_t6_generation_detail_bilingual(self, t6_result):
        data = build_report_data(
            "S4", "绿氨", t6_result,
            {"scenario": "绿氨", "template": "T6", "completeness": 1.0,
             "params": {"pv.capacity_kw": 800.0}, "levels": {}},
            {"cards": []})
        names = [g["name"] for g in data["generation_detail"]]
        assert any("Renewable" in n for n in names)          # 中英文模块名
        assert any("Green Ammonia" in n or "合成氨" in n for n in names)
        assert any("H2 Production" in n for n in names)
