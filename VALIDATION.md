# 当前验证状态

> 本文件只记录可复现证据。组件测试、研发直跑、JiuwenSwarm 多 Agent 正式路径是三类不同证据，不能互相替代。

## 最新结论（2026-07-21 13:20，Asia/Shanghai）

- 被测实现提交：`24a5e1d`；验证文档与首个封存窗口脚本随后单独归档。
- 总体结论：**PARTIAL**。代码层 Bug 已修并有回归测试；真实数据源当前不稳定，因此不能宣称两条路径在“最新一次”同时通过。
- 模型与封存集：本轮没有改策略参数，没有打开第二个封存窗口。

| 能力 | 状态 | 证据 |
|---|---|---|
| 量化单元测试 | PASSED | `17 passed`；其中缓存隔离、因果切分、覆盖失败关闭、逐只补缺新增 4 项 |
| Extension 行情隔离 | PASSED（组件） | fetch 仅返回摘要；compute/bull/bear/allocate/backtest 忽略 LLM 行情参数并读取服务端缓存 |
| 选股与仓位约束 | PASSED（组件） | 15 只、6 板块；单股 ≤10%、板块 ≤25%、现金 ≥5% |
| 研发直跑 | FAILED（外部依赖） | 2026-07-21 12:54：akshare/baostock/yfinance 未补满 49 只，程序按预期中止，未使用部分数据继续计算 |
| 正式多 Agent（成功样本） | PASSED（运行证据） | 2026-07-21 13:06~13:09：Coordinator + Bull + Bear 真实运行；8 个 RPC 均执行成功；49 只、15 持仓、20 个未来收益；行情未进入工具参数 |
| 正式多 Agent（最新样本） | FAILED（外部依赖） | 2026-07-21 13:11~13:16：抓数连续失败 3 次后保护终止；0/8，未伪报成功 |
| 8/8 判据 | PASSED（代码） | 逐项检查 `success=true` 和输出不变量；不再以工具名出现或 5/8 判成功 |
| 重复失败保护 | PASSED（真实失败） | `quant.fetch_data failed 3 times` 后停止；已新增 5 分钟数据源熔断，避免换日期重复轰炸 |
| 时间因果 | PASSED（组件与成功样本） | 训练段止于决策日；测试段含决策收盘并计算随后 20 个交易日收益 |
| 产物审计 | PASSED | 直跑和多 Agent 产物均使用时间戳文件名；保留原始日志和 JSON 摘要 |

## 关键运行证据

- 正式多 Agent 成功日志：`output/multi_e2e_20260721_130620.log`
  - `quant_fetch_data`、`quant_compute_factors`、`quant_bull_view`、`quant_bear_view`、`quant_select_stocks`、`quant_allocate_positions`、`quant_run_backtest`、`quant_generate_report` 全部真实执行。
  - Bull/Bear 为真实子 Agent，存在独立 workspace、任务与消息，不是 Coordinator 伪装。
  - 回测是 20 个前向收益；该次运行收益 `+3.77%` 仅是链路样本，不是比赛成绩或策略验证结论。
- 最新失败摘要：`output/multi_agent_summary_20260721-131112.json`
  - `loop_complete=false`，`0/8`，明确保留失败工具与重试记录。
- 研发直跑失败日志：`output/direct_e2e_20260721_125450.log`、`output/direct_e2e_20260721_125450.err.log`。
- 测试命令：`.venv/Scripts/python -m pytest tests/unit_tests/quant -q`（在 `jiuwenswarm/` 下执行）。

## 发布判断

当前不应写“最新两条真实路径均通过”。可以准确表述为：

1. 数据流、8/8 判据、因果切分、失败关闭与 Agent 编排逻辑已经修复并通过组件测试。
2. 正式 JiuwenSwarm 路径已有一次完整成功证据，且 Bull/Bear 是真实子 Agent。
3. 最新网络状态下三数据源不稳定，直跑和最新正式复跑均诚实失败；待数据源恢复后，应再用同一时间段复跑两条路径并更新本文件。
