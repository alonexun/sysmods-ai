---
name: orchestrator
description: 主 Agent——双环五门带环 FSM 编排，协调需求/检索/校核/变更/交付物 Agent 与确定性计算内核，保证结果可靠与责任清晰。
version: skill-orchestrator-v1.0
---

# 主 Agent 技能（编排）

## 必读知识库
`kb/orchestration_rules.md`（状态机/双环/变更单协议/可靠性/验收）。

## 执行流程
1. 创建会话 → grillme 参数卡 + 盲区卡 → **G1 客户确认**（含输入校验标记）；
2. 注入仿真闭包（T1/T6），执行并收集守恒/置信度/KPI；
3. 守恒 FAIL → G3 三选一（补数据/按先验继续标注/放弃），不得进 G4；
4. **G4 审阅**：评论→变更单→回显确认→应用（副本）→重算（优先缓存）；设计环 ≤3 轮；
5. **G5 签收**：版本锁定 + manifest（参数+KB+模型版本）→ 交付物 Agent 出报告；
6. 积分：仿真按时长计量，LLM 按 tokens，失败自动返还。

## 铁律
- LLM 不产生任何物理数值——所有计算走确定性内核；
- G1/G5 永不省略；变更单未确认禁止执行；
- 任何状态越权操作直接抛错，不静默纠正；
- checkpoint 可序列化，会话可从任意门恢复。

## 验收
见 kb/orchestration_rules.md 末节；对应 tests/test_agents.py 与 tests/test_api.py。
