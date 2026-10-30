# -*- coding: utf-8 -*-
"""增强报告测试：封面/目录/优化表章节/LLM 标注/打印样式。"""
import pytest
from services.reports.render_html import render_html_report


def _fake_result():
    return {"kpi": {"nh3_annual_t": 512.4, "renew_share": 0.93},
            "econ": {"npc_net_cny": 123000.0, "lcoa_cny_per_t": 32000.0},
            "cons_passed": True, "cons_summary": "守恒审计[PASS]",
            "confidence": {"grade": "B", "attribution": "模型=L3",
                           "improvement": "权威库可提升"},
            "series": {}, "opt_table": [
                {"rank": 1, "npc_cny": 90000.0, "reliability": 0.997,
                 "pv.capacity_kw": 800.0, "pemwe.rated_kw": 1200.0,
                 "h2_prod_kg": 620.0, "note": "复核 90 天"},
                {"rank": 2, "npc_cny": 102000.0, "reliability": 0.999,
                 "pv.capacity_kw": 1000.0, "pemwe.rated_kw": 1200.0,
                 "h2_prod_kg": 710.0, "note": "复核 90 天"}]}


def _render(**kw):
    return render_html_report(
        session_id="S123", description="风光绿氨演示",
        result=_fake_result(),
        param_card={"scenario": "绿氨", "template": "T6", "completeness": 0.8,
                    "params": {"pv.capacity_kw": 1000.0}, "version": 2},
        gap_report={"cards": [{"topic": "碳市场政策", "covered_by_model": "部分",
                               "impact": "影响减碳收益", "advice": "核验履约主体"}]},
        orders=[{"echo": "将 pemwe.rated_kw 设为 1200 kW", "confirmed": True}],
        opt_table=kw.pop("opt_table", None),
        llm_model=kw.pop("llm_model", "deepseek-chat（DeepSeek API）"))


class TestEnhancedReport:
    def test_cover_and_badges(self):
        html = _render()
        assert "分布式氢能方案计算报告" in html
        assert "守恒审计 PASS" in html
        assert "置信度 B" in html
        assert "版本 V2" in html

    def test_toc_and_sections(self):
        html = _render()
        for sec in ["需求回顾 Requirements Recall", "项目描述",
                    "最终方案与系统架构", "发电 / 制氢明细", "经济性",
                    "容量配置优化", "逐时序列", "关键参数", "变更记录",
                    "模型盲区", "未决问题与声明"]:
            assert sec in html, f"缺章节: {sec}"
        assert 'class="toc"' in html
        assert "0 需求回顾" in html and "2 最终方案" in html

    def test_architecture_svg_embedded(self):
        """v3 新增：系统架构 SVG 按参数卡动态生成（含组件与总线）。"""
        html = _render()
        assert "<svg" in html and "系统架构示意图" in html
        assert "光伏" in html and "合成氨" in html
        assert "#2563EB" in html or "#2563eb" in html   # 电总线色

    def test_chinese_param_names(self):
        """参数以中文名+canonical 双列展示（客户可读性硬要求）。"""
        html = _render()
        assert "光伏装机容量" in html
        assert "pv.capacity_kw" in html

    def test_kpi_cards_present(self):
        """摘要 KPI 大数字卡（IBCS 单 KPI 规则）。"""
        html = _render()
        assert "class='kpi'" in html
        assert "净 NPC" in html

    def test_cost_breakdown_section(self):
        """HOMER 成本明细章节（无组件明细时优雅降级）。"""
        html = _render()
        assert "成本明细" in html

    def test_optimization_table_rendered(self):
        html = _render(opt_table=_fake_result()["opt_table"])
        assert "HOMER 口径" in html
        assert "90,000" in html or "90000" in html      # NPC 数值渲染
        assert "复核 90 天" in html

    def test_no_opt_table_graceful(self):
        """result 与显式参数均无优化表 → 优雅降级文案。"""
        result = _fake_result()
        result.pop("opt_table", None)
        html = render_html_report(
            session_id="S124", description="x", result=result,
            param_card={"scenario": "绿氨", "template": "T6", "completeness": 1.0,
                        "params": {}, "version": 1},
            gap_report={"cards": []}, orders=[])
        assert "未执行容量优化" in html

    def test_llm_model_annotation(self):
        html = _render(llm_model="deepseek-chat（DeepSeek API）")
        assert "deepseek-chat" in html
        assert "LLM 不产生任何计算结果" in html
        html2 = _render(llm_model="规则模式（未接入 LLM）")
        assert "规则模式" in html2

    def test_print_css(self):
        assert "@media print" in _render()
