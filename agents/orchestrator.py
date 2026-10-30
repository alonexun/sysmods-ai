# -*- coding: utf-8 -*-
"""编排器：双环五门的状态机实现（V1.2 §7，MVP=三门：G1/G4/G5；G3 条件触发）。

纯逻辑层（无 IO）——持久化由服务层负责（checkpoint 可整体序列化为 dict）。
LLM 接入点：GrillmeAgent/ChangeOrderAgent 已预留 runtime。
sim_fn：服务层注入的仿真闭包（T1/T6→KPI dict），编排器不感知内核细节。
"""
from enum import Enum
from typing import Callable, Dict, List
import time

from .grillme import GrillmeAgent
from .change_order import ChangeOrderAgent, ChangeOrderError
from .gaps import GapAgent


class State(str, Enum):
    NEW = "NEW"
    G1_PENDING = "G1_PENDING"       # 参数卡已生成，待客户确认
    G1_CONFIRMED = "G1_CONFIRMED"
    G4_PENDING = "G4_PENDING"       # 方案已出，待审阅/变更
    G5_SIGNED = "G5_SIGNED"         # 终稿锁定


MAX_CHANGE_ROUNDS = 3   # 方案设计环有界（V1.2 §7.4）


class OrchestratorError(ValueError):
    pass


class Session:
    def __init__(self, sid: str, description: str):
        self.sid = sid
        self.description = description
        self.state = State.NEW
        self.param_card: Dict = {}
        self.gap_report: Dict = {}
        self.result: Dict = {}          # 最近一次仿真的 KPI+经济+守恒+置信度
        self.orders: List[Dict] = []    # 变更单历史（版本链）
        self.change_rounds = 0
        self.created_at = time.time()
        self.version = 0

    def checkpoint(self) -> Dict:
        """可序列化快照（会话可从任意门恢复）。"""
        return {"sid": self.sid, "description": self.description,
                "state": self.state.value, "param_card": self.param_card,
                "gap_report": self.gap_report, "result": self.result,
                "orders": self.orders, "change_rounds": self.change_rounds,
                "version": self.version}


class Orchestrator:
    def __init__(self, sim_fn: Callable[[str, Dict], Dict], llm_runtime=None):
        """sim_fn(template, params_overrides) -> KPI dict（含 kpi/econ/cons/confidence）。"""
        if sim_fn is None:
            raise OrchestratorError("sim_fn 必须注入")
        self.sim_fn = sim_fn
        self.grillme = GrillmeAgent(llm_runtime)
        self.change = ChangeOrderAgent(llm_runtime)
        self.gaps = GapAgent(llm_runtime)
        self._sessions: Dict[str, Session] = {}

    # ---------------- 会话 ----------------
    def session(self, sid: str) -> Session:
        s = self._sessions.get(sid)
        if s is None:
            raise OrchestratorError(f"会话不存在: {sid}")
        return s

    def create_session(self, sid: str, description: str) -> Session:
        if sid in self._sessions:
            raise OrchestratorError(f"会话已存在: {sid}")
        s = Session(sid, description)
        card = self.grillme.build_param_card(description)
        s.param_card = card
        s.gap_report = self.gaps.report(card["scenario"])
        s.state = State.G1_PENDING
        self._sessions[sid] = s
        return s

    # ---------------- G1 ----------------
    def confirm_g1(self, sid: str, overrides: Dict[str, float] = None) -> Session:
        s = self.session(sid)
        if s.state != State.G1_PENDING:
            raise OrchestratorError(f"当前状态 {s.state} 不可执行 G1 确认")
        if overrides:
            card = self.grillme.build_param_card(s.description, overrides)
            s.param_card = card
        s.state = State.G1_CONFIRMED
        s.version += 1
        return s

    # ---------------- 仿真 ----------------
    def run_simulation(self, sid: str) -> Session:
        """G1 确认后执行（或变更后重跑）。守恒 FAIL 时置 G3 异常状态信息。"""
        s = self.session(sid)
        if s.state not in (State.G1_CONFIRMED, State.G4_PENDING):
            raise OrchestratorError(f"当前状态 {s.state} 不可仿真")
        # 参数卡 params 中取内核所需的 overrides：与默认值不同的项
        from kernel.hyflow.registry import load_registry
        d = load_registry().defaults()
        ov = {k: v for k, v in s.param_card["params"].items() if k in d and float(v) != float(d[k])}
        result = self.sim_fn(s.param_card["template"], ov)
        if not result.get("cons_passed", False):
            # G3 异常处置：不进 G4，返回处置建议（fail 二分：数值/不可行）
            s.result = result
            s.result["g3_options"] = ["补数据/改约束后重跑", "按先验假设继续(标注)", "放弃本方案"]
            return s
        s.result = result
        s.state = State.G4_PENDING
        s.version += 1
        return s

    # ---------------- G4 ----------------
    def propose_change(self, sid: str, text: str, use_llm: bool = False) -> Dict:
        """评论 → 变更单（未确认）。达迭代上限则强制收敛提示。"""
        s = self.session(sid)
        if s.state != State.G4_PENDING:
            raise OrchestratorError(f"当前状态 {s.state} 不可提交变更")
        if s.change_rounds >= MAX_CHANGE_ROUNDS:
            return {"need_clarification": True,
                    "msg": f"已达设计环上限 {MAX_CHANGE_ROUNDS} 轮——建议强制收敛并签收，"
                           "未决问题将在报告中列为未决清单"}
        order = self.change.parse(text, use_llm=use_llm)
        if order.get("need_clarification"):
            return order
        s.orders.append(order)
        return order

    def confirm_change(self, sid: str, order_index: int = -1) -> Session:
        s = self.session(sid)
        if s.state != State.G4_PENDING:
            raise OrchestratorError("当前状态不可确认变更")
        order = s.orders[order_index]
        order["confirmed"] = True
        s.param_card["params"] = self.change.apply(order, s.param_card["params"])
        s.change_rounds += 1
        s.version += 1
        return self.run_simulation(sid)   # 缓存重跑（差分优化后置，V1.2 §7.6）

    # ---------------- G5 ----------------
    def sign_g5(self, sid: str) -> Session:
        s = self.session(sid)
        if s.state != State.G4_PENDING:
            raise OrchestratorError(f"当前状态 {s.state} 不可签收")
        s.state = State.G5_SIGNED
        s.version += 1
        return s

    # ---------------- 恢复 ----------------
    def restore(self, checkpoint: Dict) -> Session:
        s = Session(checkpoint["sid"], checkpoint["description"])
        s.state = State(checkpoint["state"])
        s.param_card = checkpoint["param_card"]
        s.gap_report = checkpoint["gap_report"]
        s.result = checkpoint["result"]
        s.orders = checkpoint["orders"]
        s.change_rounds = checkpoint["change_rounds"]
        s.version = checkpoint["version"]
        self._sessions[s.sid] = s
        return s
