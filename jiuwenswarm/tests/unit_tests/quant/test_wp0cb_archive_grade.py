"""Tests for EvidenceArchive, report grading, and Quality Gate enhancements."""

from __future__ import annotations

import hashlib
import json
import tempfile
from dataclasses import replace
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from jiuwenswarm.quant.reporting.models import (
    CompanyFactBundle,
    EvidenceRef,
    FundamentalLineItem,
    FundamentalReportCore,
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
    has_qualified_fundamental,
)
from jiuwenswarm.quant.reporting.report_service import ReportService
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
    as_of_time: datetime = datetime(2026, 7, 30, tzinfo=UTC),
    qualified_fundamental_reports: tuple = (),
) -> CompanyFactBundle:
    return CompanyFactBundle(
        ticker=ticker,
        report_code=report_code,
        name=f"公司{report_code}",
        sector="金融",
        as_of_time=as_of_time,
        portfolio_weight=0.06,
        selected=True,
        weight_zero_reason="",
        technical_facts=technical_facts,
        fundamental_facts=fundamental_facts,
        event_facts=event_facts,
        risk_facts=risk_facts,
        agent_views=(),
        data_provider_status=data_provider_status,
        qualified_fundamental_reports=qualified_fundamental_reports,
    )


def _make_tech_fact() -> MetricFact:
    return make_metric_fact("momentum_20_z", value=0.72)


def _make_event_fact() -> MetricFact:
    return make_metric_fact("exchange_announcement", value="重大合同公告")


def _make_fundamental_fact() -> MetricFact:
    return make_metric_fact("pe_ratio", value=15.3, unit="倍")


_CORE_STATEMENTS = {
    "operating_revenue": "income_statement",
    "net_profit_attributable_to_parent": "income_statement",
    "total_assets": "balance_sheet",
    "equity_attributable_to_parent": "balance_sheet",
}


def _make_line_item(
    line_item_id: str,
    *,
    value: float | int | None = 100.0,
    status: str = "available",
    statement: str | None = None,
    raw_unit: str | None = "CNY",
    currency: str | None = "CNY",
    normalized_unit: str | None = "CNY",
    formula: str | None = "identity",
) -> FundamentalLineItem:
    return FundamentalLineItem(
        statement=statement or _CORE_STATEMENTS[line_item_id],
        line_item_id=line_item_id,
        status=status,
        raw_value=value,
        raw_unit=raw_unit,
        currency=currency,
        normalized_value=value,
        normalized_unit=normalized_unit,
        normalization_formula=formula,
    )


