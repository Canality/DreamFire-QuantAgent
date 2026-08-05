# Claude Code：Track 2 执行手册

## 协作关系

- Missed：Agent 决策契约、正式编排、资源稳定性、集成、测试和状态记录。
- Goone：公告证据、数据口径、评测和有限预算策略研究。
- Codex：第三方架构审查、反例测试和最终验收。
- 当前交接通道：`.claude/discussion.md`。
- 唯一运行事实源：`VALIDATION.md`。
- 长期开发路线与验收契约：`DEVELOPMENT_PLAN.md`。

不要让每个执行会话都通读五份长文档。角色化加载规则如下：

- Planner / Codex：读取 `CLAUDE.md`、`AGENTS.md`、`DEVELOPMENT_PLAN.md`、当前 discussion 和 `VALIDATION.md`，负责把必要约束写入任务契约。
- Scout / Builder / Critic：先读 `AGENT_WORKFLOW.md`、`coordination/active/<TASK-ID>.md` 和已生成的最小上下文；仅当任务契约显式引用时再读其他长文档。
- Missed / Goone：仍遵守本文件的职责和文件所有权，但模型会话只接收当前任务需要的部分，不用历史聊天代替任务状态。

## 多模型任务交接

- 直接交接以 `coordination/active/<TASK-ID>.md` 和 `output/agent_handoffs/<TASK-ID>/` 为准；标准状态机、风险路由和 token 预算见 `AGENT_WORKFLOW.md`。
- `.claude/discussion.md` 只记录任务建立、风险升级、实现待审、验收裁决和阻塞，不记录逐次搜索与完整日志。
- Qwen 和 DeepSeek 使用不同的 `CLAUDE_CONFIG_DIR`，通过 `scripts/claude-qwen.cmd` 与 `scripts/claude-deepseek.cmd` 启动；不得再通过切换同一份 CC Switch 全局配置协调并行任务。
- Builder 不得自行扩大文件白名单；Critic 必须使用新会话，且不得边审边改。

### Missed 的身份与边界

- 身份：集成工程师和正式路径负责人。
- 唯一写入 Extension、direct/formal 入口、Team/config/toolkit、角色 Prompt 和 E2E audit。
- 负责维护 Coordinator/Alpha/Risk & Evidence 正式路径、清除迁移残留和保障资源稳定性。
- 不自行实现 Provider、改变 Provider 状态语义或修改研究因子。
- 对 Codex 或 Goone 的架构建议负有主动反证责任：发现正式路径不可实现、重复实现、资源回退或验收口径矛盾时，必须在动手前提出质疑，不能为了服从计划而静默实现。
- 质疑必须附调用点、失败测试、资源数据或最小反例，并给出一个不越过文件边界的替代方案。

### Missed 的工作汇报

**每次完成一个工作包或阶段性工作后，必须在 `.claude/discussion.md` 中按照 Discussion 对话格式向 Codex 汇报**：

```markdown
## [Missed → Codex] YYYY-MM-DD：<工作包编号> 完成

### 判断
一句话：完成/部分完成/受阻。

### 证据
- 命令、退出码、产物路径、关键数值变化。

### 建议动作
- 下一步工作或需要 Goone/Codex 配合的事项。

### 需要回复
- 明确的待回答问题，没有则写"无"。
```

- 汇报不等待 Goone 或 Codex 回复——写完即完成本轮工作交接。
- 若工作受阻，必须在"判断"中标注 `BLOCKED` 并说明阻断原因。
- Codex 裁决或 Goone 回复后再继续下一轮工作。

### Goone 的身份与边界

- 身份：量化研究与金融证据负责人。
- 当前第一优先级是 WP1-B0 官方窗口协议：一交易日 embargo、20 日固定股数、首日开盘和末日收盘。
- 随后负责公告 Provider、数据经济口径、分层评测和有限预算 Alpha。
- 可以质疑计划并提出修改，但不能直接改根目录状态文档、`DEVELOPMENT_PLAN.md` 或三个运行入口；通过 discussion 向文件所有者提出。
- 不使用旧污染评分、单次最好窗口或统一 `IC > 0.3` 作为研究门槛。不同方向使用与机制匹配的预筛选指标，最终仍以 20 日收益和最大回撤组合结果裁决。
- 不创建能自动解除 `SubmissionContract` 阻断的本地规则；只能准备 `candidate-only` 应急配置，正式状态仍需可归档官方答复。
- 对 Codex 或 Missed 的研究假设负有主动反证责任：发现时间口径、统计门槛、数据因果或比赛目标不一致时，必须提交可复现实验或代码证据，不得只表达偏好。
- 每次质疑必须提出可执行替代方案、预计成本和停止条件；不得用讨论代替已获授权且无争议的开发。

### 受约束的质疑与裁决

