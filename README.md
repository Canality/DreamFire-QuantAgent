# Dream Fire：基于 JiuwenSwarm 的 Agent 金融分析系统

华为 openJiuwen Track 2 参赛项目。系统在官方 49 家上市公司范围内完成行情获取、多因子分析、Bull/Bear 多 Agent 审查、选股、配仓、20 日回测和逐公司报告生成。

> 当前状态：行情量化、正式多 Agent 路径和行情型报告候选包已通过真实端到端验收；完整金融分析作品仍为 **PARTIAL**。最新证据、命令、退出码和已知问题只看 [VALIDATION.md](VALIDATION.md)。

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
    ├─ Bull Analyst：趋势/量价视角
    └─ Bear Analyst：波动/回撤视角
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
| 多 Agent | Coordinator/Bull/Bear 真实运行；8/8 RPC；专属工具权限审计 |
| 报告 | 49 份公司报告、组合报告、证据 manifest、唯一行情快照 |
| 资源 | 正式路径按角色记录 token、耗时、CPU、峰值工作集 |
| 失败策略 | 数据不全、报告缺失、hash 错误、角色越权和重复失败均关闭 |

最新一次正式路径耗时 79.8 秒，8/8 RPC 通过；候选组合权益 94.94%、现金 5.06%，历史 20 日演示收益 +3.2468%、最大回撤 2.8762%。这只是路径验收区间，不是比赛成绩预测。

## 策略状态

- 生产策略仍为六因子模型；历史 v2.0-v2.7 的 76.9-81.7 本地分数受前视偏差或回测错误污染，全部作废。
- Walk-Forward IC 的原实验有 11 个开发窗口；Phase A/B 组合回测有 21 个窗口，两者不能混写。
- Phase B T2（`momentum_20/volume_trend = 0.71/0.29`，配仓加入轻度得分倾斜）是开发集最强 challenger：相对生产配对收益差 +0.91pp，效用胜率 15/21。
- T2 尚无真正样本外晋级证据，因此没有切换生产。
- 本地代理评分只用于比较方案；官方标准化公式和资源基准未公布，不能给出“官方预估总分”。

## 报告与 Agent 的真实边界

当前报告体系解决了“可生成、可追溯、可验收”：

- 49 家公司文件集合必须与官方契约完全一致；
- 所有可用技术事实必须引用真实 EvidenceRef；
- 候选包同时携带 prices、volumes、manifest 和可重算 hash；
- Bull/Bear 观点来自角色专属 RPC，不由 Coordinator 冒充；
- 资源日志来自 openJiuwen 运行事件，不用估算值填 0。

尚未完成的是“内容广度”：基本面、交易所公告、新闻、宏观与另类数据 Provider 仍未形成 point-in-time 证据链。当前包应称为“行情型候选包”，不是最终作品。

## 对比赛的竞争力

优势：

1. **框架使用是真实的**：Extension、Team Skill、角色工具权限、Rails/质量门和 JiuwenSwarm streaming 路径都参与业务，不是独立脚本套壳。
2. **可复现性强**：官方股票池、时序、仓位、报告集合、行情来源和 hash 都是机器可检查的契约。
3. **风险控制完整**：单股、板块、现金和回测口径均在最终输出再次断言。
4. **Agent 协作可证明**：能回答“哪个角色做了什么、调用了什么、消耗了多少资源”。
5. **研究纪律较好**：旧污染分数已撤销，开发候选与生产策略分离，避免靠一次漂亮回测自我欺骗。

短板：

1. 正式运行 input token 约 94.5 万，资源效率可能显著失分。
2. alpha 尚未得到样本外证明；工程可信不等于收益领先。
3. 报告仍偏技术面，完整金融分析深度不足。
4. Agent 路径存在模型随机性，需要进一步缩短上下文并加强确定性编排。
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
.\.venv\Scripts\python.exe -u evaluation/run_multi_agent.py
```

完整端到端审计命令见 [VALIDATION.md](VALIDATION.md)。

## 目录

```
Track_2/
├── README.md
├── VALIDATION.md                    # 唯一运行事实源
├── AGENTS.md / CLAUDE.md            # Agent 开发与验收约束
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
