---
id: WP1-E2T
title: Typed factor-snapshot and forward-label trust bridge
status: CLOSED
risk: HIGH
owner: Claude
created_at: 2026-08-11T10:16:51+08:00
updated_at: 2026-08-11T17:35:45+08:00
allowed_files:
  - jiuwenswarm/jiuwenswarm/quant/candidate_factors.py
  - jiuwenswarm/jiuwenswarm/quant/factor_research.py
  - jiuwenswarm/jiuwenswarm/quant/research_evidence_loader.py
  - jiuwenswarm/tests/unit_tests/quant/test_candidate_factors.py
  - jiuwenswarm/tests/unit_tests/quant/test_factor_research.py
  - jiuwenswarm/tests/unit_tests/quant/test_research_evidence_loader.py
acceptance:
  - Public loaders construct per-decision FactorSnapshot and OfficialForwardLabel objects from current hash-verified archives and the trusted calendar; archive-byte admission hashes remain separate from typed per-window hashes.
  - Public factor research accepts genuine loader-built matured observations only after provider-owned verification of current archive bytes, exact decision window, 49-ticker coverage, calendar binding and recomputable typed payload; arbitrary snapshot or label hashes fail closed.
  - A real offline integration computes at least one factor-research snapshot from multiple strictly-prior matured observations with no network, private kernel access, trust monkeypatch or replay-local rank-IC copy.
  - Negative tests cover archive tamper, source-record tamper, modified factor values/status/hash, wrong decision/calendar/window/ticker set, future or immature labels, duplicate/missing rows and caller-injected paths/hashes.
  - Only bridge/provider/factor-research code and focused tests may change; E2C replay, production, direct/formal/RPC, archives and quant/__init__.py remain unchanged; focused tests, Ruff, py_compile, diff-check and scope-check pass.
---

## Goal

Expose a public fail-closed bridge from the pinned E0 qfq and official 1+20 label archives into per-decision FactorSnapshot and OfficialForwardLabel objects accepted by the existing public factor-research path, without replay-local trust bypasses.

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

- 2026-08-11T10:16:51+08:00 `DRAFT`: Task created.
- 2026-08-11T10:46:22+08:00 `LOCATED`: Write scope approved by Codex.
- 2026-08-11T10:46:23+08:00 `READY`: Baseline frozen; implementation may start.
- 2026-08-11T11:18:52+08:00 `IMPLEMENTED`: typed factor-snapshot + forward-label trust bridge implemented (dual-hash admission, provider-gated verify_factor_snapshot/verify_forward_label, 604-label loader, 8-observation real factor-research integration); 56 passed / 1 environment-dependent failure; awaiting Codex review
- 2026-08-11T11:27:51+08:00 `REVIEWED`: Codex review MODIFY: sector metadata typed projection can be forged while preserving archive admission; see review.json
- 2026-08-11T11:27:51+08:00 `READY`: Reopened on unchanged frozen baseline and whitelist for bounded sector-verifier correction
- 2026-08-11T11:40:37+08:00 `IMPLEMENTED`: MODIFY round: sector typed-projection verifier added (provider-admit + authoritative workbook rebuild + full to_dict compare), SectorMetadataEvidence.validate wraps it via function-local import; 4 sector negative tests added (swap rejected in public factor-research path, wrong fields/order); 60 passed / 1 env-dependent (venv 61 passed); awaiting Codex review
- 2026-08-11T11:47:53+08:00 `REVIEWED`: Codex review BLOCKED: all 604 pinned labels bind next-session entry-open prices to decision+2 typed entry dates
- 2026-08-11T11:47:53+08:00 `BLOCKED`: Authoritative archive conflicts with frozen one-full-session embargo contract; replacement archive task required
- 2026-08-11T17:35:45+08:00 `CLOSED`: Superseded by fresh-baseline task WP1-E2T-R1, accepted and closed after the corrected v2 labels and public typed evidence bridge passed focused validation; this stale baseline must never be reused.
