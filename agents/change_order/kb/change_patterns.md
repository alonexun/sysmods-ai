# 变更模式库（变更单解析 Agent）

> 来源：代码 ALIASES 沉淀 + V1.2 §7.3 变更单协议
> 版本：kb-change-v1.0 · 维护：变更单解析 Agent

## 中文别名 → canonical（唯一映射表，禁止双轨）
电解槽/电解/PEM → pemwe.rated_kw
光伏/光伏容量/装机 → pv.capacity_kw
风电/风机 → wind.capacity_kw
储能/锂电/电池 → bess.capacity_kwh
储氢/氢罐 → h2store.capacity_kg
合成氨/氨产量 → chem.nh3.capacity_t_per_h
燃料电池 → fc.rated_kw
负荷 → load.avg_kw

## 解析规则
- 识别"把/将/改为/调到/设为 X" + 数值 + 单位（kW/千瓦/kg/吨 等）；
- 数值必须过 canonical 值域校验，越界 → 澄清（给合法范围），**不得静默截断**；
- 无法识别参数或数值 → need_clarification（引导客户明确，不猜）；
- LLM 路径：prompt 只含白名单参数（名称+单位+范围），输出 JSON 后同样过校验；
  非法输出降级规则模式并标注 llm_mode=degraded。

## 回显格式
`变更单：将 {canonical}（{中文描述}）设为 {值} {单位}。确认执行？`
- 未确认 confirmed=False，禁止 apply；
- 低置信（LLM confidence<0.5）追加"请仔细核对"；
- 应用时写参数卡副本（非原地），版本+1。

## 迭代约束
设计环 ≤3 轮；达上限回复"建议强制收敛并签收，未决问题列入报告"。
