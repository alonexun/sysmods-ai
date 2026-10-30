# DSH S0 隔离基线（SysMods × DeepSeek Harness）

> **日期**：2026-10-30 · **状态**：S0 完成（配置组合级验证）
> **依据**：主计划 V1.3 §11 "DSH 分阶段验证与采用门槛"（S0 隔离基线）、§8.6 "DSH 供应链与数据边界"
> **回退开关**：`SYSMODS_DSH_ENABLED`（默认 false；关闭即回现有 React 工作台，见 V1.3 §11 回退机制）
> **责任人**：Chengzhang XUN（cz.x@des-hy.com）

---

## 1. 版本锁（Developer Preview 不跟随主分支）

| 项 | 值 |
|---|---|
| DSH 仓 | `C:\Users\Chengzhang XUN\Documents\GITHUB\deepseek-harness`（本地克隆，master 分支） |
| **固定 commit** | `22ddee3792402c3e70ec5f86a63c3e3e895a2f60` |
| **本地 tag** | `sysmods-s0-pin`（`git tag -f sysmods-s0-pin 22ddee37`，已打） |
| 版本 | `0.2.1-rc.3`（root package.json） |
| 许可 | **MIT**（Copyright (c) 2026 DeepSeek）——可商用确认 ✓ |
| 运行时 | Node v24.11.1（要求 >=24.9）· pnpm 11.28.5（corepack） |
| **升级规则** | 禁止 pull/reset 跟随 master；任何升级 = 新 DSH_HOME + 隔离环境重跑 S0–S2 全部验收，通过后才灰度 |

## 2. 供应链归档（V1.3 §8.6.1，@固定 commit 的 git blob ID）

| 文件 | blob（`git rev-parse <commit>:<file>`） | 结论 |
|---|---|---|
| `LICENSE` | `c1f7a78e89e4e4dc7b86664c3b3c76eb5eee1785` | MIT，可商用 ✓ |
| `THIRD_PARTY_NOTICES.md` | `51737ac1ed14cf24f798441118981fe6c4211c84` | 第三方归属已由上游维护；采用前另做依赖审查（S1） |
| `BRAND_GUIDELINES.md` | `900cf7bcec70ff78c6f55ed535897239cd4648df` | 品牌要求：不得暗示 DeepSeek 官方背书；SysMods 侧表述见 §5 注意事项 |

## 3. 隔离环境（按项目隔离 DSH_HOME，不碰生产数据）

| 项 | 值 |
|---|---|
| **S0 DSH_HOME** | `Sysmods/dsh-homes/s0`（本仓 `sysmods-ai/` **之外**——运行时数据不入公开仓） |
| 生产数据隔离 | 本机已有 `~/.dsh`（含用户 sessions/credentials）——**S0 全程未触碰**；bootstrap 脚本显式拒绝 `~/.dsh` 作为目标 |
| Profile | `sysmods-s0`（`--from-default-profile headless` 创建；bundles = `dsh-base` + `dsh-headless`） |
| **凭据** | 隔离 home 无 `.credentials.yaml`、无 `DEEPSEEK_API_KEY` → **LLM 外呼不可能发生** |
| 真实数据 | S0 未运行任何任务、未输入任何真实/客户数据（仅配置组合验证） |

## 4. 关闭项（profile patch 生效证据）

`profiles/sysmods-s0.cordis.patch.yml` 应用后 `--dump-config` 实测（证据文件 `dsh/s0-dump-patched.yml`）：

| 行 id | 覆盖 | dump 实测 |
|---|---|---|
| `session-log-deepseek` | `enabled: false`（默认 true——官方 DeepSeek 请求附带 dsh_session_log） | ✓ `enabled: false` |
| `session-telemetry-otel` | `mode: DISABLED`（默认 FEEDBACK_ONLY——仍外发 `dsh-otel-collector.deepseeksvc.com`） | ✓ `mode: DISABLED`（不构造传输） |
| `tool-bash` | `disabled: true`（原为 win32 条件禁用） | ✓ |
| `tool-pwsh` | `disabled: true`（Windows 下 Shell 工具实际生效者） | ✓ |
| `tool-jobs` | `disabled: true`（后台任务同样构成命令执行面） | ✓ |

