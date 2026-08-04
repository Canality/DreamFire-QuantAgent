# Dream Fire：基于 JiuwenSwarm 的 Agent 金融分析系统

华为 openJiuwen Track 2 参赛项目。系统在官方 49 家上市公司范围内完成行情获取、多因子分析、Alpha/Risk & Evidence 多 Agent 审查、选股、配仓、20 日回测和逐公司报告生成。

> 当前状态：共享行情、公告 PIT、量化 direct 与 fixed `quant_team` formal 均已真实通过；最新 direct 为 49/49 行情、1,470 条公告和 49/49 披露，最新 formal 为严格 8/8、三角色真实参与、无角色越权，绑定两者的独立 E2E audit 退出 0。fixed quant 运行时已收敛到角色自有 Quant RPC 与 `send_message`，但报告仍为 `FINANCIAL_PARTIAL`，正式提交契约仍受官方口径冲突阻断。最新数量、证据、命令、退出码和已知问题只看 [VALIDATION.md](VALIDATION.md)；下一阶段架构与验收路线见 [DEVELOPMENT_PLAN.md](DEVELOPMENT_PLAN.md)。

## 项目定位

这不是“让 LLM 看一堆价格后随口选股”。数值计算、时序切分、仓位约束和证据归档由确定性 Python 服务完成；Agent 负责分工、观点生成、风险对抗和决策编排。

```
官方49家公司
    │
    ▼
Sina → Tencent → akshare → baostock → yfinance
    │ 逐只补缺；不足49家失败关闭
    ▼
不可变行情快照 + 来源账本 + SHA-256
    │
    ├─ Coordinator：因子、选股、配仓、回测、报告
    ├─ Alpha Analyst：趋势、量价和候选发现
    └─ Risk & Evidence Analyst：波动、回撤和证据冲突
    │
    ▼
15只组合 + 49份公司报告 + 证据/资源日志
```

## 当前可验证能力

| 能力 | 当前状态 |
|---|---|
| 官方股票池契约 | Excel hash 校验；49 家、6 板块；数量不在业务入口硬编码 |
| 行情数据 | 五源逐只补缺、逐 ticker 来源、49/49 fail-closed |
| 时序安全 | 决策日前训练、首日开盘固定股数、20 日前向持有 |
| 仓位安全 | 选股输入与配仓输入一致；单股 ≤10%、板块 ≤25%、现金 ≥5% |
| 多 Agent | 正式入口精确选择 Coordinator/Alpha/Risk & Evidence 三角色；最新 formal 严格 8/8，每阶段恰好执行 1 次，角色专属 RPC 1/1 且无越权 |
| 报告 | direct/formal 均到达报告路径；49 份公司报告、组合报告、行情快照和 49/49 公告披露通过独立 E2E audit，整体仍为 `FINANCIAL_PARTIAL` |
| 资源 | 正式路径按角色记录 token、耗时和 CPU；最新峰值工作集与最大并发明确标为缺测，不伪填 0 |
| 失败策略 | 数据不全、报告缺失、hash 错误、角色越权和重复失败均关闭 |

正式路径的具体 session、token、耗时、收益和回撤数字以 `VALIDATION.md` 绑定的 timestamped `output/` 产物为准。`output/validation_summary.json` 仍是可再生的动态摘要入口，但不是项目事实源；只有它绑定当前产物且独立 E2E audit 退出 0，才能写 `BUSINESS_PASSED`。8/8 本身只证明量化 Agent 路径可运行。这只是路径验收区间，不是比赛成绩预测。

## 策略状态

- 官方评测期已确认为 2026-08-25 至 09-21，共 20 个交易日；8月25日开盘买入、9月21日收盘卖出，期间固定持股不调仓。提交截止为8月23日，因此8月24日行情不可用于决策。
- 生产策略仍为六因子模型；历史 v2.0-v2.7 的 76.9-81.7 本地分数受前视偏差或回测错误污染，全部作废。
- Walk-Forward IC 的原实验有 11 个开发窗口；Phase A/B 组合回测有 21 个窗口，两者不能混写。
- Phase B T2 在旧开发口径相对生产配对收益差约 +0.91pp、效用胜率 15/21；该实验未模拟提交与买入之间的8月24式单交易日 embargo，只能作为研究线索。最新 challenger 状态和晋级证据只看 `VALIDATION.md`。
- production、T2 和统一基线必须按“决策后隔一交易日、再开盘买入并持有20交易日”重跑；完成前不切换生产。
- 本地代理评分只用于比较方案；官方标准化公式和资源基准未公布，不能给出“官方预估总分”。

## 报告与 Agent 的真实边界

当前报告体系解决了“可生成、可追溯、可验收”：

- 49 家公司文件集合必须与官方契约完全一致；
- 所有可用技术事实必须引用真实 EvidenceRef；
- 候选包同时携带 prices、volumes、manifest 和可重算 hash；
- Alpha/Risk & Evidence 观点来自角色专属 RPC，不由 Coordinator 冒充；
- 资源日志来自 openJiuwen 运行事件，不用估算值填 0。

