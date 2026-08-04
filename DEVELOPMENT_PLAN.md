# Dream Fire 下一阶段开发计划

| 字段 | 值 |
|---|---|
| 文档版本 | `1.7.0` |
| 状态 | `ACTIVE` |
| 创建日期 | 2026-07-30 |
| 适用基线 | Git `170e904` 及其后续提交 |
| 计划负责人 | Missed / Goone |
| 独立审查与验收 | Codex |
| 运行事实源 | `VALIDATION.md` |

> 本文是长期开发路线和验收契约，由 Git 管理，不随 `.claude/discussion.md` 的当前交接清理而删除。本文中的目标、预计时间和验收标准属于计划，不代表功能已经完成。实际运行状态、命令、退出码和产物只认 `VALIDATION.md`。

## 1. 文档版本管理

### 1.1 版本规则

- 主版本：目标架构、比赛方向或完成定义发生根本变化。
- 次版本：新增、删除或重排工作包，或者改变验收标准。
- 修订版本：措辞、链接、责任人和不改变含义的澄清。

每次修改必须：

1. 更新文档版本和末尾变更记录；
2. 说明改变原因及受影响的工作包；
3. 不覆盖历史失败结论；
4. 若改变策略晋级规则，必须在新实验开始前提交；
5. 若改变运行事实，只更新 `VALIDATION.md`，本文只链接事实源。

### 1.2 文档边界

- `DEVELOPMENT_PLAN.md`：长期目标、架构、工作包和验收契约。
- `VALIDATION.md`：唯一当前运行事实源。
- `.claude/discussion.md`：当前 Agent 交接和待回复事项，可以定期归档或覆盖。
- `策略实验/` 与 `jiuwenswarm/evaluation/*.json`：实验历史证据。
- `README.md`：对外摘要，不复制完整开发计划。

## 2. 当前状态评估

### 2.1 当前架构

```text
五源行情 DataService
        ↓
不可变 Snapshot + 逐 ticker 来源账本 + SHA-256
        ↓
量化核心：因子 → 选股 → 配仓 → 回测
        ↓
Quant Extension：8 个 RPC
        ↓
Coordinator + Bull + Bear Team Skill
        ↓
Reporting Bundle / Quality Gate / 候选包
        ↓
direct + formal + 独立 E2E audit
```

### 2.2 已确认优势

- direct/formal 已共享行情、快照和主要量化实现。
- 行情覆盖、时间切分、选股到配仓传递和最终仓位约束已经可靠。
- 正式 JiuwenSwarm 路径真实完成 Coordinator/Bull/Bear 和 8/8 RPC。
- 候选包具有 EvidenceRef、hash、来源账本和角色级资源数据。
- 数据不足、角色越权、报告缺失和约束失败均能 fail-closed。
- 生产策略和研究 challenger 已分离，旧污染评分不再作为生产证据。

### 2.3 2026-07-30 基线快照

以下仅用于确定下一阶段起点，不随未来运行自动更新：

- direct：49/49、6/6、15 只、现金 5.06%。
- formal：79.8 秒、8/8 RPC、退出码 0。
- 资源：1,204,831 input、9,932 output、1,045,760 cache tokens。
- 报告：49 份，其中 20 家包含 Bull/Bear AgentView。
- 当前候选包为行情型报告，完整金融分析仍是 `PARTIAL`。
- Phase B T2 相对生产在开发集配对收益差约 +0.91pp、效用胜出 15/21，但没有真正样本外晋级证据。
- 官方已确认初赛提交截止为 2026-08-23，评测期为 **2026-08-25 至 2026-09-21，共 20 个交易日**；持仓期内不可调仓。
- 现有 Phase A/B 组合实验使用“决策后下一交易日开盘买入”，尚未模拟提交后 2026-08-24 这个不可见交易日，因此原 T2 数字只能保留为研究线索，必须按 competition-aligned embargo 口径重算。

最新结果必须查看 `VALIDATION.md`，不得引用本节判断当前是否仍通过。

## 3. 核心问题、影响与解决方案

| 编号 | 问题 | 竞争影响 | 解决方案 | 工作包 |
|---|---|---|---|---|
| A1 | Agent 对最终组合的因果作用弱 | 容易被认为是确定性 pipeline 的 Agent 包装 | 引入 `AgentProposal`、`DecisionTrace`、共享 `DecisionAssembler` 和消融实验 | WP0-B |
| A2 | Bull/Bear 消费相同价量信息，且旧 Prompt 允许各自选股、配仓、回测 | 多角色重复流水线、越过职责边界、约束冲突并浪费 token | 保持三 Agent 总数，原子替换为 Coordinator、Alpha Analyst、Risk & Evidence Analyst；迁移后删除旧角色/RPC | WP0-B/C |
| R1 | 49 份报告主要只有行情证据 | 报告完整性和金融研究深度不足 | 先接入真实 point-in-time 公告 Provider，再逐步扩展 | WP0-C |
| R2 | `Quality PASSED` 语义过宽 | 技术报告可能被误报为完整金融分析 | 质量状态分成 technical / partial / full | WP0-C |
| Q1 | T2 只在已观察开发窗口领先 | 收益优势可能过拟合，不能切生产 | 嵌套 Walk-Forward、Bootstrap、外层证据和冻结晋级规则 | WP1-B/C |
| Q2 | 21 窗硬 AND 晋级过于脆弱 | 单个随机窗口可改变结论 | 安全项保留硬门，统计项改成连续证据和置信区间 | WP1-B |
| Q3 | 历史实验决策后下一日入场，官方提交与买入之间隔一个交易日 | 当前 T2/production 比较没有完全复刻比赛信息集 | 增加一个交易日 submission-to-entry embargo，按首日开盘、末日收盘重跑全部基线 | WP1-B |
| D1 | 五源补缺未完全证明经济口径一致 | 企业行动或跨源切换可能污染收益 | canonical 日历、单位、企业行动和跨源重叠检查 | WP1-A |
| D2 | 49 股等权状态代替整个市场 | 股票池结构可能被误判为 market regime | 引入独立基准、宽度和行业状态 | WP1-A |
| E1 | 正式路径输入约 120.5 万 token | 资源分和稳定性存在风险 | 确定性阶段机、最小工具集、摘要和按需检索 | WP1-D |
| E2 | 验证器依赖 `os._exit()` | 生命周期没有正常闭环 | 修复 runtime/session teardown，正常返回退出 | WP1-D |
| G1 | README、Skill 和运行事实仍会漂移 | Agent 按过期说明执行并错误声明完成 | 机器生成摘要和文档契约测试 | WP0-A |
| C1 | 官方规则存在三类冲突 | 正式包格式无法合法确认 | 等待书面答复，以 contract adapter 隔离 | WP2 |

