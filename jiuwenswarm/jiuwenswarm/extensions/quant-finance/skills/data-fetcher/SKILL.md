---
name: data-fetcher
description: >
  Fetches historical A-share stock price and volume data for the competition
  stock pool (49 stocks across 6 sectors). Uses five-source chain:
  Sina → Tencent → akshare → baostock → yfinance, each tier fills only
  missing stocks. Unified raw (unadjusted) close prices. Fails closed if
  fewer than 49 stocks obtained.
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
   - `n_stocks` / `expected_stocks`: 实际与预期覆盖数
   - `coverage_complete`: 是否完整覆盖
   - `date_range`: 缓存行情日期范围
   - `n_stocks`: 成功获取的股票数
   - `n_days`: 交易日数
   - `date_range`: 数据日期范围

3. 只把紧凑摘要传给下一个 skill；原始行情由 Extension 缓存，不得经 LLM 传递

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

- 五源级联兜底：Sina → Tencent → akshare → baostock → yfinance，每层只请求缺失股票
- 任一环节不足49只立即失败关闭，禁止残缺股票池继续计算
- 后续工具直接读取服务端缓存；不要构造或转述 prices/volumes
- 统一使用原始（未复权）收盘价
