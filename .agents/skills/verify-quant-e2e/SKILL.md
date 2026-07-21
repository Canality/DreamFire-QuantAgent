---
name: verify-quant-e2e
description: 对量化项目执行发布前端到端验收，验证研发旁路和 JiuwenSwarm 多 Agent 正式路径，并检查真实数据覆盖、选股到配仓的数据传递、仓位约束、RPC 工具链和最终报告。用户要求测试、验收、确认功能完成、发布、提交比赛，或 Agent 准备声称 README 中的能力已实现时使用。
---

# 量化端到端验收

把“代码存在”“组件测试通过”“端到端业务通过”视为三种不同状态。不得用较低级证据证明较高级结论。

## 验收流程

1. 读取 `README.md`、`CLAUDE.md`、相关入口和本次改动，列出待验证声明。
2. 使用项目 `.venv`，不要因系统 Python 缺依赖就判定项目失败。
3. 运行研发旁路 `jiuwenswarm/scripts/run_quant_pipeline.py`，保存 stdout 和 stderr。
4. 运行 `jiuwenswarm/evaluation/run_multi_agent.py`，保存 stdout 和 stderr。设置成本护栏：相同失败工具连续调用 3 次后停止，先诊断，不允许无限重试。
5. 运行 `scripts/audit_run_artifacts.py` 审计两条路径的产物和日志。
6. 运行仓位约束边界测试；至少覆盖少板块、极端集中权重和正常六板块三类输入。
7. 对失败组件做隔离冒烟测试，但不得用隔离测试替代端到端验收。
8. 更新项目根目录 `VALIDATION.md`。它是当前可运行状态的唯一事实源；README 和其他文档只链接或摘要它，不复制长期状态。
9. 报告 Passed、Failed、Not tested 三种状态，附 commit、命令、日期、输入范围、退出码和不可变产物路径。

## 强制通过条件

研发旁路必须同时满足：

- 获取 49 只股票，覆盖 6 个板块；部分成功不能算数据获取成功。
- 数据源按缺失 ticker 逐层补齐，不得以“任意一只成功”阻止 fallback。
- 选股集合与配仓输入、最终持仓一致，或明确记录合法过滤原因。
- 单股不超过 10%，单板块不超过 25%，现金不少于 5%。约束必须在最终归一化后再次验证。
- 回测按时间推进，决策时只能使用当时可见数据；同一窗口期末选股后回看整段历史不能称为有效回测。

多 Agent 路径必须同时满足：

- Coordinator、Bull、Bear 被真实创建并各自产生可识别输出。
- ExtensionRegistry 已初始化，QuantFinance 的 8 个 RPC handler 已加载。
- 至少完成 fetch、compute、Bull、Bear、select、allocate、backtest、report 全链路。
- 工具返回 `success: false` 时任务必须失败，不得靠 LLM 重试掩盖。
- 成功判据基于业务阶段和产物字段，不得使用“有文本且有工具调用”。
- 8 个量化阶段必须全部成功；“完成任意 5 个阶段”不能算通过。
- 行情矩阵保留在 Extension 缓存中，后续工具只接收 cache key 或省略 prices。不得把全量价格数组重新送进 LLM 上下文。

## 文档一致性

更新 README 或状态表前，建立声明—实现—测试三列映射。只有对应测试在当前提交、当前环境通过，才能写“已实现/已修复”。否则写“目标设计”“局部实现”或“待验收”。

每次验收后先更新 `VALIDATION.md`，再更新 README 摘要。使用带时间戳或 session id 的日志和结果文件；不得把固定名称的旧 `pipeline_results.json` 与新日志拼成一次运行证据。

当两个入口存在重复实现时，两者都要修改和测试；更优方案是抽取共享服务，入口只负责装配。

## 审计命令

在项目根目录运行：

```powershell
python .agents/skills/verify-quant-e2e/scripts/audit_run_artifacts.py `
  --results output/pipeline_results.json `
  --direct-log output/direct_pipeline_test.log `
  --multi-log output/multi_agent_test.log
```

退出码为 0 才表示结构性验收通过。脚本不能证明无前视偏差；时间因果性仍需单独检查回测实现。

## 禁止行为

- 不得先写 README 的完成叙述，再把代码状态推定为一致。
- 不得只跑 `scoring.py` 就宣称多 Agent 正式路径通过。
- 不得用 mock 或合成数据成功掩盖真实数据链路失败。
- 不得在覆盖不足时静默降级并继续生成正式组合。
- 不得把警告、缺失字段或失败 RPC 从最终报告中省略。
