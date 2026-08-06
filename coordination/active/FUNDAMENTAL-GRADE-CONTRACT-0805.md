---
id: FUNDAMENTAL-GRADE-CONTRACT-0805
title: Fail-close fundamental report-grade qualification
status: CLOSED
risk: HIGH
owner: Codex
created_at: 2026-08-05T18:48:08+08:00
updated_at: 2026-08-05T18:54:34+08:00
allowed_files:
  - .claude/discussion.md
  - VALIDATION.md
  - coordination/active/FUNDAMENTAL-GRADE-CONTRACT-0805.md
  - jiuwenswarm/jiuwenswarm/quant/reporting/models.py
  - jiuwenswarm/jiuwenswarm/quant/reporting/quality_gate.py
  - jiuwenswarm/jiuwenswarm/quant/reporting/report_grade.py
  - jiuwenswarm/jiuwenswarm/quant/reporting/report_service.py
  - jiuwenswarm/tests/unit_tests/quant/test_wp0cb_archive_grade.py
acceptance:
  - Scout maps every fundamental-fact constructor, grade counter and report/quality consumer; Planner freezes a non-overlapping whitelist; generic MetricFact, valuation quote, announcement title, single arbitrary line item, future publication, mismatched ticker/period/version/scope/audit/unit/currency, missing/zero collapse, correction without predecessor and incomplete required core must not count as fundamental coverage; a qualified core binds issuer/security, report period/type, statement and line-item identity, consolidated scope, audit status, raw and normalized values/units/currency, publication/observed time, evidence IDs/hashes, source version and correction lineage; current runtime bundles remain fundamental=0 and overall FINANCIAL_PARTIAL; no Provider, source data, report prose, production strategy, portfolio, calendar, E0/E1, direct/formal orchestration, roles or submission status changes; focused and adjacent tests, Ruff, scope/diff and independent Critic pass.
---

## Goal

Prevent generic or semantically incomplete facts from raising the fundamental
coverage count. Define the smallest immutable qualification contract that a
future trusted Provider must satisfy before a company can receive fundamental
grade credit.

## Non-goals

- Do not implement or register a financial-data Provider.
- Do not download, parse, archive or redistribute any filing or source bytes.
- Do not add synthetic financial facts to direct/formal reports or change any
  current company/report grade upward.
- Do not change the meaning of technical, disclosure, news or risk coverage in
  this task; report-grade redesign outside fundamental qualification requires a
  separate task.
- Do not alter production strategy, holdings, decision calendar, Factor
  Registry/E0/E1, roles, RPCs, orchestration or SubmissionContract.

## Invariants

- A generic `MetricFact` remains renderable in its existing categories but can
  never self-attest as qualified fundamental coverage.
- Qualification is deterministic and local. It does not trust a caller-provided
  boolean, provider status or opaque coverage count.
- Every accepted observation must be available at or before the bundle decision
  time and refer to the same security. Period end is not publication time;
  retrieval time is not historical availability.
- Missing, unavailable, parse-failed, stale and genuine numeric zero stay
  distinct. A zero may qualify only as an explicit numeric source observation,
  never as a missing-value default.
- A correction/revision is a new immutable source version. If marked corrected,
  it must bind an explicit superseded evidence/version identity.
- Fundamental grade credit requires a coherent required core from one report
  period/type and one source version, not a mixture of unrelated periods,
  parent/consolidated statements, units or audit states.
- Current runtime supplies no qualified fundamental facts, so this task may keep
  or lower an unsafe synthetic-test grade but must not raise real coverage.

## Scout read scope

- `coordination/active/FUNDAMENTAL-GRADE-CONTRACT-0805.md`
- `output/agent_handoffs/PIT-FUNDAMENTAL-0805/location.json`
- `jiuwenswarm/jiuwenswarm/quant/reporting/models.py`
- `jiuwenswarm/jiuwenswarm/quant/reporting/report_grade.py`
- `jiuwenswarm/jiuwenswarm/quant/reporting/quality_gate.py`
- `jiuwenswarm/jiuwenswarm/quant/reporting/report_service.py`
- `jiuwenswarm/jiuwenswarm/quant/reporting/company_report.py`
- Focused tests and constructors found by `rg`; no history, source browsing,
  production entry-point edits or unrelated output.

## Scout deliverable

- Write only
  `output/agent_handoffs/FUNDAMENTAL-GRADE-CONTRACT-0805/location.json` using the
  workflow schema.
- Recommend the minimum type/helper boundary, the exact required core and
  whether `CompanyFactBundle` can remain backward-compatible while grading
  rejects generic facts.
- Enumerate negative tests for type confusion, future data, ticker mismatch,
  period/version/scope mixing, correction lineage, zero/missing, evidence and
  incomplete core. Map all existing tests that encode the permissive rule.

## Locate brief

- Scout artifact:
  `output/agent_handoffs/FUNDAMENTAL-GRADE-CONTRACT-0805/location.json`,
  schema-valid at confidence `0.98`, SHA-256
  `84030e36ee70dea50a78007eda999dd6194be8a92ba5f932a704b92d55f9e471`.
