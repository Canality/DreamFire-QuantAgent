---
id: WP1-E2O-R1
title: Operate archive identity and row-width repair
status: CLOSED
risk: HIGH
owner: Claude
created_at: 2026-08-10T14:44:26+08:00
updated_at: 2026-08-10T15:09:43+08:00
allowed_files:
  - jiuwenswarm/jiuwenswarm/quant/factor_evidence_provider.py
  - jiuwenswarm/scripts/fetch_corporate_action_operate.py
  - jiuwenswarm/tests/unit_tests/quant/test_corporate_action_operate_archive.py
  - jiuwenswarm/tests/unit_tests/quant/test_factor_evidence_provider.py
acceptance:
  - One canonical duplicate identity definition, including ticker, is shared by generator receipt/global counting, provider CSV validation, and receipt reconstruction.
  - Every receipt row must be a list whose width exactly equals fields; truncated and extra-width rows fail closed.
  - Regression coverage includes equal action attributes across different tickers and same canonical identity with differing non-identity fields, and a generated archive is accepted by the paired provider.
  - No network, BaoStock fetch, archive generation, hash pinning, capability AVAILABLE claim, E2P/E2C edits, commit, or push.
---

## Goal

Repair the three independently reproduced WP1-E2O admission defects under a fresh versioned task, without network access or archive generation.

## Non-goals

- No BaoStock connection, network fetch, real archive generation, source hash pinning, or trusted-key admission.
- No E2P/E2C, report-year archive, direct/formal/production, `quant/__init__.py`, documentation, commit, or push changes.
- No unrelated refactor and no reopening or rewriting the rejected WP1-E2O review history.

## Invariants

- Preserve AGENTS.md and project safety contracts.
- WP1-E2O remains `REVIEWED/REJECT`; this repair starts from a fresh task baseline only after location acceptance.
- Canonical action identity is exactly `(ticker, dividOperateDate, normalized economic identity fields)` and must not merge actions across tickers.
- Receipt, manifest, CSV, and reconstruction must use compatible duplicate semantics and reject malformed shapes before projection.
- Existing user and E2A/E2B worktree changes remain untouched.

## Locate brief

- Read only the four allowed files and the final `output/agent_handoffs/WP1-E2O/review.json`.
- Enumerate every identity construction and duplicate-count caller in generator/provider/tests.
- Propose one shared formula or two mechanically identical local formulas, including treatment of non-identity fields.
- Show how an offline generator output will be handed to the provider inspector in one positive integration regression.
- Identify the exact row-shape checks required before hashing, date access, duplicate counting, and reconstruction.
- Write `output/agent_handoffs/WP1-E2O-R1/location.json`, validate it, set `LOCATED`, then stop without editing source.

## Implementation evidence

- Pending.

## Review evidence

- Pending.

## Progress

- 2026-08-10T14:44:26+08:00 `DRAFT`: Task created.
- 2026-08-10T14:52:18+08:00 `READY`: Baseline frozen; implementation may start.
- 2026-08-10T15:03:40+08:00 `IMPLEMENTED`: unified canonical identity across all five sites; row-shape precedence enforced before hash/date/count/projection; four regression classes added incl generator->provider integration; offline verification done, awaiting Codex review
- 2026-08-10T15:09:43+08:00 `REVIEWED`: Codex independent review ACCEPT; direct counterexamples and 294-receipt offline generator-to-provider chain reproduced.
- 2026-08-10T15:09:43+08:00 `VERIFIED`: Offline repair acceptance reproduced independently; no network or real archive claim.
- 2026-08-10T15:09:43+08:00 `CLOSED`: Closed after VERIFIED offline repair. BaoStock fetch/hash/trusted-key admission remains a separate unauthorized gate.
