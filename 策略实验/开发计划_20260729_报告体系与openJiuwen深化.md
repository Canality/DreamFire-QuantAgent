# 初赛报告体系与 openJiuwen 深化：可执行开发计划

> 制定者：Codex（第三方架构审查与验收）
> 执行者：Claude Code / Missed
> 策略顾问：Goone
> 日期：2026-07-29
> 状态：APPROVED_FOR_IMPLEMENTATION
> 事实源：运行状态只以根目录 `VALIDATION.md` 为准；本文件只定义目标、步骤和验收契约。

---

## 0. 执行规则

### 0.1 角色边界

- Claude Code 负责实现、局部测试和在 `.claude/discussion.md` 汇报。
- Codex 负责独立代码审查、测试复跑、双路径验收和最终完成判定。
- Goone 负责策略方向建议，不直接修改 Track_2 代码。
- Claude 不得用自己的实现报告替代 Codex 验收。

### 0.2 本轮版本控制规则

本轮覆盖 `CLAUDE.md` 中“每个 Phase 自动 commit/push/打包”的默认规则：

1. Claude 在 Codex 审查前不得 commit、push、tag 或生成正式提交 ZIP。
2. 不覆盖 `output/submission/`；开发产物写入 `output/submission_candidate/`。
3. 不修改或删除现有未提交的 PA_Agent 实验、赛题音视频、Excel、转写稿及用户文件。
4. 每个 Phase 完成后，Claude 只追加 discussion 汇报并等待 Codex gate。
5. Codex 验收全部通过后，再由用户决定是否提交和推送。

### 0.3 证据等级

所有状态必须使用以下等级：

1. `DESIGN_ONLY`：只有本计划或文档。
2. `LOCAL_IMPLEMENTED`：代码存在、局部测试通过。
3. `PATH_PASSED`：真实入口运行成功。
4. `BUSINESS_PASSED`：公司覆盖、报告完整性、事实时序、组合一致性、资源日志和交付物全部通过。

只有 `BUSINESS_PASSED` 可以写“已完成/已修复”。

### 0.4 本轮冻结项

本轮是“报告与框架工程版本”，不得顺手改变交易策略：

- 生产六因子继续作为生产对照。
- T2 继续保持 challenger：
  - 因子：`momentum_20=0.71`、`volume_trend=0.29`
  - 配仓：`inverse_vol × exp(0.20 × clip(score_z, -2, 2))`
  - 单股上限 10%，板块上限 25%
- 不新增 bear 专属权重。
- 不让 LLM 自由生成股票、权重或现金比例。
- 基本面、公告和新闻第一阶段只进入报告；要影响组合必须另开预注册策略实验。

---

## 1. 当前状态评估

### 1.1 已有基础

- 五源行情逐只补缺、49/49 和 6/6 fail-closed 已有历史验收证据。
- 研发旁路和 JiuwenSwarm 正式 8 RPC 路径曾真实通过。
- Bull/Bear 命名成员曾亲自调用专属 RPC。
- Phase A 有同快照、21 个非重叠窗口的统一开发集。
- T2 是当前最强 challenger，但没有未观察样本证明。
- `agent_structured_output.py` 已存在 schema 与 Router 局部实现。

### 1.2 当前阻断问题

1. `VALIDATION.md` 记录的 HEAD 落后于当前 Git HEAD，最新代码不得沿用旧通过结论。
2. 官方静态规则与 7 月 28 日答疑存在三处冲突：
   - 静态规则说初赛客观回测；答疑说报告完整性、可用性影响入围。
   - 答疑说 50 家；官方 Excel 实际为 49 家。
   - 静态规则允许半仓/空仓；答疑说公司权重之和为 1。
