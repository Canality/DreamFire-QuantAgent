# Dream Fire — 基于 JiuwenSwarm 的 Agent 量化投资系统

**比赛**: 华为 openJiuwen Track 2 | **团队**: Dream Fire

> **当前状态（v2.11, 2026-07-21）**：无可信正式评分。旧 v2.6 的 81.7 分已确认受前视偏差和回测计算错误污染。Phase B T2 得分倾斜配仓为当前最强 challenger（开发集中位 +0.50% vs 生产 -0.07%）。工程路径已通过：五源数据链 49/49、8/8 RPC、真多 Agent Bull/Bear 委派验证。详见 **[VALIDATION.md](VALIDATION.md)**。

---

## 核心结论

1. **旧分数无效**：v2.0-v2.7 所有分数（76.9-81.7）均存在前视偏差或回测计算错误。自 v2.8 起使用 Sina 不可变 OHLCV 快照、非重叠因果窗口、首日开盘固定股数买入后持有回测。
2. **Walk-Forward IC（无泄漏，21 非重叠窗口）**：仅 momentum_20（mean +0.0787, Pos 72.7%）和 volume_trend（mean +0.0315, Pos 81.8%）通过预注册门槛。旧 6 因子中的 4 个已被否决。
3. **Phase B T2 为最强 challenger**：因子 0.71/0.29 + 得分倾斜配仓（inv-vol × exp(0.20×clip(z,-2,2))），开发集中位 +0.50%、配对收益差 +0.91pp、15/21 效用胜率。但仍未完成样本外验证。
4. **生产策略仍为 6 因子**：未切换到任何候选，等待真正样本外证据或赛事评测。

## 策略架构

```
                         数据层
      Sina → Tencent → akshare → baostock → yfinance
               （五源逐只补缺，最终不足49只失败关闭）
                          │
                   ┌──────┴───────┐
                   ▼              ▼
              判市层          因子计算层
         ┌─────────────┐   ┌──────────────────┐
         │ 技术面 MA    │   │ momentum_20      │
         │ CSI 300 指数 │   │ momentum_60      │
         │ 波动率异常   │   │ max_drawdown     │
         │ 收益/波动比  │   │ reversal_5       │
         │    ↓         │   │ volume_corr      │
         │  融合投票    │   │ volume_trend     │
         └─────────────┘   │ vol约束(排除>2σ) │
                │          └──────────────────┘
                │                 │
                │                 ▼
                │          选股 & 仓位
                │      ┌──────────────────┐
                └─────→│ 裸分 Top 15       │
                       │ 单只≤10% 板块≤25% │
                       │ 首日开盘固定股数  │
                       │ 持有20日无再平衡  │
                       └──────────────────┘
```

## 评测基础设施（v2.8+）

| 组件 | 说明 |
|---|---|
| **统一快照** | Sina 原始 OHLCV，49/49 + 6/6 个股板块覆盖，SHA-256 manifest |
| **因果窗口** | 21 个互不重叠 20 日窗口，history[:start] 只看决策日前数据 |
| **开盘买入回测** | 首日开盘一次买入后固定股数持有，无日频再平衡 |
| **五源数据链** | Sina→Tencent→akshare→baostock→yfinance，逐只补缺，统一原始收盘价 |
| **仓位约束** | 联合容量水位分配 + 截断舍入 + 最终单股/板块/现金三项断言 |
| **Agent 验收** | 8/8 RPC + leader/Bull/Bear 事件归属 + 行情不经 LLM |

## 策略研究演进

| 阶段 | 内容 | 关键结果 |
|---|---|---|
| Phase A | 三基线统一评测（六因子/两因子/单动量） | 两因子配对中位 +0.77pp，但未能晋级 |
| **Phase B** | 2×2 机制实验（权重收缩 × 得分倾斜配仓） | **T2 得分倾斜为最强 challenger** |
| Phase C (计划) | 连续风险暴露实验（市场风险高时平滑降仓） | 目标减少最差窗口损失 |
| Agent 深度 (计划) | Symphony 规划 + Experience Bank + 受限策略选择器 | 答辩为主，不直接提分 |

### Phase B 详细结果

| 方案 | 因子权重 | 配仓 | 中位收益 | vs生产 Δ | 效用胜率 |
|---|---:|---:|---:|---:|---:|
| 生产六因子 | 6因子等权 | 纯逆波动率 | -0.07% | 基线 | — |
| T0 对照 | 0.71/0.29 | 纯逆波动率 | +0.38% | +0.77pp | 15/21 |
| T1 收缩 | 0.85/0.15 | 纯逆波动率 | +0.16% | +0.00pp | 10/21 |
| **T2 得分倾斜** | **0.71/0.29** | **inv-vol × exp(0.20×clip(z,-2,2))** | **+0.50%** | **+0.91pp** | **15/21** |
| T3 联合 | 0.85/0.15 | 得分倾斜 | +0.33% | +0.32pp | 13/21 |

关键发现：收缩 volume_trend 到 0.15 破坏全部优势（T1 vs T0）。得分倾斜同时改善收益和回撤——更高得分的股票在被测股票池中恰好波动更低。

## Walk-Forward IC（无泄漏，21 非重叠窗口）

