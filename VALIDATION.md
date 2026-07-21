# 当前验证状态

> 本文件是当前可运行状态的唯一事实源。组件测试、统一离线回测、研发直跑和 JiuwenSwarm 多 Agent 正式路径是四类不同证据，不能互相替代。

## 最新结论（2026-07-21 15:05，Asia/Shanghai）

- 当前实现：v2.9 Phase A 之上新增五源生产数据链、命名成员装配修复与强制成员归属审计。
- 工程结论：**PASSED**。五源数据链、研发直跑、8个RPC和真正的Bull/Bear成员委派均在本轮真实行情上完成，同轮强制审计通过。
- 策略结论：**未改善**。最新 20 个前向收益为 -6.74%，数据可用不等于策略有效，不能把本轮工程通过表述为初赛提分。
- 生产策略仍为历史六因子。两因子和单动量候选均未通过事前验收标准，未切换生产参数。
- 旧“开发集 +2.21% / 两因子封存 +2.16% / 第二窗口仍封存”的结论撤销：两组数字来自不同模型，且动态验证区间已经与原第二窗口重叠。所有已观察历史现在只视为开发数据。

| 能力 | 状态 | 当前证据 |
|---|---|---|
| 量化单元测试 | PASSED | `23 passed`；包含五源逐只补缺、Sina/Tencent 解析、失败关闭、因果切分与仓位约束 |
| Agent装配回归 | PASSED | `88 passed`；新增命名Bull/Bear模板获得teammate rails与QuantToolkit的回归测试 |
| Phase A 数据快照 | PASSED | Sina 原始 OHLCV，49/49、6/6、500 个指数交易日；CSV gzip + SHA-256 manifest |
| 三基线统一离线评测 | PASSED | 21 个互不重叠开发窗口；同一快照、同一窗口、同一选股/配仓、首日开盘一次买入后固定股数持有 |
| 两因子候选 | DOES_NOT_QUALIFY | 全期改善明显，但最近4窗综合效用只赢2窗，未达到3/4护栏 |
| 单 momentum_20 候选 | DOES_NOT_QUALIFY | 配对中位收益差为 -0.1943 个百分点；综合效用仅赢10/21窗 |
| 集中策略配置 | PASSED（组件） | 研发直跑和 Extension 均从 `strategy_configs.py` 读取同一个生产六因子/仓位配置；行为未切换 |
| 五源生产链 | PASSED | `Sina → Tencent → akshare → baostock → yfinance`，只向下一层请求仍缺失股票；五源统一使用原始收盘价口径 |
| 研发直跑 | PASSED | Sina 49/49、158 个交易日；15只/6板块、现金5.08%；前向20日收益 -6.74%、最大回撤7.98% |
| 正式8 RPC工具链 | PASSED | session `multi-agent-validation-20260721-150232`；49/49、8/8 RPC、`loop_complete=true` |
| 真正多 Agent 协作 | PASSED | leader/Bull/Bear事件数1479/271/1904；Bull和Bear分别亲自调用1次专属视角RPC并发回独立报告 |
| 本轮路径产物审计 | PASSED | 15只、6板块、总仓位94.92%；8工具、成员归属、行情不经LLM、单股/板块/现金约束全部通过 |

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
- 最新直跑结果：`output/pipeline_results_20260721_144247.json`
- 最新直跑审计日志：`output/direct_fivesource_final_20260721_utf8.log`
- 最新正式摘要：`output/multi_agent_summary_20260721-150232.json`
- 最新正式 chunks：`output/multi_agent_chunks_20260721-150232.json`
- 最新正式日志：`output/multi_fivesource_named_members_20260721.log`
- 早期两轮分别暴露输出缓冲和leader代调问题；随后验收器增加成员归属检查，并修复命名成员模板未被装配的问题。旧轮次均未被拼入最新成功证据。

## 复现命令与退出码

在 `jiuwenswarm/` 下：

