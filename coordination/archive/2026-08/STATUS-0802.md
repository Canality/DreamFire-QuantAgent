---
id: STATUS-0802
title: Audit latest A0/A1/A2 and WP1-A blockers
status: CLOSED
risk: HIGH
owner: Codex
created_at: 2026-08-02T18:08:40+08:00
updated_at: 2026-08-03T09:38:19+08:00
allowed_files:
acceptance:
  - location.json names current implementations, tests, and unresolved blockers with evidence
---

## Goal

Read-only audit whether the current working tree fixes the July 31 rejection: A0/A1/A2 must use one immutable snapshot, isolate variant state, pass intended selected tickers into actual weights, assert selected equals weight keys, emit P10 and full DecisionTrace; WP1-A must fail closed per ticker/source, use complete return intervals and all 49 tickers, connect to real data, and emit machine-readable consistency plus market/pool/sector regime evidence. Locate definitions, callers, tests, and remaining gaps; do not edit source.

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

- 2026-08-02T18:08:40+08:00 `DRAFT`: Task created.
- 2026-08-03T09:38:19+08:00 `CLOSED`: Read-only status audit concluded; actionable findings split into bounded tasks.
