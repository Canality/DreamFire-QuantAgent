---
name: stock-selector
description: >
  Selects top-N stocks from factor scores by descending composite score.
  No forced sector diversification — pure score ranking, composite > 0 only.
  Use when: need to pick final stock list from factor scores.
allowed_tools:
  - quant_select_stocks
  - quant_compute_factors
---

# 选股决策 Skill

从因子得分中按裸分排序选出最终投资标的。

## 选股规则

1. 按综合得分从高到低选取，composite > 0 才纳入
2. 最多持仓 top_n 只（默认 15）
3. 不做板块分散强制约束——裸分 Top 15 天然跨 5-6 个板块
4. 选股结果不足 15 只（或不足 6 板块覆盖）则失败关闭

## 执行流程

1. 从前一步 (factor-engine) 接收 `all_composite` 得分数据

2. 调用 `quant_select_stocks`:
   - `all_composite`: 综合得分字典 (来自 quant_compute_factors)
   - `top_n`: 最大持仓数 (默认 15)
   - `min_score`: 最低得分阈值 (默认 -0.5)

3. 工具返回:
   - `selected_stocks`: 选中的股票列表 (含代码、得分、板块)
   - `tickers`: 选中的股票代码列表
   - `n_selected`: 选中数量
   - `n_sectors_covered`: 覆盖板块数

4. 将 `tickers` 传递给下一步 (position-manager)

## 空仓/轻仓触发条件

根据市场状态判断是否降低仓位:
- 若 regime 为 bear 且超过半数股票得分为负: 建议只保留 3-5 只防御性股票
- 若没有股票得分 > 0.5: 建议增加现金比例
