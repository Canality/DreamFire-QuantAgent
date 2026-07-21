"""Property tests for Agent-A structured output schemas and routing."""

import pytest
from jiuwenswarm.quant.agent_structured_output import (
    RegimeDiagnosis,
    AnalysisPlaybookRouter,
    AnalysisPlaybook,
    FactorEvidence,
    StockRecommendation,
    validate_router_determinism,
    validate_regime_diagnosis_roundtrip,
)


class TestRegimeDiagnosis:
    def test_from_detail_preserves_all_fields(self):
        detail = {"final": "bull", "technical": "bull", "index": "bull", "consensus": True}
        diag = RegimeDiagnosis.from_detail(detail)
        assert diag.final == "bull"
        assert diag.technical == "bull"
        assert diag.index == "bull"
        assert diag.consensus is True

    def test_from_detail_with_conflict(self):
        detail = {"final": "range", "technical": "bull", "index": "bear", "consensus": False}
        diag = RegimeDiagnosis.from_detail(detail)
        assert diag.final == "range"
        assert diag.confidence() == "low"

    def test_confidence_high(self):
        diag = RegimeDiagnosis(final="bull", technical="bull", index="bull", consensus=True)
        assert diag.confidence() == "high"

    def test_confidence_medium_range_consensus_not_high(self):
        diag = RegimeDiagnosis(final="range", technical="range", index="range", consensus=True)
        assert diag.confidence() == "medium"  # range never gets "high"

    def test_confidence_medium_one_range(self):
        diag = RegimeDiagnosis(final="bull", technical="bull", index="range", consensus=False)
        assert diag.confidence() == "medium"

    def test_is_bull(self):
        assert RegimeDiagnosis("bull", "bull", "bull", True).is_bull()
        assert not RegimeDiagnosis("range", "range", "range", True).is_bull()
        assert not RegimeDiagnosis("bear", "bear", "bear", True).is_bull()

    def test_is_range(self):
        assert RegimeDiagnosis("range", "range", "range", True).is_range()
        assert not RegimeDiagnosis("bull", "bull", "bull", True).is_range()

    def test_roundtrip_property(self):
        validate_regime_diagnosis_roundtrip()


class TestAnalysisPlaybookRouter:
    def test_default_routes_to_standard(self):
        diag = RegimeDiagnosis(final="bull", technical="bull", index="bull", consensus=True)
        pb = AnalysisPlaybookRouter.route(diag)
        assert pb.name == "standard_investment_cycle"

    def test_coverage_failure_routes_to_recovery(self):
        diag = RegimeDiagnosis(final="bull", technical="bull", index="bull", consensus=True)
        pb = AnalysisPlaybookRouter.route(diag, coverage_ok=False)
        assert pb.name == "coverage_failure_recovery"

    def test_no_data_routes_to_recovery(self):
        diag = RegimeDiagnosis(final="range", technical="range", index="range", consensus=True)
        pb = AnalysisPlaybookRouter.route(diag, data_available=False)
        assert pb.name == "coverage_failure_recovery"

    def test_decay_suspected_routes_to_diagnosis(self):
        diag = RegimeDiagnosis(final="bull", technical="bull", index="bull", consensus=True)
        pb = AnalysisPlaybookRouter.route(diag, candidate_decay_suspected=True)
        assert pb.name == "candidate_decay_diagnosis"

    def test_coverage_trumps_decay(self):
        diag = RegimeDiagnosis(final="bull", technical="bull", index="bull", consensus=True)
        pb = AnalysisPlaybookRouter.route(diag, coverage_ok=False, candidate_decay_suspected=True)
        assert pb.name == "coverage_failure_recovery"  # coverage is higher priority

    def test_all_registered_playbooks_are_valid(self):
        for name in AnalysisPlaybookRouter.registered_playbooks():
            # Every registered playbook must be routable
            assert name in ("standard_investment_cycle", "coverage_failure_recovery", "candidate_decay_diagnosis")

    def test_never_returns_unregistered(self):
        diag = RegimeDiagnosis(final="range", technical="range", index="range", consensus=True)
        for data_ok in (True, False):
            for cov_ok in (True, False):
                for decay in (True, False):
                    pb = AnalysisPlaybookRouter.route(diag, data_ok, cov_ok, decay)
                    assert pb.name in AnalysisPlaybookRouter.registered_playbooks(), (
                        f"Unregistered playbook returned: {pb.name}"
                    )

    def test_determinism_property(self):
        validate_router_determinism()


class TestFactorEvidence:
    def test_create_evidence(self):
        ev = FactorEvidence(factor_name="momentum_20", value=0.153, interpretation="positive")
        assert ev.factor_name == "momentum_20"
        assert ev.value == 0.153
        assert ev.interpretation == "positive"

    def test_negative_evidence(self):
        ev = FactorEvidence(factor_name="max_drawdown", value=-0.082, interpretation="negative")
        assert ev.interpretation == "negative"


class TestStockRecommendation:
    def test_bull_recommendation(self):
        rec = StockRecommendation(
            ticker="600519.SH",
            score=0.85,
            evidences=[
                FactorEvidence("momentum_20", 0.12, "positive"),
                FactorEvidence("volume_corr", 0.45, "positive"),
            ],
            rationale="Strong momentum with healthy volume confirmation",
        )
        assert rec.ticker == "600519.SH"
        assert len(rec.evidences) == 2
        assert rec.score == 0.85

    def test_bear_warning(self):
        rec = StockRecommendation(
            ticker="601398.SH",
            score=-0.30,
            evidences=[
                FactorEvidence("max_drawdown", -0.15, "negative"),
                FactorEvidence("volume_corr", -0.22, "negative"),
            ],
            rationale="High drawdown with volume-price divergence — veto",
        )
        assert len(rec.evidences) == 2
        assert rec.score < 0
