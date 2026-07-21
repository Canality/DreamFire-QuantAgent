---
name: report-generator
description: >
  Runs backtest and generates a structured Markdown quantitative investment
  report with metrics, portfolio breakdown, and factor score rankings.
  Use when: need final report after portfolio construction.
allowed_tools:
  - quant_run_backtest
  - quant_generate_report
---

# 投资报告生成 Skill

运行回测并生成结构化量化投资分析报告。

## 执行流程

### 步骤 1: 运行回测

调用 `quant_run_backtest`:
- 行情不作为参数传递；工具只使用服务端缓存中的前向测试段
- `weights`: ticker → weight 字典 (来自 quant_allocate_positions)
- `initial_capital`: 初始资金 (默认 1,000,000)

返回关键指标:
- `total_return`: 累计收益率
- `annualized_return`: 年化收益率
- `max_drawdown`: 最大回撤
- `sharpe_ratio`: Sharpe 比率
- `annualized_volatility`: 年化波动率
- `win_rate`: 日胜率

### 步骤 2: 生成报告

调用 `quant_generate_report`:
- `portfolio`: 投资组合列表 (来自 quant_allocate_positions)
- `backtest`: 回测指标 (来自 quant_run_backtest)
- `regime`: 市场状态 (来自 quant_compute_factors)
- `top_stocks`: Top 股票列表 (来自 quant_compute_factors)

返回:
- `report`: 完整的 Markdown 格式投资报告
- `summary`: 摘要指标

## 报告包含内容

1. 回测表现摘要 (累计收益、年化收益、最大回撤、Sharpe、波动率、胜率)
2. 投资组合明细 (持仓股票、权重、板块分布)
3. 因子得分 Top 10 排名
4. 市场状态分析

## 回测假设

- 初始资金: 1,000,000 CNY
- 交易成本: 0.03% 单边
- 首日开盘买入，固定股数持有至第20个交易日收盘
- 使用原始（未复权）OHLCV 价格
- 无日频再平衡
