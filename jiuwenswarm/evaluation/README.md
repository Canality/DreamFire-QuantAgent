# Evaluation 目录说明

运行事实只认项目根目录 `VALIDATION.md`；本目录的历史 JSON 和实验脚本不得作为“当前已通过”证据。

## 当前入口

- `run_multi_agent.py`：JiuwenSwarm 正式多 Agent 端到端验收。
- `unified_baseline_evaluation.py`：统一口径的历史开发窗口基线评测。
- `policy_validator_prototype.py`：官方契约未明确部分的规则探针；结果仍为 provisional。
- `local_scoring.py`：本地代理评分，只用于同口径比较，不冒充官方分数。

## 研究与历史记录

- `ic_*`、`phase0_*`、`phase_b_*`：无泄漏因子和策略实验。
- `pa_*`、`analyze_pa_*`：PA_Agent 对照实验。
- 带日期或 `latest` 的 JSON 是对应实验的冻结产物；它们不是当前生产运行状态。
- `scoring.py` 仅供上述历史实验复现，不能用于生产选股或 README 成绩。

已删除不再接入当前测试或正式入口的 v2.6 smoke/verify/holdout 脚本，避免 Agent 误跑旧流程。策略结论的晋级状态见 `策略实验/README.md`。