3. 当前 `output/submission/` 只有 20 份个股报告。
4. 当前总报告与 `Portfolio.json` 的股票数、权重不一致。
5. 当前报告代码硬编码旧 IC、旧窗口、旧因子结论。
6. 当前资源日志包含估算 Token、CPU 和自评分，不是运行时真实采集。
7. Agent-A schema 没有接入生产调用链。
8. `policy_validator_prototype.py` 没有调用真实 Symphony，且仍残留 `symphony_poc_latest.json` 文件名。

---

## 2. 下一步假设

如果用一套带 `as_of_time` 与来源证据的结构化事实层，同时驱动确定性组合和多 Agent 报告，再用 openJiuwen 的真实编排与领域护栏进行完整性、一致性和资源校验，就能在不改变现有交易策略的前提下，提高报告入围概率、官方复跑成功率和框架使用深度。

---

## 3. 总体交付物

实现完成后，候选运行应生成：

```text
output/submission_candidate/
├── Portfolio.json
├── portfolio_report.md
├── company_reports/
│   ├── 000333.md
│   ├── ...
│   └── <官方清单中的每家公司>.md
├── report_manifest.json
├── evidence_manifest.json
├── resource_usage.json
├── resource_usage.md
├── agent_trace.json
├── symphony_plan.json
├── symphony_execution_trace.json
├── reproducibility.md
└── framework_changes.md
```

要求：

- 报告文件集合必须精确等于运行时官方公司清单。
- 未持仓公司也必须生成报告，并明确 `weight=0` 的证据化原因。
- `Portfolio.json`、总报告、个股报告中的权重必须来自同一对象，不允许分别渲染。
- 任何行情、财务、公告、新闻和回测数字都必须能追溯到 `evidence_manifest.json`。
- 报告不能包含训练期、IC、回测结果等代码未提供的硬编码数字。

---

## 4. Phase R0：官方契约与事实源复位

### 4.1 目标

消除 49/50、现金/满仓、报告是否影响入围等规则不确定性对代码的硬编码污染。

### 4.2 实现

建议新增：

```text
jiuwenswarm/jiuwenswarm/quant/reporting/
├── __init__.py
└── submission_contract.py

jiuwenswarm/jiuwenswarm/quant/reporting/resources/
└── submission_contract.json
```

`SubmissionContract` 至少包含：

```python
@dataclass(frozen=True)
class SubmissionContract:
    company_codes: tuple[str, ...]
    company_names: Mapping[str, str]
    sectors: Mapping[str, str]
    source_file: str
    source_sha256: str
    report_file_extension: str
    equity_weight_rule: str
    allow_cash: bool | None
    report_quality_rule: str
    unresolved_questions: tuple[str, ...]
    contract_status: str
```

规则：

- 公司集合从项目股票池生成，但必须保存官方 Excel 的文件名和 SHA-256。
- 不在 Python、Skill 或验收器中硬编码 49/50；统一使用 `len(contract.company_codes)`。
- 开发模式允许 `contract_status=PROVISIONAL`。
- 正式打包模式若仍有阻断性 `unresolved_questions`，必须 fail-closed。
- `equity_weight_rule` 至少支持：
  - `equities_plus_cash_equals_one`
  - `equities_equal_one`
- 当前默认只能标记为 `PROVISIONAL`，不能替组委会决定冲突口径。

同时修复：

- `policy_validator_prototype.py` 的 `symphony_poc_latest.json` 残留命名。
- `VALIDATION.md` 顶部将当前 HEAD 之后未重新验收的能力标为 `NOT TESTED`，不得删掉历史证据。

### 4.3 测试

新增 `tests/unit_tests/quant/test_submission_contract.py`，至少覆盖：

1. 合同公司代码唯一且为 6 位字符串。
2. 公司、名称、板块映射完全一致。
3. 任意删一家公司，报告集合检查失败。
4. 49/50 都能由配置驱动，不依赖常量。
5. 两种权重规则分别验证。
6. 正式模式遇到未解决阻断问题时失败。
7. Excel/配置 hash 改变时提示合同过期。

### 4.4 Gate R0

