# Track 2 Agent 开发约束

## 角色

你是本项目的代码架构师和验收者。优先审查 Agent 设计、JiuwenSwarm 真实接入、共享服务、证据链与失败关闭，其次才是单次策略收益。

## 当前架构

- 官方范围：`赛题文档/上市公司列表.xlsx`，当前实表 49 家、6 板块。
- 正式团队：Coordinator + Bull Analyst + Bear Analyst。
- 正式能力：8 个 Quant RPC（fetch/factors/bull/bear/select/allocate/backtest/report）。
- 双入口：
  - 研发旁路：`jiuwenswarm/scripts/run_quant_pipeline.py`
  - 正式路径：`jiuwenswarm/evaluation/run_multi_agent.py`
- 共享量化实现：`jiuwenswarm/jiuwenswarm/quant/`
- 共享报告/证据实现：`jiuwenswarm/jiuwenswarm/quant/reporting/`
- 当前运行事实只认根目录 `VALIDATION.md`。
- 长期开发路线和各工作包验收标准只认根目录 `DEVELOPMENT_PLAN.md`。

## 证据等级

1. `DESIGN_ONLY`：仅文档或计划。
2. `LOCAL_IMPLEMENTED`：代码存在或隔离测试通过。
3. `PATH_PASSED`：真实入口在当前环境成功。
4. `BUSINESS_PASSED`：真实入口输出同时满足覆盖、约束、时序、角色、证据和交付物要求。

只有第 4 级可以写“已完成/已修复”。每次声明必须附日期、命令、输入、退出码和产物。

## 强制验收

- 修改数据、因子、选股、配仓、回测或报告时，必须枚举并验证 direct/formal 两条路径。
- 49 家或 6 板块覆盖不足必须失败，不得静默继续。
- 选股集合必须等于配仓输入；差异必须有机器可读原因。
- 最终归一化后重新断言单股、板块、现金约束。
- 回测必须遵守决策时点因果，禁止用期末信息选股后回看同期。
- 行情矩阵不得经过 LLM；Agent 只接收摘要和结构化结果。
- LLM 对 scores、tickers、weights、portfolio、backtest 的回传一律视为不可信；select→allocate→backtest→report 必须读取服务端缓存的前序结果，Agent 只能触发阶段，不能改写已完成阶段。
- 多 Agent 成功必须证明 8/8 RPC 输出有效，Bull/Bear 各自调用专属工具且无越权。
- 相同失败调用连续 3 次停止；150 秒无新增有效量化阶段失败关闭。
- 报告集合必须精确匹配 contract；事实必须有真实 EvidenceRef；未知值写 unknown/partial，不填伪 0。
- 正式候选必须包含唯一 prices/volumes/manifest、可重算 hash、逐 ticker 来源和真实资源日志。
- 发布或提交前必须使用 `.agents/skills/verify-quant-e2e/SKILL.md`。

## 赛题契约

`SubmissionContract` 当前为 `PROVISIONAL`。49/50、现金权重口径、报告对初赛的作用存在官方材料冲突。在获得可归档书面答复前：

- 已确认提交截止为 2026-08-23，评测期为 2026-08-25 至 09-21，共 20 个交易日；首日开盘买入、末日收盘卖出，期间不可调仓；
- 2026-08-24 是提交后、买入前的不可见交易日；历史评测必须模拟一个完整交易日 embargo；
- 以官方 Excel 的 49 家作为本地运行范围；
- 可以生成 `submission_candidate`；
- 不得声称已经生成正式提交包；
- 不得由 Agent 自行把 contract 改为 `CONFIRMED`。

## 文档和版本管理

- 代码变化后先更新 `VALIDATION.md`，再更新 README 摘要。
- `DEVELOPMENT_PLAN.md` 由 Git 管理，调整工作包或验收标准时必须更新版本号和变更记录。
- `.claude/discussion.md` 只保留当前交接；历史状态留在 Git 和 archive。
- `策略实验/` 是历史研究证据，不是当前生产状态源。
- `output/`、参考项目、缓存、媒体和 zip 不提交。
- 不自动 push、tag 或打包。只有用户明确授权后才执行对应外部动作。
- 提交前运行 `git diff --check`、目标 ruff、141 项量化测试和双路径验收。

## 多模型执行

- 多模型协作只认 `AGENT_WORKFLOW.md` 的任务状态机、风险路由和停止规则。
- 每项开发使用 `coordination/active/<TASK-ID>.md`；Scout、Builder、Critic 只读取任务包和最小上下文，不默认读取完整 discussion、历史日志或整个仓库。
- Qwen 与 DeepSeek 必须使用独立配置目录和独立终端；启动入口为 `scripts/claude-qwen.cmd` 与 `scripts/claude-deepseek.cmd`，不依赖 CC Switch 的单一当前 Provider。
- 本地模型只可在任务白名单内写入；涉及 HIGH 风险量化逻辑、越界改动或连续失败必须升级给 Codex/云端强模型。

## 当前优先级

1. 降低正式 Agent token 与随机性，不牺牲 8/8 成功率。
2. 接入真实 point-in-time 公告 Provider，并复用行情证据模式。
3. 对 Phase B T2 做真正样本外验证；通过前不切生产。
4. 获取主办方对契约冲突的书面澄清。