## 4. 目标架构

```text
Point-in-time Evidence Layer
├── MarketDataProvider
├── AnnouncementProvider
├── FundamentalProvider（后续）
├── NewsProvider（后续）
└── Macro/SectorProvider（后续）
        ↓ EvidenceRef + published/effective/observed_at + hash

Research Layer
├── 冻结策略注册表
├── 嵌套 Walk-Forward / Block Bootstrap
└── 无 Agent / 单 Agent / 多 Agent 统一消融

Agent Decision Layer
├── Alpha Analyst：期限对齐趋势、板块领导力和机会提案
├── Risk & Evidence Analyst：尾部风险、公告、证据冲突和有限否决
└── Coordinator：合并机器可读提案并触发确定性后续阶段
        ↓ AgentProposal / DecisionTrace

Deterministic Safety Core
├── 有界分数调整
├── Select
├── Allocate
├── 最终约束断言
└── Backtest
        ↓
Evidence-linked Report + 分级 Quality Gate
        ↓
direct replay / JiuwenSwarm formal / E2E audit
```

架构原则：

1. 必须阶段由确定性状态机保证顺序，LLM 不负责猜下一步 RPC。
2. Agent 只在经过批准的有界动作空间中影响组合。
3. 每个组合变化必须追溯到 Agent、EvidenceRef 和合并规则。
4. direct 可重放 formal 的 proposal bundle；两条路径调用同一个决策服务。
5. 报告文本不能绕过决策服务修改股票、仓位或回测结果。
6. 保持 Coordinator + 2 名专职成员，不增加常驻 Event Agent；公告由 Provider 提供，Risk & Evidence Analyst 消费。
7. `bull/bear/range` 可以继续作为市场状态标签，但不得继续作为 Agent 身份或工具权限名称。

## 5. 全局完成定义

1. 代码存在只是 `LOCAL_IMPLEMENTED`，不能写“完成”。
2. 涉及正式能力时必须验证 direct/formal 和业务产物。
3. 决策日之后发布或可用的证据必须被拒绝。
4. 数据、证据、proposal、选股配仓或约束失败时不得生成正式候选。
5. 实验记录 git commit、dirty 状态、snapshot/hash、配置 hash、窗口和随机种子。
6. 研究修改不得静默改变 `PRODUCTION_STRATEGY`。
7. 每个工作包独立提交和验收，避免数据、策略、Agent 和报告同时变化。
8. 真实复跑后先更新 `VALIDATION.md`，再生成 README 摘要。
9. 每个工作包必须在提交说明中列出 `KEEP / REPLACE / DELETE`；只新增新实现而保留已被替代的活动路径，不得判定完成。
10. 资源是每个集成工作包的横向约束：以最近一次已接受正式运行作为基线，input token 回退超过 5% 时标记 `RESOURCE_REGRESSION` 并解释或修正；它不是业务完成状态，也不得被写成 `BLOCKED` 来冒充外部阻断。

### 5.1 全局减法清单

| 工作包 | 保留 | 替换 | 删除或退出活动路径 |
|---|---|---|---|
| WP0-A | `VALIDATION.md` 单一事实源 | README/Skill 动态数字改为生成或引用 | 重复维护的 token、窗口、session、历史“已修复”状态 |
| WP0-B | Coordinator + 2 成员、8 阶段、市场 regime 的 bull/bear 标签 | Bull/Bear 角色改为 Alpha / Risk & Evidence | 旧角色 Prompt、RPC、缓存键、persona、parser、权限和验收规则 |
| WP0-C | EvidenceRef 与不可变归档 | 二元 `Quality PASSED` 改为分级质量状态 | “无公告=抓取失败”的混合状态、无证据却宣称完整报告的路径 |
| WP1-A | 五源逐 ticker 补缺能力 | 行情获取抽成 direct/formal 共用数据服务 | Extension 内被共享服务替代的内联数据源实现和重复标准化逻辑 |
| WP1-B | 历史 JSON 作为研究档案 | 活动评测入口改为一交易日 embargo 的官方口径 | 旧“决策后下一日买入”结果的 `latest`/晋级资格，不删除历史证据文件 |
| WP1-C | 冻结基线和失败实验 | 最强通过候选进入提交策略注册表 | 未通过 challenger 的活动注册项和临场调权入口 |
| WP1-D | 必需 Agent 判断和角色专属工具 | 固定阶段改由确定性状态机，数据改按需检索 | `os._exit()`、重复全量上下文、无关工具暴露和重复阶段规划 |
| WP2 | 可归档官方答复与 contract hash | provisional adapter 改为确认后的版本 | 被官方答复否定的假设、旧提交格式和过期候选包 |

删除规则：

1. 先有替代实现和负向测试，再删除旧路径；不能先删到正式路径不可运行。
2. 项目内部 API 不为“可能有人调用”长期保留兼容别名；全部已知调用点迁移后直接删除。
3. 历史实验、旧运行证据和 discussion archive 可以保留旧术语，但必须明确 `historical`，不能被当前入口读取。
4. 删除后用 `rg`、导入测试、direct/formal 和 E2E audit 证明旧路径不可达。

### 5.2 横向资源预算

基准正式运行 input token 为 `1,204,831`。每个涉及 formal 上下文的工作包都必须记录变更前后同输入、同模型、同工具版本的资源：

| 工作包 | 资源门 |
|---|---|
| WP0-B | 新角色替换后不得高于基准；应删除 Bull/Bear 重复上下文 |
| WP0-C | 原文留在服务端，只传有界摘要/EvidenceRef；接入后不得比最近已接受运行高 5% |
| WP1-B/C | 研究评测不把行情矩阵交给 LLM；生产候选不得新增常驻 Agent 或全量因子上下文 |
| WP1-D | 最终 input token ≤602,416，即相对基准至少降低 50% |

超过阶段资源门不抹掉功能测试结果，但不能声称该工作包的集成验收完成；先记录 `RESOURCE_REGRESSION`、定位阶段/角色/tool schema，再压缩或给出经用户接受的收益理由。

## 6. 工作包

### WP0-A：事实源、Skill 与文档契约

优先级：P0。预计 0.5–1 天。

实现：

