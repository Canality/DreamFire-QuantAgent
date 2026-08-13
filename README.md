# Dream Fire：基于 JiuwenSwarm 的 Agent 金融分析系统

华为 openJiuwen Track 2 参赛项目。系统在官方 49 家上市公司范围内完成行情获取、多因子分析、Alpha/Risk & Evidence 多 Agent 审查、选股、配仓、20 日回测和逐公司报告生成。

> 当前代码候选为 **v2.16**：Windows formal 与 E1P 数据能力已通过当前验收，开发协作已收敛为 Codex / Claude 两方；BRIDGE-OPS-5 双 CLI 桥接修复已验收；v2.15 Windows formal 继续作为历史业务锚，生产策略、报告等级和正式提交门仍按当前契约执行。任何 direct/formal 的覆盖量、阶段完成度、资源消耗和独立审计结果都不得在说明文字中手工维护，只能由下方机器区块和 [VALIDATION.md](VALIDATION.md) 表达；下一阶段路线见 [DEVELOPMENT_PLAN.md](DEVELOPMENT_PLAN.md)。

<!-- BEGIN GENERATED VALIDATION SUMMARY -->
> 本区块只能由 `generate_validation_summary.py --readme update` 根据绑定的运行与独立审计产物更新。

| 动态字段 | 当前值 |
|---|---|
| `direct_status` | `NOT_GENERATED` |
| `formal_status` | `NOT_GENERATED` |
| `report_status` | `NOT_GENERATED` |
| `formal_session` | `NOT_GENERATED` |
| `formal_input_tokens` | `NOT_GENERATED` |
| `audit_passed` | `NOT_GENERATED` |
<!-- END GENERATED VALIDATION SUMMARY -->

版本更迭、失败探索、旧数值及其适用限制统一归档在
[history/README.md](history/README.md)。新功能开发不需要默认加载历史目录。

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
| 行情数据 | 五源逐只补缺、逐 ticker 来源；未覆盖完整官方股票池时失败关闭 |
| 时序安全 | 决策日前训练、首日开盘固定股数、20 日前向持有 |
| 仓位安全 | 选股输入与配仓输入一致；单股 ≤10%、板块 ≤25%、现金 ≥5% |
| 多 Agent | 正式入口只允许 Coordinator/Alpha/Risk & Evidence 三角色；八个业务阶段、角色专属 RPC 和越权检查由机器验收 |
| 报告 | direct/formal 共享报告契约；每家公司报告、组合报告、行情快照和公告披露均须通过独立 E2E audit，等级由证据覆盖决定 |
| 资源 | 正式路径按角色记录 token、耗时和 CPU；缺测字段必须显式标为未知，不伪填 0 |
| 失败策略 | 数据不全、报告缺失、hash 错误、角色越权和重复失败均关闭 |

正式路径的具体 session、token、耗时、收益和回撤数字以 `VALIDATION.md` 绑定的 timestamped `output/` 产物为准。`output/validation_summary.json` 仍是可再生的动态摘要入口，但不是项目事实源；只有它绑定当前产物且独立 E2E audit 成功，才能写 `BUSINESS_PASSED`。业务阶段完整本身只证明量化 Agent 路径可运行，不是比赛成绩预测。

## 策略状态

- 官方评测期已确认为 2026-08-25 至 09-21，共 20 个交易日；8月25日开盘买入、9月21日收盘卖出，期间固定持股不调仓。提交截止为8月23日，因此8月24日行情不可用于决策。
- 生产策略仍为六因子模型；历史 v2.0-v2.7 的 76.9-81.7 本地分数受前视偏差或回测错误污染，全部作废。
- Walk-Forward IC 的原实验有 11 个开发窗口；Phase A/B 组合回测有 21 个窗口，两者不能混写。
- WP1-B 已建立“决策后隔一交易日、再开盘买入并持有 20 交易日”的嵌套评测与晋级边界；T2 因证据条件不完整保持 `RESEARCH_ONLY`，没有切换 production。
- WP1-C 预注册的趋势一致性、板块领导力和非对称尾部风险三个 challenger 均未通过内层/构造门；按停止规则不再调权或增加第四候选，生产策略继续为 `production_six_factor`。
- 本地代理评分只用于比较方案；官方标准化公式和资源基准未公布，不能给出“官方预估总分”。

## 报告与 Agent 的真实边界

当前报告体系解决了“可生成、可追溯、可验收”：

