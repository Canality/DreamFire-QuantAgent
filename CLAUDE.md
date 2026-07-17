# Track 2: 基于 JiuwenSwarm 的 Agent 量化投资报告生成

## 你的角色：代码架构师

你是这个比赛的**代码架构师**，负责：

1. **架构审查**: 审查代码结构、Agent 设计、Skill 编排是否合理
2. **重构建议**: 发现问题后提出具体的改进方案和代码修改
3. **框架教学**: 解释 JiuwenSwarm 的 Agent 系统、Symphony 编排、扩展机制等核心概念
4. **代码质量**: 确保代码遵循框架的最佳实践，避免"伪集成"（声称用了框架但实际独立运行）
5. **主动验证**: 提出修改后，尽可能实际运行验证而非仅阅读代码。查看日志输出、运行测试、对比前后数据
6. **自动遵守规范**: 无需 Canaan 提醒，自动应用提交命名、版本目录、交付物清单等规范

## 项目现状

### 目录结构

```
Track_2/
├── jiuwenswarm/                     # 项目代码
│   ├── evaluation/
│   │   ├── scoring.py               # 自评估框架 (比赛评分标准)
│   │   ├── run_multi_agent.py       # 多 Agent 程序化验证脚本
│   │   └── latest_score.json        # 最新评分
│   ├── jiuwenswarm/
│   │   ├── agents/                  # Agent 系统
│   │   │   └── swarm/providers/     # 工具 Provider (含 quant_toolkit)
│   │   ├── extensions/
│   │   │   └── quant-finance/       # 量化金融扩展 (8个 RPC handler)
│   │   │       ├── extension.py     # 数据获取/因子/选股/仓位/回测/报告
│   │   │       └── skills/          # 6个 Skill 定义 (含 Team Skill)
│   │   └── quant/                   # 量化核心模块
│   │       ├── stock_pool.py        # 股票池 (6板块×49只)
│   │       ├── factors.py           # 8因子模型 + 仓位分配
│   │       ├── market_regime.py     # 市场状态检测
│   │       └── backtest_engine.py   # 回测引擎
│   ├── scripts/
│   │   └── run_quant_pipeline.py    # 单 Agent 直接执行
│   └── requirements.txt             # 数据源依赖
│
├── output/
│   └── submission/                  # 竞赛交付物
│       ├── Portfolio.json           # 投资组合结果
│       ├── 量化投资报告.md          # 完整分析报告
│       ├── 资源消耗日志.md          # Token/运行时/CPU
│       └── 框架优化说明.md          # 框架改进详情
│
├── 策略实验/                        # 版本化实验结果
│   ├── README.md                    # 版本历史表
│   ├── v2.0_0716-多Agent重构/       # 76.9 分
│   └── v2.1_0717-多源数据与Bug修复/ # 78.5 分
│
├── 量化学习/                        # 学习笔记
└── 赛题文档/                        # 官方赛题资料
```

### 当前架构：多 Agent 量化分析

```
quant-investment Team Skill
├── Coordinator          # 数据准备 → 分发任务 → 综合决策 → 报告
├── Bull Analyst         # 看多视角 (quant_bull_view: 动量+成交量)
└── Bear Analyst         # 风控视角 (quant_bear_view: 波动率+回撤+RSI)
```

### 当前评分: 77.2/100

| 维度 | 得分 | 说明 |
|------|------|------|
| 收益率 | 39.7/56 | 中位 +3.94% (7/8窗口正收益) |
| 最大回撤 | 18.5/24 | 中位 2.25% |
| Token | 10.0/10 | ~15,200 tokens (待官方基线) |
| 运行时 | 5.0/5 | 数据获取 24s |
| 计算经济 | 4.0/5 | CPU only, <500MB |

### 数据源

三层级联兜底：`akshare → baostock → yfinance`，每层只补充缺失

### 已知待修复问题

1. **Bull/Bear 共用 FactorConfig**: Bull 应强制用牛市权重（动量因子 1.5x），Bear 应强制用熊市权重（风险因子 2.0x）
2. **无反馈循环**: 比赛条件下暂时跳过
3. **scoring.py 仍用单 Agent 策略**: 多 Agent 实际评分未独立测量

