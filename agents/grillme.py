# -*- coding: utf-8 -*-
"""需求分析 Agent（grillme）：把模糊项目目标变成参数卡（A/B/C 分级 + 追问）。

Phase 1 规则版：
- 场景识别（哨站/加氢站/绿氨/绿醇/氢冶金）→ 模板与追问清单
- 参数卡预填（canonical 注册表默认值 + 场景覆盖）
- 完整性评分（必需参数的 A/B 级占比）
LLM 接入后：自然语言抽取 + 智能追问替换关键词规则；输出契约不变。
"""
from kernel.hyflow.registry import load_registry
from .base import BaseAgent

SCENARIOS = {
    "哨站/离网": {"keys": ["哨站", "边防", "离网", "边境", "无电"],
                "template": "T1", "required": ["pv.capacity_kw", "load.avg_kw", "bess.capacity_kwh"]},
    "加氢/补能": {"keys": ["加氢", "补能", "加注", "叉车", "无人机"],
                "template": "T2", "required": ["pv.capacity_kw", "pemwe.rated_kw", "h2store.capacity_kg"]},
    "绿氨": {"keys": ["绿氨", "合成氨", "氨", "haber", "nh3"],
             "template": "T6", "required": ["chem.nh3.capacity_t_per_h", "wind.capacity_kw", "h2store.capacity_kg"]},
    "绿醇": {"keys": ["甲醇", "绿醇", "meoh"],
             "template": "T6-醇(后续)", "required": ["chem.meoh.h2_per_t_kg"]},
    "氢冶金": {"keys": ["冶金", "钢铁", "dri", "还原铁", "高炉"],
               "template": "T6-DRI(后续)", "required": ["chem.dri.h2_per_t_fe_kg"]},
}

# grillme 专属 KB：追问与场景的分布式考量（V1.2 §1.3 分布式中心）
QUESTIONS = {
    "common": [
        "项目地点/纬度（影响辐照与温度修正）",
        "平均电负荷与昼夜特性（保供率要求 %？）",
        "项目寿命与贴现率（可研口径）",
    ],
    "T6": [
        "合成氨年产量目标（t/a）或装置规模（t/h）？",
        "电网条件：绿电直连专线容量？分时电价/现货可参与？",
        "储氢缓冲可接受规模（决定 HB 稳定性 vs 投资）",
        "绿氨消纳：长协价或市场价口径？",
    ],
    "T1": [
        "冬季连续阴天续航要求（自主天数）？",
        "氢应用：发电/加注/无人机——负荷曲线差异大",
    ],
}


class GrillmeAgent(BaseAgent):
    name = "grillme"
    skills = ["场景识别", "参数卡预填", "完整性评分", "追问生成"]

    def __init__(self, runtime=None):
        super().__init__(runtime)
        self.domain_kb = {k: v["keys"] for k, v in SCENARIOS.items()}
        self._reg = load_registry()

    def detect_scenario(self, text: str) -> str:
        t = text.lower()
        best, score = "哨站/离网", 0
        for name, sc in SCENARIOS.items():
            s = sum(1 for k in sc["keys"] if k in t)
            if s > score:
                best, score = name, s
        return best

    def build_param_card(self, text: str, overrides: dict = None,
                         use_llm: bool = False) -> dict:
        """生成参数卡：canonical 值 + 分级 + 完整性。G1 门确认对象。

        use_llm=True 时走 LLM 抽取（输出过注册表 validate 守门），失败自动降级规则版
        （V1.2 §5.8 降级运行——参数卡标注 llm_mode 状态）。
        """
        scenario = self.detect_scenario(text)
        sc = SCENARIOS[scenario]
        self._extra_questions = []       # 重置 LLM 追问状态（修复跨调用残留）
        d = dict(self._reg.defaults())
        levels = {k: s.level for k, s in self._reg.specs.items()}
        if overrides:
            for k, v in overrides.items():
                self._reg.validate(k, v)
                d[k] = float(v)
                levels[k] = "A"      # 客户提供的值按 A 级声明（仍过输入校验 §7.11）
        llm_mode = "off"
        llm_note = ""
        if use_llm and self.runtime.llm_client is not None:
            try:
                card = self._llm_extract(text, scenario)
                llm_mode = "llm"
                if card.get("invalid"):
                    llm_note = ("LLM 抽取中 "
                                f"{len(card['invalid'])} 项未通过参数校验已丢弃（"
                                + "; ".join(card["invalid"][:3]) + "）")
                for k, v in card["params"].items():
                    if k in d:
                        d[k] = v
                        levels[k] = "A"   # 客户文本中抽取的显式数值 → A 级（仍过 §7.11）
                if card.get("questions"):
                    self._extra_questions = card["questions"]
            except Exception as e:
                llm_mode = "degraded"
                llm_note = f"LLM 抽取不可用，已按规则模式生成（原因: {type(e).__name__}）"
        required = sc["required"]
        have = [k for k in required if levels.get(k, "").startswith(("A", "B"))]
        completeness = len(have) / len(required) if required else 1.0
        questions = QUESTIONS.get(sc["template"].split("(")[0].rstrip("-"), QUESTIONS["common"]) \
            + QUESTIONS["common"]
        extra_q = getattr(self, "_extra_questions", [])
        return {
            "scenario": scenario, "template": sc["template"],
            "completeness": round(completeness, 3),
            "params": d, "levels": levels,
            "required": required,
            "questions": list(dict.fromkeys(questions + list(extra_q))),
            "kb_note": "规则版场景识别；LLM 接入后支持自由语言抽取",
            "llm_mode": llm_mode, "llm_note": llm_note,
        }

    # ---------------- LLM 抽取（输出守门：注册表 validate，黑层不进 prompt） ----------------
    _LLM_SYSTEM = (
        "你是氢能系统工程的需求分析助手。从用户的自然语言项目描述中抽取仿真参数。"
        "只允许输出 JSON 对象，格式：{"
        "\"scenario_hint\": \"哨站/加氢/绿氨/绿醇/氢冶金 之一\", "
        "\"params\": {\"<canonical参数名>\": <数值>}, "
        "\"questions\": [\"针对缺失关键信息的追问，最多3条\"], "
        "\"note\": \"一句话总结\"}。"
        "规则：1) 只抽取用户文本中明确给出的数值，单位换算到参数要求；"
        "2) 不确定的参数不要猜；3) 物理数值不由你计算，你只做抽取。")

    def _llm_extract(self, text: str, scenario_hint: str) -> dict:
        from services.api.llm import extract_json
        # 白层参数清单进 prompt（名称+单位+范围——不含任何内部标定/报价）
        schema_lines = [f"- {name}（{s.unit}，范围 {s.range[0]}~{s.range[1]}）"
                        for name, s in sorted(self._reg.specs.items())]
        user = (f"已知场景识别（规则引擎）：{scenario_hint}\n"
                f"可选参数白名单：\n" + "\n".join(schema_lines) +
                f"\n\n用户项目描述：\n{text}")
        raw = self.runtime.call_llm(self._LLM_SYSTEM, user)
        data = extract_json(raw)
        params, invalid = {}, []
        for k, v in (data.get("params") or {}).items():
            try:
                self._reg.validate(k, v)
                params[k] = float(v)
            except (KeyError, ValueError) as e:
                invalid.append(f"{k}={v!r}({type(e).__name__})")
        return {"params": params, "invalid": invalid,
                "questions": [str(q) for q in (data.get("questions") or [])][:3],
                "note": str(data.get("note", ""))}
