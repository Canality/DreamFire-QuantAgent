---
id: WP1-E3-R1
title: Locate bounded Agent strategy fusion on accepted E2C replay evidence
status: DRAFT
risk: HIGH
owner: Claude
created_at: 2026-08-11T17:35:45+08:00
updated_at: 2026-08-11T17:35:45+08:00
allowed_files:
  - coordination/active/WP1-E3-R1.md
acceptance:
  - Read-only location.json enumerates every existing AgentProposal, ProposalEvidence, DecisionTrace, DecisionAssembler, A0/A1/A2 diagnostic, E2 strategy-pool replay boundary, model-call adapter, direct/formal caller, cache owner and focused test relevant to bounded strategy-level fusion.
  - Location defines the smallest future write scope without changing product code, tests, archives, documentation, production flags, direct/formal/RPC/E2E paths or model credentials in this phase.
  - Location proves how only server-owned deterministic candidate summaries reach Alpha/Risk; price or volume matrices, ticker scores, weights, portfolios, backtests and future labels never enter or return from an LLM.
  - Location preserves one create-once proposal bundle per decision date, one call per Alpha/Risk role, zero tool or Quant RPC calls, zero retries, 45-second per-role timeout, input <=4000 tokens and output <=800 tokens.
  - Location maps negative coverage for future/expired evidence, duplicate or wrong-role proposals, unknown candidates, non-finite or out-of-bound adjustments, excess L1, unsupported veto, parser/schema failure, timeout, replay and cache leakage, and production isolation.
  - Location keeps production_six_factor as the sole production strategy; t2_comparator is only QUALIFIED_RESEARCH_ONLY, failed or unavailable E2 candidates cannot be revived by an Agent, and no promotion or PATH/BUSINESS claim occurs.
---

## Goal

Perform read-only location for the smallest deterministic, auditable E3 fusion boundary that can compare A0 with bounded Alpha and Risk proposals over the accepted E2C research evidence before any E4 outer replay.

## Non-goals

- No implementation, source/test/archive/documentation edit, network access, model call, credential use, direct/formal/RPC/E2E run, commit, push or production promotion.
- No change to factor definitions, strategy registration, E2C verdicts, stock selection, allocation, report, submission contract, roles or the eight Quant RPCs.
- No use of the LLM as a source for candidates, scores, tickers, weights, portfolios, backtests or evidence.

## Invariants

- Preserve AGENTS.md, VALIDATION.md and DEVELOPMENT_PLAN.md safety and evidence contracts.
- A0 is deterministic and remains available when either role proposal is missing or rejected.
- Alpha may adjust each eligible candidate by at most +/-0.10 with total L1 <=0.20.
- Risk may only make non-positive adjustments and may veto at most one non-fallback candidate when at least two independent PIT EvidenceRefs support the veto.
- Coordinator may only invoke the deterministic assembler; it cannot add candidates, factors, securities or weights.
- All proposal, schema, prompt, model/config and assembler identities must be hash-bound before any future outer evaluation.
- Production overlay remains disabled and production_six_factor remains the hard fallback.

## Locate brief

Use `.agents/skills/local-code-scout/SKILL.md`. Read only the minimum definitions, callers, tests and contracts needed to produce `output/agent_handoffs/WP1-E3-R1/location.json` and `claude_reply.md`. Propose exact `KEEP / REPLACE / DELETE`, future allowed files, test commands, direct/formal isolation checks, rollback and unresolved risks. Run only `python scripts/agent_task.py validate-location WP1-E3-R1`, then stop for Codex review.

## Implementation evidence

- Pending; implementation is forbidden until Codex accepts location and freezes a fresh baseline.

## Review evidence

- Pending.

## Progress

- 2026-08-11T17:35:45+08:00 `DRAFT`: Codex created the E3 read-only location contract from accepted WP1-E2C-R1 evidence; no implementation scope is frozen.
