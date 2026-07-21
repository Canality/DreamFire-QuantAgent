# 当前验证状态

> 本文件是当前可运行状态的唯一事实源。组件测试、统一离线回测、研发直跑和 JiuwenSwarm 多 Agent 正式路径是四类不同证据，不能互相替代。

## 最新结论（2026-07-21 16:53，Asia/Shanghai）

- 当前实现：Git HEAD `103df19`（v2.11 文档基线）之上新增本地代理评分器和 Phase B 逐窗证据输出；工作树尚未提交。
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
| 本地代理评分器 | PASSED（组件+固定快照） | 5项边界单测通过；生产参考40.00/80，T2为43.57/80；资源未知时保持pending |

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
- **得分倾斜提高收益**：T2自身中位回撤3.22%低于生产的3.42%，但逐日期配对中位回撤差为+0.0986pp（略恶化）；两个口径必须同时披露
- 所有候选仍失败”最近4窗≥3赢”标准（全部 2/4），但 7 窗时间块均为正（T0/T2: 3/3）
- **T2 为当前最强 challenger**，状态 CHALLENGER_WITH_RECENT_DECAY；禁止在未开新封存窗口前写入生产配置

## 本地代理评分（2026-07-21）

官方明确投资组合80分（收益70%、回撤30%）与资源20分（Token/运行/算力为10/5/5），但没有公布参赛队伍标准化分布和资源基准。官方文本还存在“Token标题10分但正文达标15分、运行标题5分但正文达标10分”的内部冲突；本地代理依据维度总分按10/5/5封顶，并把该决定写入结果假设。

`evaluation/local_scoring.py` 不再使用旧 `scoring.py` 的人为收益分段、重叠窗口、收盘价回测和估算资源满分。它读取统一评测的逐窗证据，以生产六因子21窗为冻结经验参考分布：收益占56分、回撤占24分；资源缺少真实测量或官方基准时标记pending并输出总分区间。

| 策略 | 投资期望分/80 | 中位 | P10 | 最差 | 100分制状态 |
|---|---:|---:|---:|---:|---|
| 生产六因子参考 | 40.00 | 45.33 | 8.00 | 4.19 | 40.00~60.00 |
| Phase B T2 | **43.57** | **48.38** | **10.67** | **6.10** | **43.57~63.57** |

这些是本地开发代理分，不是官方成绩或样本外结果。固定证据：`evaluation/phase_b_20260721_165233.json`、`evaluation/local_score_phase_b_t2_latest.json`、`evaluation/local_score_production_latest.json`；方法说明见 `evaluation/LOCAL_SCORING.md`。

复现：

```powershell
.venv\Scripts\python.exe -m pytest tests\unit_tests\quant\test_local_scoring.py -q --no-cov
.venv\Scripts\python.exe evaluation\local_scoring.py `
  --results evaluation\phase_b_latest.json `
  --strategy phase_b_t2_score_alloc `
  --reference-strategy production_six_factor `
  --output evaluation\local_score_phase_b_t2_latest.json
```

### 版本管理审计

- Git提交历史已经使用v2.6~v2.11命名，但仓库实际Git tag只有`v2.5`；版本名目前是提交信息约定，不是完整tag发布体系。
- `VALIDATION.md`此前顶部仍停留在15:05/v2.9+v2.10，而README和后半部分已包含v2.11/Phase B；本轮已同步顶部事实。
- legacy `evaluation/scoring.py`和`evaluation/latest_score.json`继续保留追溯，但不得作为当前评分入口或最新成绩。

## 下一阶段计划

### Agent 能力与初赛分数的传导关系

Agent 能力不会自动提高初赛成绩。只有当决策改变**最终股票、个股权重或现金比例**，并通过因果统一评测证明优于固定策略，才形成初赛 alpha。

| 能力 | 是否改变组合 | 初赛直接价值 |
|---|---|---|
| **T2 得分进入配仓** | 直接改变15只内部权重 | **高**，开发集配对 +0.91pp |
| **Agent 风险暴露选择** | 改变总仓位/现金 | **中高**，目标改善坏窗口回撤 |
| 官方公告风险覆盖 | 排除/降权重大风险股票 | 待验证，需 point-in-time 数据 |
| Experience Bank | 帮助选择已注册策略/仓位档 | 间接，必须实际改变决策 |
| Bull/Bear 对抗 | 可能否决高风险动作 | 间接，取决于否决是否提升效用 |
| Symphony | 选择和排序分析 Skills | 不直接产生收益 |
| Cron | 定时触发数据检查 | 固定持有20日口径下几乎不影响 |
| Evolution | 改进后续流程 | 本次初赛直接价值低，答辩价值高 |

### 受限 Agent 策略选择器

Agent 不自由生成股票和权重，只在 T2 基础组合上从预注册动作中选择：

```text
T2 生成基础 Top 15 与内部权重
  ↓
Experience Bank 检索相似市态和历史机制结果 (as_of_time 安全)
  ↓
Bull 论证收益机会；Bear 检查尾部风险与官方公告
  ↓
Coordinator 只能选择预注册动作：
  A. T2 + 95%总仓位
  B. T2 + 85%总仓位
  C. T2 + 75%总仓位
  D. 对命中已注册官方风险事件的股票执行固定降权/替换
  ↓
确定性 PositionSizer 重新施加约束
```

### 剩余工作优先级

| 优先级 | 项目 | 目标 | 初赛影响 |
|---|---|---|---|
| **1** | T2 生产化 | 统一 StrategySpec + 双路径验收 | **高** |
| **2** | 连续风险暴露实验 | 市场风险高时平滑降仓，减少最差窗口损失 | **中高** |
| **3** | 受限 Agent 策略选择器 | 逐窗历史经验回放验证 | **中** |
| **4** | 官方公告风险覆盖 | 建立 point-in-time 数据库后再决定 | 待验证 |
| **5** | Experience Bank | 为 3/4 提供时间安全的证据检索 | 间接 |
| **6** | Symphony / Evolution / Cron | 规划、审计、持续运行、答辩 | 答辩 |
