"""Shared announcement service: fetch → archive → facts → quality gate.

This module is the single integration point that both ``run_quant_pipeline.py``
(direct) and ``run_multi_agent.py`` (formal) are intended to call to populate
announcement evidence.  Once wired, it ensures both paths use identical logic
and produce identical EvidenceRefs from the same snapshot.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Dict, List
from zoneinfo import ZoneInfo

from jiuwenswarm.quant.reporting.models import EvidenceRef, MetricFact
from jiuwenswarm.quant.reporting.providers.announcement import (
    AnnouncementDiagnostics,
    AnnouncementProvider,
)
from jiuwenswarm.quant.reporting.providers.archive import EvidenceArchive
from jiuwenswarm.quant.reporting.providers.status import ProviderStatus


class AnnouncementService:
    """Fetch announcements and archive them in one pass.

    Usage (direct or formal)::

        service = AnnouncementService(provider, archive)
        result = await service.run(tickers, as_of_time)
        # result.facts_by_ticker → use in CompanyFactBundle
        # result.manifest → pass to quality gate
        # result.statuses → per-ticker ProviderStatus for grading
    """

    def __init__(
        self,
        provider: AnnouncementProvider,
        archive: EvidenceArchive,
    ):
        self._provider = provider
        self._archive = archive

    async def run(
        self,
        tickers: List[str],
        as_of_time: datetime,
    ) -> ServiceResult:
        """Fetch and archive announcements for all *tickers*.

        Args:
            tickers: List of ticker codes, e.g. ``["600000.SH", "000001.SZ"]``.
            as_of_time: The decision datetime (PIT boundary).

        Returns:
            ``ServiceResult`` with per-ticker facts, archive manifest, and statuses.
        """
        if as_of_time.tzinfo is None:
            as_of_time = as_of_time.replace(tzinfo=ZoneInfo("Asia/Shanghai"))

        manifest: Dict[str, EvidenceRef] = {}
        facts_by_ticker: Dict[str, List[MetricFact]] = {}
        statuses: Dict[str, ProviderStatus] = {}
        diagnostics_by_ticker: Dict[str, AnnouncementDiagnostics] = {}

        semaphore = asyncio.Semaphore(8)

        async def _fetch_one(ticker: str):
            async with semaphore:
                return ticker, await self._provider.fetch_rich(ticker, as_of_time)

        # Network retrieval is concurrent, while archive writes below remain
        # sequential because EvidenceArchive intentionally has one writer.
        fetched = await asyncio.gather(*(_fetch_one(ticker) for ticker in tickers))
        for ticker, result in fetched:
            facts_by_ticker[ticker] = list(result.facts)
            statuses[ticker] = result.status
            diagnostics_by_ticker[ticker] = result.diagnostics

            # Archive every fact's raw payload
            for eid, raw_json in result.raw_payloads.items():
                # Find the matching EvidenceRef
                matching_ref = None
                for ev_ref in result.evidence_refs:
                    if ev_ref.evidence_id == eid:
                        matching_ref = ev_ref
                        break
                if matching_ref is None:
                    continue
                self._archive.write(eid, raw_json, matching_ref)
                manifest[eid] = matching_ref

        return ServiceResult(
            facts_by_ticker=facts_by_ticker,
            manifest=manifest,
            statuses=statuses,
            diagnostics_by_ticker=diagnostics_by_ticker,
        )


class ServiceResult:
    """Result of running ``AnnouncementService.run()``."""

    def __init__(
        self,
        facts_by_ticker: Dict[str, List[MetricFact]],
        manifest: Dict[str, EvidenceRef],
        statuses: Dict[str, ProviderStatus],
        diagnostics_by_ticker: Dict[str, AnnouncementDiagnostics] | None = None,
    ):
        self.facts_by_ticker = facts_by_ticker
        self.manifest = manifest
        self.statuses = statuses
        self.diagnostics_by_ticker = diagnostics_by_ticker or {}

    @property
    def total_facts(self) -> int:
        return sum(len(f) for f in self.facts_by_ticker.values())

    @property
    def tickers_with_events(self) -> int:
        return sum(bool(facts) for facts in self.facts_by_ticker.values())

    @property
    def terminal_cause_counts(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for diagnostics in self.diagnostics_by_ticker.values():
            cause = diagnostics.terminal_cause.value
            counts[cause] = counts.get(cause, 0) + 1
        return counts


# ---------------------------------------------------------------------------
# Synchronous convenience (for direct path which is not async)
# ---------------------------------------------------------------------------

def run_announcement_service(
    tickers: List[str],
    as_of_time: datetime,
    archive_root: Path,
    provider: AnnouncementProvider | None = None,
) -> ServiceResult:
    """Synchronous wrapper for ``AnnouncementService.run()``.

    Use this from the direct path (``run_quant_pipeline.py``) which is
    not an async entry point.
    """
    if provider is None:
        provider = AnnouncementProvider()
    archive = EvidenceArchive(archive_root)
    service = AnnouncementService(provider, archive)
    return asyncio.run(service.run(tickers, as_of_time))
