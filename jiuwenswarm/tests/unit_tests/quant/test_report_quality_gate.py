"""Unit tests for quality gate — Codex R4 EvidenceRef enforcement."""

import hashlib
from datetime import datetime, timedelta, timezone

import pytest

from jiuwenswarm.quant.reporting.models import (
    CompanyFactBundle,
    EvidenceRef,
    MetricFact,
    PortfolioSnapshot,
)
from jiuwenswarm.quant.reporting.quality_gate import (
    _archive_entry_status,
    validate_submission,
)
from jiuwenswarm.quant.reporting.package_builder import build_candidate_package
from jiuwenswarm.quant.reporting.submission_contract import SubmissionContract

NOW = datetime.now(timezone.utc)


def _make_contract(n: int = 3) -> SubmissionContract:
    codes = tuple(f"{i:06d}.SH" for i in range(1, n + 1))
    return SubmissionContract(
        company_codes=codes,
        company_names={c: f"C{i}" for i, c in enumerate(codes, 1)},
        sectors={c: "T" for c in codes},
        sector_names=("T",),
        source_file="t.xlsx", source_sha256="abc", report_file_extension=".md",
        equity_weight_rule="equities_plus_cash_equals_one", allow_cash=None,
        report_quality_rule="unresolved", unresolved_questions=(),
        contract_status="PROVISIONAL",
    )


def _make_evidence_ref(eid: str, available_at: datetime | None = None) -> EvidenceRef:
    return EvidenceRef(
        evidence_id=eid, source_type="market_data", source_name="TestSource",
        source_url=None, period_end=None, published_at=None,
        available_at=available_at or NOW - timedelta(days=1),
        retrieved_at=NOW, content_sha256="a" * 64,
    )


def _make_bundle(ticker: str, weight: float = 0.0, selected: bool = False,
                 with_valid_tech: bool = True, with_views: bool = False) -> CompanyFactBundle:
    """with_valid_tech=True → fact has evidence_id and valid value."""
    from jiuwenswarm.quant.reporting.models import AgentView

    tech_facts = (
        (MetricFact(name="momentum_20", value=0.05, unit="ratio",
                    status="available", evidence_ids=("e1",)),)
        if with_valid_tech else ()
    )
    views = (
        (AgentView(role="alpha", verdict="neutral", confidence="medium",
                   candidate_tickers=(ticker,), warnings=(), evidence_ids=("e1",),
                   unknown_fields=(), summary="OK"),)
        if with_views else ()
    )
    return CompanyFactBundle(
        ticker=ticker, report_code=ticker.split(".")[0], name=f"C{ticker.split('.')[0]}",
        sector="T", as_of_time=NOW,
        portfolio_weight=weight, selected=selected,
        weight_zero_reason="" if selected else "Not in top",
        technical_facts=tech_facts, fundamental_facts=(),
        event_facts=(), risk_facts=(),
        agent_views=views,
        data_provider_status="complete" if with_valid_tech else "unavailable",
    )


def _make_ps(contract, holdings=None) -> PortfolioSnapshot:
    if holdings is None:
        holdings = {c: 0.0 for c in contract.company_codes}
    return PortfolioSnapshot(
        as_of_time=NOW, holdings=holdings, cash=1.0 - sum(holdings.values()),
        total_equity=sum(holdings.values()),
        n_selected=len([w for w in holdings.values() if w > 0]),
        n_sectors_represented=1,
        strategy_id="test", contract_hash=contract.config_hash(),
    )


# --- Core tests ---

def test_missing_report_blocked():
    c = _make_contract(3)
    bundles = {t: _make_bundle(t) for t in c.company_codes}
    result = validate_submission(c, _make_ps(c), bundles, {"000001", "000002"}, NOW,
                                  evidence_manifest={"e1": _make_evidence_ref("e1")})
    assert not result.passed


def test_exact_report_set_passes():
    c = _make_contract(3)
    bundles = {t: _make_bundle(t) for t in c.company_codes}
    result = validate_submission(c, _make_ps(c), bundles, {"000001", "000002", "000003"}, NOW,
                                  evidence_manifest={"e1": _make_evidence_ref("e1")})
    assert result.passed