```powershell
.venv\Scripts\python.exe -m pytest tests\unit_tests\quant -q --no-cov
# 退出码 0：23 passed

.venv\Scripts\python.exe evaluation\unified_baseline_evaluation.py --datalen 500
# 退出码 0：创建快照并完成三个基线

.venv\Scripts\python.exe evaluation\unified_baseline_evaluation.py --snapshot evaluation\data_snapshots\sina_20260721_135352
# 退出码 0：确定性复跑，摘要与首次运行一致

.venv\Scripts\python.exe scripts\run_quant_pipeline.py
# 退出码 0：Sina 49/49；若前层部分失败，只对缺失股票调用下一层；最终不足49只仍失败关闭

.venv\Scripts\python.exe -u evaluation\run_multi_agent.py
# 退出码0：164秒，8/8 RPC，Bull/Bear分别亲自调用专属视角RPC，validation_passed=true。
# 注意：PowerShell 5 将第三方 warning 写入 stderr 时，管道包装层可能返回1；应以摘要 JSON 和审计为准。

.venv\Scripts\python.exe ..\.agents\skills\verify-quant-e2e\scripts\audit_run_artifacts.py `
  --results ..\output\pipeline_results_20260721_144247.json `
  --direct-log ..\output\direct_fivesource_final_20260721_utf8.log `
  --multi-log ..\output\multi_fivesource_named_members_20260721.log `
  --multi-chunks ..\output\multi_agent_chunks_20260721-150232.json
# 退出码 0：E2E AUDIT PASSED；成员事件和角色专属RPC归属均通过
```

## 发布判断

当前可以准确表述为：

1. Phase A 已建立可复现的统一行情快照、因果窗口和首日开盘固定股数回测口径。
2. 三个基线已在同一开发集上完成比较；目前没有候选达到切换生产模型的完整证据标准。
3. 五源逐只补缺链已解除本轮数据阻断；Sina/Tencent 属于无正式 SLA 的网页行情接口，因此仍须保留多源、超时、覆盖统计与失败关闭。
4. 命名成员模板现按teammate能力装配，Team Skill要求分别委派，验收器要求Bull/Bear亲自调用专属RPC；本轮已真实通过。
5. 最新策略前向收益仍为 -6.74%，下一步应研究”近期失效/市态稳定性”和配仓信息传递；最终测试只能使用未来未观察数据或赛事正式评测期。

## Phase B: 2×2 机制实验结果 (2026-07-21)

数据区间：同一 Sina 快照，21 个非重叠窗口。四组事前固定方案对比生产六因子基线。

| 方案 | 因子权重 | 配仓 | 中位收益 | 最差收益 | 中位回撤 | vs生产 Δ中位收益 | 效用胜率 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 生产六因子 | 6因子等权 | 纯逆波动率 | -0.07% | -7.39% | 3.42% | (基线) | — |
| T0 对照 | 0.71/0.29 | 纯逆波动率 | +0.38% | -5.98% | 3.73% | +0.77pp | 15/21 |
| T1 收缩 | 0.85/0.15 | 纯逆波动率 | +0.16% | -6.40% | 3.76% | +0.00pp | 10/21 |
| **T2 得分倾斜** | **0.71/0.29** | **inv-vol × exp(0.20×clip(z,-2,2))** | **+0.50%** | **-6.41%** | **3.22%** | **+0.91pp** | **15/21** |
| T3 联合 | 0.85/0.15 | 得分倾斜 | +0.33% | -6.56% | 3.22% | +0.32pp | 13/21 |

关键发现：
- **volume_trend 收缩到 0.15 不可行**（T1 几乎丢失全部优势）
- **得分倾斜有效**：T2 不仅收益最高，回撤也最低（3.22%），同时改善收益和风险
- 所有候选仍失败”最近4窗≥3赢”标准（全部 2/4），但 7 窗时间块均为正（T0/T2: 3/3）
- **T2 为当前最强 challenger**，状态 CHALLENGER_WITH_RECENT_DECAY；禁止在未开新封存窗口前写入生产配置

## 下一阶段计划

### 策略线
- Phase C: 连续风险暴露实验（市场风险升高时平滑降仓，目标改善尾部回撤）
- 禁止同时修改因子、配仓和择时三个维度

### Agent 深度线 (Codex P0-P5)
- P0: 修复量化 Skill 文档中的过期事实（已完成）
- P1: Symphony 量化规划 POC（三个任务：正常投资分析、数据失败恢复、候选衰减诊断）
- P2: Agent 自主研究闭环（Bull 提出假设 → Bear 反驳 → 预注册 → 实验 → 审计 → 沉淀经验）
- P3: 结构化 Experience Bank
- P4: Evolution suggestion-only（只提流程建议，不改投资参数）
- P5: Cron 主动监控
