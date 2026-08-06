---
name: diff-contract-reviewer
description: Codex's independent review phase: inspect a task-scoped baseline diff against its contract, tests, ownership boundaries, and safety invariants before acceptance, looking for missed callers, superficial fixes, false claims, and out-of-scope edits.
---

# Codex Independent Diff Review Phase

## Workflow

1. Start from a fresh session. Read only the task contract, `implementation.json`, generated baseline diff, and concise test evidence.
2. Run `python scripts/agent_task.py scope-check <TASK-ID>` before judging behavior.
3. Check acceptance criteria, negative cases, callers, compatibility, failure closing, time causality and document claims applicable to the task.
4. Prefer a reproducible counterexample or targeted test over stylistic commentary.
5. Do not edit source. Write `output/agent_handoffs/<TASK-ID>/review.json` with `decision`, `findings`, `required_actions`, `checked_commands`, and `residual_risks`.
6. Use `ACCEPT` only when the scoped evidence is sufficient. Use `MODIFY` for actionable defects and `BLOCKED` for missing/invalid evidence.
7. Set task status to `REVIEWED`. Codex may set `VERIFIED/CLOSED` only after separately reproducing the accepted evidence.

Do not accept a patch by role authority or majority vote. Project contracts and executable evidence take precedence. This is a phase checklist, not a third development identity.