def test_package_builder_preserves_prior_run_and_rejects_candidate_reuse(tmp_path):
    c = _make_contract(3)
    historical = tmp_path / "submission_candidates" / "historical-run"
    historical.mkdir(parents=True)
    historical_file = historical / "evidence.json"
    historical_file.write_text("historical", encoding="utf-8")

    bundles = {t: _make_bundle(t) for t in c.company_codes}
    _, _, package_path = build_candidate_package(
        contract=c,
        portfolio=_make_ps(c),
        bundles=bundles,
        output_dir=str(tmp_path),
        candidate_id="direct-test-run",
        evidence_manifest={"e1": _make_evidence_ref("e1")},
    )

    package_dir = tmp_path / "submission_candidates" / "direct-test-run"
    assert package_path == str(package_dir)
    assert historical_file.read_text(encoding="utf-8") == "historical"
    assert {path.name for path in (package_dir / "company_reports").glob("*.md")} == {
        "000001.md",
        "000002.md",
        "000003.md",
    }
    with pytest.raises(FileExistsError, match="immutable candidate already exists"):
        build_candidate_package(
            contract=c,
            portfolio=_make_ps(c),
            bundles=bundles,
            output_dir=str(tmp_path),
            candidate_id="direct-test-run",
            evidence_manifest={"e1": _make_evidence_ref("e1")},
        )


def test_all_unavailable_blocked():
    c = _make_contract(3)
    bundles = {t: _make_bundle(t, with_valid_tech=False) for t in c.company_codes}
    result = validate_submission(c, _make_ps(c), bundles, {"000001", "000002", "000003"}, NOW)
    assert not result.passed
    assert any("unavailable" in b.lower() for b in result.blockers)


def test_no_technical_facts_blocked():
    c = _make_contract(2)
    bundles = {t: _make_bundle(t, with_valid_tech=False) for t in c.company_codes}
    result = validate_submission(c, _make_ps(c), bundles, {"000001", "000002"}, NOW)
    assert not result.passed
    assert any("technical facts" in b.lower() for b in result.blockers)


def test_weight_mismatch_blocked():
    c = _make_contract(2)
    b1 = _make_bundle("000001.SH", weight=0.10, selected=True)
    b2 = _make_bundle("000002.SZ", weight=0.05, selected=True)
    ps = _make_ps(c, {"000001.SH": 0.10, "000002.SZ": 0.10})
    result = validate_submission(c, ps, {"000001.SH": b1, "000002.SZ": b2},
                                  {"000001", "000002"}, NOW,
                                  evidence_manifest={"e1": _make_evidence_ref("e1")})
    assert any("Weight mismatch" in b or "weight" in b.lower() for b in result.blockers)


def test_weight_rule_violation_blocked():
    c = _make_contract(10)
    codes = c.company_codes
    bundles = {t: _make_bundle(t, weight=0.11, selected=True) for t in codes}
    ps = _make_ps(c, {t: 0.11 for t in codes})
    result = validate_submission(c, ps, bundles, set(c.report_codes), NOW,
                                  evidence_manifest={"e1": _make_evidence_ref("e1")})
    assert not result.passed
    assert any("exceeds 1.0" in b for b in result.blockers)


def test_zero_weight_company_pass():
    c = _make_contract(3)
    bundles = {t: _make_bundle(t) for t in c.company_codes}
    result = validate_submission(c, _make_ps(c), bundles, set(c.report_codes), NOW,
                                  evidence_manifest={"e1": _make_evidence_ref("e1")})
    assert result.passed


# --- NEW: EvidenceRef enforcement tests ---

def test_fact_without_evidence_id_blocked():
    """Numeric fact with empty evidence_ids → blocked."""
    c = _make_contract(1)
    ticker = c.company_codes[0]
    fact_no_evidence = MetricFact(
        name="fake_score", value=1.23, unit=None, status="derived", evidence_ids=()
    )
    bundle = CompanyFactBundle(
        ticker=ticker, report_code=ticker.split(".")[0], name="Test", sector="T",
        as_of_time=NOW, portfolio_weight=0.0, selected=False,
        weight_zero_reason="", technical_facts=(fact_no_evidence,),
        fundamental_facts=(), event_facts=(), risk_facts=(),
        agent_views=(), data_provider_status="complete",
    )
    ps = _make_ps(c)
    result = validate_submission(c, ps, {ticker: bundle}, set(c.report_codes), NOW)
    assert not result.passed, "Fact without evidence_id must be blocked"
    assert any("without any evidence" in b.lower() or "without any evidence" in b for b in result.blockers), \
        f"Got blockers: {result.blockers}"


