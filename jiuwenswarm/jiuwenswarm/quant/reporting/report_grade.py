"""Report grading: classify candidate packages by evidence coverage.

Three tiers defined in DEVELOPMENT_PLAN.md §6 (WP0-C):

* TECHNICAL_PASSED — only market/technical evidence; current baseline.
* FINANCIAL_PARTIAL — market evidence + at least one non-market evidence
  category.
* FULL_REPORT_PASSED — every company has facts from market, disclosure,
  AND at least one of {qualified fundamental, news, risk} providers.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import Dict, Mapping, Sequence

from jiuwenswarm.quant.reporting.models import (
    CompanyFactBundle,
    FundamentalLineItem,
    FundamentalReportCore,
)


_REQUIRED_FUNDAMENTAL_LINES: Mapping[str, str] = {
    "operating_revenue": "income_statement",
    "net_profit_attributable_to_parent": "income_statement",
    "total_assets": "balance_sheet",
    "equity_attributable_to_parent": "balance_sheet",
}

_NORMALIZATION_SCALES: Mapping[tuple[str, str], tuple[str, float]] = {
    ("CNY", "CNY"): ("identity", 1.0),
    ("CNY_THOUSAND", "CNY"): ("raw_value * 1000", 1_000.0),
    ("CNY_TEN_THOUSAND", "CNY"): ("raw_value * 10000", 10_000.0),
    ("CNY_MILLION", "CNY"): ("raw_value * 1000000", 1_000_000.0),
    ("CNY_HUNDRED_MILLION", "CNY"): (
        "raw_value * 100000000",
        100_000_000.0,
    ),
}

_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


class ReportGrade(str, Enum):
    """Evidence-coverage grade for a candidate submission."""

    TECHNICAL_PASSED = "TECHNICAL_PASSED"
    """Only market-data (technical) facts are present."""

    FINANCIAL_PARTIAL = "FINANCIAL_PARTIAL"
    """Market facts + at least one non-market evidence category is represented."""

    FULL_REPORT_PASSED = "FULL_REPORT_PASSED"
    """Every company has market + disclosure + fundamental/news/risk evidence."""


@dataclass(frozen=True)
class GradeResult:
    """Full grading breakdown for a submission."""

    grade: ReportGrade
    n_companies: int
    n_technical: int          # companies with technical facts
    n_disclosure: int         # companies with event/disclosure facts
    n_fundamental: int        # companies with fundamental facts
    n_news_or_risk: int       # companies with news or risk facts
    per_company: Dict[str, ReportGrade]


def _is_aware(value: object) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )


def _nonempty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_finite_number(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _valid_line_item(item: object, core_currency: str) -> bool:
    if not isinstance(item, FundamentalLineItem):
        return False
    if not isinstance(item.line_item_id, str):
        return False
    expected_statement = _REQUIRED_FUNDAMENTAL_LINES.get(item.line_item_id)
    if expected_statement is None or item.statement != expected_statement:
        return False
    if item.status != "available":
        return False
    if not _is_finite_number(item.raw_value):
        return False
    if not _is_finite_number(item.normalized_value):
        return False
    if item.currency != core_currency or core_currency != "CNY":
        return False
    if not isinstance(item.raw_unit, str) or not item.raw_unit:
        return False
    if item.normalized_unit != "CNY":
        return False
    rule = _NORMALIZATION_SCALES.get((item.raw_unit, item.normalized_unit))
    if rule is None:
        return False
    expected_formula, scale = rule
    if item.normalization_formula != expected_formula:
        return False
    expected_value = float(item.raw_value) * scale
    return math.isclose(
        float(item.normalized_value),
        expected_value,
        rel_tol=1e-12,
        abs_tol=1e-9,
    )


def _valid_report_identity(
    core: object,
    ticker: str,
    decision_time: datetime,
) -> bool:
    if not isinstance(core, FundamentalReportCore):
        return False
    if core.ticker != ticker or not _nonempty(core.issuer_id):
        return False
    if type(core.report_period_start) is not date:
        return False
    if type(core.report_period_end) is not date:
        return False
    if core.report_period_start >= core.report_period_end:
        return False
    if core.report_period_start != date(core.report_period_end.year, 1, 1):
        return False
    if core.report_period_end != date(core.report_period_end.year, 12, 31):
        return False
    if core.report_type != "annual":
        return False
    if not _is_aware(decision_time):
        return False
    if not _is_aware(core.published_at) or not _is_aware(core.available_at):
        return False
    if core.report_period_end >= core.published_at.date():
        return False
    if not core.published_at <= core.available_at <= decision_time:
        return False
    if not _nonempty(core.source_authority):
        return False
    if not _nonempty(core.source_version_id) or not _nonempty(core.evidence_id):
        return False
    if (
        not isinstance(core.evidence_sha256, str)
        or _SHA256_RE.fullmatch(core.evidence_sha256) is None
    ):
        return False
    if core.currency != "CNY":
        return False
    if type(core.is_correction) is not bool:
        return False
    if core.is_correction:
        if not _nonempty(core.superseded_source_version_id):
            return False
        if not _nonempty(core.superseded_evidence_id):
            return False
    elif (
        core.superseded_source_version_id is not None
        or core.superseded_evidence_id is not None
    ):
        return False
    return True


def is_qualified_fundamental_core(
    core: object,
    ticker: str,
    decision_time: datetime,
) -> bool:
    """Return whether one immutable filing version satisfies the frozen core."""
    if not _valid_report_identity(core, ticker, decision_time):
        return False
    assert isinstance(core, FundamentalReportCore)
    if core.statement_scope != "consolidated":
        return False
    if core.audit_status != "audited":
        return False
    if not isinstance(core.line_items, tuple):
        return False
    if len(core.line_items) != len(_REQUIRED_FUNDAMENTAL_LINES):
        return False
    if not all(isinstance(item, FundamentalLineItem) for item in core.line_items):
        return False
    if not all(isinstance(item.line_item_id, str) for item in core.line_items):
        return False
    item_ids = [item.line_item_id for item in core.line_items]
    if set(item_ids) != set(_REQUIRED_FUNDAMENTAL_LINES):
        return False
    if len(item_ids) != len(set(item_ids)):
        return False
    return all(_valid_line_item(item, core.currency) for item in core.line_items)


def _lineage_identity(core: FundamentalReportCore) -> tuple[object, ...]:
    return (
        core.ticker,
        core.issuer_id,
        core.report_period_start,
        core.report_period_end,
        core.report_type,
        core.statement_scope,
        core.audit_status,
        core.currency,
        core.source_authority,
    )


def _valid_global_lineage(
    cores: Sequence[FundamentalReportCore],
    ticker: str,
    decision_time: datetime,
) -> bool:
    """Reject correction edges that escape their predecessor's identity group."""
    versions: dict[str, FundamentalReportCore] = {}
    evidence_ids: set[str] = set()
    for core in cores:
        if not _valid_report_identity(core, ticker, decision_time):
            return False
        if core.source_version_id in versions or core.evidence_id in evidence_ids:
            return False
        versions[core.source_version_id] = core
        evidence_ids.add(core.evidence_id)
    for core in cores:
        if not core.is_correction:
            continue
        predecessor = versions.get(core.superseded_source_version_id or "")
        if predecessor is None:
            return False
        if predecessor.evidence_id != core.superseded_evidence_id:
            return False
        if _lineage_identity(predecessor) != _lineage_identity(core):
            return False
        if not predecessor.published_at < core.published_at:
            return False
        if not predecessor.available_at < core.available_at:
            return False
    return True


