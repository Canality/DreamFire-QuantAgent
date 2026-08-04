# 当前验证状态

> 本文件是项目可运行状态的唯一事实源。README、Agent 指令和讨论文档只能引用这里，不得复制长期状态。

## 结论（2026-08-04）

| 对象 | 证据等级 | 结论 |
|---|---|---|
| 量化核心与行情证据链 | BUSINESS_PASSED | 最新 direct `2025-01-02 → 2025-05-21` 真实通过共享五源 Provider、因果切分和仓位约束；49/49、6/6、15 只，收益 `+0.7476%`、最大回撤 `1.6424%` |
| JiuwenSwarm 多 Agent 路径 | BUSINESS_PASSED | 最新 session `multi-agent-validation-20260804-172234` 在 fixed quant capability ceiling 下完成 8/8；每阶段恰好请求/执行 1 次、0 cache hit、0 error，三角色真实参与且无角色 RPC 越权 |
| 公告增强型报告候选包 | DIRECT_PASSED / FORMAL_PASSED | 最新 direct 与 formal 分别绑定各自 create-once 候选包，均携带 1,470 条公告、49/49 披露；独立 E2E audit 重算两套文件树与 manifest 哈希后退出 0，报告等级仍为 `FINANCIAL_PARTIAL` |
| 完整金融分析作品 | PARTIAL / FAILED | direct/formal 报告与公告披露已形成可审计覆盖，但基本面、新闻、宏观和另类数据仍缺失，不能宣称 `FULL_REPORT_PASSED` |
| 正式提交契约 | PROVISIONAL / BLOCKED | 最新答疑与静态文档仍有 3 项冲突，不能把候选包改名为正式提交包 |
| 策略 alpha | RESEARCH_ONLY | competition-aligned 20 窗重跑中 T2 配对收益差 +0.8356pp、效用胜出 17/20；全部仍是已观察开发窗口。最新 A0/A1/A2 消融存在配仓缓存串线，不能作为 Agent 无增量证据 |
| WP1-A 数据一致性与市场状态 | PATH_PASSED | direct/formal 均已改用共享 OHLCV Bundle，并在本轮真实取得 49/49 主源、49/49 独立二源、CSI300、6/6 板块诊断和九文件 snapshot；完整报告仍因 fundamental/news-risk 缺失保持 partial |
| 正式路径失败关闭 | PATH_PASSED | 已修复“先失败、后成功仍判通过”的 validator 缺陷；回归测试 2/2，通过后的严格 session 每阶段只请求并执行 1 次 |
| 正式团队精确选择 | PATH_PASSED | `FORMAL-TEAM-SELECT-0804` 为 TeamManager 增加显式 team selector；真实 formal 构建 `quant-leader` 和两个预定义分析师，不再误选通用 `jiuwen_team` |
| Agent 资源与能力瘦身 | PATH_PASSED | fixed quant 运行时仅保留角色自有 Quant RPC 与 `send_message`；leader 为 9-tool、两名 analyst 各为 2-tool，无 task-board、文件、shell、browser、skill、subagent 或通用 team-management 工具；最新 formal 为 12 次业务/消息调用 |

以上结论适用于当前未提交工作树（HEAD `170e904`）。`output/` 是本机验收产物，不进入 Git。

## 官方事实裁决

- 2026-07-28 官方答疑确认：初赛提交截止为 **2026-08-23**；评测期为 **2026-08-25 至 2026-09-21，共 20 个交易日**；提交持仓在评测期内不可调仓。
- 官方评分口径为评测首日开盘买入、末日常规交易收盘卖出。由于 2026-08-24 位于提交截止之后、评测买入之前，提交策略不得使用该交易日行情。
- `赛题文档/上市公司列表.xlsx` 的实际内容为 **49 家、6 个板块**；SHA-256 为 `C021D69B5C3BF3EA0C4626811DF5ED9A02CD4C67E1068AD2F0CE35D759210617`。
- 答疑口述/转录写“50 家”，与 Excel 冲突。本地契约以可校验的 Excel 为当前权威，同时保留向主办方确认的问题。
- 静态赛题介绍允许空仓/半仓；答疑口述称公司权重和为 1，现金口径未明确。
- 静态材料称初赛以客观回测为主；答疑强调报告完整性和可用性影响筛选。
- 资源维度分项文字中出现“Token 10 分但规则写 15 分、运行 5 分但规则写 10 分”的内部矛盾。

因此 `SubmissionContract.can_proceed_formal()` 当前必须失败关闭。解除阻断需要主办方的可归档书面答复，不得由 Agent 自行猜测。

## 本轮真实验收

### -12. Windows 两项 P1 修复与不可变候选绑定复验（2026-08-04 16:55–17:24）

证据等级：公告全域健康门、不可变候选绑定和汇总晋级门均为 `PATH_PASSED`；fresh direct、formal 与独立绑定审计均为 `BUSINESS_PASSED`。本轮未开始 WP1-B/WP1-C，旧证据目录未被覆盖。

- Windows 复核工件 `output/agent_handoffs/FORMAL-CAPABILITY-CEILING-0804/WINDOWS_CODEX_REVIEW.json` 的两个 P1 已分别修复。49-ticker 必选宇宙若首轮公告总数为 0，会用新的 Provider 对整个宇宙做一次有界健康重试；再次全空即失败关闭，direct 的时间戳结果保留两次尝试、49 家逐 ticker 终止原因、页数/请求数、解析失败和整体 terminal cause。单测覆盖首轮恢复、连续全空和 required-universe 精确性。
- 候选输出从单一可变 `output/submission_candidate` 改为 create-once 的 `output/submission_candidates/<candidate-id>`。direct 结果与 formal summary 分别记录绝对路径、候选 ID、immutable 标志、snapshot ID/manifest hash、报告/证据 manifest hash、49 份公司报告树 hash，以及报告、公告、披露和 EvidenceRef 计数；重复 ID 失败关闭。
- 独立 audit 分别解析 direct/formal 候选，拒绝 legacy 可变路径、同目录混用和任一 hash/计数漂移，并重新计算两套 `candidate_binding.json`。`generate_validation_summary.py` 只有在 audit `passed=true` 且当前 results/summary 的绑定精确匹配时，才允许量化核心、多 Agent 路径和报告候选三项进入 `BUSINESS_PASSED`。
- 独立 Critic verdict 为 `ACCEPT`、无 P0/P1/P2；记录在 `output/agent_handoffs/WINDOWS-P1-REPAIR-0804/CRITIC_REVIEW.json`。聚焦回归 55 passed；changed-file Ruff、py_compile、diff-check、scope-check 均退出 0。
- fresh direct：日志 `output/agent_handoffs/WINDOWS-P1-REPAIR-0804/validation/direct.log`，结果 `output/pipeline_results_20260804_172026.json`，退出 0；49/49、90 日、训练 70/前向 20 日、15 只、6 板块、现金 5.06%，收益 `+0.7476%`、最大回撤 `1.6424%`、Sharpe `1.107`；1,470 条公告覆盖 49/49，候选为 `direct-20260804_172026`。
- fresh formal：日志 `output/agent_handoffs/WINDOWS-P1-REPAIR-0804/validation/formal.log`，session `multi-agent-validation-20260804-172234`，summary/chunks 为 `output/multi_agent_summary_20260804-172234.json` 与 `output/multi_agent_chunks_20260804-172234.json`；退出 0，8/8、每阶段 request/execution 各 1、0 cache hit、16 tool calls、0 error，三角色事件 1569/1011/644，专属 RPC 各 1 且无越权。候选为 `formal-multi-agent-validation-20260804-172234`。
- `output/audit_result_multi-agent-validation-20260804-172234.json` 独立审计退出 0、`passed=true`、failures 为空。direct binding SHA-256 为 `f506e5f5f2123590a98728e7139fd3612041e07c90ba319aa1cf3e4588877e88`，formal 为 `a2db8f2b377f494adc65cc51fd95b66535e92c55001548c4f9a7c159a9650072`；两者路径、snapshot、manifest、报告树和计数均独立核验。
- 历史 `output/submission_candidate` mtime 仍为 `2026-08-04 15:27:34 +0800`，未被本轮运行触碰；旧 direct/formal/audit 和既有 handoff 全部保留。当前裁决仍不改变完整金融分析 `PARTIAL` 与正式提交契约 `PROVISIONAL / BLOCKED`。

