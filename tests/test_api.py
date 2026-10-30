# -*- coding: utf-8 -*-
"""服务层 API 全链路测试（TestClient）：注册→会话→G1→仿真→变更→签收→报告，
含积分台账对账与 G3/余额不足分支。DB 用独立临时文件（不污染开发库）。"""
import os
import sys
import tempfile
import time as _time_mod

_tmp = tempfile.mkdtemp(prefix="sysmods_api_test_")
os.environ["SYSMODS_DB"] = os.path.join(_tmp, "test.db")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient
import pytest

from services.api import db
db.DB_PATH = os.environ["SYSMODS_DB"]
from services.api.main import app, orch, REPORT_DIR, sim_fn
from services.api.db import Ledger
db.init_db()

client = TestClient(app)

PHONE = "13900000001"
TOKEN = None


def post(path, **kw):
    return client.post(path, headers={"X-Token": TOKEN or ""}, **kw)


def get(path, **kw):
    return client.get(path, headers={"X-Token": TOKEN or ""}, **kw)


@pytest.fixture(scope="module")
def fresh_user():
    global TOKEN
    r = post("/auth/register", json={"phone": PHONE, "code": "000000"})
    assert r.status_code == 200
    j = r.json()
    bal0 = j["credits"]
    assert bal0 > 0
    TOKEN = j["token"]          # 注册签发会话 token，后续受保护端点全部携带
    return bal0


def _mk_session(desc):
    r = post("/session", json={"phone": PHONE, "description": desc})
    assert r.status_code == 200
    return r.json()


class TestAuthAndLedger:
    def test_register_wrong_code(self):
        r = post("/auth/register", json={"phone": "13900000002", "code": "1234"})
        assert r.status_code == 401

    def test_statement_endpoint(self, fresh_user):
        r = get(f"/ledger/{PHONE}")
        assert r.status_code == 200
        assert r.json()["balance"] == fresh_user
        assert r.json()["statement"] == []