- 修正 Team Skill 中 11 个 IC 窗口与 21 个组合窗口的混写。
- 数据长度从配置读取，不写死 180 天。
- 明确生产固定 15 只和服务端阶段缓存。
- 删除会随实验变化的静态 IC、overlap 和历史状态，改为引用产物。
- 从验收产物生成 `validation_summary.json`。
- README 状态摘要由生成脚本更新。
- 增加文档契约测试。

验收：

- Skill 中不存在窗口、数据天数、持仓数量和阶段传递矛盾。
- README 的 session、token 和状态与生成摘要一致。
- 故意制造 README 漂移时测试必须失败。
- 没有真实运行时不得改变 `VALIDATION.md` 的通过状态。
- 目标 pytest、ruff 和 `git diff --check` 退出码 0。

### WP0-B：Agent 决策契约与消融

优先级：P0。预计 2–3 天。

实现：

- 用 **Alpha Analyst** 替换 Bull Analyst：
  - 只负责 20 日期限对齐趋势、板块领导力和机会排序；
  - 只能调用 `quant_alpha_view`；
  - 输出有证据的 `AgentProposal`，不得调用 select/allocate/backtest/report。
- 用 **Risk & Evidence Analyst** 替换 Bear Analyst：
  - 负责极端下行风险、集中度、公告、证据冲突和有限 veto；
  - 只能调用 `quant_risk_evidence_view`；
  - 不提供自由现金比例或自行生成防守组合。
- Coordinator 独占 fetch/factors/select/allocate/backtest/report 的阶段触发权；成员只能提交 proposal。
- 新增 `AgentProposal`：角色、ticker、动作、调整、置信度、证据、原因和有效期。
- 新增 `DecisionTrace`：基础分、各角色调整、合并分、组合影响和拒绝原因。
- 新增共享 `DecisionAssembler`。
- 无证据提案影响为 0；未来证据、越界调整和非法 veto fail-closed。
- 普通调整和重大风险 veto 均使用预注册边界。
- 建立 A0 无 Agent、A1 Alpha 单 Agent、A2 Alpha + Risk & Evidence 统一消融。

原子迁移与删除：

1. 新增 `alpha_analyst.md`、`risk_evidence_analyst.md` 和两个新 RPC。
2. 同一工作包内迁移 Team config、toolkit 权限、Skill、缓存键、报告 parser、Symphony stage、runner 和 E2E audit。
3. 迁移完成后直接删除旧角色文件 `bull_analyst.md`、`bear_analyst.md`。
4. 删除旧 `quant_bull_view`、`quant_bear_view` / `quant.bull_view`、`quant.bear_view` handlers，不保留双逻辑兼容层。
5. 删除 `_bull_result`、`_bear_result`、`parse_bull_bear_pair`、`BULL_PERSONA`、`BEAR_PERSONA` 等旧角色专用符号。
6. 历史日志、实验 JSON 和归档文档可保留旧名称；生产代码、当前 Skill、当前文档和当前测试不得残留。

验收：

- 有效 proposal 能改变排名或仓位并留下完整 DecisionTrace。
- 相同 proposal bundle 重放结果确定；direct/formal 使用相同 assembler。
- LLM 不能传价格矩阵或覆盖确定性的选股、配仓和回测对象。
- A0/A1/A2 输出同口径收益、最大回撤、P10、效用和组合差异。
- 必须用机器指标证明 Agent 是否改变决策，不能以生成文本代替。
- 新正式路径仍为 8/8：fetch、factors、alpha_view、risk_evidence_view、select、allocate、backtest、report。
- Alpha 和 Risk & Evidence 各亲自调用唯一专属 RPC；Coordinator 代调或成员越权均失败。
- 当前生产代码、Skill、配置和测试中搜索旧角色标识必须为 0；市场状态枚举和历史归档不计入。
- 删除旧角色后，49/49、6/6、最终仓位约束、报告和独立 E2E audit 仍全部通过。
- 资源比较必须报告新旧角色 token；若新架构未减少重复工具调用或上下文，WP0-B 只能记为 `PATH_PASSED`，不能写 Agent 架构改进完成。

### WP0-C：首个真实公告 Provider 与报告分级

优先级：P0。预计 2–4 天。

WP0-Ca（接口与真实 Provider，可与 WP1-B0 并行）：

- 先实现可信交易所/公司公告，不同时扩张全部新闻和宏观。
- Evidence 保存 URL、发布时间、生效时间、Agent 可用时间、抓取时间、正文 hash 和本地归档。
- 区分 `available_with_events`、`available_no_event`、`unavailable_with_reason`。
- 完成 Provider contract、固定 fixture 和至少一个真实 point-in-time Provider。

WP0-Cb（归档与报告集成，可与 WP1-A/B 并行）：

- 完成离线 evidence archive、篡改检测、报告服务接线和质量分级。
- 49 家生成确定性基础档案，候选约 20 家做 Agent 分析，最终 15 家做完整投资论证。
- Quality Gate 分成 `TECHNICAL_PASSED`、`FINANCIAL_PARTIAL`、`FULL_REPORT_PASSED`。
- 原始公告正文和全量列表不得进入 LLM 上下文；只传有长度上限的摘要、EvidenceRef 和按需检索 id。

验收：

- 固定归档可离线重放，断网缓存不得冒充实时抓取。
- 未来公告和被篡改 hash 必须失败。
- 最终报告中每条可验证事实均能解析到 EvidenceRef。
- 49 家都有 Provider 状态；没有事件和获取失败不能混淆。
- direct/formal 对同一 evidence snapshot 生成相同 bundle/hash。
- 只有行情证据时最高只能是 `TECHNICAL_PASSED`。
- WP0-C 接入后的正式 input token 不得比接入前最近一次已接受运行高 5% 以上；超出时保留功能证据但标记 `RESOURCE_REGRESSION`，先做摘要/按需检索优化。

### WP1-A：数据经济口径与市场状态

优先级：P1。预计 2–3 天。

实现：

- canonical 交易日历、停牌规则、价格和成交量单位。
- 跨源重叠区间误差检查和来源切换异常检测。
- point-in-time 企业行动处理。
- 记录 raw、企业行动调整和可交易收益口径。
- Regime 引入独立市场基准、市场宽度和行业状态。
- 因子实验输出行业中性结果。

验收：

- 构造分红/送转时不出现虚假收益跳变。
- 跨源误差超过预注册阈值时 fail-closed。
- direct/formal 的交易日、停牌和缺失值处理一致。
- Regime 同时输出市场、股票池和行业分量。
- 实验记录 adjustment policy、calendar id 和 provider mix。

