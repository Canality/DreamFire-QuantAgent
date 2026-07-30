# 当前验证状态

> 本文件是项目可运行状态的唯一事实源。README、Agent 指令和讨论文档只能引用这里，不得复制长期状态。

## 结论（2026-07-30）

| 对象 | 证据等级 | 结论 |
|---|---|---|
| 量化核心与行情证据链 | BUSINESS_PASSED | direct/formal 共用五源补缺、因果切分、仓位约束、确定性快照与 hash 审计 |
| JiuwenSwarm 多 Agent 路径 | BUSINESS_PASSED | 8/8 量化 RPC；Coordinator/Bull/Bear 均真实参与且角色边界成立 |
| 行情型报告候选包 | BUSINESS_PASSED | 49 份公司报告、组合、行情证据、资源日志完整且独立审计通过 |
| 完整金融分析作品 | PARTIAL | 基本面、公告、新闻、宏观等 point-in-time Provider 尚未接入真实证据链 |
| 正式提交契约 | PROVISIONAL / BLOCKED | 最新答疑与静态文档仍有 3 项冲突，不能把候选包改名为正式提交包 |
| 策略 alpha | RESEARCH_ONLY | 生产仍为六因子；Phase B T2 仅为开发集最强 challenger，未获样本外晋级证据 |

以上结论适用于本次提交的源代码树。`output/` 是本机验收产物，不进入 Git。

## 官方事实裁决

- `赛题文档/上市公司列表.xlsx` 的实际内容为 **49 家、6 个板块**；SHA-256 为 `C021D69B5C3BF3EA0C4626811DF5ED9A02CD4C67E1068AD2F0CE35D759210617`。
- 答疑口述/转录写“50 家”，与 Excel 冲突。本地契约以可校验的 Excel 为当前权威，同时保留向主办方确认的问题。
- 静态赛题介绍允许空仓/半仓；答疑口述称公司权重和为 1，现金口径未明确。
- 静态材料称初赛以客观回测为主；答疑强调报告完整性和可用性影响筛选。
- 资源维度分项文字中出现“Token 10 分但规则写 15 分、运行 5 分但规则写 10 分”的内部矛盾。

因此 `SubmissionContract.can_proceed_formal()` 当前必须失败关闭。解除阻断需要主办方的可归档书面答复，不得由 Agent 自行猜测。

## 本轮真实验收

### 1. 单元测试与静态检查

- 日期：2026-07-30
- 命令：

```powershell
cd jiuwenswarm
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
.\.venv\Scripts\python.exe -m pytest -o addopts='' tests/unit_tests/quant -q
.\.venv\Scripts\python.exe -m ruff check evaluation/run_multi_agent.py evaluation/unified_baseline_evaluation.py jiuwenswarm/quant/reporting jiuwenswarm/extensions/quant-finance/extension.py scripts/run_quant_pipeline.py tests/unit_tests/quant
```

- 结果：`141 passed`，pytest 退出码 0；目标静态检查退出码 0。
- 说明：未把 JiuwenSwarm 上游仓库既有的全库 lint 债务冒充成本项目新增问题。

### 2. 研发旁路

- 命令：`.\.venv\Scripts\python.exe scripts\run_quant_pipeline.py`
- 输入：`2025-06-25` 至 `2026-07-30`
- 退出码：0
- 数据：49/49，6/6，268 个交易日；训练 248 日，前向 20 日
- 组合：15 只，权益 94.94%，现金 5.06%；单股 ≤10%，板块 ≤25%
- 本次历史前向演示：累计收益 `+3.2468%`，最大回撤 `2.8762%`
- Snapshot：`snap_20260730_083130_845296_9a03d3813260`
- 证据：
  - `output/direct_acceptance_20260730_final.log`
  - `output/pipeline_results_20260730_163130.json`

此结果是已知历史区间上的路径验收，不是未来比赛成绩预测。

### 3. JiuwenSwarm 正式多 Agent 路径

- 命令：`.\.venv\Scripts\python.exe -u evaluation\run_multi_agent.py`
- session：`multi-agent-validation-20260730-164030`
- 退出码：0；业务耗时 79.8 秒
- 8/8 RPC：fetch、factors、bull_view、bear_view、select、allocate、backtest、report 全部通过
- 事件归属：Coordinator `588`、Bull `454`、Bear `303`
- 专属 RPC：Bull 1 次、Bear 1 次；无角色越权
- 报告：49/49；20 家含 Bull/Bear AgentView；Quality PASSED
- Snapshot：`snap_20260730_084150_772468_3ce7c414850c`
- 资源实测：
  - Input Tokens `1,204,831`
  - Output Tokens `9,932`
  - Cache Tokens `1,045,760`
  - 工具调用 `32`
  - 峰值工作集 `506.00 MB`
  - CPU 时间 `11.83 s`
  - 最大并发未测量，保持 `null`
