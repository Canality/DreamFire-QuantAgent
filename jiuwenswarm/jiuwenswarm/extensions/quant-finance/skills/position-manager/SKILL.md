---
name: position-manager
description: >
  Allocates portfolio weights using risk-parity (inverse volatility) with
  single-stock ≤10% and single-sector ≤25% caps. Returns optimized portfolio.
  Use when: need to size positions for selected stocks.
allowed_tools:
  - quant_allocate_positions
---

# 仓位管理 Skill

基于风险平价原则分配投资组合权重，施加个股和板块集中度约束。

## 仓位管理方法

### 风险平价 (Risk Parity)
$$
w_i = \frac{1/\sigma_i}{\sum_j 1/\sigma_j}
$$

核心理念：让每只股票对组合总风险的贡献大致相等。低波动股票获得更高权重。

### 约束条件

| 约束类型 | 上限 | 设置理由 |
|----------|------|----------|
| 单只股票 | ≤ 10% | 避免个股黑天鹅事件 |
| 单板块 | ≤ 25% | 避免板块系统性风险 |
| 最低现金 | ≥ 5% | 保留流动性 |

## 执行流程

1. 从前一步 (stock-selector) 接收选中的 `tickers` 列表

2. 调用 `quant_allocate_positions`:
   - 行情不作为参数传递；工具从服务端缓存读取训练段行情
   - `tickers`: 选中的股票代码列表 (来自 quant_select_stocks)

3. 工具返回:
   - `portfolio`: 投资组合列表 (含代码、名称、权重、权重百分比、板块)
   - `total_weight`: 总仓位比例
   - `cash_reserve`: 现金储备比例
   - `weights`: ticker → weight 字典

4. 将 `portfolio` 和 `weights` 传递给下一步 (report-generator 和 backtest)
