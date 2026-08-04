"""Tests for EvidenceArchive, report grading, and Quality Gate enhancements."""

from __future__ import annotations

import hashlib
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from jiuwenswarm.quant.reporting.models import (
    CompanyFactBundle,
    EvidenceRef,
    MetricFact,
    PortfolioSnapshot,
)
from jiuwenswarm.quant.reporting.providers.archive import EvidenceArchive
from jiuwenswarm.quant.reporting.providers.fixtures import (
    make_metric_fact,
)
from jiuwenswarm.quant.reporting.quality_gate import validate_submission
from jiuwenswarm.quant.reporting.report_grade import (
    GRADE_DESCRIPTIONS,
    ReportGrade,
    grade_bundle,
    grade_submission,
)
from jiuwenswarm.quant.reporting.submission_contract import SubmissionContract

UTC = timezone.utc


def _make_test_contract(codes: tuple = ("600000.SH",)) -> SubmissionContract:
    """Minimal provisional contract for quality gate tests."""
    codes = tuple(codes)
    return SubmissionContract(
        company_codes=codes,
        company_names={c: f"公司_{c}" for c in codes},
        sectors={c: "测试板块" for c in codes},
        sector_names=("测试板块",),
        source_file="test.xlsx",
        source_sha256="abc123",
        report_file_extension=".md",
        equity_weight_rule="equities_plus_cash_equals_one",
        allow_cash=None,
        report_quality_rule="unresolved",
        unresolved_questions=(),
        contract_status="PROVISIONAL",
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_bundle(
    ticker: str = "600000.SH",
    report_code: str = "600000",
    technical_facts: tuple = (),
    fundamental_facts: tuple = (),
    event_facts: tuple = (),
    risk_facts: tuple = (),
    data_provider_status: str = "partial",
) -> CompanyFactBundle:
    return CompanyFactBundle(
        ticker=ticker,
        report_code=report_code,
        name=f"公司{report_code}",
        sector="金融",
        as_of_time=datetime(2026, 7, 30, tzinfo=UTC),
        portfolio_weight=0.06,
        selected=True,
        weight_zero_reason="",
        technical_facts=technical_facts,
        fundamental_facts=fundamental_facts,
        event_facts=event_facts,
        risk_facts=risk_facts,
        agent_views=(),
        data_provider_status=data_provider_status,
    )


def _make_tech_fact() -> MetricFact:
    return make_metric_fact("momentum_20_z", value=0.72)


def _make_event_fact() -> MetricFact:
    return make_metric_fact("exchange_announcement", value="重大合同公告")


def _make_fundamental_fact() -> MetricFact:
    return make_metric_fact("pe_ratio", value=15.3, unit="倍")


def _make_ref(eid: str, h: str | None = None) -> EvidenceRef:
    return EvidenceRef(
        evidence_id=eid,
        source_type="disclosure",
        source_name="test",
        source_url=None,
        period_end=None,
        published_at=None,
        available_at=datetime(2026, 7, 30, tzinfo=UTC),
        retrieved_at=datetime(2026, 7, 30, tzinfo=UTC),
        content_sha256=h or ("f" * 64),
    )


# ---------------------------------------------------------------------------
# EvidenceArchive
# ---------------------------------------------------------------------------

class TestEvidenceArchive:
    def test_write_and_read_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            archive = EvidenceArchive(Path(tmp))
            content = json.dumps({"title": "测试公告"}).encode("utf-8")
            content_hash = hashlib.sha256(content).hexdigest()
            ref = EvidenceRef(
                evidence_id="ann-001",
                source_type="disclosure",
                source_name="test",
                source_url="https://example.com",
                period_end=None,
                published_at=datetime(2026, 7, 29, tzinfo=UTC),
                available_at=datetime(2026, 7, 29, tzinfo=UTC),
                retrieved_at=datetime(2026, 7, 30, tzinfo=UTC),
                content_sha256=content_hash,
            )
            archive.write("ann-001", content, ref)
            assert archive.exists("ann-001")
            read_back = archive.read("ann-001")
            assert read_back == content

    def test_write_rejects_hash_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            archive = EvidenceArchive(Path(tmp))
            ref = EvidenceRef(
                evidence_id="bad",
                source_type="disclosure",
                source_name="test",
                source_url=None,
                period_end=None,
                published_at=None,
                available_at=datetime(2026, 7, 30, tzinfo=UTC),
                retrieved_at=datetime(2026, 7, 30, tzinfo=UTC),
                content_sha256="a" * 64,
            )
            with pytest.raises(ValueError, match="hash mismatch"):
                archive.write("bad", b"actual content", ref)

    def test_read_nonexistent_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            archive = EvidenceArchive(Path(tmp))
            assert archive.read("nonexistent") is None

    def test_exists_false_for_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            archive = EvidenceArchive(Path(tmp))
            assert not archive.exists("missing")

    def test_build_manifest_only_includes_intact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            archive = EvidenceArchive(Path(tmp))
            content = b'{"x": 1}'
            import hashlib
            h = hashlib.sha256(content).hexdigest()
            ref = EvidenceRef(
                evidence_id="ev1",
                source_type="disclosure",
                source_name="test",
                source_url=None,
                period_end=None,
                published_at=None,
                available_at=datetime(2026, 7, 30, tzinfo=UTC),
                retrieved_at=datetime(2026, 7, 30, tzinfo=UTC),
                content_sha256=h,
            )
            archive.write("ev1", content, ref)
            manifest = archive.build_manifest()
            assert "ev1" in manifest
            assert manifest["ev1"].content_sha256 == h

    def test_list_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            archive = EvidenceArchive(Path(tmp))
            content = b"data"
            import hashlib
            h = hashlib.sha256(content).hexdigest()
            ref = EvidenceRef(
                evidence_id="ev-a",
                source_type="disclosure",
                source_name="test",
                source_url=None,
                period_end=None,
                published_at=None,
                available_at=datetime(2026, 7, 30, tzinfo=UTC),
                retrieved_at=datetime(2026, 7, 30, tzinfo=UTC),
                content_sha256=h,
            )
            archive.write("ev-a", content, ref)
            assert archive.list_ids() == ["ev-a"]

    def test_corrupted_file_not_in_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            archive = EvidenceArchive(Path(tmp))
            content = b"original"
            h = hashlib.sha256(content).hexdigest()
            ref = EvidenceRef(
                evidence_id="corrupt-me",
                source_type="disclosure",
                source_name="test",
                source_url=None,
                period_end=None,
                published_at=None,
                available_at=datetime(2026, 7, 30, tzinfo=UTC),
                retrieved_at=datetime(2026, 7, 30, tzinfo=UTC),
                content_sha256=h,
            )
            file_path = archive.write("corrupt-me", content, ref)
            # Corrupt the file
            file_path.write_bytes(b"tampered")
            assert not archive.exists("corrupt-me")
            assert "corrupt-me" not in archive.build_manifest()

    # -- Write-once semantics --

    def test_write_once_same_hash_is_idempotent(self) -> None:
        """Same (id, hash) → idempotent success, no error."""
        with tempfile.TemporaryDirectory() as tmp:
            archive = EvidenceArchive(Path(tmp))
            content = b"write-once-test"
            h = hashlib.sha256(content).hexdigest()
            ref = EvidenceRef(
                evidence_id="wo-1",
                source_type="disclosure",
                source_name="test",
                source_url=None,
                period_end=None,
                published_at=None,
                available_at=datetime(2026, 7, 30, tzinfo=UTC),
                retrieved_at=datetime(2026, 7, 30, tzinfo=UTC),
                content_sha256=h,
            )
            p1 = archive.write("wo-1", content, ref)
            p2 = archive.write("wo-1", content, ref)
            assert p1 == p2
            assert archive.exists("wo-1")

    def test_write_once_different_hash_is_rejected(self) -> None:
        """Same ID, different hash → ValueError."""
        with tempfile.TemporaryDirectory() as tmp:
            archive = EvidenceArchive(Path(tmp))
            content1 = b"first-write"
            h1 = hashlib.sha256(content1).hexdigest()
            ref1 = EvidenceRef(
                evidence_id="wo-2",
                source_type="disclosure",
                source_name="test",
                source_url=None,
                period_end=None,
                published_at=None,
                available_at=datetime(2026, 7, 30, tzinfo=UTC),
                retrieved_at=datetime(2026, 7, 30, tzinfo=UTC),
                content_sha256=h1,
            )
            archive.write("wo-2", content1, ref1)
            # Different content, different hash
            content2 = b"different-content"
            h2 = hashlib.sha256(content2).hexdigest()
            ref2 = EvidenceRef(
                evidence_id="wo-2",
                source_type="disclosure",
                source_name="test",
                source_url=None,
                period_end=None,
                published_at=None,
                available_at=datetime(2026, 7, 30, tzinfo=UTC),
                retrieved_at=datetime(2026, 7, 30, tzinfo=UTC),
                content_sha256=h2,
            )
            with pytest.raises(ValueError, match="already archived"):
                archive.write("wo-2", content2, ref2)
            # Original content still intact
            assert archive.read("wo-2") == content1

    # -- Path traversal / validation --

    def test_rejects_path_traversal_dot_dot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            archive = EvidenceArchive(Path(tmp))
            with pytest.raises(ValueError, match="Invalid evidence_id"):
                archive.write("../etc-passwd", b"x", _make_ref("bad"))

    def test_rejects_path_traversal_slash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            archive = EvidenceArchive(Path(tmp))
            with pytest.raises(ValueError, match="Invalid evidence_id"):
                archive.write("a/b", b"x", _make_ref("bad"))

    def test_rejects_path_traversal_backslash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            archive = EvidenceArchive(Path(tmp))
            with pytest.raises(ValueError, match="Invalid evidence_id"):
                archive.write("a\\b", b"x", _make_ref("bad"))

    def test_rejects_empty_evidence_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            archive = EvidenceArchive(Path(tmp))
            with pytest.raises(ValueError, match="Invalid evidence_id"):
                archive.write("", b"x", _make_ref("bad"))

    def test_rejects_overly_long_evidence_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            archive = EvidenceArchive(Path(tmp))
            long_id = "a" * 300
            with pytest.raises(ValueError, match="too long"):
                archive.write(long_id, b"x", _make_ref(long_id))


# ---------------------------------------------------------------------------
# Report grading
# ---------------------------------------------------------------------------

class TestReportGrade:
    def test_technical_only(self) -> None:
        bundle = _make_bundle(technical_facts=(_make_tech_fact(),))
        assert grade_bundle(bundle) == ReportGrade.TECHNICAL_PASSED

    def test_empty_bundle_is_technical(self) -> None:
        bundle = _make_bundle()
        assert grade_bundle(bundle) == ReportGrade.TECHNICAL_PASSED

    def test_tech_plus_disclosure_is_partial(self) -> None:
        bundle = _make_bundle(
            technical_facts=(_make_tech_fact(),),
            event_facts=(_make_event_fact(),),
        )
        assert grade_bundle(bundle) == ReportGrade.FINANCIAL_PARTIAL

    def test_tech_plus_fundamental_is_partial(self) -> None:
        bundle = _make_bundle(
            technical_facts=(_make_tech_fact(),),
            fundamental_facts=(_make_fundamental_fact(),),
        )
        assert grade_bundle(bundle) == ReportGrade.FINANCIAL_PARTIAL

    def test_full_report_requires_tech_disclosure_and_fundamental(self) -> None:
        bundle = _make_bundle(
            technical_facts=(_make_tech_fact(),),
            event_facts=(_make_event_fact(),),
            fundamental_facts=(_make_fundamental_fact(),),
        )
        assert grade_bundle(bundle) == ReportGrade.FULL_REPORT_PASSED

    def test_full_report_tech_disclosure_risk(self) -> None:
        bundle = _make_bundle(
            technical_facts=(_make_tech_fact(),),
            event_facts=(_make_event_fact(),),
            risk_facts=(make_metric_fact("vol_warning", value="高波动"),),
        )
        assert grade_bundle(bundle) == ReportGrade.FULL_REPORT_PASSED

    def test_disclosure_only_no_tech_is_technical(self) -> None:
        """Without technical facts, can't even reach TECHNICAL_PASSED properly."""
        bundle = _make_bundle(event_facts=(_make_event_fact(),))
        assert grade_bundle(bundle) == ReportGrade.TECHNICAL_PASSED

    def test_grade_submission_overall_is_min(self) -> None:
        full = _make_bundle(
            ticker="600000.SH", report_code="600000",
            technical_facts=(_make_tech_fact(),),
            event_facts=(_make_event_fact(),),
            fundamental_facts=(_make_fundamental_fact(),),
        )
        tech = _make_bundle(
            ticker="000001.SZ", report_code="000001",
            technical_facts=(_make_tech_fact(),),
        )
        result = grade_submission({"600000.SH": full, "000001.SZ": tech})
        assert result.grade == ReportGrade.TECHNICAL_PASSED
        assert result.n_companies == 2
        assert result.n_disclosure == 1
        assert result.per_company["600000.SH"] == ReportGrade.FULL_REPORT_PASSED
        assert result.per_company["000001.SZ"] == ReportGrade.TECHNICAL_PASSED

    def test_grade_submission_all_full(self) -> None:
        b1 = _make_bundle(
            ticker="600000.SH", report_code="600000",
            technical_facts=(_make_tech_fact(),),
            event_facts=(_make_event_fact(),),
            fundamental_facts=(_make_fundamental_fact(),),
        )
        b2 = _make_bundle(
            ticker="000001.SZ", report_code="000001",
            technical_facts=(_make_tech_fact(),),
            event_facts=(_make_event_fact(),),
            risk_facts=(make_metric_fact("risk", value=1),),
        )
        result = grade_submission({"600000.SH": b1, "000001.SZ": b2})
        assert result.grade == ReportGrade.FULL_REPORT_PASSED

    def test_grade_submission_empty(self) -> None:
        result = grade_submission({})
        assert result.n_companies == 0
        assert result.grade == ReportGrade.TECHNICAL_PASSED

    def test_grade_descriptions_exist_for_all_levels(self) -> None:
        for grade in ReportGrade:
            assert grade in GRADE_DESCRIPTIONS
            assert len(GRADE_DESCRIPTIONS[grade]) > 0


# ---------------------------------------------------------------------------
# Quality gate — archive + grading integration
# ---------------------------------------------------------------------------

class TestQualityGateEnhancements:
    def test_archive_unresolved_is_blocker(self) -> None:
        """Evidence referenced by a fact but not in archive → blocker."""
        with tempfile.TemporaryDirectory() as tmp:
            archive = EvidenceArchive(Path(tmp))
            # Don't write anything to archive — evidence_id will not resolve
            fact = MetricFact(
                name="momentum_20_z", value=0.72, unit=None,
                status="available", evidence_ids=("ev-missing",),
            )
            bundle = _make_bundle(technical_facts=(fact,))
            ref = EvidenceRef(
                evidence_id="ev-missing",
                source_type="market_data",
                source_name="test",
                source_url=None,
                period_end=None,
                published_at=None,
                available_at=datetime(2026, 7, 29, tzinfo=UTC),
                retrieved_at=datetime(2026, 7, 29, tzinfo=UTC),
                content_sha256="f" * 64,
            )
            contract = _make_test_contract()
            portfolio = PortfolioSnapshot(
                as_of_time=datetime(2026, 7, 30, tzinfo=UTC),
                holdings={"600000.SH": 0.06},
                cash=0.94,
                total_equity=0.06,
                n_selected=1,
                n_sectors_represented=1,
                strategy_id="test",
                contract_hash=contract.config_hash(),
            )
            result = validate_submission(
                contract, portfolio, {"600000.SH": bundle},
                {"600000"}, datetime(2026, 7, 30, tzinfo=UTC),
                evidence_manifest={"ev-missing": ref},
                archive=archive,
            )
            # Archive unresolved → must be a BLOCKER, not just warning
            assert not result.passed
            assert any("not found in archive" in b for b in result.blockers)

    def test_archive_check_passes_when_all_ids_resolve(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            archive = EvidenceArchive(Path(tmp))
            content = b"evidence-data"
            import hashlib
            h = hashlib.sha256(content).hexdigest()
            ref = EvidenceRef(
                evidence_id="ev-tech-1",
                source_type="market_data",
                source_name="test",
                source_url=None,
                period_end=None,
                published_at=None,
                available_at=datetime(2026, 7, 29, tzinfo=UTC),
                retrieved_at=datetime(2026, 7, 29, tzinfo=UTC),
                content_sha256=h,
            )
            archive.write("ev-tech-1", content, ref)

            fact = MetricFact(
                name="momentum_20_z", value=0.72, unit=None,
                status="available", evidence_ids=("ev-tech-1",),
            )
            bundle = _make_bundle(technical_facts=(fact,))

            contract = _make_test_contract()
            portfolio = PortfolioSnapshot(
                as_of_time=datetime(2026, 7, 30, tzinfo=UTC),
                holdings={"600000.SH": 0.06},
                cash=0.94,
                total_equity=0.06,
                n_selected=1,
                n_sectors_represented=1,
                strategy_id="test",
                contract_hash=contract.config_hash(),
            )

            result = validate_submission(
                contract, portfolio, {"600000.SH": bundle},
                {"600000"}, datetime(2026, 7, 30, tzinfo=UTC),
                evidence_manifest={"ev-tech-1": ref},
                archive=archive,
            )
            assert result.passed  # no blockers from archive

    def test_grading_adds_warning_when_technical_only(self) -> None:
        bundle = _make_bundle(technical_facts=(_make_tech_fact(),))
        contract = _make_test_contract()
        portfolio = PortfolioSnapshot(
            as_of_time=datetime(2026, 7, 30, tzinfo=UTC),
            holdings={"600000.SH": 0.06},
            cash=0.94,
            total_equity=0.06,
            n_selected=1,
            n_sectors_represented=1,
            strategy_id="test",
            contract_hash=contract.config_hash(),
        )
        result = validate_submission(
            contract, portfolio, {"600000.SH": bundle},
            {"600000"}, datetime(2026, 7, 30, tzinfo=UTC),
        )
        assert result.passed  # TECHNICAL_PASSED is not a blocker
        has_grade_warning = any(
            "TECHNICAL_PASSED" in w for w in result.warnings
        )
        assert has_grade_warning

    def test_metrics_include_grade_breakdown(self) -> None:
        bundle = _make_bundle(
            technical_facts=(_make_tech_fact(),),
            event_facts=(_make_event_fact(),),
        )
        contract = _make_test_contract()
        portfolio = PortfolioSnapshot(
            as_of_time=datetime(2026, 7, 30, tzinfo=UTC),
            holdings={"600000.SH": 0.06},
            cash=0.94,
            total_equity=0.06,
            n_selected=1,
            n_sectors_represented=1,
            strategy_id="test",
            contract_hash=contract.config_hash(),
        )
        result = validate_submission(
            contract, portfolio, {"600000.SH": bundle},
            {"600000"}, datetime(2026, 7, 30, tzinfo=UTC),
        )
        assert result.metrics["report_grade_technical"] == 1
        assert result.metrics["report_grade_disclosure"] == 1
        assert result.metrics["report_grade_fundamental"] == 0
        assert result.metrics["overall_grade"] == "FINANCIAL_PARTIAL"
