# 当前协作交接

> 当前运行事实只认根目录 `VALIDATION.md`；路线和验收只认
> `DEVELOPMENT_PLAN.md`；已关闭版本见 [history/README.md](../history/README.md)。
> 本文件只保留一个当前交接，不保存逐次搜索、完整日志或旧身份讨论。

## [Codex → Windows Codex / Claude] 2026-08-06：v2.15 Mac 候选交接复验

### 判断

- v2.15 实现边界为
  `89322cdff88ccd3172055fe870efbf5d45676ff6..f205967b11065b36fc1ef6d7898c2cf79dea0872`。
  Mac 的本地代码门和独立审查已完成，但本轮没有 fresh direct/formal/model/network
  运行；v2.14 `89322cd` 继续作为最后一次 BUSINESS 运行锚。
- 开发协作现精确为两方：Windows Codex 负责计划、范围、独立审查和验收；
  Claude 负责定位、实现、测试和 implementation 工件。双方平等，可相互反证，
  同一争议最多各两次证据交换，随后必须收敛或升级用户。
- production 仍为 `production_six_factor`，T2 仍为 `RESEARCH_ONLY`，WP1-C
  三个候选仍为 `DOES_NOT_QUALIFY`；报告与正式提交状态未提升。
- 未 push、tag 或修改 Windows 主工作区；Mac 的 `tmp/` 和全部历史证据未触碰。

### 证据

本轮需要按父子依赖顺序复验的提交：

1. `4a3d812` — 建立 v2.13/v2.14 append-only history；
2. `43559a4` — 预注册 WP1-E 动态研究路线和失败关闭门；
3. `9c16155` — 实现 12 项 Factor Registry；
4. `66e711c` — 实现成熟 20 日标签的因子研究快照；
5. `6f54a70` — 建立 evidence Provider 准入总门；
6. `e690455` — 准入 official calendar；
7. `5fb0ec6` — 记录 PIT adjusted OHLC/ledger 数据阻塞；
8. `dd38f34` — 绑定比赛固定分组及其非 PIT 边界；
9. `3586ce0` — 加入有证据的冻结契约质疑规则；
10. `775666f` — 记录 fundamental source admission 阻塞；
11. `8d00f54` — 收紧 fundamental grade 失败关闭；
12. `5391cbb` — 稳定 factor implementation hash；
13. `921fe88` — WP0-A 机器生成文档契约；
14. `eb81ce5` — WP0-B PIT Agent 决策、共享 selection 和 A0/A1/A2 诊断；
15. `0a32068` — WP0-C 公告 receipt/replay/direct-formal parity；
16. `287f5e8` — WP1-D 八阶段状态机和 20-run offline replay；
17. `cf6017d` — WP1-D formal 资源测量和三 run 聚合器；
18. `2a04f49` — WP1-D 正常 teardown 和 watchdog；
19. `44acb51` — WP1-D 同名连续失败 guard；
20. `6b6482e` — accepted WP1-B review 原字节固化，量化全量
    `610 passed, 1 skipped`；
21. `f205967` — Codex/Claude 两方身份、计划和工作流；删除 8 个旧启动器。

此前已复制到 Windows：

- `D:\work\incoming\WP1D-RESOURCE-BENCH-0806`
- `D:\work\incoming\WP1D-SESSION-TEARDOWN-0806`

本次收口还将提供以下 task-scoped 目录；以各目录 `BASE_COMMIT.txt`、
`HEAD_COMMIT.txt`、bundle、patch、handoff 和 `SHA256SUMS.txt` 为准：

- `D:\work\incoming\WP1D-FAILURE-GUARD-0806`
- `D:\work\incoming\WP1B-EVIDENCE-PIN-0806`
- `D:\work\incoming\TWO-AGENT-GOVERNANCE-0806`
- `D:\work\incoming\CURRENT-HANDOFF-0806`
- `D:\work\incoming\TRACK2-V215-HANDOFF-0806`（完整
  `89322cd..CURRENT-HANDOFF HEAD` 汇总 bundle/patch；按上述有序链应用或直接用
  汇总包，二选一，不可重复应用）

每个代码任务的独立 review 都是 `ACCEPT`、开放 P0-P3 为 0。治理任务在最终
接受前关闭 3 个 P1、2 个 P2；它只改变开发治理，不改变金融运行时的
Coordinator/Alpha/Risk & Evidence 三角色和 8 RPC。

### 建议动作

1. **Windows Codex**：先核对每包 SHA、BASE/HEAD、commit ancestry、白名单和
   review；不要把 bundle 存在等同于验收，不要在脏主工作区直接覆盖。
2. **Claude**：只在 Windows Codex 接受的独立任务分支应用一个包，运行该包
   focused tests、Ruff、scope/diff；遇到差异提交证据挑战，不静默扩大范围。
3. **Windows Codex**：在完整链上执行 fresh direct/formal/E2E；重点复验服务端
   selection、公告 replay projection、候选绑定、teardown 和 failure guard。
4. **Claude + Windows Codex**：同一不可变 snapshot 完成 3 次 formal，使用
   resource aggregator 验证不同 summary hash、相同 market/snapshot/manifest/
   ToolCard identity、P95、RSS、并发和 token 门；确认健康进程正常返回。
5. 若 Windows 需要修正，只生成
   `D:\work\outgoing\<TASK-ID>` 的 task-scoped 返回补丁；Mac 不与之同时修改。

当前不能由代码继续完成的 blocker：

- E1P 缺历史 sector、PIT corporate-action/adjusted OHLC、逐 ticker ledger、
  成熟 label 和可信 E0 snapshot；E2/E3/E4 不得开始。
- Fundamental/news-risk 缺合法、可归档、可跨设备交付的数据源；报告保持
  `FINANCIAL_PARTIAL`。
- 主办方仍需书面确认 49/50、现金口径和报告作用；SubmissionContract 保持
  `PROVISIONAL / BLOCKED`。

### 需要回复

- Windows Codex 请按任务分别回传 `ACCEPT / MODIFY / BLOCKED`、实际命令、
  退出码和产物 hash；不要只回复“整体看起来没问题”。
- 若 Windows 已有同范围未交回修改，请在应用对应包前指出，避免双端覆盖。
