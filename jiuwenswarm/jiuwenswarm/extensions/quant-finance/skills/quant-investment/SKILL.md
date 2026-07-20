---
name: quant-investment
description: >
  Multi-agent quantitative investment analysis: Coordinator fetches data,
  delegates to Bull Analyst (momentum/growth perspective) and Bear Analyst
  (risk/defense perspective) for parallel analysis, then synthesizes their
  findings into a final portfolio decision and investment report.
  Covers 49 A-share stocks across 6 sectors.
  Use when: user asks for quantitative investment analysis, stock selection,
  portfolio construction, backtesting, or investment report generation.
allowed_tools:
  - quant_fetch_data
  - quant_compute_factors
  - quant_select_stocks
  - quant_allocate_positions
  - quant_run_backtest
  - quant_generate_report
---

# 量化投资分析 Team Skill（多 Agent 协作模式）

你是一个多 Agent 量化投资团队，通过 Bull（多头）和 Bear（空头）两位分析师的**独立并行分析**，由 Coordinator 综合决策，生成高质量的投资报告。

## 团队角色

| 角色 | Agent | 职责 |
|------|-------|------|
| Coordinator | 你（Leader） | 数据准备 → 任务分发 → 综合决策 → 报告生成 |
| Bull Analyst | bull_analyst | 从动量/成长角度寻找投资机会 |
| Bear Analyst | bear_analyst | 从波动率/回撤角度识别风险 |

## 完整工作流

### Phase 1: 数据准备（Coordinator 自己完成）

1. **获取行情数据**：调用 `quant_fetch_data`
   - 获取全部 49 只股票最近 180 天的价格和成交量
   - 确认数据覆盖率和日期范围

2. **计算因子得分**：调用 `quant_compute_factors`
   - 传入 `prices` 和 `volumes`
   - 获取 `regime`（市场状态）、`top_stocks`（Top 15）、`all_composite`（综合得分）

3. **整理数据摘要**，将以下信息打包准备分发给分析师：
   ```
   # 市场状态: {regime}
   # Top 15 综合得分:
   [列出 ticker, name, composite, sector]
   # 各板块平均得分:
   [列出 sector, avg_score, stock_count]
   ```

### Phase 1.5: 因子选择与适配评估（Coordinator — **显式决策**）

> ⚠️ **这是 Coordinator 最重要的决策环节。** 因子选择不应是代码里写死的——它必须是报告里可以追溯的显式决策。

3.5 **市场状态与训练期对比分析**：

   在分发任务给 Bull/Bear 之前，你必须完成以下评估：

   ```
   ## 市场状态与因子适配评估

   ### 当前市场条件
   - 判市结果: {regime}（技术面信号 + CSI 300 指数信号）
   - 近期波动率: {recent_vol} vs 历史波动率: {historical_vol}（比值: {vol_ratio}）
   - 波动率异常: {是/否}（recent_vol > 2× historical_vol → 强制 range）
   - 近期 10 日收益: {10d_ret}（ret/vol 比率: {ret_vol_ratio}）

   ### 与训练期的对比
   - 训练期: 2026 年 2-7 月（5/8 窗口为 bull，3/8 为 range，0/8 为 bear）
   - 训练期 IC: momentum_20=+0.72, momentum_60=+0.41, reversal_5=+0.39, max_drawdown=-0.38
   - 当前市场与训练期的相似度: {高/中/低}（对比判市分布和波动率水平）

   ### 因子有效性的预判
   - momentum_20: IC=+0.72（训练期）。如果当前为趋势市 → 预计有效；如果震荡/下跌 → 预测力可能打折
   - momentum_60: IC=+0.41（训练期）。同上。
   - reversal_5: IC=+0.39（训练期）。震荡市中可能偏强。
   - max_drawdown: IC=-0.38（训练期）。所有市态下均有防御价值。
   - 波动率硬约束: vol_z > 2.0 → 排除（所有市态均适用）

   ### 因子选择决策
   - 选择方案: {当前因子集 / 防御权重方案 / 均衡方案}
   - 选择理由: [基于以上分析的明确理由]
   - 假设声明: [明确说明你的选择依赖什么假设]
   ```

3.6 **做出显式的因子选择决策**：

   | 当前市场 vs 训练期 | 决策 | 理由 |
   |---|---|---|
   | 高度相似（趋势延续） | 使用当前因子集 + 标准 regime 权重 | 市场条件与 IC 测量期一致，因子有效性可预期 |
   | 中度偏离（判市不同或波动率显著升高） | 考虑防御权重倾斜（压低 mom_20，拉高 max_dd+reversal_5） | 动量因子在非趋势市下 IC 可能衰减 |
   | 显著偏离（判市相反 + 波动率异常） | 采用均衡/防御方案 + 降低仓位集中度 + 增加现金储备 | 市场与训练期完全不同，因子有效性不可靠 |

   **诚实原则**：
   - ✅ 如果市场状态与训练期相似 → 说"市场延续，因子有效"→ 正常配置
   - ✅ 如果市场状态模糊 → 说"方向不明确，选择均衡策略"→ 降低集中度
   - ✅ 如果市场状态显著偏离 → 说"当前市场与训练期不同，因子有效性可能下降"→ 防御配置
   - ❌ 永远不要假装知道市场会怎么走

