---
id: BRIDGE-OPS-1
title: Read-only audit of the local Codex-Claude discussion bridge
status: CLOSED
risk: MEDIUM
owner: Codex
created_at: 2026-08-11T00:00:00+08:00
updated_at: 2026-08-11T16:45:00+08:00
allowed_files:
  - coordination/active/BRIDGE-OPS-1.md
  - output/agent_handoffs/BRIDGE-OPS-1/location.json
  - output/agent_handoffs/BRIDGE-OPS-1/claude_reply.md
  - output/agent_handoffs/BRIDGE-OPS-1/review.json
acceptance:
  - Claude audits only the seven frozen local bridge files named in this contract.
  - location.json identifies bridge entry points, control flow, failure modes, security and lifecycle risks, and the smallest proposed follow-up boundary without modifying bridge files.
  - claude_reply.md summarizes the verdict, exact files inspected, unknowns, validation command and exit code.
  - Codex independently reviews the artifacts and records ACCEPT, MODIFY, or REJECT before this task can close.
---

## Goal

Perform exactly one bounded, read-only Claude location/audit phase of the local
Codex-Claude discussion bridge. Establish evidence about the bridge's current
configuration, stop-hook control flow, helper-script lifecycle, and operational
risks without changing or executing the bridge.

## Frozen read scope

Claude may read only the task/workflow instructions required by
`local-code-scout` and these bridge files:

1. `.codex/hooks.json`
2. `.codex/hooks/discussion_bridge_stop.py`
3. `.claude/settings.json`
4. `.claude/hooks/codex_bridge_stop.py`
5. `output/bridge_runtime/start-codex-cli.ps1`
6. `output/bridge_runtime/start-claude-cli.ps1`
7. `output/bridge_runtime/bridge-status.ps1`

The audit may use read-only filesystem metadata and targeted syntax/static
checks for those files. It must not open product source, product tests, roadmap,
validation, history, unrelated output, logs, data, secrets, or discussion
history beyond the new instruction at the top.

## Writable artifacts for this phase

- `output/agent_handoffs/BRIDGE-OPS-1/location.json`
- `output/agent_handoffs/BRIDGE-OPS-1/claude_reply.md`
- `coordination/active/BRIDGE-OPS-1.md` only to set `status: LOCATED` and append
  a truthful progress entry after schema validation succeeds.

No bridge file is writable. No implementation whitelist or baseline is frozen
by this planning phase.

## Required audit evidence

- Enumerate the exact seven inspected files and tight relevant ranges/symbols.
- Trace Codex Stop to Claude wake-up and Claude Stop to Codex wake-up, including
  termination, recursion/re-entry prevention, state/pid handling, quoting,
  encoding, path resolution, and Windows process-lifecycle assumptions.
- Identify fail-open/fail-closed behavior, stale state, concurrent invocation,
  command injection, secret leakage, destructive action, and unbounded-loop
  risks, using evidence from the frozen files only.
- Distinguish confirmed findings from unknowns; do not infer runtime success from
  static inspection.
- Recommend the smallest possible follow-up write boundary, but do not edit,
  run, or test the bridge.
- Produce `location.json` compatible with `local-code-scout`, then run
  `python scripts/agent_task.py validate-location BRIDGE-OPS-1` and record the
  exact command and exit code in `claude_reply.md`.

## Non-goals and prohibitions

- Do not inspect or modify product code, product tests, financial data, Quant
  RPCs, direct/formal/E2E paths, `VALIDATION.md`, `DEVELOPMENT_PLAN.md`, README,
  history, or unrelated coordination tasks.
- Do not modify or execute any bridge hook/helper, start either CLI, signal or
  terminate processes, inspect live process command lines, or access network.
- Do not create baseline.json or implementation.json, start implementation,
  commit, push, tag, or claim PATH/BUSINESS success.
- Do not expand scope silently. Record any needed extra file as an unknown and
  stop for Codex adjudication.

## Codex review gate

On the later hook wake-up, Codex must independently compare both artifacts to
this contract and the seven frozen files, record `ACCEPT`, `MODIFY`, or `REJECT`,
and close `BRIDGE-OPS-1` only if the read-only audit is complete and truthful.
Only after that verdict may Codex select the highest-priority
evidence-bounded product task under `AGENTS.md`; no product work belongs to this
phase.

## Progress

- 2026-08-11 `DRAFT`: Codex created the bounded read-only audit contract. Awaiting Claude location artifacts through the Stop-hook handoff.
- 2026-08-11T16:30:02+08:00 `LOCATED`: Read-only audit of the seven frozen bridge files completed; location.json validated (confidence 0.85). Awaiting Codex review.
- 2026-08-11 `REVIEWED / MODIFY`: Codex independently confirmed the normalized heading regex and location schema, but found incomplete command-injection analysis plus understated permission-bypass, debug/status exposure, and follow-up lifecycle risk. Evidence-only correction required; bridge files remain read-only.
- 2026-08-11 `REVIEWED / REJECT`: The correction handoff contained no new evidence; both artifacts remained unchanged and all three findings remained open. The existing outbox was incorrectly treated as fresh by the Stop hook. BRIDGE-OPS-1 is not accepted and cannot authorize implementation or product-task selection.
- 2026-08-11 `CLOSED / ACCEPT`: Codex revalidated the corrected artifacts after Claude completed the delayed write. The three findings are now addressed. The earlier REJECT is retained as evidence of the stale-outbox race, not as the final artifact verdict.