- Exact unsafe seam: `CompanyFactBundle.fundamental_facts` is a generic,
  renderable `MetricFact` tuple, while `grade_bundle` and `grade_submission`
  currently award fundamental credit from tuple truthiness alone. Four existing
  tests encode that permissive behavior. Runtime direct/formal constructors
  currently leave the tuple empty.
- Planner adjudication follows the Scout's smaller boundary: keep generic
  `fundamental_facts` backward-compatible and render-only; add a separate frozen
  `qualified_fundamental_reports` tuple with explicit report and four-line core
  types; let only a deterministic grader helper consume it. The shared
  `ReportService` may forward the new optional tuple, but no current caller will
  populate it.
- Frozen minimum core is one annual, consolidated, audited, CNY filing version
  containing exactly operating revenue, attributable net profit, total assets
  and attributable equity with correct statement mappings and normalized
  values. A unique explicit terminal correction version must qualify; an
  available invalid correction, fork, cycle or multiple terminal cannot fall
  back to its predecessor.

## Implementation evidence

- Immutable qualification-only filing/line-item types and a deterministic
  correction-chain resolver now separate grade semantics from generic rendered
  facts. Current callers default the new tuple to empty.
- The quality gate rejects self-attested cores unless the manifest binds exact
  financial-statement source type, period, publication/availability timestamps
  and hash, and the evidence ID resolves in the immutable archive.
- Focused tests: `63 passed`; adjacent report/model/Provider/quality tests:
  `136 passed, 1 skipped`; changed-file Ruff and `git diff --check` pass.
- `scope_check.json` reports all 8 changed tracked files inside the expanded
  whitelist with no violations. Detailed commands and exit codes are in
  `implementation.json`.

## Review evidence

- Independent Critic ran three adversarial rounds. The first two correctly
  returned `MODIFY` and reproduced seven P1/P2 issues; every counterexample was
  converted to a regression and closed.
- Final decision `ACCEPT`, P0/P1/P2/P3=`0/0/0/0`; all seven previous findings
  closed. The Critic replayed identity-group correction escapes, malformed
  containers/items, archive hash/source/embedded-ID mismatches, valid positive
  binding and the 12-ID linear-scaling counter.
- Final `review.json` SHA-256:
  `76a35a77331e0fbb937fa0b3648c6f04fe49545196aa3b236265000324c191be`.

## Progress

- 2026-08-05T18:48:08+08:00 `DRAFT`: Task created from the accepted contract blocker; no Provider or grade change authorized.
- 2026-08-05T18:54:33+08:00 `LOCATED`: Write scope approved by Planner.
- 2026-08-05T18:54:34+08:00 `READY`: Baseline frozen; implementation may start.
- 2026-08-05T19:00:00+08:00 `SCOPE-CHALLENGE`: Planner expanded the
  whitelist before editing `quality_gate.py`. The qualification core would
  otherwise self-attest its evidence ID/hash without manifest binding or
  archive resolution. The original whole-tree freeze already records the
  file's pre-edit SHA-256, so the baseline was not regenerated after code
  changes.
- 2026-08-05T19:04:00+08:00 `IMPLEMENTED`: Builder evidence written; focused,
  adjacent, Ruff, diff and scope checks pass. Awaiting independent Critic.
- 2026-08-05T19:11:00+08:00 `MODIFY`: Independent Critic reproduced two P1
  bypasses (external manifest versus archive-internal content, and correction
  identity-group escape) plus malformed-type crashes and incomplete diff
  evidence. Planner rejected the first implementation.
- 2026-08-05T19:15:00+08:00 `REPAIRED`: Archive bytes/internal `EvidenceRef`
  now match the supplied manifest exactly; correction edges preserve immutable
  identity and strict time order; malformed line items fail closed. The missing
  frozen `quality_gate.py` copy was restored from `HEAD` only after its SHA-256
  matched the recorded pre-edit baseline; regenerated diff now contains exact
  hunks. Focused 58/58 and adjacent 131/132 (1 expected skip) pass.
- 2026-08-05T19:18:00+08:00 `MODIFY-2`: Critic confirmed all first-round
  findings closed, then found an embedded evidence-ID mismatch, mutable/scalar
  top-level container handling and quadratic archive verification. Planner
  again withheld acceptance.
- 2026-08-05T19:20:00+08:00 `REPAIRED-2`: Manifest key, embedded ID, core ID,
  archive metadata and raw-byte hash now form one identity. Qualification
  accepts only an immutable tuple and rejects every malformed member. Archive
  manifest verification is built once and raw entries are checked linearly;
  a 12-ID regression proves one manifest build and at most 24 reads. Focused
  63/63 and adjacent 136/137 (1 expected skip) pass.
- 2026-08-05T19:23:00+08:00 `REVIEWED`: Final independent Critic `ACCEPT`;
  P0/P1/P2/P3=`0/0/0/0`, seven prior findings closed.
- 2026-08-05T19:23:10+08:00 `VERIFIED`: Planner reproduced scope, focused,
  adjacent, Ruff, diff and review-artifact checks; current runtime grade remains
  unchanged because no production caller populates the new tuple.
- 2026-08-05T19:23:20+08:00 `CLOSED`: Contract blocker closed; external
  structured fundamental data remains separately `DATA_BLOCKED`.
