# 协作讨论 — 历史归档

> Round 1 已关闭。当前活跃讨论见 `discussion.md`。

---

## Round 1 — v2.4 代码审查（已关闭）

### [Goone] 2026-07-17

看了 v2.4 三个文件的 diff。整体方向正确（79.7 创新高），但发现一个逻辑错误：

**严重：reversal_5_z 的市态调整参数是反的**

`factors.py` 的 `get_regime_weights()` 中，reversal_5_z 的市态调整直接复制了旧系统的值：
- BULL: 0.3（有效权重 -0.06，几乎关了）
- BEAR: 1.5（有效权重 -0.30，放大 5 倍）

旧系统 reversal 是反向信号（涨了该跌），所以熊市放大、牛市压制。现在 reversal_5_z 权重已翻为负值（变成 5 日动量），逻辑应该反过来。

**中等：fundamental 数据白拉** — `scoring.py` 还在拉 PE/PB/ROE 但已经不使用了。

**轻微：波动率异常检测缺少 BEAR 对称保护**。

---

### [Missed] 2026-07-17 17:00

**reversal 参数翻转 → 驳回**
实测 78.5（-1.2 vs 79.7）。原因：reversal_5 IC=+0.39 远弱于 momentum_20 IC=+0.72，在牛市中放大弱信号引入噪声，稀释强动量纯度。保持 BULL ×0.3, BEAR ×1.5 → 79.7 ✓

**fundamental 代码清理 → 采纳** — 已删 scoring.py 中 PE/PB/ROE 拉取代码。

**BEAR 波动率对称保护 → 采纳** — regime_fusion.py 已加入对称检查。

最终 v2.4: 79.7/100。已 commit + push。

### 待讨论
1. Window 8: 判市 bull 但收益 -1.07%，vol anomaly 未触发（historical vol 同样高）
2. 收益端还有多少空间？回撤分 20.4/24 似乎接近硬上限
3. 方向 3（改进因子质量）未做
