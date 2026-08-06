---
id: IDENTITY-CHALLENGE-0805
title: Make frozen contracts challengeable through user-authorized unfreeze
status: CLOSED
risk: LOW
owner: Codex
created_at: 2026-08-05T18:10:05+08:00
updated_at: 2026-08-05T18:17:20+08:00
allowed_files:
  - .claude/discussion.md
  - AGENTS.md
  - coordination/active/IDENTITY-CHALLENGE-0805.md
  - jiuwenswarm/tests/unit_tests/quant/test_document_contract.py
acceptance:
  - AGENTS.md identity explicitly distinguishes obey, challenge and unfreeze; disputed frozen rules remain enforced while a challenge is pending; the Agent asks the user only when the change alters product intent, external authority or a material safety boundary; clear evidence and a scoped alternative are required; user approval creates a new versioned task/contract rather than an undocumented bypass; current production/data/submission states are unchanged; document contract, scope, diff and independent Critic pass.
---

## Goal

Record in the active Agent identity that frozen rules are default safety boundaries rather than unquestionable truth, and define evidence-backed challenge, user escalation and explicit unfreeze behavior without permitting silent bypass.

## Non-goals

- Do not reinterpret this rule as permission to ignore a frozen contract,
  silently widen a task whitelist, weaken fail-closed behavior or change
  production/data/submission state before adjudication.
- Do not interrupt the user for ordinary implementation choices that can be
  resolved from current evidence within an already authorized task.
- Do not make every constant configurable.  Deterministic constants remain
  appropriate when their role, version and migration boundary are explicit.
- Do not change any current production strategy, factor threshold, Provider
  trust root, submission contract, task status or external permission.

## Invariants

- A frozen or hard-coded rule is a versioned default safety boundary, not an
  unquestionable fact and not permanent proof that its design is optimal.
- While a challenge is pending, the current rule remains enforced.  An Agent
  cannot use its own objection as authority to bypass it.
- A challenge must identify the disputed proposition, concrete evidence or
  counterexample, a scoped alternative, affected files/behavior, risks and a
  verification plan.  Preference alone does not pause work.
- Ask the user when the proposed change alters product intent, an official or
  external authority, risk tolerance, a material safety/evidence boundary, or
  requires new permission.  Otherwise the Planner may adjudicate a reversible,
  task-scoped technical improvement under the existing workflow.
- Approval creates an explicit new task/contract version, whitelist, negative
  tests and migration record.  Rejected or unanswered challenges preserve the
  current frozen rule and allow unrelated authorized work to continue.

## Locate brief

- Scout artifact `output/agent_handoffs/IDENTITY-CHALLENGE-0805/location.json`
  is schema-valid at confidence `0.98`, SHA-256
  `bff978f5709714b103a80b25113edc69986ac04c2d8fc90d1148ba6bf523e2f1`.
- The smallest identity location is immediately after the role statement in
  `AGENTS.md`, before current architecture.  `CLAUDE.md` already defines the
  evidence-backed challenge/adjudication mechanics and `AGENT_WORKFLOW.md`
  already supplies versioned tasks, whitelists and frozen baselines; duplicating
  the new rule there would create drift.
- Planner accepts the recommended four-file whitelist: task contract, active
  identity, one durable document-contract test and current discussion.  No
  runtime fact, plan, history, production or Provider file is writable.

## Implementation evidence

- `AGENTS.md` now distinguishes obey, challenge and unfreeze in the active
  identity.  Frozen/hard-coded/adjudicated rules remain the default contract;
  evidence-backed objections are required; pending objections cannot authorize
  bypass; user escalation is reserved for product intent, external authority or
  material safety/evidence boundaries; approval creates a versioned migration.
- Added a durable document-contract test for the required positive semantics
  and forbidden shortcuts.  The first run exposed only a line-wrap-sensitive
  assertion; whitespace normalization fixed the test without changing the
  identity rule.  Final focused result: `2 passed`; Ruff passed.
- No plan, runtime, production, Provider, submission, history or validation
  state changed.

## Review evidence

- Independent Critic bound baseline `dd38f34c2f8b8e5d5f7d675d89b0e9aed265b472`
  and diff `e44894c7b39510e1ee27ccd38ff9ba67dc51a63d92071439cfe88bf108156e82`,
  then returned `ACCEPT`, P0/P1/P2/P3=`0/0/0/0`; review SHA-256
  `7190cede3d080d0e2ebc47df7efcd7e7eb028914cccf71f2afdae02405481726`.
- Critic attacked self-unfreeze, silent bypass/whitelist expansion, user
  over-escalation, global pause, undocumented post-approval edits and current
  production/PIT/submission state changes; all passed.
- Full document module remains honestly non-green at `9 passed / 9 failed`
  versus baseline `8 passed / 9 failed`; the same nine failures are the known
  missing ignored resource Skill mirror, while this task adds one passing test
  and no regression.

## Progress

- 2026-08-05T18:10:05+08:00 `DRAFT`: Task created.
- 2026-08-05T18:12:30+08:00 `LOCATED`: Scout validated at confidence 0.98; minimal identity edit is AGENTS.md plus a durable document-contract test.
- 2026-08-05T18:12:30+08:00 `LOCATED`: Write scope approved by Planner.
- 2026-08-05T18:12:31+08:00 `READY`: Baseline frozen; implementation may start.
- 2026-08-05T18:12:31+08:00 `READY`: Four-file governance whitelist frozen; no runtime or plan state is writable.
- 2026-08-05T18:13:48+08:00 `IMPLEMENTED`: Active identity now defines evidence-backed challenge and versioned unfreeze; focused document tests 2/2 and Ruff pass.
- 2026-08-05T18:17:20+08:00 `REVIEWED`: Independent Critic ACCEPT; P0/P1/P2/P3=0/0/0/0 on self-unfreeze and over-escalation attacks.
- 2026-08-05T18:17:20+08:00 `VERIFIED`: Focused document contracts 2/2, Ruff, diff and exact four-file scope pass; no runtime state changed.
- 2026-08-05T18:17:20+08:00 `CLOSED`: Active identity now treats frozen rules as challengeable versioned defaults without authorizing silent bypass.
