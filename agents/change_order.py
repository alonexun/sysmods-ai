# -*- coding: utf-8 -*-
"""变更单解析器：自由文本 → 结构化变更单 → 回显确认（唯一合法修改通道，V1.2 §7.3）。

规则版：数值修改的语义模式匹配（"把 X 改成/调到 Y"）；canonical 参数通过
注册表别名匹配（含中文名映射——导入边界内的唯一别名集）。LLM 接入后由模型
抽取，回显确认机制不变。
"""
import re
from kernel.hyflow.registry import load_registry
from .base import BaseAgent

# canonical 中文名映射（导入边界别名——内核仍用 canonical 名，铁律2）
ALIASES = {
    "电解槽": "pemwe.rated_kw", "电解": "pemwe.rated_kw", "pem": "pemwe.rated_kw",
    "光伏": "pv.capacity_kw", "光伏容量": "pv.capacity_kw", "装机": "pv.capacity_kw",
    "风电": "wind.capacity_kw", "风机": "wind.capacity_kw",
    "储能": "bess.capacity_kwh", "锂电": "bess.capacity_kwh", "电池": "bess.capacity_kwh",
    "储氢": "h2store.capacity_kg", "氢罐": "h2store.capacity_kg",
    "合成氨": "chem.nh3.capacity_t_per_h", "氨产量": "chem.nh3.capacity_t_per_h",
    "燃料电池": "fc.rated_kw",
    "负荷": "load.avg_kw",
}

_NUM = r"([0-9]+(?:\.[0-9]+)?)\s*(kw|千瓦|kwh|kwh|kg|吨|t|a|年|mwh|万)?"


class ChangeOrderError(ValueError):
    pass


class ChangeOrderAgent(BaseAgent):
    name = "change_order"
    skills = ["文本→结构化变更单", "回显确认", "低置信转 grillme 追问"]

    def __init__(self, runtime=None):
        super().__init__(runtime)
        self.domain_kb = {"aliases": ALIASES}
        self._reg = load_registry()

    def parse(self, text: str, use_llm: bool = False) -> dict:
        """解析评论 → 变更单（类型=参数变更）。
        无法解析时返回 {'need_clarification': True}（转 grillme 式追问，不猜）。
        use_llm=True 时优先 LLM 抽取（输出过注册表 validate 守门），失败降级规则版。"""
        if use_llm and self.runtime.llm_client is not None:
            try:
                order = self._llm_parse(text)
                if order is not None:
                    return order
                return {"need_clarification": True,
                        "msg": "LLM 未能从评论中识别出参数变更——请指明设备与目标值"}
            except Exception as e:
                # 降级规则版（标注）
                order = self._rule_parse(text)
                if order and not order.get("need_clarification"):
                    order["llm_mode"] = "degraded"
                    order["llm_note"] = f"LLM 解析不可用，已用规则引擎（{type(e).__name__}）"
                return order
        return self._rule_parse(text)

    # ---------------- LLM 解析（守门：JSON + 注册表 validate） ----------------
    _LLM_SYSTEM = (
        "你是工程方案的变更单解析器。把客户审阅评论解析为参数变更。"
        "只允许输出 JSON：{\"param\": \"<canonical参数名>\", \"new_value\": <数值>, "
        "\"confidence\": <0~1>}。若评论不包含参数修改意图（纯提问/确认/抱怨），"
        "输出 {\"param\": null}。禁止猜测数值，禁止修改非白名单参数。")

    def _llm_parse(self, text: str):
        from services.api.llm import extract_json
        schema_lines = [f"- {name}（{s.unit}，{s.desc}）"
                        for name, s in sorted(self._reg.specs.items())]
        user = ("可变更参数白名单：\n" + "\n".join(schema_lines) +
                f"\n\n客户评论：\n{text}")
        raw = self.runtime.call_llm(self._LLM_SYSTEM, user)
        data = extract_json(raw)
        if not data.get("param"):
            return None
        p, v = data["param"], data.get("new_value")
        spec = self._reg.spec(p)          # 不在注册表 → KeyError → 外层降级
        self._reg.validate(p, v)
        conf = float(data.get("confidence", 0.9))
        order = {
            "type": "param_change", "param": p, "new_value": float(v),
            "unit": spec.unit, "original_text": text,
            "echo": f"变更单：将 {p}（{spec.desc}）设为 {float(v)} {spec.unit}。确认执行？",
            "confirmed": False, "llm_mode": "llm", "llm_confidence": conf,
        }
        if conf < 0.5:
            order["echo"] += "（低置信解析——请仔细核对）"
        return order

    # ---------------- 规则版解析（原逻辑保留） ----------------
    def _rule_parse(self, text: str) -> dict:
        t = text.lower().replace("，", ",").replace(" ", "")
        # 别名匹配
        hit_param = None
        for alias, canon in ALIASES.items():
            if alias in t:
                hit_param = canon
                break
        if hit_param is None:
            return {"need_clarification": True,
                    "msg": "未识别要修改的参数——请指明设备（电解槽/光伏/储能/储氢/合成氨…）"}
        nums = re.findall(_NUM, t)
        if not nums:
            return {"need_clarification": True,
                    "msg": f"识别到参数[{hit_param}]但未找到新值——请给出目标数值与单位"}
        val = float(nums[-1][0])
        spec = self._reg.spec(hit_param)
        try:
            self._reg.validate(hit_param, val)
        except ValueError as e:
            return {"need_clarification": True,
                    "msg": f"建议值越界：{e}——请复核口径（单位应为 {spec.unit}）"}
        return {
            "type": "param_change", "param": hit_param, "new_value": val,
            "unit": spec.unit, "original_text": text,
            "echo": f"变更单：将 {hit_param}（{spec.desc}）设为 {val} {spec.unit}。确认执行？",
            "confirmed": False, "llm_mode": "rule",
        }

    def apply(self, order: dict, params: dict) -> dict:
        """确认后的变更单应用到参数卡（副本，非原地）。"""
        if order.get("type") != "param_change" or not order.get("confirmed"):
            raise ChangeOrderError("变更单未确认——禁止执行（唯一合法修改通道）")
        p = dict(params)
        p[order["param"]] = float(order["new_value"])
        return p
