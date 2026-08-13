---
id: BRIDGE-OPS-3
title: Make the visible Codex-Claude bridge recover from closed terminals and sleep
status: CLOSED
risk: HIGH
owner: Codex
created_at: 2026-08-12T13:05:00+08:00
updated_at: 2026-08-12T13:52:00+08:00
allowed_files:
  - .codex/hooks.json
  - .codex/hooks/discussion_bridge_stop.py
  - .claude/hooks/codex_bridge_stop.py
  - .claude/settings.json
  - output/bridge_runtime/start-codex-cli.ps1
  - output/bridge_runtime/start-claude-cli.ps1
  - scripts/tests/test_discussion_bridge_hooks.py
  - coordination/active/BRIDGE-OPS-3.md
acceptance:
  - A Stop-hook waiter exits and releases its OS lock within one poll after its visible launcher process dies.
  - A replacement waiter retries a temporarily busy lock for a bounded interval and takes over after the orphan releases it.
  - Hook commands remain correct when the CLI current directory is a repository subdirectory.
  - Internal standby uses wall-clock time and returns at least one hour before the configured outer hook timeout, including across Windows sleep.
  - Existing stale/fresh outbox, single-waiter and no-reply standby behavior remains covered.
  - Closing and reopening the visible Claude CLI is reproduced live without manual orphan-tree cleanup.
---

## Goal

Remove the recurring bridge stalls caused by orphan Stop-hook children, cwd-sensitive commands, non-retried lock contention and sleep-sensitive timeout margins.

## Non-goals

- No product, quant, E3/E4, Provider, report or submission changes.
- No background service, scheduled task, registry edit, network dependency or hidden terminal.
- No change to the two-party governance or one-visible-session-per-side rule.

## Progress

- 2026-08-12T13:05:00+08:00 `DRAFT`: Codex reproduced the failure chain and froze a bridge-only repair scope.
- 2026-08-12T13:06:00+08:00 `READY`: exact bridge-only scope frozen; implementation may start.
- 2026-08-12T13:52:00+08:00 `CLOSED`: 25 focused tests and syntax/config gates passed; live close released the Hook tree with `owner_exited`, restart removed the stale Claude process and produced one visible session plus one waiter tree.