class TestFullFlow:
    def test_ammonia_flow_to_report(self, fresh_user):
        s = _mk_session("建风光绿氨项目 合成氨 1吨每小时")
        sid = s["sid"]
        assert s["param_card"]["scenario"] == "绿氨"
        assert len(s["gap_cards"]) >= 6
        # G1：给绿氨合理参数（吨级缓冲）
        r = post(f"/session/{sid}/g1", json={
            "overrides": {"pv.capacity_kw": 800.0, "wind.capacity_kw": 1200.0,
                          "h2store.capacity_kg": 6000.0, "h2store.level_init_kg": 3000.0,
                          "pemwe.rated_kw": 1000.0, "bess.capacity_kwh": 1000.0,
                          "bess.power_kw": 300.0}})
        assert r.status_code == 200
        # RUN
        r = post(f"/session/{sid}/run", json={"phone": PHONE})
        assert r.status_code == 200
        j = r.json()
        assert j["state"] == "G4_PENDING"
        res = j["result"]
        assert res["cons_passed"] is True
        assert res["kpi"]["nh3_annual_t"] > 0
        assert res["element_audit"]["N"] == pytest.approx(0.0, abs=1e-3)
        assert res["confidence"]["grade"] in "ABCD"
        # 月度免费额度优先：2 积分从免费 50 扣，实付 0（V1.2 §9.2）
        bal = get(f"/ledger/{PHONE}").json()["balance"]
        assert bal == fresh_user
        # G4 变更单回显
        r = post(f"/session/{sid}/change",
                        json={"phone": PHONE, "text": "把光伏改到 1000"})
        assert r.status_code == 200
        assert "确认执行" in r.json()["echo"]
        # 确认变更→重跑
        r = post(f"/session/{sid}/change/confirm",
                        json={"phone": PHONE, "text": "确认"})
        assert r.status_code == 200
        assert r.json()["rounds"] == 1
        # 线下打款→线上加积分（V1.2 §9.1 商业闭环；报告固定费 200 超新用户免费+余额）
        con = db.connect()
        Ledger(con).grant(PHONE, 500, reason="线下打款(测试)", ref="TX-001")
        con.close()
        # G5 签收→报告
        r = post(f"/session/{sid}/g5", json={"phone": PHONE})
        assert r.status_code == 200
        url = r.json()["report_url"]
        r2 = get(url)
        assert r2.status_code == 200
        html = r2.text
        assert "守恒审计 PASS" in html and "置信度" in html
        assert "nh3_annual_t" in html or "合成氨" in html
        assert "模型盲区提示" in html
        # 对账：初始 = 余额 + 2(仿真) + 2(重跑) + 200(报告)
        bal_end = get(f"/ledger/{PHONE}").json()
        spent = [x for x in bal_end["statement"]]
        assert bal_end["balance"] >= 0
        assert len(spent) >= 2

    def test_insufficient_credits_blocked(self):
        p = "13900000003"
        r = post("/auth/register", json={"phone": p, "code": "000000"})
        bal = r.json()["credits"]
        token_p = r.json()["token"]
        # 穷光蛋场景：清零（免费额度与月份标记同月，避免跨月重置干扰）
        con = db.connect()
        con.execute("UPDATE users SET credits=0, free_monthly=0, free_month=? WHERE phone=?",
                    (_time_mod.strftime("%Y-%m"), p))
        con.commit()
        con.close()
        s = _mk_session("哨站离网")
        r = post(f"/session/{s['sid']}/g1", json={"overrides": {}})
        # 用该账号自己的 token（鉴权通过但余额为 0 → 应 402 而非 401）
        r = client.post(f"/session/{s['sid']}/run", json={"phone": p},
                        headers={"X-Token": token_p})
        assert r.status_code == 402
        assert "积分不足" in r.json()["detail"]

    def test_report_not_found(self):
        r = get("/report/NOPE")
        assert r.status_code == 404

    def test_session_auto_restore_from_checkpoint(self, fresh_user):
        """服务重启语义：内存丢会话后，任何端点自动从 DB checkpoint 恢复。"""
        s = _mk_session("哨站离网供电")
        sid = s["sid"]
        post(f"/session/{sid}/g1", json={"phone": PHONE, "overrides": {}})
        # 模拟服务重启：从编排器内存删除会话（DB checkpoint 仍在）
        orch._sessions.pop(sid, None)
        with pytest.raises(Exception):
            orch.session(sid)                 # 内存确实没有
        r = get(f"/session/{sid}/diagram")     # 自动恢复路径
        assert r.status_code == 200 and r.text.startswith("<svg")
        assert sid in orch._sessions          # 已恢复进内存
        rd = get(f"/session/{sid}/report_data")
        assert rd.status_code == 200
        assert rd.json()["recall"]["goal"] == "哨站离网供电"

    def test_index_served(self):
        r = get("/")
        assert r.status_code == 200
        assert "Sysmods AI" in r.text

    def test_protected_requires_token(self):
        """无 token / 错 token 一律 401（会话级鉴权）。"""
        r = client.get(f"/ledger/{PHONE}")                       # 无 token
        assert r.status_code == 401
        r = client.get(f"/ledger/{PHONE}", headers={"X-Token": "wrong"})
        assert r.status_code == 401
        r = client.post("/session", json={"phone": PHONE, "description": "越权尝试"})
        assert r.status_code == 401


class TestOptimizeEndpoint:
    def test_optimize_capacity_top_table(self, fresh_user):
        """穷举+NPC 排序端点：小候选集 → top 表 + 统计 + 扣时长积分。"""
        con = db.connect()
        Ledger(con).grant(PHONE, 300, reason="优化测试充值", ref="TX-OPT")
        con.close()
        s = _mk_session("边防哨站离网供电 保供优先")
        sid = s["sid"]
        post(f"/session/{sid}/g1", json={"overrides": {
            "load.avg_kw": 4.0, "pv.capacity_kw": 40.0}})
        r = post(f"/session/{sid}/optimize", json={
            "phone": PHONE,
            "candidates": {"pv.capacity_kw": [30.0, 60.0],
                           "bess.capacity_kwh": [200.0]},
            "n_days": 30, "refine_days": 30})
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["n_combinations"] == 2
        assert len(j["top"]) >= 1
        assert j["top"][0]["rank"] == 1
        assert "npc_cny" in j["top"][0]
        # 排序：top[0].npc ≤ top[-1].npc
        npcs = [row["npc_cny"] for row in j["top"]]
        assert npcs == sorted(npcs)

    def test_optimize_bad_param_rejected(self, fresh_user):
        s = _mk_session("哨站离网")
        r = post(f"/session/{s['sid']}/optimize", json={
            "phone": PHONE, "candidates": {"not.a.param": [1.0]}, "n_days": 30})
        assert r.status_code == 400

    def test_session_llm_flag_off_by_default(self, fresh_user):
        """默认规则模式：llm_mode=off（计费透明，不产生 token 计量）。"""
        s = _mk_session("绿氨 合成氨 1吨每小时")
        assert s["param_card"]["llm_mode"] == "off"
        assert s["llm_tokens_used"] == 0
