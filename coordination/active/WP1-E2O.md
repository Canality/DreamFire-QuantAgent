---
id: WP1-E2O
title: Operate-year corporate-action archive admission
status: CLOSED
risk: HIGH
owner: Claude
created_at: 2026-08-10T10:36:26+08:00
updated_at: 2026-08-10T14:52:16+08:00
allowed_files:
  - jiuwenswarm/scripts/fetch_corporate_action_operate.py
  - jiuwenswarm/jiuwenswarm/quant/factor_evidence_provider.py
  - jiuwenswarm/evaluation/research_evidence/corporate_action_operate_2020_2025/corporate_actions.csv
  - jiuwenswarm/evaluation/research_evidence/corporate_action_operate_2020_2025/source_records.json
  - jiuwenswarm/tests/unit_tests/quant/test_factor_evidence_provider.py
  - jiuwenswarm/tests/unit_tests/quant/test_corporate_action_operate_archive.py
acceptance:
  - Location phase first: inspect the local BaoStock yearType=operate contract, existing report-year archive/provider/test patterns, E2C date needs, and propose an exact minimal write scope; no network or implementation before Codex freeze.
  - The eventual archive must bind 49 tickers and explicit operate years with per-request receipts that distinguish successful zero rows from errors and record request identity, response schema, row count, timestamps, and recomputable hashes.
  - Canonical action identity uses dividOperateDate and supports multiple actions per ticker/window; dividStockMarketDate cannot substitute for the ex-right/ex-dividend operation date.
  - Coverage start/end, current-year partial cutoff, empty-result proof, duplicate handling, missing ticker/year, tampering, request error, and date-bound failures must be explicit and fail closed.
  - The eventual pinned archive and provider trust key must be Windows-reproducible and independently reviewable; E2P/E2C/direct/formal/production and quant/__init__.py remain unchanged in this task.
---

## Goal

Design and admit a hash-bound BaoStock `yearType='operate'` corporate-action archive that can
prove adjustment-window completeness for the official 49-stock research universe and unblock
the separate E2P typed-evidence bridge.

## Non-goals

- No E2P bridge or E2C replay implementation.
- No production, direct, formal, RPC, allocation, backtest, or report changes.
- No network request or archive generation during the location phase.

## Invariants

- Preserve AGENTS.md evidence, causality, coverage, and fail-closed contracts.
- Report-year archive remains historical evidence but cannot prove operate-date window coverage.
- Empty results require successful request receipts; absence of CSV rows is not proof of no action.
- Existing uncommitted E2A/E2B and user worktree changes remain untouched.

## Locate brief

- Inspect local BaoStock API semantics, archive/provider patterns, E2C date needs, exact callers,
  tests, network boundary, and the smallest proposed write scope.
- Write `output/agent_handoffs/WP1-E2O/location.json`, validate it, set `LOCATED`, then stop.

## Implementation evidence

- Pending.

## Review evidence

- Pending.

## Progress

- 2026-08-10T10:36:26+08:00 `DRAFT`: Codex created a separate operate-year archive admission task; Claude authorized for read-only location only.
- 2026-08-10T10:45:47+08:00 `LOCATED`: Claude submitted read-only BaoStock operate-year feasibility evidence; validate-location passed with confidence 0.85.
- 2026-08-10T10:48:06+08:00 `LOCATED`: Codex location review MODIFY: derive partial coverage from successful receipt as-of time rather than max event date, distinguish parsed payload hash from unavailable wire bytes, and include a reproducible in-repo generator with frozen dependency identity; network remains unauthorized.
- 2026-08-10T10:52:24+08:00 `LOCATED`: Codex ACCEPT: freeze v1 to complete operate years 2020..2025 only, six exact files, independent capability, committed deterministic generator, and a separate unauthorized network-fetch gate.
- 2026-08-10T10:53:04+08:00 `READY`: Baseline frozen; implementation may start.
- 2026-08-10T11:21:58+08:00 `BLOCKED`: BLOCKED_BY_NETWORK_FETCH: offline generator+provider structure implemented and verified; network fetch is an independent gate, not authorized
- 2026-08-10T11:42:00+08:00 `REVIEWED`: Codex independent review MODIFY: four P1 counterexamples reproduced (provider trust bypass, arbitrary 49 universe, non-atomic archive pair replace, malformed schema/CSV admission); see review.json.
- 2026-08-10T11:42:00+08:00 `READY`: Same baseline and six-file whitelist reopened for review-required offline fixes; network gate remains closed.
- 2026-08-10T12:29:45+08:00 `BLOCKED`: BLOCKED_BY_NETWORK_FETCH after Claude round-1 MODIFY fixes; network remained closed and no archive/hash was generated.
- 2026-08-10T12:34:01+08:00 `REVIEWED`: Codex round-2 review MODIFY: core builder still self-authorizes arbitrary valid-format 49 tickers; provider does not recompute receipt payloads or exact CSV projection; capability availability is not bound to the operate trust key/inventory hash.
- 2026-08-10T12:34:01+08:00 `READY`: Same baseline and six-file whitelist reopened for final offline fixes; next Codex verdict must ACCEPT or REJECT/BLOCKED.
- 2026-08-10T12:29:45+08:00 `BLOCKED`: BLOCKED_BY_NETWORK_FETCH: review.json MODIFY P1 fixes applied and verified offline (generator universe binding + transactional pair replace + strict validation; provider full admission validation); network fetch is an independent gate, not authorized
- 2026-08-10T14:10:35+08:00 `BLOCKED`: BLOCKED_BY_NETWORK_FETCH: review.json round-2 P1 fixes applied and verified (generator Excel-authority binding + deep receipt content/hash reconciliation + trusted-key-gated capability + inventory-hash binding); network fetch is an independent gate, not authorized
- 2026-08-10T14:19:44+08:00 `REVIEWED`: Final Codex verdict REJECT after two evidence exchanges; three P1 counterexamples reproduced. Network gate remains unauthorized; any repair requires a new versioned task and fresh baseline.
- 2026-08-10T14:40:05+08:00 `REVIEWED`: REJECT (round 3): three P1 defects confirmed (CSV duplicate identity omits ticker; receipt row-width not enforced; generator/provider duplicate semantics differ). Two-exchange limit exhausted; offline implementation not accepted; network gate stays unauthorized. Continue via a new versioned repair task.
- 2026-08-10T14:52:16+08:00 `CLOSED`: Closed as REJECTED after final round-3 review; not accepted and not verified. Superseded only for bounded repair by WP1-E2O-R1; network gate remains unauthorized.
