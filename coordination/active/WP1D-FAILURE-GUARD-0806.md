---
id: WP1D-FAILURE-GUARD-0806
title: Prove the three-identical-failure stop contract
status: CLOSED
risk: HIGH
owner: Codex
created_at: 2026-08-06T13:49:00+08:00
updated_at: 2026-08-06T14:10:30+08:00
allowed_files:
  - coordination/active/WP1D-FAILURE-GUARD-0806.md
  - jiuwenswarm/jiuwenswarm/quant/orchestration_guard.py
  - jiuwenswarm/tests/unit_tests/quant/test_orchestration_guard.py
  - jiuwenswarm/evaluation/run_multi_agent.py
  - jiuwenswarm/tests/unit_tests/quant/test_run_multi_agent_validator.py
acceptance:
  - Read-only Scout distinguishes formal first-failure closure from the three-identical-stream-call guard; Planner freezes the smallest test-only or code boundary; deterministic tests prove the third identical failed call stops with a diagnostic and cannot be reset without real quant progress; scope-check, diff-check and independent review pass without weakening the formal first-failure contract.
---

## Goal

Close the final local WP1-D acceptance ambiguity by proving that three identical
failed tool calls stop with a machine-readable diagnostic, while formal Quant
RPC failures continue to fail closed on the first unsuccessful payload.

## Non-goals

- Do not permit retries of the deterministic eight formal Quant RPCs.
- Do not change strategy, roles, RPC sequence, Provider, resource gates or
  production pointers.
- Do not reinterpret varying arguments as an identical call unless the current
  identity contract explicitly does so.

## Invariants

- Preserve AGENTS.md and the deterministic replay/teardown contracts.
- A stronger first-failure boundary must not be weakened merely to reach a
  counter value of three.

## Locate brief

- Validated Scout artifact confidence `0.99`, SHA-256
  `1fabd42c8485305d51dcad5aebfb49ceff95693dc45922f1eadd2a61e1348e4a`.
- `ToolProgressGuard` currently counts a complete name/arguments/result
  signature. Varying arguments or error text therefore evades the literal
  same-tool failure rule. Add failure outcome state to this pure guard and its
  focused tests only; `run_multi_agent.py` already consumes `record_tool_call`
  and serializes `as_dict`, so it remains read-only.
- Freeze `same tool` as the normalized non-empty tool name. Three failed calls
  are consecutive only when no successful or differently named tool call
  intervenes. Arguments and volatile error text do not change tool identity.
- A failed result is explicit `failed=true`, non-empty `error`, a mapping with
  `success=false`, or a mapping/string-JSON with a terminal failed/error status.
  Ambiguous free text is not guessed as failure. The third failure emits stable
  reason code, tool name, count and bounded last-error text.
- Formal Quant RPC payload/exception validation remains fail-closed on its
  first failed attempt. This generic guard is a retry/churn ceiling, not
  permission to repeat deterministic stages.
- Critic counterexample amended the initial three-file scope: locked
  OpenJiuwen emits terminal outcomes as separate `tool_result` events, so the
  runtime adapter and its focused integration test must be writable. The
  original baseline already hashed both files; only the allowed list expands.

## Implementation evidence

- `ToolProgressGuard` now recognizes only explicit structured failures and
  counts consecutive failures by non-empty tool name, independent of changing
  arguments and volatile error text. A success, ambiguous result or differently
  named tool starts a new sequence.
- The exact third failure trips stable reason code
  `CONSECUTIVE_TOOL_FAILURE_LIMIT`, name, count and bounded last-error detail.
  After any guard trips, later calls or quant-progress events cannot mutate the
  diagnostic.
- The formal adapter now keeps call-id/name bindings and feeds separate
  terminal `tool_result` events into the failure sequence without double
  counting them as new calls for existing churn budgets. Missing result names
  resolve from their prior call id; completed bindings are removed.
- Existing identical-call, management-no-progress and global-no-progress
  budgets remain independent. Formal Quant RPC first-failure invalidation is
  unchanged.
- Focused guard plus formal-validator regression: 34 passed. Ruff, pycompile,
  frozen scope-check and diff-check pass locally; import-time dependency
  ResourceWarnings remain visible and are not hidden.

## Review evidence

- Independent Critic final verdict `ACCEPT`; P0/P1/P2/P3 are empty on frozen
  diff `5f6af7e23e860c9c4dbb06756bfd01b6b9afd1d1acc98b1edf59c7aa727d41f4`.
- Review closed four findings across two rounds: formal result dead path,
  whitespace identity bypass, duplicate/mismatched result replay and incomplete
  amended baseline files. Final focused/adjacent result is 35 passed.
- This closes the local code contract only. Windows formal runs must still
  demonstrate the guard and diagnostics on the locked runtime.

## Progress

- 2026-08-06T13:49:00+08:00 `DRAFT`: Task created for the final WP1-D local acceptance ambiguity.
- 2026-08-06T13:53:30+08:00 `LOCATED`: Scout location validated at confidence
  0.99; Planner froze a three-file pure-guard/test boundary and retained the
  stronger first-failure formal RPC verdict.
- 2026-08-06T13:54:18+08:00 `READY`: Baseline frozen; implementation may start.
- 2026-08-06T13:56:00+08:00 `IMPLEMENTED`: Added structured same-tool failure
  sequencing and immutable third-failure diagnostics; 31 focused/adjacent tests
  plus Ruff and pycompile pass without modifying the formal runtime caller.
- 2026-08-06T13:58:30+08:00 `REVIEWED/REJECT`: Independent Critic proved the
  guard was dead on the real formal stream because `tool_result` is a separate
  event rejected by `_extract_tool_call`; whitespace tool-name variants also
  bypassed identity normalization.
- 2026-08-06T13:59:00+08:00 `LOCATED/READY`: Planner accepted the reproducible
  scope challenge, expanded the whitelist only to the runtime event adapter and
  its validator test, and retained all original baseline file hashes.
- 2026-08-06T14:03:00+08:00 `IMPLEMENTED`: Bound separate OpenJiuwen result
  events back to call id/name, normalized whitespace, avoided churn-budget
  double counting and added split-event success/failure regressions; 34 tests
  plus Ruff and pycompile pass.
- 2026-08-06T14:05:30+08:00 `REVIEWED/REJECT`: Closure review found result
  frames were not required to consume one unique pending call id, allowing
  duplicate or mismatched frames to fabricate a third failure. It also found
  the scope amendment lacked baseline-file copies for the two added paths.
- 2026-08-06T14:07:30+08:00 `IMPLEMENTED`: Result frames now require exactly
  one known pending call id and matching name; duplicate, unknown, missing-id,
  mismatch and stream-end pending results fail closed. Planner restored the two
  original 2a04f49 baseline-file bytes for an applicable minimal diff; 35 tests
  pass.
- 2026-08-06T13:54:18+08:00 `READY`: Baseline frozen; implementation may start.
- 2026-08-06T14:10:00+08:00 `REVIEWED`: Independent Critic accepted the
  repaired five-file diff with P0-P3 empty after validating unique result
  binding, unchanged churn budgets and complete scope-amendment baselines.
- 2026-08-06T14:10:30+08:00 `VERIFIED/CLOSED`: Planner verified 35 tests,
  Ruff, pycompile, exact scope, applicable diff and retained Windows formal
  gate; no push and no production/strategy change.
