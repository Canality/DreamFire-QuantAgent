---
id: BRIDGE-OPS-2
title: Harden the persistent local Codex-Claude discussion bridge
status: CLOSED
risk: HIGH
owner: Codex
created_at: 2026-08-11T16:45:00+08:00
updated_at: 2026-08-11T17:14:00+08:00
allowed_files:
  - .codex/hooks.json
  - .codex/hooks/discussion_bridge_stop.py
  - .claude/settings.json
  - .claude/hooks/codex_bridge_stop.py
  - output/bridge_runtime/start-codex-cli.ps1
  - output/bridge_runtime/start-claude-cli.ps1
  - output/bridge_runtime/bridge-status.ps1
  - scripts/tests/test_discussion_bridge_hooks.py
  - coordination/active/BRIDGE-OPS-2.md
  - output/agent_handoffs/BRIDGE-OPS-2/baseline.json
  - output/agent_handoffs/BRIDGE-OPS-2/implementation.json
  - output/agent_handoffs/BRIDGE-OPS-2/claude_reply.md
  - output/agent_handoffs/BRIDGE-OPS-2/review.json
acceptance:
  - Existing outboxes cannot wake Codex after a newer Codex instruction unless their content and mtime prove freshness.
  - Both Stop hooks remain in bounded idle standby and re-enter standby after timeout without producing user-visible heartbeat messages.
  - A per-agent operating-system lock prevents concurrent Stop hook waiters and releases automatically when a process exits.
  - Codex no longer races on claude agents idle status before waiting for an outbox.
  - Launchers resolve executables dynamically, use task-generic prompts, keep intentional high-trust mode explicit, and make Claude debug logging opt-in.
  - Status output excludes full process command lines and sensitive prompt or argument data.
  - Focused regression tests cover stale, unchanged, fresh, and idle-standby behavior on Windows-compatible paths.
  - JSON, Python, PowerShell, focused tests, diff-check, and task scope-check all pass before acceptance.
---

## Goal

Implement the smallest reliable local-file bridge that keeps one persistent Codex CLI and one persistent Claude CLI coordinated through `.claude/discussion.md` and task outboxes, without timer heartbeats or stale-response loops.

## Frozen implementation rules

- Freshness requires an outbox to be newer than the current discussion instruction and, when a stale snapshot exists, to have different content.
- Both agents wait for relevant local file changes even when the current top handoff requires no reply. A long bounded timeout must re-enter standby rather than silently detach.
- Each agent may have at most one active Stop-hook waiter. Use an operating-system lock that is released on process death; do not rely on stale PID files.
- Remove the Codex `claude agents` working-state gate from hook control flow. The persistent CLI lifecycle is managed by launchers and operators, not inferred during every Stop event.
- Keep unattended high-trust flags because this is an explicitly authorized local bridge, but print a clear warning and reduce avoidable debug/status exposure.
- Do not add network dependencies, background services, registry changes, scheduled tasks, destructive cleanup, product-code edits, or a second Claude/Codex project session.

## Implementation evidence

Claude must use `bounded-code-implementer`, stay inside `allowed_files`, add focused regression coverage, run targeted validation, and write machine-readable `implementation.json` plus `claude_reply.md`. Claude may set the task to `IMPLEMENTED`, but only Codex may accept and close it.

## Codex review gate

Codex independently reviews the baseline diff, test evidence, process/trust boundaries, and one live stale-to-fresh handoff cycle before `ACCEPT`. Runtime proof is limited to this bridge and must not be promoted to product PATH or BUSINESS completion.

## Progress

- 2026-08-11 `DRAFT`: Codex accepted BRIDGE-OPS-1 and created this HIGH-risk implementation contract from its bounded findings.
- 2026-08-11T16:41:28+08:00 `READY`: Baseline frozen; implementation may start.
- 2026-08-11T17:07:00+08:00 `IMPLEMENTED`: Codex completed the frozen bridge hardening after repeated Claude API/session stalls; the baseline records a narrow erratum for the post-freeze Codex discussion instruction, and independent review/live acceptance remain pending.
- 2026-08-11T17:12:19+08:00 `REVIEWED`: Independent terminal Codex returned `ACCEPT`; scope-check, generated baseline diff, 14 tests, syntax checks, and a stale-touch-to-fresh-content live cycle passed.
- 2026-08-11T17:14:00+08:00 `CLOSED`: New persistent Codex and Claude CLIs both loaded the hardened hooks and entered local-file standby; status output confirmed one Claude project session and no command-line disclosure.
- 2026-08-11T17:12:19+08:00 `REVIEWED`: Codex independent review ACCEPT; live stale-to-fresh cycle and targeted validation passed. Separate verification/closure remains pending.
