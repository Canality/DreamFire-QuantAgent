# Dream Fire 当前开发计划

| 字段 | 值 |
|---|---|
| 文档版本 | `2.4.0` |
| 状态 | `ACTIVE` |
| 更新日期 | 2026-08-07 |
| 适用基线 | Git `1f84b01` 及后续提交 |
| 计划与验收 | Codex |
| 执行与开发 | Claude |
| 运行事实源 | `VALIDATION.md` |

> 本文只保存当前路线、完成定义和仍有效的验收契约。真实命令、退出码、运行
> 产物和证据等级只认 `VALIDATION.md`；已关闭版本的完整演进见
> [history/README.md](history/README.md)。计划条目不等于已经实现。

## 1. 文档与版本规则

- 主版本用于目标架构或比赛方向根本变化；次版本用于工作包、依赖或验收标准
  变化；修订版本用于不改变含义的澄清。
- 路线变化必须先更新本文版本和末尾变更记录；运行事实只更新
  `VALIDATION.md`；当前交接只写 `.claude/discussion.md`。
- `history/` 是 append-only 版本档案，不是当前事实源、路线源或普通任务上下文。
- 工作包必须独立提交，并列出 `KEEP / REPLACE / DELETE`；新实现已经替代活动
  路径时，不为“可能有人调用”保留内部兼容代码。

## 2. 固定比赛与安全契约

所有策略、候选周期和历史回放统一预测同一官方目标：

```text
decision close
→ 1 个完整交易日 embargo
→ entry day open 固定股数买入
→ 持有 20 个交易日且不调仓
→ 第 20 个交易日常规 close 卖出
```

- 官方提交截止 2026-08-23；评测期 2026-08-25 至 09-21。
- 2026-08-24 不可进入提交决策。最近 20 个交易日只能描述当前状态，因为未来
  20 日标签尚未成熟。
- 短/中/长只表示输入 lookback，不能分别使用 5/20/60 日目标后直接比较。
- 历史决策日 `d` 只能使用 `d` 当时可见的数据、当时 registry，以及在 `d`
  前已完成官方退出日的标签。
- 股票池不足 49 家、板块不足 6 组、选股/配仓集合不一致、单股 >10%、板块
  >25% 或现金 <5% 必须失败关闭。
- `SubmissionContract` 在 49/50、现金权重和报告作用获得书面澄清前保持
  `PROVISIONAL / BLOCKED`。

## 3. 当前架构

```text
Point-in-time Evidence Layer
        ↓ EvidenceRef + published/effective/observed_at + hash
Research Layer
├── versioned Factor Registry
├── matured-label FactorResearchSnapshot
├── multi-lookback candidates
├── prior-only market similarity
└── full selector nested replay
        ↓ bounded proposals
Agent Decision Layer
├── Alpha Analyst
├── Risk & Evidence Analyst
└── Coordinator
        ↓ StrategyProposal / DecisionTrace
Deterministic Safety Core
├── eligibility / fusion / fallback
├── select / allocate / assertions
└── official-window backtest
        ↓
evidence-linked reports → direct / formal / E2E
```

原则：

1. 必需阶段由确定性状态机保证，LLM 不猜顺序。
2. LLM 不接收价格矩阵，不创建因子、证券或权重，不解除策略资格。
3. Agent 只在预注册的有界动作空间影响候选分数，所有变化写 DecisionTrace。
4. direct/formal 调用同一服务并可重放同一 proposal/evidence bundle。
5. 数据、提案或证据门失败时回退 `production_six_factor`；回退必须有 reason code。

## 4. 已实现基础与未提升的边界

以下状态摘要用于安排路线，证据等级仍以 `VALIDATION.md` 为准：

- WP0-A 已把 README 动态字段改为机器生成并恢复 runtime Skill 镜像。
- WP0-B 已实现 PIT `AgentProposal`、不可变 `DecisionTrace`、共享确定性 selection
  和 A0/A1/A2 诊断；生产 Agent overlay 仍关闭。
- 公告已形成 1,470 条、49/49 的历史已接受运行证据；WP0-C 新增不可变 receipt、
  离线 replay 和 direct/formal 状态投影，但本轮没有冒充新的网络或 formal 运行。
- WP1-B 已实现 embargo、嵌套内外层、Bootstrap 和晋级边界；T2 仍为
  `RESEARCH_ONLY`。WP1-C 三个冻结 challenger 均未晋级，搜索保持关闭。
- WP1-D 已实现精确阶段状态、20 次无 LLM replay、资源聚合、正常 teardown 和
  同工具连续失败诊断；Windows 三次 formal 全部 8/8，资源门全绿（P95 105s /
  RSS 575MB / token -91%），**CLOSED**。
