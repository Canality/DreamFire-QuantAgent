# Claude Code：Track 2 执行手册

## 协作关系

- Missed / Claude Code：实现、测试、复现和记录。
- Goone：策略与框架建议。
- Codex：第三方架构审查、反例测试和最终验收。
- 当前交接通道：`.claude/discussion.md`。
- 唯一运行事实源：`VALIDATION.md`。

每次工作先读这四个文件：`CLAUDE.md`、`AGENTS.md`、`.claude/discussion.md`、`VALIDATION.md`。

## 不可违反的原则

1. 不把设计目标、代码存在、单测通过和业务完成混写。
2. 不使用旧 `scoring.py` 的污染分数判断策略。
3. 不因 direct 通过就声称 JiuwenSwarm 正式路径通过，反之亦然。
4. 不把 LLM 文本、工具名出现或“已完成”话术当成 8/8 证据。
5. 不让价格矩阵进入 LLM 上下文。
6. 不信任 LLM 回传的 scores、tickers、weights、portfolio 或 backtest；后续阶段只能读取 Extension 缓存的前序确定性结果。
7. 不用占位 hash、伪来源、假 token 或 0 填补未知值。
8. 不在主办方未澄清时把 `SubmissionContract` 改成 `CONFIRMED`。
9. 不自动 push、tag、打 zip；这些动作需要用户明确授权。

## 当前实现

```
quant-investment Team Skill
├── Coordinator：fetch → factors → select → allocate → backtest → report
├── Bull Analyst：quant_bull_view
└── Bear Analyst：quant_bear_view
```

- 五源逐只补缺：Sina → Tencent → akshare → baostock → yfinance。
- 官方 Excel 当前实表为 49 家；业务代码从 contract/stock_pool 读取数量。
- direct/formal 共用量化、报告和 SnapshotWriter 服务。
- 组合约束：15 只、单股 ≤10%、板块 ≤25%、现金 ≥5%。
- 报告候选：49 份公司报告、组合、行情证据和正式资源日志。
- 当前完整状态、最新 session 和阻断项只看 `VALIDATION.md`。

## 开发闭环

1. 在 discussion 写清假设、影响入口和验收判据。
2. 搜索全部调用入口，优先抽共享服务，不复制业务逻辑。
3. 先补负向测试，再实现修复。
4. 运行目标 pytest 与 ruff。
5. 依次跑 direct、formal、独立 E2E audit。
6. 先更新 `VALIDATION.md`，再更新 README/discussion。
7. 检查旧候选、日志、缓存和临时文件；只保留一套当前证据。
8. 用户要求时再 commit；没有授权不 push。

## 常用命令

```powershell
cd jiuwenswarm
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
.\.venv\Scripts\python.exe -m pytest -o addopts='' tests/unit_tests/quant -q
.\.venv\Scripts\python.exe -m ruff check evaluation/run_multi_agent.py jiuwenswarm/quant/reporting jiuwenswarm/extensions/quant-finance/extension.py scripts/run_quant_pipeline.py tests/unit_tests/quant
.\.venv\Scripts\python.exe scripts/run_quant_pipeline.py
.\.venv\Scripts\python.exe -u evaluation/run_multi_agent.py
```

发布前审计命令和当前产物名从 `VALIDATION.md` 复制，不要复用历史 session。

## 当前工作重点

1. 正式路径 input token 约 94.5 万：用摘要、按需检索和更短系统提示降本。
2. 一次复跑曾停在 4/8：保留 150 秒无进展 fail-closed，并提高确定性编排。
3. 报告仍偏行情/技术面：下一 Provider 优先做交易所公告，必须 point-in-time、原文归档、URL/hash、双路径接入。
4. T2 仍是开发候选，未完成样本外验证前不得切生产。
5. 49/50、现金口径、报告权重需要主办方书面澄清。
