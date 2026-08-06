---
name: local-code-scout
description: Claude's read-only location phase: find definitions, callers, tests, contracts, and the smallest likely change boundary, then write a bounded location.json for Codex to accept before baseline freeze.
---

# Claude Read-only Location Phase

## Workflow

1. Read `AGENT_WORKFLOW.md` and the named `coordination/active/<TASK-ID>.md`. Do not load unrelated plans, archives, discussion history, output, or data matrices.
2. Search with `rg`/`rg --files` before opening files. Limit the pass to 12 search/read calls.
3. Trace the definition, direct callers, relevant tests and any project contract that can invalidate the proposed change.
4. Do not edit source, tests, state documents or the task contract. Only write `output/agent_handoffs/<TASK-ID>/location.json`.
5. Run `python scripts/agent_task.py validate-location <TASK-ID>` and hand the artifact to Codex. Codex alone approves the write scope and freezes the baseline.

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

Use repository-relative POSIX paths. Keep ranges tight and confidence conservative. Stop for Codex adjudication when confidence is below `0.75`, ownership is unclear, or the task touches a HIGH-risk area in `AGENT_WORKFLOW.md`. This is a phase checklist, not a third development identity.