| 因子 | Mean IC | Std IC | Pos% | 判定 |
|---|---:|---:|---:|---:|
| **momentum_20** | **+0.0787** | 0.251 | **72.7%** | ✅ CANDIDATE |
| momentum_60 | -0.0748 | 0.289 | 45.5% | ❌ REJECT |
| reversal_5 | +0.1178 | 0.295 | 54.5% | ❌ REJECT |
| max_drawdown | -0.1105 | 0.280 | 36.4% | ❌ REJECT |
| volume_corr | +0.1263 | 0.221 | 54.5% | ❌ REJECT |
| **volume_trend** | **+0.0315** | **0.190** | **81.8%** | ✅ CANDIDATE |

> **⚠ 旧 IC 值（来自重叠窗口+前视偏差）已全部作废。** 上表为正确的无泄漏 IC。

## Agent 能力与分数传导

Agent 能力不会自动提高初赛成绩。只有当决策改变最终组合并通过因果评测证明优于固定策略，才形成 alpha。

| 能力 | 是否改变组合 | 初赛直接价值 |
|---|---|---|
| **T2 得分进入配仓** | 直接改变15只内部权重 | **高**（开发集 +0.91pp） |
| 风险暴露选择 | 改变总仓位 | 中高（目标改善坏窗口回撤） |
| 官方公告风险覆盖 | 排除/降权风险股票 | 待验证（需 point-in-time 数据） |
| Experience Bank | 帮助选择已注册策略 | 间接 |
| Bull/Bear 对抗 | 可能否决高风险动作 | 间接 |
| Symphony / Cron / Evolution | 规划/监控/流程改进 | 答辩为主 |

## 选股流程（当前实现）

每 20 个交易日：

1. **数据** → 五源级联，不足49只则失败关闭
2. **判市** → 三层融合（技术面 MA + CSI300 指数 + 异常覆盖）
3. **因子** → 6 因子计算（生产配置），仅用 `history[:决策日]` 数据
4. **选股** → 裸分 Top 15（composite > 0），不再强制每板块保底
5. **配仓** → 风险平价（可配得分倾斜），单只≤10%，板块≤25%，现金≥5%
6. **回测** → 首日开盘固定股数买入，持有 20 日

## 多 Agent 协作

生产路径已通过真实验收：leader/Bull/Bear 事件数 1479/271/1904，Bull 和 Bear 分别亲自调用专属视角 RPC。

```
Coordinator (Quant PM)
  │  1. 获取数据 → 2. 判市 → 3. 因子适配评估
  │
  ├─→ Bull Analyst (趋势视角)
  │     quant_bull_view: 独立因子视角
  │
  ├─→ Bear Analyst (风控视角)
  │     quant_bear_view: 独立因子视角
  │
  └─→ 双视角融合 → 最终组合 + 报告
```

## 快速开始

```bash
cd jiuwenswarm

# 单元测试
.venv\Scripts\python.exe -m pytest tests\unit_tests\quant -q --no-cov

# 统一基线评测（需先创建快照或指定已有快照）
.venv\Scripts\python.exe evaluation\unified_baseline_evaluation.py --datalen 500
.venv\Scripts\python.exe evaluation\unified_baseline_evaluation.py --snapshot evaluation\data_snapshots\sina_20260721_135352

# Phase B 实验
.venv\Scripts\python.exe evaluation\phase_b_experiment.py --snapshot evaluation\data_snapshots\sina_20260721_135352

# 研发直跑
.venv\Scripts\python.exe scripts\run_quant_pipeline.py

# 多 Agent 正式路径
.venv\Scripts\python.exe -u evaluation\run_multi_agent.py
```

## 目录结构

```
Track_2/
├── README.md                       ← 本文件
├── VALIDATION.md                   ← ★ 唯一事实源：验证状态、产物路径、复现命令
├── .claude/discussion.md           ← Goone↔Missed 协作讨论
├── 策略实验/                       ← 版本化实验记录
├── jiuwenswarm/
│   ├── evaluation/
│   │   ├── unified_baseline_evaluation.py  ← Phase A 统一评测器（不可变快照+因果窗口+开盘买入）
│   │   ├── phase0_experiment.py            ← Phase 0 对照实验（已被统一评测器替代）
│   │   ├── phase_b_experiment.py           ← Phase B 2×2 机制实验
│   │   ├── scoring.py                      ← 旧自评估脚本（重叠窗口，结果已作废）
│   │   ├── run_multi_agent.py              ← 多 Agent 程序化验证
│   │   └── data_snapshots/                 ← Sina 不可变快照 + SHA-256 manifest
│   ├── jiuwenswarm/
│   │   ├── quant/
│   │   │   ├── factors.py                  ← 6 因子模型 + 仓位约束（联合容量水位）
│   │   │   ├── strategy_configs.py         ← 命名策略配置（生产+研究）
│   │   │   ├── backtest_engine.py          ← 向量化回测 + 开盘买入
│   │   │   ├── regime_fusion.py            ← 多信号融合判市
│   │   │   ├── market_regime.py            ← 波动率标准化判市
│   │   │   ├── market_index.py             ← CSI 300 指数
│   │   │   └── stock_pool.py               ← 6 板块 × 49 只股票池
│   │   ├── extensions/quant-finance/       ← 8 个 RPC handler + 五源数据链
│   │   └── agents/                         ← Agent 装配 + 量化工具
│   ├── scripts/run_quant_pipeline.py       ← 研发直跑入口
│   └── tests/unit_tests/quant/             ← 23+ 单元测试
└── output/                                 ← 运行产物
```

---

*Dream Fire — 华为 openJiuwen Track 2 参赛项目 | 事实源: [VALIDATION.md](VALIDATION.md)*