### -11. Fixed quant capability ceiling 与最新完整双路径复验（2026-08-04 13:35–15:28）

证据等级：fixed quant 能力边界为 `PATH_PASSED`；direct、formal 与绑定两者的独立审计均为 `BUSINESS_PASSED`。报告覆盖仍为 `FINANCIAL_PARTIAL`，正式提交契约仍为 `PROVISIONAL / BLOCKED`，不得据此宣称项目已可正式提交。

- `FORMAL-CAPABILITY-CEILING-0804` 在项目层为 exact `quant_team` 及其 canonical session 名实现 fail-closed discriminator。固定团队清空继承的 skills、MCPs、browser/general subagents、task loop/planning/discovery 与通用 rails；generic team 和 generic `DeepAgentSpec` 继续直接委托 pinned openJiuwen 行为。
- 固定 leader 的 agent-facing 工具精确为 8 个 Quant RPC 加 `send_message`；`alpha_analyst` 与 `risk_evidence_analyst` 各自只有专属 Quant RPC 加 `send_message`。task-board、spawn/build/clean/async team-management、workspace、文件、code、shell、browser、cron、skill 和 subagent 均未暴露。
- DeepAgent 内部 workspace 初始化只获得一个未注册为 rail/tool card 的 FS 对象，唯一 sandbox root 为显式 member workspace，`restrict_to_sandbox=true`；缺失/空白 workspace 失败关闭，code 与 shell 永久拒绝。该内部对象不形成 Agent 可见文件工具。
- pinned openJiuwen 在移除 model-visible `build_team` 后不会注册预定义成员；fixed leader 因此在首个 model call 前服务端确定性创建并核对精确三成员 roster。`send_message` 仅保留上游 `on_teammate_created` 句柄，用于启动已注册的 `UNSTARTED` 成员，不恢复 allocator、workspace、swarmflow 或任何 spawn/build/task 工具。
- 四次未通过的 formal seam 均保留：第一次因 configurator 注入 sys-operation 失败关闭；第二次因 DeepAgent workspace bootstrap 缺 FS 失败关闭；第三次遗漏验收日期而作废并暴露 roster 未注册；第四次使用正确日期、完成 roster 和两次消息投递，但因遗漏成员启动回调被人工中断。每次发现均补回归、重新走独立 Critic，未覆盖成成功记录。
- 独立 Critic 共七轮；最终 round 7 为 `ACCEPT`、无 finding。其行为探针证明实际 team tool 精确为 `send_message`，且投递前以同一 callback 启动已注册成员；聚焦测试 6/6 通过。完整冻结目标集合为 `163 passed, 1 warning`，Ruff、py_compile、diff-check、scope-check 均退出 0，`.venv` 未修改。
- post-fix direct：`output/direct_pipeline_FORMAL-CAPABILITY-CEILING-0804_20260804_1522.log` 与 `output/pipeline_results_20260804_152623.json`，日期 `2025-01-02 → 2025-05-21`，退出 0；49/49 行情、90 日、15 只、6 板块、现金 5.06%，收益 `+0.7476%`、最大回撤 `1.6424%`、Sharpe `1.107`；公告 1,470 条、49/49，rails 4/4，Quality PASSED。
- post-fix formal：session `multi-agent-validation-20260804-152646`，日志/summary/chunks 分别为 `output/formal_run_FORMAL-CAPABILITY-CEILING-0804_20260804_1526.log`、`output/multi_agent_summary_20260804-152646.json`、`output/multi_agent_chunks_20260804-152646.json`。退出 0，8/8 阶段均恰好请求/执行 1 次、0 cache hit；12 tool calls、0 error、48.0 秒，三角色事件为 1177/508/389，Alpha/Risk 专属 RPC 各 1 次且无越权。
- formal 资源为 95,569 input、6,510 output、61,952 cache tokens、CPU 12.68 秒；leader 为 71,390/4,007/54,784 tokens 与 8 calls，Alpha 为 12,495/1,389/2,304 与 2 calls，Risk 为 11,684/1,114/4,864 与 2 calls。峰值内存和最大并发缺测，未伪填为 0。
- `verify-quant-e2e` 绑定 fresh direct results/log 与 formal log/chunks 后写出 `output/audit_result_multi-agent-validation-20260804-152646.json`，退出 0：15 只、6 板块、总仓位 94.94%，八工具遍历齐全，三角色参与和角色 RPC 均满足契约，工件 SHA-256 已记录。
- formal 生成的候选包质量门通过且无 warning；49 份报告均达到 technical/disclosure grade，公告 1,470 条覆盖 49/49。fundamental/news-risk grade 仍为 0，整体等级为 `FINANCIAL_PARTIAL`，所以 `FULL_REPORT_PASSED` 仍禁止使用。

### -10. 公告 PIT、正式团队选择与最新双路径复验（2026-08-04 11:46–13:14）

证据等级：公告 Provider 与 direct 为 `BUSINESS_PASSED`；正式团队选择为 `PATH_PASSED`；最新 formal 与完整 E2E 为 `BUSINESS_FAILED`。不得把 direct 公告恢复或三角色加载成功合并成项目整体通过。

