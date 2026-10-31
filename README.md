# SysMods

**Distributed hydrogen energy system planning, done right.**
模块化 · 可审计 · 参数允许不确定

分布式氢能系统（kW–MW 级离网/微电网/撬装/就地消纳）的方案平台：确定性物理内核
HyFlow + 守恒审计 + canonical 参数注册表 + 置信度引擎 + 经济简算 + 可审计 Excel
计算书与交互式报告。

**SysMods is a modular, auditable planning platform for distributed hydrogen
energy systems. A deterministic physics kernel (no LLM ever produces numbers),
conservation audits on every step, a canonical parameter registry that tolerates
uncertainty, and auditable Excel/report exports.**

由 [DES Hydrogen（德斯氢能）](https://des-hy.com) 发起并维护 · Apache 2.0 开源。

---

## 核心特性

- **确定性内核 HyFlow**：模块-端口-总线制物理内核，模块族覆盖 PV / PEM·ALK·AEM·SOEC
  电解 / BESS / 储氢三型（高压·固态 MH·液氢 LH2）/ 压缩机 / 燃料电池 / 合成氨·空分；
- **守恒审计**：每步电/氢平衡，年误差 > 0.5% 直接 FAIL——结果不可用，而不是"看起来还行"；
- **参数允许不确定**：三级标注（A 实测 / B 市场 / C 文献）+ 取值裁决链 + 置信度短板归因，
  缺参不静默兜底；
- **经济简算**：Total NPC / LCOE / LCOH（HOMER 公开口径）；
- **可审计交付**：带公式 Excel 计算书 + 自包含 HTML / React 交互式报告，同源 KPI；
- **LLM 可选接入**：OpenAI 兼容网关（DeepSeek 等），未配置 key 时全链路规则模式可跑。

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 运行测试（基线 224 passed / 1 skipped）
python -m pytest tests -q

# 3. 启动 API 服务（本机 8000 被 Windows 保留时用 8765）
python -m uvicorn services.api.main:app --host 127.0.0.1 --port 8765

# 4. 前端（工作台/报告，构建产物由 FastAPI 托管）
cd apps/web && npm install && npm run build

# 5. 演示（T1 离网光储氢电端到端 + Excel 计算书）
python scripts/run_demo.py

# 6.（可选）DSH / 外部 MCP Agent 受控工具接入（stdio）
python -m services.mcp_server   # DSH 侧 mcp-client 配置见 integrations/dsh-sysmods/
```

LLM 接入（可选）：设置环境变量 `DEEPSEEK_API_KEY` 即真实调用；不设置则全链路
规则模式，功能完整、数值口径不变。

## 仓库结构

```
kernel/hyflow/          # 物理内核（数值唯一来源，LLM 不参与数值）
  engine.py             #   T1 时序引擎：调度顺序/BESS→PEM(+压缩自限)→弃电
  modules/              #   pv / electrolyzers(PEM 唯一实现) / bess / h2store /
                        #   compressor / lh2 / mh(固态) / chemical(HB/ASU/MeOH/DRI)
  templates/            #   t1_offgrid（离网光储氢电）/ t6_ammonia（氨消纳）
  optimize.py           #   穷举+保供过滤+NPC 排序
  audit/guard.py        #   守恒审计（平衡+方向双检查）
  uq/confidence.py      #   置信度引擎（四维短板评级，确定性规则）
  econ/npc.py           #   NPC/LCOE/LCOH
kb/
  params/canonical_registry.json   # canonical 参数注册表（单一权威源）
  materials/pmht/       #   固态储氢材料库（.mh，出处见 kb/materials/README.md）
agents/                 # 编排 Agent（orchestrator/grillme/change_order…）
services/api/           # FastAPI：/session /run /optimize /report（X-Token 鉴权）
services/mcp_server.py  # DSH/外部 MCP Agent 受控工具（create/补参/仿真/只读卡，stdio）
services/reports/       # 报告数据层 + 设备卡 + SVG 系统图 + Excel/HTML 导出
apps/web/               # Vite + React 18：工作台 + 交互式报告
integrations/dsh-sysmods/  # DeepSeek Harness 集成：版本锁/S0-S1 基线/profile patch/复现脚本
tests/                  # 225+ 项测试与物理锚点（手工可验算）
docs/                   # HOMER 官方示例合法对标指南等
```

## 设计铁律

1. 参数 Schema 带单位强制（`域.量_单位`，效率一律小数 0–1）；
2. canonical 注册表单一权威源，别名只在导入边界；
3. 禁止静默兜底：缺参 fail，不默认 0/1；
4. 每步守恒审计，年误差 > 0.5% 报告 FAIL；
5. 物理锚点必须第二口径交叉验算。

## 验证锚点（回归基线速查）

| 锚点 | 值 |
|---|---|
| PEM 电耗（η=0.65） | 52.6 kWh/kg（ALK 52.9 / AEM 52.1 / SOEC 38.8 热中性） |
| LaNi5 半充 298K 平台压 | P_abs≈2.27 / P_des≈1.86 bar |
| 压缩 30→350 bar @η0.7 | ≈ 1.16 kWh/kg |
| 守恒 | 电/氢年误差 ≤ 0.5%，FAIL 即结果不可用 |

## 贡献与安全

- 贡献指南（模块验收标准、DCO 签署、数据红线）：[CONTRIBUTING.md](CONTRIBUTING.md)
- 安全漏洞请私联维护者，勿开公开 Issue：[SECURITY.md](SECURITY.md)

## 许可与商标

- 代码以 **Apache License 2.0** 授权：[LICENSE](LICENSE)；第三方归属见 [NOTICE](NOTICE)；
- Apache 2.0 不授予任何商标权："DES Hydrogen"、"DESHY"、"德斯氢能" 为 DES Hydrogen
  公司品牌；"SysMods"、"SysMods AI"、"HyFlow" 为其项目与产品名称。

## 商业版说明

DES Hydrogen 提供 SysMods AI 托管服务与私有部署（设备/报价库接入、标定数据、
SLA 支持）。商业合作联系：**cz.x@des-hy.com**。

---

*输出为规划级仿真结果，供投资决策参考；详细设计须由注册工程师复核。*
