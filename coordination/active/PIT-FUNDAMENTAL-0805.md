---
id: PIT-FUNDAMENTAL-0805
title: Locate and admit point-in-time fundamental filing evidence
status: CLOSED
risk: HIGH
owner: Codex
created_at: 2026-08-05T18:21:39+08:00
updated_at: 2026-08-05T18:44:38+08:00
allowed_files:
  - .claude/discussion.md
  - VALIDATION.md
  - coordination/active/PIT-FUNDAMENTAL-0805.md
acceptance:
  - Scout maps existing fundamental report grade consumers and all current announcement/filing seams; evaluates SSE/SZSE issuer disclosure or XBRL sources separately from aggregators; specifies security identifier, report period/type, consolidated scope, units, publication/observed time, correction/restatement/version lineage, raw-byte archive, empty-result proof, 49/49 coverage and Mac-to-Windows delivery rights; distinguishes filing availability from parsed metric correctness; current announcement evidence cannot self-attest fundamentals; Planner freezes a non-overlapping whitelist only after location validation; implementation, if admitted, rejects future/revised/ambiguous/unit-mixed inputs and leaves production strategy, weights, calendar, E0/E1, direct/formal orchestration and submission status unchanged until separate integration; otherwise records DATA_BLOCKED without fake values; focused tests, scope, diff and independent Critic pass.
---

## Goal

Find the smallest first-party, legally archivable and Windows-replayable fundamental filing chain for all 49 contest issuers, with disclosure-time, period, statement-scope, unit, restatement and lineage semantics; implement a fixed trust-boundary Provider only if the source can fail closed.

## Non-goals

- Do not treat a filing title, announcement count or PDF presence as parsed
  fundamental evidence.
- Do not backfill a later corrected/restated statement into an earlier decision
  cutoff, use fiscal-period end as publication time, or use download time as
  historical `observed_at`.
- Do not combine parent-company and consolidated statements, currencies, units,
  accounting standards, unaudited/audited figures or cumulative/single-quarter
  values without an explicit normalized schema and deterministic derivation.
- Do not use Eastmoney, Sina, AkShare, generic search snippets or LLM-extracted
  PDF text as the authority for formal admission.  They may locate a first-party
  record but cannot replace it.
- Do not change current report grade, production strategy, portfolio, calendar,
  E0/E1, direct/formal orchestration, roles or submission status in the locate
  phase.  Do not delete or overwrite existing announcement/filing evidence.

## Invariants

- A historical decision at cutoff `d` may use only the latest statement version
  whose first-party publication timestamp is at or before `d`.  Corrections and
  restatements are new immutable versions with their own publication time and
  supersession link.
- Each observation binds security identifier, issuer, report period, filing
  type, statement/table and line-item identity, consolidated/parent scope,
  audited status, original value/unit/currency, normalized value/formula,
  publication/observed time, raw source bytes, source version and evidence hash.
- Missing, `--`, not-applicable, parse-failed and genuine numeric zero are
  different states.  Unknown data stays unknown/partial and never becomes 0.
- Coverage is assessed for all 49 tickers and every admitted metric at each
  claimed cutoff.  A source that serves only current/latest values or cannot
  prove empty results cannot be called PIT-complete.
- Filing discovery, raw-byte authenticity, table parsing, semantic mapping,
  derived metrics and report consumption are separate trust stages.  Success in
  an earlier stage cannot self-attest a later stage.
- Candidate derived metrics must preserve raw line items and define formulas,
  minimum comparable periods and denominator/zero/negative-equity behavior.
  Prefer a small auditable raw core before ratios such as growth, margins or ROE.

## Scout read scope

- `coordination/active/PIT-FUNDAMENTAL-0805.md`
- Existing announcement Provider/service, report models, evidence reference,
  report quality gate and company report renderer under
  `jiuwenswarm/jiuwenswarm/quant/reporting/`.
- Focused tests and direct/formal call sites found by `rg`; no history, strategy
  experiment logs, full output tree or unrelated runtime modules.
- First-party disclosure candidates evaluated separately: SSE issuer/full-text
  disclosure, SZSE issuer/full-text disclosure, CNINFO designated disclosure and
  any exchange XBRL/structured financial data service.  Record official legal/
  data-service terms and do not download bulk files before delivery rights are
  understood.

## Scout deliverable and stop conditions

- Write only `output/agent_handoffs/PIT-FUNDAMENTAL-0805/location.json` using
  the workflow schema.  The tracked task remains Planner-owned.
- Map the exact current seam that produces `fundamental grade=0` and the minimum
  schema that would change it without modifying production behavior in this
  task.
- For each candidate source, report query identity, pagination/empty semantics,
  timestamp precision/timezone, report/version identifiers, raw format and
  hashes, correction/supersession behavior, 49/49 sample coverage, rate/access
  constraints and repository/Windows redistribution rights.
- Test at least one renamed issuer, one amended/corrected report, one numeric
  zero versus missing value, one unit/scope ambiguity and one cutoff boundary.
- Stop at `DATA_BLOCKED` if historical versions, raw bytes, structured semantics
  or delivery rights cannot be proven.  Stop at `CONTRACT_BLOCKED` if the report
  consumer lacks a grade/metric contract.  Do not invent a local manifest to
  turn samples into trusted coverage.

