# 当前验证状态

> 本文件是项目可运行状态的唯一事实源。计划、README、Agent 身份和历史只能
> 引用这里，不得把本地单测、旧 session 或设计目标改写成新的业务通过。

## 结论（2026-08-13）

| 对象 | 证据等级 | 当前结论 |
|---|---|---|
| v2.15 Windows formal | BUSINESS_PASSED | commit `1f84b01` 的 `2025-01-02 → 2025-05-21` 三次 8/8（115235/122418/122852），REAL_EXIT=0，12 tool calls，0 errors，三金融角色无越权；P95 105s / RSS 575MB / token -91% |
| v2.15 E1P 数据能力 | BUSINESS_PASSED | 五项全部 AVAILABLE：calendar + corporate_action（baostock 347 行）+ factor_snapshot（baostock 77,541 行 qfq）+ forward_label（604 决策日）+ sector（赛题 6 板块） |
| v2.14 量化 direct | BUSINESS_PASSED（历史锚） | commit `89322cd`，收益 `+0.7476%`、最大回撤 `1.6424%` |
| GitHub 发布前 fresh direct | PATH_PASSED | 2026-08-09 在 Windows 请求 `2025-07-04 → 2026-08-08` 数据，exit 0；覆盖 49/49、6 板块、15 持仓、cash 5.07%、quality `PASSED`；direct 路径没有 Agent views，不提升为 `BUSINESS_PASSED` |
| v2.14 JiuwenSwarm formal | BUSINESS_PASSED（历史锚） | session `multi-agent-validation-20260805-100147` 8/8、12 tool calls、0 error |
| WP0-A 文档契约 | LOCAL_IMPLEMENTED | README 动态区块由绑定产物生成；runtime Skill 镜像恢复并防漂移；无产物时保持 `NOT_GENERATED`，不能从文档提升事实 |
| WP0-B Agent 决策契约 | LOCAL_IMPLEMENTED / OVERLAY_DISABLED | PIT `AgentProposal`、不可变 `DecisionTrace`、共享 server-owned selection 和 A0/A1/A2 诊断已实现；生产 overlay 仍关闭，没有样本外晋级证据 |
| WP0-C 公告 replay | LOCAL_IMPLEMENTED | hash-verified archive 离线重放；direct/formal 同一投影 |
| WP1-B 嵌套评测 | PATH_PASSED（v2.14） | embargo/首日开盘/20 日/末日收盘/内外层隔离/Bootstrap 已实现并固化 |
| WP1-C challengers | PATH_PASSED / DOES_NOT_QUALIFY | 三个候选均未晋级；production 仍为 `production_six_factor` |
| WP1-D 全包 | BUSINESS_PASSED | 8 阶段状态机/20 次 replay/资源门/teardown/failure-guard 全部通过 Windows 三次 formal |
| WP1-E0/E1 | LOCAL_IMPLEMENTED / RESEARCH_ONLY | 12 项 Factor Registry、稳定 implementation hash 和成熟标签因子研究策略已实现；没有真实完整 trust roots，不产生当前因子方向/权重，不接 production |
| WP1-E1P Provider 准入 | BUSINESS_PASSED | 五项全部 AVAILABLE：E0 snapshot（baostock qfq）/ corporate action（baostock）/ forward label（604 日）/ sector（静态 6 板块）/ calendar（原有） |
| WP1-E2 策略池 | LOCAL_IMPLEMENTED / RESEARCH_ONLY | E2A 六槽位不可变注册表与 E2B prior-only 六维相似市场选择器已通过 Codex 独立验收；真实对齐 benchmark 仍缺失，相似分支保持 `BENCHMARK_UNAVAILABLE`；未接 production |
| WP1-E2C 策略池回放 | LOCAL_IMPLEMENTED / RESEARCH_ONLY | 2026-08-11 Windows 独立复跑 12 个不重叠成熟窗口并复现 artifact SHA-256；T2 通过预注册研究门，三类趋势因可比窗口不足失败关闭，相似市场因 benchmark 缺失失败关闭；production 未改变 |
| WP1-E3 有界 Agent 融合 | LOCAL_IMPLEMENTED / RESEARCH_ONLY | `WP1-E3-R1` 已由 Codex 独立验收并关闭；fresh scope-check、61 项聚焦测试、107 项相邻测试、真实 PIT 前缀工件、Ruff 和差异检查均通过；未运行真实模型或 direct/formal/RPC/E2E，overlay 与 production 均未改变 |
| PIT fundamental/news-risk | DATA_BLOCKED | fundamental grade 已失败关闭 generic fact；仍缺合法 structured historical source、版本/更正链和跨设备交付授权。news-risk 也未建立独立准入 |
| 完整金融报告 | FINANCIAL_PARTIAL | 公告和技术证据可审计，但 fundamental/news-risk/宏观/另类数据不足，不能写 `FULL_REPORT_PASSED` |
| 正式提交契约 | PROVISIONAL / BLOCKED | 49/50、现金权重和报告作用仍需主办方可归档书面答复；不得生成或命名正式提交包 |
| 开发协作治理 | LOCAL_IMPLEMENTED / BRIDGE_FIXED | Codex/Claude 两方平等协作；AGENTS.md 已记录 Windows 跨平台 5 陷阱；BRIDGE-OPS-5 已验收，Stop hook 默认 actionable + pending-record 跨进程耐久化，47 项聚焦测试通过；双 CLI 桥接不属于产品运行证据 |