### WP1-B0：官方窗口协议与统一基线

优先级：P0，立即执行，不依赖 WP0-C。

实现：

- 新建唯一共享的 `CompetitionWindowPolicy`，明确 `embargo_trading_days=1`、`holding_days=20`、`entry=open`、`exit=close`。
- 评测入口先使用该协议重跑 production、T2 和三个统一基线；旧入口保留历史 JSON，但退出活动 `latest` 和晋级路径。
- Goone 负责协议、评测实现和单测；Missed 后续只把同一协议接入 direct/formal，禁止复制日期切分逻辑。

验收：

- 日期序列严格为 `decision close → 完整 embargo 日 → entry open → 20 个 valuation dates → 第 20 日 close`。
- 故意把 embargo 日数据注入因子或证据时测试失败。
- production、T2 和三个基线在同一 snapshot、窗口和成本口径下输出逐窗 paired table。
- 原 T2 `+0.91pp / 15/21` 被明确标记为旧口径，不再驱动晋级。

### WP1-B：分层评测与策略晋级

优先级：P1。预计 1–2 天。

官方评测协议：

- 提交截止：2026-08-23。
- 信息截止：市场行情最晚只能使用 2026-08-21 收盘；公告等证据不得晚于实际提交时间。
- Embargo：2026-08-24 是提交后、买入前的不可见交易日。
- 买入：2026-08-25 开盘。
- 卖出：2026-09-21 常规交易收盘。
- 持有：20 个交易日，固定股数，不调仓。

所有历史窗口必须模拟同一信息结构：

```text
decision close → 1 个完整交易日 embargo → entry open
               → 20 个交易日固定股数 → 第 20 日 close
```

原有“decision close → 下一交易日 open”的 Phase A/B 结果可以保留为历史诊断，但不得继续作为比赛策略晋级证据。

硬安全门：

- 无泄漏；
- 股票和板块覆盖完整；
- 选股配仓一致；
- 仓位约束通过；
- 尾部收益和回撤无灾难性恶化。

连续研究证据：

- 20 日累计收益及配对收益差；
- Block Bootstrap 区间；
- 效用胜率及区间；
- 中位、均值、P10 和最差收益；
- 中位和最差最大回撤；
- 近期加权表现；
- 分 regime 稳定性。

收益和最大回撤是正式优化目标；Sharpe、长期 IC 和行业中性收益只作诊断，不得替代官方 20 日累计收益。

建议晋级规则：

- 配对中位收益差 ≥0.30pp；
- Bootstrap `P(delta > 0)` ≥80%；
- P10 收益和中位最大回撤满足预注册非劣界；
- 近期表现作为加权证据，不再让最近 4 窗 3/4 单独一票否决；
- 必须有未参与内层选择的外层证据。

验收：

- train/decision/test 日期机器可读且无泄漏。
- 每个窗口记录 `decision_date`、`embargo_date`、`entry_date`、20 个 valuation dates 和 `exit_date`。
- 测试必须证明 embargo 日的行情、公告和因子值完全不能进入决策。
- 买入使用 entry 日开盘，卖出使用第 20 个交易日收盘，期间固定股数且不调仓。
- 调参代码不能访问外层结果，故意泄漏测试必须失败。
- 输出逐窗 paired table、Bootstrap 分布和风险非劣判断。
- 同一 snapshot/config/seed 重跑一致。
- dirty run 不得成为生产晋级证据。
- competition-aligned 基线重跑前不得沿用原 T2 +0.91pp 结论；策略选择结果必须明确标注旧口径与新口径。

### WP1-C：有限预算 Alpha 研究

优先级：P1。依赖 WP1-A/B。

比赛目标：

> 在 2026-08-25 至 09-21 这个固定 20 日窗口中，目标是提高组合绝对累计收益并控制最大回撤，而不是证明长期行业中性 Alpha。行业与市场 Beta 若能在提交前的可见信息中稳定指向短期强势方向，应被视为潜在收益来源，而不是先验污染。

下一步假设：

> T2 的中短期动量可以作为底座；20 日趋势一致性、板块领导力和只针对极端风险的非对称惩罚，可能比全面行业中性或普遍降 Beta 更贴合官方 20 日收益/回撤目标。

第一轮最多测试三个方向，每次只改变一个机制：

1. **20 日期限对齐的趋势确认**
   - 保留 T2 的 `momentum_20 + volume_trend`。
   - 增加一个预注册的 5/10/20 日趋势一致性或加速度确认，不连续扫描周期和权重。
   - 目标是识别在买入后 20 日仍可能延续的趋势，而不是优化长期 IC。
2. **板块领导力 Tilt**
   - 保留个股 T2 裸分，加入有界的板块相对强度和板块宽度调整。
   - 允许主动保留有利行业暴露，但最终板块权重仍不得超过 25%。
   - 行业内标准化残差动量只作为诊断对照，用于解释收益来自个股还是板块，不再作为默认主方向。
3. **非对称尾部风险 Overlay**
   - 只对极端下行波动、跳空风险或近期深回撤的股票做有界削减。
   - 不做全面 Beta 中性，不普遍压低高波动股票。
   - 只有回撤改善足以补偿收益损失时才允许晋级。

固定约束：单股 ≤10%、板块 ≤25%、现金 ≥5%。

机制预筛选：

- 不设置统一 `IC ≥0.3` 门槛。横截面 IC 的合理量级、样本数和适用性随机制不同，统一高阈值会误杀有效信号，也无法评估风控 overlay。
- 期限对齐趋势使用 20 日目标的 rank IC、符号稳定性和分窗口组合结果预筛。
- 板块领导力因只有 6 个板块，优先使用板块命中率、宽度一致性和配对组合结果，不以单个 IC 数值裁决。
- 尾部风险 overlay 使用 P10/最差收益、最大回撤改善及相应收益成本预筛。
- 预筛只决定是否占用 challenger 实现预算；最终晋级仍使用 WP1-B 的 20 日收益、最大回撤和外层证据。

行业中性残差动量诊断：

- 在基础因子算完后、组合构建前，仅由 evaluation 路径计算，不进入 production runtime。
- 输出到 `jiuwenswarm/evaluation/diagnostics/industry_neutral_momentum_<timestamp>.json`，包含窗口、snapshot/config hash、原始与残差信号、IC、收益归因和 paired portfolio 结果。
- 只有机制预筛证据成立时，才允许占用后续一轮的一个 challenger 名额；之后仍须完整通过 WP1-B，不能凭“更纯”自动晋级。