- WP1-E0 Registry、12 个趋势候选、E1 因子研究策略已 `LOCAL_IMPLEMENTED`。
- WP1-E1P 五项数据能力全部 `AVAILABLE`（baostock corporate_action / qfq
  snapshot / forward_label + 赛题 sector + calendar），**CLOSED**。
- E2 基线已冻结（6 槽位策略池），Claude 待实现；E3/E4 未开始。
- 完整报告仍缺 fundamental/news-risk 等 PIT 数据；正式提交契约仍阻塞。

## 5. 全局完成定义

1. 代码存在只算 `LOCAL_IMPLEMENTED`；正式能力还需 direct/formal/E2E。
2. 每个历史窗绑定 registry、实现、输入 snapshot、特征 schema、成熟标签、候选、
   融合、Git/config hash 和随机种子。
3. 调参代码不能访问 outer；dirty run、test-only evidence 和未成熟标签不能晋级。
4. 研究任务不得静默改变 `PRODUCTION_STRATEGY`。
5. 同一输入、模型、工具版本的 formal input token 回退超过 5% 标记
   `RESOURCE_REGRESSION`；不抹去功能测试，但不能关闭资源验收。
6. 真实复跑后先更新 `VALIDATION.md`，形成版本边界后再写 history，最后更新
   README/discussion。
7. 删除旧路径前先有替代和负向测试；删除后用 `rg`、导入、direct/formal/E2E
   证明不可达。历史证据不删除。

## 6. 当前工作包

### WP1-D：Windows 正式稳定性验收

状态：`CLOSED`（2026-08-07）。

Windows 三次 formal 全部 8/8（115235/122418/122852），REAL_EXIT=0。
五项 Windows 缺陷全部修复。资源门：P95 105.1s ≤120s，RSS 575.09MB ≤600MB，
token -91.3% ≥50%。111 聚焦测试通过。commit 链 `bbe728d..1f84b01`。

### WP1-E1P：研究数据能力准入

状态：`CLOSED`（2026-08-07）。

五项全部 AVAILABLE：
- CANONICAL_CALENDAR：SSE/SZSE 官方日历（原有）
- PIT_CORPORATE_ACTION：baostock 分红归档（347 行 × 49 股 × 2020-2025）
- E0_FACTOR_SNAPSHOT：baostock qfq OHLCV（77,541 行 × 49 股 × 2020-2026）
- OFFICIAL_FORWARD_LABEL：1+20 成熟标签（604 决策日）
- PIT_SECTOR：赛题 6 板块 STATIC_V1（无历史版本链，标注 PARTIAL）

### WP1-E2：多 lookback 候选与相似市场

状态：`BASELINE_FROZEN`（2026-08-07）。Claude 待实现。

6 个槽位：

1. `production_six_factor`：唯一生产资格和硬回退；
2. `t2_comparator`：只作 `RESEARCH_ONLY` 对照；
3. `trend_short_5_10_20`；
4. `trend_medium_20_60`；
5. `trend_long_120_250`；
6. `similar_market_blend`。

相似性首版固定六维：benchmark 20/60 日动量、20 日波动、MA20 宽度、行业
20 日收益离散度、成交量宽度。只用 expanding prior 样本的中位数/MAD，至少
60 个历史状态，取 5 个已成熟且不重叠邻居。排序固定为
`(distance, decision_date, market_snapshot_hash)`；缺字段、MAD 为零或邻居不足
只关闭相似分支，基础研究契约失败才硬回退 production。

### WP1-E3：有界 Agent 策略融合

状态：`BLOCKED_BY_E2`。E2 完成后启动。

- A0 纯确定性；A1 的 Alpha 单项调整 ≤±0.10、总 L1 ≤0.20；A2 的 Risk 只做
  非正调整，并在至少两个独立 PIT EvidenceRef 支持时否决最多一个非回退策略。
- 每个决策日最多一个 create-once proposal bundle：Alpha/Risk 各最多一次模型
  调用、0 tool/RPC、0 retry、45 秒；每角色 input ≤4,000、output ≤800 token。
- model、Prompt、schema、生成配置和 assembler 版本在 outer 前共同哈希冻结。
- 超时、未来证据、越界或解析失败只丢弃对应 proposal，保留 A0；A0 无效才回退。
- Coordinator 只触发确定性 assembler，不能新增因子、候选、证券或权重。

### WP1-E4：完整动态选择器回放

状态：`BLOCKED_BY_E3`。

- 每个历史决策日从零重建 registry、因子快照、成熟标签、变换器、邻居、候选、
  Agent 输入、融合、组合和官方 20 日结果。
