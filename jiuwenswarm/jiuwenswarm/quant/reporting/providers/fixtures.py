"""Shared provider fixtures for unit and integration tests.

These factories produce deterministic, network-free MetricFact and EvidenceRef
instances so every concrete provider can be tested offline.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import List, Tuple

from jiuwenswarm.quant.reporting.models import EvidenceRef, MetricFact
from jiuwenswarm.quant.reporting.providers.base import BaseProvider
from jiuwenswarm.quant.reporting.providers.status import ProviderCategory, ProviderStatus


# ---------------------------------------------------------------------------
# Time constants
# ---------------------------------------------------------------------------

UTC = timezone.utc
CST = timezone.utc  # Use UTC in tests; real providers use local timezone

FROZEN_NOW = datetime(2026, 7, 30, 12, 0, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# EvidenceRef builders
# ---------------------------------------------------------------------------

def make_evidence_ref(
    evidence_id: str,
    source_type: str = "disclosure",
    source_name: str = "test-provider",
    content: str = "",
) -> EvidenceRef:
    """Build an EvidenceRef with deterministic defaults."""
    content_bytes = content.encode("utf-8") if content else evidence_id.encode("utf-8")
    return EvidenceRef(
        evidence_id=evidence_id,
        source_type=source_type,
        source_name=source_name,
        source_url="https://example.com/test",
        period_end=None,
        published_at=FROZEN_NOW,
        available_at=FROZEN_NOW,
        retrieved_at=FROZEN_NOW,
        content_sha256=hashlib.sha256(content_bytes).hexdigest(),
    )


# ---------------------------------------------------------------------------
# MetricFact builders
# ---------------------------------------------------------------------------

def make_metric_fact(
    name: str,
    value: float | int | str | None = None,
    unit: str | None = None,
    status: str = "available",
    evidence_ids: Tuple[str, ...] = ("test-evidence-1",),
) -> MetricFact:
    """Build a MetricFact with sensible defaults."""
    return MetricFact(
        name=name,
        value=value,
        unit=unit,
        status=status,
        evidence_ids=evidence_ids,
    )


def make_announcement_fact(
    title: str,
    announce_date: datetime,
    ticker: str = "600000.SH",
    url: str = "https://example.com/ann/1",
) -> MetricFact:
    """Build a MetricFact that looks like a real exchange announcement."""
    evidence_id = f"ann-{ticker}-{announce_date.strftime('%Y%m%d')}-{_short_hash(title)}"
    return MetricFact(
        name="exchange_announcement",
        value=title,
        unit=None,
        status="available",
        evidence_ids=(evidence_id,),
    )


def _short_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:8]


# ---------------------------------------------------------------------------
# Mock provider
# ---------------------------------------------------------------------------

class MockProvider(BaseProvider):
    """A fully deterministic provider for unit tests.

    Returns pre-programmed facts from an in-memory store keyed by
    ``(ticker, as_of_time.date())``.  Never touches the network.
    """

    def __init__(
        self,
        name: str = "mock-provider",
        category: ProviderCategory = ProviderCategory.DISCLOSURE,
    ):
        super().__init__(name=name, source_url="mock://local")
        self._category = category
        self._store: dict[Tuple[str, str], Tuple[List[MetricFact], ProviderStatus]] = {}
        self._fetch_count: int = 0

    @property
    def category(self) -> ProviderCategory:
        return self._category

    def seed(
        self,
        ticker: str,
        as_of_date: str,
        facts: List[MetricFact],
        status: ProviderStatus = ProviderStatus.COMPLETE,
    ) -> None:
        """Pre-populate the store with facts for a given ticker/date."""
        self._store[(ticker, as_of_date)] = (list(facts), status)

    async def fetch_for_ticker(
        self, ticker: str, as_of_time: datetime,
    ) -> Tuple[List[MetricFact], ProviderStatus]:
        self._fetch_count += 1
        key = (ticker, as_of_time.strftime("%Y-%m-%d"))
        if key in self._store:
            facts, status = self._store[key]
            return list(facts), status
        return [], ProviderStatus.UNAVAILABLE

    def supports_ticker(self, ticker: str) -> bool:
        return True


class TickerFilteredMockProvider(MockProvider):
    """Mock provider that only supports specific tickers."""

    def __init__(self, supported: set[str], name: str = "filtered-mock"):
        super().__init__(name=name)
        self._supported = supported

    def supports_ticker(self, ticker: str) -> bool:
        return ticker in self._supported
