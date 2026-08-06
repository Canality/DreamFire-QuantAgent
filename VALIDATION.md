# 当前验证状态

> 本文件是项目可运行状态的唯一事实源。计划、README、Agent 身份和历史只能
> 引用这里，不得把本地单测、旧 session 或设计目标改写成新的业务通过。

## 结论（2026-08-06）

| 对象 | 证据等级 | 当前结论 |
|---|---|---|
| v2.14 量化 direct | BUSINESS_PASSED（历史当前锚） | commit `89322cd` 的 `2025-01-02 → 2025-05-21` 运行 49/49、6/6、15 只，收益 `+0.7476%`、最大回撤 `1.6424%`；候选绑定 `4e4ff29c8269d5e9a43e96a5fabd05c89ce10d1a8742c2c624c878db59f2fac1` |
| v2.14 JiuwenSwarm formal | BUSINESS_PASSED（历史当前锚） | session `multi-agent-validation-20260805-100147` 完成 8/8、12 tool calls、0 error，三金融角色无越权；候选绑定 `50d49ce963809c72cfda73f53ec7ac0cd0e419fdb4d6c16a487781f45dc529a4`，独立 E2E 通过 |
| v2.15 Mac 候选 | LOCAL_IMPLEMENTED / WINDOWS_PENDING | 实现边界 `89322cdff88ccd3172055fe870efbf5d45676ff6..f205967b11065b36fc1ef6d7898c2cf79dea0872`；所有代码工作包均有独立审查，但本轮没有 fresh direct/formal/model/network 运行，不能继承为新的 BUSINESS_PASSED |
| WP0-A 文档契约 | LOCAL_IMPLEMENTED | README 动态区块由绑定产物生成；runtime Skill 镜像恢复并防漂移；无产物时保持 `NOT_GENERATED`，不能从文档提升事实 |
| WP0-B Agent 决策契约 | LOCAL_IMPLEMENTED / OVERLAY_DISABLED | PIT `AgentProposal`、不可变 `DecisionTrace`、共享 server-owned selection 和 A0/A1/A2 诊断已实现；生产 overlay 仍关闭，没有样本外晋级证据 |
| WP0-C 公告 replay | LOCAL_IMPLEMENTED / WINDOWS_PENDING | 已接受公告运行可写 create-once receipt，并从 hash-verified archive 离线重放相同 facts/status/snapshot；direct/formal 使用同一投影。没有新网络或 formal 运行，不提高报告等级 |
| WP1-B 嵌套评测 | PATH_PASSED（v2.14） | 一完整交易日 embargo、首日开盘、固定股数 20 日、末日收盘、内外层隔离和 Bootstrap 已实现；accepted review 现以相同 5,956 字节固化到 Git，干净检出不再依赖 ignored `output/` |
| WP1-C challengers | PATH_PASSED / DOES_NOT_QUALIFY | 趋势一致性、板块领导力和尾部风险三个冻结候选均未晋级；production 仍为 `production_six_factor`，T2 仍为 `RESEARCH_ONLY` |
| WP1-D deterministic replay | LOCAL_IMPLEMENTED | 8 阶段精确状态机、snapshot/epoch/single-flight 绑定和 20 次无网络/无 LLM replay 已实现；20 次一致不等于三次 formal |
| WP1-D 资源与生命周期 | LOCAL_IMPLEMENTED / WINDOWS_PENDING | 每阶段/角色 token、ToolCard schema、进程树 RSS、并发和三 run 聚合器已实现；`os._exit()` 已删除，session/stream/Runner bounded teardown 与 PID watchdog 已实现；Windows 三次真实 formal、P95/RSS/并发和正常返回仍待验 |
| WP1-D 失败关闭 | LOCAL_IMPLEMENTED / WINDOWS_PENDING | 同名工具第三次连续结构化失败输出不可变诊断；split result 必须唯一 call-id/name 绑定；正式 8 个 Quant RPC 仍首次失败即关闭，不获得重试许可 |
| WP1-E0/E1 | LOCAL_IMPLEMENTED / RESEARCH_ONLY | 12 项 Factor Registry、稳定 implementation hash 和成熟标签因子研究策略已实现；没有真实完整 trust roots，不产生当前因子方向/权重，不接 production |
| WP1-E1P Provider 准入 | LOCAL_IMPLEMENTED / DATA_BLOCKED | official calendar 单项可用；历史行业、PIT corporate-action/adjusted OHLC、逐 ticker ledger、成熟 label 和可信 E0 snapshot 不可用，E2/E3/E4 不得开始 |
| PIT fundamental/news-risk | DATA_BLOCKED | fundamental grade 已失败关闭 generic fact；仍缺合法 structured historical source、版本/更正链和跨设备交付授权。news-risk 也未建立独立准入 |
| 完整金融报告 | FINANCIAL_PARTIAL | 公告和技术证据可审计，但 fundamental/news-risk/宏观/另类数据不足，不能写 `FULL_REPORT_PASSED` |
| 正式提交契约 | PROVISIONAL / BLOCKED | 49/50、现金权重和报告作用仍需主办方可归档书面答复；不得生成或命名正式提交包 |
| 开发协作治理 | LOCAL_IMPLEMENTED | 活动开发身份精确为 Codex 计划/验收与 Claude 执行/开发；双方平等、有界质疑，定位/实现/审查是阶段；8 个旧模型路由启动器已删除，金融运行时三角色不变 |

