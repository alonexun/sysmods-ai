# 固态储氢材料库（PMHT 格式）

本目录收录固态储氢合金的热力学与动力学数据，采用 PMHT（Metal Hydride Toolbox）
的 `.mh` 纯文本格式。

## 数据出处与许可

- **全部数据取自公开发表的文献测量**（如 Liang 等氢化物等温线、Oesterreicher 等
  合金热力学表），每个文件内的字段注释标注了文献来源（如 `# Liang Isotherm
  reversible capacity only`、`# Oesterreicher Table 1`）；
- 文献数据本身为公开事实数据；`.mh` 文件按本仓库 Apache 2.0 一并分发；
- **禁止**向本目录提交任何厂商保密数据、内部标定系数或未公开实测数据
  （见 [CONTRIBUTING.md](../../CONTRIBUTING.md) 数据红线）。

## 新增材料文件要求

1. 文件名 = 合金组成（如 `Ca[0.85]Mm[0.15]Ni[5].mh`，方括号内为摩尔比）；
2. 每个数值字段必须带出处注释（文献 + 表/图号）；
3. 若同一材料存在多个来源，优先收录可交叉验证的一组，并在注释中列另一来源；
4. 质量分数、平台压等关键锚点需可在 `tests/test_pmht_*.py` 中复现（当前 golden：
  LaNi5 半充 298K 平台压 P_abs≈2.27 / P_des≈1.86 bar）。

## 解析

加载与验证逻辑见 `kernel/hyflow/modules/mh/parser.py`；格式规范以解析器与
现有文件为准。
