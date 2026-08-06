"""Unified evidence model for deterministic report generation.

All report content must be derived from these structured facts.
No hardcoded numbers, no LLM hallucinations, no stale IC numbers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Mapping, Tuple


@dataclass(frozen=True)
class EvidenceRef:
    """A pointer to an external piece of evidence with time-bound availability."""

    evidence_id: str
    source_type: str       # "market_data" | "financial_statement" | "disclosure" | "news" | "agent_view"
    source_name: str        # e.g. "Sina Finance", "CSI 300", "Alpha Analyst"
    source_url: str | None
    period_end: datetime | None          # the data period end
    published_at: datetime | None         # when it was published
    available_at: datetime               # when it became available for retrieval
    retrieved_at: datetime               # when we actually retrieved it
    content_sha256: str                  # hash of the raw content


@dataclass(frozen=True)
class MetricFact:
    """A single named metric with value, unit, status, and evidence."""

    name: str
    value: float | int | str | None
    unit: str | None
    status: str          # "available" | "unavailable" | "stale" | "derived"
    evidence_ids: Tuple[str, ...]


@dataclass(frozen=True)
class FundamentalLineItem:
    """One normalized line item inside a qualification-only filing core.

    These objects do not replace :class:`MetricFact` and are not rendered.
    They carry the statement semantics needed to decide whether a future
    Provider's filing is strong enough to affect the report grade.
    """

    statement: str
    line_item_id: str
    status: str
    raw_value: float | int | None
    raw_unit: str | None
    currency: str | None
    normalized_value: float | int | None
    normalized_unit: str | None
    normalization_formula: str | None


@dataclass(frozen=True)
class FundamentalReportCore:
    """Immutable qualification record for one version of one annual filing."""

    ticker: str
    issuer_id: str
    report_period_start: date
    report_period_end: date
    report_type: str
    statement_scope: str
    audit_status: str
    currency: str
    published_at: datetime
    available_at: datetime
    source_authority: str
    source_version_id: str
    evidence_id: str
    evidence_sha256: str
    is_correction: bool
    superseded_source_version_id: str | None
    superseded_evidence_id: str | None
    line_items: Tuple[FundamentalLineItem, ...]


@dataclass(frozen=True)
class AgentView:
    """Structured output from an Alpha or Risk & Evidence analyst."""

    role: str                         # "alpha" | "risk_evidence"
    verdict: str                      # "overweight" | "neutral" | "underweight"
    confidence: str                   # "high" | "medium" | "low"
    candidate_tickers: Tuple[str, ...]
    warnings: Tuple[str, ...]
    evidence_ids: Tuple[str, ...]
    unknown_fields: Tuple[str, ...]   # fields that were requested but unavailable
    summary: str = ""                 # optional human-readable text

    def __post_init__(self) -> None:
        if self.role not in {"alpha", "risk_evidence"}:
            raise ValueError(f"unsupported AgentView role: {self.role}")


@dataclass(frozen=True)
class CompanyFactBundle:
    """All available structured facts for a single company at a decision point."""

    ticker: str
    report_code: str                  # 6-digit code for file naming
    name: str
    sector: str
    as_of_time: datetime              # decision date
    portfolio_weight: float           # 0.0 for unselected companies
    selected: bool                    # True if in the portfolio
    weight_zero_reason: str           # "" if selected, otherwise why not

    # Fact categories
    technical_facts: Tuple[MetricFact, ...]
    fundamental_facts: Tuple[MetricFact, ...]
    event_facts: Tuple[MetricFact, ...]       # disclosures, news, announcements
    risk_facts: Tuple[MetricFact, ...]
    agent_views: Tuple[AgentView, ...]

    # Provider status
    data_provider_status: str          # complete | available_no_event | partial | unavailable

    # Qualification-only filing cores. Generic ``fundamental_facts`` remain
    # renderable but cannot self-attest report-grade coverage.
    qualified_fundamental_reports: Tuple[FundamentalReportCore, ...] = ()


@dataclass(frozen=True)
class PortfolioSnapshot:
    """The portfolio at decision time — single source for weights in all outputs."""

    as_of_time: datetime
    holdings: Mapping[str, float]      # ticker → weight
    cash: float
    total_equity: float
    n_selected: int
    n_sectors_represented: int
    strategy_id: str                   # "production_six_factor" | "phase_b_t2_score_alloc"
    contract_hash: str                 # config_hash of SubmissionContract used


@dataclass(frozen=True)
class ReportQualityResult:
    """Result of running the quality gate on a candidate submission."""

    passed: bool
    blockers: Tuple[str, ...]
    warnings: Tuple[str, ...]
    metrics: Mapping[str, float | int] = field(default_factory=dict)
