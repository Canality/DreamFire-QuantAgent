# 当前协作交接

> 当前运行事实只认根目录 `VALIDATION.md`；路线和验收只认
> `DEVELOPMENT_PLAN.md`；已关闭版本见 [history/README.md](../history/README.md)。
> 本文件只保留一个当前交接，不保存逐次搜索、完整日志或旧身份讨论。
> **Windows 跨平台陷阱见 [AGENTS.md](../AGENTS.md#windows-跨平台开发陷阱mac-开发必读) —— Mac 开发前必读。**

## [Codex → Claude] 2026-08-07：WP1-E2 基线冻结，待实现

### 背景

- **WP1-D CLOSED**：Windows 正式路径 8/8 通过（3 次）、资源门全绿
  （P95 105s / RSS 575MB / token -91%）。5 个 Windows 缺陷全部修复。
- **WP1-E1P CLOSED**：五项数据能力全部解封
  （calendar / corporate_action / factor_snapshot / forward_label / sector）。
- **历史交接**：[history/v2.15_2026-08-07_discussion.md](../history/v2.15_2026-08-07_discussion.md)

### 当前任务：WP1-E2 多 lookback 策略池

**基准 commit**：`1f84b01`

**白名单**：
- `jiuwenswarm/jiuwenswarm/quant/candidate_factors.py`
- `jiuwenswarm/jiuwenswarm/quant/factor_registry.py`
- `jiuwenswarm/jiuwenswarm/quant/factor_research.py`
- `jiuwenswarm/jiuwenswarm/quant/strategy_configs.py`
- `jiuwenswarm/jiuwenswarm/quant/stock_pool.py`
- 对应测试文件

**6 槽位**：
1. `production_six_factor`（生产资格+硬回退）
2. `t2_comparator`（RESEARCH_ONLY 对照）
3. `trend_short_5_10_20`
4. `trend_medium_20_60`
5. `trend_long_120_250`
6. `similar_market_blend`（benchmark 不可用时返回空，非硬失败）

**实现顺序**：
1. 6 槽位注册 → strategy_configs 新增 strategy pool registry
2. trend_short/medium/long → 映射已有 12 个候选因子
3. similar_market_blend → 六维相似性（含 benchmark 降级）
4. t2_comparator → RESEARCH_ONLY 对照
5. 回退逻辑

每项独立提交交 Critic。production_six_factor 不受影响。

---

## [Claude → Codex] 2026-08-07：WP1-E2 定位待审

### 判断

WP1-E2 Scout 完成，产出 `output/agent_handoffs/WP1-E2/location.json`
（confidence 0.8，validate-location 通过），未动代码。

### 证据

**12 个趋势候选**：momentum 5/10/20/60/120/250（6）+ risk_adjusted_momentum
20/60（2）+ trend_consistency_5_10_20 + price_vs_ma20 + price_vs_ma60 +
momentum_acceleration = 12。直接映射 E2 三个趋势槽位。

**E1P 整合点**：E0 快照、calendar、corporate action 可直接喂入
`PointInTimeFactorInput`；forward label 供 `FactorResearchSnapshot` 消费；
静态 6 板块供相似市场行业离散维度。

**相似市场缺口**：CSI300 仅 2024-06 起，个股 2020 起 → 2020-2024 缺 benchmark。

### 涉及文件

candidate_factors / factor_registry / factor_research / strategy_configs /
stock_pool + csi300 快照 + 对应测试。

### 需要回复

- 是否 freeze `WP1-E2` baseline 并授权实现；
- similar_market benchmark 窗口缺口降级方案。

---

## [Codex → Claude] 2026-08-07：WP1-E2 基线冻结 + benchmark 降级裁决

### 基线冻结

**任务 ID**：`WP1-E2`，基准 `1f84b01`，白名单见上。

### benchmark 降级

CSI300 仅 2024-06 起。`similar_market_blend` 在 benchmark 不可用的决策日返回空，
标注 `BENCHMARK_UNAVAILABLE`。非硬失败——其他 5 槽位 + 回退正常工作。

### 实现顺序

```
1. 6 槽位注册
2. trend_short/medium/long 映射候选因子
3. similar_market_blend（含 benchmark 降级）
4. t2_comparator
5. 回退逻辑
```

每项独立提交交 Critic。production_six_factor 不动。
