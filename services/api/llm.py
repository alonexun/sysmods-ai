# -*- coding: utf-8 -*-
"""LLM 网关：DeepSeek API（OpenAI 兼容）真实接入 + Mock 离线回退。

- 配置：环境变量 DEEPSEEK_API_KEY（必填才真实调用）、DEEPSEEK_BASE_URL（默认官方）、
  DEEPSEEK_MODEL（默认 deepseek-chat）。
- 纪律（V1.2 §8.5/铁律）：LLM 只做抽取/建议/叙述——输出必须经 JSON 解析 +
  canonical 注册表 validate 才能进参数卡；黑层资产不进 prompt。
- MockLLM：固定/回调响应，供测试与无 key 降级（降级显式标注，V1.2 §5.8）。
- tokens 计量：每次调用记录 usage，供积分双重计量（0.5 积分/万 tokens）。
"""
import json
import os
import time
import urllib.request
import urllib.error
from typing import Callable, Dict, List, Optional


class LLMError(RuntimeError):
    pass


class LLMNotConfiguredError(LLMError):
    pass


class LLMUsage:
    def __init__(self):
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.calls = 0

    def add(self, p: int, c: int):
        self.prompt_tokens += p
        self.completion_tokens += c
        self.calls += 1

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def chargeable_credits(self, rate_per_10k: float = 0.5) -> int:
        """可计费积分（不足 1 不计——小额豁免）。"""
        import math
        return math.floor(self.total_tokens / 10000.0 * rate_per_10k)


class LLMGateway:
    """DeepSeek / OpenAI 兼容网关（无 SDK 依赖，urllib 直调）。"""

    def __init__(self, api_key: Optional[str] = None, base_url: str = None,
                 model: str = None, timeout: int = 60, max_retries: int = 2):
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY", "")
        self.base_url = (base_url or os.environ.get("DEEPSEEK_BASE_URL")
                         or "https://api.deepseek.com").rstrip("/")
        self.model = model or os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
        self.timeout = timeout
        self.max_retries = max_retries
        self.usage = LLMUsage()

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def chat(self, system: str, user: str, json_mode: bool = False,
             temperature: float = 0.3) -> str:
        if not self.configured:
            raise LLMNotConfiguredError(
                "DEEPSEEK_API_KEY 未配置——请设置环境变量或注入 MockLLM（服务以规则模式降级运行）")
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system},
                          {"role": "user", "content": user}],
            "temperature": temperature,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        body = json.dumps(payload).encode("utf-8")
        last_err = None
        for attempt in range(self.max_retries + 1):
            req = urllib.request.Request(
                self.base_url + "/chat/completions", data=body,
                headers={"Content-Type": "application/json",
                         "Authorization": "Bearer " + self.api_key})
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                u = data.get("usage", {})
                self.usage.add(int(u.get("prompt_tokens", 0)),
                               int(u.get("completion_tokens", 0)))
                return data["choices"][0]["message"]["content"]
            except urllib.error.URLError as e:
                last_err = e
                time.sleep(1.5 * (attempt + 1))   # 网络重试退避
            except (KeyError, json.JSONDecodeError) as e:
                raise LLMError(f"LLM 响应解析失败: {e}")
        raise LLMError(f"LLM 调用失败（重试 {self.max_retries} 次后）: {last_err}")


class MockLLM:
    """离线 Mock：按 (system, user) 关键词路由预设响应；未命中回退 default_response。

    测试用：注入确定性 JSON；无 key 环境的降级路径也用它验证全链路。
    """

    def __init__(self, routes: Optional[Dict[str, str]] = None,
                 default_response: str = "{}",
                 responder: Optional[Callable[[str, str], str]] = None):
        self.routes = routes or {}
        self.default_response = default_response
        self.responder = responder
        self.usage = LLMUsage()
        self.calls: List[Dict[str, str]] = []

    def chat(self, system: str, user: str, json_mode: bool = False,
             temperature: float = 0.3) -> str:
        self.usage.add(len(system) // 4, len(user) // 4)   # 粗略 token 估算
        self.calls.append({"system": system, "user": user})
        if self.responder:
            return self.responder(system, user)
        for key, resp in self.routes.items():
            if key in user or key in system:
                return resp
        return self.default_response


def extract_json(text: str) -> dict:
    """LLM 输出 → JSON dict（容错：剥 markdown 代码块围栏）。"""
    s = text.strip()
    if s.startswith("```"):
        s = s.split("```")[1]
        if s.startswith("json"):
            s = s[4:]
    try:
        return json.loads(s)
    except json.JSONDecodeError as e:
        raise LLMError(f"LLM 输出不是合法 JSON: {e}；原文开头: {s[:120]}")
