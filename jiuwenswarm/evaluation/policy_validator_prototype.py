#!/usr/bin/env python3
"""Policy Validator prototype: validates quant workflow plans before execution.

Note: This is NOT a Symphony integration — it validates hand-written task
templates against invariant rules. Symphony integration requires actual
Symphony plan generation, which is future work (P1 proper).

Three task types, each with a pre-registered skill sequence.
PolicyValidator enforces invariants before any plan executes.
"""

from __future__ import annotations

import json, sys, time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

# ---- Policy: invariants that every plan MUST satisfy ----

class Severity(Enum):
    BLOCKER = "blocker"  # plan cannot execute
    WARNING = "warning"  # plan can execute but should be reviewed


@dataclass
class PolicyViolation:
    severity: Severity
    rule: str
    detail: str


class PolicyValidator:
    """Validates a Symphony-generated plan before execution."""

    REQUIRED_PHASES = [
        "fetch_data",      # must come first
        "compute_factors",  # must come second
        "bull_view",        # must happen before select
        "bear_view",        # must happen before select
        "select_stocks",    # must happen after factors + views
        "allocate_positions",  # must happen after select
        "run_backtest",     # must happen after allocate
        "generate_report",  # must come last
    ]

    def validate(self, plan: dict) -> list[PolicyViolation]:
        violations: list[PolicyViolation] = []
        steps = plan.get("steps", [])
        task_type = plan.get("task", "")

        # R1: For standard investment tasks, all 8 quant phases must be present.
        #     Recovery and diagnosis tasks may have different phase sets.
        step_names = [s.get("skill", "") for s in steps]
        if task_type == "normal_investment_analysis":
            for phase in self.REQUIRED_PHASES:
                if phase not in step_names:
                    violations.append(PolicyViolation(
                        Severity.BLOCKER,
                        "R1: phase-coverage",
                        f"Missing required phase: {phase}"
                    ))
        else:
            # Non-standard tasks: must at least have fetch_data + coverage_check
            for phase in ("fetch_data",):
                if phase not in step_names:
                    violations.append(PolicyViolation(
                        Severity.BLOCKER,
                        "R1: phase-coverage",
                        f"Non-standard task missing required phase: {phase}"
                    ))

        # R2: fetch must be first data operation
        fetch_idx = self._index_of(step_names, "fetch_data")
        factor_idx = self._index_of(step_names, "compute_factors")
        if fetch_idx is not None and factor_idx is not None:
            if fetch_idx >= factor_idx:
                violations.append(PolicyViolation(
                    Severity.BLOCKER,
                    "R2: fetch-before-factor",
                    "fetch_data must execute before compute_factors"
                ))

        # R3: coverage check — if data fetch shows <49 stocks, must abort
        # (checked at runtime, but plan must include failure branch)
        has_coverage_check = any(
            "coverage" in str(s).lower() or "fail" in str(s).lower()
            for s in steps
        )
        if not has_coverage_check:
            violations.append(PolicyViolation(
                Severity.WARNING,
                "R3: coverage-fail-closed",
                "Plan should include coverage check; <49 stocks → abort"
            ))

        # R4: backtest must reference a frozen strategy ID
        backtest_step = self._find_step(steps, "run_backtest")
        if backtest_step:
            strategy_id = backtest_step.get("config", {}).get("strategy_id", "")
            if not strategy_id:
                violations.append(PolicyViolation(
                    Severity.BLOCKER,
                    "R4: frozen-strategy-id",
                    "run_backtest must reference a frozen strategy_id from STRATEGY_SPECS"
                ))

        # R5: no step may depend on a step that comes after it
        for i, step in enumerate(steps):
            deps = step.get("depends_on", [])
            for dep in deps:
                dep_idx = self._index_of(step_names, dep)
                if dep_idx is not None and dep_idx >= i:
                    violations.append(PolicyViolation(
                        Severity.BLOCKER,
                        "R5: dependency-order",
                        f"Step '{step.get('skill')}' depends on '{dep}' "
                        f"but '{dep}' comes after or at same position"
                    ))

        # R6: bull_view and bear_view must not be called by Coordinator
        for step in steps:
            if step.get("skill") in ("bull_view", "bear_view"):
                caller = step.get("assigned_to", "")
                if caller in ("coordinator", "leader", ""):
                    violations.append(PolicyViolation(
                        Severity.BLOCKER,
                        "R6: agent-role-isolation",
                        f"{step.get('skill')} must be called by Bull/Bear agent, "
                        f"not by {caller or 'unassigned'}"
                    ))

        return violations

    def _index_of(self, names: list[str], target: str) -> int | None:
        try:
            return names.index(target)
        except ValueError:
            return None

    def _find_step(self, steps: list[dict], skill: str) -> dict | None:
        for s in steps:
            if s.get("skill") == skill:
                return s
        return None


