# -*- coding: utf-8 -*-
"""工作台/报告桌面与移动端视觉检查。用法：python scripts/ui_visual_check.py [输出前缀]"""
import os
import sys
from playwright.sync_api import sync_playwright

BASE = os.environ.get("SYSMODS_UI_BASE", "http://127.0.0.1:8765")
SID = os.environ.get("SYSMODS_DEMO_SID", "S1792919443538")
PREFIX = sys.argv[1] if len(sys.argv) > 1 else "before"
OUT = os.path.join(os.path.dirname(__file__), "..", "output", "ui_review")
os.makedirs(OUT, exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
    errors = []
    page.on("console", lambda msg: errors.append(f"console:{msg.type}:{msg.text}") if msg.type == "error" else None)
    page.on("pageerror", lambda exc: errors.append(f"pageerror:{exc}"))
    for name, url in [("workbench", f"{BASE}/#/"), ("report", f"{BASE}/#/report/{SID}")]:
        page.goto(url, wait_until="networkidle")
        page.reload(wait_until="networkidle")  # hash 路由：确保按目标 URL 完整挂载
        page.screenshot(path=os.path.join(OUT, f"{PREFIX}_{name}_desktop.png"), full_page=True)
        print(name, "title=", page.title(), "body=", len(page.locator("body").inner_text()))
        if name == "report":
            print("device_cards=", page.locator(".devc").count(), "sections=", page.locator(".sec").count())
    page.set_viewport_size({"width": 390, "height": 844})
    for name, url in [("workbench", f"{BASE}/#/"), ("report", f"{BASE}/#/report/{SID}")]:
        page.goto(url, wait_until="networkidle")
        page.reload(wait_until="networkidle")
        page.screenshot(path=os.path.join(OUT, f"{PREFIX}_{name}_mobile.png"), full_page=True)
        print(name, "mobile_scroll_width=", page.evaluate("document.documentElement.scrollWidth"))
    print("errors=", errors)
    browser.close()
print("screenshots:", os.path.abspath(OUT))