def _unique_terminal_core(
    cores: Sequence[FundamentalReportCore],
    ticker: str,
    decision_time: datetime,
) -> FundamentalReportCore | None:
    """Resolve an explicit correction chain without stale fallback."""
    versions: dict[str, FundamentalReportCore] = {}
    evidence_to_version: dict[str, str] = {}
    for core in cores:
        if not _valid_report_identity(core, ticker, decision_time):
            return None
        if core.source_version_id in versions or core.evidence_id in evidence_to_version:
            return None
        versions[core.source_version_id] = core
        evidence_to_version[core.evidence_id] = core.source_version_id

    predecessor_by_child: dict[str, str] = {}
    child_counts: dict[str, int] = defaultdict(int)
    for version, core in versions.items():
        if not core.is_correction:
            continue
        predecessor = core.superseded_source_version_id
        predecessor_evidence = core.superseded_evidence_id
        if predecessor not in versions:
            return None
        previous = versions[predecessor]
        if previous.evidence_id != predecessor_evidence:
            return None
        if predecessor == version:
            return None
        predecessor_by_child[version] = predecessor
        child_counts[predecessor] += 1
        if child_counts[predecessor] > 1:
            return None

    terminals = [
        version for version in versions
        if child_counts.get(version, 0) == 0
    ]
    if len(terminals) != 1:
        return None
    terminal = terminals[0]

    visited: set[str] = set()
    cursor: str | None = terminal
    while cursor is not None:
        if cursor in visited:
            return None
        visited.add(cursor)
        cursor = predecessor_by_child.get(cursor)
    if len(visited) != len(versions):
        return None
    return versions[terminal]


