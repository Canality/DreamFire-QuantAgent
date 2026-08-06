---
id: WP0C-REPLAY-PARITY-0806
title: Bind announcement offline replay and direct/formal status parity
status: CLOSED
risk: HIGH
owner: Codex
created_at: 2026-08-06T11:28:00+08:00
updated_at: 2026-08-06T11:46:06+08:00
allowed_files:
  - coordination/active/WP0C-REPLAY-PARITY-0806.md
  - jiuwenswarm/jiuwenswarm/quant/reporting/providers/archive.py
  - jiuwenswarm/jiuwenswarm/quant/reporting/announcement_service.py
  - jiuwenswarm/jiuwenswarm/quant/reporting/providers/announcement.py
  - jiuwenswarm/jiuwenswarm/quant/reporting/models.py
  - jiuwenswarm/jiuwenswarm/quant/reporting/report_service.py
  - jiuwenswarm/scripts/run_quant_pipeline.py
  - jiuwenswarm/jiuwenswarm/extensions/quant-finance/extension.py
  - jiuwenswarm/tests/unit_tests/quant/test_announcement_service.py
  - jiuwenswarm/tests/unit_tests/quant/test_wp0cb_archive_grade.py
  - jiuwenswarm/tests/unit_tests/quant/test_direct_pipeline_adapter.py
  - jiuwenswarm/tests/unit_tests/quant/test_extension_cache_pipeline.py
acceptance:
  - An accepted announcement run writes an immutable hash-bound receipt containing the exact requested universe, as-of clock, per-ticker status, terminal diagnostics and referenced evidence IDs.
  - The receipt and archived payloads replay offline to the same canonical facts, statuses and snapshot hash without network access; missing, tampered, future or mismatched evidence fails closed.
  - Provider status remains complete, available_no_event, partial or unavailable per ticker and is not collapsed to a hard-coded partial value.
  - Direct and formal adapters consume the same canonical announcement snapshot projection and expose the same hash for identical evidence.
  - Focused replay, tamper, future, status, direct/formal parity, Ruff, pycompile, scope-check and diff-check pass.
---

## Goal

Close the locally actionable WP0-C gaps after the real PIT Provider integration:
make the accepted 49-ticker result independently replayable without a network,
preserve provider-state semantics into every company bundle, and bind direct and
formal report construction to one canonical announcement snapshot hash.

## Non-goals

- Do not add a second disclosure/news Provider or change source licensing.
- Do not upgrade report grades beyond evidence actually present.
- Do not place raw announcement bodies or full lists in Agent context.
- Do not claim a new real 49-ticker or formal run in this task.
- Do not change factor, portfolio, Agent RPC or submission contracts.

## Invariants

- Archive replay is explicitly `OFFLINE_REPLAY`; it must never be labelled a
  fresh retrieval or substitute for a current run.
- Absence of an event is accepted only from a bound successful Provider receipt;
  absence of archive bytes or a receipt is not `available_no_event`.
- The accepted live service and offline replay must produce the same canonical
  snapshot hash from the same immutable evidence.

## Locate brief

- Scout must locate archive manifest/read-write semantics, AnnouncementService
  result construction, Provider parser helpers, CompanyFactBundle status
  consumers, direct/formal report adapters and focused tests. It writes only
  `location.json` and proposes the smallest receipt/replay/parity boundary.

## Implementation evidence

- Accepted live runs now archive a canonical, SHA-256-addressed receipt that
  binds the ordered requested universe, aware as-of time, exact ProviderStatus,
  terminal diagnostics, universe health and every fact evidence ID.
- `replay_announcement_service` reconstructs facts only from hash-verified
  archived payloads, makes no Provider call, labels the result
  `OFFLINE_REPLAY`, and rejects missing/tampered/future/mismatched state.
- Direct and formal call one shared snapshot projection and propagate each
  ticker's exact status into `CompanyFactBundle`; report-grade policy is not
  changed.
- 100 focused tests passed; Ruff, pycompile, scope-check and diff-check passed.
  The existing post-success event-loop/socket ResourceWarnings are assigned to
  WP1-D teardown work and do not change the test exit status.
- Critic round 1 found four P1 counterexamples. Closure now validates payload
  ticker ownership in both parsers, deep-seals accepted results, rejects
  impossible/zero-request terminal diagnostics, and verifies existing bytes
  before treating an archive write as idempotent.
- Critic round 2 found one P1 live/archive fact-content mismatch. Closure now
  reconstructs every live fact from the committed archive bytes through the
  offline parser and requires exact equality before signing the receipt.

## Review evidence

- Independent Critic decision: `ACCEPT`; P0/P1/P2/P3 = `0/0/0/0`.
- Five cumulative P1 counterexamples were reproduced and closed: cross-ticker
  ownership, mutable hash-bound state, zero/impossible diagnostics,
  missing/corrupt idempotent receipt, and forged live/archive fact parity.
- Reviewed implementation diff SHA-256:
  `cd9ce8c1d43be12e00c668f894f3b9620aad8c79368e8c8716ba6c03de3a28cd`.
- Final `review.json` SHA-256:
  `ddd05e0b04778695e518467236f51671f08e0aba5dfb3123525cde1f2d4d78f4`.

## Progress

- 2026-08-06T11:28:00+08:00 `DRAFT`: Created from the full roadmap audit after WP0-B closure; real-provider sourcing remains unchanged.
- 2026-08-06T11:20:00+08:00 `LOCATED`: Scout location validated at confidence 0.96. Planner froze the shared receipt/replay boundary and exact direct/formal status propagation; Provider vocabulary and report-grade policy remain unchanged.
- 2026-08-06T11:25:00+08:00 `IMPLEMENTED`: Receipt/replay, fail-closed validation and direct/formal parity implemented with 94 focused tests passing.
- 2026-08-06T11:37:00+08:00 `IMPLEMENTED`: Closed the four round-1 P1 counterexamples; 99 focused tests pass pending independent closure review.
- 2026-08-06T11:43:00+08:00 `IMPLEMENTED`: Closed the round-2 canonical-fact mismatch; 100 focused tests pass pending final Critic closure.
- 2026-08-06T11:47:00+08:00 `CLOSED`: Independent Critic accepted all five closures with no P0-P3 findings; Planner acceptance complete without a real-network or formal-run claim.
- 2026-08-06T11:20:15+08:00 `READY`: Baseline frozen; implementation may start.
- 2026-08-06T11:26:01+08:00 `IMPLEMENTED`: Receipt/replay and direct/formal parity implemented; 94 focused tests pass.
- 2026-08-06T11:46:06+08:00 `REVIEWED`: Independent Critic ACCEPT; cumulative five P1 counterexamples closed.
- 2026-08-06T11:46:06+08:00 `VERIFIED`: 100 focused tests and all static/scope/diff gates passed.
- 2026-08-06T11:46:06+08:00 `CLOSED`: Planner accepted; no real-network or formal-run claim.
