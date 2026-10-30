# 设备卡片组件库（模块化卡片规范）

> 版本：kb-device-cards-v1.0 · 维护：交付物 Agent
> 代码实现：`services/reports/device_cards.py`（注册表 DEVICE_SPECS = 本文档的机器可读形态）
> 设计原则：**报告出现哪些设备，就调用哪些设备卡片**——卡片即模块（与内核模块/DESHY 产品线同构）。

## 卡片结构（紧凑三段式）

```
┌──────────────────────────┐  ← 顶部 2.5px 品牌绿边
│ {icon} {中文名}   {英文名} │  ← 11.5px 粗体 / 9px 灰
│ {额定值}{单位}             │  ← monospace 15px 深绿（卡片主信息）
│ ────────────────────    │
│ 槽位1 label        value │  ← 10px，最多 3 行
│ 槽位2 label        value │
└──────────────────────────┘
```

## 注册表（设备 → 启用条件 → 卡片槽位）

| 设备 key | 中文名/英文名 | 启用条件 | 额定槽 | specs 槽位（最多 3） |
|---|---|---|---|---|
| pv | 光伏阵列 PV Array | 模板基础 | pv.capacity_kw (kW) | 折减 / 年发电 / 风光合计发电 |
| wind | 风电机组 Wind Turbine | T6 基础 | wind.capacity_kw (kW) | 切入额定风速 / 切出风速 / 合计发电 |
| bess | 锂电池储能 Battery | T1/T6 基础 | bess.capacity_kwh (kWh) | 功率 / 往返效率 / SOC 窗口 |
| pemwe | PEM 电解槽 | T1/T6 基础 | pemwe.rated_kw (kW) | 效率 / min 负荷 / 年产氢 |
| alk / aem / soec | 碱性 / AEM / SOEC 电解 | rated>0 | 同上 | 效率 / min 负荷 /（soec: 热中性+缺热效率） |
| h2store | 储氢单元 H2 Storage | 基础 | capacity_kg | 初始存量 / 耗氢 / 罐位波动 |
| mh | 固态储氢床 Metal Hydride | bed_mass>0 | bed_mass_kg | 传热系数 / 供氢压 / 母线压 |
| fc / sofc | 燃料电池 | fc: T1 基础；sofc: rated>0 | rated_kw | 效率 /（sofc 余热比）/ 年发电 |
| hb | 合成氨装置 Haber-Bosch | T6 基础 | nh3.capacity_t_per_h (t/h) | 吨氨耗氢 / min 负荷 / 年产量 |
| asu | 空分制氮 ASU | T6 基础 | lec_kwh_per_kg_n2 | 年氮需求 |
| grid | 电网接口 | max_import>0 | max_import_kw | 购售电 / 失电 |

规则：
1. specs 槽位最多 3 行——更多信息走参数清单（卡片不塞满）；
2. kpi 来源取不到 → 该行省略（不显示"—"占位）；
3. 新设备 = 本表加一行 + DEVICE_SPECS 加条目，**报告自动出现该卡片**（模块化）；
4. bom_ref 映射（DESHY 产品型号）在卡片英文名下预留一行（接入产品库后自动挂）。

## 渲染出口（同一注册表）
- `cards_grid_html(devices)` → 导出 HTML（4 列网格）；
- `devices_data(params, kpi, template)` → JSON → React `<DeviceCards>`（同视觉 tokens）；
- Recall 的"客户确认关键参数"优先用**设备卡片**呈现（每设备一卡），完整参数表退居附录。
