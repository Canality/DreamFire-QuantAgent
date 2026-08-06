---
id: HISTORY-DOCS-0805
title: Introduce versioned history archive and slim current context
status: CLOSED
risk: HIGH
owner: Codex
created_at: 2026-08-05T10:32:52+08:00
updated_at: 2026-08-05T11:07:00+08:00
allowed_files:
  - .claude/discussion.md
  - AGENTS.md
  - AGENT_WORKFLOW.md
  - CLAUDE.md
  - DEVELOPMENT_PLAN.md
  - README.md
  - VALIDATION.md
  - coordination/active/HISTORY-DOCS-0805.md
  - history/README.md
  - history/v2.13_2026-07-30.md
  - history/v2.14_2026-08-05.md
  - jiuwenswarm/tests/unit_tests/quant/test_document_contract.py
acceptance:
  - history index and real-version files exist; migrated records retain headings, evidence and limitations; README/VALIDATION/discussion no longer carry redundant historical timelines; AGENTS/AGENT_WORKFLOW/CLAUDE define append-only history boundaries; documentation tests, links, frozen scope and independent Critic pass.
---

## Goal

Create a Git-managed history/ archive keyed by real project version and date; preserve complete change records while keeping current identity and fact documents concise.

## Non-goals

- Do not change production code, strategy, evidence status or package version.
- Do not invent version numbers or Git tags for intermediate work packages.
- Do not archive the still-actionable Windows v2.14 re-verification handoff.
- Do not delete raw Git, coordination/archive or output evidence.

## Invariants

- `VALIDATION.md` remains the sole current run-state source.
- `DEVELOPMENT_PLAN.md` remains the sole current route/acceptance source.
- `history/` is Git-managed and append-only, but is never injected as current
  identity or used to upgrade an evidence grade.
- Historical commands, hashes, failures, limitations and superseded judgments
  are preserved under real project-version boundaries.

## Locate brief

- Independent read-only Scout confidence: 0.97.
- Real project boundaries are v2.13 commit `170e904` (2026-07-30) and v2.14
  commit `89322cd` (2026-08-05); neither is a matching Git tag.
- Move validation sections 0–4 to v2.13, sections -15 through -1 and closed
  August 4 handoffs to v2.14. Keep the latest Windows handoff current.
- Correct three stale current-risk statements after archival: announcements are
  complete, WP1-B embargo/nested evaluation is implemented, and WP1-C stopped.
- Location artifact: `output/agent_handoffs/HISTORY-DOCS-0805/location.json`.

## Implementation evidence

- Added `history/README.md` with exact naming, real commit mapping,
  append-only/Erratum rules, evidence hierarchy and default non-loading policy.
- Added v2.13/v2.14 version files. Canonical markers preserve the complete
  source validation snapshots and closed v2.14 discussion; SHA-256 contract
  tests bind the snapshots byte-for-byte after newline normalization.
- Reduced current `VALIDATION.md` from 510 to 151 lines and current discussion
  from 250 to 85 lines while retaining latest session, candidate bindings,
  tests, Critic verdict, current blockers and actionable Windows handoff.
- Corrected current stale statements: announcement evidence is complete;
  WP1-B embargo/nested evaluation exists; WP1-C stopped without promotion.
- Updated AGENTS/AGENT_WORKFLOW/CLAUDE identities, README navigation and
  DEVELOPMENT_PLAN 1.9.0 without changing production code or evidence grade.
- Replaced the active quick-test command that disabled pytest plugin autoload;
  the normal-plugin validator run passes 8/8. Updated current R1/E1 route facts
  to 49/49 announcements and the 97,209-input/12-call formal candidate.
- Document-contract set excluding the known absent resource mirror:
  8 passed, 9 deselected. Ruff, diff-check and frozen scope-check passed.

## Review evidence

- Independent Critic final verdict: `ACCEPT`; open P0/P1/P2/P3: 0.
- Initial review found one P1 in the active pytest command and one P2 in stale
  DEVELOPMENT_PLAN R1/E1 wording. Both were fixed, protected by contract tests
  and independently re-run before acceptance.
- Review artifact:
  `output/agent_handoffs/HISTORY-DOCS-0805/review.json`.
- Review SHA-256:
  `00ef223cf9dd1cfb43148ca3d2bc386f8d95a697e7a57b2c4436768df66cb3f4`.
- Independent checks: history/document 8/8; normal-plugin validator 8/8;
  Ruff, diff-check, scope-check, links and three canonical byte comparisons pass.
- Full document-contract module remains 9 failed / 8 passed solely because the
  baseline lacks the out-of-scope resource Skill mirror; this known limitation
  is not altered or hidden by this documentation task.

## Progress

- 2026-08-05T10:32:52+08:00 `DRAFT`: Task created.
- 2026-08-05T10:38:08+08:00 `LOCATED`: Write scope approved by Planner.
- 2026-08-05T10:38:09+08:00 `READY`: Baseline frozen; implementation may start.
- 2026-08-05T10:48:00+08:00 `IMPLEMENTED`: Version archive, current-document slimming, identity rules and canonical evidence tests complete; independent Critic pending.
- 2026-08-05T11:03:25+08:00 `REVIEWED`: Initial Critic rejected one P1 and one P2; both were fixed and independently re-tested.
- 2026-08-05T11:05:11+08:00 `VERIFIED`: Final Critic accepted with zero open findings; all task-scoped gates pass.
- 2026-08-05T11:07:00+08:00 `CLOSED`: Documentation governance task closed for task-scoped commit and Windows re-verification.