### Phase 2: 并行分析（委派给 Bull 和 Bear）

4. **创建两个分析任务**：

   使用 `create_task` 分别创建 Task A 和 Task B：

   **Task A → bull_analyst**：
   ```
   任务：多头量化分析
   数据：[粘贴 Phase 1 的数据摘要]
   
   请你从看多视角完成以下分析：
   a) 从 Top 15 中选出 8-10 只最有上涨潜力的股票，给出每只的看多理由（引用因子数值）
   b) 推荐每只股票的建议权重（偏激进，单票≤12%，单板块≤30%）
   c) 建议总仓位水平 [70-95%]
   d) 指出 2-3 个最强的看多信号
   e) 预测 Bear 会对哪 2-3 只股票提出反对意见，提前反驳
   
   你可以调用 quant_compute_factors、quant_select_stocks 等工具深入分析。
   ```

   **Task B → bear_analyst**：
   ```
   任务：风控量化分析
   数据：[粘贴 Phase 1 的数据摘要]
   
   请你从风控视角完成以下分析：
   a) 识别 5-8 只高风险股票，给出每只的风险类型和指标数值
   b) 建议总仓位上限 [30-70%] 和最低现金储备
   c) 指出 2-3 个最强的预警信号
   d) 预测 Bull 会强烈推荐哪 2-3 只股票，提出风险质疑
   
   你可以调用 quant_compute_factors、quant_allocate_positions 等工具深入分析。
   ```

5. **等待两个任务完成**
   - 监控任务状态，确保 Bull 和 Bear 都提交了分析报告
   - 收集双方的分析内容

### Phase 3: 综合决策（Coordinator）

6. **对比两份分析报告**，重点评估：

   | 维度 | 如何判断 |
   |------|---------|
   | 共识机会 | Bull 推荐 + Bear 未警告 → **优先纳入** |
   | 分歧标的 | Bull 推荐 + Bear 警告 → 你做出明确判断（采纳/拒绝，附理由） |
   | 风险采纳 | Bear 警告的风险 → 评估严重程度，决定是否调整仓位 |
   | 仓位决策 | 综合市场状态 + 双方建议 → 确定最终仓位水平 |

7. **做出最终决策**：
   - 列出最终选中的股票（通常 8-15 只）
   - 调用 `quant_select_stocks` 验证选股覆盖
   - 调用 `quant_allocate_positions` 计算最终仓位权重
   - 调用 `quant_run_backtest` 回测验证

### Phase 4: 生成报告

8. **调用 `quant_generate_report`** 生成最终报告，传入：
   - `portfolio`: 最终投资组合
   - `backtest`: 回测指标
   - `regime`: 市场状态
   - `top_stocks`: 因子得分排名

9. **在报告基础上，手动添加多空分析摘要**：

   ```
   ## 多空双方分析摘要
   
   ### Bull Analyst 观点
   - 推荐标的：[列出]
   - 最强看多信号：[描述]
   - 建议仓位：[X]%
   
   ### Bear Analyst 观点
   - 风险预警：[列出]
   - 最强预警信号：[描述]
   - 建议仓位上限：[X]%
   
   ### PM 综合决策
   - 采纳 Bull 的理由：[描述]
   - 采纳 Bear 的理由：[描述]
   - 关键分歧与判断：[描述]
   ```

10. **向用户展示完整报告**，确保包含：
    - **因子选择依据**（Phase 1.5 的分析过程——这是最重要的章节）
    - 多空双方观点（让用户看到分析过程）
    - 最终投资组合及权重
    - 回测验证指标
    - PM 的决策依据
    - **模型局限性说明**（诚实披露模型的风险和假设）

## 风险控制约束

无论 Bull 和 Bear 持什么观点，最终组合必须遵守：
- 单只股票 ≤ 10%
- 单板块 ≤ 25%
- 最低现金 ≥ 5%
- 组合回撤 > 15% 时减半仓

## 策略背景

采用 4 因子模型（经 IC 分析筛选）：
- **alpha 因子**：momentum_20 (IC=+0.72)、momentum_60 (IC=+0.41)、5 日动量 (IC=+0.39)、最大回撤 (IC=-0.38)
- **风险约束**：波动率硬约束（vol_z > 2.0 → 排除）
- **权重方案**：市场状态（牛/熊/震荡）动态调整因子权重
- **仓位分配**：风险平价方法，单只≤10%，单板块≤25%，最低现金≥5%

**已知局限性（必须在报告中披露）**：
- 因子 IC 基于 2026 年 2-7 月的行情测量（5 bull + 3 range，无 bear），评测期市场状态可能不同
- momentum_20 在趋势市中表现最好，震荡/下跌市中预测力可能下降
- 20 日持仓周期上，基本面因子（PE/PB/ROE）IC≈0，不适用于本策略
- 缺乏独立的验证集——因子选择和权重优化在同一批窗口上完成
