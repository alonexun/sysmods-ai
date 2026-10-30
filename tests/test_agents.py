# -*- coding: utf-8 -*-
"""Agent 层测试：grillme / 变更单 / 盲区卡 / 编排状态机（规则版全程可测）。"""
import pytest
from agents.grillme import GrillmeAgent, SCENARIOS
from agents.change_order import ChangeOrderAgent, ChangeOrderError
from agents.gaps import GapAgent
from agents.orchestrator import Orchestrator, State, OrchestratorError, MAX_CHANGE_ROUNDS


def dummy_sim(template, overrides):
    """确定性仿真替身：KPI 与光伏容量成正比（状态机测试不依赖真内核）。"""
    cap = float(overrides.get("pv.capacity_kw", 50.0))
    return {"kpi": {"e_pv_kwh": cap * 100.0, "reliability": 1.0},
            "econ": {"lcoe": 1.0}, "cons_passed": True,
            "confidence": {"grade": "C", "attribution": "模型=C",
                          "improvement": "切换权威库精算模式（pvlib/PySAM）可提升"},
            "series": {}, "elapsed_s": 0.01}


class TestGrillme:
    def test_scenario_detection(self):
        g = GrillmeAgent()
        assert g.detect_scenario("建风光绿氨项目，合成氨 1 吨每小时") == "绿氨"
        assert g.detect_scenario("边防哨站离网供电") == "哨站/离网"
        assert g.detect_scenario("氢冶金 DRI 钢厂") == "氢冶金"

    def test_param_card_structure(self):
        g = GrillmeAgent()
        card = g.build_param_card("绿氨项目", {"wind.capacity_kw": 2000.0})
        assert card["template"] == "T6"
        assert card["completeness"] > 0
        assert "合成氨" in " ".join(card["questions"])
        assert card["levels"]["wind.capacity_kw"] == "A"   # 客户提供的值→A 级声明

    def test_override_validated(self):
        g = GrillmeAgent()
        with pytest.raises(ValueError):
            g.build_param_card("绿氨", {"wind.capacity_kw": -5.0})   # 越界拒绝


class TestChangeOrder:
    def test_parse_and_echo(self):
        c = ChangeOrderAgent()
        order = c.parse("把电解槽功率调到 100 千瓦")
        assert order["param"] == "pemwe.rated_kw"
        assert order["new_value"] == pytest.approx(100.0)
        assert "确认执行" in order["echo"]
        assert order["confirmed"] is False

    def test_out_of_range_turned_into_clarification(self):
        c = ChangeOrderAgent()
        order = c.parse("把电解槽改到 99999")
        assert order.get("need_clarification") is True   # 越界→澄清而非静默

    def test_no_param_clarification(self):
        c = ChangeOrderAgent()
        order = c.parse("价格太贵了")
        assert order.get("need_clarification") is True

    def test_unconfirmed_apply_forbidden(self):
        c = ChangeOrderAgent()
        order = c.parse("把储氢改到 8000")
        with pytest.raises(ChangeOrderError):
            c.apply(order, {"h2store.capacity_kg": 10.0})
        order["confirmed"] = True
        new = c.apply(order, {"h2store.capacity_kg": 10.0})
        assert new["h2store.capacity_kg"] == 8000.0
        assert "h2store.capacity_kg" in new and len(new) == 1  # 副本非原地


class TestGapAgent:
    def test_ammonia_scenario_gets_ammonia_card(self):
        g = GapAgent()
        rep = g.report("绿氨")
        topics = [c["topic"] for c in rep["cards"]]
        assert "氨储运与危化品" in topics
        assert "碳市场政策" in topics

    def test_every_card_has_impact_direction(self):
        g = GapAgent()
        for card in g.report("哨站/离网")["cards"]:
            assert card["impact"] and card["advice"]


class TestOrchestrator:
    def test_full_flow_g1_run_change_g5(self):
        orch = Orchestrator(dummy_sim)
        s = orch.create_session("S1", "绿氨项目 合成氨 1吨每小时")
        assert s.state == State.G1_PENDING
        assert s.param_card["template"] == "T6"
        # G1
        orch.confirm_g1("S1", {"pv.capacity_kw": 60.0})
        assert s.state == State.G1_CONFIRMED
        # RUN
        s = orch.run_simulation("S1")
        assert s.state == State.G4_PENDING
        assert s.result["kpi"]["e_pv_kwh"] == pytest.approx(6000.0)
        assert s.version == 2
        # G4 变更单
        order = orch.propose_change("S1", "把光伏改到 80")
        assert "确认执行" in order["echo"]
        s = orch.confirm_change("S1")
        assert s.change_rounds == 1
        assert s.result["kpi"]["e_pv_kwh"] == pytest.approx(8000.0)
        # G5
        orch.sign_g5("S1")
        assert s.state == State.G5_SIGNED

    def test_state_guards(self):
        orch = Orchestrator(dummy_sim)
        orch.create_session("S2", "哨站离网")
        with pytest.raises(OrchestratorError):
            orch.run_simulation("S2")          # 未 G1 不能跑
        with pytest.raises(OrchestratorError):
            orch.propose_change("S2", "把光伏改到 80")
        orch.confirm_g1("S2")
        with pytest.raises(OrchestratorError):
            orch.sign_g5("S2")                # 无结果不能签收

    def test_bounded_change_rounds(self):
        orch = Orchestrator(dummy_sim)
        orch.create_session("S3", "哨站离网")
        orch.confirm_g1("S3")
        orch.run_simulation("S3")
        for i in range(MAX_CHANGE_ROUNDS):
            order = orch.propose_change("S3", "把光伏改到 55")
            orch.confirm_change("S3")
        blocked = orch.propose_change("S3", "把光伏改到 66")
        assert blocked.get("need_clarification")
        assert "上限" in blocked["msg"]

    def test_checkpoint_roundtrip(self):
        orch = Orchestrator(dummy_sim)
        orch.create_session("S9", "绿氨 合成氨")
        orch.confirm_g1("S9")
        orch.run_simulation("S9")
        cp = orch.session("S9").checkpoint()
        orch2 = Orchestrator(dummy_sim)
        s2 = orch2.restore(cp)
        assert s2.state == State.G4_PENDING
        assert s2.result["kpi"]["e_pv_kwh"] == pytest.approx(5000.0)
        orch2.sign_g5("S9")
        assert s2.state == State.G5_SIGNED

    def test_conservation_fail_g3(self):
        def bad_sim(template, ov):
            return {"kpi": {}, "econ": {}, "cons_passed": False,
                    "cons_summary": "守恒审计[FAIL]", "series": {}}
        orch = Orchestrator(bad_sim)
        orch.create_session("S4", "哨站离网")
        orch.confirm_g1("S4")
        s = orch.run_simulation("S4")
        assert s.state == State.G1_CONFIRMED    # 未进 G4
        assert len(s.result["g3_options"]) == 3
