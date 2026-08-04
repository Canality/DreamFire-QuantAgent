---
name: bounded-code-implementer
description: Implement a prepared agent task strictly within its frozen file whitelist, add regression coverage, run targeted validation, and emit machine-readable evidence. Use after Scout localization and baseline freeze for LOW-risk local work or a bounded cloud-model implementation.
---

# Bounded Code Implementer

## Preconditions

Require the task status to be `READY`, a generated `context.md`, and a frozen `baseline.json`. If any is missing, stop without editing.

## Workflow

1. Read only the task contract, generated context and listed files.
2. Confirm the intended edits are all in `allowed_files`. Propose an updated scope instead of editing outside it.
3. Add or strengthen a failing regression test before the implementation when practical.
4. Make the smallest change that satisfies the acceptance contract. Do not update `VALIDATION.md`, README or discussion unless the task explicitly assigns those files.
5. Run the task's targeted tests and lint commands. Preserve exact commands, exit codes and short result summaries.
6. Run `python scripts/agent_task.py scope-check <TASK-ID>`. Any violation is `BLOCKED`, not a warning.
7. Write `output/agent_handoffs/<TASK-ID>/implementation.json` with `task_id`, `changed_files`, `commands`, `exit_codes`, `summary`, and `unknowns`.
8. Set status to `IMPLEMENTED`; never claim `VERIFIED` or business completion.

Stop after two failed attempts and request escalation with the failing assertion and current diff. Do not solve a scope problem by silently widening the whitelist.