- `ANNOUNCEMENT-SCOUT-0804` 只读定位确认根因：Eastmoney Provider 固定只取最新第 1 页再做历史 PIT 过滤，导致更早页存在合格公告时仍误报无事件。49/49 第 1 页请求成功、1,470 条均晚于决策时点；`600000` 第 5 页和 `000001` 第 4/5 页可复现合格历史记录。
- `ANNOUNCEMENT-PIT-0804` 增加服务端 `end_time`、有界分页、客户端保守 Asia/Shanghai PIT 和六类终止原因；三轮 Critic 反例修复了提前空页、缺失末页、畸形标量、跨页 `total_hits` 漂移和去重问题，第四轮 `ACCEPT`。目标回归 `69 passed, 1 skipped`，Ruff、py_compile、diff-check、scope-check 均通过。
- 限流解除后的单次 49-ticker smoke：1,470 个 eligible facts，49/49 `complete` 且有事件，59 页/请求，0 parse failure；`pit_verified=true`，archive、manifest 和 fact IDs 一致。
- 最新 direct 日志 `output/direct_pipeline_20260804_131259.log` 与结果 `output/pipeline_results_20260804_131305.json` 均为新鲜产物：退出 0，49/49、90 日，训练 70 日、前向 20 日，15 只、6 板块、现金 5.06%，收益 `+0.7476%`、最大回撤 `1.6424%`、Sharpe `1.107`；候选包含 1,470 条公告事实、49/49 披露和 4/4 rails。
- 公告修复后的前两次 formal 均误选用户配置中的首个通用 `jiuwen_team`。`FORMAL-TEAM-SELECT-0804` 为 loader/TeamManager 增加可选的精确 selector，并在 Runner 前校验规范化 team 名、`quant-leader` 和恰好两个唯一预定义分析师；省略 selector 的既有调用仍保留首 team 行为，空白/不存在 selector 失败关闭。
- 第一轮团队选择 Critic 给出 1 HIGH、2 MEDIUM、1 LOW，重复角色、空白 selector、session 名规范化和 Runner 哨兵四项均已修复；第二轮 verdict 为 `ACCEPT`。目标集合 `71 passed, 2 skipped`；另有 1 个基线前失败来自白名单外 `resources/config.yaml` 已硬编码 DeepSeek、而旧测试仍期待环境占位符，未越界修改。
- 最新 formal session `multi-agent-validation-20260804-131332` 真实构建 `quant_team_multi-agent-validation-20260804-131332`，Leader 为 `quant-leader`、Members 为 2，三角色流事件分别为 409/14/2；团队选择修复因此通过真实路径验证。
- 同一 formal 仍退出 1：通用任务看板调用在没有任何 quant 进展时达到 12 次，guard 在 22 秒失败关闭；8 个阶段请求/业务执行均为 0，Alpha/Risk 专属 RPC 均为 0。资源为 140,181 input、2,052 output、101,248 cache tokens、14 tool calls；formal 的失败资源记录覆盖了 direct 候选包资源文件，不能把当前目录当作完整 formal 候选。
- 按 `verify-quant-e2e` 执行独立审计，`output/audit_result_multi-agent-validation-20260804-131332.json` 退出 1：缺 8 个量化工具遍历、两个角色专属 RPC、精确一次业务执行和完整三角色资源明细。公告/披露不再是本次失败项，当前唯一主阻断已推进为 openJiuwen capability ceiling。
- 当前裁决：`FORMAL-TEAM-SELECT-0804` 的精确选择目标可关闭；完整 E2E 继续 `BUSINESS_FAILED`。下一步复核并扩展 `WP1A-ORCH-0803` 的冻结范围，在项目层保留 `send_message` 和角色专属 Quant 工具，移除 fixed quant team 的 task-board、文件、browser、sys-operation、skill/task-loop 能力；不得修改 `.venv` 或削弱通用 team。

### -9. 工作树同步基线与严格双路径复验（2026-08-04 10:05–10:45）

证据等级：量化 direct 为 `BUSINESS_PASSED`；严格 formal 量化链为 `PATH_PASSED`；完整 E2E 为 `BUSINESS_FAILED`。不得把三者合并成“项目整体通过”。