def test_fact_with_dangling_evidence_blocked():
    """Evidence ID not in manifest → blocked."""
    c = _make_contract(1)
    ticker = c.company_codes[0]
    fact_dangling = MetricFact(
        name="momentum_20", value=0.05, unit="ratio",
        status="available", evidence_ids=("e_missing",)
    )
    bundle = CompanyFactBundle(
        ticker=ticker, report_code=ticker.split(".")[0], name="Test", sector="T",
        as_of_time=NOW, portfolio_weight=0.0, selected=False,
        weight_zero_reason="", technical_facts=(fact_dangling,),
        fundamental_facts=(), event_facts=(), risk_facts=(),
        agent_views=(), data_provider_status="complete",
    )
    ps = _make_ps(c)
    # Manifest has "e1" but fact references "e_missing"
    result = validate_submission(c, ps, {ticker: bundle}, set(c.report_codes), NOW,
                                  evidence_manifest={"e1": _make_evidence_ref("e1")})
    assert not result.passed, "Dangling evidence must be blocked"
    assert any("not in manifest" in b.lower() or "invalid evidence" in b.lower() for b in result.blockers), \
        f"Got: {result.blockers}"


def test_fact_with_future_evidence_blocked():
    """Evidence available after decision_time → blocked."""
    c = _make_contract(1)
    ticker = c.company_codes[0]
    future_ref = _make_evidence_ref("e_future", available_at=NOW + timedelta(days=30))
    fact = MetricFact(
        name="momentum_20", value=0.05, unit="ratio",
        status="available", evidence_ids=("e_future",)
    )
    bundle = CompanyFactBundle(
        ticker=ticker, report_code=ticker.split(".")[0], name="Test", sector="T",
        as_of_time=NOW, portfolio_weight=0.0, selected=False,
        weight_zero_reason="", technical_facts=(fact,),
        fundamental_facts=(), event_facts=(), risk_facts=(),
        agent_views=(), data_provider_status="complete",
    )
    ps = _make_ps(c)
    result = validate_submission(c, ps, {ticker: bundle}, set(c.report_codes), NOW,
                                  evidence_manifest={"e_future": future_ref})
    assert not result.passed, "Future evidence must be blocked"
    assert any("future evidence" in b.lower() for b in result.blockers), f"Got: {result.blockers}"


def test_fact_with_bad_hash_evidence_blocked():
    """EvidenceRef with empty/invalid content_sha256 → blocked."""
    c = _make_contract(1)
    ticker = c.company_codes[0]
    bad_ref = EvidenceRef(
        evidence_id="e_bad", source_type="market_data", source_name="X",
        source_url=None, period_end=None, published_at=None,
        available_at=NOW - timedelta(days=1), retrieved_at=NOW,
        content_sha256="",  # empty!
    )
    fact = MetricFact(
        name="momentum_20", value=0.05, unit="ratio",
        status="available", evidence_ids=("e_bad",)
    )
    bundle = CompanyFactBundle(
        ticker=ticker, report_code=ticker.split(".")[0], name="Test", sector="T",
        as_of_time=NOW, portfolio_weight=0.0, selected=False,
        weight_zero_reason="", technical_facts=(fact,),
        fundamental_facts=(), event_facts=(), risk_facts=(),
        agent_views=(), data_provider_status="complete",
    )
    ps = _make_ps(c)
    result = validate_submission(c, ps, {ticker: bundle}, set(c.report_codes), NOW,
                                  evidence_manifest={"e_bad": bad_ref})
    assert not result.passed, "Evidence with empty hash must be blocked"
    assert any("hash" in b.lower() for b in result.blockers), f"Got: {result.blockers}"


