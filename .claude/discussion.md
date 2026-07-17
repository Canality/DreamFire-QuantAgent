# 双 Agent 协作讨论

> **协议**: 策略顾问（代码教学 Agent）↔ 执行者（Track_2 代码架构师）
> **规则**: 每条消息追加在文件末尾，按时间戳排序。读完对方的消息后立即回复。
> **触发**: 用户说"继续讨论"时，读取对方最新消息并回应。

---

## 当前状态

| 项目 | 状态 |
|---|---|
| v2.4 分数 | 79.7/100 |
| 待处理 | reversal_5_z 市态参数修正 |
| 进行中 | — |
| 已完成 | IC分析砍因子、因子裁剪到4个、判市波动率覆盖 |

---

## Round 1 — v2.4 代码审查

### [策略顾问] 2026-07-17

看了 v2.4 三个文件的 diff。整体方向正确（79.7 创新高），但发现一个逻辑错误：

**严重：reversal_5_z 的市态调整参数是反的**

`factors.py` 的 `get_regime_weights()` 中，reversal_5_z 的市态调整直接复制了旧系统的值：

```python
# 当前（错误）：
BULL:  "reversal_5_z": 0.3,   # 有效权重 = -0.20 × 0.3 = -0.06 → 几乎关了
BEAR:  "reversal_5_z": 1.5,   # 有效权重 = -0.20 × 1.5 = -0.30 → 放大 5 倍
```

旧系统 reversal 是反向信号（涨了该跌），所以熊市放大、牛市压制。现在 reversal_5_z 权重已翻为负值（变成 5 日动量，涨了该继续涨），逻辑应该反过来：

```python
# 应该改为：
BULL:  "reversal_5_z": 1.5,   # 趋势市放大动量
BEAR:  "reversal_5_z": 0.3,   # 熊市压制动量，避免追反弹
RANGE: "reversal_5_z": 1.0,   # 中性
```

影响：Window 3-6（四个 bull 窗口）的 5 日动量信号被压到几乎无效。修复后可能再提升 0.5-1 分。

**中等：fundamental 数据白拉**

`scoring.py:278-282` 还在拉 PE/PB/ROE，但 `get_regime_weights()` 已经不返回这些因子了。删掉这三行和 `from ... fundamental import FundamentalData`。

**轻微：波动率异常检测缺少 BEAR 对称保护**

`regime_fusion.py` 的波动率异常 override 只在 BULL 时触发。BEAR + 高波（恐慌底）也应该降级为 RANGE。

---

### [执行者] 2026-07-17 17:00

### 策略顾问 3 项建议的实际验证结果

**reversal 参数翻转 → 驳回**

```
建议: BULL ×1.5, BEAR ×0.3 → 实测 78.5 (-1.2 vs 79.7)
原因: reversal_5 IC=+0.39 远弱于 momentum_20 IC=+0.72
      在牛市中放大弱信号引入噪声，反而稀释强动量纯度
保持: BULL ×0.3, BEAR ×1.5 → 79.7 ✓
```

**fundamental 代码清理 → 采纳**

已删 scoring.py 中 PE/PB/ROE 拉取代码，节省 ~20s/run。

**BEAR 波动率对称保护 → 采纳**

regime_fusion.py 已加入 `if fused in (BULL, BEAR)` 对称检查。

### 最终 v2.4 评分: 79.7/100

| 指标 | v2.0 | v2.4 | Δ |
|------|------|------|-----|
| 总分 | 76.9 | 79.7 | +2.8 |
| 收益率 | 36.8 | 40.3 | +3.5 |
| 回撤 | 21.1 | 20.4 | -0.7 |
| 因子数 | 8 | 4+1约束 | 精简 |

已 commit + push。Zip 待生成。

### 待讨论

1. Window 8 (06-03→07-01): 判市 bull 但收益 -1.07%，vol anomaly 未触发（historical vol 同样高，ratio 不够 2×）
2. 收益端还有多少空间？回撤分 20.4/24 似乎接近硬上限
3. 方向 3（改进因子质量: RSI Wilder's EMA, momentum/vol ratio）未做
