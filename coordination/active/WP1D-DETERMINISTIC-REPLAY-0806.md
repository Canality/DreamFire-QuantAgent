---
id: WP1D-DETERMINISTIC-REPLAY-0806
title: Deterministic eight-stage state machine and no-LLM replay
status: CLOSED
risk: HIGH
owner: Codex
created_at: 2026-08-06T11:48:42+08:00
updated_at: 2026-08-06T12:31:00+08:00
allowed_files:
  - coordination/active/WP1D-DETERMINISTIC-REPLAY-0806.md
  - jiuwenswarm/evaluation/run_multi_agent.py
  - jiuwenswarm/evaluation/replay_quant_trace.py
  - jiuwenswarm/jiuwenswarm/extensions/quant-finance/extension.py
  - jiuwenswarm/jiuwenswarm/quant/phase_state.py
  - jiuwenswarm/jiuwenswarm/quant/reporting/snapshot_writer.py
  - jiuwenswarm/tests/unit_tests/quant/test_run_multi_agent_validator.py
  - jiuwenswarm/tests/unit_tests/quant/test_extension_cache_pipeline.py
  - jiuwenswarm/tests/unit_tests/quant/test_deterministic_replay.py
acceptance:
  - The exact fetch/factors/alpha_view/risk_evidence_view/select/allocate/backtest/report order is server-validated and rejects missing, duplicate, reordered or stale-snapshot transitions.
  - A replay CLI consumes an immutable local snapshot/trace, performs 20 no-network/no-LLM runs, and emits identical per-run and aggregate hashes or fails closed.
  - Production strategy, role count, eight RPC names and official window remain unchanged.
  - Focused state/replay tests, a real 20-run fixture replay, Ruff, pycompile, scope-check and diff-check pass.
---

## Goal

Make the eight formal quant stages an explicit order-checked deterministic state machine and prove identical output hashes across 20 offline no-LLM replays of one immutable snapshot.

## Non-goals

- Do not change production strategy, official window, role count or RPC names.
- Do not import openJiuwen, Runner, network Providers or model clients in the
  replay CLI.
- Offline replay is not a fresh formal run and cannot satisfy the three-run
  Windows stability gate.

## Invariants

- Preserve AGENTS.md and project safety contracts.

## Locate brief

- Scout must locate the current unordered formal validator, Extension phase
  cache/epoch boundary, canonical full-market snapshot hash implementation and
  focused tests. Prefer one shared pure state module plus an isolated replay
  CLI; no duplicate snapshot hashing or runtime imports.

## Implementation evidence

- Exact state validation rejects missing, duplicate, reordered, invalid or
  cross-snapshot stage transitions. Every fresh phase is bound to the canonical
  decision-time full-market content SHA-256; a new fetch resets the epoch.
- `replay_quant_trace.py` verifies caller-supplied hashes for the formal summary
  and snapshot manifest, re-verifies every snapshot artifact, then emits exactly
  20 timestamp-free `OFFLINE_REPLAY` receipts and fails unless all hashes match.
- Real 49-stock fixture replay and negative cases pass: 20 focused tests, Ruff,
  pycompile, frozen scope-check and diff-check all exit 0. Full command evidence
  is in `implementation.json`; offline replay is not formal-run evidence.

## Review evidence

- Independent Critic first reproduced one P1 stale-epoch/single-flight race.
  The closure round independently replayed both counterexamples after the
  reservation repair and returned `ACCEPT`, P0/P1/P2/P3=`0/0/0/0`.
- Accepted implementation diff SHA-256:
  `28aed52085b1ac79c265ae5fe4dd3dc5bd88a0aca346ee946a38079ffd59dcaf`.
  The mutable handoff `review.json` is the closure-delta verdict source; its
  final delivery checksum is recorded outside this tracked contract.

## Progress

- 2026-08-06T11:48:42+08:00 `DRAFT`: Task created.
- 2026-08-06T11:56:00+08:00 `LOCATED`: Scout location validated at confidence 0.95; Planner froze shared full-bundle hash, exact stage-state and isolated replay boundaries.
- 2026-08-06T11:56:46+08:00 `READY`: Baseline frozen; implementation may start.
- 2026-08-06T12:08:00+08:00 `IMPLEMENTED`: Exact market-epoch state, canonical
  trace and isolated 20-run replay implemented; local acceptance checks pass;
  independent Critic review pending.
- 2026-08-06T12:17:00+08:00 `IMPLEMENTED`: Critic found one P1 epoch race:
  admitted old-snapshot work could commit under a refreshed hash, and duplicate
  in-flight stages could perform work before rejection. Review verdict MODIFY.
- 2026-08-06T12:27:00+08:00 `IMPLEMENTED`: Added monotonically versioned epoch
  reservations propagated across worker threads, pre-work single-flight guards,
  stale update/commit rejection and guaranteed abort cleanup. Force-refresh and
  duplicate-report concurrency regressions now pass; re-review pending.
- 2026-08-06T12:30:00+08:00 `REVIEWED`: Closure Critic ACCEPT; original P1
  independently reproduced as closed; P0-P3 all zero.
- 2026-08-06T12:31:00+08:00 `VERIFIED`: Planner reproduced 22 focused passes,
  Ruff, pycompile, exact frozen scope and diff-check. Broad quant run remains
  557 passed / 1 skipped / 10 dependency failures caused solely by the absent
  ignored historical WP1-B review artifact; no evidence was synthesized.
- 2026-08-06T12:31:00+08:00 `CLOSED`: Deterministic state/replay subtask closed
  as LOCAL_IMPLEMENTED. Resource benchmarks, normal session teardown and three
  fresh Windows formal runs remain separate WP1-D work and are not claimed.
