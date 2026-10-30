# -*- coding: utf-8 -*-
"""盲区补偿 Agent（V1.2 增补5 决策："Agent 在模型没估计到的方面有很强能力"）。

模型覆盖的是物理与经济量化；以下因素在仿真边界之外，由 Agent 以"外挂建议卡"
呈现（C 级先验 + 影响方向 + 建议人工确认点）。LLM 联网检索接入后，静态卡升级为
实时检索卡（裁决链 §1.3.1：①实测→②市场→③文献→④通用，禁止跳级）。
"""
from .base import BaseAgent

GAP_CARDS = [
    {"topic": "碳市场政策", "covered_by_model": "部分（碳价参数）",
     "impact": "全国碳市场扩容节奏影响减碳收益现值；CCER 签发周期影响变现时间",
     "advice": "确认项目是否纳入履约主体；CCER 方法学适用性人工核验",
     "source": "静态卡（LLM 联网后实时化）", "level": "C2"},
    {"topic": "绿证/绿电溢价", "covered_by_model": "未覆盖",
     "impact": "绿证交易或绿电直连的溢价/核销影响度电收入与绿色属性认定",
     "advice": "按省核绿电交易政策；绿证与碳市场不重复计算（口径确认）",
     "source": "静态卡", "level": "C2"},
    {"topic": "水资源", "covered_by_model": "未覆盖",
     "impact": "吨氢耗水 ~10L（含冷却与纯水制备 ~20L）；西北项目水指标是硬约束",
     "advice": "确认水权指标与废水处置；缺水地区影响选址",
     "source": "静态卡", "level": "C1"},
    {"topic": "氢安全距离", "covered_by_model": "部分（标准库首批规则）",
     "impact": "GB 50177/GB 50516 对站界间距要求影响土地与总图；固态低压可显著缩短",
     "advice": "总图阶段由注册工程师按强条核验",
     "source": "静态卡+标准库", "level": "C1"},
    {"topic": "氢储运半径", "covered_by_model": "未覆盖（分布式就地消纳默认）",
     "impact": "若需外售，20MPa 长管拖车 ~200km 经济半径外成本陡增",
     "advice": "明确消纳协议；分布式场景外售仅在半径内核算",
     "source": "静态卡", "level": "C1"},
    {"topic": "审批与补贴", "covered_by_model": "未覆盖",
     "impact": "能评/环评/氢危化品许可周期影响时间表；地方制氢补贴（如内蒙/吉陇）改变 LCOH",
     "advice": "属地政策清单人工确认；补贴按保守口径不入基准经济",
     "source": "静态卡", "level": "C2"},
]


class GapAgent(BaseAgent):
    name = "knowledge_gaps"
    skills = ["盲区识别", "外挂建议卡", "影响方向评估"]

    def __init__(self, runtime=None):
        super().__init__(runtime)
        self.domain_kb = {c["topic"]: c for c in GAP_CARDS}

    def report(self, scenario: str) -> dict:
        """输出场景相关的盲区卡（绿氨场景额外加氨储运/危化品卡）。"""
        cards = list(GAP_CARDS)
        if "氨" in scenario:
            cards.append({"topic": "氨储运与危化品", "covered_by_model": "未覆盖",
                          "impact": "液氨属危化品——储罐间距/道路运输许可影响总图与许可周期",
                          "advice": "氨罐区按 GB 18218 重大危险源辨识；运输半径人工核验",
                          "source": "静态卡", "level": "C1"})
        return {"scenario": scenario, "cards": cards,
                "note": "以上因素在仿真边界外——影响方向已标注，数值须人工确认后回填（转 C 级先验）"}
