# -*- coding: utf-8 -*-
"""置信度引擎 v0：四维短板评级（确定性规则非 LLM）。"""
from kernel.hyflow.uq.confidence import assess, ConfidenceInput


def test_all_high():
    c = assess(ConfidenceInput(data_level="A", model_level="L1",
                               verified="T3实测", cons_passed=True))
    assert c.grade == "A"


def test_conservation_failure_is_D():
    c = assess(ConfidenceInput("A", "L1", "T3实测", cons_passed=False))
    assert c.grade == "D"
    assert "守恒" in c.improvement


def test_shortboard_principle():
    """短板原则：即便其余全 A，L3 简化模型 + 自证 → C。"""
    c = assess(ConfidenceInput("A", "L3", "自证", True))
    assert c.grade == "C"
    assert "模型" in c.attribution


def test_unverified_is_D():
    c = assess(ConfidenceInput("B", "L2", verified="未验证", cons_passed=True))
    assert c.grade == "D"


def test_model_upgrade_path_mentioned():
    c = assess(ConfidenceInput("B", "L3", "自证", True))
    assert "pvlib" in c.improvement or "权威库" in c.improvement
