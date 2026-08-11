---
id: WP1-E2T-R1
title: Revalidate typed research bridge on v2 causal labels
status: CLOSED
risk: HIGH
owner: Claude
created_at: 2026-08-11T12:28:03+08:00
updated_at: 2026-08-11T13:55:53+08:00
allowed_files:
  - coordination/active/WP1-E2T-R1.md
acceptance:
  - A read-only location artifact proves every typed bridge definition, caller, test and provider identity affected by the v2 migration and proposes the smallest exact whitelist; no implementation occurs before Codex freeze.
  - Public load_forward_labels returns exactly 604 v2 labels with decision+2 entry, 20 valuation sessions, decision+21 exit, 49 tickers and provider-owned full-payload verification; legacy v1 identity and arbitrary self-consistent tampering fail closed.
  - At least eight strictly-prior non-overlapping matured observations pass the public compute_factor_research_snapshot path under the Windows project venv with no network, monkeypatch trust, private kernel or replay-local rank-IC copy.
  - Focused tests, generator committed-byte equality, provider readiness, Ruff, py_compile, diff-check and scope-check pass; no E2C replay, production/direct/formal/RPC/archive/docs/quant/__init__.py change, commit or push occurs in this task.
---

## Goal

Re-freeze and verify the public FactorSnapshot/OfficialForwardLabel/SectorMetadata trust bridge against the accepted official_forward_label_2024_2026/v2 archive, preserving exact full-embargo causality before E2C replay.

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

- 2026-08-11T12:28:03+08:00 `DRAFT`: Task created.
- 2026-08-11T12:38:43+08:00 `BLOCKED`: Claude interactive session context hard limit; compaction also exceeds provider limit; awaiting clean replacement session
- 2026-08-11T13:03:41+08:00 `DRAFT`: Clean replacement Claude session established; resuming read-only location
- 2026-08-11T13:08:14+08:00 `LOCATED`: Read-only location complete: v2 typed bridge (decision+2 entry/20 valuations/decision+21 exit, 604 labels, 49 tickers, v2 identity + legacy-v1 reject) already implemented by WP1-E2L-R1; evidence-only revalidation suffices; no source change needed.
- 2026-08-11T13:11:51+08:00 `LOCATED`: Write scope approved by Codex.
- 2026-08-11T13:11:52+08:00 `READY`: Baseline frozen; implementation may start.
- 2026-08-11T13:25:33+08:00 `IMPLEMENTED`: Evidence-only revalidation complete: 99 passed/1 skipped focused; OFFICIAL_FORWARD_LABEL AVAILABLE; 604/604 v2 labels (decision+2/20 vals/decision+21/49 tickers); 8 matured observations -> 12 metrics, snapshot hash 07ad5456...; generator byte-equal + ruff + py_compile + diff-check pass; scope-check only Codex-owned discussion item.
- 2026-08-11T13:29:36+08:00 `REVIEWED`: Codex MODIFY: original scope gate failed and public-path heredoc was not exactly replayable
- 2026-08-11T13:29:38+08:00 `READY`: Baseline frozen; implementation may start.
- 2026-08-11T13:36:17+08:00 `IMPLEMENTED`: MODIFY evidence corrections applied: exact script output/agent_handoffs/WP1-E2T-R1/revalidate_public_bridge.py saved and run unchanged (log exit_code=0, snapshot_hash 07ad5456...); scope-check passed=true violations=[] on corrected baseline; no source/test/archive/docs/discussion change.
- 2026-08-11T13:55:53+08:00 `REVIEWED`: ACCEPT: independent review found no product-source drift; public replay and focused negative tests passed
- 2026-08-11T13:55:53+08:00 `VERIFIED`: Codex independently reproduced public bridge snapshot and key fail-closed cases on Windows
- 2026-08-11T13:55:53+08:00 `CLOSED`: Closed at LOCAL_IMPLEMENTED; E2C remains a separate frozen task
