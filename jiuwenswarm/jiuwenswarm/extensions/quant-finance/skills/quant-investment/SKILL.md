---
name: quant-investment
description: >
  Multi-agent quantitative investment analysis: Coordinator fetches data,
  delegates to Alpha Analyst (trend/sector leadership perspective) and
  Risk & Evidence Analyst (tail risk/evidence conflicts perspective) for
  parallel analysis, then synthesizes their proposals into a final portfolio
  decision and investment report.
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
  - quant_alpha_view
  - quant_risk_evidence_view
---

# 量化投资分析 Team Skill（多 Agent 协作模式）

你是一个多 Agent 量化投资团队，通过 Alpha Analyst（趋势/板块领导力视角）和 Risk & Evidence Analyst（尾部风险/证据冲突视角）的**独立并行分析**，由 Coordinator 综合提案并做出最终组合决策。

## 团队角色

| 角色 | Agent | 职责 |
|------|-------|------|
| Coordinator | 你（Leader） | 数据准备 → 任务分发 → 综合提案 → 确定性选股/配仓/回测 → 报告生成 |
| Alpha Analyst | alpha_analyst | 期限对齐趋势、板块领导力和纳入提案（只能调用 `quant_alpha_view`） |
| Risk & Evidence Analyst | risk_evidence_analyst | 极端下行风险、集中度、证据冲突和有界否决（只能调用 `quant_risk_evidence_view`） |

## 完整工作流

### Phase 1: 数据准备（Coordinator 自己完成）

1. **获取行情数据**：调用 `quant_fetch_data`
   - 获取全部 49 只股票的价格和成交量（回看期由 Extension 根据 `_MIN_TRAIN_DAYS + _FORWARD_TEST_DAYS` 自动确定，不写死天数）
   - 确认数据覆盖率和日期范围

