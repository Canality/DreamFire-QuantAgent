---
name: local-code-scout
description: Read-only repository localization that finds definitions, callers, tests, contracts, and likely change boundaries, then writes a bounded location.json handoff. Use before assigning implementation when a task would otherwise require a model to read broad repository context.
---

# Local Code Scout

## Workflow

1. Read `AGENT_WORKFLOW.md` and the named `coordination/active/<TASK-ID>.md`. Do not load unrelated plans, archives, discussion history, output, or data matrices.
2. Search with `rg`/`rg --files` before opening files. Limit the pass to 12 search/read calls.
3. Trace the definition, direct callers, relevant tests and any project contract that can invalidate the proposed change.
4. Do not edit source, tests, state documents or the task contract. Only write `output/agent_handoffs/<TASK-ID>/location.json`.
5. Run `python scripts/agent_task.py validate-location <TASK-ID>` and stop if validation fails.

## Output schema

```json
{
  "task_id": "TASK-001",
  "hypothesis": "concise suspected cause",
  "confidence": 0.0,
  "files": [
    {
      "path": "relative/path.py",
      "reason": "definition or caller",
      "ranges": [{"start": 10, "end": 80}]
    }
  ],
  "tests": ["relative/test_path.py"],
  "symbols": ["package.module.symbol"],
  "unknowns": [],
  "recommended_risk": "LOW|MEDIUM|HIGH"
}
```

Use repository-relative POSIX paths. Keep ranges tight and confidence conservative. Recommend escalation when confidence is below `0.75`, ownership is unclear, or the task touches a HIGH-risk area in `AGENT_WORKFLOW.md`.
