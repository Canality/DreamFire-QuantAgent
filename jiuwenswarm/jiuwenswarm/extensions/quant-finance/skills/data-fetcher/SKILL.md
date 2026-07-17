---
name: data-fetcher
description: >
  Fetches historical A-share stock price and volume data for the competition
  stock pool (49 stocks across 6 sectors). Uses yfinance with akshare fallback.
  Use when: need to load stock data for factor calculation or backtesting.
allowed_tools:
  - quant_fetch_data
---

# 股票数据获取 Skill

获取比赛股票池（6 大板块 × 49 只股票）的历史行情数据。

## 执行流程

当用户请求量化分析或回测时，作为第一步：

1. 调用 `quant_fetch_data` 获取股票数据
   - `start_date`: 默认 180 天前
   - `end_date`: 默认今天
   - `tickers`: 留空获取全部 49 只股票，或指定特定股票列表

2. 工具返回的数据包含:
   - `prices`: 价格矩阵 (JSON 格式，按日期索引)
   - `volumes`: 成交量矩阵
   - `n_stocks`: 成功获取的股票数
   - `n_days`: 交易日数
   - `date_range`: 数据日期范围

3. 将返回的 `prices` 和 `volumes` 传递给下一个 skill (factor-engine)

## 股票池覆盖范围

| 板块 | 股票数 |
|------|--------|
| 金融 | 8 只 |
| 消费 | 9 只 |
| 新能源/电力 | 8 只 |
| 科技/AI/半导体 | 12 只 |
| 周期/资源 | 8 只 |
| 高端制造/基建 | 4 只 |

## 注意事项

- 如果 yfinance 获取失败，会自动降级到模拟数据
- 返回的 prices 和 volumes 是 JSON 格式，需要原样传递给后续工具
- 数据已前复权处理