- 局部测试退出码 0。
- 代码中新增功能不得出现新的 `==49`、`==50` 业务判断。
- discussion 写清实际修改、测试命令、退出码。
- Codex 通过审查后才能进入 R1。

---

## 5. Phase R1：统一证据模型与确定性报告生成

### 5.1 目标

把报告从硬编码 Markdown 模板改成“结构化事实的确定性视图”。

### 5.2 数据模型

建议新增：

```text
jiuwenswarm/jiuwenswarm/quant/reporting/models.py
jiuwenswarm/jiuwenswarm/quant/reporting/company_report.py
jiuwenswarm/jiuwenswarm/quant/reporting/portfolio_report.py
jiuwenswarm/jiuwenswarm/quant/reporting/quality_gate.py
jiuwenswarm/jiuwenswarm/quant/reporting/package_builder.py
```

核心 schema：

```python
@dataclass(frozen=True)
class EvidenceRef:
    evidence_id: str
    source_type: str
    source_name: str
    source_url: str | None
    period_end: datetime | None
    published_at: datetime | None
    available_at: datetime
    retrieved_at: datetime
    content_sha256: str

@dataclass(frozen=True)
class MetricFact:
    name: str
    value: float | int | str | None
    unit: str | None
    status: str
    evidence_ids: tuple[str, ...]

@dataclass(frozen=True)
class CompanyFactBundle:
    ticker: str
    name: str
    sector: str
    as_of_time: datetime
    portfolio_weight: float
    selected: bool
    technical_facts: tuple[MetricFact, ...]
    fundamental_facts: tuple[MetricFact, ...]
    event_facts: tuple[MetricFact, ...]
    risk_facts: tuple[MetricFact, ...]
    agent_views: tuple["AgentView", ...]

@dataclass(frozen=True)
class ReportQualityResult:
    passed: bool
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    metrics: Mapping[str, float | int]
```

约束：

- 缺数据写 `status=unavailable`，不得填补或猜测。
- `available_at > as_of_time` 的事实不能进入报告。
- 自然语言段落只允许解释已有 fact；其中出现的数值必须能匹配 fact。
- 因子配置、回测统计、市场状态必须作为输入传入，不得写死在模板。

### 5.3 共享服务

- 研发旁路和 Extension `quant.generate_report` 必须调用同一个报告服务。
- 旧 `_build_report_markdown()` 要么删除，要么变成共享服务的薄适配器。
- `run_quant_pipeline.py` 与 Agent 正式路径生成相同 schema 和相同报告文件集合。
- 不覆盖正式 `output/submission/`。

### 5.4 报告章节

每家公司至少包含：

1. 数据时点和来源状态
2. 投资结论与持仓比例
3. 技术/量化分析
4. 基本面分析
5. 估值与同板块比较
6. 公告/事件/新闻
7. Bull/Bear 观点
8. 风险、催化剂和情景
9. 组合角色或零持仓原因
10. 局限性

没有数据的章节仍需存在，明确“数据不可用”，但 quality gate 将其记入缺失率。

### 5.5 Quality Gate

阻断条件：

- 报告代码集合不等于合同公司集合。
- 缺少 `Portfolio.json` 中的公司报告。
- 任一权重在三个产物中不一致。
- 组合权重不满足合同规则。
- 报告引用不存在的 evidence ID。
- 使用决策日之后才可获得的数据。
- 报告仍出现已撤销的 81.7、78.5、旧 IC、8 窗口等事实。
- 报告数字无法映射到结构化事实。

### 5.6 测试

新增：

```text
tests/unit_tests/quant/test_report_models.py
tests/unit_tests/quant/test_company_report.py
tests/unit_tests/quant/test_report_quality_gate.py
tests/unit_tests/quant/test_submission_package.py
```

至少覆盖：

