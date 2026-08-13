---
id: BRIDGE-OPS-5
title: Require durable output after actionable bridge wakes
status: VERIFIED
risk: HIGH
owner: Claude
created_at: 2026-08-13T10:16:00+08:00
updated_at: 2026-08-13T13:19:14+08:00
allowed_files:
  - .claude/hooks/codex_bridge_stop.py
  - .codex/hooks/discussion_bridge_stop.py
  - coordination/active/BRIDGE-OPS-5.md
  - output/agent_handoffs/.bridge/
  - output/bridge_runtime/start-claude-cli.ps1
  - output/bridge_runtime/start-codex-cli.ps1
  - scripts/tests/test_discussion_bridge_hooks.py
acceptance:
  - A routed handoff without an explicit reply section fails closed as actionable; an explicit no-reply section remains passive.
  - Every actionable Codex wake requires a changed Codex-owned discussion handoff before Codex may re-enter standby.
  - Every actionable Claude wake requires a changed task outbox before Claude may re-enter standby.
  - Pending input and the required output baseline survive across Stop-hook processes and are content-addressed.
  - Passive standby, explicit no-reply and timeout re-entry do not create heartbeat writes or wake the peer.
  - Existing freshness, single-delivery, lock takeover, owner-liveness and timeout behavior remains covered.
  - Launcher prompts state the durable-output rule for both collaborators.
  - The current WP1-E4-R1 instruction is resumed once without replaying its stale outbox.
---

## Goal

Remove the bridge state in which both visible CLIs wait even though the newest routed
handoff contains actionable work. Require a durable output mutation after each actionable
wake, while keeping passive standby write-free.

## Current Evidence

- At 2026-08-13T10:14+08:00 both Stop hooks were alive and waiting.
- The newest discussion route was `Codex → Claude` for `WP1-E4-R1`, written at 10:09:32.
- The task outbox was older, written at 09:50:07.
- `_top_handoff` selected the new instruction, but `_requires_reply` returned false because
  the handoff omitted `### 需要回复`.
- Therefore Claude entered standby instead of executing the instruction; Codex also waited
  for a newer Claude outbox.

## Required Protocol

- Do not require writes for passive/no-reply standby; heartbeat writes would create a
  ping-pong loop.
- For an actionable wake, persist a pending record before continuing the model. It must bind
  the input token, required output path and pre-wake output content hash.
- On the next Stop, unchanged required output must block the same side again. A content
  change clears the pending record and permits normal delivery/standby processing.
- Codex output is a new top entry in `.claude/discussion.md`; Claude output is the current
  task `claude_reply.md`.
- An omitted reply section on a routed handoff is actionable by default. Only an explicit
  no-reply value suppresses action.

## Phase

Use `local-code-scout` now. Read only the workflow, this contract, bridge hooks, launchers
and focused bridge tests. Do not edit source, tests, launchers, WP1-E4 files or discussion.
Write bounded `location.json` and a fresh `claude_reply.md`, run
`python scripts/agent_task.py validate-location BRIDGE-OPS-5`, set the task to `LOCATED`,
then stop for Codex scope adjudication.

## Progress

- 2026-08-13T10:16:00+08:00 `DRAFT`: Codex established the bridge-only diagnosis and
  requested a read-only Claude location phase.
- 2026-08-13T10:25:27+08:00 `LOCATED`: Read-only protocol location complete per local-code-scout. Located both Stop hooks, hook wiring, both launcher prompts and focused bridge tests; root cause = _requires_reply treats a handoff without a reply section as passive. Proposed write scope marked CHANGE/KEEP in location.json. validate-location pass pending. Not implemented; no source/test/launcher/discussion edited.
- 2026-08-13T10:26:35+08:00 `REVIEWED`: Codex independently ACCEPTED the read-only location. Pending-record schema, lifecycle, exact whitelist and fresh baseline require a separate planning phase before implementation.
- 2026-08-13T12:38:02+08:00 `LOCATED`: Write scope approved by Codex.
- 2026-08-13T12:38:16+08:00 `READY`: Baseline frozen; implementation may start.
- 2026-08-13T12:40:00+08:00 `READY`: Codex planning phase complete. Frozen whitelist: both Stop hooks, both launcher prompts, focused bridge test, task file, and runtime pending-record directory output/agent_handoffs/.bridge/. Pending-record schema adjudicated: per-side JSON at output/agent_handoffs/.bridge/{claude,codex}-pending.json with keys input_token (SHA-256 of actionable input), required_output (normalized path), pre_hash (SHA-256 of pre-wake required-output content), created_at. Lifecycle: write pending record before actionable wake; unchanged required output blocks same side on next Stop; content change atomically clears record; explicit no-reply/passive/timeout create no record and no heartbeat. Implementation authorized on exact whitelist only; WP1-E4-R1 resumes once after independent review.
- 2026-08-13T12:44:53+08:00 `READY`: Handed off to Claude for bounded implementation on frozen whitelist.
- 2026-08-13T12:49:48+08:00 `IMPLEMENTED`: Bounded implementation complete; focused tests 43 passed / 1 skipped, scope-check red only on Codex-owned discussion. Handed to Codex for independent review.
- 2026-08-13T12:52:36+08:00 `VERIFIED`: Codex independent implementation review ACCEPT. 43 focused tests passed, static checks passed, launcher prompts verified. Scope-check red only on Codex-owned discussion.md.
- 2026-08-13T13:19:14+08:00 `VERIFIED`: Final implementation review ACCEPT after pending-record deadlock fix; 47 focused tests passed. Discussion handoff written to clear pending record.
