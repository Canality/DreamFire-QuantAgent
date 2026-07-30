# 当前协作讨论

> 这里只保留当前交接。历史讨论见 Git 历史和 `discussion-archive.md`；运行事实只认根目录 `VALIDATION.md`。

## [Codex → Missed / Goone] 2026-07-30：清理、修复与最终验收

### 判断

行情量化、正式多 Agent 和行情型报告候选包已经达到 `BUSINESS_PASSED`；完整金融分析作品仍为 `PARTIAL`，正式提交契约仍为 `PROVISIONAL`。

### 本轮完成

1. 修复 SnapshotWriter 与五源逐 ticker 来源账本，direct/formal 共用同一实现。
2. 候选包只保留当前一套 prices/volumes/manifest；EvidenceRef URL 和 hash 指向同一真实 manifest。
3. 验收器从 contract 读取公司/板块数量，不再在业务校验中硬编码 49。
4. contract 配置改为相对官方 Excel 路径，仓库迁移后仍可校验。
5. 正式路径新增角色级真实资源日志：token、耗时、CPU、峰值工作集；测不到的最大并发保持 null。
6. E2E audit 新增 49 份报告集合、资源文件、三角色 token、快照、hash、ledger、角色边界检查。
7. 新增 150 秒无有效量化阶段进展的失败关闭边界。
8. 删除旧提交包、旧候选、旧运行日志、媒体中间件、smoke/dry-run、临时脚本和缓存。
9. 重写 README、VALIDATION、CLAUDE、AGENTS 与赛题资料索引，消除旧 session 和过期“已修复”状态。
10. 真实复跑发现 Agent 会在正确配仓后自行删股并二次配仓；现已把 select→allocate→backtest→report 改为服务端缓存单向传递，LLM 参数不能覆盖前序结果。
11. 单测曾把模拟快照写入真实 `output/`；现已隔离到 `tmp_path` 并增加“不污染项目输出”的回归断言。
12. 8/8 后 Team stream 不退出时，Runner 现在显式停止 session runtime，再关闭 stream，避免完成后悬挂。

### 最终证据

- 141 项量化测试通过；目标 ruff 通过。
- direct：49/49、6/6、15 只、现金 5.06%，退出码 0。
- formal：session `multi-agent-validation-20260730-164030`，79.8 秒，8/8，退出码 0。
- Agent 事件：Coordinator/Bull/Bear = 588/454/303；Bull/Bear 各 1 次专属 RPC，无越权。
- 候选包：49 份报告；Quality PASSED；唯一三文件行情快照。
- 资源：1,204,831 input、9,932 output、1,045,760 cache tokens；峰值工作集 506.00 MB。
- 独立 E2E audit 退出码 0。

### 不得外推

- `+3.2468% / 2.8762%` 是已知历史 20 日路径演示，不是未来比赛预测。
- 49 份文件齐全不等于基本面/公告/新闻内容已完成。
- T2 只在 21 个开发窗口领先，仍不能替换生产六因子。
- 资源基准未公布，不能把当前 token 折算成官方资源分。
- 官方材料仍有 49/50、现金、报告作用三项冲突，不能发布正式包。

## 下一轮建议

### P0：资源与稳定性

- 对 Coordinator 上下文做阶段摘要，只保留结构化因子/组合结果。
- Bull/Bear 只接收各自必要的横截面摘要，禁止重复全量上下文。
- 统计每阶段/角色 token，设预注册降本目标；8/8 成功率不能下降。
- 对“4/8 后等待成员”的失败轨迹做回放测试，确保 150 秒内 fail-closed。

### P1：第一个真实非行情 Provider

- 优先交易所公告，不先做广泛新闻爬虫。
- 每条证据必须有原始 URL、发布时间、Agent 可用时间、抓取时间、正文 hash 和本地归档。
- 决策日前不可见的公告不得进入报告或组合。
- direct/formal 双路径必须共用 Provider 与质量门。

### P2：策略

- 冻结生产六因子。
- T2 只做真正未来/封存窗口验证；预注册收益、回撤和尾部护栏。
- Agent 只能在已注册策略集合中路由，不能临场发明权重。

### P3：官方澄清

向主办方书面确认：

1. 公司数量以 Excel 49 家还是口述 50 家为准？
2. 权重和为 1 是否包含现金？
3. 报告完整性是否影响初赛筛选，资源分项文字中的 10/15 与 5/10 矛盾如何解释？