- 证据：
  - `output/formal_acceptance_20260730_resource_r4.stdout.log`
  - `output/formal_acceptance_20260730_resource_r4.stderr.log`
  - `output/multi_agent_chunks_20260730-164030.json`
  - `output/multi_agent_summary_20260730-164030.json`
  - `output/submission_candidate/`

### 4. 独立端到端审计

```powershell
.\.venv\Scripts\python.exe ..\.agents\skills\verify-quant-e2e\scripts\audit_run_artifacts.py `
  --results ..\output\pipeline_results_20260730_163130.json `
  --direct-log ..\output\direct_acceptance_20260730_final.log `
  --multi-log ..\output\formal_acceptance_20260730_resource_r4.stdout.log `
  --multi-chunks ..\output\multi_agent_chunks_20260730-164030.json
```

- 退出码：0，`E2E AUDIT: PASSED`
- 审计范围：49 份报告、组合约束、8 个 RPC、角色归属、禁止 LLM 传行情矩阵、唯一快照、prices/volumes gzip、五类 SHA-256、逐 ticker 来源账本、EvidenceRef 本地路径与 hash、正式资源日志及三角色 token 明细。

## 已知问题与竞争风险

1. **资源成本高**：正式运行总输入 token 约 120.5 万。官方基准尚未公布，不能折算分数，但这是当前最明确的工程短板。
2. **Agent 路径有随机性**：本轮曾出现 Agent 在正确配仓后擅自删掉一只股票并二次配仓。正式验收正确失败；Extension 现已把选股、配仓、回测、报告的输入锁定为服务端缓存的前序结果，LLM 只能触发、不能改写。150 秒阶段无进展和 8/8 后显式 runtime teardown 也已加入，但减少 prompt/上下文膨胀仍是 P0。
3. **报告广度不足**：当前 49 份报告主要来自技术面和市场行情，`data_provider_status` 仍为 partial；不能宣称已经完成基本面、公告、新闻或宏观分析。
4. **报告深度不均**：只有进入 Bull/Bear 候选集合的 20 家包含 AgentView，其余公司是确定性技术报告。
5. **策略未完成样本外晋级**：T2 在 21 个开发窗口优于生产，但未完成封存/未来窗口验证，生产配置未切换。
6. **契约未确认**：49/50、现金口径、报告对初赛的作用仍需主办方书面答复。
7. **上游弃用警告**：正式运行出现 Authlib、Pydantic/openJiuwen 弃用警告；当前不影响退出码和业务结果，但升级依赖前必须回归。

## 清理状态

本轮已删除：

- 被 Git 跟踪的旧 `output/submission/`（仅 20 份报告，已过期）
- 5 个历史提交 zip
- 答疑视频/音频中间文件（保留文字稿和结构化笔记）
- smoke/dry-run JSON、转录临时脚本、旧运行日志/候选包
- 不再接入当前测试或正式入口的 v2.6 smoke/verify/holdout 脚本
- 本轮生成的 `__pycache__`、pytest/ruff/coverage/htmlcov/logs 等缓存；复跑测试后重新生成的忽略缓存不进入 Git

保留：

- 官方提交样例 `提交/赛题二提交样例/`
- 官方 Excel、静态赛题材料、文字稿和结构化笔记
- 可复现实验快照与具有研究意义的最终实验 JSON
- 本地参考项目 `参考项目/PA_Agent`，但通过 `.gitignore` 排除

## 下一步完成标准

1. 获取主办方对 3 项契约冲突的书面答复，更新 contract JSON、hash 与负向测试。
2. 将 Agent 上下文和报告生成改为摘要/按需检索，目标是在不降低 8/8 成功率的前提下降低 token。
3. 建立至少一个真实 point-in-time Provider（优先交易所公告），保存原文、URL、发布时间、可用时间和 hash，并双路径验收。
4. 对 Phase B T2 做真正样本外/封存验证；未通过前不得替换生产策略。
5. 最终提交前重新运行本文件全部命令，再生成 zip；不得复用当前候选包冒充正式包。