def has_qualified_fundamental(bundle: CompanyFactBundle) -> bool:
    """Return whether the bundle has one coherent, latest qualified filing."""
    if not _is_aware(bundle.as_of_time):
        return False
    if not isinstance(bundle.qualified_fundamental_reports, tuple):
        return False
    available: list[FundamentalReportCore] = []
    for core in bundle.qualified_fundamental_reports:
        if not isinstance(core, FundamentalReportCore):
            return False
        if not _is_aware(core.available_at):
            return False
        if core.available_at <= bundle.as_of_time:
            if not _valid_report_identity(core, bundle.ticker, bundle.as_of_time):
                return False
            available.append(core)
    if available and not _valid_global_lineage(
        available, bundle.ticker, bundle.as_of_time,
    ):
        return False
    groups: dict[
        tuple[object, ...],
        list[FundamentalReportCore],
    ] = defaultdict(list)
    for core in available:
        key = (
            core.ticker,
            core.issuer_id,
            core.report_period_start,
            core.report_period_end,
            core.report_type,
            core.statement_scope,
            core.audit_status,
            core.currency,
            core.source_authority,
        )
        groups[key].append(core)
    for cores in groups.values():
        terminal = _unique_terminal_core(cores, bundle.ticker, bundle.as_of_time)
        if terminal is not None and is_qualified_fundamental_core(
            terminal,
            bundle.ticker,
            bundle.as_of_time,
        ):
            return True
    return False


def grade_bundle(bundle: CompanyFactBundle) -> ReportGrade:
    """Grade a single company's fact bundle by evidence categories present."""
    has_technical = len(bundle.technical_facts) > 0
    has_disclosure = len(bundle.event_facts) > 0
    has_fundamental = has_qualified_fundamental(bundle)
    has_news_risk = len(bundle.risk_facts) > 0

    if has_technical and has_disclosure and (has_fundamental or has_news_risk):
        return ReportGrade.FULL_REPORT_PASSED

    if has_technical and (has_disclosure or has_fundamental or has_news_risk):
        return ReportGrade.FINANCIAL_PARTIAL

    return ReportGrade.TECHNICAL_PASSED


def grade_submission(
    bundles: Mapping[str, CompanyFactBundle],
) -> GradeResult:
    """Grade an entire submission across all companies.

    The overall grade is the *minimum* of all per-company grades — a chain
    is only as strong as its weakest link.
    """
    if not bundles:
        return GradeResult(
            grade=ReportGrade.TECHNICAL_PASSED,
            n_companies=0,
            n_technical=0,
            n_disclosure=0,
            n_fundamental=0,
            n_news_or_risk=0,
            per_company={},
        )

    per_company: Dict[str, ReportGrade] = {}
    n_technical = n_disclosure = n_fundamental = n_news_or_risk = 0

    for ticker, bundle in bundles.items():
        g = grade_bundle(bundle)
        per_company[ticker] = g
        if bundle.technical_facts:
            n_technical += 1
        if bundle.event_facts:
            n_disclosure += 1
        if has_qualified_fundamental(bundle):
            n_fundamental += 1
        if bundle.risk_facts:
            n_news_or_risk += 1

    # Overall grade = minimum per-company grade
    grades = set(per_company.values())
    if ReportGrade.TECHNICAL_PASSED in grades:
        overall = ReportGrade.TECHNICAL_PASSED
    elif ReportGrade.FINANCIAL_PARTIAL in grades:
        overall = ReportGrade.FINANCIAL_PARTIAL
    else:
        overall = ReportGrade.FULL_REPORT_PASSED

    return GradeResult(
        grade=overall,
        n_companies=len(bundles),
        n_technical=n_technical,
        n_disclosure=n_disclosure,
        n_fundamental=n_fundamental,
        n_news_or_risk=n_news_or_risk,
        per_company=per_company,
    )


# ---------------------------------------------------------------------------
# Convenience: label for use in report summaries
# ---------------------------------------------------------------------------

GRADE_DESCRIPTIONS: Mapping[ReportGrade, str] = {
    ReportGrade.TECHNICAL_PASSED: (
        "行情技术面报告 — 仅包含量价因子和市场数据证据，无基本面/公告/新闻覆盖"
    ),
    ReportGrade.FINANCIAL_PARTIAL: (
        "部分金融分析报告 — 行情证据 + 至少一项非行情数据源覆盖了多数公司"
    ),
    ReportGrade.FULL_REPORT_PASSED: (
        "完整金融分析报告 — 每家公司均有行情、公告、及基本面/风险证据覆盖"
    ),
}
