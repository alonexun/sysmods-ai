# -*- coding: utf-8 -*-
"""Agent 知识库统一加载器：按 kb_registry.json 校验文件存在性、读取内容、输出版本清单。

设计：KB 是一等产品资产（V1.2 增补 5/6——每个 Agent=模型+prompt+专属 KB+skills）。
- load_agent_kb(agent) → {"kb": {路径: 文本}, "skills": {...}, "version": ...}
- kb_manifest() → 各 Agent 的 KB 版本与文件哈希（进交付物 manifest，可复现）。
"""
import hashlib
import json
import os
from typing import Dict

_AGENTS_DIR = os.path.dirname(os.path.abspath(__file__))


def _registry_path() -> str:
    return os.path.join(_AGENTS_DIR, "kb_registry.json")


def load_registry() -> Dict:
    with open(_registry_path(), "r", encoding="utf-8") as f:
        return json.load(f)


def load_agent_kb(agent: str) -> Dict:
    reg = load_registry()
    if agent not in reg["agents"]:
        raise KeyError(f"未注册 Agent KB: {agent}")
    meta = reg["agents"][agent]
    out = {"kb": {}, "skills": {}, "version": meta.get("version"),
           "external_sources": meta.get("external_sources", [])}
    for kind in ("kb", "skills"):
        for rel in meta.get(kind, []):
            path = os.path.join(_AGENTS_DIR, rel)
            if not os.path.isfile(path):
                raise FileNotFoundError(f"KB 文件缺失: {rel}（Agent {agent}）")
            with open(path, "r", encoding="utf-8") as f:
                out[kind][rel] = f.read()
    return out


def kb_manifest() -> Dict[str, Dict]:
    """各 Agent 的 KB 版本与文件 sha256（截断 12 位）——可复现性证据。"""
    reg = load_registry()
    manifest = {}
    for agent, meta in reg["agents"].items():
        files = list(meta.get("kb", [])) + list(meta.get("skills", []))
        hashes = {}
        for rel in files:
            path = os.path.join(_AGENTS_DIR, rel)
            if os.path.isfile(path):
                with open(path, "rb") as f:
                    hashes[rel] = hashlib.sha256(f.read()).hexdigest()[:12]
        manifest[agent] = {"version": meta.get("version"), "files": hashes}
    return manifest


def design_tokens() -> str:
    """交付物/前端共用的设计 tokens 文本（唯一视觉事实源）。"""
    return load_agent_kb("deliverable")["kb"][
        "deliverable/kb/report_design_tokens.md"]
