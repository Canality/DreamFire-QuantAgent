---
id: WP1-E2L-R1
title: Regenerate causal official 1+20 forward-label archive
status: CLOSED
risk: HIGH
owner: Claude
created_at: 2026-08-11T11:48:08+08:00
updated_at: 2026-08-11T12:27:01+08:00
allowed_files:
  - jiuwenswarm/evaluation/research_evidence/official_forward_label_2024_2026_v2/forward_labels.csv
  - jiuwenswarm/evaluation/research_evidence/official_forward_label_2024_2026_v2/source_records.json
  - jiuwenswarm/jiuwenswarm/quant/factor_evidence_provider.py
  - jiuwenswarm/jiuwenswarm/quant/research_evidence_loader.py
  - jiuwenswarm/scripts/generate_official_forward_labels.py
  - jiuwenswarm/tests/unit_tests/quant/test_factor_evidence_provider.py
  - jiuwenswarm/tests/unit_tests/quant/test_research_evidence_loader.py
acceptance:
  - A read-only location artifact identifies the authoritative qfq/calendar inputs, existing archive generator, provider pins, all consumers and the smallest exact write whitelist; no implementation occurs before Codex freezes a new baseline.
  - The proposed archive schema binds decision_date, embargo_date, entry_open_date, 20 valuation dates, exit_close_date, 49 ticker prices, source identities and recomputable hashes, and proves every row's dates against the canonical calendar.
  - Migration preserves the frozen one-full-session embargo contract; it must not reinterpret old next-session prices, use network data, alter production/direct/formal/RPC paths, or claim BUSINESS_PASSED from local evidence.
  - The plan includes deterministic regeneration, old/new archive isolation, provider repinning, negative tamper/date-shift tests, E2T re-freeze steps, rollback and Windows validation.
---

## Goal

Replace the incompatible next-session-entry label archive with a reproducible pinned archive that exactly follows decision close -> one full trading-session embargo -> following entry open -> twentieth valuation close, while preserving 49-stock coverage and provider-owned provenance.

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

- 2026-08-11T11:48:08+08:00 `DRAFT`: Task created.
- 2026-08-11T11:53:51+08:00 `LOCATED`: read-only location: root cause = forward_labels.csv entry_open_date/prices are decision+1 (embargo session) vs frozen decision+2 entry contract; qfq+calendar cover correct entry/exit for all 604 decisions (NOT BLOCKED); no generator in repo -> new deterministic generator + versioned archive + repin proposed
- 2026-08-11T11:56:46+08:00 `LOCATED`: Write scope approved by Codex.
- 2026-08-11T11:56:48+08:00 `READY`: Baseline frozen; implementation may start.
- 2026-08-11T12:10:41+08:00 `IMPLEMENTED`: v2 full-embargo 604-label archive generated deterministically (decision+2 entry, decision+21 exit, 49x604, qfq prices); provider repinned to v2; loader reads v2 with fail-closed projection/entry/evidence checks; 96 passed / 1 env-dependent (venv passes); awaiting Codex review
- 2026-08-11T12:14:38+08:00 `REVIEWED`: Codex MODIFY: v2 archive still uses legacy v1 source_version identity; see review.json
- 2026-08-11T12:14:38+08:00 `READY`: Reopened on unchanged seven-file whitelist/baseline for v2 identity correction
- 2026-08-11T12:22:35+08:00 `IMPLEMENTED`: v2 source identity corrected: provider trusted tuple + loader _LABEL_VERSION = official_forward_label_2024_2026/v2; v2 admitted, legacy v1 rejected (regression tests added); archive bytes unchanged; 98 passed / 1 env-dependent; awaiting Codex review
- 2026-08-11T12:27:01+08:00 `REVIEWED`: Codex ACCEPT: v2 source identity and deterministic causal archive independently verified
- 2026-08-11T12:27:01+08:00 `VERIFIED`: Windows project-venv provider+loader 67 passed, 1 skipped; v2 identity accepted and v1 rejected
- 2026-08-11T12:27:01+08:00 `CLOSED`: Closed at LOCAL_IMPLEMENTED; E2T/E2C require separate re-freeze and validation
