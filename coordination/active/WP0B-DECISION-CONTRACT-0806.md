---
id: WP0B-DECISION-CONTRACT-0806
title: Harden point-in-time Agent decision and shared selection contracts
status: CLOSED
risk: HIGH
owner: Codex
created_at: 2026-08-06T10:24:00+08:00
updated_at: 2026-08-06T11:25:00+08:00
allowed_files:
  - jiuwenswarm/jiuwenswarm/quant/agent_decision.py
  - jiuwenswarm/jiuwenswarm/extensions/quant-finance/extension.py
  - jiuwenswarm/scripts/run_quant_pipeline.py
  - jiuwenswarm/evaluation/agent_ablation.py
  - jiuwenswarm/tests/unit_tests/quant/test_agent_decision.py
  - jiuwenswarm/tests/unit_tests/quant/test_extension_cache_pipeline.py
  - jiuwenswarm/tests/unit_tests/quant/test_direct_pipeline_adapter.py
  - jiuwenswarm/tests/unit_tests/quant/test_agent_ablation.py
acceptance:
  - AgentProposal binds immutable evidence identity, availability and validity to a decision date.
  - Unknown ticker, future or expired evidence, non-finite scores, bounds violations and under-evidenced veto fail closed without mutating input proposals.
  - DecisionTrace records per-role adjustments, rejection reasons, ranking and selection impact deterministically.
  - Direct and formal paths use one server-owned selection function; production overlay remains disabled.
  - Focused positive/negative/parity tests, Ruff, scope-check and git diff --check pass.
---

## Goal

Complete the missing WP0-B decision safety contract and remove duplicated stock
selection logic while leaving the production Agent overlay disabled until a
separate A0/A1/A2 experiment proves bounded value.

## Non-goals

- Do not enable `AGENT_OVERLAY_ENABLED` or change the production portfolio.
- Do not implement WP1-E3 strategy-level Agent fusion.
- Do not claim A0/A1/A2 evidence in this task.
- Do not change roles, RPC count, factor weights, Provider roots or submission rules.

## Invariants

- Preserve AGENTS.md and project safety contracts.
- LLM input cannot provide price matrices, scores, selected tickers, weights or
  backtest objects to deterministic stages.
- Same base scores, proposal bundle, evidence clock and selection policy must
  produce the same trace and ticker list on direct/formal callers.

## Locate brief

- Scout must locate all AgentProposal/DecisionTrace/DecisionAssembler constructors,
  selection implementations, cache consumers and tests. It must identify the
  smallest evidence-time schema and direct/formal parity boundary, writing only
  `location.json`.

## Implementation evidence

- `ProposalEvidence` binds signal identity, payload SHA-256, availability and
  expiry; `AgentProposal` binds an aware validity interval.
- `DecisionAssembler` rejects unsafe scores and proposals without mutating
  input, enforces two independent veto signals and emits a deeply immutable
  ranking/selection/role trace.
- Both direct and formal callers use `select_portfolio`; the retained canonical
  policy is the pre-existing formal 15-stock, six-sector, `-0.5` threshold
  policy. `AGENT_OVERLAY_ENABLED` remains `False`.
- `agent_ablation.py` now evaluates A0/A1/A2 with separate pure selections,
  allocations and fixed-share open-to-close backtests on one hash-bound
  decision/embargo/20-session snapshot. A single snapshot is never promotable.
- 46 focused tests, Ruff, py_compile, scope-check and diff-check pass.

## Review evidence

- Initial review correctly rejected two P1 and two P2 counterexamples; a second
  review rejected an unbound official-window label and incomplete baseline
  reconstruction. All findings were reproduced and closed.
- Final independent verdict: `ACCEPT`, P0/P1/P2/P3 = 0/0/0/0, 46 focused
  tests passed, exact baseline-backed diff reverse-applied successfully.
- Final review SHA-256:
  `e4b33eee13f9ee2fd9b97c5212840b4c2eeddf33653cee5a6af654e4f8b8d910`.

## Progress

- 2026-08-06T10:24:00+08:00 `DRAFT`: Task created from the roadmap audit; production overlay remains disabled.
- 2026-08-06T10:43:00+08:00 `LOCATED`: Read-only location validated at confidence 0.94. Planner froze the existing decision contract and both duplicated caller boundaries; no new selector module is needed.
- 2026-08-06T10:32:20+08:00 `READY`: Baseline frozen; implementation may start.
- 2026-08-06T10:50:00+08:00 `IMPLEMENTED`: Builder completed the typed PIT evidence boundary, immutable deterministic trace and shared formal/direct selector. Independent review is pending.
- 2026-08-06T11:00:00+08:00 `IMPLEMENTED`: Critic requested two P1 and two P2 fixes. Planner accepted a review-driven scope amendment for the already-located legacy ablation consumer and one focused test; the original baseline hashes remain authoritative.
- 2026-08-06T11:08:00+08:00 `IMPLEMENTED`: Closure rejects relabelled payloads and all public non-finite scores, enforces runtime-deep immutability, and replaces the invalid cache-reusing ablation with three independent official-window evaluations. Re-review pending.
- 2026-08-06T11:16:00+08:00 `IMPLEMENTED`: Second review P1 closed by binding the complete canonical session calendar, entry-open label and unique 20-date close sequence. Original ablation bytes were restored into baseline_files and the exact replacement diff regenerated.
- 2026-08-06T11:23:00+08:00 `REVIEWED`: Independent closure review accepted with no P0-P3 findings.
- 2026-08-06T11:24:00+08:00 `VERIFIED`: Planner reproduced 46 focused passes, Ruff, pycompile, scope-check, exact diff and diff-check.
- 2026-08-06T11:25:00+08:00 `CLOSED`: WP0-B decision contract and diagnostic A0/A1/A2 runner accepted. Overlay remains disabled because outer-window promotion evidence is still absent.
