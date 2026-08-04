"""Unified evidence model for deterministic report generation.

All report content must be derived from these structured facts.
No hardcoded numbers, no LLM hallucinations, no stale IC numbers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Mapping, Tuple


@dataclass(frozen=True)
class EvidenceRef:
    """A pointer to an external piece of evidence with time-bound availability."""

    evidence_id: str
    source_type: str       # "market_data" | "financial_statement" | "disclosure" | "news" | "agent_view"
    source_name: str        # e.g. "Sina Finance", "CSI 300", "Bull Analyst"
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
class AgentView:
    """Structured output from an Alpha or Risk & Evidence analyst.

    Historical "bull"/"bear" roles are deprecated but still accepted
    for backward compatibility with archived data.
    """

    role: str                         # "bull" | "bear" | "alpha" | "risk_evidence"
    verdict: str                      # "overweight" | "neutral" | "underweight"
    confidence: str                   # "high" | "medium" | "low"
    candidate_tickers: Tuple[str, ...]
    warnings: Tuple[str, ...]
    evidence_ids: Tuple[str, ...]
    unknown_fields: Tuple[str, ...]   # fields that were requested but unavailable
    summary: str = ""                 # optional human-readable text


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
    data_provider_status: str          # "complete" | "partial" | "unavailable"


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
