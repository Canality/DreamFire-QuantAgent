---
name: "source-command-experiment"
description: "执行一轮完整的策略实验闭环"
---

# source-command-experiment

Use this skill when the user asks to run the migrated source command `experiment`.

## Command Template

请执行一轮完整的策略实验：

1. **确认策略**：读取上一轮 `/plan` 的输出（或当前待验证的假设）
2. **实现代码**：编写 Agent Skills 和策略代码
3. **运行回测**：执行回测，收集数据
4. **分析结果**：
   - 收益率（累计/年化）
   - 风险指标（最大回撤、波动率、夏普比率、Calmar比率）
   - 与基线策略对比
   - 各因子贡献度分析
5. **记录**：将实验结果追加到 `策略实验/` 目录下的实验记录表
6. **更新 MEMORY.md**：如果结论重要，用 `/memory` 记录
7. **教学**：向罗迦南解释本次实验的关键发现和涉及的量化概念

每次实验的结论驱动下一次 `/plan`。
