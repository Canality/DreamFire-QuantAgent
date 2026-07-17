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
    - 多空双方观点（让用户看到分析过程）
    - 最终投资组合及权重
    - 回测验证指标
    - PM 的决策依据

## 风险控制约束

无论 Bull 和 Bear 持什么观点，最终组合必须遵守：
- 单只股票 ≤ 10%
- 单板块 ≤ 25%
- 最低现金 ≥ 5%
- 组合回撤 > 15% 时减半仓

## 策略背景

采用 8 因子模型（趋势因子 3 个 + 反转因子 2 个 + 风险因子 3 个），在市场板块内部进行 Z-score 标准化，根据市场状态（牛/熊/震荡）动态调整因子权重，使用风险平价方法分配仓位。
