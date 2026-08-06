---
id: WP1D-RESOURCE-BENCH-0806
title: Cross-platform formal resource accounting and three-run benchmark
status: CLOSED
risk: HIGH
owner: Codex
created_at: 2026-08-06T12:33:33+08:00
updated_at: 2026-08-06T13:08:19+08:00
allowed_files:
  - coordination/active/WP1D-RESOURCE-BENCH-0806.md
  - jiuwenswarm/evaluation/run_multi_agent.py
  - jiuwenswarm/evaluation/aggregate_formal_resources.py
  - jiuwenswarm/jiuwenswarm/quant/reporting/resource_meter.py
  - jiuwenswarm/tests/unit_tests/quant/test_resource_meter.py
  - jiuwenswarm/tests/unit_tests/quant/test_run_multi_agent_validator.py
  - jiuwenswarm/tests/unit_tests/quant/test_formal_resource_benchmark.py
acceptance:
  - A pure aggregator verifies three immutable same-snapshot formal summaries and computes P95 duration, peak RSS, max concurrency and token-reduction gates without network or LLM calls.
  - Formal runtime records eight phase timings, role token usage, tool-schema token bytes/tokens, process-tree current/peak RSS and observed concurrency, leaving unavailable values null.
  - Focused positive/tamper/missing/cross-platform tests, Ruff, pycompile, frozen scope-check and diff-check pass; no three-run BUSINESS_PASSED claim is made on Mac.
---

## Goal

Measure per-stage, per-role and tool-schema token costs, elapsed time, process-tree peak RSS and real concurrency; aggregate exactly three same-snapshot formal summaries without inventing absent measurements.

## Non-goals

- Do not run three network/model-backed formal sessions on Mac or claim their
  acceptance before Windows supplies three hash-bound same-snapshot summaries.
- Do not infer token attribution, process memory or concurrency from timestamps;
  unavailable measurements remain null and fail their aggregate gates.
- Do not add tool-schema diagnostic tokens to Provider-reported input usage.
- Do not change strategy, roles, eight RPC order, competition window or session
  teardown behavior.

## Invariants

- Preserve AGENTS.md and project safety contracts.

## Locate brief

- Scout validated the formal seams at confidence 0.97. Instrument monotonic RPC
  timings and active-call concurrency at `audited_call_rpc`, sample root plus
  recursive child RSS across Runner lifetime, preserve field-wise optional role
  usage, and serialize the actual formal ToolCards with named tokenizer/null.
- Add a pure offline aggregator that accepts exactly three distinct raw-summary
  hashes, rebuilds the LIVE_TRACE, requires one market/snapshot/manifest identity,
  uses nearest-rank P95 (the maximum for n=3), and fails any missing metric gate.

## Implementation evidence

- Formal summaries now include monotonic duration for each exact RPC stage,
  exact-role Provider usage with null-preserving totals, canonical accounting
  for the eight actual quant ToolCards, observed RPC concurrency, and sampled
  root-plus-recursive-child current/peak RSS.
- `aggregate_formal_resources.py` reads exactly three caller-hash-bound distinct
  summaries, rebuilds each LIVE_TRACE, verifies immutable same-snapshot and
  same-schema identity, and evaluates nearest-rank P95, RSS, concurrency and
  ≥50% input-token-reduction gates without network/model imports.
- 32/32 focused tests, Ruff, pycompile, scope-check and `git diff --check`
  passed. The broad quant suite reached 574 passed / 1 skipped; its same 10
  pre-existing failures require the absent ignored historical
  `WP1B-EVALUATION-0804/review.json` and were not bypassed or synthesized.

## Review evidence

- Independent Critic first returned `REJECT` with one P1 partial per-event token
  undercount and one P2 self-reported ToolCard identity gap. Both counterexamples
  now have focused regressions and are closed.
- Closure Critic returned `ACCEPT`, P0/P1/P2/P3=`0/0/0/0`; accepted
  implementation diff SHA-256 is
  `ad6b7591cc672857fef13015bbc35efef81ec7d6a152978ca5200a1479974ad9`.
  Final mutable `review.json` and delivery checksums are recorded outside this
  tracked contract.

## Progress

- 2026-08-06T12:33:33+08:00 `DRAFT`: Task created.
- 2026-08-06T12:39:00+08:00 `LOCATED`: Scout location validated; Planner
  accepted the seven-file runtime/measurement/aggregator boundary.
- 2026-08-06T12:40:51+08:00 `READY`: Baseline frozen; implementation may start.
- 2026-08-06T12:51:17+08:00 `IMPLEMENTED`: Builder added cross-platform formal resource accounting and a hash-bound exactly-three-run offline aggregator; focused tests, static checks and scope-check passed.
- 2026-08-06T13:03:00+08:00 `REVIEWED/REJECT`: Independent Critic found
  one P1 partial-usage undercount and one P2 self-reported ToolCard identity gap.
- 2026-08-06T13:06:20+08:00 `IMPLEMENTED`: Missing usage in any role event now
  invalidates that role/field total; summaries carry the canonical eight-card
  projection and the aggregator recomputes its byte count/hash and role boundary.
- 2026-08-06T13:08:19+08:00 `REVIEWED`: Closure Critic ACCEPT; prior P1/P2 counterexamples reproduced as closed; P0-P3 all zero.
- 2026-08-06T13:08:19+08:00 `VERIFIED`: Planner reproduced 32 focused passes, Ruff, pycompile, frozen scope-check and diff-check; broad suite only retains the known absent historical WP1-B artifact dependency.
- 2026-08-06T13:08:19+08:00 `CLOSED`: Resource instrumentation and offline three-run aggregation closed as LOCAL_IMPLEMENTED; actual three formal Windows runs remain explicitly pending and BUSINESS_PASSED is false.