公告事件 overlay 的处理：

- WP0-C 仍需完成，因为它对 Agent 和报告完整性有直接价值。
- 第一轮默认不占三个 Alpha challenger 名额，因为当前历史 point-in-time 覆盖尚未建立。
- 若 WP0-C 在策略冻结前形成足够历史覆盖并能完成同口径事件消融，公告 overlay 可替代一个预筛失败的第一轮名额，或进入第二轮；每轮总数仍不得超过 3。
- 没有收益/回撤增量时，公告证据只进入报告，不影响组合。

最终决策策略：

- 所有候选的公式、阈值和 regime 路由必须在使用 2026-08-21 收盘数据前冻结。
- 最终 Agent 只能根据截至提交时可见的结构化状态，在已注册策略中按预注册规则路由。
- 禁止看到当前候选输出后由人或 Agent 临场修改权重公式。
- 2026-08-24 行情在提交时不可见，最终流程和历史实验都不得使用。

内部赛前时间表：

- 2026-08-10 前：完成 WP0-B/C 和 WP1-A/B 的可用版本，至少能按 embargo 新口径重跑统一基线。
- 2026-08-15 前：完成第一轮三个 challenger，冻结公式、阈值、策略注册表和路由规则。
- 2026-08-16 至 08-20：只做反例、故障、资源和报告验收，不再根据收益结果增加候选。
- 2026-08-21 收盘后：冻结最终市场数据 snapshot。
- 2026-08-22：运行最终 Agent、生成候选包、独立审计和离线复现。
- 2026-08-23：在官方截止时间前提交；若官方公布精确时刻，以更早者为内部截止。

验收和停止规则：

- 每轮最多 3 个 challenger，不根据结果继续微调同一候选权重。
- 每个 challenger 必须在带 1 个交易日 embargo 的 20 日官方口径下通过内层研究和外层证据。
- 不删除失败实验，必须记录失败原因。
- 行业中性版本只作为诊断；不能因为它“更纯”就自动晋级。
- 三个方向均失败后停止 Alpha 搜索，使用 competition-aligned 统一评测中最强的冻结基线，不继续调权重。
- Agent overlay 没有样本外增量时，可以保留报告能力，但不得影响组合。
- 最终报告必须同时披露预期收益来源是个股、板块还是市场暴露，不能把 Beta 收益包装成长期个股 Alpha。

### WP1-D：资源压缩与运行稳定性

优先级：P1，可与 WP1-A 并行。

实现：

- 8 个必需阶段改由确定性状态机调度。
- Coordinator 使用阶段摘要，Agent 不接收价格矩阵和重复全历史。
- 每个 Agent 只暴露最小工具集。
- 大数据留在服务端，通过 id/hash 按需检索。
- 记录每阶段、角色和工具 schema 的 token。
- 修复 runtime/session 正常关闭，移除 `os._exit()`。

验收：

- 同一 snapshot 做 20 次无 LLM replay，20/20 结果一致。
- 3 次完整正式 Agent 运行均完成 8/8，无越权、悬挂和非法重试。
- 相比 1,204,831 input token 降低至少 50%；未达到时资源项不能标记完成。
- 单次 P95 耗时 ≤120 秒，峰值工作集 ≤600 MB。
- `max_concurrency` 有真实测量值。
- 进程通过正常返回结束。
- 同一失败工具连续 3 次后停止并输出诊断。

### WP2：正式契约与最终发布

状态：`BLOCKED`，依赖主办方书面答复。

待确认：

1. 公司数量以 Excel 49 家还是口述 50 家为准；
2. 权重和为 1 是否包含现金；
3. 报告完整性是否影响初赛；
4. Token 10/15 分和运行 5/10 分的冲突口径；
5. 2026-08-23 的精确提交截止时刻。

验收：

- 书面答复归档并生成 contract version/hash。
- `SubmissionContract.can_proceed_formal()` 只在契约完整时返回 true。
- contract adapter 适配提交格式，不污染研究核心。
- 最终包股票、权重、现金和报告数量与 contract 一致。
- zip 可在干净目录离线校验 schema、hash 和文件集合。
- 最终 commit 工作树干净，完整命令、日期、输入、退出码和产物写入 `VALIDATION.md`。

无官方回复的准备边界：

- 2026-08-05 前在现有 contract 测试中准备若干 `candidate-only` 配置，例如以可校验 Excel 的 49 家为股票全集，并分别表达现金是否计入权重和的歧义。
- 这些配置只用于提前跑候选包、暴露格式风险，不新增并行正式实现，也不单独创建会漂移的 `FALLBACK_RULES.md`。
- 日期到达或组织方沉默不得自动令任何配置生效；`SubmissionContract.can_proceed_formal()` 仍保持 false，直到书面答复被归档并生成 contract hash。
- 若临近截止仍无回复，由用户基于候选包选择是否承担规则解释风险；Agent 不得自行把 provisional 改成 confirmed。

## 7. 依赖顺序、分工与文件所有权

```text
WP0-A 事实收敛 ─────────────┐
                            ├→ WP0-B Agent 决策契约 → A0/A1/A2 消融
WP0-Ca Provider → WP0-Cb 归档/报告 ─────────────┘

WP1-B0 官方窗口协议/统一基线（立即、独立）─┐
WP1-A 数据口径 ────────────────────────────┴→ WP1-B 分层评测 → WP1-C Alpha 研究

资源预算贯穿每个集成工作包；WP1-D 做集中压缩并在新 Agent 架构上复验
WP2 等待官方书面契约，任何 Agent 都不能自行解除
```

### 7.1 两人分工

- **Missed：集成与 Agent 线**
  - WP0-A：事实源、Skill 和文档契约。
  - WP0-B：`AgentProposal`、`DecisionTrace`、`DecisionAssembler`、A0/A1/A2 消融。
  - WP1-D：确定性编排、资源压缩、正式运行稳定性。
  - 唯一负责 Extension、direct/formal 入口和根目录状态文档的集成。
- **Goone：证据、数据与策略线**
  - WP1-B0：共享官方窗口协议和 competition-aligned 统一基线，立即执行。
  - WP0-C：公告 Provider、EvidenceRef、报告分级与质量门。
  - WP1-A：数据经济口径、企业行动和市场状态。
  - WP1-B：嵌套评测、Bootstrap 和晋级证据。
  - WP1-C：有限预算 Alpha 研究。
- **Codex：独立审查**
  - 不参与两人的日常文件写入。
  - 每个工作包完成后做反例测试、双路径验收和完成状态判定。

