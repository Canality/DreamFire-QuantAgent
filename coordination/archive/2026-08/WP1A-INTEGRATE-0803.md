---
id: WP1A-INTEGRATE-0803
title: Locate WP1-A production integration boundary
status: CLOSED
risk: HIGH
owner: Goone
created_at: 2026-08-03T09:42:14+08:00
updated_at: 2026-08-04T10:37:21+08:00
allowed_files:
acceptance:
  - location maps shared data service, snapshot schema, direct/formal callers, report artifacts, and targeted tests
  - proposal preserves 49-ticker coverage and server-owned select-to-report boundaries
  - no source files modified during Scout
---

## Goal

Read-only localization for wiring canonical OHLCV/provider evidence, data-integrity fail-closed checks, and market/pool/sector regime reports into both direct and formal paths through shared services.

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

- 2026-08-03T09:42:14+08:00 `DRAFT`: Task created.
- 2026-08-03T09:46:13+08:00 `LOCATED`: Codex Scout: shared service absent; production fetch/snapshot discard required evidence. Split schema/service before entry adapters.
- 2026-08-04T10:37:21+08:00 `CLOSED`: Localization was completed and superseded by the closed WP1A contract/provider/direct/formal/e2e task chain; production facts remain governed by VALIDATION.md.