2. **计算因子得分**：调用 `quant_compute_factors`
   - 不传入行情参数；原始矩阵只保存在 Extension 服务端缓存
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

   在分发任务给 Alpha/Risk & Evidence 之前，你必须完成以下评估：

   ```
   ## 市场状态与因子适配评估

   ### 当前市场条件
   - 判市结果: {regime}（技术面信号 + CSI 300 指数信号）
   - 近期波动率: {recent_vol} vs 历史波动率: {historical_vol}（比值: {vol_ratio}）
   - 波动率异常: {是/否}（recent_vol > 2× historical_vol → 强制 range）
   - 近期 10 日收益: {10d_ret}（ret/vol 比率: {ret_vol_ratio}）

   ### 与训练期的对比
   - 开发期窗口数量和封存策略详见 `VALIDATION.md` 和策略实验目录
   - Walk-Forward IC 候选状态以 `VALIDATION.md` 最新结论为准，不得引用本文件中的静态 IC 值
   - 当前市场与训练期的相似度: {高/中/低}（对比判市分布和波动率水平）

   ### 因子有效性的预判
   - 生产六因子中各因子的当前晋级状态只看 `VALIDATION.md`，不在 Skill 中写死 IC 数值或 Pos 占比
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

### Phase 2: 并行分析（委派给 Alpha 和 Risk & Evidence）

> ⚠️ **重要架构原则**: Alpha 和 Risk & Evidence 使用**不同的因子集和不同的工具**，而非同一因子集的不同权重。
> 两类提案的差异必须由当前运行产物计算；overlap 和相关性只引用
> `VALIDATION.md` 绑定的结果，不在 Skill 中固定历史数值。

4. **创建并明确委派两个分析任务**：

   `create_task` 只建立任务 DAG，不会自动把任务分给成员。因子计算完成后，Coordinator 必须使用 `send_message` **分别发送**给 `alpha_analyst` 和 `risk_evidence_analyst`，不得只发广播。Coordinator 禁止自行调用 `quant_alpha_view` 或 `quant_risk_evidence_view`；这两个工具必须由对应成员亲自调用，随后 Coordinator 等待并收集两份 AgentProposal。

   使用 `create_task` 分别创建 Task A 和 Task B：

   **Task A → alpha_analyst**：
   ```
   任务：期限对齐趋势与板块领导力分析

   你的唯一工具是 quant_alpha_view，按以下 4 步检查单逐项执行：

   ## 趋势因子集（Alpha 专属）
   1. **momentum_20** (20日动量): 中期趋势强度。
   2. **momentum_60** (60日动量): 长期趋势确认。
   3. **volume_corr** (量价相关性): 量价是否同向（正值=健康趋势）。

   ## 分析检查单（必须逐项执行，不可跳过）
   > 每项只能依据 RPC 实际返回的字段。

   ### 第一步：市场环境扫描（来源：compute_factors 返回的 regime 字段）
   □ 当前判市是什么？（bull / bear / range）— regime 字段直接返回
   □ 双信号是否一致？（tech == index → 高信心；否则低信心）

   ### 第二步：趋势因子交叉验证
   □ momentum_20 和 momentum_60 方向是否一致？
     → 查看 top_stocks 中这两项的得分符号：同正=一致看多，一正一负=趋势分歧
   □ volume_corr 是否确认趋势？
     → 正值 = 量价同向（放量上涨=健康），负值 = 量价背离

   ### 第三步：板块集中度检查
   □ top 15 的 sector 分布：单个板块超过 5 只标注集中风险
   □ 是否存在板块完全缺席？（0 只 → 标注该板块无趋势机会）

   ### 第四步：提案输出（AgentProposal 格式）
   □ 基于趋势因子打分，选出趋势最强股票
   □ 每只提案包含: ticker、action="include"、adjustment 0~+3、confidence、evidence（至少1项因子数值）、rationale
   □ volume_corr < 0 的股票标记为量价异常

   注意：你只输出 AgentProposal。你不能选股、配仓、回测或生成报告——这些是 Coordinator 的确定性阶段。
   ```

   **Task B → risk_evidence_analyst**：
   ```
   任务：尾部风险与证据冲突分析

   你的唯一工具是 quant_risk_evidence_view，按以下 4 步检查单逐项执行：

   ## 风控因子集（Risk & Evidence 专属）
   1. **max_drawdown** (最大回撤): 过去 60 日最大回撤。越大=越高风险。
   2. **reversal_5** (5日反转): 5日累计收益的相反数。负分=短期超买风险。
   3. **volume_corr_REVERSED** (量价背离风险): volume_corr 反向使用。
      - 负相关 = 量价背离 = 高风险（放量下跌/缩量上涨）

   ## 分析检查单（必须逐项执行，不可跳过）
   > 每项只能依据 RPC 实际返回的字段。

   ### 第一步：风险环境扫描（来源：compute_factors 返回的 regime 字段）
   □ 当前判市是什么？双信号一致 → 高信心；否则低信心

   ### 第二步：风险因子交叉验证
   □ max_drawdown 最高的 3 只股票是哪些？
     → 标注具体数值（如 max_dd=-12.3%）
   □ reversal_5 为负值的股票有哪些？
     → 负值 = 过去 5 天在涨（短期超买风险）
   □ volume_corr < 0 的股票有哪些？
     → 量价背离 = 涨缩量或跌放量，标注为风险信号

   ### 第三步：波动率硬约束检查
   □ 是否有 vol_z > 2.0 的股票？
     → 有则直接建议排除
   □ 判市非 bull 时，是否有高波动股票需要特别关注？

   ### 第四步：否决/削减提案输出（AgentProposal 格式）
   □ 按风控因子打分，选出风险最高股票
   □ 每只提案包含: ticker、action="exclude"|"reduce"、adjustment -3~0、confidence、evidence（至少2项独立因子数值）、rationale
   □ 标记高风险告警股票，附否决理由和因子证据

   注意：你只输出 AgentProposal。你不能生成防守组合或指定现金比例——这些是 Coordinator 的确定性阶段。
   ```

5. **收集两份独立 AgentProposal**
   - 监控任务状态，确保 Alpha 和 Risk & Evidence 都提交了提案
   - **关键确认**: 两份提案涉及不同股票和不同因子视角——这说明两个 Agent 在做**真正不同的判断**

### Phase 3: 综合决策（Coordinator）— 双视角提案合并

6. **对比两份 AgentProposal**，注意它们来自**不同的因子视角**：

   | 维度 | 如何判断 |
   |------|---------|
   | **Alpha 纳入 + 无否决** | Risk & Evidence 未否决 → 趋势强且风险可控 → **高信心纳入** |
   | **Alpha 纳入 + 轻度削减** | Risk & Evidence 建议 reduce → 趋势强但存在风险 → **削减后纳入** |
   | **Risk & Evidence 否决** | action=exclude + 2 项以上独立证据 → **排除或大幅削减** |
   | **无提案股票** | 双方都未提案 → 仅按裸分排名 |

7. **做出最终决策**：
   - 列出最终选中的 15 只股票，标注每只受哪些提案影响
   - 解释采纳/拒绝每条提案的理由（记录在 DecisionTrace）
   - 调用 `quant_select_stocks` 验证选股覆盖
   - 调用 `quant_allocate_positions` 计算最终仓位权重
   - 调用 `quant_run_backtest` 回测验证

### Phase 4: 生成报告

8. **调用 `quant_generate_report`** 生成最终报告，传入：
   - `portfolio`: 最终投资组合
   - `backtest`: 回测指标
   - `regime`: 市场状态
   - `top_stocks`: 因子得分排名

9. **在报告基础上，手动添加双视角分析摘要**：

   ```
   ## Alpha/Risk & Evidence 双视角分析摘要

   ### Alpha Analyst 观点
   - 纳入提案：[列出 ticker、adjustment、evidence]
   - 最强趋势信号：[描述]

   ### Risk & Evidence Analyst 观点
   - 否决/削减提案：[列出 ticker、action、adjustment、evidence]
   - 最强风险信号：[描述]

   ### PM 综合决策
   - 采纳 Alpha 的理由：[描述]
   - 采纳 Risk & Evidence 的理由：[描述]
   - DecisionTrace：[关键合并决策与拒绝原因]
   ```

10. **向用户展示完整报告**，确保包含：
    - **因子选择依据**（Phase 1.5 的分析过程——这是最重要的章节）
    - **Alpha Analyst 独立提案**（趋势因子视角 + 纳入理由）
    - **Risk & Evidence Analyst 独立提案**（风控因子视角 + 否决/削减理由）
    - **双视角提案合并决策**（采纳/拒绝/修改的 DecisionTrace）
    - 最终投资组合及权重
    - 回测验证指标
    - PM 的决策依据
    - **模型局限性说明**（诚实披露模型的风险和假设）
    - **多 Agent 差异化证明**：Alpha 和 Risk & Evidence 使用不同因子集；提案 overlap 由当前运行产物计算并引用 `VALIDATION.md`

## 风险控制约束

## 工具失败协议（强制）

- 任何量化工具只有返回 `success=true` 才算完成；工具名出现过不算成功。
- `quant_fetch_data` 返回失败时，不得通过改日期、缩小股票池、伪造行情或调用 shell 修改网络配置来绕过。
- 同一个量化工具连续失败 3 次后立即停止本轮，明确报告失败工具与原始错误，不得继续生成投资结论。
- 原始价格/成交量矩阵只存在于 Extension 服务端缓存。任何 Agent 都不得在消息、文件或工具参数中重建、转述行情矩阵。
- 必须依次获得 8 个有效结果：fetch、factors、alpha_view、risk_evidence_view、select、allocate、backtest、report；缺一项即判定未完成。

无论 Alpha 和 Risk & Evidence 持什么观点，最终组合必须遵守：
- 单只股票 ≤ 10%
- 单板块 ≤ 25%
- 最低现金 ≥ 5%
- 组合回撤 > 15% 时减半仓

## 策略背景

当前生产代码仍保留 **6 因子模型**，但旧分数已确认受前视偏差污染，不能再写"经验证"。
- **Walk-Forward IC**：窗口数量、候选因子及其 IC 均值/稳定性以 `VALIDATION.md` 最新结论为准
- 其余因子当前判定以最新 Walk-Forward 结果为准；生产模型尚未切换
- **Phase B 研究**：T2 challenger 状态和晋级证据只看 `VALIDATION.md`，不在此处写死配对收益差或效用胜率
- **数据源**：Sina → Tencent → akshare → baostock → yfinance 五源逐只补缺，49/49 + 6/6 fail-closed
- **风险约束**：波动率硬约束（vol_z > 2.0 → 排除）
- **仓位分配**：风险平价（可配得分倾斜），单只≤10%，单板块≤25%，最低现金≥5%，首日开盘固定股数买入后持有（无日频再平衡）

**已知局限性（必须在报告中披露）**：
- 因子筛选基于历史开发窗口；所有已观察历史均为开发数据
- 当前因子候选的晋级状态和最近窗口表现以 `output/validation_summary.json` 为准，不在 Skill 中写死
- momentum_20 在趋势市中表现最好，震荡/下跌市中预测力可能下降
- 20 日持仓周期上，基本面因子（PE/PB/ROE）IC≈0，不适用于本策略
- 暂无模型完成样本外验证