### 7.2 第一阶段可立即修改的文件

#### Missed 白名单：WP0-A / WP0-B

现有文件：

- `README.md`
- `CLAUDE.md`
- `AGENTS.md`
- `DEVELOPMENT_PLAN.md`（只允许更新版本、状态和变更记录）
- `.claude/discussion.md`
- `jiuwenswarm/jiuwenswarm/quant/agent_structured_output.py`
- `jiuwenswarm/jiuwenswarm/quant/team_config.py`
- `jiuwenswarm/jiuwenswarm/quant/__init__.py`
- `jiuwenswarm/jiuwenswarm/quant/roles/bull_analyst.md`（迁移后删除）
- `jiuwenswarm/jiuwenswarm/quant/roles/bear_analyst.md`（迁移后删除）
- `jiuwenswarm/jiuwenswarm/quant/reporting/models.py`（仅 WP0-B 角色字段迁移）
- `jiuwenswarm/jiuwenswarm/quant/reporting/agent_view_parser.py`
- `jiuwenswarm/jiuwenswarm/quant/reporting/company_report.py`
- `jiuwenswarm/jiuwenswarm/quant/reporting/symphony_adapter.py`
- `jiuwenswarm/jiuwenswarm/quant/reporting/__init__.py`（仅导出迁移）
- `jiuwenswarm/jiuwenswarm/extensions/quant-finance/extension.py`
- `jiuwenswarm/jiuwenswarm/extensions/quant-finance/skills/quant-investment/SKILL.md`
- `jiuwenswarm/jiuwenswarm/resources/agent/workspace/skills/quant-investment/SKILL.md`
- `jiuwenswarm/jiuwenswarm/resources/config.yaml`
- `jiuwenswarm/jiuwenswarm/agents/harness/common/tools/quant_toolkits.py`
- `jiuwenswarm/jiuwenswarm/agents/harness/team/team_runtime_inheritance.py`
- `jiuwenswarm/jiuwenswarm/agents/swarm/providers/tools.py`
- `jiuwenswarm/jiuwenswarm/agents/swarm/assembly.py`（只改角色示例/注释）
- `jiuwenswarm/evaluation/run_multi_agent.py`
- `jiuwenswarm/evaluation/policy_validator_prototype.py`
- `jiuwenswarm/scripts/run_quant_pipeline.py`
- `.agents/skills/verify-quant-e2e/SKILL.md`
- `.agents/skills/verify-quant-e2e/scripts/audit_run_artifacts.py`
- `jiuwenswarm/tests/unit_tests/quant/test_agent_structured_output.py`
- `jiuwenswarm/tests/unit_tests/quant/test_agent_view_parser.py`
- `jiuwenswarm/tests/unit_tests/quant/test_extension_cache_pipeline.py`
- `jiuwenswarm/tests/unit_tests/quant/test_symphony_adapter.py`
- `jiuwenswarm/tests/agents/swarm/test_swarm_assembly.py`

允许新增：

- `scripts/generate_validation_summary.py`
- `jiuwenswarm/jiuwenswarm/quant/agent_decision.py`
- `jiuwenswarm/jiuwenswarm/quant/roles/alpha_analyst.md`
- `jiuwenswarm/jiuwenswarm/quant/roles/risk_evidence_analyst.md`
- `jiuwenswarm/evaluation/agent_ablation.py`
- `jiuwenswarm/tests/unit_tests/quant/test_agent_decision.py`
- `jiuwenswarm/tests/unit_tests/quant/test_document_contract.py`

特殊规则：

- `VALIDATION.md` 只在真实复跑完成后由 Missed 更新，开发中不得预写通过状态。
- Missed 在 WP0-B 可修改 `reporting/models.py` 的 AgentView 角色约束、parser、company report 和 Symphony stage；角色迁移提交完成后，这些 reporting 文件所有权转交 Goone。
- Missed 不修改 `reporting/providers/`、`quality_gate.py`、Provider 状态语义和策略因子文件。

#### Goone 白名单：WP1-B0 / WP0-C

现有文件：

- `jiuwenswarm/jiuwenswarm/quant/reporting/models.py`
- `jiuwenswarm/jiuwenswarm/quant/reporting/agent_view_parser.py`（Missed 完成角色迁移后接管）
- `jiuwenswarm/jiuwenswarm/quant/reporting/company_report.py`（Missed 完成角色迁移后接管）
- `jiuwenswarm/jiuwenswarm/quant/reporting/symphony_adapter.py`（Missed 完成角色迁移后接管）
- `jiuwenswarm/jiuwenswarm/quant/reporting/providers/__init__.py`
- `jiuwenswarm/jiuwenswarm/quant/reporting/providers/base.py`
- `jiuwenswarm/jiuwenswarm/quant/reporting/providers/registry.py`
- `jiuwenswarm/jiuwenswarm/quant/reporting/report_service.py`
- `jiuwenswarm/jiuwenswarm/quant/reporting/package_builder.py`
- `jiuwenswarm/jiuwenswarm/quant/reporting/quality_gate.py`
- `jiuwenswarm/jiuwenswarm/quant/reporting/__init__.py`
- `jiuwenswarm/tests/unit_tests/quant/test_report_models.py`
- `jiuwenswarm/tests/unit_tests/quant/test_report_quality_gate.py`
- `jiuwenswarm/tests/unit_tests/quant/test_evidence_hash.py`
- `jiuwenswarm/evaluation/unified_baseline_evaluation.py`
- `jiuwenswarm/evaluation/phase_b_experiment.py`
- `jiuwenswarm/tests/unit_tests/quant/test_unified_baselines.py`

允许新增：

- `jiuwenswarm/jiuwenswarm/quant/reporting/providers/announcement.py`
- `jiuwenswarm/jiuwenswarm/quant/reporting/evidence_archive.py`
- `jiuwenswarm/tests/unit_tests/quant/test_announcement_provider.py`
- `jiuwenswarm/tests/unit_tests/quant/test_evidence_archive.py`
- `jiuwenswarm/tests/fixtures/quant/announcements/` 下的脱敏固定样本
- `jiuwenswarm/jiuwenswarm/quant/evaluation_protocol.py`
- `jiuwenswarm/tests/unit_tests/quant/test_competition_window_policy.py`

特殊规则：