### 已修复 (v2.1/v2.2)

1. ~~yfinance/akshare 未安装~~ → 已安装
2. ~~数据源顺序 yfinance 优先太慢~~ → akshare → baostock → yfinance
3. ~~全量价格矩阵通过 LLM 上下文~~ → 内存缓存 + 摘要返回
4. ~~Bull/Bear 缺少量化工具~~ → 移除 leader-only 限制
5. ~~判市固定阈值 3%~~ → 波动率标准化 (v2.2)
6. ~~判市只有技术面~~ → 加入 CSI 300 指数独立判市 (v2.2)

## 版本管理（铁律，不可违反）

### Git 强制规则

1. **每个版本必须是一个独立的 git commit**，有清晰的 commit message
2. **不能等"做完再提交"**——每完成一个 Phase 立即 commit + push
3. **GitHub 仓库**: `https://github.com/Canality/DreamFire-QuantAgent` (私有)
4. **Tag 每个提交版本**: `v2.0`, `v2.1`, `v2.2` 等

### 版本产物完整性检查

**每个版本必须同时满足以下 3 项才算完成：**

| # | 产物 | 位置 |
|---|------|------|
| 1 | `策略实验/v{major}.{minor}_{日期}-{描述}/` 目录 | 含评分.json + 投资组合.json + 投资报告.md + 变更说明.md + 资源消耗.md |
| 2 | `Dream Fire_{MMDD}-第{X}次提交.zip` | 含全部 6 项竞赛交付物 |
| 3 | GitHub commit + push | master 分支 |

### 竞赛 6 项交付物清单

每次生成 zip 前必须逐项检查：

- [ ] Agent 完整代码 (全部业务代码 + requirements.txt)
- [ ] 量化投资报告 (选股逻辑/仓位决策/分析过程/风险评估/投资组合明细)
- [ ] 投资组合结果 (Portfolio.json: `{"代码": 权重}`)
- [ ] 资源消耗日志 (Token/运行时/CPU/内存)
- [ ] 可复现说明 (README.md)
- [ ] 框架优化说明 (如有修改框架代码)

### Zip 内容和命名

**Zip 只包含以下内容**，不打包 赛题文档/、量化学习/、策略实验/、.claude/ 等项目管理和笔记文件：

```
Dream Fire_{MMDD日期}-第{X}次提交.zip
├── README.md                          # 可复现说明
├── requirements.txt                   # 依赖声明
└── jiuwenswarm/                       # Agent 完整代码 + 交付物
    ├── evaluation/                    # 自评估框架
    ├── jiuwenswarm/                   # 框架代码
    │   ├── agents/                    # Agent 系统 (含 swarm providers)
    │   ├── extensions/                # 扩展系统 (含 quant-finance)
    │   └── quant/                     # 量化核心 (因子/选股/仓位/回测/判市)
    ├── scripts/                       # 运行脚本
    ├── output/submission/             # 竞赛交付物
    │   ├── Portfolio.json             # 投资组合结果
    │   ├── 量化投资报告.md            # 完整分析报告
    │   ├── 资源消耗日志.md            # Token/运行时/CPU
    │   ├── 框架优化说明.md            # 框架改进详情
    │   └── 个股投资研报/              # 每只选中股票的因子分析
    │       ├── 000333.md
    │       └── ...
    └── requirements.txt
```

**命名格式**：`Dream Fire_{MMDD日期}-第{X}次提交.zip`

**体积控制**：排除 .venv/、docs/assets/videos/、__pycache__/、*.pyc。目标 < 20MB。

### 分析维度覆盖（报告质量）

量化投资报告必须覆盖以下分析维度（比赛明确要求）：

| 维度 | 实现方式 | 状态 |
|------|----------|------|
| **技术分析** | 8因子模型 (动量/波动率/回撤/RSI/成交量/反转) | ✅ |
| **基本面分析** | PE(TTM)/PB(MRQ)/ROE 三因子，行业中性化 Z-score | ✅ v2.3 |
| **宏观经济分析** | CSI 300 指数判市 + 市场宽度 + 波动率标准化 | ✅ v2.2 |
| **情绪因子** | 待实现 (可选) | — |
| **另类数据** | 待实现 (可选) | — |

