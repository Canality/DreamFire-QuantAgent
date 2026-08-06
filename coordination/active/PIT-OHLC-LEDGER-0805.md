---
id: PIT-OHLC-LEDGER-0805
title: Locate and admit PIT corporate actions, adjusted OHLC and per-ticker provenance
status: CLOSED
risk: HIGH
owner: Codex
created_at: 2026-08-05T16:46:31+08:00
updated_at: 2026-08-05T17:02:04+08:00
allowed_files:
  - .claude/discussion.md
  - VALIDATION.md
  - coordination/active/PIT-OHLC-LEDGER-0805.md
acceptance:
  - Scout validates exact sources, license/archive feasibility, PIT timestamps, adjustment formula, ticker/date grain, per-ticker lineage and failure modes; Planner freezes a non-overlapping whitelist; implementation archives immutable source payloads and recomputable ledgers or closes DATA_BLOCKED; future/backfilled/tampered/cross-source/unit/duplicate/missing-action inputs fail closed; existing calendar remains exact; E0/E1 stay blocked unless every required capability is actually admitted; focused tests, scope, diff and independent Critic pass; production/direct/formal remain unchanged.
---

## Goal

Locate the smallest first-party or otherwise auditable A-share evidence chain that can reproduce point-in-time corporate-action adjustments and per-ticker OHLC provenance without caller self-attestation; implement only after Planner accepts Scout evidence.

## Non-goals

- Do not treat a vendor's current `qfq`/`hfq` series as point-in-time evidence
  unless the exact historical adjustment inputs and versioned formula can be
  replayed as they were visible on each decision date.
- Do not infer splits, dividends, allotments, suspensions or delistings from
  price jumps; do not backfill publication/record/ex-date timestamps.
- Do not promote the existing Sina `raw/unadjusted` snapshot, static sector
  map, caller-provided path/hash or an in-memory dataframe to a trust root.
- Do not start forward-label, sector, E0 snapshot, E2, production, Agent,
  direct/formal or strategy-weight work in this task.
- Do not delete, rewrite or overwrite the existing official-calendar archive,
  historical evidence, task handoffs or Windows delivery packages.

## Invariants

- Preserve AGENTS.md, the official canonical-calendar trust key and the exact
  `decision -> one full session embargo -> entry open -> twentieth session
  close` contract.
- Intended grain is one immutable source observation per
  `(ticker, trade_date, field, source, observed_at)` plus one corporate-action
  record per stable action id/version.  Derived adjusted OHLC must bind all
  contributing raw observations, actions, formula version and cutoff.
- Every admitted ticker must map deterministically to the 49-name contest
  universe and an SSE/SZSE security identifier; ambiguity, missing mappings or
  mixed market identifiers fail closed.
- Separate source publication/effective/ex/record/pay dates from fetch time.
  A historical decision may use only bytes observable by its cutoff; a later
  correction or backfill must create a new source version rather than silently
  rewriting an earlier PIT view.
- Corporate-action and adjusted-OHLC capability dispositions remain separate
  from source-byte verification.  Partial ticker/date coverage cannot populate
  the aggregate E0/E1 trust root.
- Prefer exchange/company first-party archives.  A secondary vendor is
  admissible only if source identity, version, raw payload, adjustment formula,
  license/redistribution boundary and historical visibility are all auditable.

## Scout read scope

- `coordination/active/PIT-OHLC-LEDGER-0805.md`
- `jiuwenswarm/jiuwenswarm/quant/factor_evidence_provider.py`
- `jiuwenswarm/jiuwenswarm/quant/market_data_service.py`
- `jiuwenswarm/jiuwenswarm/quant/candidate_factors.py`
- `jiuwenswarm/jiuwenswarm/quant/factor_research.py`
- `jiuwenswarm/jiuwenswarm/quant/snapshot_writer.py`
- `jiuwenswarm/evaluation/data_snapshots/sina_20260721_135352/manifest.json`
- Relevant source adapters and the focused tests found by `rg`; no history,
  output logs, production entry points or unrelated repository-wide reading.

## Scout deliverable and stop conditions

- Write only `output/agent_handoffs/PIT-OHLC-LEDGER-0805/location.json` using
  the workflow schema.  Report definitions, call sites, tests, candidate source
  archives, exact missing evidence and a proposed minimal write whitelist.
- For each source candidate report authority, coverage, grain, timestamps,
  correction/backfill behavior, formula reproducibility, archive/redistribution
  feasibility and whether each claim is verified or only assumed.
- Stop at `DATA_BLOCKED` if no source can preserve raw historical bytes and
  time-of-availability.  Do not recommend accepting opaque adjusted prices as a
  shortcut.

## Locate brief

- Scout artifact
  `output/agent_handoffs/PIT-OHLC-LEDGER-0805/location.json` validates with
  confidence `0.94`; disposition is `DATA_BLOCKED` and risk remains `HIGH`.
