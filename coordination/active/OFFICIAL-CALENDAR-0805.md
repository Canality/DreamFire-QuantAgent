---
id: OFFICIAL-CALENDAR-0805
title: Archive and admit official A-share calendar evidence
status: CLOSED
risk: HIGH
owner: Codex
created_at: 2026-08-05T15:02:16+08:00
updated_at: 2026-08-05T15:54:59+08:00
allowed_files:
  - .claude/discussion.md
  - DEVELOPMENT_PLAN.md
  - VALIDATION.md
  - coordination/active/OFFICIAL-CALENDAR-0805.md
  - jiuwenswarm/evaluation/research_evidence/official_calendar_2024_2026/calendar_sessions.csv
  - jiuwenswarm/evaluation/research_evidence/official_calendar_2024_2026/source_records.json
  - jiuwenswarm/jiuwenswarm/quant/factor_evidence_provider.py
  - jiuwenswarm/jiuwenswarm/quant/official_calendar_archive.py
  - jiuwenswarm/tests/unit_tests/quant/test_factor_evidence_provider.py
  - jiuwenswarm/tests/unit_tests/quant/test_official_calendar_archive.py
acceptance:
  - Official first-party records are archived with URLs, publication/retrieval times and hashes; SSE/SZSE schedules agree; every calendar date is classified; historical opens are confirmed by official daily market statistics; future opens remain scheduled; path/hash/tamper/truncation/cross-market/future-promotion negatives fail closed; CANONICAL_CALENDAR alone becomes AVAILABLE while E0/E1 remain blocked; tests, scope, diff and independent Critic pass.
---

## Goal

Build a repository-held, point-in-time official SSE/SZSE scheduled calendar plus SSE daily-confirmed historical session ledger for 2024-2026, without treating future scheduled dates or Hong Kong Connect calendars as confirmed A-share sessions.

## Non-goals

- Do not treat Sina/CSI300 row indexes, pandas `bdate_range`, a third-party
  calendar, a Hong Kong Connect service calendar or a caller-supplied path/hash
  as A-share calendar authority.
- Do not mark dates after the official daily-statistics confirmation cutoff as
  actual sessions merely because the annual schedule says they should open.
- Do not add sector, corporate-action, adjusted-price, label, E0 snapshot or E2
  logic, and do not change production, T2, WP1-C or direct/formal paths.

## Invariants

- Preserve AGENTS.md, the official `decision -> 1 full session embargo -> entry
  open -> 20th session close` contract and all project safety contracts.
- Archive one complete date row per calendar day for 2024-01-01 through
  2026-12-31.  Scheduled status is derived from Monday-Friday plus the exact
  SSE/SZSE annual closure spans; both exchanges must agree year by year.
- For every weekday on or before 2026-08-04, bind the result of the official SSE
  daily stock-statistics query.  A confirmed open must return exactly the
  requested trade date and the frozen product rows; a scheduled holiday must
  return no rows.  Weekends are closed by the exchange rule and are not queried.
- Dates after 2026-08-04 retain only `SCHEDULED_OPEN/SCHEDULED_CLOSED`.  Only the
  monotonically ordered `CONFIRMED_OPEN` sequence may enter the E0/E1 trusted
  calendar key.
- Public inspection/loading accepts no repository root, path, hash, source URL,
  confirmation cutoff or allowlist.  Fixed files must be regular non-symlinks,
  remain under the repository root, match pinned hashes and have exact directory
  membership.
- `CANONICAL_CALENDAR` may become available alone.  Sector, label,
  corporate-action and E0 snapshot remain unavailable, so aggregate E0/E1
  readiness remains false and E2 remains prohibited.

## Locate brief

- Scout artifact `output/agent_handoffs/OFFICIAL-CALENDAR-0805/location.json`
  validates with confidence `0.90`; risk remains `HIGH` because this changes an
  evidence trust root and historical causality boundary.
- The tracked Sina snapshot covers 2024-06-13 through 2026-07-20, but its dates
  are observations rather than authority.  E0 needs 251 canonical sessions and
  E1 needs at least eight matured, non-overlapping official 1+20 windows.
- First-party SSE/SZSE annual notices for 2024, 2025 and 2026 are available and
  agree on scheduled closures.  Exchange rules state that trading days are
  Monday-Friday except statutory holidays and exchange-announced closures.
