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
   - 策略逻辑改动后运行 `scoring.py`；Agent、Extension、数据源、入口或报告链路改动后，还必须使用 `verify-quant-e2e` 验证两条真实路径
   - 把“组件测试通过”“离线回测通过”“真实数据端到端通过”分别记录，禁止互相替代
   - 数据不足 49 只或 6 个板块时 fail closed，不生成正式评分或组合
4. **分析结果**：
   - 收益率（累计/年化）
   - 风险指标（最大回撤、波动率、夏普比率、Calmar比率）
   - 与基线策略对比
   - 各因子贡献度分析
5. **记录**：将实验结果追加到 `策略实验/` 目录下的实验记录表
6. **更新 MEMORY.md**：如果结论重要，用 `/memory` 记录
7. **教学**：向Canaan解释本次实验的关键发现和涉及的量化概念

## 完成标准

- 先写假设和验收阈值，再运行实验；不得看到结果后改写成功标准。
- 报告命令、日期范围、数据覆盖率、退出码和原始产物路径。
- README/CLAUDE.md 中新增或变更的能力声明必须有当前提交产生的测试证据。
- 未通过的实验也必须记录为失败，不得只保留最优窗口或成功输出。

每次实验的结论驱动下一次 `/plan`。