- Git 基线为本地 HEAD `170e904`；工作树尚未提交或推送。已把审计后的未提交状态镜像到 Mac 可通过 SSH 访问的真实工作树 `D:\work\track2-clean`；比较 114 个变更路径，Git 规范化 hash 差异为 0，两个工作树的 88 项 `git status --short` 差异为 0。
- direct 命令：`jiuwenswarm\.venv\Scripts\python.exe jiuwenswarm\scripts\run_quant_pipeline.py --start-date 2025-01-02 --end-date 2025-05-21`，退出 0。Sina 主源与 Tencent 独立二源均 49/49，CSI300 来自 AKShare；90 个公共交易日，训练 70 日、前向 20 日；15 只、6 板块、现金 5.06%，收益 `+0.7476%`、最大回撤 `1.6424%`。结果为 `output/pipeline_results_20260804_100914.json`，日志为 `output/direct_pipeline_20260804.log`。
- 第一轮 formal session `multi-agent-validation-20260804-101054` 暴露 validator 假通过：`quant.compute_factors` 在 fetch 完成前并发调用并返回 `success=false`，随后成功重试；旧 validator 仍写 `validation_passed=true`。该运行仅是缺陷复现，不是通过证据。
- `FORMAL-FAILCLOSED-0804` 已修复上述缺口：任何量化 RPC 的失败或无效 payload 都使阶段永久失败并立即触发 formal fail-closed；后续成功调用不能覆盖失败。2 项回归测试、目标 Ruff、py_compile 和 diff-check 均退出 0。
- 严格 formal 命令同样使用 `2025-01-02 → 2025-05-21`；session `multi-agent-validation-20260804-102234` 退出 0。8/8 阶段请求数和业务执行数均精确为 1，Alpha/Risk 各自调用专属 RPC 1 次，无角色越权；收益和回撤与 direct 一致。summary/chunks 分别为 `output/multi_agent_summary_20260804-102234.json` 和 `output/multi_agent_chunks_20260804-102234.json`。
- 严格 formal 的资源事实：33 tool calls、842,284 input tokens、13,933 output tokens、755,840 cache tokens、230.4 秒、峰值工作集约 561 MiB。工具流仍含 `build_team/create_task/view_task/claim_task`、4 次 `list_files`，运行日志仍构建 browser subagent 并注册 sys-operation；因此三文件“最小能力 profile”只能算局部实现，任务 `WP1A-ORCH-0803` 已置为 `BLOCKED`。
- 独立 E2E audit 对最新 strict formal 退出 1：`candidate: announcement evidence was not integrated`、`candidate: disclosure facts were not integrated`。产物 `output/audit_result_multi-agent-validation-20260804-102234.json`；当前候选只有 1 条行情 EvidenceRef，公告事实 0、公告公司 0/49，等级为 `TECHNICAL_PASSED`。
- 回归：量化目录 `354 passed, 1 skipped`；swarm assembly `91 passed`；新增 formal validator `2 passed`。60 个变更/新增 Python 文件 Ruff 和 py_compile 均退出 0；`git diff --check` 退出 0。测试约束文档中的“141 项”已过期，当前量化目录为 355 个收集结果。
- 工作树分类：源码、测试、任务契约、长期计划和两份新策略研究 JSON 可进入后续代码审查基线；`output/` 保持忽略。包含本机用户名/IP 的 `MAC_CODEX_HANDOFF.md`、`REMOTE_MAC_WORKFLOW.md` 已加入 `.git/info/exclude`，不得进入公开仓库。
- Mac 本地 clone 的可移植同步包位于 `D:\work\incoming\track2-baseline-20260804\`，包含 tracked patch、68 文件 untracked archive、SHA-256 和 fail-closed 应用命令；精确校验和只保存在包外 README，避免补丁内容自引用。
- `.claude/discussion.md` 已收敛为当前交接，完整旧快照保存为 `discussion-archive-through-20260804.md`；11 个已关闭任务和 1 个被后继任务取代的定位任务已移入 `coordination/archive/2026-08/`。活动目录只保留公告 Scout、能力边界 Scout 和被阻断的 ORCH 任务。

下一阻断项：先决定是为 openJiuwen TeamAgent 增加可配置的 coordination/sys-operation/subagent 能力 ceiling，还是把固定八阶段改为宿主确定性编排、只让 Alpha/Risk 执行有界 Agent 判断；未完成前不得声称 token/随机性优化已经验收。公告 Provider 需要恢复真实 49/49 PIT 证据后再跑完整 E2E。

### -8. WP1-A 共享行情契约与五源 Provider（2026-08-03）

证据等级：`LOCAL_IMPLEMENTED`。本节只证明共享服务在隔离入口可构造并验证真实 `MarketDataBundle`；研发旁路和 JiuwenSwarm 正式路径仍使用旧 Extension 私有抓数，未提升为 `PATH_PASSED`。

- `WP1A-CONTRACT-0803` 新增 canonical OHLCV、逐 ticker provider ledger、显式价格/成交量单位、独立二源、CSI300、交易日历标识、复权策略和时区化 `as_of/retrieved_at` 契约；缺 close 的畸形输入、任一股票跨源偏离、OHLCV/benchmark/metadata 不完整均失败关闭。目标测试 `12 passed`，关联集合 `41 passed`，新旧 Ruff、py_compile、diff-check 和 scope-check 均退出 0。
- `WP1A-PROVIDER-0803` 实现 `Sina → Tencent → AKShare → BaoStock → yfinance` 逐股票主源补缺，并为每只股票再次选择与主源名称和 endpoint 均不同的复核源；二源重叠少于 20 日或任一点价格偏离超过 1% 即抛出 `MarketDataFetchError`。yfinance 的 exclusive end、BaoStock 的 `sh.600000` 代码方向、15:30 前当日未完整行情和成交量倍率均有回归测试。
- 成交量真实单票核对：`600000.SH` 在 2025-05-21 的 Sina/BaoStock 为 `41,672,064` 股；Tencent/AKShare 原始“手”经 ×100 后为 `41,672,100` 股。四个国内源均返回 `90/90` 行；yfinance 在本机仍遭 Yahoo 限流并正确留作末级 fallback。
- 真实隔离 49 股命令退出 0：区间 `2025-01-02 → 2025-05-21`，主源 Sina `49/49`，独立复核源 Tencent `49/49`，公共日历 90 日，CSI300 为 AKShare，`diagnostics_passed=true`、blocker 0、板块 `6/6`。原始行情对 `300394.SZ` 产生 1 条疑似企业行动 warning；本任务未把该 warning 伪写为 blocker 或已解决。
- Provider 目标测试为 `12 passed`；Provider + contract + integrity + market-width 关联集合为 `53 passed`；系统 Ruff 与项目 Ruff、py_compile、diff-check、scope-check 全部退出 0。DeepSeek 独立 Critic 产出 `review.json` 并裁决 `ACCEPT`。
- 本地 Qwen Critic 第一轮因 `66,290 > 65,536` tokens 被接口拒绝；压缩 handoff 后第二轮错误声称实际存在的任务契约、`implementation.json` 和 diff 缺失，未形成可信审查工件。该失败已记录在 `critic_attempts.json`，进一步确认 Qwen 只承担非阻塞线索，HIGH 风险裁决需强模型或 Codex 复核。
- 剩余边界：旧 snapshot 只持久化 close/volume，未保存完整 OHLCV、二源矩阵和 diagnostics；direct/formal 未接线；原始历史价与企业行动调整策略仍需在集成任务中显式裁决。因此不得写“WP1-A 已生产完成”。

### -7. WP1-A 核心反例修正与角色化执行复核（2026-08-03 09:20–09:37）

证据等级：`LOCAL_IMPLEMENTED`。本轮只验收数据一致性和市场宽度的确定性核心，不代表 WP1-A 已接入 direct/formal，也不提高生产路径证据等级。

- 任务 `WP1A-CORE-0802` 在冻结的 4 文件白名单内修正三类反例：跨源差异改为逐 ticker/逐日判断且任一点超阈值即 `passed=false`；量价反演扫描全部共有 ticker；5/20 日宽度使用完整端点区间，并显式拒绝越界 `date_idx`。
- 新增负向覆盖：49 只中仅第 49 只异常不能被均值稀释；第 10 只之后的企业行动异常可检出；成交量缺列不再中断共有 ticker 扫描；路径型价格序列能击穿旧 `tail(N).pct_change().sum()`；短历史和正负越界索引均有断言。
- Ruff：`jiuwenswarm\.venv\Scripts\python.exe -m ruff check` 检查上述 4 文件，退出码 0，`All checks passed`。
- 目标测试：禁用插件自动加载并使用 `-c NUL`，`test_data_integrity.py + test_market_width.py` 为 `29 passed`，退出码 0；加入 `test_agent_decision.py` 的相关集合为 `50 passed`，退出码 0。`pytest.ini` 的插件型 `addopts` 与禁用自动加载组合会导致未使用 `-c NUL` 的一次启动失败，已如实保留在 `implementation.json`。
- `python scripts/agent_task.py scope-check WP1A-CORE-0802`：退出码 0、`passed=true`；实现与审查工件为 `output/agent_handoffs/WP1A-CORE-0802/implementation.json` 和 `review.json`。任务已按本地契约 `VERIFIED` 后关闭，残余生产集成另立 HIGH 风险任务。
- 角色执行实测：DeepSeek Builder 在 300 秒内写入部分正确改动但超时且未生成实现工件；Qwen Critic 在 105.8 秒返回正确 `ACCEPT`，但没有写其声称已写的工件或状态。Codex 以冻结基线保留有用改动、补强反例并生成真实工件。
- 文档任务 `DOC-ROLE-0803` 已把 Goone 身份改为直接陈述当前职责，并在 `AGENT_WORKFLOW.md` 规定新会话只接收当前身份和决策相关事实。Qwen Builder 180 秒超时且只完成一处修改；Qwen Critic 122.3 秒返回 `ACCEPT` 并写工件，但中文工件发生编码错误，已由 Codex 归一为可读 JSON。
- 当前裁决：本地 Qwen 适合 Scout 和非阻塞第二意见，不能让它的口头状态声明成为事实；同步 Builder 必须由 Planner 根据墙钟预算显式路由，并由工件存在性、哈希、测试和 scope-check 独立裁决。
- A0/A1/A2 缓存串线、不可变 OHLCV snapshot、P10 和完整 DecisionTrace 仍未修正；WP1-A 的真实数据服务接线、open/跨源样本/复权口径、机器可读 consistency/regime 报告和入口失败关闭也仍未完成。两项都不得进入下一工作包。

### -6. 多模型开发基础设施（2026-08-02）

证据等级：`LOCAL_IMPLEMENTED`。本项只证明开发协作工具可用，不改变量化 direct/formal 路径和比赛策略的证据等级。

- `python -m py_compile scripts\agent_task.py scripts\agent_role.py`：退出码 0。
- 仓库虚拟环境 Ruff 检查两个脚本：退出码 0，`All checks passed`。
- 三个 skill 分别运行 `quick_validate.py`：均返回 `Skill is valid!`，退出码 0。
- 最新自检任务 `INFRA-E2E-TEST` 完成创建、定位结果校验、7,754 字节最小上下文、冻结 2,052 个 Git 可见文件、task-scoped diff、正常范围检查和清理；人工加入越界文件后 `scope-check` 返回 `violations`、退出码 2，移除后退出码恢复 0，测试文件与工件已清理。
- 并行范围负向测试：`LOCK-A-TEST` 冻结 `scripts/agent_role.py` 后，`LOCK-B-TEST` 对同一文件执行 `freeze` 返回退出码 2，并机器指出冲突任务和文件；两个测试任务均已清理。
- `scripts\claude-deepseek.cmd -p ... --tools= --output-format json --max-turns 1`：退出码 0，返回 `DEEPSEEK_PROFILE_OK`。
- Qwen3.5-9B Q4_K_M 下载完成，GGUF 为 5,627,044,256 字节；Kaiwu `/v1/models` 报告运行上下文 65,536、训练上下文 262,144、参数量 8,953,803,264，显存实测约 5,925/8,188 MiB。
- Anthropic 兼容接口短请求 0.70 秒返回 `QWEN35_API_OK`；`scripts\claude-qwen.cmd --bare -p ...` 退出码 0，3.67 秒返回 `QWEN35_PROFILE_OK`。Claude JSON 中的美元成本是客户端按模型名估算，不是本地服务实际扣费。
- 两个启动入口分别设置独立 `CLAUDE_CONFIG_DIR`，profile 位于用户目录，密钥不写入 Git，也不改写 CC Switch 的单一当前 Provider。
- `scripts\agent-role.cmd` 能按任务风险路由独立角色会话：LOW 默认 Qwen、MEDIUM Builder 默认 DeepSeek、HIGH/UNKNOWN Builder 在启动前失败关闭。
- DeepSeek 角色精简模式 `--bare` 真实请求返回 `BARE_PROFILE_OK`、退出码 0；只输入 1,171 tokens，证明角色会话无需自动加载完整项目长文档。
- 旧 Qwen3.6 的真实 Scout 在 120 秒内没有生成 `location.json`。Qwen3.5 同类任务在 120 秒内生成并校验通过 `location.json`（定位 `choose_profile` 定义和调用点，置信度 0.95），但 Claude 进程未在预算内自行结束，角色命令仍按退出码 124 判失败；因此本地 Scout 适合低成本后台定位，不视为前台低延迟完成证据。1 秒超时负向测试确认无 Claude/Python/Node 孤儿进程。
- CC Switch 的本地 Provider、独立 Qwen profile 和当前用户 Claude settings 已更新到 `qwen3.5-9b-q4_k_m`；开机任务已由 `Kaiwu Qwen3.6 Local Model` 替换为 `Kaiwu Qwen3.5 Local Model`。旧 35B 模型和启动脚本仍保留，可回滚。
- 手工触发新开机任务后状态恢复 `Ready`，11435 Kaiwu 与 11436 Claude 兼容代理均继续监听，证明启动脚本在服务已运行时幂等；下次用户登录会自动启动，无需手工运行模型。
- 并发真请求：同一 PowerShell 进度中同时启动 Qwen 与 DeepSeek 独立 Claude 进程，分别返回 `PARALLEL_QWEN_OK` 和 `PARALLEL_DEEPSEEK_OK`，两者退出码均为 0；期间没有切换 CC Switch，也没有重启任一终端。

### -5. A0/A1/A2 与 WP1-A 审查、生产双路径第七轮复验（2026-07-31 15:49–15:56）

- Git：仍为提交 `170e904` 上的未提交共享工作树；没有新 commit。
- 总体裁决：生产 direct/formal 继续为 `BUSINESS_PASSED`；Missed 的 A0/A1/A2 为 `REJECT / INVALID_EXPERIMENT`；Goone 的 WP1-A 为 `MODIFY / LOCAL_IMPLEMENTED`，两者均不得进入下一工作包。
- A0/A1/A2 实跑：`evaluation/agent_ablation.py` 退出码 0，获取 49 股、119 日，生成 `output/ablation_results_20260731_154926.json`。但脚本在 A1/A2 只计算了新的 `a1_selected/a2_selected`，没有更新 Extension 的 `_selection_result`；`allocate_positions()` 只读取缓存的 A0 selection 并忽略调用参数，因此三组配仓和回测必然相同。
- 串线反例：A0 持仓与 A1 意图持仓只有 12/15 重合，A1 意图换入 `688981.SH/600183.SH/600703.SH`，但 A1 产物的 weight keys 仍完全等于 A0，继续持有 `300750.SZ/600309.SH/601899.SH`。因此 `+0.0000pp` 不是 Agent 无效证据，而是实验对象未进入配仓。
- DecisionTrace 申报也与产物冲突：本次实跑 A1 为 10 proposals、10 accepted、0 rejected；A2 为 19 proposals、19 accepted、0 rejected，不是 discussion 所称“0 accepted / 无 evidence”。产物只保存 trace 计数，没有完整 proposal、调整和拒绝明细。
- 消融未使用或记录“同一不可变 snapshot”；它每次重新联网 fetch，既没有 snapshot id/hash，也未输出计划要求的 P10。`evaluation/agent_ablation.py` ruff 退出码 1，存在 2 个 `F401`。
- WP1-A 局部测试：数据一致性与市场宽度 22 项 fixture 测试通过；全量量化测试 `299 passed, 1 skipped`，退出码 0，但结束仍有未关闭 event loop/socket `ResourceWarning`。Swarm 测试 `112 passed`，退出码 0；`git diff --check` 退出码 0。
- WP1-A 尚无业务入口或机器可读诊断产物：`data_integrity.py`、`market_width.py` 仅被自身单测引用；没有独立市场基准接线、market/pool/sector regime 对照、calendar id、adjustment policy 或 provider mix 报告。当前行情缓存也只保留合并后的 close/volume 和单一来源账本，未保留 open、逐源重叠价格或企业行动时间线，无法执行其申报的完整经济口径检查。
- 跨源规则不符合 fail-closed：超过阈值只追加 warning，`passed` 仍为 true；而且按“每日 49 股平均误差”聚合会稀释单股异常。反例中 49 股仅 1 股偏差 20%，最大平均差仅 0.51%，没有任何 warning。
- 市场宽度窗口存在 off-by-one：所谓 5 日收益用 `tail(5).pct_change()`，实际只有 4 个收益间隔；反例价格 `100→50→51→52→53→54` 的真实 5 日收益为 -46%，模块却输出 `pct_positive_5d=1.0`。企业行动量价反演也只扫描前 10 个 ticker，不能覆盖官方 49 股。
- direct：退出码 0；请求区间 `2025-06-26 → 2026-07-31`，49/49、268 日；训练截止 `2026-07-03`，20 个前向收益；15 只、6 板块、现金 5.06%，收益 `+3.7107%`、最大回撤 `2.2461%`；snapshot `snap_20260731_075223_949304_62da9d4e9373`；1134 条公告、49/49 公司。
- formal：session `multi-agent-validation-20260731-155331`，退出码 0；8/8、精确 3 角色、专属 RPC 各 1、0 越权；各阶段请求/业务执行恰为 1、缓存命中 0；21 tool calls、input `628,189`、output `10,659`、cache `492,288`、耗时 99.1 秒。
- 独立 audit：退出码 0，产物 `output/audit_result_multi-agent-validation-20260731-155331.json`；generator 输出 direct/formal/report `BUSINESS_PASSED`、`audit_status.passed=true`。
- 下一步：Missed 必须修复 variant 隔离和选股→配仓传递，使用一个已落盘且有 hash 的不可变 snapshot，并补“意图 tickers 必须等于 weight keys”、P10、完整 DecisionTrace 和跨 variant 缓存隔离测试；修复前不得进入 WP1-D。Goone 必须先让跨源超阈值 fail-closed、逐 ticker 检查、修正窗口计数并覆盖 49 股，再接入真实数据服务输出机器可读 consistency/regime report；通过前不得进入 WP1-B。
- 证据日志：`output/ablation_review_20260731_154904.stdout.log`、`output/direct_latest_review_20260731_155210.stdout.log`、`output/formal_latest_review_20260731_155308.stdout.log`、`output/multi_agent_chunks_20260731-155331.json`。

### -4. Codex 直接修复与第六轮独立复验（2026-07-31 14:20–14:31）

- Git：仍为提交 `170e904` 上的未提交共享工作树；没有新 commit。
- 修复范围：变参任务管理空转预算、8 阶段统一 `cached/executed` 标记与业务执行计数、audit 的 formal session + direct snapshot + 五项产物 hash 绑定、多 EvidenceRef 审计、公告服务 direct/Extension 双入口接线、公告决策时点纠正和包内原文归档。
- 编排保护：新增与工具参数无关的预算；同一量化进展点后，任务管理工具达到 12 次或全部工具达到 24 次即失败，不再允许通过改变 `update_task` 参数绕过。4 项回归测试覆盖变参循环、阶段推进重置、相同调用和其他工具空转。
- 幂等：首次成功执行统一返回 `cached=false, executed=true`，后续命中返回 `cached=true, executed=false`；formal summary 分别记录请求、业务执行和缓存命中。最新 8 阶段请求数和业务执行数全部恰为 1。
- audit 绑定：JSON 同时记录 formal session、direct snapshot、results/direct log/multi chunks/multi log/multi summary 的规范路径与 SHA-256；generator 重算并精确匹配。5 项负向测试覆盖跨 snapshot、替换 direct、跨 session 和缺 hash。
- 公告时序：direct 与 formal 均以训练窗口末日 `2026-07-02T00:00:00+08:00` 为 as-of，不再使用 formal 运行时当前日期；49 家并发抓取、归档串行写入，保持 PIT 和 write-once 语义。
- 量化全量单测：`277 passed, 1 skipped`，退出码 0；结束时仍有上游/测试装载产生的未关闭 event loop/socket `ResourceWarning`。
- Swarm 装配：`88 passed`，退出码 0。必须正常加载 pytest 插件；人为设置 `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` 会因 `pytest.mark.asyncio` 未注册而在收集期失败，不属于产品回归。
- 本轮修改文件 ruff：`All checks passed!`，退出码 0；`git diff --check` 退出码 0。
- direct：退出码 0；49/49、6/6、15 只、现金 5.06%，收益 `+3.2468%`、最大回撤 `2.8762%`；snapshot `snap_20260731_062558_498636_29090fb1e0c5`；结果 `output/pipeline_results_20260731_142558.json`。
- direct 公告与报告：49/49 公司有事件，1123 条公告事实；候选包共 1124 条 EvidenceRef（1 条行情 snapshot + 1123 条公告），包内 archive 1123 份原始 JSON，49 份报告，`quality_passed=true`、`overall_grade=FINANCIAL_PARTIAL`。
- formal：session `multi-agent-validation-20260731-142732`，退出码 0；8/8、精确 3 角色、专属 RPC 各 1、0 越权；29 tool calls、input `818,573`、output `9,513`、cache `674,944`、耗时 136.7 秒。
- formal 工具分布：8 个量化 RPC 各 1 次；`update_task=6`、`view_task=6`，未触发预算。业务执行计数为 fetch/factors/alpha/risk/select/allocate/backtest/report 各 1，缓存命中均为 0。
- 独立 audit：退出码 0；角色、8 RPC、业务执行次数、仓位、snapshot、多证据路径/hash/as-of、公告 archive、报告 disclosure 均通过；产物 `output/audit_result_multi-agent-validation-20260731-142732.json`。
- summary generator：退出码 0；精确绑定上述五项产物后输出 direct/formal/report `BUSINESS_PASSED`、`audit_status.passed=true`；产物 `output/validation_summary.json`。
- 状态裁决：WP0-C 的公告 Provider、归档、报告分级和双路径接线已经达到业务通过，可关闭；WP0-B 的角色迁移与工程路径通过，但 A0/A1/A2 Agent 因果消融尚未完成，因此 WP0-B 研究验收仍保持打开。
- 证据日志：`output/direct_fix_20260731_142538.stdout.log`、`output/formal_fix_20260731_142700.stdout.log`、`output/multi_agent_chunks_20260731-142732.json`。

### -3. WP0-B/WP0-C 第五轮独立复验（2026-07-31 13:59–14:06）

- Git：仍为提交 `170e904` 上的未提交工作树；没有新 commit。
- 静态检查：对全部新增/修改 Python 文件运行 ruff，输出 `All checks passed!`、退出码 0；`git diff --check` 退出码 0。
- 量化单测：`268 passed, 1 skipped`，退出码 0；结束时仍有未关闭 event loop/socket 的 `ResourceWarning`。
- Swarm 装配测试：`88 passed`，退出码 0。
- Goone 公告真实网络 smoke：`600000.SH`、`000001.SZ` 各 30 facts，manifest 共 60 条，退出码 0；7 项 fixture 单测已纳入上述全量测试。该实现局部可接收，但 direct、formal 和 Extension 报告入口仍没有 `AnnouncementService`/`run_announcement_service` 调用，WP0-C 保持 `LOCAL_IMPLEMENTED`。
- Missed canonical idempotency 恶意重放：依次向 allocation 传入正确顺序、逆序、缺一只并附任意权重，`PositionSizer.allocate()` 只执行 1 次，三次返回权重一致，`_phase_results` 只含 canonical phase 名；此修复局部通过。
- 幂等结果标记仍不一致：首次执行返回值没有 `cached`/`executed` 字段，只有缓存副本记录 `cached=false, executed=true`；后续命中才返回 `cached=true, executed=false`。runner/audit 也尚未统计 8 个阶段的业务执行次数。
- direct：`scripts/run_quant_pipeline.py` 退出码 0；49/49、6/6、15 只、现金 5.06%；收益 `+3.2468%`、最大回撤 `2.8762%`；snapshot `snap_20260731_060211_339024_29090fb1e0c5`；产物 `output/pipeline_results_20260731_140211.json`。报告仍为 `TECHNICAL_PASSED`，无公告证据。
- formal：`evaluation/run_multi_agent.py` 退出码 1；session `multi-agent-validation-20260731-140254`，耗时 176.5 秒，仅 fetch/factors 2/8 完成，Alpha/Risk 均未参与，select/allocate/backtest/report 均未执行。
- formal 资源：96 次工具调用、input `1,975,273`、output `8,605`、cache `1,884,032`；其中 `update_task` 90 次。现有保护只拦截“参数和结果完全相同”的连续工具签名，Agent 通过改变任务更新参数绕过保护，最终由 150 秒无量化进展超时终止。
- formal 正确失败关闭，没有把残缺执行误报为成功。这说明 fail-closed 有效，但正式路径在当前工作树上不稳定，WP0-B 整体不能关闭。
- 独立 audit 对上述失败 session 退出码 1，并生成 `output/audit_result_multi-agent-validation-20260731-140254.json`；失败原因为资源角色明细不完整、缺少 6 个量化阶段、Alpha/Risk 没有专属 RPC。
- `generate_validation_summary.py` 随后退出码 0，并把最新状态写为 direct `BUSINESS_PASSED`、formal `FAILED`、report `FAILED`、`audit_status.passed=false`。同 session 失败传递已经生效。
- audit 绑定仍不完整：audit JSON 有 formal `session_id`、`results_sha256` 和 `multi_chunks_sha256`，但没有 direct `snapshot_id`；generator 只比较 formal session，不重算并核对当前 direct result 或 chunks 的 hash。因此“同一 formal session + 被替换的 direct 结果”仍可能错误升级为 `BUSINESS_PASSED`。
- `audit_candidate_evidence()` 仍要求 EvidenceRef 集合严格等于 `{snapshot_id}`。公告接线后证据集必然大于 1；如不先把规则改成“必须包含并校验 snapshot，同时逐条校验新增证据”，正确的公告集成会被旧审计规则拒绝。
- 证据日志：`output/direct_review_20260731_140152.stdout.log`、`output/formal_review_20260731_140220.stdout.log`、`output/multi_agent_chunks_20260731-140254.json`、`output/validation_summary.json`。

### -2. WP0-B/WP0-C 第四轮独立复验（2026-07-31 13:07–13:12）

- Git：仍为提交 `170e904` 上的未提交工作树；没有新 commit。
- 量化单测：`261 passed, 1 skipped`，退出码 0；结束时仍有未关闭 event loop/socket 的 `ResourceWarning`。
- Swarm 装配测试：`88 passed`，退出码 0。
- 对全部新增/修改 Python 文件运行 ruff：退出码 1；`reporting/__init__.py` 导出的 `AnnouncementService`、`ServiceResult`、`run_announcement_service` 未进入 `__all__`，共 3 个 `F401`。
- `git diff --check`：退出码 2；`reporting/providers/__init__.py` 存在 EOF 多余空行。
- 配置处理：`run_multi_agent.py` 已改为只替换 `quant_team`，不再遍历删除其他 team。代码修复可接收；尚缺“无关 team 保留”的自动化回归测试。
- 公告 smoke：`600000.SH`、`000001.SZ` 均为 30 facts、30 raw、30 refs，manifest 共 60 条；详情 URL 示例经 `curl -I -L` 返回 HTTP 200。具体 URL 修复通过。
- `AnnouncementService` 已实现 fetch → archive → manifest，但 `run_quant_pipeline.py`、`run_multi_agent.py` 和 Extension 报告入口均没有调用该服务。其模块 docstring 所称“两路径共同调用”目前只是设计目标。
- direct：退出码 0；49/49、6/6、15 只、现金 5.06%；收益 `+3.2468%`、最大回撤 `2.8762%`；产物 `output/pipeline_results_20260731_130857.json`。输出仍为 `TECHNICAL_PASSED`，无公告步骤。
- formal：session `multi-agent-validation-20260731-130922`，退出码 0；8/8、恰 3 角色、专属 RPC 各 1 次、0 越权；input `1,521,817`、tool calls `39`、耗时 151.6 秒。
- formal 实际有 10 次量化 RPC，其中 `allocate_positions` 成功调用 3 次。独立反例也证明：将同一 selected ticker 集合逆序传入会产生两个不同的参数化缓存 key，并让 PositionSizer 实际执行 2 次。结果虽然相同，但“成功阶段只执行一次”不成立。
- 同批次独立 E2E audit：退出码 0，角色、8 种 RPC、仓位和快照结构通过；当前 audit 只检查工具种类，不检查成功阶段执行次数。
- `generate_validation_summary.py` 的分级函数能在 audit 缺失时降为 `PATH_PASSED`，这部分修复有效；但主程序只寻找目录中“最新”的 `audit_result_*.json`，既不校验 session/snapshot，也没有对应文件生产者。本次 audit 退出 0 后生成 summary，`audit_status.passed` 仍为 `null`。
- 最新候选包 `evidence_manifest.json` 只有 1 条行情 snapshot；`report_manifest.json` 为 `overall_grade=TECHNICAL_PASSED`、disclosure=0。WP0-C 保持 `LOCAL_IMPLEMENTED`。

### -1. 最新工作树独立复验（2026-07-31 11:42–11:48）

- Git：仍为提交 `170e904` 上的未提交 Missed/Goone 工作树；没有新 commit。
- 量化单测：`259 passed, 1 skipped`，退出码 0；结束时仍有未关闭 event loop/socket 的 `ResourceWarning`。
- Swarm 装配测试：`88 passed`，退出码 0。
- 对本轮全部新增/修改 Python 文件运行 ruff：退出码 1；`.agents/skills/verify-quant-e2e/scripts/audit_run_artifacts.py:18` 存在 `E402`。
- 公告真实网络 smoke：`600000.SH`、`000001.SZ` 均返回 `status=complete`、30 facts、30 raw payloads、30 EvidenceRefs，证明去重死循环已修复；但所有 `source_url` 仍是通用 Eastmoney API，而不是具体公告/原文 URL。
- 公告归档、write-once、路径穿越和 Quality Gate fail-closed 的局部测试通过；direct/formal 中没有公告或 `EvidenceArchive` 调用点，所以 WP0-C 仍是 `LOCAL_IMPLEMENTED`。
- direct：`scripts/run_quant_pipeline.py` 退出码 0；49/49、6/6、15 只、现金 5.06%；收益 `+3.2468%`、最大回撤 `2.8762%`；产物 `output/pipeline_results_20260731_114541.json`。
- formal：session `multi-agent-validation-20260731-114621`，退出码 0；8/8、恰 3 角色、专属 RPC 各 1 次、0 越权；收益与回撤同 direct；input `1,235,300`、tool calls `32`、耗时 137 秒。
- 本次 formal 有 10 次量化 RPC：`select_stocks` 与 `allocate_positions` 各成功执行 2 次；幂等只覆盖 compute/alpha/risk 三个阶段，未满足“任一成功阶段不得重复执行”。
- 独立 E2E audit：本次和既有 `104820/105317/105638` 三个 session 均退出码 0；角色、8 个 RPC 种类、仓位约束通过。
- 既有三次资源事实如下；先前“后两次约 70 万 token、20–29 tool calls”的报告不准确：

| Session | 阶段 | 成员 | Tool Calls | Input Tokens | 耗时 |
|---|---|---|---:|---:|---:|
| `104820` | 8/8 | 3 | 20 | 693,709 | 97.2s |
| `105317` | 8/8 | 3 | 42 | 1,451,984 | 162.8s |
| `105638` | 8/8 | 3 | 27 | 857,473 | 130.4s |
| `114621`（Codex 独立复跑） | 8/8 | 3 | 32 | 1,235,300 | 137.0s |

- `evaluation/run_multi_agent.py` 会删除用户工作区 `modes.team` 下除 `quant_team` 外的全部 team；这不是隔离配置，可能破坏无关用户配置，必须改成 session 隔离或仅替换明确命名的旧量化 team。
- `scripts/generate_validation_summary.py` 尚未读取独立 audit 结果，只要 formal summary 自报 `validation_passed` 就写 `BUSINESS_PASSED`；因此不能作为发布事实聚合器。
- `AGENT_OVERLAY_ENABLED=False` 正确保护了生产组合，direct/formal 的持仓集合与绩效一致；这同时意味着 Agent 对选股/配仓的因果增量尚未完成，A0/A1/A2 仍待实验。

### 0. WP0-B 原子迁移完成验收（2026-07-30 18:44–18:51）

- Git：`170e904` 上的未提交 Missed/Goone 工作树。
- 量化单测：`229 passed`，退出码 0。
- ruff（Missed 所有文件）：`All checks passed`，退出码 0。
- 旧代码删除：`bull_analyst.md`、`bear_analyst.md` 已物理删除；旧 bull_view/bear_view RPC handler 已删除；Extension 恰好 8 个 RPC handler；`config.yaml`/`providers/tools.py`/`team_runtime_inheritance.py`/`test_swarm_assembly.py`/`policy_validator` 全部迁至新角色。
- direct：`scripts/run_quant_pipeline.py` 退出码 0，49/49、6/6、15 只、现金 5.06%；产物 `output/pipeline_results_20260730_184428.json`。
- formal：session `multi-agent-validation-20260730-184818`，退出码 0，耗时 97.7 秒。8/8 RPC。3 成员：`quant-leader`(1505) + `alpha_analyst`(554) + `risk_evidence_analyst`(545)。专属 RPC 各 1 次、0 越权。
- formal 资源：input `875,743`（比基线 `1,204,831` 降 27.3%）、output `12,597`、cache `723,840`、tool calls `23`。
- Agent 决策接入：`select_stocks` 读取 `_alpha_result`/`_risk_result`，转换为 `AgentProposal`，经 `DecisionAssembler.assemble()` 合并，调整后分数进入选股排序。
- 独立 E2E audit：退出码 0，`E2E AUDIT: PASSED`。8 工具、3 角色、专属 RPC 正确识别、无越权。该单次成功已被 2026-07-31 复验推翻其稳定性结论，仅保留为历史运行证据。
- WP1-B0（Goone，不可变快照重跑）：统一基线和 Phase B 均退出码 0，20 窗满足 embargo 协议。两因子 control 配对差 `+0.8185pp`/效用胜率 80%；T2 `+0.8356pp`/17/20。仍是开发集，保持 `RESEARCH_ONLY`。

以下第 1–4 节保留提交 `170e904` 的历史通过证据（Bull/Bear 旧路径），用于回归比较；当前工作树的新角色路径证据在上面第 0 节。正式提交前必须用最终数据重新运行全部命令。

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

1. **资源成本仍需基准化**：最新 capability-ceiling formal 已降至 95,569 input、6,510 output、61,952 cache tokens 和 12 tool calls，显著低于历史通用团队路径；官方基准尚未公布，仍不能折算分数或宣称资源分已达标。
2. **Agent 路径有随机性**：本轮曾出现 Agent 在正确配仓后擅自删掉一只股票并二次配仓。正式验收正确失败；Extension 现已把选股、配仓、回测、报告的输入锁定为服务端缓存的前序结果，LLM 只能触发、不能改写。150 秒阶段无进展和 8/8 后显式 runtime teardown 也已加入，但减少 prompt/上下文膨胀仍是 P0。
3. **报告广度不足**：当前 49 份报告主要来自技术面和市场行情，`data_provider_status` 仍为 partial；不能宣称已经完成基本面、公告、新闻或宏观分析。
4. **报告深度不均**：49 家均有技术面与公告披露报告，但只有被 Alpha/Risk 覆盖的候选包含角色观点；fundamental/news-risk grade 仍为 0。
5. **策略未完成样本外晋级**：T2 在 21 个开发窗口优于生产，但未完成封存/未来窗口验证，生产配置未切换。
6. **契约未确认**：49/50、现金口径、报告对初赛的作用仍需主办方书面答复。
7. **上游弃用警告**：正式运行出现 Authlib、Pydantic/openJiuwen 弃用警告；当前不影响退出码和业务结果，但升级依赖前必须回归。
8. **历史窗口尚未完全对齐官方节奏**：当前 unified/Phase B 使用“决策后下一交易日开盘”入场；官方节奏是提交后隔 2026-08-24 一个完整交易日，再于 2026-08-25 开盘买入。因此原 T2 `+0.91pp / 15/21` 仅保留为研究线索，加入一交易日 embargo 重跑前不得作为提交策略晋级证据。

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
3. 在已通过的公告 PIT 与 capability ceiling 基线上补齐 fundamental/news-risk 的真实 point-in-time Provider 和证据归档；未达到两类 grade 前不得改写 `FINANCIAL_PARTIAL`。
4. 先按“决策收盘 → 1 个交易日 embargo → 首日开盘买入 → 20 日固定股数 → 末日收盘卖出”重跑 production/T2/统一基线，再执行嵌套外层验证；重跑前不得沿用旧 T2 晋级结论。
5. 最终提交前重新运行本文件全部命令，再生成 zip；不得复用当前候选包冒充正式包。