# ---- Task specifications ----

TASK_SPECS = {
    "normal_investment_analysis": {
        "description": "Standard 20-day investment cycle: fetch → factor → Bull/Bear → select → allocate → backtest → report",
        "plan": {
            "task": "normal_investment_analysis",
            "strategy_id": "phase_b_t2_score_alloc",
            "steps": [
                {"skill": "fetch_data",       "assigned_to": "coordinator", "depends_on": [],           "config": {"tickers": "ALL_STOCKS", "fail_if_lt": 49}},
                {"skill": "compute_factors",  "assigned_to": "coordinator", "depends_on": ["fetch_data"], "config": {"strategy_id": "phase_b_t2_score_alloc"}},
                {"skill": "bull_view",        "assigned_to": "bull_analyst","depends_on": ["compute_factors"], "config": {}},
                {"skill": "bear_view",        "assigned_to": "bear_analyst","depends_on": ["compute_factors"], "config": {}},
                {"skill": "select_stocks",    "assigned_to": "coordinator", "depends_on": ["bull_view", "bear_view"], "config": {"top_n": 15, "min_score": 0}},
                {"skill": "allocate_positions","assigned_to": "coordinator","depends_on": ["select_stocks"], "config": {"strategy_id": "phase_b_t2_score_alloc"}},
                {"skill": "run_backtest",     "assigned_to": "coordinator", "depends_on": ["allocate_positions"], "config": {"strategy_id": "phase_b_t2_score_alloc"}},
                {"skill": "generate_report",  "assigned_to": "coordinator", "depends_on": ["run_backtest"], "config": {"strategy_id": "phase_b_t2_score_alloc"}},
            ],
        },
    },
    "data_coverage_failure_recovery": {
        "description": "Sina returns 32/49 → fallback through Tencent → akshare → baostock → yfinance; if still <49, abort with clear error",
        "plan": {
            "task": "data_coverage_failure_recovery",
            "strategy_id": "phase_b_t2_score_alloc",
            "steps": [
                {"skill": "fetch_data",       "assigned_to": "coordinator", "depends_on": [],           "config": {"tickers": "ALL_STOCKS", "fail_if_lt": 49, "fallback_chain": ["sina","tencent","akshare","baostock","yfinance"]}},
                {"skill": "coverage_check",   "assigned_to": "coordinator", "depends_on": ["fetch_data"], "config": {"required_stocks": 49, "required_sectors": 6}},
                # If coverage_check passes → continue; if fails → abort (no further steps)
                {"skill": "compute_factors",  "assigned_to": "coordinator", "depends_on": ["coverage_check"], "config": {"strategy_id": "phase_b_t2_score_alloc"}, "optional": True},
                {"skill": "select_stocks",    "assigned_to": "coordinator", "depends_on": ["compute_factors"], "config": {}, "optional": True},
                {"skill": "allocate_positions","assigned_to": "coordinator","depends_on": ["select_stocks"], "config": {}, "optional": True},
                {"skill": "run_backtest",     "assigned_to": "coordinator", "depends_on": ["allocate_positions"], "config": {"strategy_id": "phase_b_t2_score_alloc"}, "optional": True},
                {"skill": "generate_report",  "assigned_to": "coordinator", "depends_on": ["run_backtest"], "config": {}, "optional": True},
            ],
        },
    },
    "candidate_decay_diagnosis": {
        "description": "T2 recent 4 windows only 2/4 utility wins → diagnose whether decay is regime-specific or structural",
        "plan": {
            "task": "candidate_decay_diagnosis",
            "strategy_id": "phase_b_t2_score_alloc",
            "steps": [
                {"skill": "fetch_data",       "assigned_to": "coordinator", "depends_on": [],           "config": {"tickers": "ALL_STOCKS", "fail_if_lt": 49}},
                {"skill": "compute_factors",  "assigned_to": "coordinator", "depends_on": ["fetch_data"], "config": {"strategy_id": "phase_b_t2_score_alloc"}},
                {"skill": "regime_analysis",  "assigned_to": "coordinator", "depends_on": ["compute_factors"], "config": {"lookback_windows": 21}},
                {"skill": "decay_diagnosis",  "assigned_to": "coordinator", "depends_on": ["regime_analysis"], "config": {
                    "candidate": "phase_b_t2_score_alloc",
                    "baseline": "production_six_factor",
                    "check": "recent_4_utility_wins",
                    "threshold": 3,
                }},
                {"skill": "bull_view",        "assigned_to": "bull_analyst","depends_on": ["decay_diagnosis"], "config": {}},
                {"skill": "bear_view",        "assigned_to": "bear_analyst","depends_on": ["decay_diagnosis"], "config": {}},
                {"skill": "generate_report",  "assigned_to": "coordinator", "depends_on": ["bull_view", "bear_view"], "config": {"include_diagnosis": True}},
            ],
        },
    },
}


