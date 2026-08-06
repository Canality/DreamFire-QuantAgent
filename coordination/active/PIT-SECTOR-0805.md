---
id: PIT-SECTOR-0805
title: Locate and admit historical point-in-time six-sector membership
status: CLOSED
risk: HIGH
owner: Codex
created_at: 2026-08-05T17:06:30+08:00
updated_at: 2026-08-05T17:51:34+08:00
allowed_files:
  - .claude/discussion.md
  - VALIDATION.md
  - coordination/active/PIT-SECTOR-0805.md
  - jiuwenswarm/jiuwenswarm/quant/reporting/contest_universe_archive.py
  - jiuwenswarm/jiuwenswarm/quant/reporting/submission_contract.py
  - jiuwenswarm/tests/unit_tests/quant/test_contest_universe_archive.py
  - jiuwenswarm/tests/unit_tests/quant/test_submission_contract.py
acceptance:
  - Scout identifies the authoritative taxonomy owner, exact 49-ticker mapping semantics, effective/observed/version dates, code/name/listing changes, historical coverage, correction behavior, archive and delivery rights; Planner freezes a non-overlapping whitelist; implementation admits only immutable contest metadata or versioned PIT sector observations through the existing Provider trust boundary, otherwise closes DATA_BLOCKED; static current SECTOR_MAP cannot be backfilled as historical evidence; wrong date/ticker/taxonomy/version/hash/source inputs fail closed; calendar, E0/E1, production, direct/formal and strategy weights remain unchanged unless separately authorized; focused tests, scope, diff and independent Critic pass.
---

## Goal

Determine whether the contest six-sector taxonomy is immutable evaluation metadata or time-varying industry evidence, then locate the smallest first-party historical membership chain that can be replayed at each decision cutoff without silently backfilling today's mapping.

## Non-goals

- Do not treat the workbook modified timestamp, local Git import time or a
  current website response as historical `observed_at` for a past decision.
- Do not relabel the six contest columns as CSRC, SSE, SZSE, CNI or another
  standard industry taxonomy unless the authoritative source says so.
- Do not backfill the 2026 contest grouping across 2024-2026 decisions merely
  because the current 49 tickers and six labels are convenient for
  neutralization.
- Do not change the production `STOCK_POOL`/`SECTOR_MAP`, portfolio constraints,
  report contract, factor weights, calendar, labels, corporate-action state,
  E0/E1 disposition, direct/formal or Agent behavior in the locate phase.
- Do not delete, rewrite or overwrite the official workbook, historical
  evidence, prior handoffs or Windows delivery packages.

## Invariants

- Preserve AGENTS.md, the official 49-name submission universe, current six
  report/portfolio groups, and the exact calendar/embargo/20-session target.
- Keep three concepts separate: (1) the 2026 contest's fixed submission
  grouping, (2) an issuer's PIT industry membership as market data, and (3) a
  researcher-defined neutralization bucket.  Evidence for one cannot silently
  authorize another.
- For a historical decision cutoff, any market-data classification must bind
  taxonomy owner/version, security identifier, class code and name, effective
  interval, publication/observed time, raw source bytes and correction/version
  lineage.  Later restatements create a new version rather than rewriting the
  earlier view.
- If the contest grouping is shown to be immutable evaluation metadata rather
  than market data, it may describe the fixed evaluation universe only after
  its official publication time.  Whether it can be used as a historical
  neutralization design constant must be an explicit Planner decision with a
  leakage limitation; it is not automatically `PIT_SECTOR`.
- Exact 49-ticker and six-nonempty-group coverage is mandatory for the current
  research contract.  Unknown, ambiguous, duplicated, delisted, renamed or
  changed-code securities fail closed rather than falling into `其他`.
- A public classification page is not an archive by itself.  Source identity,
  historical versions, empty-result proofs, retrieval timestamps and
  archive/Windows-delivery rights must be independently auditable.

## Scout read scope

