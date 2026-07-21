# 当前验证状态

> 本文件是当前可运行状态的唯一事实源。组件测试、统一离线回测、研发直跑和 JiuwenSwarm 多 Agent 正式路径是四类不同证据，不能互相替代。

## 最新结论（2026-07-21 14:08，Asia/Shanghai）

- 当前实现：v2.9 Phase A 提交；原始评测产物保留运行时的 `afe777a + dirty` Git 状态以便审计。
- 总体结论：**PARTIAL**。Phase A 统一评测器和三个真实基线已完成；生产双路径仍因原三数据源不可用而失败关闭。
- 生产策略仍为历史六因子。两因子和单动量候选均未通过事前验收标准，未切换生产参数。
- 旧“开发集 +2.21% / 两因子封存 +2.16% / 第二窗口仍封存”的结论撤销：两组数字来自不同模型，且动态验证区间已经与原第二窗口重叠。所有已观察历史现在只视为开发数据。

| 能力 | 状态 | 当前证据 |
|---|---|---|
| 量化单元测试 | PASSED | `22 passed`；新增首日开盘、固定股数持有、统一配置和窗口因果测试 |
| Phase A 数据快照 | PASSED | Sina 原始 OHLCV，49/49、6/6、500 个指数交易日；CSV gzip + SHA-256 manifest |
| 三基线统一离线评测 | PASSED | 21 个互不重叠开发窗口；同一快照、同一窗口、同一选股/配仓、首日开盘一次买入后固定股数持有 |
| 两因子候选 | DOES_NOT_QUALIFY | 全期改善明显，但最近4窗综合效用只赢2窗，未达到3/4护栏 |
| 单 momentum_20 候选 | DOES_NOT_QUALIFY | 配对中位收益差为 -0.1943 个百分点；综合效用仅赢10/21窗 |
| 集中策略配置 | PASSED（组件） | 研发直跑和 Extension 均从 `strategy_configs.py` 读取同一个生产六因子/仓位配置；行为未切换 |
| 研发直跑 | FAILED（外部依赖） | 2026-07-21 13:55，akshare/baostock/yfinance 为 0/49，退出码1并 fail closed |
| 正式多 Agent 最新摘要 | FAILED（外部依赖） | `loop_complete=false`、0/8；`quant.fetch_data failed 3 times` 护栏触发 |
| 正式多 Agent 历史成功样本 | PASSED（历史运行证据） | 2026-07-21 13:06~13:09 曾完整执行8个 RPC；只证明链路当时可运行，不代表当前发布通过或策略成绩 |
| 本轮双路径产物审计 | NOT PASSED | 直跑在抓数阶段失败，按设计没有生成结果 JSON；审计脚本对缺失结果文件抛出 `FileNotFoundError`，不能用旧结果拼接本轮日志 |

## Phase A 统一基线结果

数据区间：2024-06-27 至 2026-07-20。以下都是开发集统计，不是官方得分或封存集成绩。

| 模型 | 中位20日收益 | 平均20日收益 | 最差收益 | 正收益窗 | 中位回撤 | 最差回撤 | 中位 Sharpe |
|---|---:|---:|---:|---:|---:|---:|---:|
| 生产六因子 | -0.07% | +0.45% | -7.39% | 10/21 | 3.42% | 10.30% | -0.13 |
| 两因子 0.71/0.29 | +0.38% | +1.21% | -5.98% | 13/21 | 3.73% | 10.86% | 0.55 |
| momentum_20 only | +0.70% | +0.59% | -5.85% | 12/21 | 3.27% | 10.60% | 1.26 |

事前晋级规则要求同时满足：配对中位收益差 ≥0.30 个百分点、综合效用胜率 ≥60%、最近4窗至少赢3窗、回撤与最差收益不明显恶化。

- 两因子：配对中位收益差 +0.7673 个百分点，综合效用赢15/21，但最近4窗仅2/4，故不晋级。
- 单动量：配对中位收益差 -0.1943 个百分点，综合效用赢10/21，故不晋级。

注意：单动量自身的中位收益高于六因子，不等于“逐窗收益差的中位数”为正；模型比较必须使用同日期配对差，不能比较两个互不配对的中位数。

## 关键不可变证据

- 快照清单：`jiuwenswarm/evaluation/data_snapshots/sina_20260721_135352/manifest.json`
- 首次结果：`jiuwenswarm/evaluation/unified_baselines_20260721_135404.json`
- 确定性复跑：`jiuwenswarm/evaluation/unified_baselines_20260721_140824.json`
- 最新指针：`jiuwenswarm/evaluation/unified_baselines_latest.json`
- 研发直跑日志：`output/direct_phasea_20260721_135527.log`、`output/direct_phasea_20260721_135527.err.log`
- 正式失败摘要：`output/multi_agent_summary_20260721-135921.json`
- 正式复跑日志（另一独立 session，外层等待超时后人工终止）：`output/multi_phasea_20260721_135936.log`、`output/multi_phasea_20260721_135936.err.log`
- 历史正式成功日志：`output/multi_e2e_20260721_130620.log`

## 复现命令与退出码

在 `jiuwenswarm/` 下：

```powershell
.venv\Scripts\python.exe -m pytest tests\unit_tests\quant -q --no-cov
# 退出码 0：22 passed

.venv\Scripts\python.exe evaluation\unified_baseline_evaluation.py --datalen 500
# 退出码 0：创建快照并完成三个基线

.venv\Scripts\python.exe evaluation\unified_baseline_evaluation.py --snapshot evaluation\data_snapshots\sina_20260721_135352
# 退出码 0：确定性复跑，摘要与首次运行一致

.venv\Scripts\python.exe scripts\run_quant_pipeline.py
# 退出码 1：原三数据源 0/49，按预期失败关闭

.venv\Scripts\python.exe ..\.agents\skills\verify-quant-e2e\scripts\audit_run_artifacts.py `
  --results ..\output\pipeline_results_phasea_20260721_135527.json `
  --direct-log ..\output\direct_phasea_20260721_135527.log `
  --multi-log ..\output\multi_phasea_20260721_135936.log
# 退出码 1：本轮没有 direct result；审计脚本抛 FileNotFoundError。禁止改用旧固定结果拼接。
```

## 发布判断

当前可以准确表述为：

1. Phase A 已建立可复现的统一行情快照、因果窗口和首日开盘固定股数回测口径。
2. 三个基线已在同一开发集上完成比较；目前没有候选达到切换生产模型的完整证据标准。
3. 生产 Agent 的策略配置已集中，但正式路径仍使用六因子，且最新真实运行被原三数据源阻断。
4. 下一步应先研究“近期失效/市态稳定性”和配仓信息传递，继续使用同一快照做有预算的开发实验；最终测试只能使用未来未观察数据或赛事正式评测期。
