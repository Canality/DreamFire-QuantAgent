"""Report grading: classify candidate packages by evidence coverage.

Three tiers defined in DEVELOPMENT_PLAN.md §6 (WP0-C):

* TECHNICAL_PASSED — only market/technical evidence; current baseline.
* FINANCIAL_PARTIAL — market evidence + at least one non-market provider
  contributed facts for a majority of companies.
* FULL_REPORT_PASSED — every company has facts from market, disclosure,
  AND at least one of {fundamental, news, risk} providers.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Mapping

from jiuwenswarm.quant.reporting.models import CompanyFactBundle


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


def grade_bundle(bundle: CompanyFactBundle) -> ReportGrade:
    """Grade a single company's fact bundle by evidence categories present."""
    has_technical = len(bundle.technical_facts) > 0
    has_disclosure = len(bundle.event_facts) > 0
    has_fundamental = len(bundle.fundamental_facts) > 0
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
        if bundle.fundamental_facts:
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