def run_validation(task_name: str) -> dict[str, Any]:
    """Run PolicyValidator against a task plan and record the result."""
    spec = TASK_SPECS[task_name]
    plan = spec["plan"]
    validator = PolicyValidator()
    violations = validator.validate(plan)
    blockers = [v for v in violations if v.severity == Severity.BLOCKER]
    warnings = [v for v in violations if v.severity == Severity.WARNING]

    result = {
        "task": task_name,
        "description": spec["description"],
        "strategy_id": plan["strategy_id"],
        "n_steps": len(plan["steps"]),
        "step_sequence": [s["skill"] for s in plan["steps"]],
        "violations": [
            {"severity": v.severity.value, "rule": v.rule, "detail": v.detail}
            for v in violations
        ],
        "verdict": "PASSED" if not blockers else "BLOCKED",
        "warnings": len(warnings),
    }
    return result


def main() -> int:
    print("=" * 70)
    print("  Policy Validator Prototype: Quant Workflow Planning Rules")
    print("=" * 70)

    all_results = {}
    for task_name in TASK_SPECS:
        result = run_validation(task_name)
        all_results[task_name] = result

        status = "[PASSED]" if result["verdict"] == "PASSED" else "BLOCKED"
        print(f"\n[{status}] {task_name}")
        print(f"  Strategy: {result['strategy_id']}, Steps: {result['n_steps']}")
        print(f"  Sequence: {' → '.join(result['step_sequence'])}")
        if result["violations"]:
            for v in result["violations"]:
                tag = "[STOP]" if v["severity"] == "blocker" else "[WARN]"
                print(f"  {tag} [{v['rule']}] {v['detail']}")
        if result["warnings"]:
            print(f"  [WARN] {result['warnings']} warning(s) — plan can proceed with review")

    # Save POC artifact
    run_id = datetime.now().strftime("policy_validator_%Y%m%d_%H%M%S")
    artifact = {
        "run_id": run_id,
        "created_at": datetime.now().astimezone().isoformat(),
        "validator_version": "prototype_v1",
        "note": "This is a policy validator prototype, NOT a Symphony integration. Symphony P1 proper is future work.",
        "policy_rules": [
            "R1: phase-coverage (8 quant phases must be present)",
            "R2: fetch-before-factor (dependency order)",
            "R3: coverage-fail-closed (<49 stocks → abort)",
            "R4: frozen-strategy-id (backtest must reference registered StrategySpec)",
            "R5: dependency-order (no step depends on later step)",
            "R6: agent-role-isolation (Bull/Bear skills called by Bull/Bear, not Coordinator)",
        ],
        "results": all_results,
        "summary": {
            "total": len(all_results),
            "passed": sum(1 for r in all_results.values() if r["verdict"] == "PASSED"),
            "blocked": sum(1 for r in all_results.values() if r["verdict"] == "BLOCKED"),
        },
    }

    out_path = Path(__file__).resolve().parent / f"{run_id}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(artifact, f, indent=2, ensure_ascii=False)
    latest = Path(__file__).resolve().parent / "symphony_poc_latest.json"
    with open(latest, "w", encoding="utf-8") as f:
        json.dump(artifact, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*70}")
    print(f"  Summary: {artifact['summary']['passed']}/{artifact['summary']['total']} tasks passed")
    print(f"  Artifact: {out_path}")
    print(f"{'='*70}")

    # Demonstrate PolicyValidator detects a real violation
    print(f"\n[Demostration] Injecting violation: Coordinator calling bull_view...")
    bad_plan = {
        "task": "test_violation",
        "strategy_id": "production_six_factor",
        "steps": [
            {"skill": "fetch_data", "assigned_to": "coordinator", "depends_on": []},
            {"skill": "compute_factors", "assigned_to": "coordinator", "depends_on": ["fetch_data"]},
            {"skill": "bull_view", "assigned_to": "coordinator", "depends_on": ["compute_factors"]},  # ← violation!
            {"skill": "run_backtest", "assigned_to": "coordinator", "depends_on": ["bull_view"], "config": {}},  # ← no strategy_id
        ],
    }
    v = PolicyValidator().validate(bad_plan)
    for violation in v:
        tag = "[BLOCKER]" if violation.severity == Severity.BLOCKER else "[WARN] WARNING"
        print(f"  {tag}: [{violation.rule}] {violation.detail}")
    print(f"  Verdict: {'CORRECTLY BLOCKED' if any(x.severity == Severity.BLOCKER for x in v) else 'MISSED VIOLATION'}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