公告 Provider 的 point-in-time 分页、终止诊断和归档已通过真实 49/49 smoke、direct 与 formal；最新候选含 1,470 条公告事实。基本面、新闻、宏观与另类数据尚未形成当前可审计覆盖，因此仍不是 `FULL_REPORT_PASSED` 最终作品。

## 对比赛的竞争力

优势：

1. **框架使用是真实的**：Extension、Team Skill、角色工具权限、Rails/质量门和 JiuwenSwarm streaming 路径都参与业务，不是独立脚本套壳。
2. **可复现性强**：官方股票池、时序、仓位、报告集合、行情来源和 hash 都是机器可检查的契约。
3. **风险控制完整**：单股、板块、现金和回测口径均在最终输出再次断言。
4. **Agent 协作可证明**：能回答“哪个角色做了什么、调用了什么、消耗了多少资源”。
5. **研究纪律较好**：旧污染分数已撤销，开发候选与生产策略分离，避免靠一次漂亮回测自我欺骗。

短板：

1. 最新 formal 已收敛为 95,569 input、6,510 output、61,952 cache tokens、12 次工具调用和 48 秒；相较历史通用团队路径显著下降，但官方资源基准未公布，仍不能断言资源分达标。
2. alpha 尚未得到样本外证明；工程可信不等于收益领先。
3. 报告仍偏技术面，完整金融分析深度不足。
4. fixed quant capability ceiling 依赖锁定的 openJiuwen `0.1.15.post3` 接口与工具面；依赖升级会故意失败关闭，必须重新审查和双路径验收。
5. 赛题规则仍有 49/50、现金和报告权重冲突，正式契约保持 PROVISIONAL。

## 快速复现

```powershell
cd jiuwenswarm

# 单元测试
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
.\.venv\Scripts\python.exe -m pytest -o addopts='' tests/unit_tests/quant -q

# 研发旁路
.\.venv\Scripts\python.exe scripts/run_quant_pipeline.py

# JiuwenSwarm 正式多 Agent 路径
.\.venv\Scripts\python.exe -u evaluation/run_multi_agent.py --start-date 2025-01-02 --end-date 2025-05-21
```

完整端到端审计命令见 [VALIDATION.md](VALIDATION.md)。

## 多模型开发协作

Qwen、DeepSeek 和 Codex 不再通过一段超长聊天串行接力。每个任务使用 Git 管理的任务契约与本机最小交接工件；Qwen 负责低成本定位和受限小改，DeepSeek 只在中风险或本地实现失败时读取最小上下文，Codex 负责规划、裁决与最终验收。

```powershell
# 创建任务、查看任务状态
python scripts/agent_task.py new TASK-ID --title "任务标题" --risk LOW
python scripts/agent_task.py status TASK-ID

# 自动按任务风险选择模型并启动独立角色会话
.\scripts\agent-role.cmd TASK-ID scout
.\scripts\agent-role.cmd TASK-ID builder
.\scripts\agent-role.cmd TASK-ID critic

# 在两个终端中独立启动；无需切换 CC Switch 或重启另一终端
.\scripts\claude-qwen.cmd
.\scripts\claude-deepseek.cmd
```

完整状态机、文件白名单、token 预算和升级规则见 [AGENT_WORKFLOW.md](AGENT_WORKFLOW.md)。密钥和模型 Provider 配置位于用户目录的独立 profile，不进入仓库。

## 目录

```
Track_2/
├── README.md
├── VALIDATION.md                    # 唯一运行事实源
├── DEVELOPMENT_PLAN.md              # Git 管理的长期开发计划与验收契约
├── AGENT_WORKFLOW.md                 # 多模型任务状态机、风险路由与交接规范
├── AGENTS.md / CLAUDE.md            # Agent 开发与验收约束
├── coordination/                    # Git 管理的当前任务契约和模板
├── scripts/agent_task.py            # 任务工件、基线和越界检查 CLI
├── scripts/agent_role.py            # 按风险选择模型并启动 Scout/Builder/Critic
├── scripts/claude-*.cmd             # 独立 Qwen / DeepSeek Claude Code 启动入口
├── .agents/skills/local-code-scout/ # 本地只读代码定位 Skill
├── .agents/skills/bounded-code-implementer/ # 白名单受限实现 Skill
├── .agents/skills/diff-contract-reviewer/   # 新会话差异审查 Skill
├── .agents/skills/verify-quant-e2e/ # 发布前双路径验收 Skill
├── .claude/discussion.md            # 当前协作交接
├── jiuwenswarm/
│   ├── evaluation/                  # 因果评测、策略实验、正式 Agent 验收
│   ├── jiuwenswarm/quant/           # 因子、配仓、回测、报告契约与证据
│   ├── jiuwenswarm/extensions/quant-finance/
│   ├── scripts/run_quant_pipeline.py
│   └── tests/unit_tests/quant/
├── 策略实验/                         # 历史研究证据，不是当前状态源
├── 赛题文档/                         # 官方材料与答疑转录
└── output/                           # 本机验收产物，Git 忽略
```