## 证据边界

### 最后一次已接受业务运行

v2.14 commit：`89322cdff88ccd3172055fe870efbf5d45676ff6`。

- direct：`output/pipeline_results_20260805_100118.json`，退出 0；49/49、6/6、
  15 只、现金 5.06%、公告 1,470 条、49/49 披露。
- formal：`multi-agent-validation-20260805-100147`，退出 0，48.6 秒；8/8、
  12 tool calls、0 error；Alpha/Risk & Evidence 专属 RPC 各 1，无越权。
- formal 资源：97,209 input、6,356 output、65,280 cache tokens。它是单次
  已接受工件，不是 WP1-D 三次当前基准。
- 独立 audit：`passed=true`、failures 为空；v2.14 review SHA-256：
  `e04e34ddebf462d10d219fb1bd3162cabe48f53dd84f7a468c8b1c2f103eabfd`。

这些结果继续支持 v2.14 的量化/公告增强路径，但不自动覆盖 v2.15 的运行时、
资源、teardown 和失败关闭改动。Windows 必须在新提交链上 fresh 复验。

### v2.15 Mac 本地实现链

| 工作包 | commit | 本地验收 | Windows 状态 |
|---|---|---|---|
| E0/E1/E1P 与数据门 | `9c16155..5391cbb` | 聚焦与独立审查通过；仅 calendar 单项准入 | 待按提交链复验；外部数据仍阻塞 |
| WP0-A 文档契约 | `921fe88` | 33 个 closure 文档/生成契约通过 | 待复验 |
| WP0-B 决策契约 | `eb81ce5` | 46 focused，通过多轮反例 | 待复验；overlay 关闭 |
| WP0-C replay parity | `0a32068` | 100 focused；5 个 P1 关闭 | 待复验；无 fresh network/formal |
| WP1-D deterministic replay | `287f5e8` | 22 focused；20-run fixture 一致 | 待复验 |
| WP1-D resource bench | `cf6017d` | 32 focused；P1/P2 关闭 | 已复制 Windows，正式三 run 待执行 |
| WP1-D session teardown | `2a04f49` | 44 focused；5 轮生命周期反例关闭 | 已复制 Windows，真实正常退出待执行 |
| WP1-D failure guard | `44acb51` | 35 focused；4 项 P1/P2 关闭 | 待交付/复验 |
| WP1-B evidence pin | `6b6482e` | 19 focused；全量 quant `610 passed, 1 skipped` | 待交付/复验 |
| 两方治理 | `f205967` | 文档契约 22 passed；3 P1/2 P2 关闭 | 待交付/复验 |