- Annual notices alone cannot prove that no extraordinary full-market closure
  occurred.  The frozen design therefore adds an SSE official daily market
  statistics confirmation ledger through 2026-08-04; future scheduled dates are
  never promoted to historical facts.
- The contest schedule resolves to decision 2026-08-21, embargo 2026-08-24,
  entry 2026-08-25 and twentieth-session exit close 2026-09-21.  These future
  dates remain scheduled evidence until they occur.

## Implementation evidence

- Archived 10 first-party source records, a 677-row normalized SSE daily-query
  ledger with the complete canonical result-row payloads, and 1,096 daily calendar classifications under the two frozen data
  files.  The loader independently derives the annual schedule, cross-checks
  SSE/SZSE closures, binds each historical weekday to its ledger record and
  admits only 626 `CONFIRMED_OPEN` sessions through 2026-08-04.
- Source/evidence/audit hashes are
  `b5f6027ca0528821e51a0986adccb9076702878d20a5041b45637bb388c1713d`,
  `c845b13e4f43cb42538cea1da8cd68708dbda3cecf170966af3b0ae573e2ddaa`
  and `9096b949c1c46952a53af96d3020a67b13d225e516ae55aa286c3bfc2eaffe6c`.
  Provider inventory/audit hashes are
  `d9522f814830c112a57a19063c63e429970424048c520408ece0611a06e7d320`
  and `857fdbd9282b07c8cb0e57b6641d83719fee3c3c52b65a6cf9b94132e97c610d`.
- Calendar+Provider+E1 tests pass 26/26; Ruff, `git diff --check` and task
  scope-check pass.  The broader 47-test run passed 38 and exposed nine
  pre-existing E0 candidate failures caused by the unchanged
  `trend_consistency_5_10_20` implementation-hash mismatch; this task does not
  expand scope to repair that separate baseline defect.

## Review evidence

- Initial independent review `REJECT` bound diff
  `917455b9f77c002e7b07b63e5f615ed8d4f4c3a2e468e21fe47f2fb3124a9bbe`
  with P0/P1/P2/P3=`0/1/0/0`: daily open records exposed only an opaque
  result hash, so a coordinated repin could not be audited offline.
- Remediation archives the complete canonical SSE result-row list for all 677
  weekday queries, recomputes every daily digest from those bytes, derives the
  stored count/products/trade date from the payload, and adds the reproduced
  coordinated-repin counterexample.
- Final independent re-review `ACCEPT`, P0/P1/P2/P3=`0/0/0/0`; it independently
  recomputed 677 ledger records, 1,878 result rows, all daily and aggregate
  hashes, and rejected opaque-digest, payload/date/summary and truncation
  variants. The final review artifact is
  `output/agent_handoffs/OFFICIAL-CALENDAR-0805/review.json`.

## Progress

- 2026-08-05T15:02:16+08:00 `DRAFT`: Task created.
- 2026-08-05T15:02:16+08:00 `LOCATED`: Scout location valid=true confidence=0.90; official annual schedules are usable but require actual-session confirmation.
- 2026-08-05T15:02:16+08:00 `READY`: Baseline frozen; implementation may start.
- 2026-08-05T15:30:54+08:00 `IMPLEMENTED`: First-party archive, normalized
  daily-query ledger, fail-closed loader, single calendar trust key, negative
  tests and current-fact documentation completed; independent review pending.
- 2026-08-05T15:44:00+08:00 `IMPLEMENTED`: First Critic P1 reproduced and
  remediated with offline-recomputable canonical result-row payloads and a
  coordinated-repin regression; final re-review pending.
- 2026-08-05T15:53:00+08:00 `REVIEWED`: Independent Critic accepted the
  remediated evidence boundary with P0/P1/P2/P3=`0/0/0/0`.
- 2026-08-05T15:53:00+08:00 `VERIFIED`: Planner confirmed payload/hash
  recomputation, 26/26 focused tests, bounded baseline failures and 10/10 scope.
- 2026-08-05T15:53:00+08:00 `CLOSED`: Official calendar is singly admitted;
  aggregate E0/E1 and the remaining four E1P capabilities stay fail-closed.
