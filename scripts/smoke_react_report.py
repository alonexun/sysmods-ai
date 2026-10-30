# -*- coding: utf-8 -*-
"""React 前端 + 报告数据（Recall）+ 导出 HTML 的端到端冒烟。"""
import glob
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ["SYSMODS_DB"] = os.path.join(tempfile.mkdtemp(), "smoke.db")

from services.api import db
db.DB_PATH = os.environ["SYSMODS_DB"]
from fastapi.testclient import TestClient
from services.api.main import app
db.init_db()
c = TestClient(app)

# 1) React 页面与静态资源
r = c.get("/")
assert r.status_code == 200 and 'id="root"' in r.text, "index"
css = glob.glob("apps/web/dist/assets/*.css")[0].split("dist")[1].replace("\\", "/")
r = c.get(css)
assert r.status_code == 200 and len(r.text) > 5000, "css assets"

# 2) 全流程到 G5 + report_data（Recall 验证）
j = c.post("/auth/register", json={"phone": "13911112222"}).json()
h = {"X-Token": j["token"]}
s = c.post("/session", json={"phone": "13911112222",
    "description": "内蒙古风光绿氨项目 合成氨每小时 0.8 吨 光伏 900 千瓦"},
    headers=h).json()
sid = s["sid"]
c.post(f"/session/{sid}/g1", json={"phone": "13911112222", "overrides": {
    "pv.capacity_kw": 900.0, "chem.nh3.capacity_t_per_h": 0.8,
    "h2store.capacity_kg": 5000.0, "h2store.level_init_kg": 2500.0,
    "wind.capacity_kw": 1200.0, "pemwe.rated_kw": 700.0}}, headers=h)
r = c.post(f"/session/{sid}/run", json={"phone": "13911112222"}, headers=h)
assert r.json()["state"] == "G4_PENDING", r.text

# 线下打款→线上加积分（报告导出固定费 200 超出免费额度——商业闭环演示）
from services.api.db import Ledger
con = db.connect()
Ledger(con).grant("13911112222", 500, reason="线下打款(冒烟)", ref="TX-SMOKE")
con.close()

r = c.post(f"/session/{sid}/g5", json={"phone": "13911112222"}, headers=h)
assert r.status_code == 200, r.text
rd = c.get(f"/session/{sid}/report_data", headers=h).json()
assert "内蒙古" in rd["recall"]["goal"] and "绿氨" in rd["recall"]["goal"]
cnp = [p["canonical"] for p in rd["recall"]["client_params"]]
assert "pv.capacity_kw" in cnp and "chem.nh3.capacity_t_per_h" in cnp
assert any("光伏" in p["cn"] for p in rd["recall"]["client_params"])
assert rd["diagram_svg"].startswith("<svg")
assert len(rd["kpi_cards"]) == 4
rep = c.get(f"/report/{sid}")
assert "需求回顾" in rep.text and "Requirements Recall" in rep.text
print("SMOKE OK: react=/ · assets=/ · report_data(recall+svg+kpi) · export-html(recall)")
print("react report url: #/report/" + sid)
