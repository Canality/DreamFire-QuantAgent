"""Domain Rails for quantitative report generation.

Each Rail runs at report generation time and can block or warn.
Rails are NOT offline scripts — they must execute during actual Agent/Team runs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple


@dataclass
class RailResult:
    """Result of running a single rail check."""
    rail_name: str
    passed: bool = False
    blockers: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)


class EvidenceRail:
    """Validates that all displayed numbers trace to real EvidenceRef objects."""

    def __init__(self, quality_gate_result: Any):
        self._qg = quality_gate_result

    def check(self) -> RailResult:
        result = RailResult(rail_name="EvidenceRail")
        if hasattr(self._qg, 'passed') and not self._qg.passed:
            result.passed = False
            result.blockers = list(getattr(self._qg, 'blockers', []))
        else:
            result.passed = True
        return result


class ReportCompletenessRail:
    """Validates that all required report files exist."""

    def __init__(self, expected_count: int, actual_count: int):
        self._expected = expected_count
        self._actual = actual_count

    def check(self) -> RailResult:
        result = RailResult(rail_name="ReportCompletenessRail")
        if self._actual < self._expected:
            result.passed = False
            result.blockers.append(
                f"Missing reports: {self._actual}/{self._expected} on disk"
            )
        else:
            result.passed = True
        result.metrics = {"expected": self._expected, "actual": self._actual}
        return result


class PortfolioConsistencyRail:
    """Validates weight consistency across all outputs."""

    def __init__(self, portfolio_weights: Dict[str, float], bundle_weights: Dict[str, float]):
        self._pw = portfolio_weights
        self._bw = bundle_weights

    def check(self) -> RailResult:
        result = RailResult(rail_name="PortfolioConsistencyRail")
        mismatches = []
        all_tickers = set(self._pw) | set(self._bw)
        for t in all_tickers:
            pw = self._pw.get(t, 0.0)
            bw = self._bw.get(t, 0.0)
            if abs(pw - bw) > 1e-6:
                mismatches.append(f"{t}: p={pw:.6f}, b={bw:.6f}")
        if mismatches:
            result.passed = False
            result.blockers.append(f"Weight mismatches: {len(mismatches)} tickers")
        else:
            result.passed = True
        return result


class ResourceBudgetRail:
    """Validates resource usage against configured budget."""

    def __init__(self, max_duration_s: float | None = None, max_tokens: int | None = None):
        self._max_duration = max_duration_s
        self._max_tokens = max_tokens

    def check(self, duration_s: float | None = None, tokens: int | None = None) -> RailResult:
        result = RailResult(rail_name="ResourceBudgetRail", passed=True)
        dur = duration_s or 0
        tok = tokens or 0
        if self._max_duration and dur > self._max_duration:
            result.warnings.append(f"Duration {dur:.0f}s exceeds budget {self._max_duration:.0f}s")
        if self._max_tokens and tok > self._max_tokens:
            result.warnings.append(f"Tokens {tok} exceeds budget {self._max_tokens}")
        result.metrics = {"duration_s": dur, "tokens": tok}
        return result


def run_all_rails(
    rails: List[Any],
    **context,
) -> Tuple[bool, List[RailResult]]:
    """Execute all registered rails. Returns (all_passed, results)."""
    results = []
    all_passed = True
    for rail in rails:
        r = rail.check(**context) if hasattr(rail.check, '__code__') and 'context' in rail.check.__code__.co_varnames else rail.check()
        results.append(r)
        if not r.passed:
            all_passed = False
    return all_passed, results