- `coordination/active/PIT-SECTOR-0805.md`
- `赛题文档/上市公司列表.xlsx`, `赛题文档/README.md`,
  `赛题文档/赛题介绍.txt` and only the relevant cited passages in the answer
  transcript/notes.
- `jiuwenswarm/jiuwenswarm/quant/stock_pool.py`
- `jiuwenswarm/jiuwenswarm/quant/factor_evidence_provider.py`
- `jiuwenswarm/jiuwenswarm/quant/factor_research.py`
- `jiuwenswarm/jiuwenswarm/quant/reporting/submission_contract.py`
- Focused tests and call sites found by `rg`; no history, output logs,
  production entry points or unrelated repository-wide reading.

## Scout deliverable and stop conditions

- Write only `output/agent_handoffs/PIT-SECTOR-0805/location.json` using the
  workflow schema.  The tracked task file remains Planner-owned.
- Inspect the workbook's sheets, formulas, properties, hash and repository
  provenance.  Report whether any cell or first-party context declares the six
  labels to be a stable taxonomy, supplies an effective/publication date or
  defines historical applicability.
- Evaluate at least these candidate authorities separately: the contest
  workbook/grouping, CSRC listed-company industry classification, SSE issuer
  profile/classification data and SZSE/SSIC issuer classification data.  For
  each, report exact source authority, taxonomy version, history coverage,
  grain, effective/observed time, corrections, code/name changes, raw-byte
  archive and delivery feasibility.
- Test both competing hypotheses: `CONTEST_FIXED_METADATA` and
  `PIT_MARKET_CLASSIFICATION`.  Recommend a trust key and minimal write scope
  only if one hypothesis can be admitted without temporal leakage or semantic
  relabeling.
- Stop at `DATA_BLOCKED` if no source supplies historical-as-published versions
  for all 49 tickers, or at `CONTRACT_BLOCKED` if the workbook's role is too
  ambiguous to decide.  Do not propose self-attested dates or hashes as a
  bypass.

## Locate brief

- Scout artifact:
  `output/agent_handoffs/PIT-SECTOR-0805/location.json`, SHA-256
  `9b80f614ee887e50fdef6294ed453f569852bf3ddab0ae20c1d5c675cc5ccdc5`,
  schema-valid at confidence `0.97`.
- Disposition: `CONTRACT_BLOCKED` for historical use of the contest grouping;
  secondary disposition `DATA_BLOCKED` for `PIT_SECTOR` market evidence.
- The official workbook is an exact, formula-free 49-name/six-group contest
  artifact (`c021d69b...0617`) and matches `stock_pool.py`, but it declares no
  taxonomy owner/version, publication or effective time, historical scope, or
  revision chain.  It can therefore be admitted only as
  `CONTEST_FIXED_METADATA`, never as historical sector evidence.
- CAPCO's current semiannual classification files are a different standard
  taxonomy.  They presently cover 49/49, but old attachments have been
  re-hosted in 2026, no historical-as-published byte/version chain was found,
  and the association's legal statement does not authorize copying those PDFs
  into this repository or a Windows delivery package.
- Planner adjudication: implement only a fixed-path/fixed-hash XLSX parser and
  exact semantic binding for `SubmissionContract`.  Reject symlinks, formulas,
  extra cells/sheets, duplicates, unexpected counts or code/name/group drift.
  Do not add a factor-provider capability or trust key; keep `PIT_SECTOR`, E0,
  E1, calendar, production, direct/formal and strategy weights unchanged.

## Implementation evidence

- Added a standard-library, fixed-path/fixed-hash OOXML audit for the official
  contest workbook.  It rejects symlinks, missing/tampered bytes, unsafe or
  duplicate ZIP members, unexpected sheet names, formulas, non-shared-string
  cells, extra/missing cells, non-empty Sheet2/Sheet3, header drift, malformed
  codes, exchange ambiguity, duplicates, wrong counts and renamed groups.
