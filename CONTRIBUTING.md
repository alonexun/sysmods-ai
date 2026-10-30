# 贡献指南（CONTRIBUTING）

感谢你考虑为 **SysMods** 贡献！这是一个分布式氢能系统的模块化仿真平台——**确定性物理内核 + 守恒审计 + 参数可审计**。请先读完本指南再提交 Issue / PR。

## 1. 项目原则（所有贡献必须遵守）

1. **LLM 不产生任何物理/经济数值**——数值只能来自确定性内核代码；
2. **参数 Schema 必带单位**（命名规范 `域.量_单位`，效率一律小数 0–1）；
3. **canonical 参数注册表是单一权威源**（`kb/params/canonical_registry.json`），别名只允许出现在导入边界；
4. **禁止静默兜底**：缺参 fail，不允许默认 0/1 掩盖错误；
5. **守恒审计双检查**：新模块必须同时通过"能量/质量平衡"与"能量方向"两道审计；
6. **物理锚点必须双口径交叉验算**：任何新锚点值需有第二个独立来源/方法复核（防止与代码同错）。

## 2. 贡献流程

```
开 Issue（描述场景/模块/问题） → Fork + 分支 → 开发 + 测试 → PR → CI 全绿 → 维护者评审 → 合入
```

- 分支命名：`feat/<模块名>`、`fix/<问题号>-<简述>`、`data/<材料或参数>`
- PR 必须通过全部测试：`python -m pytest tests -q`（当前基线 224 passed / 1 skipped）
- 改动前端（`apps/web/`）时请附截图并本地执行 `npm run build` 确认构建通过

### 新物理模块的验收标准

- 在 `kb/params/canonical_registry.json` 注册参数（含 unit / range / level / source）；
- 年度电/氢守恒误差 ≤ 0.5%（audit 通过，FAIL 即结果不可用）；
- 提供至少 1 个**文献可查证的物理锚点测试**（并注明第二口径来源）；
- 关闭守恒审计跑同配置，结果应不一致（证明审计真实生效）；
- 在 PR 描述中给出"效率>100%"类量纲自检结果。

## 3. 绝对禁止提交的内容

- **客户数据**（任何真实项目参数、报价、合同信息）；
- **厂商保密数据**（设备内部标定系数、报价策略、未公开实测数据）；
- **HOMER 逆向工程产物**（HOMER Pro 为 UL Solutions 商业软件；对标验证只允许走
  官方试用版导出与公开文档，见 `docs/homer_sample_guide.md`；`tests/golden/homer_t1/`
  目录被 gitignore，导出数据**不得入库**）；
- **密钥与凭据**（API key 一律走环境变量，如 `DEEPSEEK_API_KEY`）；
- 运行时产物（`output/`、`*.db`、日志——均被 .gitignore 排除）。

> 以上红线同样适用于 Issue / 讨论：请使用**虚构或公开数据**描述问题。

## 4. 贡献许可协议：DCO

本项目采用 [Developer Certificate of Origin](https://developercertificate.org/)（DCO）。
提交 PR 前请为每个 commit 添加 Signed-off-by 签名：

```bash
git commit -s   # 自动附加 "Signed-off-by: 你的名字 <你的邮箱>"
```

签署即表示你声明：该贡献为你本人创作、且有权按 Apache 2.0 提交。
**所有贡献按 Apache License 2.0 授权**（见 LICENSE），供本项目及衍生使用。

## 5. 报告安全漏洞

请勿公开 Issue 报告安全漏洞，见 [SECURITY.md](SECURITY.md) 私联系维护者。

## 6. 联系与社区

- 仓库问题走 GitHub Issues；
- 商业合作（设备库接入、私有部署、托管服务）请联系 **cz.x@des-hy.com**。

---

SysMods 由 [DES Hydrogen（德斯氢能）](https://des-hy.com) 发起并维护。