def _make_fundamental_core(
    *,
    ticker: str = "600000.SH",
    version: str = "filing-v1",
    evidence_id: str = "fundamental-v1",
    published_at: datetime = datetime(2026, 4, 1, 18, 0, tzinfo=UTC),
    available_at: datetime = datetime(2026, 4, 1, 18, 0, tzinfo=UTC),
    line_items: tuple[FundamentalLineItem, ...] | None = None,
    is_correction: bool = False,
    superseded_version: str | None = None,
    superseded_evidence: str | None = None,
    evidence_sha256: str | None = None,
) -> FundamentalReportCore:
    if line_items is None:
        line_items = tuple(_make_line_item(item) for item in _CORE_STATEMENTS)
    return FundamentalReportCore(
        ticker=ticker,
        issuer_id=f"issuer-{ticker}",
        report_period_start=date(2025, 1, 1),
        report_period_end=date(2025, 12, 31),
        report_type="annual",
        statement_scope="consolidated",
        audit_status="audited",
        currency="CNY",
        published_at=published_at,
        available_at=available_at,
        source_authority="test-first-party",
        source_version_id=version,
        evidence_id=evidence_id,
        evidence_sha256=evidence_sha256 or (
            ("a" if version == "filing-v1" else "b") * 64
        ),
        is_correction=is_correction,
        superseded_source_version_id=superseded_version,
        superseded_evidence_id=superseded_evidence,
        line_items=line_items,
    )


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

    def test_idempotent_write_rejects_missing_committed_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            archive = EvidenceArchive(Path(tmp))
            content = b"missing-idempotent-bytes"
            ref = EvidenceRef(
                evidence_id="wo-missing",
                source_type="disclosure",
                source_name="test",
                source_url=None,
                period_end=None,
                published_at=None,
                available_at=datetime(2026, 7, 30, tzinfo=UTC),
                retrieved_at=datetime(2026, 7, 30, tzinfo=UTC),
                content_sha256=hashlib.sha256(content).hexdigest(),
            )
            path = archive.write("wo-missing", content, ref)
            path.unlink()
            with pytest.raises(ValueError, match="missing or corrupted"):
                archive.write("wo-missing", content, ref)

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

    def test_generic_fundamental_fact_cannot_raise_grade(self) -> None:
        bundle = _make_bundle(
            technical_facts=(_make_tech_fact(),),
            fundamental_facts=(_make_fundamental_fact(),),
        )
        assert grade_bundle(bundle) == ReportGrade.TECHNICAL_PASSED

    def test_full_report_requires_tech_disclosure_and_fundamental(self) -> None:
        bundle = _make_bundle(
            technical_facts=(_make_tech_fact(),),
            event_facts=(_make_event_fact(),),
            fundamental_facts=(_make_fundamental_fact(),),
            qualified_fundamental_reports=(_make_fundamental_core(),),
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
            qualified_fundamental_reports=(_make_fundamental_core(),),
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
            qualified_fundamental_reports=(_make_fundamental_core(),),
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


class TestFundamentalQualification:
    def test_complete_coherent_core_qualifies_and_explicit_zero_is_not_missing(self) -> None:
        zero_profit = _make_line_item(
            "net_profit_attributable_to_parent", value=0,
        )
        core = _make_fundamental_core(line_items=(
            _make_line_item("operating_revenue"),
            zero_profit,
            _make_line_item("total_assets"),
            _make_line_item("equity_attributable_to_parent"),
        ))
        bundle = _make_bundle(qualified_fundamental_reports=(core,))
        assert has_qualified_fundamental(bundle)

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("ticker", "000001.SZ"),
            ("issuer_id", ""),
            ("issuer_id", None),
            ("report_type", "quarterly"),
            ("statement_scope", "parent"),
            ("audit_status", "unaudited"),
            ("currency", "USD"),
            ("evidence_sha256", "not-a-hash"),
        ],
    )
    def test_invalid_report_identity_fails_closed(self, field: str, value: object) -> None:
        core = replace(_make_fundamental_core(), **{field: value})
        assert not has_qualified_fundamental(
            _make_bundle(qualified_fundamental_reports=(core,))
        )

    def test_future_or_naive_availability_fails_closed(self) -> None:
        future = _make_fundamental_core(
            published_at=datetime(2026, 8, 1, tzinfo=UTC),
            available_at=datetime(2026, 8, 1, tzinfo=UTC),
        )
        naive = replace(
            _make_fundamental_core(),
            available_at=datetime(2026, 4, 1, 18, 0),
        )
        assert not has_qualified_fundamental(
            _make_bundle(qualified_fundamental_reports=(future,))
        )
        assert not has_qualified_fundamental(
            _make_bundle(qualified_fundamental_reports=(naive,))
        )

    @pytest.mark.parametrize(
        "bad_item",
        [
            _make_line_item("operating_revenue", value=None),
            _make_line_item("operating_revenue", status="unavailable"),
            _make_line_item("operating_revenue", statement="balance_sheet"),
            _make_line_item(
                "operating_revenue", raw_unit="CNY_THOUSAND", formula="identity",
            ),
            _make_line_item("operating_revenue", currency="USD"),
        ],
    )
    def test_invalid_line_item_fails_closed(self, bad_item: FundamentalLineItem) -> None:
        items = tuple(
            bad_item if item == "operating_revenue" else _make_line_item(item)
            for item in _CORE_STATEMENTS
        )
        core = _make_fundamental_core(line_items=items)
        assert not has_qualified_fundamental(
            _make_bundle(qualified_fundamental_reports=(core,))
        )

    def test_line_item_type_confusion_fails_closed_without_exception(self) -> None:
        bad_items = (
            replace(
                _make_line_item("operating_revenue"),
                line_item_id=None,
            ),
            replace(
                _make_line_item("operating_revenue"),
                line_item_id=["operating_revenue"],
            ),
            MetricFact(
                name="operating_revenue", value=100.0, unit="CNY",
                status="available", evidence_ids=(),
            ),
        )
        for bad_item in bad_items:
            core = _make_fundamental_core(line_items=(
                bad_item,
                _make_line_item("net_profit_attributable_to_parent"),
                _make_line_item("total_assets"),
                _make_line_item("equity_attributable_to_parent"),
            ))
            assert not has_qualified_fundamental(
                _make_bundle(qualified_fundamental_reports=(core,))
            )

    @pytest.mark.parametrize("bad_reports", [[], None, 7])
    def test_top_level_report_container_must_be_immutable_tuple(
        self, bad_reports: object,
    ) -> None:
        bundle = replace(
            _make_bundle(),
            qualified_fundamental_reports=bad_reports,
        )
        assert not has_qualified_fundamental(bundle)
        assert grade_bundle(bundle) == ReportGrade.TECHNICAL_PASSED

    def test_incomplete_duplicate_or_cross_core_fragments_do_not_combine(self) -> None:
        items = tuple(_make_line_item(item) for item in _CORE_STATEMENTS)
        incomplete = _make_fundamental_core(line_items=items[:-1])
        duplicate = _make_fundamental_core(line_items=items + (items[0],))
        fragment_a = _make_fundamental_core(line_items=items[:2])
        fragment_b = replace(
            _make_fundamental_core(line_items=items[2:]),
            report_period_start=date(2024, 1, 1),
            report_period_end=date(2024, 12, 31),
        )
        for reports in ((incomplete,), (duplicate,), (fragment_a, fragment_b)):
            assert not has_qualified_fundamental(
                _make_bundle(qualified_fundamental_reports=reports)
            )

    def test_correction_cutoff_selects_unique_terminal_version(self) -> None:
        original = _make_fundamental_core()
        correction = _make_fundamental_core(
            version="filing-v2",
            evidence_id="fundamental-v2",
            published_at=datetime(2026, 6, 1, 18, 0, tzinfo=UTC),
            available_at=datetime(2026, 6, 1, 18, 0, tzinfo=UTC),
            is_correction=True,
            superseded_version="filing-v1",
            superseded_evidence="fundamental-v1",
        )
        before = _make_bundle(
            as_of_time=datetime(2026, 5, 1, tzinfo=UTC),
            qualified_fundamental_reports=(original, correction),
        )
        after = _make_bundle(
            qualified_fundamental_reports=(original, correction),
        )
        assert has_qualified_fundamental(before)
        assert has_qualified_fundamental(after)

    def test_invalid_available_correction_blocks_stale_predecessor(self) -> None:
        original = _make_fundamental_core()
        correction = _make_fundamental_core(
            version="filing-v2",
            evidence_id="fundamental-v2",
            published_at=datetime(2026, 6, 1, 18, 0, tzinfo=UTC),
            available_at=datetime(2026, 6, 1, 18, 0, tzinfo=UTC),
            line_items=tuple(
                _make_line_item(item) for item in tuple(_CORE_STATEMENTS)[:-1]
            ),
            is_correction=True,
            superseded_version="filing-v1",
            superseded_evidence="fundamental-v1",
        )
        bundle = _make_bundle(
            qualified_fundamental_reports=(original, correction),
        )
        assert not has_qualified_fundamental(bundle)

    def test_missing_predecessor_fork_and_cycle_fail_closed(self) -> None:
        original = _make_fundamental_core()
        correction = _make_fundamental_core(
            version="filing-v2",
            evidence_id="fundamental-v2",
            published_at=datetime(2026, 6, 1, 18, 0, tzinfo=UTC),
            available_at=datetime(2026, 6, 1, 18, 0, tzinfo=UTC),
            is_correction=True,
            superseded_version="filing-v1",
            superseded_evidence="fundamental-v1",
        )
        fork = replace(
            correction,
            source_version_id="filing-v3",
            evidence_id="fundamental-v3",
            evidence_sha256="c" * 64,
        )
        cycle_original = replace(
            original,
            is_correction=True,
            superseded_source_version_id="filing-v2",
            superseded_evidence_id="fundamental-v2",
        )
        assert not has_qualified_fundamental(
            _make_bundle(qualified_fundamental_reports=(correction,))
        )
        assert not has_qualified_fundamental(
            _make_bundle(qualified_fundamental_reports=(original, correction, fork))
        )
        assert not has_qualified_fundamental(
            _make_bundle(qualified_fundamental_reports=(cycle_original, correction))
        )

    def test_correction_cannot_escape_period_issuer_or_authority_group(self) -> None:
        original = _make_fundamental_core()
        correction = _make_fundamental_core(
            version="filing-v2",
            evidence_id="fundamental-v2",
            published_at=datetime(2026, 6, 1, 18, 0, tzinfo=UTC),
            available_at=datetime(2026, 6, 1, 18, 0, tzinfo=UTC),
            is_correction=True,
            superseded_version="filing-v1",
            superseded_evidence="fundamental-v1",
        )
        escaped = (
            replace(
                correction,
                report_period_start=date(2024, 1, 1),
                report_period_end=date(2024, 12, 31),
            ),
            replace(correction, issuer_id="different-issuer"),
            replace(correction, source_authority="different-authority"),
        )
        for bad_correction in escaped:
            assert not has_qualified_fundamental(_make_bundle(
                qualified_fundamental_reports=(original, bad_correction),
            ))

    def test_correction_must_be_published_and_available_after_predecessor(self) -> None:
        original = _make_fundamental_core()
        correction = _make_fundamental_core(
            version="filing-v2",
            evidence_id="fundamental-v2",
            published_at=original.published_at,
            available_at=original.available_at,
            is_correction=True,
            superseded_version="filing-v1",
            superseded_evidence="fundamental-v1",
        )
        assert not has_qualified_fundamental(_make_bundle(
            qualified_fundamental_reports=(original, correction),
        ))

    def test_report_service_forwards_typed_cores_without_populating_current_callers(self) -> None:
        core = _make_fundamental_core()
        service = ReportService(_make_test_contract())
        bundle = service.build_company_bundle(
            ticker="600000.SH",
            name="公司600000",
            sector="金融",
            as_of_time=datetime(2026, 7, 30, tzinfo=UTC),
            portfolio_weight=0.06,
            selected=True,
            qualified_fundamental_reports=(core,),
        )
        assert bundle.qualified_fundamental_reports == (core,)
        empty = service.build_company_bundle(
            ticker="600000.SH",
            name="公司600000",
            sector="金融",
            as_of_time=datetime(2026, 7, 30, tzinfo=UTC),
            portfolio_weight=0.06,
            selected=True,
        )
        assert empty.qualified_fundamental_reports == ()


