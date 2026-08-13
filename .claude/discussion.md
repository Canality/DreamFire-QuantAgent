# 当前协作交接

## [Codex → Claude] 2026-08-13：WP1-E4-R1 contract v2 implementation ACCEPT / VERIFIED

`ACCEPT / VERIFIED`. Codex has completed the independent implementation review of the WP1-E4-R1 contract v2 bounded implementation.

### Review conclusion

- Contract v2 is correctly implemented within the frozen whitelist (`jiuwenswarm/evaluation/dynamic_selector_replay.py`, `jiuwenswarm/tests/unit_tests/quant/test_dynamic_selector_replay.py`, `coordination/active/WP1-E4-R1.md`):
  - `_blend_frames` raises on asymmetric post-filter eligible-set exclusions.
  - `decision_composition` records per-decision `eligible_universe` / `excluded_stocks` and `run_selector_replay` binds them into each window payload, so tampering either list fails `verify_selector_payload`.
  - Shared post-filter exclusions are accepted; the real archive records `excluded_stocks=['sh.601688','sh.603986']` with a 47-ticker eligible universe.
  - A0 == accepted E2C production portfolio is asserted per window.
  - The E2C oracle is the unique literal `load_e2c_evidence(regenerate=True)`; AST static regression `test_e2c_oracle_is_literal_regenerate_true_only` confirms no artifact-read switch.
- Independent reruns pass: focused pytest **42 passed**, adjacent suite **109 passed**, ruff and py_compile exit 0.
- `git diff --check` fails only on the pre-existing Codex-owned `.claude/discussion.md` blank-line-at-EOF.
- `scope-check WP1-E4-R1` fails because the 10:09:51 baseline is stale: 13 external files modified after the freeze (Codex/bridge/user state such as `.claude/discussion.md`, bridge hooks, `DEVELOPMENT_PLAN.md`, `README.md`, `VALIDATION.md`, `history/*`, `EXTDATA-AKSHARE-R1.md`, etc.). The three allowed WP1-E4-R1 files are **not** in violations.

### Required follow-up

- Before any submission or production promotion, a fresh Codex planning phase must re-freeze the baseline to reconcile the external workspace state. This acceptance does not unblock formal/direct/RPC/E2E or any `SubmissionContract` change.

### Evidence level

- `LOCAL_IMPLEMENTED / RESEARCH_ONLY` only. No `PATH_PASSED` or `BUSINESS_PASSED` claim.

### 无需回复

- WP1-E4-R1 is accepted and verified. The next work item remains per the current priority: external data exploration (`EXTDATA-AKSHARE-R1.md`) is still `DRAFT` and must wait for a fresh Codex planning phase before starting.

---

## [Codex → Claude] 2026-08-13：恢复 WP1-E4-R1 有界实现，外部数据探索排至其后

`READY / IMPLEMENT`。用户已确认开发优先级：先完成 WP1-E4-R1 完整动态选择器回放，
验收关闭后再启动零成本外部数据（AkShare）可行性研究。当前 WP1-E4-R1 的 contract v2
与 fresh baseline 已冻结；外部数据任务已草拟为 `coordination/active/EXTDATA-AKSHARE-R1.md`，
状态 `DRAFT`，等 WP1-E4-R1 关闭后再启动。

### 当前冻结状态

1. **允许改动的文件（精确白名单）**：
   - `jiuwenswarm/evaluation/dynamic_selector_replay.py`
   - `jiuwenswarm/tests/unit_tests/quant/test_dynamic_selector_replay.py`
   - `coordination/active/WP1-E4-R1.md`

2. **Contract v2 已冻结**：
   - 决策时 source 必须精确覆盖官方 49 股票/6 板块，任何 source 覆盖丢失失败关闭。
   - post-`filter_high_volatility` 后的 slot eligible sets 必须完全相同；exclusions 必须记录并绑定 hash。
   - shared post-filter exclusion 不视为 source 覆盖丢失。
   - A0 必须与已接受的 E2C production portfolio 保持字节/身份等价。
   - 研究专用；不得改动 production/direct/formal/RPC/E2E。

3. **后续任务已草拟**：`coordination/active/EXTDATA-AKSHARE-R1.md`（状态 `DRAFT`），
   等 WP1-E4-R1 关闭后再由 Codex 建立契约、白名单和基线。

### 实现要求

严格使用 `.agents/skills/bounded-code-implementer/SKILL.md`。在 frozen whitelist 内完成
WP1-E4-R1 实现并满足 contract v2：

1. 移除/关闭所有 reachable 的 `regenerate=False` 或 artifact-read oracle；
   `load_e2c_evidence(regenerate=True)` 必须是唯一模式。
2. 实现 post-filter identical-eligible-set gate：两个 slot 的 eligible ticker 集合必须相等，
   否则失败关闭；将 excluded tickers 和 eligible identities 记录到每决策日的 payload 并绑定 hash。
3. A0 与 accepted E2C production portfolio 逐窗等价断言。
4. 保留 deterministic E2C 12-window 清单、E3 create-once bundle、A0/A1/A2 独立评估、
   Bootstrap 20260804/2000/3、资源门 1800s/2048MB。
5. 负向测试覆盖：source 丢失 49/6、slot exclusion 不对称、excluded/eligible identity 篡改、
   A0 不等价、hash drift、未来数据泄漏、one-shot 调用次数、Bootstrap 绑定、资源验证失败、
   production import 隔离。

完成后运行 focused pytest、相邻测试、Ruff、py_compile、`git diff --check`、
`scope-check WP1-E4-R1`；写 `implementation.json` 与 `claude_reply.md`，状态只写 `IMPLEMENTED`，
然后停止交 Codex 独立审查。

### 外部数据任务后置说明

WP1-E4-R1 关闭前不要启动 `EXTDATA-AKSHARE-R1`。该任务当前仅作路线占位，契约、白名单和
基线将在 WP1-E4-R1 验收后由 Codex 建立。

### 需要回复

收到本 handoff 后确认优先级，开始 bounded 实现；实现完成后更新 outbox 并停止，等待 Codex 审查。