## 证据边界

### 最后一次已接受业务运行

v2.15 commit：`1f84b01`（2026-08-07）。

- formal：三次 8/8（`115235`/`122418`/`122852`），REAL_EXIT=0，12 tool calls，
  0 errors，三金融角色无越权，quality_passed=True，summary 完整生成。
- 资源门：P95 105.1s ≤ 120s，峰值 RSS 575.09MB ≤ 600MB，concurrency=1 实测，
  token 降幅 91.3% ≥ 50%。
- 五次 Windows 缺陷全部修复（supervisor 祖先链/mappingproxy 序列化/asyncio 退出/
  evidence 身份比对/mappingproxy 泄漏），111 聚焦测试通过。

v2.14 锚 commit `89322cd` 仍为可回溯历史参考。

### GitHub 发布前 fresh 路径复验（2026-08-09）

- 工作目录：`jiuwenswarm`。
- 命令：`.\.venv\Scripts\python.exe -u scripts/run_quant_pipeline.py`。
- 请求数据区间：`2025-07-04 → 2026-08-08`；退出码：`0`。
- 结果：官方范围覆盖 49/49、6 个板块、15 个持仓、现金权重 5.07%，quality
  `PASSED`。
- 产物：`output/direct_github_release_20260809.log`、
  `output/pipeline_results_20260809_133817.json`、
  `output/submission_candidates/direct-20260809_133817`（均相对仓库根目录）。
- 证据等级仅为 `PATH_PASSED`：direct 运行明确警告没有 Agent views，不能证明
  正式三角色、8/8 Quant RPC 或角色权限边界。
- fresh formal：`Not tested`；combined independent E2E：`Not tested`。当前 shell
  没有安全的模型 credential，不复用或调用已经泄露的 key，也不为绕过该边界降低
  正式运行门禁。

这次 fresh direct 不降低或替代 2026-08-07 v2.15 formal 的
`BUSINESS_PASSED` 历史锚，也不改变 `SubmissionContract` 的
`PROVISIONAL / BLOCKED` 状态。

### v2.15 Windows 实现链

| commit | 内容 |
|---|---|
| `bbe728d` | v2.15 Mac 全量合入 |
| `6a7f883` | supervisor 祖先链 + mappingproxy 序列化修复 |
| `6ec2de3` | asyncio 退出修复 |
| `8e690f5` | asyncio.run 替代方案 |
| `1bc3361` | evidence 身份比对修复 |
| `62730ec` | mappingproxy 泄漏修复 |
| `2317ddc` | phantom pending 过滤 |
| `2c65c11` | 聚合器 identity 调整 |
| `9ffcc17` | PIT_CORPORATE_ACTION 准入 |
| `de5a618` | E0_FACTOR_SNAPSHOT 准入 |
| `4187062` | OFFICIAL_FORWARD_LABEL 准入 |
| `1f84b01` | PIT_SECTOR_STATIC_V1 准入 |

### WP1-E2C 本地确定性策略池回放（2026-08-11）

