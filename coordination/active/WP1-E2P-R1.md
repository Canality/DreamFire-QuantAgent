---
id: WP1-E2P-R1
title: Windows LF trust roots and typed operate-evidence bridge
status: CLOSED
risk: HIGH
owner: Claude
created_at: 2026-08-10T17:11:22+08:00
updated_at: 2026-08-11T09:53:16+08:00
allowed_files:
  - .gitattributes
  - jiuwenswarm/evaluation/data_snapshots/sina_20260721_135352/manifest.json
  - jiuwenswarm/evaluation/research_evidence/official_calendar_2024_2026/calendar_sessions.csv
  - jiuwenswarm/evaluation/research_evidence/official_calendar_2024_2026/source_records.json
  - jiuwenswarm/jiuwenswarm/quant/candidate_factors.py
  - jiuwenswarm/jiuwenswarm/quant/factor_evidence_provider.py
  - jiuwenswarm/jiuwenswarm/quant/research_evidence_loader.py
  - jiuwenswarm/tests/unit_tests/quant/test_candidate_factors.py
  - jiuwenswarm/tests/unit_tests/quant/test_factor_evidence_provider.py
  - jiuwenswarm/tests/unit_tests/quant/test_research_evidence_loader.py
acceptance:
  - Exactly the three proven CRLF-affected pinned text paths are forced to LF with precise .gitattributes rules; current Windows worktree and a fresh checkout hash to the existing pinned bytes without runtime normalization or wildcard rules.
  - A public loader constructs typed CalendarEvidence and CorporateActionEvidence from hash-verified archives, uses the admitted yearType=operate dividOperateDate receipts, and preserves separate archive-byte admission hashes and per-window typed evidence hashes.
  - Calendar windows are contiguous slices of the full trusted calendar; qfq input is honestly labeled retrospective scale-invariant research evidence, and uncovered, future, tampered, untrusted, incomplete, or session-mismatched inputs fail closed.
  - A real-archive integration computes a strictly-prior 251-session, 49-stock x 12-factor snapshot through public compute_trend_snapshot with no network and no private kernel/trust bypass.
  - Focused tests, Ruff, py_compile, diff-check, scope-check, pinned-hash checks, and fresh-checkout LF verification pass; E2C/direct/formal/production/quant/__init__.py remain unchanged and no commit/push occurs.
---

## Goal

Restore cross-platform source-byte verification for the exact three CRLF-affected trust roots and build a public typed real-archive bridge using the newly admitted operate-year corporate-action archive, unblocking E2C without weakening trust or production boundaries.

## Non-goals

- No network fetch, archive regeneration, report-year corporate-action fallback, E2C replay, production activation, direct/formal/RPC changes, commit, or push.
- No runtime newline normalization, dual acceptance of CRLF/LF hashes, wildcard `.gitattributes`, trust allowlist weakening, private `_KERNELS` access, or local snapshot-hash recreation.
- No reuse of the rejected WP1-E2P assumption that report-year coverage can prove operate-date completeness.

## Invariants

- Preserve AGENTS.md and project safety contracts.
- The accepted operate archive and its pinned hashes are immutable inputs; this task consumes them and never rewrites their bytes or semantics.
- Provider-owned immutable trust roots remain the only archive admission authority; typed per-window hashes bind the derived evidence separately.
- Retrospective qfq bytes are never described as decision-time-observed prices; only mathematically scale-invariant derived factor values may carry a strictly-prior research claim.
- Existing user and E2A/E2B worktree changes remain untouched.

## Locate brief

- Reproduce the exact three Windows CRLF hash mismatches using worktree hash, pinned hash, git blob hash, and `git check-attr` evidence.
- Re-evaluate every previously accepted E2P design point against the newly admitted operate-year archive; delete obsolete report-year coverage assumptions.
- Locate public provider/inspector APIs for the official calendar, qfq snapshot, official universe, and operate corporate actions; no private trust or kernel bypass.
- Specify the typed dual-hash design, contiguous calendar-slice proof, retrospective scale-invariant policy, per-window `dividOperateDate` projection, and exact fail-closed cases.
- Propose an exact whitelist including `.gitattributes`, the three LF normalization targets, code, and tests; explain current-checkout and fresh-checkout verification without destructive commands.
- Write `output/agent_handoffs/WP1-E2P-R1/location.json`, validate it, set `LOCATED`, then stop without editing source/data or running network commands.

## Implementation evidence

- Pending.

## Review evidence

- Pending.

## Progress

- 2026-08-10T17:11:22+08:00 `DRAFT`: Task created.
- 2026-08-10T18:26:38+08:00 `LOCATED`: Write scope approved by Codex.
- 2026-08-10T18:26:40+08:00 `READY`: Baseline frozen; implementation may start.
- 2026-08-11T09:29:21+08:00 `IMPLEMENTED`: CRLF three-file LF fix via temp-index (real index untouched, LF+pinned); public loader bridge built (626 calendar + operate dual-hash + 8-tuple in_window_actions + scale_invariant policy); real 251-session 49x12 via public compute_trend_snapshot; focused tests pass; 2 stale out-of-scope provider test assertions flagged; awaiting Codex review
- 2026-08-11T09:37:35+08:00 `REVIEWED`: Codex decision MODIFY: typed operate projection and exact window are not fail-closed; provider regression suite remains red.
- 2026-08-11T09:37:36+08:00 `LOCATED`: Write scope approved by Codex.
- 2026-08-11T09:37:36+08:00 `READY`: Same original baseline reopened after first implementation MODIFY; whitelist expanded only for provider verifier and stale provider regressions.
- 2026-08-11T09:53:16+08:00 `REVIEWED`: Codex final review ACCEPT after independent counterexamples and 87-pass combined suite.
- 2026-08-11T09:53:16+08:00 `VERIFIED`: Independent Windows validation reproduced fail-closed evidence binding, pinned LF hashes, static checks, and exact combined test pass.
- 2026-08-11T09:53:16+08:00 `CLOSED`: Accepted and closed at LOCAL_IMPLEMENTED; E2C/direct/formal/business remain unrun.