- The verified output is explicitly `CONTEST_FIXED_METADATA` with
  `pit_sector_eligible=false`; it exposes no effective or observed time.  Exact
  result: 49 members, group counts `8/9/8/12/8/4`, canonical evidence hash
  `b490612174fc0b79554e7ca3d04b9a14e14d4b8b5b6c9c50983330e94fdbdc12`.
  That hash is an independent frozen semantic anchor: changing the workbook
  byte hash alone cannot rename a company or move it across groups.
- `SubmissionContract` now sets `source_verified=true` only when canonical
  workbook bytes pass the semantic audit and the contract's sorted codes,
  names, groups and group order exactly match it.  The former positive test in
  which an unrelated two-company contract borrowed the official path/hash is
  now a required failure.
- Final focused + adjacent regression: archive, submission contract, factor
  Provider and E1 research `70 passed`; changed-file Ruff passed.  An initial
  negative test accidentally assigned a stock to its existing group and failed
  to raise; the test input was corrected to select a guaranteed different
  group, after which the unchanged implementation and full 67-test set passed.
- Runtime audit remains byte-for-byte at `PIT_SECTOR=false`, reason
  `UNAVAILABLE_NO_HISTORICAL_SECTOR_VERSION`, trusted evidence key count `1`,
  `ready_for_e0=false`, `ready_for_e1=false`.  Provider and factor-research
  source files are unchanged from baseline.

## Review evidence

- First independent Critic pass bound diff
  `33e2a8109d24a9fcaa473d22e6f97cd71d40f72b54540eca13123e16a058fec7`
  and correctly returned `REJECT`: P1 showed that byte-hash-only repinning could
  accept a same-shape rename/group swap; P2 showed that `realpath` accepted an
  external symlink alias.  The review SHA-256 was
  `7d4a6420059fdc24bb3da42edbfe0cddd3e1003b0418e5389d3d497dd8e715a4`.
- Fixes add the independent semantic evidence anchor plus exact lexical source
  identity and link/junction/reparse-component rejection.  New negative tests
  cover a valid-shape rename, cross-group swap, final symlink and symlinked
  parent.
- Final Critic re-review bound diff
  `bae449d6606b2413450b2655fe221188adc730a834ba73811d931f114fff3f36`
  and returned `ACCEPT`, P0/P1/P2/P3=`0/0/0/0`; review SHA-256
  `d4d73e4d0b4128d67f989fa8ffb71fe8c630042d11f11d26a318c28304571456`.
  Independent replay included valid-shape rename, cross-group swap, unique
  unknown code, matching malicious contract, exact/alias path, symlink parent,
  provider isolation and the full 70-test set.

## Progress

- 2026-08-05T17:06:30+08:00 `DRAFT`: Task created.
- 2026-08-05T17:28:25+08:00 `LOCATED`: Scout validated at confidence 0.97; admit only CONTEST_FIXED_METADATA parser/binding; PIT_SECTOR remains DATA_BLOCKED.
- 2026-08-05T17:28:25+08:00 `LOCATED`: Write scope approved by Planner.
- 2026-08-05T17:28:25+08:00 `READY`: Baseline frozen; implementation may start.
- 2026-08-05T17:28:25+08:00 `READY`: Whitelist frozen after Planner adjudication; implementation is limited to immutable contest metadata semantic binding.
- 2026-08-05T17:35:50+08:00 `IMPLEMENTED`: Fixed contest metadata parser and semantic binding implemented; 67 focused/adjacent tests and Ruff pass; PIT_SECTOR/E0/E1 unchanged.
- 2026-08-05T17:51:34+08:00 `REVIEWED`: Independent Critic ACCEPT on bae449d6; P0/P1/P2/P3=0/0/0/0 after semantic-repin and symlink fixes.
- 2026-08-05T17:51:34+08:00 `VERIFIED`: 70/70 focused and adjacent tests, Ruff, pycompile, diff and 7-file scope pass; PIT_SECTOR/E0/E1 unchanged.
- 2026-08-05T17:51:34+08:00 `CLOSED`: Task closed as CONTEST_FIXED_METADATA semantic binding only; historical PIT sector remains DATA_BLOCKED.
