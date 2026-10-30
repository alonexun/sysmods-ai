# -*- coding: utf-8 -*-
"""生成一份持久化的演示报告会话（开发库），供浏览器查看 React 报告与导出 HTML。

运行后输出两个可点击地址（需 uvicorn 已在 8000 端口运行，或自行替换端口）。
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient
from services.api import db
from services.api.main import app
from services.api.db import Ledger

db.init_db()
c = TestClient(app)
PHONE = "13800009999"

r = c.post("/auth/register", json={"phone": PHONE})
token = r.json()["token"]
h = {"X-Token": token}

# 线下打款→线上加积分（报告导出固定费演示）
con = db.connect()
Ledger(con).grant(PHONE, 500, reason="线下打款(演示)", ref="TX-DEMO")
con.close()

DESC = ("内蒙古风光绿氨示范项目：风电 1500kW + 光伏 800kW，PEM 700kW 电解，"
        "储氢 5000kg 缓冲，合成氨装置 0.8 吨/小时，目标全年高负荷稳定产氨。")
s = c.post("/session", json={"phone": PHONE, "description": DESC}, headers=h).json()
sid = s["sid"]
print("会话:", sid, "| 场景:", s["param_card"]["scenario"])

c.post(f"/session/{sid}/g1", json={"phone": PHONE, "overrides": {
    "pv.capacity_kw": 800.0, "wind.capacity_kw": 1500.0,
    "pemwe.rated_kw": 700.0, "alk.rated_kw": 300.0,
    "h2store.capacity_kg": 5000.0, "h2store.level_init_kg": 2500.0,
    "chem.nh3.capacity_t_per_h": 0.8}}, headers=h)

r = c.post(f"/session/{sid}/run", json={"phone": PHONE}, headers=h)
assert r.json()["state"] == "G4_PENDING", r.text

# 容量优化（穷举示例）
r = c.post(f"/session/{sid}/optimize", json={"phone": PHONE,
    "candidates": {"pemwe.rated_kw": [400.0, 700.0, 1000.0],
                   "h2store.capacity_kg": [2500.0, 5000.0, 8000.0]},
    "n_days": 30, "refine_days": 60}, headers=h)
print("优化组合:", r.json()["n_combinations"], "可行:", r.json()["n_feasible"])

r = c.post(f"/session/{sid}/g5", json={"phone": PHONE}, headers=h)
assert r.status_code == 200, r.text
print()
print("=" * 62)
print("演示报告已生成（开发库持久化，服务重启不丢）")
print(f"  React 交互式报告 : http://127.0.0.1:8000/#/report/{sid}")
print(f"  自包含 HTML 导出  : http://127.0.0.1:8000/report/{sid}")
print(f"  系统架构 SVG      : http://127.0.0.1:8000/session/{sid}/diagram")
print(f"  文件路径           : output/reports/{sid}.html")
print("=" * 62)
print("本地另有静态演示文件: output/reports/demo_v3.html（多路线并联版）")