def test_fact_with_valid_evidence_passes():
    """Fact with valid evidence in manifest → passes."""
    c = _make_contract(1)
    ticker = c.company_codes[0]
    good_ref = _make_evidence_ref("e_good")
    fact = MetricFact(
        name="momentum_20", value=0.05, unit="ratio",
        status="available", evidence_ids=("e_good",)
    )
    bundle = CompanyFactBundle(
        ticker=ticker, report_code=ticker.split(".")[0], name="Test", sector="T",
        as_of_time=NOW, portfolio_weight=0.0, selected=False,
        weight_zero_reason="", technical_facts=(fact,),
        fundamental_facts=(), event_facts=(), risk_facts=(),
        agent_views=(), data_provider_status="complete",
    )
    ps = _make_ps(c)
    result = validate_submission(c, ps, {ticker: bundle}, set(c.report_codes), NOW,
                                  evidence_manifest={"e_good": good_ref})
    assert result.passed, f"Valid evidence should pass, got blockers: {result.blockers}"


def _fake_archive(archived_ref: EvidenceRef, content: bytes):
    """Build a minimal archive exposing read() + build_manifest()."""
    class _Archive:
        def __init__(self) -> None:
            self._manifest = {archived_ref.evidence_id: archived_ref}
            self._content = {archived_ref.evidence_id: content}

        def read(self, evidence_id: str) -> bytes | None:
            return self._content.get(evidence_id)

        def build_manifest(self) -> dict[str, EvidenceRef]:
            return dict(self._manifest)

    return _Archive()


def test_archive_status_accepts_same_content_with_different_retrieved_at():
    """Same identity+content but a fresh retrieved_at must pass (shared archive)."""
    eid = "ann-test-0001"
    content = b'{"raw": true}'
    sha = hashlib.sha256(content).hexdigest()
    archived_ref = EvidenceRef(
        evidence_id=eid, source_type="disclosure", source_name="TestSource",
        source_url="https://example.invalid/source", period_end=None,
        published_at=None, available_at=None,
        retrieved_at=NOW - timedelta(hours=2), content_sha256=sha,
    )
    # identical identity/content but a later retrieval time
    expected_ref = EvidenceRef(
        evidence_id=eid, source_type="disclosure", source_name="TestSource",
        source_url="https://example.invalid/source", period_end=None,
        published_at=None, available_at=None,
        retrieved_at=NOW, content_sha256=sha,
    )
    archive = _fake_archive(archived_ref, content)
    status = _archive_entry_status(
        archive, archive.build_manifest(), eid, expected_ref,
    )
    assert status is None, f"Same content with new retrieved_at must pass: {status}"


def test_archive_status_rejects_content_hash_mismatch():
    """Different content_sha256 must still fail closed."""
    eid = "ann-test-0002"
    content = b'{"raw": "other"}'
    sha = hashlib.sha256(content).hexdigest()
    archived_ref = EvidenceRef(
        evidence_id=eid, source_type="disclosure", source_name="TestSource",
        source_url="https://example.invalid/source", period_end=None,
        published_at=None, available_at=None,
        retrieved_at=NOW, content_sha256=sha,
    )
    expected_ref = EvidenceRef(
        evidence_id=eid, source_type="disclosure", source_name="TestSource",
        source_url="https://example.invalid/source", period_end=None,
        published_at=None, available_at=None,
        retrieved_at=NOW + timedelta(minutes=1),
        content_sha256="f" * 64,
    )
    archive = _fake_archive(archived_ref, content)
    status = _archive_entry_status(
        archive, archive.build_manifest(), eid, expected_ref,
    )
    assert status is not None, "Content hash mismatch must fail closed"


def test_archive_status_rejects_wrong_source_url():
    """Identity/source lineage change must still be rejected."""
    eid = "ann-test-0003"
    content = b'{"raw": true}'
    sha = hashlib.sha256(content).hexdigest()
    archived_ref = EvidenceRef(
        evidence_id=eid, source_type="disclosure", source_name="TestSource",
        source_url="https://example.invalid/source", period_end=None,
        published_at=None, available_at=None,
        retrieved_at=NOW, content_sha256=sha,
    )
    expected_ref = EvidenceRef(
        evidence_id=eid, source_type="disclosure", source_name="TestSource",
        source_url="https://example.invalid/other", period_end=None,
        published_at=None, available_at=None,
        retrieved_at=NOW, content_sha256=sha,
    )
    archive = _fake_archive(archived_ref, content)
    status = _archive_entry_status(
        archive, archive.build_manifest(), eid, expected_ref,
    )
    assert status is not None, "Changed source_url must be rejected"
