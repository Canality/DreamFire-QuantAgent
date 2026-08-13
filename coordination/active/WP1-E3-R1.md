---
id: WP1-E3-R1
title: Locate bounded Agent strategy fusion on accepted E2C replay evidence
status: CLOSED
risk: HIGH
owner: Claude
created_at: 2026-08-11T17:35:45+08:00
updated_at: 2026-08-12T14:12:46+08:00
allowed_files:
  - jiuwenswarm/evaluation/strategy_fusion_replay.py
  - jiuwenswarm/tests/unit_tests/quant/test_strategy_fusion_replay.py
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
- 2026-08-11T18:00:05+08:00 `LOCATED`: read-only location complete; enumerate fusion machinery; propose future two-new-file research bypass; no product change
- 2026-08-11T18:03:02+08:00 `REVIEWED`: Codex location review MODIFY: required model-call boundary missing, strategy-level fractional assembler unresolved, formal caller omitted, and E2C evidence consumption undecided.
- 2026-08-11T18:07:27+08:00 `LOCATED`: location MODIFY corrected: mandatory research-only model adapter; strategy-slot fractional fusion schema/assembler/L1-veto; run_multi_agent formal entry; hash-verified E2C artifact boundary
- 2026-08-11T18:09:50+08:00 `REVIEWED`: Codex revision-2 location review MODIFY: globally failed trends were revivable per-window and the no-LLM-score/weight adjustment boundary remained unresolved.
- 2026-08-11T18:12:38+08:00 `LOCATED`: location revision 3 (final): global eligible set = production+t2 only; model returns typed signals + evidence IDs + rationale, server maps to bounded deltas; L1/veto/normalization frozen; no adjustment-target unknown
- 2026-08-11T18:14:05+08:00 `REVIEWED`: Codex final location review ACCEPT; design scope converged. Baseline freeze and implementation dispatch remain a separate planning phase.
- 2026-08-12T10:00:00+08:00 `LOCATED`: Codex selected deterministic E2C regeneration as the implementation oracle and approved the exact two-new-file research scope; baseline freeze pending.
- 2026-08-12T10:02:23+08:00 `READY`: Baseline frozen; implementation may start.
- 2026-08-12T10:26:03+08:00 `IMPLEMENTED`: Implementation complete; scope-check exit 2 on Codex-owned discussion.md baseline-order only. Handed to Codex for independent review.
- 2026-08-12T10:45:00+08:00 `REVIEWED`: Codex independent review MODIFY; whole-replay realized metrics were exposed as PIT evidence at the first decision date, and scope-check remained red. No source fix or E4 work was authorized.
- 2026-08-12T11:23:00+08:00 `IMPLEMENTED`: MODIFY applied within the exact two-source-file boundary. slot_summaries/build_evidence_registry/build_input_summary are now per-decision PIT prefixes (only windows with exit_date < decision_date contribute realized return/drawdown; the first decision exposes no realized evidence). EvidenceRef.available_at now equals the source window's actual exit session; valid_until is a fixed non-expiring sentinel decoupled from window data. Added negative regression proving later-window mutation/appending leaves an early decision's summary, registry, bundle identity and A0/A1/A2 unchanged. Real-artifact check: 48 refs across 12 window exits, none at decision_set[0]; last decision sees only 10 matured windows. 59 focused / 105 adjacent tests pass, ruff/py_compile/git diff --check clean; scope-check still red solely on the Codex-owned discussion.md baseline-order item (re-freeze pending).
- 2026-08-12T11:40:00+08:00 `REVIEWED`: Codex re-review MODIFY; realized metrics are now PIT-prefixed, but first-decision input still leaks whole-replay OK/QUALIFIED status, and the recorded real-artifact verification command reproduces exit 1 rather than claimed exit 0. No E4 work authorized.
- 2026-08-12T12:10:00+08:00 `IMPLEMENTED`: Second MODIFY applied within the exact two-source-file boundary. Decision-scoped `slot_summaries` now expose only the fixed outcome-free eligibility label `PIT_ELIGIBILITY_STATUS='ELIGIBLE'` and never read the whole-replay `candidates.status/verdict`, so the first decision no longer leaks `OK/QUALIFIED`; the whole-replay aggregate verdict survives only in the `decision_date=None` audit digest (never a model input). Negative regression extended to also flip whole-replay `candidates.status/verdict`; explicit first-decision status-semantics test added. Real-artifact verification script import bootstrap corrected so the recorded command reproduces exit 0 (first-decision status `ELIGIBLE`, 0 refs, n_windows=0). 61 focused / 107 adjacent tests pass, ruff/py_compile/git diff --check clean; scope-check still red on Codex/bridge-owned `.claude/discussion.md` + `.claude/settings.json` baseline-order items (re-freeze pending).
- 2026-08-12T12:25:00+08:00 `REVIEWED`: Codex independent behavior review passed the two prior PIT findings (61 focused tests and real-artifact verification exit 0), but verdict is BLOCKED because mandatory scope-check remains exit 2 on Codex/bridge-owned handoff/settings state outside the stale baseline. No further source change requested; fresh Codex baseline freeze is required before acceptance.
- 2026-08-12T13:57:21+08:00 `READY`: Baseline frozen; implementation may start.
- 2026-08-12T14:00:00+08:00 `READY`: Codex completed exactly one baseline-refresh planning phase after the current handoff/settings state. Exact three-file whitelist preserved; fresh scope-check exit 0 with no violations. This is not the final acceptance review and does not upgrade evidence.
- 2026-08-12T13:58:15+08:00 `READY`: Baseline frozen; implementation may start.
- 2026-08-12T14:12:27+08:00 `VERIFIED`: Codex ACCEPT: fresh scope-check exit 0; 61 focused and 107 adjacent tests passed; real PIT artifact exit 0; Ruff, compile and git diff check passed. Evidence remains LOCAL_IMPLEMENTED / RESEARCH_ONLY; no production or PATH/BUSINESS claim.
- 2026-08-12T14:12:46+08:00 `CLOSED`: Closed after separate Codex reproduction and ACCEPT review. Deliverable is research-only bounded fusion; E4 may enter a new read-only location task.
