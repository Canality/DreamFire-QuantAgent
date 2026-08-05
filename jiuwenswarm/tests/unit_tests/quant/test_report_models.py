"""Unit tests for reporting models — Phase R1."""

from datetime import datetime, timezone

import pytest

from jiuwenswarm.quant.reporting.models import (
    AgentView,
    CompanyFactBundle,
    EvidenceRef,
    MetricFact,
    PortfolioSnapshot,
    ReportQualityResult,
)


def test_evidence_ref_construction():
    now = datetime.now(timezone.utc)
    ref = EvidenceRef(
        evidence_id="e1",
        source_type="market_data",
        source_name="Sina Finance",
        source_url="https://example.com",
        period_end=None,
        published_at=None,
        available_at=now,
        retrieved_at=now,
        content_sha256="abc123",
    )
    assert ref.evidence_id == "e1"
    assert ref.source_type == "market_data"


def test_metric_fact_available():
    f = MetricFact(
        name="momentum_20",
        value=0.084,
        unit="ratio",
        status="available",
        evidence_ids=("e1",),
    )
    assert f.status == "available"
    assert f.value == 0.084


def test_metric_fact_unavailable():
    f = MetricFact(
        name="pe_ratio",
        value=None,
        unit=None,
        status="unavailable",
        evidence_ids=(),
    )
    assert f.status == "unavailable"
    assert f.value is None


def test_agent_view_alpha():
    view = AgentView(
        role="alpha",
        verdict="overweight",
        confidence="high",
        candidate_tickers=("000333.SZ", "000651.SZ"),
        warnings=(),
        evidence_ids=("e1", "e2"),
        unknown_fields=(),
        summary="Strong momentum signal.",
    )
    assert view.role == "alpha"
    assert view.verdict == "overweight"


def test_agent_view_risk_evidence_with_unknown():
    view = AgentView(
        role="risk_evidence",
        verdict="underweight",
        confidence="low",
        candidate_tickers=(),
        warnings=("High volatility",),
        evidence_ids=(),
        unknown_fields=("vol_ratio_percentile", "sector_momentum_persistence"),
        summary="",
    )
    assert view.role == "risk_evidence"
    assert len(view.unknown_fields) == 2


@pytest.mark.parametrize("role", ["bull", "bear", "coordinator", "unknown"])
def test_agent_view_rejects_retired_or_unknown_roles(role):
    with pytest.raises(ValueError, match="unsupported AgentView role"):
        AgentView(
            role=role,
            verdict="neutral",
            confidence="medium",
            candidate_tickers=(),
            warnings=(),
            evidence_ids=(),
            unknown_fields=(),
        )


def test_company_fact_bundle_zero_weight():
    now = datetime.now(timezone.utc)
    bundle = CompanyFactBundle(
        ticker="000333.SZ",
        report_code="000333",
        name="美的集团",
        sector="家用电器",
        as_of_time=now,
        portfolio_weight=0.0,
        selected=False,
        weight_zero_reason="因子得分未进入 Top 15",
        technical_facts=(),
        fundamental_facts=(),
        event_facts=(),
        risk_facts=(),
        agent_views=(),
        data_provider_status="complete",
    )
    assert bundle.selected is False
    assert bundle.portfolio_weight == 0.0


def test_portfolio_snapshot():
    now = datetime.now(timezone.utc)
    ps = PortfolioSnapshot(
        as_of_time=now,
        holdings={"000333.SZ": 0.08, "000651.SZ": 0.07},
        cash=0.05,
        total_equity=0.95,
        n_selected=15,
        n_sectors_represented=6,
        strategy_id="phase_b_t2_score_alloc",
        contract_hash="abc123",
    )
    assert ps.n_selected == 15
    assert ps.cash == 0.05


def test_report_quality_result_pass():
    r = ReportQualityResult(
        passed=True,
        blockers=(),
        warnings=("Minor: 1 evidence ID unreferenced",),
        metrics={"reports_on_disk": 49},
    )
    assert r.passed is True


def test_report_quality_result_fail():
    r = ReportQualityResult(
        passed=False,
        blockers=("Missing reports: ['000333']",),
        warnings=(),
        metrics={"reports_missing": 1},
    )
    assert r.passed is False
    assert len(r.blockers) == 1
