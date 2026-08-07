# 当前验证状态

> 本文件是项目可运行状态的唯一事实源。计划、README、Agent 身份和历史只能
> 引用这里，不得把本地单测、旧 session 或设计目标改写成新的业务通过。

## 结论（2026-08-07）

| 对象 | 证据等级 | 当前结论 |
|---|---|---|
| v2.15 Windows formal | BUSINESS_PASSED | commit `1f84b01` 的 `2025-01-02 → 2025-05-21` 三次 8/8（115235/122418/122852），REAL_EXIT=0，12 tool calls，0 errors，三金融角色无越权；P95 105s / RSS 575MB / token -91% |
| v2.15 E1P 数据能力 | BUSINESS_PASSED | 五项全部 AVAILABLE：calendar + corporate_action（baostock 347 行）+ factor_snapshot（baostock 77,541 行 qfq）+ forward_label（604 决策日）+ sector（赛题 6 板块） |
| v2.14 量化 direct | BUSINESS_PASSED（历史锚） | commit `89322cd`，收益 `+0.7476%`、最大回撤 `1.6424%` |
| v2.14 JiuwenSwarm formal | BUSINESS_PASSED（历史锚） | session `multi-agent-validation-20260805-100147` 8/8、12 tool calls、0 error |
| WP0-A 文档契约 | LOCAL_IMPLEMENTED | README 动态区块由绑定产物生成；runtime Skill 镜像恢复并防漂移；无产物时保持 `NOT_GENERATED`，不能从文档提升事实 |
| WP0-B Agent 决策契约 | LOCAL_IMPLEMENTED / OVERLAY_DISABLED | PIT `AgentProposal`、不可变 `DecisionTrace`、共享 server-owned selection 和 A0/A1/A2 诊断已实现；生产 overlay 仍关闭，没有样本外晋级证据 |
| WP0-C 公告 replay | LOCAL_IMPLEMENTED | hash-verified archive 离线重放；direct/formal 同一投影 |
| WP1-B 嵌套评测 | PATH_PASSED（v2.14） | embargo/首日开盘/20 日/末日收盘/内外层隔离/Bootstrap 已实现并固化 |
| WP1-C challengers | PATH_PASSED / DOES_NOT_QUALIFY | 三个候选均未晋级；production 仍为 `production_six_factor` |
| WP1-D 全包 | BUSINESS_PASSED | 8 阶段状态机/20 次 replay/资源门/teardown/failure-guard 全部通过 Windows 三次 formal |
| WP1-E0/E1 | LOCAL_IMPLEMENTED / RESEARCH_ONLY | 12 项 Factor Registry、稳定 implementation hash 和成熟标签因子研究策略已实现；没有真实完整 trust roots，不产生当前因子方向/权重，不接 production |
| WP1-E1P Provider 准入 | BUSINESS_PASSED | 五项全部 AVAILABLE：E0 snapshot（baostock qfq）/ corporate action（baostock）/ forward label（604 日）/ sector（静态 6 板块）/ calendar（原有） |
| WP1-E2 策略池 | 基线冻结 | 6 槽位已定义，Claude 待实现 |
| PIT fundamental/news-risk | DATA_BLOCKED | fundamental grade 已失败关闭 generic fact；仍缺合法 structured historical source、版本/更正链和跨设备交付授权。news-risk 也未建立独立准入 |
| 完整金融报告 | FINANCIAL_PARTIAL | 公告和技术证据可审计，但 fundamental/news-risk/宏观/另类数据不足，不能写 `FULL_REPORT_PASSED` |
| 正式提交契约 | PROVISIONAL / BLOCKED | 49/50、现金权重和报告作用仍需主办方可归档书面答复；不得生成或命名正式提交包 |
| 开发协作治理 | LOCAL_IMPLEMENTED | Codex/Claude 两方平等协作；AGENTS.md 已记录 Windows 跨平台 5 陷阱 |

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

## 当前冻结状态

- 生产策略：`production_six_factor`。
- T2：`RESEARCH_ONLY`。
- WP1-C：三个候选全部 `DOES_NOT_QUALIFY`，没有第四候选。
- Agent overlay：关闭。
- 报告：`FINANCIAL_PARTIAL`。
- SubmissionContract：`PROVISIONAL / BLOCKED`。
- E2：基线冻结，Claude 待实现（6 槽位策略池）
- E3/E4：未开始，依赖 E2 完成
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

1. WP1-E2 实现完成后按 E2 → E3 → E4 分任务开发。
2. fundamental/news-risk 只有授权 source 到位后才恢复 Provider 工作。
3. 主办方答复归档并生成 contract version/hash 后才开始 WP2 正式包。
4. 最终提交前在最终 commit、最终数据和 Windows 环境 fresh 重跑 direct/
   formal/E2E。

## 仓库保留边界

- Git 跟踪源码、当前文档、官方材料、可复现实验、任务契约和版本 history。
- `output/`、交付包、缓存、媒体和 `tmp/` 不提交；本轮未删除或改写用户 `tmp/`。
- v2.13/v2.14 历史保持原样；v2.15 讨论已归档 `history/v2.15_2026-08-07_discussion.md`。
- 未经用户明确授权不 push、tag。
