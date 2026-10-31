# -*- coding: utf-8 -*-
"""MCP 受控工具契约测试（S1，V1.3 §2.6.1 封套 / §11 S1 验收）：
- 鉴权：无效 actor_token → UNAUTHORIZED（封套错误，不抛异常）
- 非法值不写入：注册表 range 之外 → INVALID_PARAM，参数卡值/状态/version 不变
- expected_version 过期 → VERSION_CONFLICT(retryable)
- 幂等：同 idempotency_key 重试 run_simulation 不重复扣费（台账行数不变）
- 只读：get_param_card 无副作用（version/台账不变）
- 协议冒烟：stdio 启动 python -m services.mcp_server → list_tools 四工具可见（DSH 接入面）
DB 用独立临时文件（不污染开发库）。"""
import asyncio
import os
import sys
import tempfile

_tmp = tempfile.mkdtemp(prefix="sysmods_mcp_test_")
os.environ["SYSMODS_DB"] = os.path.join(_tmp, "test.db")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.api import db
db.DB_PATH = os.environ["SYSMODS_DB"]
db.init_db()

import pytest

from services import mcp_server as mc
from services.api.db import Ledger, register_user

PHONE = "13800000001"
TOKEN = None


def _ledger_rows():
    con = db.connect()
    try:
        return len(con.execute("SELECT * FROM ledger WHERE phone=?", (PHONE,)).fetchall())
    finally:
        con.close()


@pytest.fixture(scope="module", autouse=True)
def fresh_user():
    global TOKEN
    assert register_user(PHONE, "000000")
    TOKEN = db.issue_token(PHONE)
    yield


class TestEnvelopeAuth:
    def test_unauthorized_token_rejected(self):
        r = mc.create_project(PHONE, "bad-token", "哨站离网供电")
        assert r["ok"] is False and r["error"]["code"] == "UNAUTHORIZED"

    def test_create_project_envelope(self):
        r = mc.create_project(PHONE, TOKEN, "哨站离网供电：光伏 30kW、保供 99%")
        assert r["ok"] is True
        assert r["session_id"].startswith("S")
        assert r["state"] == "G1_PENDING"
        card = r["data"]["param_card"]
        assert card["scenario"] and card["template"] in ("T1", "T6")
        assert card["questions"]                 # 首问清单非空
        assert r["usage_ref"] == r["session_id"]


class TestSubmitAnswer:
    def test_invalid_value_not_written(self):
        r0 = mc.create_project(PHONE, TOKEN, "哨站离网供电")
        sid = r0["session_id"]
        # bess.eff_roundtrip 合法范围 [0.8, 1.0]，1.5 越界
        r = mc.submit_requirement_answer(sid, PHONE, TOKEN, {"bess.eff_roundtrip": 1.5})
        assert r["ok"] is False
        assert r["error"]["code"] == "INVALID_PARAM"
        assert r["error"]["retryable"] is False
        # 非法值未写入：默认值仍在、状态与 version 不变
        g = mc.get_param_card(sid, PHONE, TOKEN)
        assert g["ok"] is True
        assert g["data"]["version"] == 0
        assert g["state"] == "G1_PENDING"
        assert abs(g["data"]["param_card"]["params"]["bess.eff_roundtrip"] - 0.90) < 1e-9

    def test_valid_submit_and_version_conflict(self):
        r0 = mc.create_project(PHONE, TOKEN, "哨站离网供电")
        sid = r0["session_id"]
        r = mc.submit_requirement_answer(sid, PHONE, TOKEN, {"pv.capacity_kw": 60},
                                         expected_version=0)
        assert r["ok"] is True and r["data"]["version"] == 1
        # 过期 version → 409 语义
        r2 = mc.submit_requirement_answer(sid, PHONE, TOKEN, {"pv.capacity_kw": 80},
                                          expected_version=0)
        assert r2["ok"] is False
        assert r2["error"]["code"] == "VERSION_CONFLICT"
        assert r2["error"]["retryable"] is True


class TestRunIdempotent:
    def test_run_charge_once_per_idempotency_key(self):
        r0 = mc.create_project(PHONE, TOKEN, "哨站离网供电：光伏 50kW、锂电 200kWh")
        sid = r0["session_id"]
        mc.submit_requirement_answer(sid, PHONE, TOKEN, {"pv.capacity_kw": 60})
        rows0 = _ledger_rows()
        r = mc.run_simulation(sid, PHONE, TOKEN, idempotency_key="k1")
        assert r["ok"] is True
        assert r["state"] in ("G4_PENDING", "G3_PENDING")
        rows1 = _ledger_rows()
        assert rows1 >= rows0                    # 计费落账（免费额度覆盖时 delta=0 也留行）
        # 重试同 key：同一响应，不重复扣费
        r2 = mc.run_simulation(sid, PHONE, TOKEN, idempotency_key="k1")
        assert r2 == r
        assert _ledger_rows() == rows1

    def test_get_param_card_readonly(self):
        r0 = mc.create_project(PHONE, TOKEN, "哨站离网供电")
        sid = r0["session_id"]
        rows0 = _ledger_rows()
        g1 = mc.get_param_card(sid, PHONE, TOKEN)
        g2 = mc.get_param_card(sid, PHONE, TOKEN)
        assert g1["ok"] is True and g2["ok"] is True
        assert g1["data"]["version"] == g2["data"]["version"] == 0
        assert _ledger_rows() == rows0          # 只读不计费
        assert g2["state"] == "G1_PENDING"      # 无状态迁移


class TestStdioProtocol:
    def test_stdio_lists_four_tools(self):
        """DSH mcp-client 接入面冒烟：spawn 本 server（stdio）→ 握手 → 四工具可见。"""
        root = os.path.join(os.path.dirname(__file__), "..")

        async def _probe():
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
            params = StdioServerParameters(
                command=sys.executable, args=["-m", "services.mcp_server"], cwd=root)
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    return {t.name for t in tools.tools}

        names = asyncio.run(_probe())
        assert {"create_project", "submit_requirement_answer",
                "run_simulation", "get_param_card"} <= names
