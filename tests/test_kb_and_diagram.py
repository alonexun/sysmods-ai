# -*- coding: utf-8 -*-
"""Agent 知识库体系测试：注册表/加载器/manifest/设计 tokens/架构图生成。"""
import pytest
from agents.kb_loader import (load_registry, load_agent_kb, kb_manifest,
                               design_tokens)
from services.reports.system_diagram import diagram_svg


class TestKBRegistry:
    EXPECTED = ["orchestrator", "grillme", "retrieval", "checker",
                "change_order", "deliverable"]

    def test_all_agents_have_kb(self):
        """每个 Agent 都有正式 KB 文件（用户核心诉求：知识库是一等资产）。"""
        reg = load_registry()
        for agent in self.EXPECTED:
            assert agent in reg["agents"], f"Agent {agent} 缺 KB 注册"
            kb = load_agent_kb(agent)
            assert kb["kb"], f"Agent {agent} KB 为空"
            for rel, text in kb["kb"].items():
                assert len(text) > 200, f"{rel} 内容过短"
                assert "来源" in text or "来源：" in text

    def test_deliverable_skill_and_external_sources(self):
        kb = load_agent_kb("deliverable")
        assert "deliverable/skills/SKILL.md" in kb["skills"]
        assert len(kb["external_sources"]) >= 3     # HOMER/IBCS/nTop 标杆出处
        text = kb["kb"]["deliverable/kb/homer_report_structure.md"]
        assert "Cash Flow" in text and "五类" in text
        assert "homerenergy.com" in text

    def test_manifest_has_versions_and_hashes(self):
        m = kb_manifest()
        for agent in self.EXPECTED:
            assert m[agent]["version"]
            assert m[agent]["files"]
            for h in m[agent]["files"].values():
                assert len(h) == 12

    def test_design_tokens(self):
        t = design_tokens()
        assert "#16489D" in t          # 主色
        assert "禁忌" in t             # IBCS 红线
        assert "Microsoft YaHei" in t

    def test_unknown_agent_rejected(self):
        with pytest.raises(KeyError):
            load_agent_kb("nonexistent")


class TestDiagram:
    def test_t6_layout_contains_enabled_units(self):
        svg = diagram_svg({
            "pv.capacity_kw": 800.0, "wind.capacity_kw": 1500.0,
            "pemwe.rated_kw": 600.0, "alk.rated_kw": 300.0,
            "h2store.capacity_kg": 6000.0,
            "chem.nh3.capacity_t_per_h": 0.6}, template="T6")
        assert svg.startswith("<svg")
        for s in ["光伏", "风电", "PEM 电解", "ALK 电解", "储氢缓冲",
                  "ASU 空分", "合成氨 HB", "绿氨产品"]:
            assert s in svg, s
        assert "800 kW" in svg and "300 kW" in svg
        assert "AEM" not in svg          # 未启用的不画

    def test_t1_layout(self):
        svg = diagram_svg({"pv.capacity_kw": 50.0, "pemwe.rated_kw": 25.0,
                           "h2store.capacity_kg": 10.0, "fc.rated_kw": 10.0,
                           "load.avg_kw": 5.0}, template="T1")
        for s in ["光伏", "PEM 电解", "储氢", "燃料电池", "负载"]:
            assert s in svg

    def test_empty_params_graceful(self):
        svg = diagram_svg({}, template="T6")
        assert svg.startswith("<svg")    # 不崩溃（缺省块仍存在）
