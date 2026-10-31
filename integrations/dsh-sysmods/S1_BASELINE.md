# DSH S1 基础能力基线（SysMods × DeepSeek Harness · MCP 路径）

> **日期**：2026-10-31 · **状态**：S1 协议级完成；带 key 全环对话冒烟待 `DEEPSEEK_API_KEY`
> **依据**：主计划 V1.3 §11 S1（三基础能力 + 只读卡）、§2.6.1（工具契约/封套）、§2.6.2（幂等/单写者/恢复/计量）
> **前置**：`S0_BASELINE.md`（版本锁 22ddee37 / 隔离 DSH_HOME / 出口与 Shell 关闭——S1 全程继承，未改动）

---

## 1. 架构决策：MCP 路径（stdio）

| 决策 | 内容 | 理由 |
|---|---|---|
| 接入方式 | **MCP**（`@deepseek-ai/dsh-mcp-client` → `python -m services.mcp_server`，stdio） | DSH 零代码改动；单写者不变（工具只调 Sysmods 领域服务）；官方本地程序模式 |
| 复用原则 | MCP 层只做封套/鉴权/幂等/错误翻译，**复用 FastAPI 同一 Orchestrator/Ledger/LLM 网关** | V1.3 §2.5：DSH 工具与 REST 复用同一领域服务，不另设计算与计费口径 |
| 数据隔离 | DSH 子进程专用 `SYSMODS_DB=dsh-homes/s0/sysmods-mcp.db` | V1.3 §8.6.5：验证阶段只用虚构样例，不碰开发库与客户数据 |

## 2. 四个受控工具（`mcp__sysmods__<name>`）

| 工具 | 语义 | 写/读 | 契约要点（§2.6.1） |
|---|---|---|---|
| `create_project` | 创建项目 → 完整参数卡 + 首问清单 | 写 | `actor_token`；可选 `idempotency_key`；`use_llm`（无 key 规则模式） |
| `submit_requirement_answer` | 对话补参 | 写 | answers **逐项过 canonical 注册表 validate（非法值不写入）**；`expected_version` 过期 → `VERSION_CONFLICT`；`idempotency_key` |
| `run_simulation` | 仿真（KPI/守恒/置信度） | 写（计费） | 时长计费 2 积分/分钟；G3 守恒 FAIL 不扣费；幂等重试不重复扣费 |
| `get_param_card` | 参数卡只读 | 读 | 无副作用、不计费（§2.6.1：读操作可省幂等/版本） |

统一响应封套：`{ok, session_id, state, data, error{code,message,retryable}, usage_ref}`；
错误码：`UNAUTHORIZED / INVALID_PARAM / VERSION_CONFLICT / STATE_ERROR / INSUFFICIENT_CREDITS / NOT_FOUND`——只返回可行动信息，不暴露堆栈/数据库细节。

## 3. 验收证据（V1.3 §11 S1 逐项）

| S1 验收项 | 结果 | 证据 |
|---|---|---|
| 三基础能力 + 只读卡实现 | ✅ | `services/mcp_server.py`；`tests/test_mcp_server.py` 7/7 passed |
| 显式参数逐项过注册表，非法值不写入 | ✅ | 契约测试：`bess.eff_roundtrip=1.5`（越界）→ `INVALID_PARAM`；卡值保持 0.90 默认、version 0、状态不变（领域层 `grillme._reg.validate` 在写入前拦截） |
| 普通文本无工程副作用 | ✅ | `get_param_card` 只读测试：两次读取 version/台账/状态零变化 |
| 无重复扣费（幂等） | ✅ | 同 `idempotency_key` 重试 `run_simulation`：响应相同、台账行数不变（`mcp_idempotency` 表按 tool+session+key 去重） |
| `expected_version` 过期保护 | ✅ | 过期提交 → `VERSION_CONFLICT`（retryable，要求重读参数卡）——禁止 DSH 以旧快照覆盖新方案 |
| DSH 侧组合生效 | ✅ | `dsh/s1-dump-mcp.yml`：`mcp-sysmods` 行（insert 语法）入组合；S0 五项覆盖全部保留 |
| **启动级活体验证** | ✅ | headless 启动探针：DSH spawn `services.mcp_server` 子进程并完成 `ListToolsRequest`（MCP SDK 日志 `server.py:534 ListToolsRequest`），随后失败点精确落在预期 `MISSING_CREDENTIAL`（无 key 的 LLM 门——其余链路全通） |
| 协议一致性（DSH 同款接入面） | ✅ | `test_stdio_lists_four_tools`：以 mcp-client 相同的 stdio spawn 方式握手，四工具全部可见 |
| 会话恢复/重启参数来源 | ✅（继承） | MCP 走 `_session_auto`（checkpoint 自动恢复，与 REST 同路径，`test_session_auto_restore` 已覆盖）；DSH 恢复/分叉不触领域状态（§2.0.1，DSH 侧无写权限） |
| **聊需求→参数卡→仿真全通（LLM 在环）** | ⏳ 待 key | 需要 `DEEPSEEK_API_KEY` 驱动 DSH 真实对话；隔离 home 无凭据是 S0 的设计约束。**补测路径**：隔离环境注入测试 key → `dsh --profile sysmods-s0 "搭建一个哨站离网供电方案"` → 观察模型调用 `mcp__sysmods__create_project` → 补参 → `run_simulation` 全链 |

## 4. 运行时级出口审计（S0 遗留项，本轮部分完成）

- 启动探针确认：无 key 时唯一失败点是 `llm-deepseek` 凭据门——**在 LLM 未配置时无任何网络外呼可能**；
- MCP 子进程为 stdio 本地进程，无网络面；
- 完整抓包级审计（带 key 跑一轮任务核对仅 api.deepseek.com 出口）随 §3 待 key 项一并进行。

## 5. 复现步骤

```powershell
cd sysmods-ai\integrations\dsh-sysmods
powershell -ExecutionPolicy Bypass -File bootstrap-s0.ps1    # 幂等：版本锁校验→重建 profile→打 patch（含 mcp 行）→dump 证据
# 契约测试
cd ..\.. && python -m pytest tests/test_mcp_server.py -q
# 启动探针（无 key，预期失败点=MISSING_CREDENTIAL，此前的 ListToolsRequest 即 MCP 同步证据）
$env:DSH_HOME="..\dsh-homes\s0"; cd <deepseek-harness 仓>; corepack pnpm dsh --profile sysmods-s0 "列出可用 sysmods 工具"
```

## 6. S2 前待办

1. 带 key 全环对话冒烟（§3 待 key 项）+ 抓包级出口审计；
2. G1/G3/G4/G5 门与变更单走 MCP 通路（新增 propose_change / confirm_change / sign_off 等工具，扩展现有 idempotency 表）；
3. MCP 工具结果在 DSH 卡片上的呈现打磨（§2.7 标准不降）；
4. `_persist`/`_session_auto` 等私有函数抽取为共享服务模块（当前 MCP 层直接复用 main.py 函数，行为一致但属技术债候选）。