## Invariants

- Preserve AGENTS.md and project safety contracts.

## Locate brief

- Scout findings were captured in the schema-valid
  `output/agent_handoffs/PIT-FUNDAMENTAL-0805/location.json`, SHA-256
  `d0cf01c9b2aa25a72c7ad530369a76b3c62d13bec5d584ac32adc25b7a5b8c2d`,
  confidence `0.96`.
- Disposition: `DATA_BLOCKED`; secondary disposition `CONTRACT_BLOCKED`.
  Public SSE/SZSE/CNINFO records can locate filings and raw PDFs, but this
  task did not prove a documented immutable structured line-item taxonomy,
  predecessor/supersession chain, sub-day publication-time contract, complete
  49/49 historical coverage and permission to archive and redistribute the
  source chain to Windows. CNINFO links a separate structured data-service/API
  portal, but no project-bound taxonomy/version/empty-result contract or
  entitlement semantics were captured; no claim is made that access is
  necessarily paid or prohibited.
- Reproducible metadata probes found annual-report records for 49/49 contest
  tickers (40 SSE, 9 CNINFO), but qualified structured line-item coverage is
  0/49. The 603501 sample proves name and cutoff drift; an SSE revision search
  returns revised filings without an explicit predecessor id. Two sampled SSE
  PDF downloads returned identical CDN bot-denial HTML rather than PDF bytes,
  so discovery could not be promoted to an automatable raw-byte archive.
- The exact consumer seam is
  `ReportService.build_company_bundle(fundamental_facts=...)` →
  `CompanyFactBundle` → `grade_submission`. The current grader treats any
  non-empty tuple of generic `MetricFact` as fundamental coverage even though
  that type cannot bind statement, line item, period, consolidated/parent
  scope, audit status, original unit/currency, filing version or correction
  lineage.
- Planner adjudication: do not implement a Provider or copy source PDFs in this
  task. Open a separate contract-hardening task that makes generic or
  semantically incomplete facts ineligible for a fundamental grade. That
  safety repair must not raise the current report grade or alter production.

## Implementation evidence

- No Provider, parser, archive, trust root or report fact was added. The
  official-data boundary remains closed and no historical evidence was
  overwritten.
- The existing focused grade/archive baseline was rerun before adjudication:
  `29 passed`. This is recorded as evidence of the permissive pre-change
  contract, not evidence that fundamental coverage exists.
- Frozen closure scope contains only this task, `VALIDATION.md` and the current
  discussion. Source code and runtime state remain identical to the task
  baseline.

## Review evidence

- Initial independent Critic review returned `REJECT`, P1=1, because the first
  location artifact did not record official URLs, exact query identities,
  response/sample hashes, 49/49 results, terms or reproducible boundary
  counterexamples. Review SHA-256:
  `b381753f7beee8654c6843abd592ab7da73197cbf283f61bd2a6f7822885f7fb`.
- The finding was accepted. The location artifact now includes exact SSE and
  CNINFO query contracts, official legal pages, response hashes, all 49
  metadata counts, rename/cutoff/revision samples, raw-byte denial evidence and
  explicit `NOT_TESTABLE` results for zero/missing and scope/unit semantics.
- Final independent re-review returned `ACCEPT`, P0/P1/P2/P3=`0/0/0/0`, bound
  diff SHA-256
  `5d29bc0fd2cd66db4fabf7d9678d015a9bdfbd86e333ac30762fb4242ef87a56`
  and location SHA-256
  `d0cf01c9b2aa25a72c7ad530369a76b3c62d13bec5d584ac32adc25b7a5b8c2d`.
  Final review SHA-256:
  `4f67dcb3c1421da1cafd4ed94d53997adc74a153a086126f2bf7620aff3b13af`.

## Progress

- 2026-08-05T18:21:39+08:00 `DRAFT`: Task created.
- 2026-08-05T18:31:09+08:00 `LOCATED`: First-party discovery paths do not prove the structured history, lineage or delivery rights required for admission; report grading also lacks a semantic fundamental contract.
- 2026-08-05T18:31:09+08:00 `READY`: Three-file documentation closure scope frozen; no Provider implementation authorized.
- 2026-08-05T18:45:00+08:00 `IMPLEMENTED`: Initial Critic P1 accepted; official URLs, query identities, sample/response hashes, 49/49 discovery versus 0/49 structured coverage and fail-closed untestable boundaries added for re-review.
- 2026-08-05T18:31:09+08:00 `LOCATED`: Write scope approved by Planner.
- 2026-08-05T18:31:09+08:00 `READY`: Baseline frozen; implementation may start.
- 2026-08-05T18:33:35+08:00 `IMPLEMENTED`: DATA_BLOCKED closure documented; no Provider or source data admitted.
- 2026-08-05T18:44:38+08:00 `REVIEWED`: Independent Critic ACCEPT after P1 reproducibility remediation; no open findings.
- 2026-08-05T18:44:38+08:00 `VERIFIED`: DATA_BLOCKED and CONTRACT_BLOCKED closure verified; no Provider/source/runtime admission.
- 2026-08-05T18:44:38+08:00 `CLOSED`: Read-only source task closed; follow-up fundamental grade contract task authorized.