# ---------------------------------------------------------------------------
# Quality gate — archive + grading integration
# ---------------------------------------------------------------------------

class TestQualityGateEnhancements:
    @staticmethod
    def _portfolio(contract: SubmissionContract) -> PortfolioSnapshot:
        return PortfolioSnapshot(
            as_of_time=datetime(2026, 7, 30, tzinfo=UTC),
            holdings={"600000.SH": 0.06},
            cash=0.94,
            total_equity=0.06,
            n_selected=1,
            n_sectors_represented=1,
            strategy_id="test",
            contract_hash=contract.config_hash(),
        )

    def test_qualified_core_requires_manifest_and_archive(self) -> None:
        core = _make_fundamental_core()
        bundle = _make_bundle(
            technical_facts=(MetricFact(
                name="trend", value="positive", unit=None,
                status="available", evidence_ids=(),
            ),),
            qualified_fundamental_reports=(core,),
        )
        contract = _make_test_contract()
        result = validate_submission(
            contract, self._portfolio(contract), {"600000.SH": bundle},
            {"600000"}, datetime(2026, 7, 30, tzinfo=UTC),
        )
        assert not result.passed
        assert any("require an evidence_manifest" in b for b in result.blockers)
        assert any("require an EvidenceArchive" in b for b in result.blockers)

    def test_qualified_core_manifest_mismatch_is_blocker(self) -> None:
        core = _make_fundamental_core()
        ref = EvidenceRef(
            evidence_id=core.evidence_id,
            source_type="disclosure",
            source_name="test",
            source_url=None,
            period_end=datetime(2025, 12, 31, tzinfo=UTC),
            published_at=core.published_at,
            available_at=core.available_at,
            retrieved_at=core.available_at,
            content_sha256="f" * 64,
        )
        bundle = _make_bundle(
            technical_facts=(MetricFact(
                name="trend", value="positive", unit=None,
                status="available", evidence_ids=(),
            ),),
            qualified_fundamental_reports=(core,),
        )
        contract = _make_test_contract()
        with tempfile.TemporaryDirectory() as tmp:
            result = validate_submission(
                contract, self._portfolio(contract), {"600000.SH": bundle},
                {"600000"}, datetime(2026, 7, 30, tzinfo=UTC),
                evidence_manifest={core.evidence_id: ref},
                archive=EvidenceArchive(Path(tmp)),
            )
        assert not result.passed
        assert any(
            "core hash does not match evidence manifest" in b
            for b in result.blockers
        )
        assert any(
            "source_type must be financial_statement" in b
            for b in result.blockers
        )

    @pytest.mark.parametrize("mismatch", ["hash", "source"])
    def test_supplied_manifest_must_match_archive_internal_entry(
        self, mismatch: str,
    ) -> None:
        archived_content = b'{"archive":"actual"}'
        supplied_content = (
            b'{"manifest":"different"}'
            if mismatch == "hash"
            else archived_content
        )
        archived_hash = hashlib.sha256(archived_content).hexdigest()
        supplied_hash = hashlib.sha256(supplied_content).hexdigest()
        core = _make_fundamental_core(evidence_sha256=supplied_hash)
        archived_ref = EvidenceRef(
            evidence_id=core.evidence_id,
            source_type=(
                "disclosure" if mismatch == "source" else "financial_statement"
            ),
            source_name=(
                "different-authority"
                if mismatch == "source"
                else core.source_authority
            ),
            source_url="https://example.com/archive-copy.pdf",
            period_end=datetime(2025, 12, 31, tzinfo=UTC),
            published_at=core.published_at,
            available_at=core.available_at,
            retrieved_at=datetime(2026, 4, 2, tzinfo=UTC),
            content_sha256=archived_hash,
        )
        supplied_ref = replace(
            archived_ref,
            source_type="financial_statement",
            source_name=core.source_authority,
            source_url="https://example.com/supplied-copy.pdf",
            content_sha256=supplied_hash,
        )
        bundle = _make_bundle(
            technical_facts=(MetricFact(
                name="trend", value="positive", unit=None,
                status="available", evidence_ids=(),
            ),),
            event_facts=(MetricFact(
                name="exchange_announcement", value="重大合同公告", unit=None,
                status="available", evidence_ids=(),
            ),),
            qualified_fundamental_reports=(core,),
        )
        contract = _make_test_contract()
        with tempfile.TemporaryDirectory() as tmp:
            archive = EvidenceArchive(Path(tmp))
            archive.write(core.evidence_id, archived_content, archived_ref)
            result = validate_submission(
                contract, self._portfolio(contract), {"600000.SH": bundle},
                {"600000"}, datetime(2026, 7, 30, tzinfo=UTC),
                evidence_manifest={core.evidence_id: supplied_ref},
                archive=archive,
            )
        assert not result.passed
        assert result.metrics["overall_grade"] == "FULL_REPORT_PASSED"
        assert any(
            "Archived evidence does not match the supplied manifest" in blocker
            for blocker in result.blockers
        )

    def test_embedded_evidence_id_must_match_manifest_and_archive_key(self) -> None:
        content = b'{"annual_report":"key-binding"}'
        content_hash = hashlib.sha256(content).hexdigest()
        core = _make_fundamental_core(evidence_sha256=content_hash)
        ref = EvidenceRef(
            evidence_id="embedded-different-id",
            source_type="financial_statement",
            source_name=core.source_authority,
            source_url="https://example.com/key-binding.pdf",
            period_end=datetime(2025, 12, 31, tzinfo=UTC),
            published_at=core.published_at,
            available_at=core.available_at,
            retrieved_at=datetime(2026, 4, 2, tzinfo=UTC),
            content_sha256=content_hash,
        )
        bundle = _make_bundle(
            technical_facts=(MetricFact(
                name="trend", value="positive", unit=None,
                status="available", evidence_ids=(),
            ),),
            qualified_fundamental_reports=(core,),
        )
        contract = _make_test_contract()
        with tempfile.TemporaryDirectory() as tmp:
            archive = EvidenceArchive(Path(tmp))
            archive.write(core.evidence_id, content, ref)
            result = validate_submission(
                contract, self._portfolio(contract), {"600000.SH": bundle},
                {"600000"}, datetime(2026, 7, 30, tzinfo=UTC),
                evidence_manifest={core.evidence_id: ref},
                archive=archive,
            )
        assert not result.passed
        assert any(
            "embedded EvidenceRef id does not match manifest key" in blocker
            for blocker in result.blockers
        )

    def test_malformed_core_is_quality_blocker_not_exception(self) -> None:
        malformed = _make_fundamental_core(line_items=(
            MetricFact(
                name="operating_revenue", value=100.0, unit="CNY",
                status="available", evidence_ids=(),
            ),
            _make_line_item("net_profit_attributable_to_parent"),
            _make_line_item("total_assets"),
            _make_line_item("equity_attributable_to_parent"),
        ))
        bundle = _make_bundle(
            technical_facts=(MetricFact(
                name="trend", value="positive", unit=None,
                status="available", evidence_ids=(),
            ),),
            qualified_fundamental_reports=(malformed,),
        )
        contract = _make_test_contract()
        result = validate_submission(
            contract, self._portfolio(contract), {"600000.SH": bundle},
            {"600000"}, datetime(2026, 7, 30, tzinfo=UTC),
        )
        assert not result.passed
        assert any(
            "core is not individually qualified" in blocker
            for blocker in result.blockers
        )

    def test_qualified_core_with_bound_archived_evidence_can_raise_grade(self) -> None:
        content = b'{"annual_report":"qualified-core"}'
        content_hash = hashlib.sha256(content).hexdigest()
        core = _make_fundamental_core(evidence_sha256=content_hash)
        ref = EvidenceRef(
            evidence_id=core.evidence_id,
            source_type="financial_statement",
            source_name="test-first-party",
            source_url="https://example.com/annual-report.pdf",
            period_end=datetime(2025, 12, 31, tzinfo=UTC),
            published_at=core.published_at,
            available_at=core.available_at,
            retrieved_at=datetime(2026, 4, 2, tzinfo=UTC),
            content_sha256=content_hash,
        )
        bundle = _make_bundle(
            technical_facts=(MetricFact(
                name="trend", value="positive", unit=None,
                status="available", evidence_ids=(),
            ),),
            event_facts=(MetricFact(
                name="exchange_announcement", value="重大合同公告", unit=None,
                status="available", evidence_ids=(),
            ),),
            qualified_fundamental_reports=(core,),
        )
        contract = _make_test_contract()
        with tempfile.TemporaryDirectory() as tmp:
            archive = EvidenceArchive(Path(tmp))
            archive.write(core.evidence_id, content, ref)
            result = validate_submission(
                contract, self._portfolio(contract), {"600000.SH": bundle},
                {"600000"}, datetime(2026, 7, 30, tzinfo=UTC),
                evidence_manifest={core.evidence_id: ref},
                archive=archive,
            )
        assert result.passed
        assert result.metrics["report_grade_fundamental"] == 1
        assert result.metrics["overall_grade"] == "FULL_REPORT_PASSED"
        assert result.metrics["qualified_fundamental_evidence_ids"] == 1

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

    def test_archive_manifest_is_built_once_for_many_evidence_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            archive = EvidenceArchive(Path(tmp))
            refs: dict[str, EvidenceRef] = {}
            facts: list[MetricFact] = []
            for index in range(12):
                evidence_id = f"ev-scale-{index}"
                content = f"evidence-{index}".encode()
                ref = EvidenceRef(
                    evidence_id=evidence_id,
                    source_type="market_data",
                    source_name="test",
                    source_url=None,
                    period_end=None,
                    published_at=None,
                    available_at=datetime(2026, 7, 29, tzinfo=UTC),
                    retrieved_at=datetime(2026, 7, 29, tzinfo=UTC),
                    content_sha256=hashlib.sha256(content).hexdigest(),
                )
                archive.write(evidence_id, content, ref)
                refs[evidence_id] = ref
                facts.append(MetricFact(
                    name=f"metric-{index}", value=float(index), unit=None,
                    status="available", evidence_ids=(evidence_id,),
                ))

            original_build_manifest = archive.build_manifest
            original_read = archive.read
            calls = {"build_manifest": 0, "read": 0}

            def counted_build_manifest() -> dict[str, EvidenceRef]:
                calls["build_manifest"] += 1
                return original_build_manifest()

            def counted_read(evidence_id: str) -> bytes | None:
                calls["read"] += 1
                return original_read(evidence_id)

            archive.build_manifest = counted_build_manifest
            archive.read = counted_read
            bundle = _make_bundle(technical_facts=tuple(facts))
            contract = _make_test_contract()
            result = validate_submission(
                contract, self._portfolio(contract), {"600000.SH": bundle},
                {"600000"}, datetime(2026, 7, 30, tzinfo=UTC),
                evidence_manifest=refs,
                archive=archive,
            )
            assert result.passed
            assert calls["build_manifest"] == 1
            assert calls["read"] <= 24

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