- 49 家公司文件集合必须与官方契约完全一致；
- 所有可用技术事实必须引用真实 EvidenceRef；
- 候选包同时携带 prices、volumes、manifest 和可重算 hash；
- Alpha/Risk & Evidence 观点来自角色专属 RPC，不由 Coordinator 冒充；
- 资源日志来自 openJiuwen 运行事件，不用估算值填 0。

公告 Provider 实现 point-in-time 分页、终止诊断和不可变归档；实际覆盖量和候选事实数只看机器摘要与 `VALIDATION.md`。基本面、新闻、宏观与另类数据必须分别通过证据准入，不能由公告或技术风险字段替代。

## 对比赛的竞争力

优势：

1. **框架使用是真实的**：Extension、Team Skill、角色工具权限、Rails/质量门和 JiuwenSwarm streaming 路径都参与业务，不是独立脚本套壳。
2. **可复现性强**：官方股票池、时序、仓位、报告集合、行情来源和 hash 都是机器可检查的契约。
3. **风险控制完整**：单股、板块、现金和回测口径均在最终输出再次断言。
4. **Agent 协作可证明**：能回答“哪个角色做了什么、调用了什么、消耗了多少资源”。
5. **研究纪律较好**：旧污染分数已撤销，开发候选与生产策略分离，避免靠一次漂亮回测自我欺骗。

短板：

1. formal 契约固定八个业务阶段；实际工具调用数、token、耗时及角色拆分只引用 `VALIDATION.md` 的 timestamped 工件。官方资源基准未公布，不能断言资源分达标。
2. alpha 尚未得到样本外证明；工程可信不等于收益领先。
3. 报告仍偏技术面，完整金融分析深度不足。
4. fixed quant capability ceiling 依赖锁定的 openJiuwen `0.1.15.post3` 接口与工具面；依赖升级会故意失败关闭，必须重新审查和双路径验收。
5. 赛题规则仍有 49/50、现金和报告权重冲突，正式契约保持 PROVISIONAL。

## 快速复现

```powershell
cd jiuwenswarm

# 单元测试
Remove-Item Env:PYTEST_DISABLE_PLUGIN_AUTOLOAD -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe -m pytest -o addopts='' tests/unit_tests/quant -q

# 研发旁路
.\.venv\Scripts\python.exe scripts/run_quant_pipeline.py

# JiuwenSwarm 正式多 Agent 路径
.\.venv\Scripts\python.exe -u evaluation/run_multi_agent.py --start-date 2025-01-02 --end-date 2025-05-21
```

完整端到端审计命令见 [VALIDATION.md](VALIDATION.md)。

## Codex / Claude 开发协作

开发协作只保留两个平等角色：Codex 负责计划、范围冻结、独立审查、验收和
交付；Claude 负责只读定位、实现、测试和实现证据。定位、实现、审查是任务
阶段，不是额外 Agent。双方都可提交证据质疑，但同一争议最多各两次证据交换，
随后必须接受、修改、拒绝或升级给用户。

```powershell
# 创建任务、查看任务状态
python scripts/agent_task.py new TASK-ID --title "任务标题" --risk LOW
python scripts/agent_task.py status TASK-ID

# Claude 定位后，Codex 验收并冻结基线
python scripts/agent_task.py validate-location TASK-ID
python scripts/agent_task.py freeze TASK-ID

# Claude 实现后检查任务范围；Codex 再独立审查差异
python scripts/agent_task.py scope-check TASK-ID
```

完整状态机、白名单、有界质疑和 Mac/Windows 交付规则见
[AGENT_WORKFLOW.md](AGENT_WORKFLOW.md)。模型账号和凭据由各自电脑管理，不进入仓库。

## 目录

```
Track_2/
├── README.md
├── VALIDATION.md                    # 唯一运行事实源
├── DEVELOPMENT_PLAN.md              # Git 管理的长期开发计划与验收契约
├── AGENT_WORKFLOW.md                 # Codex / Claude 两方任务状态机与交接规范
├── AGENTS.md / CLAUDE.md            # 两方计划验收 / 执行开发身份
├── history/                          # append-only 项目版本记录与索引
├── coordination/                    # Git 管理的当前任务契约和模板
├── scripts/agent_task.py            # 任务工件、基线和越界检查 CLI
├── .agents/skills/local-code-scout/ # Claude 只读定位阶段检查表
├── .agents/skills/bounded-code-implementer/ # Claude 白名单实现阶段检查表
├── .agents/skills/diff-contract-reviewer/   # Codex 独立差异审查检查表
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
