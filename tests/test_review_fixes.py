# -*- coding: utf-8 -*-
"""2026-10-25 构建审查修复的专项回归（A 级口径/语义/状态问题）。"""
import pytest
from kernel.hyflow.templates.t1_offgrid import run_t1_scenario
from kernel.hyflow.templates.t6_ammonia import run_t6_scenario, build_t6_config, run_t6
from kernel.hyflow.templates.t1_offgrid import synth_ghi
from kernel.hyflow.modules.wind import synth_wind
from kernel.hyflow.econ.npc import crf
from agents.grillme import GrillmeAgent
from agents.base import AgentRuntime
from services.api.llm import MockLLM
import json


class TestLcohCrf:
    def test_lcoh_matches_annualized_formula(self):
        """LCOH = NPC×CRF/年产氢（与 LCOE 同口径；此前漏乘 CRF）。"""
        r = run_t1_scenario(n_days=90)
        e = r.econ
        expect = e["total_npc_cny"] * crf(0.06, 20) / r.kpi["h2_prod_kg"]
        assert e["lcoh_cny_per_kg"] == pytest.approx(expect, rel=1e-9)
        assert "年化口径" in e["lcoh_note"]


class TestT6EconDedicatedParams:
    def test_nh3_capex_parameter_sensitivity(self):
        """合成氨装置投资使用专用参数（敏感于 nh3_capex，而非储氢价格凑数）。"""
        ov = {"pv.capacity_kw": 500.0, "wind.capacity_kw": 800.0,
              "h2store.capacity_kg": 4000.0, "h2store.level_init_kg": 2000.0,
              "pemwe.rated_kw": 500.0, "bess.capacity_kwh": 500.0}
        base = run_t6_scenario(ov, n_days=30)
        double = run_t6_scenario({**ov, "econ.nh3_capex_cny_per_t_per_h": 4e7}, n_days=30)
        assert double.econ["npc_gross_cny"] > base.econ["npc_gross_cny"]
        # 装置投资翻倍对 NPC 有实质影响（单位投资与寿命项进入现值）
        delta = double.econ["npc_gross_cny"] - base.econ["npc_gross_cny"]
        assert delta > 0

    def test_wind_capex_uses_wind_params(self):
        ov = {"pv.capacity_kw": 500.0, "wind.capacity_kw": 800.0,
              "h2store.capacity_kg": 4000.0, "h2store.level_init_kg": 2000.0,
              "pemwe.rated_kw": 500.0, "bess.capacity_kwh": 500.0}
        a = run_t6_scenario(ov, n_days=30)
        b = run_t6_scenario({**ov, "econ.wind_capex_per_kw": 11000.0}, n_days=30)
        assert b.econ["npc_gross_cny"] > a.econ["npc_gross_cny"]


class TestOptimizerReliabilitySemantic:
    def test_t6_reliability_is_supply_based(self):
        """优化器 T6 保供率 = 1 - 失电/总供给（不再误用绿电自给率）。"""
        from services.api.main import _opt_sim
        out = _opt_sim("T6", {"h2store.capacity_kg": 4000.0,
                              "h2store.level_init_kg": 2000.0}, n_days=15)
        assert 0.0 <= out["reliability"] <= 1.0


class TestGrillmeNoStateLeak:
    def test_llm_questions_not_leaked_to_next_card(self):
        """LLM 追问不得残留到下一次（规则模式）参数卡——状态污染回归。"""
        m = MockLLM(routes={"已知场景识别": json.dumps({
            "scenario_hint": "绿氨", "params": {},
            "questions": ["这是 LLM 的追问"], "note": "x"})})
        agent = GrillmeAgent(AgentRuntime(llm_client=m))
        card1 = agent.build_param_card("风光绿氨 1吨/小时", use_llm=True)
        assert "这是 LLM 的追问" in card1["questions"]
        card2 = agent.build_param_card("边防哨站离网", use_llm=False)
        assert "这是 LLM 的追问" not in card2["questions"]


class TestG1Persist:
    def test_g1_checkpoint_saved(self):
        import os
        from services.api import db
        from fastapi.testclient import TestClient
        from services.api.main import app
        c = TestClient(app)
        r = c.post("/auth/register", json={"phone": "13900000009", "code": "000000"})
        token = r.json()["token"]
        h = {"X-Token": token}
        s = c.post("/session", json={"phone": "13900000009", "description": "哨站"},
                   headers=h).json()
        r = c.post(f"/session/{s['sid']}/g1",
                   json={"phone": "13900000009", "overrides": {}}, headers=h)
        assert r.status_code == 200
        cp = db.load_checkpoint(s["sid"])
        assert cp is not None and cp["state"] == "G1_CONFIRMED"