对照基线：`dsh/s0-dump-default.yml`（未打 patch 的默认组合，395 行）。

## 5. 网络出口清单（S0 出口审计）

| 出口面 | 状态 |
|---|---|
| 官方 LLM API | 无凭据 → 物理不可能外呼 |
| `session-log-deepseek`（dsh_session_log 上传） | **已关闭** |
| `session-telemetry-otel`（OTel 反馈导出） | **已关闭**（DISABLED 不构造传输） |
| `web-fetch-http` / web search | Agent 工具（模型可调用）；S0 未运行任务未触达；S1 起按需评估白名单 |
| plugin market / 远程插件安装 | headless profile 不含 market bundle；`dsh plugin` 为显式人工操作，S0 未执行 |
| ⚠️ 诚实边界 | 本 S0 验证到**配置组合级**（DSH 官方审计面 `--dump-config`）。运行时抓包级出口验证排入 S1（届时以测试 key 驱动真实任务并核对无未批准上传） |

## 6. 复现步骤（一键脚本）

```powershell
cd sysmods-ai\integrations\dsh-sysmods
powershell -ExecutionPolicy Bypass -File bootstrap-s0.ps1   # 幂等：校验版本锁 → 建 profile → 打 patch → dump 证据
```

## 7. S0 验收清单（对照 V1.3 §11）

| S0 验收项 | 结果 | 证据 |
|---|---|---|
| 固定 DSH 版本/commit 与 profile | ✓ | commit `22ddee37` + tag `sysmods-s0-pin` + profile `sysmods-s0`（headless 基） |
| 归档 MIT/第三方依赖/品牌要求 | ✓ | §2 blob ID 归档；MIT 确认 |
| 独立 `DSH_HOME`/workspace | ✓ | `dsh-homes/s0`，与 `~/.dsh` 完全隔离 |
| 默认关闭日志上传和 Shell | ✓ | §4 五项 dump 实测 |
| 仅用虚构或公开样例 | ✓ | 未运行任何任务/未输入任何数据 |
| 启动与配置可复现 | ✓ | `bootstrap-s0.ps1` 幂等重建 + dump 证据可再生成 |
| 网络出口审计无未批准上传 | ✓（配置级）/ 运行时级排入 S1 | §5 诚实边界 |
| 无真实客户数据 | ✓ | §3 |
| 现有 React 工作台与报告仍可正常使用 | ✓ | sysmods-ai 本日全量 `pytest` 224 passed / 1 skipped（S0 未改动平台代码，本目录为新增集成资产） |
| 明确回退开关和责任人 | ✓ | `SYSMODS_DSH_ENABLED=false`（默认）；责任人 Chengzhang XUN |

## 8. 品牌注意事项（来自 BRAND_GUIDELINES.md @固定 commit）

- 对外表述使用 "DeepSeek Harness（DSH）" 时不得暗示 DeepSeek 官方对 SysMods 的背书或合作关系；
- SysMods 侧文案：DSH 是"通用工作台集成"，Sysmods 是独立产品——与 V1.3 §2.0.1 职责边界表述一致。

## 9. 下一步（S1 三个基础能力）

1. Sysmods 侧：FastAPI 之上暴露 MCP 工具（`mcp-client` 行接入，DSH 零改动）或轻量 Cordis 插件——**优先 MCP 路径**（最小侵入、单写者不变：工具只传结构化 JSON 调用 Sysmods 受控 API）；
2. 三工具 + 一只读：`create_project` / `submit_requirement_answer` / `run_simulation` / `get_param_card`（按 V1.3 §2.6.1 请求封套：`session_id`/`actor_token`/`idempotency_key`/`expected_version`）；
3. S1 验收门槛：非法值不写入、普通文本无工程副作用、Sysmods checkpoint 为重启后唯一参数来源、无重复扣费、运行时级出口审计。