- 任务：`WP1-E2C-R1`；代码锚：`4b96859`；证据等级：`LOCAL_IMPLEMENTED / RESEARCH_ONLY`。
- Windows 命令：`jiuwenswarm/.venv/Scripts/python.exe evaluation/strategy_pool_replay.py --out-dir ../output/agent_handoffs/WP1-E2C-R1/codex_replay`；退出码：`0`。
- 输入：已准入 49 股/6 板块、E0 baostock qfq 快照、官方 v2 `decision+2 open → decision+21 close` 成熟标签；12 个不重叠窗口覆盖 `2025-01-14 → 2025-12-11`。
- 产物：`output/agent_handoffs/WP1-E2C-R1/codex_replay/strategy_pool_replay.json`；独立复现 SHA-256 `b45fbaebb606f23af41734e133130920b2afb57834f2262297411db96f40e9f5`，逐窗口和整包 hash 可重算且篡改负测通过。
- 结果：`production_six_factor=OK_BASELINE`；`t2_comparator=QUALIFIED_RESEARCH_ONLY`，中位收益差 `+0.7448%`、utility win rate `91.67%`、最近四窗 `4/4`，回撤门通过；短/中/长趋势均因 `<8` 个可比窗口 `DOES_NOT_QUALIFY_INSUFFICIENT_WINDOWS`；`similar_market_blend=BENCHMARK_UNAVAILABLE`。
- 独立门禁：31 项聚焦测试、Ruff、py_compile、scope-check、`git diff --check` 和 artifact 重算均 exit `0`；完整裁决见 `output/agent_handoffs/WP1-E2C-R1/review.json`。
- 边界：E0 归档没有 volume 列，production/T2 的 volume 因子在本回放中为中性；未运行 direct/formal/RPC/E2E，不提升为 `PATH_PASSED` 或 `BUSINESS_PASSED`，不构成 T2 生产晋级。

## 当前冻结状态

- 生产策略：`production_six_factor`。
- T2：`RESEARCH_ONLY`。
- WP1-C：三个候选全部 `DOES_NOT_QUALIFY`，没有第四候选。
- Agent overlay：关闭。
- 报告：`FINANCIAL_PARTIAL`。
- SubmissionContract：`PROVISIONAL / BLOCKED`。
- E2A/E2B：`LOCAL_IMPLEMENTED / RESEARCH_ONLY`；六槽位注册与相似市场核心已验收，真实 benchmark 缺失时分支失败关闭
- E2C：`LOCAL_IMPLEMENTED / RESEARCH_ONLY / CLOSED`；T2 仅获得 E3 研究候选资格，production 不变
- E3：`LOCAL_IMPLEMENTED / RESEARCH_ONLY / CLOSED`；有界融合已验收，真实模型、production 和正式路径均未启用
- E4：`READY_FOR_LOCATION`；E3 前置阻塞已解除，但完整动态选择器回放尚未开始
- 开发协作：Codex/Claude 两方；金融运行时仍为三角色和 8 RPC

## 仍缺少什么

### 外部数据/授权

1. fundamental 需要 structured historical line items、taxonomy/version、期间、
   合并/审计/单位币种、publication/observed 和 correction lineage。
2. news-risk 需独立来源授权、事件/修订/空结果和 49/49 状态契约。

### 主办方

- 书面确认 Excel 49 家与口述 50 家的裁决；
- 书面确认权重和为 1 是否包含现金；
- 书面确认报告完整性对初赛筛选/评分的作用。

## 下一阶段开始条件

1. 为 WP1-E4 建立新的只读定位契约；完成定位、范围冻结、实现和独立验收后，才形成完整动态选择器回放证据。
2. fundamental/news-risk 只有授权 source 到位后才恢复 Provider 工作。
3. 主办方答复归档并生成 contract version/hash 后才开始 WP2 正式包。
4. 最终提交前在最终 commit、最终数据和 Windows 环境 fresh 重跑 direct/
   formal/E2E。

## 仓库保留边界

- Git 跟踪源码、当前文档、官方材料、可复现实验、任务契约和版本 history。
- `output/`、交付包、缓存、媒体和 `tmp/` 不提交；本轮未删除或改写用户 `tmp/`。
- v2.13/v2.14 历史保持原样；v2.15 讨论已归档 `history/v2.15_2026-08-07_discussion.md`。
- commit/push 与版本边界由 Codex 按用户持续授权、门禁证据和任务契约自主裁定并记录；tag 和外部发布仍需单独授权。
