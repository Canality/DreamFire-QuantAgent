---
name: factor-engine
description: >
  Computes the production 6-factor scores with market regime detection
  and sector-neutral Z-score normalization. Factors: momentum_20,
  momentum_60, reversal_5, max_drawdown, volume_corr, volume_trend.
  Use when: need to score and rank stocks after data fetching.
allowed_tools:
  - quant_compute_factors
---

# 多因子计算 Skill

对服务端缓存中的训练段行情执行 6 因子计算。原始价格和成交量不得进入 LLM 上下文。

## 当前生产因子

| 类别 | 因子 | 含义 |
|---|---|---|
| 趋势 | momentum_20 | 20 日动量 |
| 趋势 | momentum_60 | 60 日动量 |
| 反转 | reversal_5 | 5 日短期反转 |
| 风险 | max_drawdown | 60 日最大回撤 |
| 量价 | volume_corr | 量价相关性 |
| 量价 | volume_trend | 短长周期成交量趋势 |

## 执行流程

1. 确认 `quant_fetch_data` 返回 `success=true`、`coverage_complete=true`、`49/49`。
2. 无参数调用 `quant_compute_factors`；工具只读取服务端缓存中的训练段。
3. 检查返回 `success=true`、`n_stocks_analyzed=49`。
4. 将紧凑的 `all_composite`、`top_stocks`、`regime` 传给后续决策；不得传行情矩阵。

## 诚实披露

生产代码仍使用历史 6 因子模型。开发集候选模型和封存窗口结果必须按 `VALIDATION.md` 描述，不得把候选结论写成生产模型已切换。