`610 passed, 1 skipped` 绑定 code head `6b6482e`；`f205967` 后只改变开发文档、
文档测试、任务 CLI 和删除旧开发启动器，聚焦 22 个文档契约通过。本轮没有把
这些单测写成 direct/formal 运行。

## 当前冻结状态

- 生产策略：`production_six_factor`。
- T2：`RESEARCH_ONLY`。
- WP1-C：三个候选全部 `DOES_NOT_QUALIFY`，没有第四候选。
- Agent overlay：关闭。
- 报告：`FINANCIAL_PARTIAL`。
- SubmissionContract：`PROVISIONAL / BLOCKED`。
- E2/E3/E4：未开始，受 E1P 数据能力门阻塞。
- 开发协作：Codex/Claude 两方；金融运行时仍为三角色和 8 RPC。

## 仍缺少什么

### Windows 必须完成

1. 按 commit 依赖链校验每个 bundle/patch、BASE/HEAD、白名单、测试和 handoff
   hash；不要直接覆盖脏主工作区。
2. 在同一不可变 snapshot 上执行 3 次完整 formal：每次 8/8、无越权、无非法
   重试、无悬挂，正常返回。
3. 用 `aggregate_formal_resources.py` 核验三份不同 summary hash 且同一
   market/snapshot/manifest/ToolCard identity；P95 ≤120 秒、peak RSS ≤600 MB，
   concurrency 有真实值，input token 相对 1,204,831 降低至少 50%。
4. fresh direct/formal/E2E 验证公告 replay projection、服务端 selection、
   teardown、failure guard 和候选绑定没有破坏 v2.14 业务能力。
5. 回传 task-scoped verdict 或 `D:\work\outgoing\<TASK-ID>` 修正补丁；同一任务
   不在 Windows/Mac 同时修改，不自动 push。

### 外部数据/授权

1. E1P 需要可归档、可跨设备复验的历史 sector、corporate-action/adjusted
   OHLC、逐 ticker ledger、成熟标签和可信 E0 snapshot；缺任一项保持阻塞。
2. fundamental 需要 structured historical line items、taxonomy/version、期间、
   合并/审计/单位币种、publication/observed 和 correction lineage；metadata/PDF
   discovery 不能代替。
3. news-risk 需独立来源授权、事件/修订/空结果和 49/49 状态契约。

### 主办方

- 书面确认 Excel 49 家与口述 50 家的裁决；
- 书面确认权重和为 1 是否包含现金；
- 书面确认报告完整性对初赛筛选/评分的作用。

## 下一阶段开始条件

1. Windows 采用并复验当前 commit 链后，可关闭 v2.15 的 `WINDOWS_PENDING`。
2. WP1-D 三次正式门通过后，M4 才能关闭；单次 v2.14 工件不能代替。
3. E1P 全部能力 `AVAILABLE` 后才能按 E2 → E3 → E4 分任务开发，不能一次性
   合并，也不能用 test-only evidence。
4. fundamental/news-risk 只有授权 source 到位后才恢复 Provider 工作。
5. 主办方答复归档并生成 contract version/hash 后才开始 WP2 正式包。
6. 最终提交前在最终 commit、最终数据和 Windows 环境 fresh 重跑 direct、
   formal 和独立 E2E；不得复用 v2.14 候选冒充最终包。

## 仓库保留边界

- Git 跟踪源码、当前文档、官方材料、可复现实验、任务契约和版本 history。
- `output/`、交付包、缓存、媒体和 `tmp/` 不提交；本轮未删除或改写用户 `tmp/`。
- v2.13/v2.14、旧任务、官方材料和历史研究证据保持原样；v2.15 只追加新记录。
- 未经用户明确授权不 push、tag 或修改 Windows 主工作区。
