# -*- coding: utf-8 -*-
"""LLM 接入测试：Mock 离线全链路 + 真实 DeepSeek API 冒烟（skipif 无 key）。

守门纪律验证：LLM 输出必须过 canonical 注册表 validate；越界值丢弃；
非法输出降级规则模式（V1.2 §5.8 降级运行——禁止静默）。
"""
import json
import os
import pytest

from agents.base import AgentRuntime
from agents.grillme import GrillmeAgent
from agents.change_order import ChangeOrderAgent
from agents.orchestrator import Orchestrator
from services.api.llm import LLMGateway, LLMNotConfiguredError, MockLLM, extract_json, LLMError

TEXT = "在内蒙古建风光绿氨项目，合成氨每小时 1.5 吨，风机 2000 千瓦"


@pytest.fixture
def mock_llm():
    return MockLLM(routes={
        "已知场景识别": json.dumps({
            "scenario_hint": "绿氨",
            "params": {"chem.nh3.capacity_t_per_h": 1.5, "wind.capacity_kw": 2000.0,
                       "pv.capacity_kw": 999.99},      # 最后一项越界（PV 上限合法，但值荒谬→靠业务范围？改用真越界）
            "questions": ["绿氨消纳是长协还是市场价？"],
            "note": "抽取完成"}, ensure_ascii=False),
        "可变更参数白名单": json.dumps({
            "param": "pemwe.rated_kw", "new_value": 60.0, "confidence": 0.92}),
        "客户评论：把电解槽改到 60 千瓦": json.dumps({
            "param": "pemwe.rated_kw", "new_value": 60.0, "confidence": 0.92}),
    })


class TestGateway:
    def test_not_configured_raises(self, monkeypatch):
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        gw = LLMGateway()
        assert gw.configured is False
        with pytest.raises(LLMNotConfiguredError):
            gw.chat("s", "u")

    def test_extract_json_strips_fences(self):
        assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
        assert extract_json('{"a": 2}') == {"a": 2}
        with pytest.raises(LLMError):
            extract_json("不是 JSON")

    def test_mock_usage_accounting(self):
        m = MockLLM(default_response='{"ok": true}')
        m.chat("system text", "user text")
        assert m.usage.calls == 1
        assert m.usage.total_tokens > 0


class TestGrillmeLLM:
    def test_llm_extraction_with_validation_gate(self, mock_llm):
        """LLM 抽取：合法项入卡并升 A 级；越界/未注册项被丢弃并显式标注。"""
        # 构造一个真越界项（pv.derate 上限 1.0）
        mock_llm.routes["已知场景识别"] = json.dumps({
            "scenario_hint": "绿氨",
            "params": {"chem.nh3.capacity_t_per_h": 1.5, "pv.derate": 1.5},
            "questions": ["绿氨消纳口径？"], "note": "x"})
        agent = GrillmeAgent(AgentRuntime(llm_client=mock_llm))
        card = agent.build_param_card(TEXT, use_llm=True)
        assert card["llm_mode"] == "llm"
        assert card["params"]["chem.nh3.capacity_t_per_h"] == pytest.approx(1.5)
        assert card["levels"]["chem.nh3.capacity_t_per_h"] == "A"
        assert card["params"]["pv.derate"] == pytest.approx(0.85)   # 越界被拒→保持默认
        assert "丢弃" in card["llm_note"] or "未通过" in card["llm_note"]
        assert any("长协" in q or "消纳" in q for q in card["questions"])

    def test_degrades_to_rules_on_llm_failure(self):
        """LLM 输出非法 JSON → 降级规则模式并标注（禁止静默）。"""
        bad = MockLLM(default_response="我行我素不是 JSON")
        agent = GrillmeAgent(AgentRuntime(llm_client=bad))
        card = agent.build_param_card(TEXT, use_llm=True)
        assert card["llm_mode"] == "degraded"
        assert "规则模式" in card["llm_note"]
        assert card["scenario"] == "绿氨"          # 规则版结果仍可用

    def test_rule_mode_default(self):
        """use_llm=False → 不调 LLM（计费透明）。"""
        called = []
        spy = MockLLM(responder=lambda s, u: called.append(1) or "{}")
        agent = GrillmeAgent(AgentRuntime(llm_client=spy))
        card = agent.build_param_card(TEXT, use_llm=False)
        assert card["llm_mode"] == "off"
        assert called == []


class TestChangeOrderLLM:
    def test_llm_parse_with_gate(self, mock_llm):
        agent = ChangeOrderAgent(AgentRuntime(llm_client=mock_llm))
        order = agent.parse("把电解槽改到 60 千瓦", use_llm=True)
        assert order["type"] == "param_change"
        assert order["param"] == "pemwe.rated_kw"
        assert order["new_value"] == pytest.approx(60.0)
        assert order["llm_mode"] == "llm"
        assert "确认执行" in order["echo"]

    def test_llm_illegal_value_degrades_to_rule(self):
        """LLM 给出越界值 → 校验拒绝 → 降级规则版（守门生效）。"""
        bad = MockLLM(default_response=json.dumps(
            {"param": "pv.derate", "new_value": 9.9, "confidence": 0.8}))
        agent = ChangeOrderAgent(AgentRuntime(llm_client=bad))
        order = agent.parse("把系统折损改到 9.9", use_llm=True)
        # 越界 → LLM 路径抛 ValueError → 降级规则版；规则版识别不到"折损"别名 → 澄清
        assert order.get("need_clarification") or order.get("llm_mode") == "degraded"

    def test_no_param_intent_returns_none_path(self):
        """纯提问/抱怨（param=null）→ 澄清而非猜参数。"""
        m = MockLLM(default_response=json.dumps({"param": None}))
        agent = ChangeOrderAgent(AgentRuntime(llm_client=m))
        order = agent.parse("价格太贵了", use_llm=True)
        assert order.get("need_clarification") is True

    def test_orchestrator_with_llm_change(self, mock_llm):
        """编排端到端：LLM 变更单 → 确认 → 重跑。"""
        def dummy_sim(template, ov):
            return {"kpi": {"e_pv_kwh": 50.0 * 100}, "econ": {"lcoe": 1.0},
                    "cons_passed": True,
                    "confidence": {"grade": "C", "attribution": "模型=C",
                                   "improvement": "权威库"},
                    "series": {}, "elapsed_s": 0.01}
        orch = Orchestrator(dummy_sim, llm_runtime=AgentRuntime(llm_client=mock_llm))
        s = orch.create_session("S1", TEXT)
        orch.confirm_g1("S1")
        orch.run_simulation("S1")
        order = orch.propose_change("S1", "把电解槽改到 60 千瓦", use_llm=True)
        assert order.get("type") == "param_change"
        orch.confirm_change("S1")
        assert s.param_card["params"]["pemwe.rated_kw"] == pytest.approx(60.0)


class TestRealDeepSeekSmoke:
    @pytest.mark.skipif(not os.environ.get("DEEPSEEK_API_KEY"),
                        reason="DEEPSEEK_API_KEY 未配置——真实调用冒烟跳过")
    def test_real_api_smoke(self):
        gw = LLMGateway()
        out = gw.chat("你是一个 JSON 生成器。只输出 JSON。",
                      '输出 {"ok": true, "n": 42}', json_mode=True)
        data = extract_json(out)
        assert data.get("ok") is True
        assert gw.usage.total_tokens > 0
