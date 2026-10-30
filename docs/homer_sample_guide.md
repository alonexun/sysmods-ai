# HOMER 官方示例数据获取指南（T1 验证基准）

> 目的：取得 **Sample-StandalonePVHydrogenSystem** 的官方输入/输出，作为 Sysmods AI 的系统级验证基准（方案 V1.2 §3.2 双轨测试②）。
> 合规：仅使用官方试用版与公开文档。**不使用任何逆向工程产物**（IP 红线）。

## 1. 获取 HOMER Pro 官方试用版

1. 打开官网 **https://www.homerenergy.com/**（UL Solutions 旗下）；
2. 进入 **HOMER Pro → Download / Free Trial**，注册后下载安装包（通常提供 **30 天全功能试用**）；
3. 安装到 Windows（与 MATLAB/项目目录隔离，仅用于查看与导出示例）。

## 2. 找到官方示例文件

- 启动后 **File → Open Sample**（示例库），选择 **`StandalonePVHydrogenSystem`**（独立光伏-氢系统）；
- 示例 `.hmr` 文件通常位于：
  - `C:\Users\<你>\Documents\HOMER Pro\Samples\`（或 `HOMER\Samples`），或
  - 安装目录下的 `Samples\` 子目录；
- 若列表无此示例：在 HOMER 内 **File → New** 按文档手动搭建同名系统，或查看官方文档 "Sample Files" 章节获取下载链接。

## 3. 需要导出的内容（对应 `tests/golden/homer_t1/`）

| 内容 | 导出方式 | 用途 |
|---|---|---|
| **输入参数表**（光伏/电解槽/储氢/燃料电池/负荷/成本/效率/寿命/贴现率） | 各组件 Properties 窗口逐项记录，或 File → Export as Excel | 填入 canonical 参数卡 |
| **最优配置与结果摘要**（NPC、LCOE/LCOH、年制氢量、保供率、余电率） | Simulation Results → Summary / Optimization Results 表（右键 Copy 或 Export） | 输出对照基准 |
| **逐时序列**（8760h：PV、电解功率、储氢 SOC、FC、负荷、失电） | Time Series 标签 → Export as CSV/Excel | 时序差异归因 |
| **气象与负荷数据**（地点、GHI、负荷曲线） | Resources/Load 页面导出 | 输入复现 |

## 4. 放置位置与对跑

```
sysmods-ai/tests/golden/homer_t1/
  ├── inputs.yaml / inputs.json     # 按 canonical 命名的输入参数（含单位与出处）
  ├── expected_summary.json         # HOMER 输出摘要（NPC/LCOE/产氢/保供率）
  └── timeseries.csv                # 可选：逐时序列
```

数据到位后执行（将创建的脚本）：
```powershell
python tests/golden/homer_t1/compare.py
```
输出：逐项差异表（我平台 vs HOMER），每处差异强制归因（口径不同/模型简化/疑似 bug），并给出可接受容差。

## 5. 容差与口径说明（预期差异，不必强求一致）

- 效率曲线：HOMER 用电解/FC 效率曲线，我们当前为固定效率（L3 规划级）——产氢/电耗会有系统性小偏差；
- PV 模型：HOMER 的温度/辐照修正 vs 我们的简化模型——发电量差异需归因；
- 调度策略：Load Following / Cycle Charging 的差异（在 G1 中注明所选策略）；
- 经济口径：NPC/LCOE 的组件范围与残值处理（HOMER 五类成本）应对齐到同一组件清单再比。

**验证目标**：在同口径下关键指标（产氢量、保供率、NPC 构成）差异可解释且 < 10-15%；不可解释的大偏差按 bug 处理。
