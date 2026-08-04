"""Base provider interface for external data sources."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Tuple

from jiuwenswarm.quant.reporting.models import MetricFact
from jiuwenswarm.quant.reporting.providers.status import ProviderCategory, ProviderStatus


class BaseProvider(ABC):
    """Abstract base for data providers (fundamentals, disclosures, news).

    Each concrete provider must satisfy this contract:

    1. **Deterministic identity**: ``name`` and ``source_url`` are fixed at init.
    2. **Point-in-time**: ``fetch_for_ticker`` must only return facts whose
       ``available_at`` (or publish date) is ≤ ``as_of_time``.
    3. **Status honesty**: return ``COMPLETE`` / ``PARTIAL`` / ``UNAVAILABLE``;
       never mask fetch failures as "no significant events".
    4. **Timeout and retry**: honour ``timeout`` and ``max_retries``.
    5. **EvidenceRef for every fact**: each ``MetricFact`` must carry at least one
       ``evidence_id`` that resolves to a stored ``EvidenceRef`` with a content hash.
    6. **Fixture-compatible**: must work with a ``ProviderFixture`` in tests
       without network access.
    """

    def __init__(
        self,
        name: str,
        source_url: str,
        timeout: float = 10.0,
        max_retries: int = 2,
    ):
        if not name.strip():
            raise ValueError("Provider name must be non-empty")
        if not source_url.strip():
            raise ValueError("Provider source_url must be non-empty")
        self.name = name
        self.source_url = source_url
        self.timeout = timeout
        self.max_retries = max_retries

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @property
    @abstractmethod
    def category(self) -> ProviderCategory:
        """Semantic category for registry discovery and quality-gate checks."""
        ...

    @abstractmethod
    async def fetch_for_ticker(
        self, ticker: str, as_of_time: datetime,
    ) -> Tuple[List[MetricFact], ProviderStatus]:
        """Fetch facts for a single ticker at a decision point.

        Args:
            ticker: e.g. ``"600000.SH"``.
            as_of_time: The decision datetime.  Only facts available on or
                before this moment may be returned.

        Returns:
            ``(facts, status)`` where *status* is one of
            ``COMPLETE`` / ``PARTIAL`` / ``UNAVAILABLE``.
        """
        ...

    @abstractmethod
    def supports_ticker(self, ticker: str) -> bool:
        """Whether this provider can serve facts for the given ticker."""
        ...

    # ------------------------------------------------------------------
    # Validation helpers (callable by subclasses)
    # ------------------------------------------------------------------

    def _validate_ticker_format(self, ticker: str) -> None:
        """Raise ValueError if *ticker* does not match ``XXXXXX.{SH,SZ}``."""
        if not isinstance(ticker, str) or "." not in ticker:
            raise ValueError(f"Invalid ticker format: {ticker!r}")
        code, exchange = ticker.split(".", 1)
        if len(code) != 6 or not code.isdigit():
            raise ValueError(f"Invalid ticker code: {ticker!r}")
        if exchange not in ("SH", "SZ"):
            raise ValueError(f"Invalid exchange: {ticker!r}")

    def _validate_as_of_time(self, as_of_time: datetime) -> None:
        """Raise ValueError if *as_of_time* is in the future or timezone-naive."""
        if as_of_time.tzinfo is None:
            raise ValueError("as_of_time must be timezone-aware")
        now = datetime.now(as_of_time.tzinfo)
        if as_of_time > now:
            raise ValueError(
                f"as_of_time {as_of_time.isoformat()} is in the future"
            )
