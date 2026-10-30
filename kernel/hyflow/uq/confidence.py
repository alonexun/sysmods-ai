# -*- coding: utf-8 -*-
"""置信度引擎 v0（V1.2 §5.7）——四维短板评级。

确定性规则计算，非 LLM 打分。综合等级 = min(四维)，禁止高等级单项拉高。
与 UQ 区间正交：UQ 量化参数不确定（P50/P90），置信度量化模型与数据可信度。
"""
from dataclasses import dataclass

# 等级字典序 A>B>C>D
_GRADE_ORDER = {"A": 0, "B": 1, "C": 2, "D": 3}
_GRADES = ["A", "B", "C", "D"]


@dataclass
class ConfidenceInput:
    data_level: str          # 关键参数最差等级 A/B/C
    model_level: str         # L1(权威库)/L2(移植)/L3(简化)
    verified: str            # 'T3实测' / 'T2文献' / '自证' / '未验证'
    cons_passed: bool        # 守恒审计是否通过


@dataclass
class Confidence:
    grade: str
    attribution: str          # 短板归因
    improvement: str          # 提升路径


def _idx(grade: str) -> int:
    return _GRADE_ORDER[grade]


def assess(ci: ConfidenceInput) -> Confidence:
    # 维度1 数据
    if ci.data_level in ("A", "B"):
        g_data = ci.data_level
    else:
        g_data = "C"
    # 维度2 模型
    g_model = {"L1": "A", "L2": "B", "L3": "C"}.get(ci.model_level, "D")
    # 维度3 验证
    g_verify = {"T3实测": "A", "T2文献": "B", "自证": "C"}.get(ci.verified, "D")
    # 维度4 数值健康（守恒）
    g_cons = "A" if ci.cons_passed else "D"

    dims = {"数据": g_data, "模型": g_model, "验证": g_verify, "数值": g_cons}
    worst = max(_idx(g) for g in dims.values())
    grade = _GRADES[worst]
    weakest = [k for k, v in dims.items() if _idx(v) == worst]
    tips = {
        "数据": "补充客户实测/报价数据（A/B 级）可提升",
        "模型": "切换权威库精算模式（pvlib/PySAM）可提升",
        "验证": "接入独立文献算例或样板工程实测标定可提升",
        "数值": "守恒未通过——结果不可用（bug 或场景不可行，先修复）",
    }
    return Confidence(grade=grade,
                      attribution=f"短板维度: {weakest[0]}={dims[weakest[0]]}",
                      improvement=tips[weakest[0]])