- Goone 先完成 WP1-B0 的共享窗口协议、测试和统一基线，再开发 `providers/`、evidence archive、report service、package builder、quality gate 和 fixture；在 Missed 提交 WP0-B 角色迁移前，不修改 models/parser/company report/Symphony adapter。
- Goone 不修改 `extension.py`、`run_quant_pipeline.py`、`run_multi_agent.py`、Team config、角色 Prompt 或根目录状态文档。
- Missed 在 WP1-B0 验收后把共享协议接入 direct/formal；不得在运行入口另写一套日期切分。
- Goone 完成 Provider 接口和 fixture 测试后，由 Missed 在集成文件中接入 direct/formal。
- “无公告”必须与“抓取失败”使用不同状态；真实网络 smoke 不得取代 fixture 单测。

### 7.3 第二阶段文件所有权

WP0-B/C 集成通过后再开放：

#### Missed：WP1-D

- `jiuwenswarm/evaluation/run_multi_agent.py`
- `jiuwenswarm/jiuwenswarm/extensions/quant-finance/extension.py`
- `jiuwenswarm/scripts/run_quant_pipeline.py`
- `jiuwenswarm/jiuwenswarm/quant/reporting/resource_meter.py`
- 新增 runtime/replay/resource 相关测试和脚本

#### Goone：WP1-A / WP1-B / WP1-C

- `jiuwenswarm/jiuwenswarm/quant/market_index.py`
- `jiuwenswarm/jiuwenswarm/quant/market_regime.py`
- `jiuwenswarm/jiuwenswarm/quant/regime_fusion.py`
- `jiuwenswarm/jiuwenswarm/quant/factors.py`
- `jiuwenswarm/jiuwenswarm/quant/strategy_configs.py`
- `jiuwenswarm/evaluation/phase0_experiment.py`
- `jiuwenswarm/evaluation/phase_b_experiment.py`
- `jiuwenswarm/evaluation/unified_baseline_evaluation.py`
- `jiuwenswarm/evaluation/README.md`
- 新增 data consistency、nested evaluation、Bootstrap 和 challenger 测试/脚本

Goone 若需要改变行情获取实现，应新建共享数据模块并先定义接口；`extension.py` 和 `run_quant_pipeline.py` 仍由 Missed 集成。

### 7.4 冻结文件与冲突规则

在 WP0 阶段冻结：

- `jiuwenswarm/jiuwenswarm/quant/strategy_configs.py` 中的生产策略指向和生产权重。
- `jiuwenswarm/jiuwenswarm/quant/stock_pool.py`。
- `jiuwenswarm/jiuwenswarm/quant/backtest_engine.py`。
- `jiuwenswarm/jiuwenswarm/quant/reporting/resources/submission_contract.json`。
- `赛题文档/`、`提交/` 和当前 `output/submission_candidate/`。

冲突规则：

1. `extension.py`、`run_quant_pipeline.py`、`run_multi_agent.py` 只有 Missed 可写。
2. `reporting/models.py`、parser、company report、Symphony adapter 在 WP0-B 角色迁移时由 Missed 独占；迁移提交后转交 Goone。
3. `reporting/providers/`、`quality_gate.py` 和 Provider 状态语义始终只有 Goone 可写。
4. `.claude/discussion.md` 只接受遵守 `CLAUDE.md` 格式的阶段交接：Missed/Goone 各自追加自己的汇报，Codex 追加裁决；任何角色不得覆盖或改写他人的既有消息。逐次搜索和完整日志改写任务工件，不进入 discussion。
5. 两人提交时只 stage 自己白名单内的文件，不得顺带提交对方未完成改动。
6. 发现必须跨边界修改时先停止，在 discussion 写出接口需求，由文件所有者修改。
7. 不允许用复制实现绕开文件边界。

### 7.5 提交边界

Missed：

1. `WP0-A docs-contract`
2. `WP0-B role-migration-and-deletion`
3. `WP0-B proposals-and-unit-tests`
4. `WP0-B integration-and-ablation`
5. `WP1-D runtime-and-resource`

Goone：

1. `WP1-B0 competition-window-policy-and-baselines`
2. `WP0-Ca provider-contract-and-fixtures`
3. `WP0-Ca real-provider`
4. `WP0-Cb archive-and-report-quality`
5. `WP1-A data-consistency`
6. `WP1-B evaluation`
7. `WP1-C challenger-round`

不得把多个提交压成一个“大功能完成”提交；每个提交必须附目标测试命令和退出码。

### 7.6 多模型开发基础设施

模型与项目职责解耦。Missed/Goone 仍拥有本节前述文件边界，但一次实现由 Planner、Scout、Builder、Critic 四种执行角色通过任务工件交接，不再依赖某个供应商的长会话：

1. Planner 在 `coordination/active/<TASK-ID>.md` 写目标、非目标、读写白名单、风险等级和验收命令；
2. 本地 Qwen 先定位定义、调用点和测试，写机器可校验的 `location.json`；
3. Planner 冻结文件哈希并生成最小 `context.md`；LOW 风险由本地模型实现，MEDIUM 才把最小任务包交给 DeepSeek，HIGH 由 Codex 重新规划或复核；
4. Critic 必须用新会话审查任务差异和测试证据，不得与 Builder 共享长聊天；
5. 任务脚本必须发现相对冻结基线的越界写入，即使仓库开始时已有未提交修改也不能把这些修改误算成本任务成果；
6. 两个 active task 的具体写入范围不得重叠；第二个任务冻结基线时必须失败关闭，避免并行修改归属混淆；
7. Qwen 与 DeepSeek 使用独立 `CLAUDE_CONFIG_DIR` 和独立终端并行运行，CC Switch 只保留为人工选择默认 Provider 的入口。

验收标准：

- 三个本地 skill 通过结构校验，分别覆盖只读定位、白名单实现和独立差异审查；
- 任务 CLI 能创建任务、校验定位结果、构造最小上下文、冻结基线、检测越界修改并生成 task-scoped diff；
- 人工构造一个越界文件时 `scope-check` 非零退出，删除越界文件后恢复通过；
- 两个任务声明同一写入文件时，第二个 `freeze` 非零退出并指出冲突任务；
- Qwen 与 DeepSeek 各自在独立 profile 中完成一次真实 Claude Code 请求，不改写另一 profile 或 CC Switch 当前状态；
- 该基础设施只达到 `LOCAL_IMPLEMENTED`，不得据此提高量化生产路径的证据等级。

## 8. 里程碑

### M0：事实一致

WP0-A 通过，不改变投资组合。

### M1：Agent 具有可审计因果作用

旧 Bull/Bear 角色已被 Alpha Analyst 与 Risk & Evidence Analyst 完整替换并删除，WP0-B 通过且获得 A0/A1/A2 消融结果。若 Agent 没有决策或报告增量，停止扩张角色数量。