- A0/A1/A2 在同一次 one-shot outer 共同评估；不得先看 A0 再决定是否运行覆盖层。
- outer 结果不得反馈到本轮 policy。价格级 embargo、缺数、企业行动、泄漏、
  selector replay、Block Bootstrap、资源和独立审查全部通过后，只产生新的
  `RESEARCH_ONLY` 证据。
- 改 production 必须另建晋级任务，执行 direct/formal/E2E 和 Windows 复验。

### PIT Fundamental / News-risk Provider

状态：`DATA_BLOCKED`。

- fundamental 需要 historical-as-published structured line items、taxonomy、
  期间/合并/审计/单位币种、发布/可见时间、修订链、raw-byte archive 和跨设备
  交付授权。metadata discovery 或 PDF 存在不等于准入。
- news-risk 必须独立定义来源权威、时间口径、事件身份、修订/删除、空结果证明、
  49/49 状态和授权边界；不得用公告标题或 LLM 摘要冒充。
- 未获授权数据前不开始 Provider 实现；当前报告保持 `FINANCIAL_PARTIAL`。

### WP2：正式契约与最终发布

状态：`BLOCKED_EXTERNAL`。

需主办方可归档书面答复：Excel 49/口述 50、现金是否计入权重和、报告对初赛
作用。Token/运行分值冲突和精确截止时刻也应一并确认。答复归档并生成 contract
version/hash 后，才能适配正式格式和生成可称为正式提交的包。

## 7. 两方协作与文件所有权

### Codex：计划与验收

- 确认基线和工作树来源，创建任务，决定风险、依赖和验收标准。
- 验收 Claude 的只读定位后冻结精确白名单和 baseline。
- 独立审查 task-scoped diff、反例、测试和事实声明；只有 Codex 设置
  `VERIFIED/CLOSED`。
- 维护根目录当前事实/路线/交接，创建任务级 bundle/patch 并核对 Windows 回执。

### Claude：执行与开发

- 完成只读定位，枚举定义、直接调用点、契约和测试，提出最小写范围。
- 在 `READY` 后测试优先实现，只修改 `allowed_files`，写 implementation 工件。
- 对不可实现、重复逻辑、时序/证据矛盾或范围遗漏主动提交可复现挑战。
- 不自行扩大白名单、提高证据等级、改 production/contract 或声称验收完成。

### 共同规则

- 双方平等，阶段职责不构成一般上下级。有效质疑按 `AGENT_WORKFLOW.md` 最多
  各两次证据交换，随后必须 `ACCEPT / MODIFY / REJECT / 用户升级`。
- 同一任务不由 Mac/Windows 同时修改；来源不明工作树不覆盖、不清理。
- 任务契约按实际改动冻结文件，不保留永久按人划分的巨大白名单；跨边界调用点
  由 Codex 显式扩 scope 并保留原基线。
- 定位、实现、审查是阶段，不创建第三个开发身份；三角色金融运行时保持不变。

## 8. 里程碑

| 里程碑 | 当前结论 |
|---|---|
| M0 事实一致 | ✅ CLOSED — Windows 复验通过 |
| M1 Agent 决策契约 | LOCAL_IMPLEMENTED，overlay 关闭 |
| M2 公告证据 | LOCAL_IMPLEMENTED，待 E2E 复验 |
| M3 动态研究 | E1P CLOSED，E2 基线冻结 |
| M4 正式稳定性 | ✅ CLOSED — Windows 三次 8/8，资源门全绿 |
| M5 正式提交 | BLOCKED_EXTERNAL — 主办方书面 contract |

## 9. 当前执行顺序

1. WP1-E2 实现（6 槽位策略池）→ E3 → E4
2. fundamental/news-risk 授权 source 到位后恢复 Provider
3. 主办方答复后 WP2 正式包

## 10. 文档版本

| 版本 | 日期 | 作者 | 变更 |
|---|---|---|---|
| 2.4.0 | 2026-08-07 | Codex | WP1-D CLOSED（Windows 三次 8/8 资源门全绿）；WP1-E1P CLOSED（五项数据能力全部解封）；WP1-E2 基线冻结；M4 关闭 |
| 2.3.0 | 2026-08-06 | Codex | 收敛为 Codex 计划/验收与 Claude 执行/开发的平等两方协作；把定位、实现、审查改为阶段；同步 WP0、WP1-D 和 WP1-E 当前路线，明确本地代码门、Windows 正式门和外部数据/契约 blocker |
| 2.2.0 | 2026-08-05 | Codex | 完成 E1P official calendar 单项准入，其余能力保持失败关闭 |
| 2.1.0 | 2026-08-05 | Codex | 增加 E1P Provider 准入门 |
| 2.0.0 | 2026-08-05 | Codex | 新增 Factor Registry、PIT 因子研究、多 lookback、相似市场、有界融合和完整 selector replay 路线 |
