"""Agent-A: Structured Agent output schemas and analysis routing.

RegimeDiagnosis contains only fields that detect_with_detail() actually returns.
AnalysisPlaybookRouter selects analysis templates without changing strategy weights.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import ClassVar

# ---- Schema 1: Regime Diagnosis (exactly what detect_with_detail returns) ----


@dataclass(frozen=True)
class RegimeDiagnosis:
    """Machine-readable regime diagnosis. Only fields the RPC actually returns."""

    final: str       # "bull" | "bear" | "range"
    technical: str   # "bull" | "bear" | "range"
    index: str       # "bull" | "bear" | "range"
    consensus: bool  # True = tech and index agree → high confidence

    @staticmethod
    def from_detail(detail: dict) -> "RegimeDiagnosis":
        return RegimeDiagnosis(
            final=str(detail["final"]),
            technical=str(detail["technical"]),
            index=str(detail["index"]),
            consensus=bool(detail["consensus"]),
        )

    def confidence(self) -> str:
        """Human-readable confidence level."""
        if self.consensus and self.final != "range":
            return "high"
        if not self.consensus and self.technical != "range" and self.index != "range":
            return "low"  # tech vs index conflict
        return "medium"

    def is_bull(self) -> bool:
        return self.final == "bull"

    def is_range(self) -> bool:
        return self.final == "range"


# ---- Schema 2: Structured evidence for Bull/Bear recommendations ----


@dataclass(frozen=True)
class FactorEvidence:
    """A single factor's contribution to a stock recommendation."""

    factor_name: str    # e.g. "momentum_20"
    value: float        # e.g. 0.153
    interpretation: str  # e.g. "positive" | "negative" | "neutral"


@dataclass
class StockRecommendation:
    """Structured Bull or Bear recommendation for one stock."""

    ticker: str
    score: float
    evidences: list[FactorEvidence]  # which factors drove this score
    rationale: str                   # 1-2 sentence reason


# ---- Schema 3: Analysis Playbook Router ----


@dataclass(frozen=True)
class AnalysisPlaybook:
    """Pre-registered analysis template. Router selects one, never generates."""

    name: str
    description: str
    required_skills: tuple[str, ...]
    output_fields: tuple[str, ...]


# Only three registered playbooks. Router must return one of these.
_REGISTERED_PLAYBOOKS: tuple[AnalysisPlaybook, ...] = (
    AnalysisPlaybook(
        name="standard_investment_cycle",
        description="Full 8-phase quant pipeline: fetch → factor → Bull/Bear → select → allocate → backtest → report",
        required_skills=(
            "fetch_data", "compute_factors", "bull_view", "bear_view",
            "select_stocks", "allocate_positions", "run_backtest", "generate_report",
        ),
        output_fields=("portfolio", "weights", "backtest_metrics", "report"),
    ),
    AnalysisPlaybook(
        name="coverage_failure_recovery",
        description="Data coverage <49 stocks → multi-source fallback → abort if still incomplete",
        required_skills=(
            "fetch_data", "coverage_check",
        ),
        output_fields=("coverage_status", "missing_tickers", "fallback_chain_used"),
    ),
    AnalysisPlaybook(
        name="candidate_decay_diagnosis",
        description="Challenger model showing recent decay → diagnose whether regime-specific or structural",
        required_skills=(
            "fetch_data", "compute_factors", "regime_analysis",
            "decay_diagnosis", "bull_view", "bear_view", "generate_report",
        ),
        output_fields=("decay_verdict", "regime_breakdown", "recommendation"),
    ),
)

_PLAYBOOK_BY_NAME: ClassVar[dict] = {p.name: p for p in _REGISTERED_PLAYBOOKS}


class AnalysisPlaybookRouter:
    """Routes a RegimeDiagnosis + context to exactly one registered playbook.

    Pure function: same inputs → same output. Never invents playbooks.
    """

    @staticmethod
    def route(
        diagnosis: RegimeDiagnosis,
        data_available: bool = True,
        coverage_ok: bool = True,
        candidate_decay_suspected: bool = False,
    ) -> AnalysisPlaybook:
        """Select the appropriate analysis template.

        Rules (in priority order):
          1. If coverage is insufficient → coverage_failure_recovery
          2. If candidate model shows recent decay → candidate_decay_diagnosis
          3. Otherwise → standard_investment_cycle
        """
        if not data_available or not coverage_ok:
            return _PLAYBOOK_BY_NAME["coverage_failure_recovery"]

        if candidate_decay_suspected:
            return _PLAYBOOK_BY_NAME["candidate_decay_diagnosis"]

        return _PLAYBOOK_BY_NAME["standard_investment_cycle"]

    @staticmethod
    def registered_playbooks() -> tuple[str, ...]:
        return tuple(p.name for p in _REGISTERED_PLAYBOOKS)


# ---- Validation: same input → same output ----


def validate_router_determinism() -> None:
    """Property: identical inputs always route to the same playbook."""
    diag = RegimeDiagnosis(final="bull", technical="bull", index="bull", consensus=True)

    r1 = AnalysisPlaybookRouter.route(diag)
    r2 = AnalysisPlaybookRouter.route(diag)
    assert r1.name == r2.name, f"Non-deterministic: {r1.name} vs {r2.name}"

    # Coverage failure must route to recovery
    r3 = AnalysisPlaybookRouter.route(diag, coverage_ok=False)
    assert r3.name == "coverage_failure_recovery", f"Expected recovery, got {r3.name}"

    # Decay suspected must route to diagnosis
    r4 = AnalysisPlaybookRouter.route(diag, candidate_decay_suspected=True)
    assert r4.name == "candidate_decay_diagnosis", f"Expected diagnosis, got {r4.name}"

    # All routes must return registered playbooks
    for pb in (r1, r2, r3, r4):
        assert pb.name in AnalysisPlaybookRouter.registered_playbooks(), (
            f"Unregistered playbook: {pb.name}"
        )


def validate_regime_diagnosis_roundtrip() -> None:
    """Property: RegimeDiagnosis accurately reflects detect_with_detail() output."""
    detail = {"final": "bull", "technical": "bull", "index": "range", "consensus": False}
    diag = RegimeDiagnosis.from_detail(detail)
    assert diag.final == "bull"
    assert diag.consensus is False
    assert diag.confidence() == "medium"

    detail2 = {"final": "bull", "technical": "bull", "index": "bull", "consensus": True}
    diag2 = RegimeDiagnosis.from_detail(detail2)
    assert diag2.confidence() == "high"

    detail3 = {"final": "range", "technical": "bull", "index": "bear", "consensus": False}
    diag3 = RegimeDiagnosis.from_detail(detail3)
    assert diag3.confidence() == "low"
