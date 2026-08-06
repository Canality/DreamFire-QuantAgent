---
name: bounded-code-implementer
description: Claude's implementation phase: implement a prepared task strictly within the Codex-frozen whitelist, add regression coverage, run targeted validation, and emit machine-readable evidence for independent Codex review.
---

# Claude Bounded Implementation Phase

## Preconditions

Require the task status to be `READY` and a frozen `baseline.json`. Read
`context.md` when the task generated one; its absence is valid unless the task
contract explicitly requires it. If a required precondition is missing, stop
without editing.

## Workflow

1. Read the task contract, any generated context, and the listed files.
2. Confirm the intended edits are all in `allowed_files`. Propose an updated scope instead of editing outside it.
3. Add or strengthen a failing regression test before the implementation when practical.
4. Make the smallest change that satisfies the acceptance contract. Do not update `VALIDATION.md`, README or discussion unless the task explicitly assigns those files.
5. Run the task's targeted tests and lint commands. Preserve exact commands, exit codes and short result summaries.
6. Run `python scripts/agent_task.py scope-check <TASK-ID>`. Any violation is `BLOCKED`, not a warning.
7. Write `output/agent_handoffs/<TASK-ID>/implementation.json` with `task_id`, `changed_files`, `commands`, `exit_codes`, `summary`, and `unknowns`.
8. Set status to `IMPLEMENTED` and hand off to Codex; never claim `VERIFIED`, `CLOSED` or business completion.

Stop after two failed attempts and submit an evidence challenge with the failing assertion and current diff. Do not solve a scope problem by silently widening the whitelist. This is a phase checklist, not a separate development identity.
