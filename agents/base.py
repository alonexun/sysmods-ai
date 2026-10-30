# -*- coding: utf-8 -*-
"""Agent 基础协议与运行时（V1.2 §7.9：每个 Agent = 模型 + 专属KB + skills + 验收测试）。

Phase 1 为规则引擎实现（确定性、可测试）；LLM 注入点为 AgentRuntime.llm_client——
接入 DeepSeek API 时替换该对象，结构化输出接口不变。
"""
from typing import Callable, Optional, Protocol


class LLMClient(Protocol):
    """LLM 网关协议（OpenAI 兼容）。Phase 1 用规则版，不实现网络调用。"""

    def chat(self, system: str, user: str) -> str: ...


class RuleLLM:
    """规则占位：直接抛错——规则 Agent 不应请求 LLM。"""

    def chat(self, system: str, user: str) -> str:
        raise NotImplementedError("Phase 1 规则模式不调用 LLM；接入 DeepSeek 时替换本对象")


class AgentRuntime:
    def __init__(self, llm_client: Optional[LLMClient] = None,
                 model_name: str = "deepseek-chat（未接入）"):
        self.llm_client = llm_client or RuleLLM()
        self.model_name = model_name

    def call_llm(self, system: str, user: str) -> str:
        return self.llm_client.chat(system, user)


class BaseAgent:
    name: str = "base"
    domain_kb: dict = {}
    skills: list = []

    def __init__(self, runtime: AgentRuntime = None):
        self.runtime = runtime or AgentRuntime()

    def summary(self) -> str:
        kb_n = len(self.domain_kb)
        return f"[{self.name}] kb={kb_n} skills={len(self.skills)}"