- 全股票池与零权重公司报告。
- 权重差 1e-6 即被发现。
- 未来数据泄露被阻断。
- 缺数据以 unavailable 输出而非幻觉。
- 报告顺序、文件名、hash 可确定性复跑。
- 恶意/异常 Markdown 文本不能注入伪 evidence。

### 5.7 Gate R1

- 单元测试通过。
- 用固定 fixture 生成一套完整候选包。
- 连续两次运行除 `generated_at` 外 hash 一致。
- Codex 随机抽查至少 5 份报告和全部一致性断言。

---

## 6. Phase R2：Agent-A 接入真实报告链

### 6.1 目标

让已有结构化 Agent 输出从孤立模块变成真实路径输入，但不允许改变交易动作。

### 6.2 实现

- 扩展 `FactorEvidence`，增加 `evidence_id` 和实际输入字段名。
- 定义统一的 `AgentView`：

```python
@dataclass(frozen=True)
class AgentView:
    role: str
    verdict: str
    confidence: str
    candidate_tickers: tuple[str, ...]
    warnings: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    unknown_fields: tuple[str, ...]
```

- Bull/Bear Skill 必须输出可解析 JSON；自由文本只能作为可选 `summary`。
- Extension RPC 返回结构化视角并做 schema 校验。
- `AnalysisPlaybookRouter` 接入真实入口，只选择报告分析 playbook。
- Router 不得修改因子、股票列表、权重和现金。
- 字段缺失进入 `unknown_fields`，不调用 LLM 猜测。
- Agent 调用失败时，报告可生成“Agent 分析不可用”的事实性结果，但正式多 Agent 业务验收必须失败。

### 6.3 测试

- malformed JSON fail-closed。
- 引用不存在的股票或 evidence ID fail-closed。
- 相同输入路由相同 playbook。
- Router 输出不改变组合对象。
- Bull/Bear 角色归属正确。
- 缺数据时不发生额外 LLM 重试。

### 6.4 Gate R2

- `agent_structured_output.py` 在真实入口有调用证据。
- 正式路径产物包含 Bull/Bear 的结构化视角。
- 将 Agent 输出替换为不同观点时，组合 hash 不变、报告内容变化。

---

## 7. Phase R3：真实 Symphony 报告编排

### 7.1 目标

消除“伪 Symphony 集成”，生成并执行真实任务图。

### 7.2 实现

Claude 必须先阅读：

- `jiuwenswarm/symphony/orchestration/service.py`
- `artifacts.py`
- `execution_graph.py`
- `planning/`
- 对应 Symphony 单测

建议新增：

```text
jiuwenswarm/evaluation/run_symphony_report_workflow.py
jiuwenswarm/jiuwenswarm/quant/reporting/symphony_adapter.py
```

真实证据链：

```text
任务输入
→ Symphony 真实规划 API
→ plan artifact
→ plan 规范化
→ PolicyValidator
→ execution graph
→ 实际报告任务执行
→ RPC/worker trace
→ plan 与 trace 对账
```

任务图至少包含：

- 合同/公司清单加载
- 行情与指数数据
- 公司事实准备
- Bull/Bear 分析
- 公司报告并发生成
- Portfolio/report 一致性审计
- 资源日志
- 候选包构建

并发规则：

- 使用有界 worker pool，不创建 49 个无限制 Agent。
- 默认并发数由配置决定。
- 相同任务失败 3 次停止。
- 上游失败时依赖任务不得运行。

如果当前 Symphony API 无法完成真实执行，必须：

1. 保存阻断证据。
2. 把状态写成 `BLOCKED`。
3. 不退回手写 DAG 后继续宣称 Symphony 已接入。

### 7.3 测试

- 正常 plan 可执行。
- 缺步骤 plan 被 PolicyValidator 阻断。
- Coordinator 代调 Bull/Bear 被阻断。
- 公司报告缺一份时终止打包。
- plan/trace 多一步或少一步均失败。
- worker 超时与三次失败触发熔断。

### 7.4 Gate R3