- The frozen Sina snapshot has 49 unique tickers (40 SH, 9 SZ) and five
  510-by-49 OHLCV matrices from 2024-06-13 through 2026-07-20.  Each matrix has
  exactly 490 missing cells (`1.96%`) without a ticker/date suspension or
  no-trade reason.  Its single manifest identifies a raw/unadjusted Sina
  source, but holds no HTTP response bodies, response headers, row-level
  observed time, correction history or per-ticker source ledger.
- SSE/SZSE rules and sampled issuer implementation notices establish that
  record, ex, payment and publication dates plus ordinary or exceptional
  ex-rights formulas exist.  Samples do not prove the complete 49-ticker action
  set, stable action ids, corrections/withdrawals or historical empty results.
- SZSE states that SSIC exclusively manages and distributes SZSE securities
  information and separately offers EOD and corporate-action data services.
  The public pages inspected do not establish permission to archive and
  redistribute a complete historical product in a Windows delivery.
- No candidate therefore satisfies all of raw historical bytes,
  time-of-availability, exact 49-ticker coverage, versioned formulas,
  correction lineage and archive/redistribution feasibility.

## Implementation evidence

- Planner independently recomputed the five matrix profiles: every file is
  `(510, 49)` with `490 / 24,990 = 0.0196078431` missing observations.
- Planner verified the official SZSE data-service description for Level-1 EOD
  OHLC and corporate actions, and confirmed the current SSE rule version/date
  boundary.  This confirms a source class exists, not that the repository owns
  an admissible archive or redistribution right.
- No Provider, trust key, formula, archive or source byte was added.  Existing
  `PIT_CORPORATE_ACTION=UNAVAILABLE_NO_CORPORATE_ACTION_ARCHIVE`, empty E0/E1
  roots, production, direct/formal, calendar evidence and historical files are
  unchanged.
- The current document-contract suite collected 17 tests: 8 passed and 9 failed
  on the unchanged missing ignored resource mirror
  `jiuwenswarm/resources/agent/workspace/skills/quant-investment/SKILL.md`.
  This is the same baseline limitation already recorded in `VALIDATION.md`; the
  task neither changes that path nor reports the suite as green.
- The smallest safe deliverable is this machine-readable location/blocker
  record.  Implementation may resume only after written/licensed source access
  establishes full bytes, versions, timestamps, correction semantics and
  delivery rights; public-page scraping is explicitly not an accepted bypass.

## Review evidence

- Independent Critic verdict is `ACCEPT`; open P0/P1/P2/P3 counts are
  `0/0/0/0`.
- Critic independently rehashed every manifest child and reproduced all five
  matrix dimensions, missing counts and identical missing masks.  It also
  verified that every ticker has exactly ten missing dates and that no missing
  reason or row-level provenance ledger is present.
- Official first-party historical products were treated as a viable acquisition
  route, not as evidence already held by this repository.  The Critic found no
  complete historical-as-published bytes, versions, corrections or delivery
  permission that would falsify `DATA_BLOCKED`.
- The Provider is byte-identical to baseline; only the pre-existing calendar
  trust tuple remains admitted, E0/E1 remain false, and the frozen three-file
  scope has zero violations.
- The final review must bind the closure diff after this status record is
  frozen; its machine-readable verdict is delivered in
  `output/agent_handoffs/PIT-OHLC-LEDGER-0805/review.json`.

## Progress

- 2026-08-05T16:46:31+08:00 `DRAFT`: Task created.
- 2026-08-05T16:53:39+08:00 `LOCATED`: Scout location valid=true confidence=0.94; no source satisfies raw PIT bytes, full 49-ticker coverage, correction lineage and archive/redistribution feasibility.
- 2026-08-05T16:53:39+08:00 `LOCATED`: Write scope approved by Planner.
- 2026-08-05T16:53:40+08:00 `READY`: Baseline frozen; implementation may start.
- 2026-08-05T16:56:00+08:00 `IMPLEMENTED`: Planner reproduced the matrix
  profile and official data-service boundary, declined an opaque adjusted-price
  shortcut and documented the external source blocker; independent review
  pending.
- 2026-08-05T16:56:11+08:00 `IMPLEMENTED`: No provider code was authorized: source and license blockers documented; current trust roots remain unchanged.
- 2026-08-05T17:02:04+08:00 `REVIEWED`: Independent Critic ACCEPT; P0/P1/P2/P3=0/0/0/0 and DATA_BLOCKED survived source, missingness, correction, licensing and trust-root counterexamples.
- 2026-08-05T17:02:04+08:00 `VERIFIED`: Location schema, matrix profile, manifest hashes, scope and diff checks verified; document-contract suite remains honestly non-green only on the unchanged ignored Skill mirror.
- 2026-08-05T17:02:04+08:00 `CLOSED`: External source/archive/delivery rights are required before implementation can resume; no runtime or trust-root change was made.