### M2：第一类真实非行情证据

WP0-C 通过。此时只能声明“公告增强型报告”，不能自动声明完整金融分析。

### M3：策略研究工具可信

WP1-A/B 通过后才允许 WP1-C。三个预注册方向都失败时停止权重搜索。

### M4：资源和正式路径稳定

WP1-D 通过，完成 3 次正式复跑和 20 次确定性 replay。

### M5：正式提交

WP2 外部阻断解除并重新执行 `VALIDATION.md` 全部命令后才能进入。

## 9. 预期效果与风险

### 预期效果

- Agent 的贡献从“有角色事件”升级为“能追踪哪条证据如何改变组合”。
- 报告从行情技术面扩展到第一类真实非行情证据。
- T2 或新候选的晋级建立在更可信的外层证据上。
- 正式路径 input token 目标下降至少 50%，同时保持业务成功率。
- 文档和实际运行状态不再依赖人工复制动态数字。

这些目标不能保证比赛收益上升；它们首先减少假 Alpha、报告空洞和 Agent 伪增量。只有 WP1-C 通过外层证据，才能把收益改善写为策略结论。

### 主要风险

- 数据不足导致外层评估统计能力仍有限。
- point-in-time 企业行动和公告归档实现复杂。
- Agent 有界调整可能没有样本外增量。
- 行业中性会去掉一部分真实板块趋势收益。
- 资源压缩可能降低角色分析深度。
- 官方契约延迟会阻塞最终格式，但不应阻塞研究核心。

## 10. 教学要点

1. 真实历史不等于样本外证据：数据真实，但模型若已经根据它被选择，结果仍是开发集表现。
2. Agent 参与不等于 Agent 有价值：必须用 DecisionTrace 或消融增量证明。
3. 安全 Agent 不是没有决策权，而是在有界动作空间中基于证据决策。
4. 报告完整性不是字数，而是 point-in-time、多来源、可追溯和冲突披露。
5. 数据源数量不等于数据质量；日历、单位、企业行动和来源切换决定研究可靠性。
6. 硬安全门适合布尔判定，统计证据应使用分布和置信区间。

## 11. 立即执行入口

用户已授权 Missed 和 Goone 按本文开始开发，不再等待第三个实现角色回复。

### Missed 现在开始

1. 先执行只读定位：解释最新真实双路径为何得到 49/49 行情、却只有 0/49 公告/披露证据；输出 Provider 注册、调用、缓存、归档、质量门和测试边界，不修改代码。
2. 不接受“网络不可用”作为唯一根因；必须区分未调用、调用失败、真实无公告、时间窗过滤、解析失败和证据未接线。
3. 定位结果进入有文件白名单的 WP0-C 修复任务；修复后必须通过 fixture、时间穿越/篡改负测、direct/formal 和独立 audit，才能恢复报告业务通过声明。
4. `evaluation/agent_ablation.py` 保留为后续任务；公告 E2E 未恢复前不得用消融结果掩盖报告缺口，也不得切换生产组合。

### Goone 现在开始

1. 先执行只读定位：解释固定 quant profile 为何仍暴露并调用通用 task、file、browser 和 sys-operation 能力；不得修改 `.venv` 或依赖源码。
2. 输出 openJiuwen 当前版本可支持的排除机制、项目层最小变更边界、负向验收和无法由项目层解决的上游限制。
3. 定位结果进入有文件白名单的 WP1-D 修复任务；必须保持严格 8/8、每阶段只执行一次，并用同输入正式复跑比较 token、耗时和工具调用。
4. WP1-A/B 研究可以在不触碰正式 Agent 组装和公告路径的前提下继续准备，但 WP1-B 通过前不得启动 WP1-C challenger 调权。

Codex 在两个只读定位产物完成后冻结具体修复契约和文件白名单。当前不得把 `PATH_PASSED` 写成 Agent 架构或完整报告已经完成。

两人都必须先运行相关局部测试；不得等待所有开发完成后才第一次验收。

## 12. 变更记录

| 版本 | 日期 | 作者 | 变更 |
|---|---|---|---|
| 1.7.0 | 2026-08-04 | Codex | 用严格双路径和独立 audit 推翻过期的 WP0-C/WP1-D 完成假设：公告/披露仍为 0/49，formal 虽严格 8/8 但仍暴露通用能力且资源未下降；将立即执行入口改为两个只读定位任务，修复前禁止恢复业务通过声明 |
| 1.6.0 | 2026-08-02 | Codex | 新增多模型角色化任务包、最小上下文、文件白名单与独立 Provider 配置验收；用工件交接替代长聊天和 CC Switch 单一全局 Provider，明确本地/云端风险路由 |
| 1.5.0 | 2026-07-31 | Codex | 完成变参空转预算、统一阶段执行标记、完整 audit 绑定和公告双路径接线并通过真实 E2E；关闭 WP0-C，更新立即执行入口为 Missed 的 A0/A1/A2 + WP1-D、Goone 的 WP1-A/B |
| 1.4.0 | 2026-07-30 | Codex | 回应 Goone 质疑：将官方 embargo 协议和统一基线提升为独立 P0 的 WP1-B0；拆分 WP0-Ca/b 并行依赖；增加逐工作包资源回归门、candidate-only 契约预案、机制特定预筛选、行业中性诊断产物与公告 overlay 条件晋级；明确 Goone 文件所有权 |
| 1.3.0 | 2026-07-30 | Codex | 增加减法与迁移计划：保持三 Agent 总数，将 Bull/Bear 原子替换为 Alpha Analyst、Risk & Evidence Analyst；列出旧角色文件、RPC、缓存、parser、persona 的删除项，补充跨 Agent 文件交接和负向验收 |
| 1.2.0 | 2026-07-30 | Codex | 根据官方 2026-08-25 至 09-21 固定 20 交易日窗口重构 WP1-B/C；新增 2026-08-24 submission-to-entry embargo；将行业中性降为诊断，主方向改为期限对齐趋势、板块领导力和非对称尾部风险 |
| 1.1.0 | 2026-07-30 | Codex | 用户授权立即开发；移除不存在的 Claude 实现角色，重分配 Missed/Goone 工作包，增加两阶段文件白名单、唯一集成文件所有权、冻结范围和提交边界 |
| 1.0.0 | 2026-07-30 | Codex | 建立独立长期计划；固化当前架构分析、问题矩阵、目标架构、工作包、验收标准、依赖和停止规则 |