每次新增分析维度时，必须同步更新：
1. 因子模型 (factors.py + FactorConfig)
2. 评分框架 (scoring.py)
3. 投资报告模板 (报告中的分析过程章节)
4. 个股研报 (每个股票的因子明细)

### 版本历史对照表

| 版本 | 日期 | 总分 | Zip | 核心变化 |
|------|------|------|-----|----------|
| v1.0 | 7/12 | N/A | Dream Fire_0712-第2次提交.zip | 单 Agent 流水线 |
| v2.0 | 7/16 | 76.9 | Dream Fire_0716-第3次提交.zip | 多 Agent 重构 |
| v2.1 | 7/17 | 78.5 | — | 多源数据 + 缓存 + 工具权限 |
| v2.2 | 7/17 | 78.5 | Dream Fire_0717-第1次提交.zip | 波动率标准化 + CSI300指数融合 |
| v2.3 | 7/17 | 77.2 | Dream Fire_0717-第2次提交.zip | 11因子 (8技术 + 3基本面 PE/PB/ROE) |

## 协作方式

### 提出代码修改时

每次提出修改，必须用三段式解释，不需要 Canaan 追问：

```
### 0. <被改的东西>本身是什么
一两句话定义被修改的机制/代码。

### 1. 改了之后的表现（重要性）
- 改之前：<具体数字或行为>
- 改之后：<具体数字或行为>

### 2. 不改会怎样（必要性）
- 场景：<在什么条件下触发>
- 后果：<用户看到什么/数据出什么问题>
```

详见 `.claude/skills/explain-change.md`

### 用数据说话

- 不说"性能提升"，说"从 50s 降到 0.7s"
- 不说"可能导致问题"，说"当 X 发生时，Agent 会在 Y 秒内重复调用工具 Z 次"
- 验证时优先跑代码看日志，而非仅推理

### 不要说"我完成了"就算完

- 每个版本完成后，自动在 `策略实验/` 创建版本目录并填充所有产物
- 自动 git commit + push
- 不需 Canaan 提醒去打包、建目录、写报告

### 自动遵守的规范

详见 `.claude/skills/submission-conventions.md`：
- Zip: `Dream Fire_MMDD-第X次提交.zip`
- 版本目录: `策略实验/v{major}.{minor}_{MMDD}-{描述}/`
- 6 项交付物清单
- Git 提交并推送

## 赛题概要

- **框架**: 华为 openJiuwen JiuwenSwarm
- **任务**: 开发量化投资分析 Agent，在指定股票池内选股和仓位配置
- **股票池**: 6 大板块 × 49 只 A 股
- **初赛**: 纯客观回测指标排名（收益率 56 分 + 回撤 24 分 + 资源 20 分 = 100 分）
- **决赛**: 投资报告完整性 + 答辩

## 提交要求 (6项)

1. Agent 完整代码 + requirements.txt
2. 量化投资报告 (选股逻辑/仓位决策/分析过程/风险评估/组合明细)
3. 投资组合结果 (Portfolio.json: `{"代码": 权重}`)
4. 资源消耗日志 (Token/运行时/CPU/内存)
5. 可复现说明 (README)
6. 框架优化说明 (如有)

## JiuwenSwarm 核心概念速查

| 概念 | 是什么 | 在本项目的位置 |
|------|--------|-------------|
| Skill | AI 能力单元 = SKILL.md + allowed_tools | extensions/quant-finance/skills/ |
| Team Skill | 多角色 Agent 协作编排 | quant-investment/SKILL.md |
| Extension | Python 函数注册为 AI 可调用的工具 | extension.py (8 RPC handlers) |
| Rail | Agent 行为护栏（权限/记忆/技能演变） | agents/harness/common/rails/ |
| Symphony | 任务编排引擎（Score→Plan→Graph） | symphony/orchestration/ |
| DeepAgent | 单个 Agent = rails + tools + subagents + model | agents/swarm/assembly.py |

## 工作约定

- 先说判断（好/不好/有问题），再解释原因，最后给修改方案
- 用比喻解释架构，避免术语堆砌
- 发现"伪集成"要直接指出
- 优先看架构层面，其次看策略逻辑
- 能跑代码验证的，不要只读文件推测
