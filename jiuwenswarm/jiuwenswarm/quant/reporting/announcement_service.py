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
from typing import Callable, Dict, List, Sequence
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
        *,
        retry_provider_factory: Callable[[], AnnouncementProvider] | None = None,
    ):
        self._provider = provider
        self._archive = archive
        self._retry_provider_factory = retry_provider_factory

    async def run(
        self,
        tickers: List[str],
        as_of_time: datetime,
        *,
        required_universe: Sequence[str] | None = None,
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

        required = list(required_universe) if required_universe is not None else None
        if required is not None and (
            len(tickers) != len(required) or set(tickers) != set(required)
        ):
            raise ValueError(
                "requested tickers do not match the required announcement universe"
            )

        primary = await self._fetch_all(self._provider, tickers, as_of_time)
        attempts = [self._attempt_diagnostics(primary)]
        chosen = primary
        recovered = False

        if required is not None and primary.total_facts == 0:
            if self._retry_provider_factory is None:
                health = self._unhealthy_diagnostics(
                    tickers,
                    attempts,
                    terminal_cause="fresh_retry_provider_unavailable",
                )
                raise AnnouncementUniverseHealthError(health)
            retry_provider = self._retry_provider_factory()
            retry = await self._fetch_all(retry_provider, tickers, as_of_time)
            attempts.append(self._attempt_diagnostics(retry))
            if retry.total_facts == 0:
                health = self._unhealthy_diagnostics(
                    tickers,
                    attempts,
                    terminal_cause="required_universe_all_empty",
                )
                raise AnnouncementUniverseHealthError(health)
            chosen = retry
            recovered = True

        chosen.universe_health = {
            "required": required is not None,
            "required_ticker_count": len(required or ()),
            "requested_ticker_count": len(tickers),
            "healthy": True,
            "recovered_after_retry": recovered,
            "terminal_cause": (
                "fresh_provider_retry_nonempty" if recovered else "primary_accepted"
            ),
            "attempts": attempts,
        }
        self._archive_result(chosen)
        return chosen

    async def _fetch_all(
        self,
        provider: AnnouncementProvider,
        tickers: List[str],
        as_of_time: datetime,
    ) -> ServiceResult:
        """Fetch one bounded universe attempt without mutating the archive."""

        manifest: Dict[str, EvidenceRef] = {}
        facts_by_ticker: Dict[str, List[MetricFact]] = {}
        statuses: Dict[str, ProviderStatus] = {}
        diagnostics_by_ticker: Dict[str, AnnouncementDiagnostics] = {}

        semaphore = asyncio.Semaphore(8)

        async def _fetch_one(ticker: str):
            async with semaphore:
                return ticker, await provider.fetch_rich(ticker, as_of_time)

        # Network retrieval is concurrent, while archive writes below remain
        # sequential because EvidenceArchive intentionally has one writer.
        fetched = await asyncio.gather(*(_fetch_one(ticker) for ticker in tickers))
        for ticker, result in fetched:
            facts_by_ticker[ticker] = list(result.facts)
            statuses[ticker] = result.status
            diagnostics_by_ticker[ticker] = result.diagnostics

            # Retain raw payloads until the universe attempt is accepted. This
            # prevents a failed health probe from becoming candidate evidence.
            for eid, raw_json in result.raw_payloads.items():
                # Find the matching EvidenceRef
                matching_ref = None
                for ev_ref in result.evidence_refs:
                    if ev_ref.evidence_id == eid:
                        matching_ref = ev_ref
                        break
                if matching_ref is None:
                    continue
                manifest[eid] = matching_ref

        return ServiceResult(
            facts_by_ticker=facts_by_ticker,
            manifest=manifest,
            statuses=statuses,
            diagnostics_by_ticker=diagnostics_by_ticker,
            raw_payloads={
                eid: raw_json
                for _ticker, result in fetched
                for eid, raw_json in result.raw_payloads.items()
            },
        )

    def _archive_result(self, result: ServiceResult) -> None:
        for evidence_id, raw_json in result.raw_payloads.items():
            ref = result.manifest.get(evidence_id)
            if ref is not None:
                self._archive.write(evidence_id, raw_json, ref)

    @staticmethod
    def _attempt_diagnostics(result: ServiceResult) -> Dict[str, object]:
        status_counts: Dict[str, int] = {}
        for status in result.statuses.values():
            status_counts[status.value] = status_counts.get(status.value, 0) + 1
        return {
            "total_facts": result.total_facts,
            "tickers_with_events": result.tickers_with_events,
            "all_empty": result.total_facts == 0,
            "status_counts": status_counts,
            "terminal_cause_counts": result.terminal_cause_counts,
            "diagnostics_by_ticker": {
                ticker: diagnostics.to_dict()
                for ticker, diagnostics in result.diagnostics_by_ticker.items()
            },
        }

    @staticmethod
    def _unhealthy_diagnostics(
        tickers: Sequence[str],
        attempts: List[Dict[str, object]],
        *,
        terminal_cause: str,
    ) -> Dict[str, object]:
        return {
            "required": True,
            "required_ticker_count": len(tickers),
            "requested_ticker_count": len(tickers),
            "healthy": False,
            "recovered_after_retry": False,
            "terminal_cause": terminal_cause,
            "attempts": attempts,
        }


class AnnouncementUniverseHealthError(RuntimeError):
    """Required announcement universe stayed empty after a fresh retry."""

    def __init__(self, diagnostics: Dict[str, object]):
        self.diagnostics = diagnostics
        cause = diagnostics.get("terminal_cause", "unknown")
        super().__init__(f"announcement universe health failed: {cause}")


class ServiceResult:
    """Result of running ``AnnouncementService.run()``."""

    def __init__(
        self,
        facts_by_ticker: Dict[str, List[MetricFact]],
        manifest: Dict[str, EvidenceRef],
        statuses: Dict[str, ProviderStatus],
        diagnostics_by_ticker: Dict[str, AnnouncementDiagnostics] | None = None,
        raw_payloads: Dict[str, str] | None = None,
        universe_health: Dict[str, object] | None = None,
    ):
        self.facts_by_ticker = facts_by_ticker
        self.manifest = manifest
        self.statuses = statuses
        self.diagnostics_by_ticker = diagnostics_by_ticker or {}
        self.raw_payloads = raw_payloads or {}
        self.universe_health = universe_health or {
            "required": False,
            "healthy": True,
            "recovered_after_retry": False,
            "terminal_cause": "not_required",
            "attempts": [],
        }

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
    *,
    required_universe: Sequence[str] | None = None,
    retry_provider_factory: Callable[[], AnnouncementProvider] | None = None,
) -> ServiceResult:
    """Synchronous wrapper for ``AnnouncementService.run()``.

    Use this from the direct path (``run_quant_pipeline.py``) which is
    not an async entry point.
    """
    if provider is None:
        provider = AnnouncementProvider()
        if retry_provider_factory is None:
            retry_provider_factory = AnnouncementProvider
    archive = EvidenceArchive(archive_root)
    service = AnnouncementService(
        provider,
        archive,
        retry_provider_factory=retry_provider_factory,
    )
    return asyncio.run(
        service.run(
            tickers,
            as_of_time,
            required_universe=required_universe,
        )
    )