1. 任何人都可以质疑任何计划，但不能越权修改对方文件或先实现后补讨论。
2. 一条质疑必须包含：争议命题、证据、替代方案、影响文件、验收方式；缺一项只记为建议，不暂停开发。
3. 被质疑者应在一次回复中选择 `ACCEPT`、`MODIFY` 或 `REJECT` 并说明证据。双方最多各两轮；已有共识的无争议工作继续并行。
4. 两轮后仍无共识时，由 Codex 按官方规则、时序安全、可复现实验和复杂度依次裁决；若涉及产品目标或新增外部权限，再交给用户。
5. 裁决写入 `DEVELOPMENT_PLAN.md` 后即成为执行契约。没有新证据不得重复开启同一争议；新证据可以发起新版本讨论。
6. 讨论不得降低完成标准：反对 fail-closed、数据因果、双路径一致性或事实分级的方案不进入表决。

## Discussion 对话格式

在 `.claude/discussion.md` 新增消息必须使用：

```markdown
## [发送者 → 接收者] YYYY-MM-DD：主题

### 判断
一句话结论。

### 证据
- 代码、实验或文档证据。

### 建议动作
1. 明确动作、文件所有者和验收条件。

### 需要回复
- 没有则写“无”；不得把阻塞问题藏在正文。
```

- 不使用无接收者的 `### [Goone]`、`### [Missed]`。
- 回复现有消息时必须写清接收者。
- 计划变更先在 discussion 提议，由 Missed 更新正式计划版本；运行事实仍只由真实验收更新。

## 不可违反的原则

1. 不把设计目标、代码存在、单测通过和业务完成混写。
2. 不使用旧 `scoring.py` 的污染分数判断策略。
3. 不因 direct 通过就声称 JiuwenSwarm 正式路径通过，反之亦然。
4. 不把 LLM 文本、工具名出现或“已完成”话术当成 8/8 证据。
5. 不让价格矩阵进入 LLM 上下文。
6. 不信任 LLM 回传的 scores、tickers、weights、portfolio 或 backtest；后续阶段只能读取 Extension 缓存的前序确定性结果。
7. 不用占位 hash、伪来源、假 token 或 0 填补未知值。
8. 不在主办方未澄清时把 `SubmissionContract` 改成 `CONFIRMED`。
9. 不自动 push、tag、打 zip；这些动作需要用户明确授权。

## 当前实现

```
quant-investment Team Skill
├── Coordinator：fetch → factors → select → allocate → backtest → report
├── Alpha Analyst：quant_alpha_view
└── Risk & Evidence Analyst：quant_risk_evidence_view
```

- 五源逐只补缺：Sina → Tencent → akshare → baostock → yfinance。
- 官方 Excel 当前实表为 49 家；业务代码从 contract/stock_pool 读取数量。
- direct/formal 共用量化、报告和 SnapshotWriter 服务。
- 组合约束：15 只、单股 ≤10%、板块 ≤25%、现金 ≥5%。
- 报告候选：49 份公司报告、组合、行情证据和正式资源日志。
- 当前完整状态、最新 session 和阻断项只看 `VALIDATION.md`。

## 开发闭环

1. 在 discussion 写清假设、影响入口和验收判据。
2. 搜索全部调用入口，优先抽共享服务，不复制业务逻辑。
3. 先补负向测试，再实现修复。
4. 运行目标 pytest 与 ruff。
5. 依次跑 direct、formal、独立 E2E audit。
6. 先更新 `VALIDATION.md`，再更新 README/discussion。
7. 检查旧候选、日志、缓存和临时文件；只保留一套当前证据。
8. 用户要求时再 commit；没有授权不 push。

## 常用命令

```powershell
cd jiuwenswarm
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
.\.venv\Scripts\python.exe -m pytest -o addopts='' tests/unit_tests/quant -q
.\.venv\Scripts\python.exe -m ruff check evaluation/run_multi_agent.py jiuwenswarm/quant/reporting jiuwenswarm/extensions/quant-finance/extension.py scripts/run_quant_pipeline.py tests/unit_tests/quant
.\.venv\Scripts\python.exe scripts/run_quant_pipeline.py
.\.venv\Scripts\python.exe -u evaluation/run_multi_agent.py
```

发布前审计命令和当前产物名从 `VALIDATION.md` 复制，不要复用历史 session。

## 当前工作重点

1. 官方评测期为 2026-08-25 至 09-21；WP1-B 已实现一交易日 embargo、20 日固定持股和嵌套外层边界，但当前历史快照仍为 `RESEARCH_ONLY`。
2. WP1-C 的趋势一致性、板块领导力和尾部风险三项冻结 challenger 均未通过预注册门槛；停止继续扫描公式，生产仍为 `production_six_factor`。
3. 保留 150 秒无进展和连续失败 3 次的 fail-closed，并继续降低正式路径 token 与随机性。
4. 公告 Provider 已有 point-in-time 实现与工件，仍需 Windows 正式双路径复验后才能提高报告证据等级。
5. 49/50、现金口径、报告权重需要主办方书面澄清。
