"""Base provider interface for external data sources."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Tuple

from jiuwenswarm.quant.reporting.models import MetricFact


class BaseProvider(ABC):
    """Abstract base for data providers (fundamentals, disclosures, news).

    Each provider must:
    - Have a clear source name and URL.
    - Save publish_time, available_at, retrieval_at, content_hash.
    - Have timeout, limited retries, and per-company error recording.
    - NOT mask fetch failures as "no significant events".
    - Support fixture tests and real smoke tests.
    """

    def __init__(
        self,
        name: str,
        source_url: str,
        timeout: float = 10.0,
        max_retries: int = 2,
    ):
        self.name = name
        self.source_url = source_url
        self.timeout = timeout
        self.max_retries = max_retries

    @abstractmethod
    async def fetch_for_ticker(
        self, ticker: str, as_of_time: datetime
    ) -> Tuple[List[MetricFact], str]:
        """Fetch facts for a single ticker at a decision point.

        Returns (facts, status) where status is "complete" | "partial" | "unavailable".
        """
        ...

    @abstractmethod
    def supports_ticker(self, ticker: str) -> bool:
        """Whether this provider can serve facts for the given ticker."""
        ...