- `symphony_plan.json` 来自真实 Symphony API。
- `symphony_execution_trace.json` 与实际调用对账。
- 负向测试能阻断错误计划。
- Codex 审查后才能出现“Symphony 已接入”描述。

---

## 8. Phase R4：基本面、公告与新闻证据层

### 8.1 目标

让报告覆盖技术面之外的金融分析，但不污染量化决策。

### 8.2 Provider 接口

建议新增：

```text
jiuwenswarm/jiuwenswarm/quant/reporting/providers/
├── base.py
├── fundamentals.py
├── disclosures.py
├── news.py
└── registry.py
```

每个 Provider 必须：

- 有明确数据源名称和 URL。
- 保存发布时间、可用时间、抓取时间和正文 hash。
- 有超时、有限重试和逐公司错误记录。
- 不把抓取失败伪装成“无重大事件”。
- 支持固定 fixture 测试和真实 smoke test。

来源优先级：

1. 交易所、巨潮资讯、上市公司公告等一手披露。
2. 可追溯的结构化财务接口。
3. 主流媒体新闻只作补充。

真实性规则：

- 重大财务和治理事实优先使用一手披露。
- 二手新闻必须保留原文 URL；重大负面事件需一手公告或第二独立来源确认。
- 只有标题、抓取失败、时间不明的内容不得生成肯定结论。
- 所有历史回放严格按 `available_at <= as_of_time`。

### 8.3 决策隔离

- 基本面、公告和新闻只写入报告事实层。
- 不得修改选股或配仓。
- 若未来要做事件风险降权，另建 Phase Alpha 实验并预注册动作。

### 8.4 Gate R4

- 固定 fixture 全测试通过。
- 至少三家公司完成真实数据 smoke test，涵盖沪市、深市、科创板。
- 逐字段保留来源和时点。
- 网络失败时报告明确 unavailable，正式提交状态不得误写为完整数据覆盖。

---

## 9. Phase R5：领域 Rails 与资源计量

### 9.1 目标

形成对比赛有直接业务价值的 openJiuwen 框架扩展。

### 9.2 Rails

实现或接入：

- `EvidenceRail`
- `ReportCompletenessRail`
- `PortfolioConsistencyRail`
- `ResourceBudgetRail`

要求：

- Rail 在真实 Agent/Team 运行时执行，不得只是离线脚本同名包装。
- 每个 Rail 输出机器可读事件和 blocker/warning。
- Rail 失败必须体现在最终状态和 trace。

### 9.3 资源采集

运行时自动采集：

- 每角色/每阶段 input、output、cache tokens（模型提供什么就记录什么）。
- 端到端耗时和阶段耗时。
- 进程 CPU time、峰值 RSS。
- GPU/显存：未使用时明确写 0/none，不能估算。
- 重试次数、工具调用数、并发峰值。

禁止：

- 使用旧 `scoring.py` 的资源估计。
- 在没有官方基线时生成确定的资源得分。
- 手写“约 19,700 tokens”等数字。

### 9.4 Gate R5

- `resource_usage.json` 完全由本次运行生成。
- JSON 和 Markdown 来自同一资源对象。
- 缺少模型 usage 时标记 unknown，不填 0。
- 资源 Rail 能在超预算 fixture 中阻断或降级。

---

## 10. Phase R6：候选发布验收

### 10.1 Claude 预检

Claude 完成实现后只做预检，不得宣称发布：

1. 量化单测。
2. 报告/契约/Provider/Rail 单测。
3. 固定 fixture 完整候选包。
4. 研发旁路真实数据运行。
5. JiuwenSwarm 正式多 Agent 运行。
6. Symphony plan/trace 对账。
7. 候选交付物审计。
8. discussion 汇报全部命令、退出码、日期、输入和产物。

### 10.2 Codex 独立验收

Codex 将：

