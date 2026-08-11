---
id: WP1-E2P
title: Real archive factor-evidence trust bridge
status: CLOSED
risk: HIGH
owner: Claude
created_at: 2026-08-09T17:03:03+08:00
updated_at: 2026-08-10T17:11:22+08:00
allowed_files:
acceptance:
  - Location phase first: reproduce the calendar and corporate-action contradictions against actual admitted archives, enumerate definitions/callers/tests and propose the smallest write scope; no implementation before Codex freezes a baseline.
  - The eventual fix must use public typed evidence and compute_trend_snapshot; direct access to private _KERNELS, local recreation of snapshot hashing, monkeypatching trust membership, or weakening provider-owned immutable trust roots is forbidden.
  - A real-archive integration test must construct PointInTimeFactorInput from hash-verified official calendar and corporate-action evidence and compute a 49-stock x 12-factor snapshot for a valid strictly-prior window, with no network or future-data leakage.
  - Tampered archive bytes, untrusted identity/hash, incomplete 49-stock coverage, calendar/session mismatch, and insufficient/future input fail closed; existing synthetic unit contracts remain covered.
  - Focused pytest, Ruff, py_compile, diff-check and scope-check pass; direct/formal/production callers and quant/__init__.py remain unchanged unless a later explicit Codex scope decision says otherwise.
---

## Goal

Repair the typed PointInTimeFactorInput evidence contract so the admitted official calendar and corporate-action archives can drive compute_trend_snapshot without bypassing provider-owned trust roots; this is a prerequisite for WP1-E2C.

## Non-goals

- No unrelated refactor.

## Invariants

- Preserve AGENTS.md and project safety contracts.

## Locate brief

- Pending.

## Implementation evidence

- Pending.

## Review evidence

- Pending.

## Progress

- 2026-08-09T17:03:03+08:00 `DRAFT`: Task created.
- 2026-08-09T17:08:33+08:00 `LOCATED`: Scout complete: reproduced 3 trust-contract failure layers (CRLF calendar hash, calendar_id, corporate-action authority); 251-session feasibility confirmed; location.json confidence 0.86
- 2026-08-10T09:46:34+08:00 `LOCATED`: Codex pre-freeze MODIFY: dual-hash and exact CRLF scope accepted in principle; require read-only proof of qfq decision-time semantics, all-kernel scale invariance, per-decision corporate-action windows, and honest policy naming before baseline freeze.
- 2026-08-10T10:02:00+08:00 `LOCATED`: Codex supplement review MODIFY: kernel invariance accepted; calendar must use contiguous-subsequence proof (not suffix), corporate-action coverage cannot derive from max observed ex-date, ticker_results must have one typed meaning, and current-checkout LF normalization needs an explicit safe procedure.
- 2026-08-10T10:20:56+08:00 `BLOCKED`: Codex final two-exchange verdict REJECT: report-year archive cannot prove operate-date window completeness and uses the wrong event-date field; require a separately admitted yearType=operate archive before E2P can resume.
- 2026-08-10T17:11:22+08:00 `CLOSED`: Closed as REJECTED/BLOCKED design version: report-year corporate-action archive could not prove operate-date completeness. Superseded by a fresh E2P-R1 location after the verified operate-year archive admission.
