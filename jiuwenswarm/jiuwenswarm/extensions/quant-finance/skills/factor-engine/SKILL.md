---
name: factor-engine
description: >
  Computes 8-factor scores with market regime detection (Bull/Bear/Range)
  and sector-neutral Z-score normalization. Factors: momentum_20/60,
  turnover_momentum, reversal_5, RSI, volatility, volume_trend, max_drawdown.
  Use when: need to score and rank stocks after data fetching.
allowed_tools:
  - quant_compute_factors
---

# 多因子计算 Skill

对股票价格数据执行 8 因子计算，包含市场状态识别和行业中性化处理。

## 因子体系

| 类别 | 因子 | 含义 |
|------|------|------|
| 趋势 | 20日动量 | 短期趋势强度 |
| 趋势 | 60日动量 | 中期趋势强度 |
| 趋势 | 换手率动量 | 趋势质量（动量/波动率） |
| 反转 | 5日反转 | 短期均值回归信号 |
| 反转 | RSI(14) | 超买超卖指标 |
| 风险 | 20日波动率 | 价格不确定性 |
| 风险 | 60日最大回撤 | 极端风险度量 |
| 交易 | 成交量趋势 | 5日均量/20日均量 |

## 执行流程

1. 从前一步 (data-fetcher) 接收 `prices` 和 `volumes` 数据

2. 调用 `quant_compute_factors`:
   - `prices`: 价格数据 (来自 quant_fetch_data 的返回)
   - `volumes`: 成交量数据 (可选)

3. 工具返回:
   - `regime`: 市场状态 (bull/bear/range)
   - `top_stocks`: 综合得分 Top 15 (含代码、名称、得分、板块)
   - `all_composite`: 所有股票的综合得分字典

4. 将 `all_composite` 和 `regime` 传递给下一步 (stock-selector)

## 市场状态动态权重

- **牛市 (Bull)**: 动量因子权重 ×1.5，反转因子 ×0.3
- **熊市 (Bear)**: 风险因子权重 ×1.5~2.0，动量因子 ×0.3
- **震荡 (Range)**: 均衡配置，略偏反转因子

## 行业中性化

所有因子在板块内部进行 Z-score 标准化，确保跨板块可比。
