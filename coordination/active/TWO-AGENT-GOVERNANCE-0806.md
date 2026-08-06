---
id: TWO-AGENT-GOVERNANCE-0806
title: Replace legacy multi-model development roles with peer Codex and Claude
status: CLOSED
risk: HIGH
owner: Codex
created_at: 2026-08-06T14:34:00+08:00
updated_at: 2026-08-06T14:44:00+08:00
allowed_files:
  - coordination/active/TWO-AGENT-GOVERNANCE-0806.md
  - AGENTS.md
  - CLAUDE.md
  - AGENT_WORKFLOW.md
  - DEVELOPMENT_PLAN.md
  - README.md
  - .agents/skills/local-code-scout/SKILL.md
  - .agents/skills/bounded-code-implementer/SKILL.md
  - .agents/skills/diff-contract-reviewer/SKILL.md
  - scripts/agent-role.cmd
  - scripts/agent_role.py
  - scripts/claude-deepseek.cmd
  - scripts/claude-deepseek.ps1
  - scripts/claude-profile.ps1
  - scripts/claude-qwen.cmd
  - scripts/claude-qwen.ps1
  - scripts/claude_profile.py
  - scripts/agent_task.py
  - jiuwenswarm/tests/unit_tests/quant/test_document_contract.py
acceptance:
  - Active development identities define exactly two peer collaborators: Codex owns planning and independent acceptance; Claude owns location, implementation and validation evidence; neither is a general superior and both may challenge with evidence.
  - A challenge is bounded to two exchanges per side and must end in ACCEPT, MODIFY, REJECT or explicit user escalation; undisputed work continues and the same evidence-free dispute cannot loop.
  - Location and review remain auditable task phases, not permanent third or fourth Agent identities; task contracts, whitelists, baseline hashes and handoff artifacts remain mandatory.
  - The runtime financial team remains Coordinator, Alpha Analyst and Risk & Evidence Analyst and is explicitly distinct from the two-Agent development collaboration.
  - Obsolete Qwen/DeepSeek role/profile launchers are deleted; active identity, workflow, plan, README and phase skills contain no legacy Missed/Goone model routing.
  - Focused document-contract tests, Ruff, scope-check and git diff --check pass; no runtime, strategy, Provider, evidence grade or submission state changes.
---

## Goal

Make Windows Codex and Claude the only active development collaborators while
retaining the task evidence and fail-closed practices that proved useful.

## Non-goals

- Do not change the three-role financial runtime, eight Quant RPCs or prompts.
- Do not change strategy, data, reporting, submission or validation facts.
- Do not rewrite append-only history or old task evidence.
- Do not preserve unused model routing merely for backward compatibility.

## Locate brief

- Validated read-only location confidence `0.99`; artifact SHA-256 is recorded
  in the implementation handoff. The five active governance documents contain
  the legacy Missed/Goone, four-role and Qwen/DeepSeek routing; eight tracked
  launcher/profile files implement that retired route.
- Keep the three phase skills as bounded checklists, but assign location and
  implementation to Claude and independent diff review to Codex. They are
  phases inside a two-party workflow, not additional Agent identities.
- Freeze the exact nineteen-file boundary above. Runtime role files, prompts,
  strategy, Provider, validation facts, history and discussion are read-only.

## Implementation evidence

- Replaced the active identities with exactly two peer collaborators. Codex owns
  plan/scope/review/acceptance; Claude owns read-only location, implementation,
  tests and implementation evidence. Phase authority is explicit and neither
  role is a general superior.
- The challenge contract requires a proposition, reproducible evidence,
  bounded alternative, affected scope, acceptance and rollback. Each side gets
  at most two evidence exchanges before `ACCEPT`, `MODIFY`, `REJECT` or user
  escalation; undisputed work continues.
- Preserved task contracts, baseline hashes, frozen whitelists, location/
  implementation/review artifacts and the three phase skills. Reassigned those
  skills to Claude location/implementation and Codex independent review rather
  than treating them as extra Agent identities.
- Deleted eight obsolete provider/model role launchers. No runtime financial
  role, RPC, strategy, Provider, validation fact, evidence grade or submission
  state changed.
- Focused document contracts: 22 passed. Ruff, exact active-identity search,
  frozen scope-check and `git diff --check` pass.
- Independent review found two active-flow contradictions. The implementation
  phase now treats `context.md` as optional unless the task requires it, and
  `agent_task.py` identifies its workflow and scope approval as Codex/Claude
  rather than injecting a retired third identity.

## Review evidence

- Independent closure review verdict `ACCEPT`; P0/P1/P2/P3 are all zero.
  Three P1 findings and two P2 findings were reproduced and closed: optional
  context consistency, task-CLI legacy identity output, expanded baseline scope,
  non-monotonic timestamps and understated risk.
- Final scope is exactly nineteen allowed files with `violations=[]`; document
  contracts are 22 passed and Ruff, pycompile and diff-check pass.
- Review SHA-256:
  `4c0df786396b0c61f1f5716588ba3ce53201b2262f1888c9af0dcc9025ff8e23`.
- This is governance-only acceptance. Runtime evidence grades and Windows
  formal/resource/normal-exit gates remain unchanged.

## Progress

- 2026-08-06T14:34:00+08:00 `DRAFT`: Created from the user's explicit request
  to hand development to peer Windows Codex and Claude and remove the legacy
  three/multi-model collaboration rules.
- 2026-08-06T14:35:00+08:00 `LOCATED`: Codex validated the complete active
  governance surface at confidence 0.99 and accepted an exact documentation,
  phase-skill, regression-test and obsolete-launcher boundary.
- 2026-08-06T14:36:00+08:00 `READY`: Baseline frozen; implementation may start.
- 2026-08-06T14:38:00+08:00 `IMPLEMENTED`: Two-party identities, bounded
  challenge closure, phase checklists, current plan and obsolete-launcher
  deletion are implemented; 22 document contracts and static/scope gates pass.
- 2026-08-06T14:40:00+08:00 `REVIEWED/MODIFY`: Independent review found the
  implementation Skill incorrectly required optional context and the task CLI
  still generated retired workflow/approval wording. Codex accepted both
  reproducible findings and expanded scope only to the already-baselined CLI.
- 2026-08-06T14:42:00+08:00 `IMPLEMENTED`: Both review findings are closed;
  the task generator now emits Codex scope ownership and no active tool creates
  an extra development identity.
- 2026-08-06T14:43:00+08:00 `REVIEWED/MODIFY`: Codex accepted the Critic's
  self-consistency finding and raised this nineteen-file governance migration
  from MEDIUM to HIGH under the new workflow's cross-file risk rule.
- 2026-08-06T14:44:00+08:00 `REVIEWED/VERIFIED/CLOSED`: Independent closure
  review accepted all five remediations with no open P0-P3 finding. Codex
  reproduced the nineteen-file scope and 22-pass contract suite; no runtime
  fact, history evidence, push or Windows main-workspace mutation occurred.
