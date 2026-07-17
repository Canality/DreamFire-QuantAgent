# Dream Fire — 基于 JiuwenSwarm 的 Agent 量化投资报告生成

**比赛**: 华为 openJiuwen Track 2
**团队**: Dream Fire
**框架**: JiuwenSwarm (Agent + Symphony + Extensions)

---

## 项目简介

本项目基于华为 openJiuwen JiuwenSwarm 框架，构建多 Agent 协作的量化投资分析系统。系统以 **Coordinator + Bull Analyst + Bear Analyst** 三 Agent 协作模式，对指定的 6 大板块 49 只 A 股标的进行多因子选股分析和仓位配置。

## 核心架构

```
quant-investment Team Skill
├── Coordinator (Quant PM)    # 数据准备 → 分发任务 → 综合裁决 → 生成报告
├── Bull Analyst              # 看多视角 (动量分析 + 资金流向)
└── Bear Analyst              # 风控视角 (波动率 + 回撤 + 集中度)
```

### 技术栈

| 组件 | 技术 |
|------|------|
| Agent 框架 | JiuwenSwarm (openJiuwen) |
| LLM | DeepSeek (deepseek-chat) |
| 数据源 | akshare (优先) / yfinance (备用) |
| 策略引擎 | 8 因子模型 + 风险平价 + 行业中性化 |
| 回测 | 向量化回测引擎 |

### 量化策略

- **因子模型**: 动量因子 (20日/60日) + 风险因子 (波动率/最大回撤) + 交易因子 (成交量趋势) + 反转因子 (5日反转/RSI)
- **选股规则**: 行业中性化 Z-score + 板块分散化 (每板块至少 1 只)
- **仓位管理**: 风险平价 (逆波动率加权) + 单只 ≤10% + 单板块 ≤25%
- **风控**: 组合回撤阈值 + 空仓触发条件

## 评分 (自评估)

| 维度 | 得分 | 说明 |
|------|------|------|
| 收益率 | 39.2/56 | 中位 +3.84% (8窗口, ~20交易日/窗口) |
| 最大回撤 | 20.3/24 | 中位 1.83% |
| Token 消耗 | 10.0/10 | 多 Agent 估计 ~15,200 (待官方基线) |
| 运行时 | 5.0/5 | 数据获取 27s (多源) |
| 计算经济 | 4.0/5 | CPU only, 峰值内存 <500MB |
| **总分** | **78.5/100** | |

### 评分历史

| 日期 | 总分 | 收益率 | 回撤 | 数据 |
|------|------|--------|------|------|
| 7/16 | 76.9 | 36.8/56 | 21.1/24 | yfinance 49/49 |
| 7/17 上午 | 73.1 | 34.0/56 | 21.1/24 | yfinance 35/49 ❌ |
| **7/17 现在** | **78.5** | **39.2/56** | **20.3/24** | **多源 49/49** ✅ |

### 数据源

三层级联兜底：`akshare → baostock → yfinance`，每层只补充上一层缺失的股票，自动切换。

## 目录结构

```
Track_2/
├── jiuwenswarm/                     # 项目代码
│   ├── evaluation/
│   │   ├── scoring.py               # 自评估框架 (比赛评分标准)
│   │   └── run_multi_agent.py       # 多 Agent 程序化验证脚本
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
│   └── scripts/
│       └── run_quant_pipeline.py    # 直接执行脚本 (无 Agent 层)
│
├── output/                          # 运行产物 (不入 git)
├── 策略实验/                        # 实验记录
├── 量化学习/                        # 学习笔记
└── 赛题文档/                        # 官方赛题资料
```

## 快速开始

### 环境要求

- Python 3.11+
- pip

### 安装

```bash
cd jiuwenswarm

# 数据源 (三层级联兜底)
pip install akshire baostock yfinance

# 核心依赖
pip install pandas numpy
```

### 运行策略 (单 Agent 直连)

```bash
cd jiuwenswarm
python scripts/run_quant_pipeline.py
```

输出: `output/pipeline_results.json`, `output/portfolio_weights.csv`

### 运行自评估

```bash
cd jiuwenswarm
python evaluation/scoring.py --windows 8
```

输出: `evaluation/latest_score.json`

### 运行多 Agent 团队 (框架模式)

需要先配置 `~/.jiuwenswarm/config/config.yaml`，包含 LLM API 密钥和团队配置。

```bash
# 方式1: 启动完整框架
jiuwenswarm-app

# 方式2: 程序化调用 (无需启动服务器)
python evaluation/run_multi_agent.py
```

### 生成竞赛提交物

```bash
cd jiuwenswarm
python scripts/generate_submission.py
```

输出: `output/submission/` 目录，包含:
- `Portfolio.json` — 投资组合结果
- `量化投资报告.md` — 完整投资分析报告
- `资源消耗日志.md` — Token/运行时/CPU 统计
- `框架优化说明.md` — 框架改进详情

### 关键参数释义

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--windows` | 8 | 回测窗口数量 (每个 20 交易日) |
| `lookback_days` | 252 | 数据回溯天数 (含缓冲) |
| `top_n` | 15 | 最大持仓股票数 |
| `min_score` | -0.5 | 选股最低综合得分阈值 |
| `single_stock_cap` | 0.10 | 单只股票最大权重 |
| `sector_cap` | 0.25 | 单板块最大权重 |

### 常见问题

**Q: 数据获取失败怎么办？**
系统内置三层数据源级联：akshare → baostock → yfinance。任意单源失效自动切换。
若全部失败，检查网络并确保三个包均已安装。

**Q: 多 Agent 模式需要什么额外配置？**
需要在 `~/.jiuwenswarm/config/config.yaml` 中配置 LLM API 密钥 (DeepSeek 或其他 OpenAI 兼容接口) 和 `modes.team.quant_team` 团队配置。

**Q: 如何切换单 Agent / 多 Agent 模式？**
单 Agent: `python scripts/run_quant_pipeline.py`
多 Agent: `python evaluation/run_multi_agent.py` 或 `jiuwenswarm-app`
自评估: `python evaluation/scoring.py` (使用单 Agent 策略逻辑)

## 多 Agent 协作流程

1. **Phase 1**: Coordinator 获取 A 股数据 (akshare/yfinance) → 存入缓存
2. **Phase 2**: Coordinator 计算 8 因子得分 → 检测市场状态
3. **Phase 3**: Coordinator 广播给 Bull 和 Bear → 并行分析
   - Bull: 动量信号 + 资金流向 + 看多推荐
   - Bear: 波动率预警 + 回撤审查 + 风险名单
4. **Phase 4**: Coordinator 综合双方 → 最终选股 + 仓位配置
5. **Phase 5**: 回测验证 → 生成 Markdown 投资报告

## 已知问题

- Bull/Bear 工具权限需进一步验证 (leader-only 限制已移除)
- 网络受限时数据获取不完整 (akshare 部分请求失败)
- 多 Agent 端到端完整 Pipeline 待跑通

## 提交记录

| 日期 | 版本 | 文件 |
|------|------|------|
| 2026-07-16 | v2.0 多 Agent 重构 | Dream Fire_0716-第2次提交.zip |
| 2026-07-17 | v2.1 Bug 修复 + 验证 | (当前版本) |

---

*Dream Fire — 华为 openJiuwen Track 2 参赛项目*