1. 审查完整 diff，重点检查硬编码事实、时序泄露、重复实现和伪集成。
2. 独立复跑单元与负向测试。
3. 使用 `.agents/skills/verify-quant-e2e/SKILL.md` 验收双路径。
4. 核对报告数、公司集合、权重、证据、Agent 角色、8 RPC、Symphony、资源。
5. 抽查至少 5 家公司报告：
   - 2 家持仓
   - 2 家零持仓
   - 1 家数据缺失或风险事件公司
6. 只有业务通过后更新 `VALIDATION.md` 为 PASSED。
7. 未通过项写明 BLOCKED/NOT TESTED，不允许降级措辞。

### 10.3 最终业务断言

- 公司清单与报告集合完全一致。
- 组合、总报告、个股报告权重完全一致。
- 选股列表等于配仓输入。
- 单股、板块、现金/满仓规则满足当前合同。
- 事实全部满足时点因果。
- 每个数字有来源。
- Bull/Bear 及 8 RPC 真实完成。
- Symphony 真实规划并执行。
- 相同失败连续 3 次停止。
- 资源数据来自真实运行。
- README、CLAUDE.md、Skill、报告和 VALIDATION 不再复制互相冲突的完成状态。

---

## 11. 预期效果

### 收益与回撤

- R0-R6 本身不应改变组合，因此理论上收益和回撤应与输入策略完全一致。
- 若报告工程导致组合 hash 改变，视为回归缺陷。
- T2 的历史开发集改善不能写成官方预期收益。

### 报告与入围

- 从 20 份旧报告提升到合同驱动的全公司覆盖。
- 从不可追溯自由文本提升到事实、时点、来源可审计。
- 从报告/Portfolio 不一致提升到单一对象生成和机器校验。

### openJiuwen 深度

- Extension、Team Skill、结构化输出、真实 Symphony、领域 Rails 和资源审计形成同一条路径。
- 框架创新有实际业务作用，而非为了答辩增加模块名。

---

## 12. 主要风险

1. 官方 49/50 和权重规则未澄清，正式打包必须保留阻断门。
2. 财务与公告 Provider 可能受限流或网页变更影响。
3. 全公司报告可能导致 Token 和运行时间膨胀。
4. LLM 可能引用不存在的数字或证据。
5. Symphony API 可能与当前项目封装不匹配。
6. 当前工作树有大量用户未提交文件，Claude 必须避免覆盖。
7. `CLAUDE.md` 中部分历史事实已经过期，不能直接复制进新报告。

缓解方式：

- 合同配置化、Provider 多级失败状态、有界并发、事实 schema、领域 Rails、候选输出目录、分阶段 Codex gate。

---

## 13. 教学要点

1. **报告不是策略本身，而是策略事实的可审计投影**。
2. **Agent 适合做证据综合与不确定性表达；代码适合数字、约束和一致性**。
3. **框架使用深度取决于真实执行链，不取决于文件名或模块数量**。
4. **point-in-time 数据的关键不是发生时间，而是决策时何时可获得**。
5. **完整性和真实性必须分开衡量：章节齐全不等于事实可靠**。
6. **同一事实对象生成组合和报告，才能从源头避免文档与代码漂移**。

---

## 14. Claude 每阶段汇报模板

```markdown
### [Missed / Claude Code] YYYY-MM-DD HH:MM — Phase Rx

#### 0. 理解确认
- 本阶段目标：
- 明确不做：

#### 1. 实现
- 修改文件：
- 新增接口：
- 删除/替换的旧路径：

#### 2. 验证
- 命令：
- 输入：
- 退出码：
- 结果：
- 产物：

#### 3. 声明映射
| 声明 | 实现文件 | 真实入口 | 当前证据等级 |
|---|---|---|---|

#### 4. 风险与未解决项
- blockers：
- warnings：

#### 5. 请求 Codex Gate
- 请求审查 Phase：
- 未 commit / 未 push / 未覆盖正式 submission：是/否
```
