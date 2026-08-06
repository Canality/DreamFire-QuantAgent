"""Shared announcement service: fetch → archive → facts → quality gate.

This module is the single integration point that both ``run_quant_pipeline.py``
(direct) and ``run_multi_agent.py`` (formal) are intended to call to populate
announcement evidence.  Once wired, it ensures both paths use identical logic
and produce identical EvidenceRefs from the same snapshot.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from types import MappingProxyType
from typing import Callable, Dict, List, Sequence
from zoneinfo import ZoneInfo

from jiuwenswarm.quant.reporting.models import EvidenceRef, MetricFact
from jiuwenswarm.quant.reporting.providers.announcement import (
    AnnouncementDiagnostics,
    AnnouncementProvider,
    AnnouncementTerminalCause,
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
        self._write_receipt(chosen, tickers, as_of_time)
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

    def _write_receipt(
        self,
        result: ServiceResult,
        tickers: Sequence[str],
        as_of_time: datetime,
    ) -> None:
        archived_manifest = self._archive.build_manifest()
        for ticker in tickers:
            for fact in result.facts_by_ticker.get(ticker, []):
                if not isinstance(fact, MetricFact) or len(fact.evidence_ids) != 1:
                    raise ValueError(
                        f"announcement facts are non-canonical for {ticker}"
                    )
                evidence_id = fact.evidence_ids[0]
                ref = archived_manifest.get(evidence_id)
                raw = self._archive.read(evidence_id)
                if ref is None or raw is None:
                    raise ValueError(
                        f"announcement evidence missing after archive write: {evidence_id}"
                    )
                canonical_fact = AnnouncementProvider.replay_archived_fact(
                    ticker,
                    raw,
                    ref,
                    as_of_time,
                )
                if fact != canonical_fact:
                    raise ValueError(
                        f"live announcement fact differs from archived payload: {evidence_id}"
                    )
            result.facts_by_ticker[ticker] = sorted(
                result.facts_by_ticker.get(ticker, []),
                key=lambda fact: tuple(fact.evidence_ids),
            )
        receipt = _build_receipt(result, tickers, as_of_time)
        content = _canonical_json(receipt)
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        receipt_id = f"announcement-receipt-{digest}"
        ref = EvidenceRef(
            evidence_id=receipt_id,
            source_type="announcement_run_receipt",
            source_name="AnnouncementService",
            source_url=None,
            period_end=as_of_time,
            published_at=as_of_time,
            available_at=as_of_time,
            retrieved_at=datetime.now(as_of_time.tzinfo),
            content_sha256=digest,
        )
        self._archive.write(receipt_id, content, ref)
        result.receipt_id = receipt_id
        result.snapshot_sha256 = digest
        result.mode = "LIVE_ACCEPTED"
        result.requested_tickers = tuple(tickers)
        result.as_of_time = as_of_time
        result.seal()

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
        receipt_id: str | None = None,
        snapshot_sha256: str | None = None,
        mode: str = "UNBOUND",
        requested_tickers: Sequence[str] = (),
        as_of_time: datetime | None = None,
    ):
        self._sealed = False
        self.facts_by_ticker = {
            ticker: list(facts) for ticker, facts in facts_by_ticker.items()
        }
        self.manifest = dict(manifest)
        self.statuses = dict(statuses)
        self.diagnostics_by_ticker = dict(diagnostics_by_ticker or {})
        self.raw_payloads = dict(raw_payloads or {})
        self.universe_health = json.loads(json.dumps(universe_health or {
            "required": False,
            "healthy": True,
            "recovered_after_retry": False,
            "terminal_cause": "not_required",
            "attempts": [],
        }, ensure_ascii=False))
        self.receipt_id = receipt_id
        self.snapshot_sha256 = snapshot_sha256
        self.mode = mode
        self.requested_tickers = tuple(requested_tickers)
        self.as_of_time = as_of_time

    def __setattr__(self, name: str, value: object) -> None:
        if getattr(self, "_sealed", False):
            raise AttributeError("accepted announcement ServiceResult is immutable")
        object.__setattr__(self, name, value)

    def seal(self) -> None:
        """Deep-freeze all state covered by the accepted receipt hash."""
        if self._sealed:
            return
        self.facts_by_ticker = MappingProxyType({
            ticker: tuple(facts)
            for ticker, facts in self.facts_by_ticker.items()
        })
        self.manifest = MappingProxyType(dict(self.manifest))
        self.statuses = MappingProxyType(dict(self.statuses))
        self.diagnostics_by_ticker = MappingProxyType(
            dict(self.diagnostics_by_ticker)
        )
        self.raw_payloads = MappingProxyType({})
        self.universe_health = _freeze_json(self.universe_health)
        self.requested_tickers = tuple(self.requested_tickers)
        object.__setattr__(self, "_sealed", True)

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

    def status_value(self, ticker: str) -> str:
        """Return the exact shared ProviderStatus value for one ticker."""
        if not self._sealed:
            raise ValueError("announcement result is not sealed")
        try:
            return self.statuses[ticker].value
        except KeyError as exc:
            raise ValueError(f"announcement status missing for {ticker}") from exc


def announcement_snapshot_projection(result: ServiceResult) -> Dict[str, object]:
    """Return the one direct/formal summary projection for an accepted run."""
    if not getattr(result, "_sealed", False):
        raise ValueError("announcement result is not sealed")
    if result.mode not in {"LIVE_ACCEPTED", "OFFLINE_REPLAY"}:
        raise ValueError("announcement result is not bound to an accepted receipt")
    if not result.receipt_id or not result.snapshot_sha256 or result.as_of_time is None:
        raise ValueError("announcement result receipt binding is incomplete")
    return {
        "as_of_time": result.as_of_time.isoformat(),
        "mode": result.mode,
        "receipt_id": result.receipt_id,
        "snapshot_sha256": result.snapshot_sha256,
        "healthy": bool(result.universe_health.get("healthy")),
        "total_facts": result.total_facts,
        "tickers_with_events": result.tickers_with_events,
        "manifest_count": len(result.manifest),
        "status_counts": {
            status.value: sum(item == status for item in result.statuses.values())
            for status in ProviderStatus
            if any(item == status for item in result.statuses.values())
        },
        "terminal_cause_counts": result.terminal_cause_counts,
        "diagnostics_by_ticker": {
            ticker: diagnostics.to_dict()
            for ticker, diagnostics in result.diagnostics_by_ticker.items()
        },
        "universe_health": _thaw_json(result.universe_health),
    }


def replay_announcement_service(
    archive_root: Path,
    receipt_id: str,
    *,
    expected_tickers: Sequence[str] | None = None,
    expected_as_of_time: datetime | None = None,
) -> ServiceResult:
    """Replay an accepted receipt and its payloads without any provider call."""
    archive = EvidenceArchive(archive_root)
    receipt_ref = archive.build_manifest().get(receipt_id)
    content = archive.read(receipt_id)
    if receipt_ref is None or content is None:
        raise ValueError("announcement receipt is missing or tampered")
    if receipt_ref.source_type != "announcement_run_receipt":
        raise ValueError("announcement receipt source_type mismatch")
    try:
        receipt = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("announcement receipt is invalid JSON") from exc
    if not isinstance(receipt, dict) or receipt.get("schema_version") != 1:
        raise ValueError("unsupported announcement receipt schema")
    if receipt.get("source_mode") != "LIVE_ACCEPTED":
        raise ValueError("announcement receipt source mode is invalid")
    if _canonical_json(receipt).encode("utf-8") != content:
        raise ValueError("announcement receipt is not canonical")
    receipt_digest = hashlib.sha256(content).hexdigest()
    if (
        receipt_ref.content_sha256 != receipt_digest
        or receipt_id != f"announcement-receipt-{receipt_digest}"
    ):
        raise ValueError("announcement receipt identity mismatch")

    tickers = receipt.get("requested_tickers")
    ticker_rows = receipt.get("tickers")
    if (
        not isinstance(tickers, list)
        or not tickers
        or len(tickers) != len(set(tickers))
        or not all(isinstance(ticker, str) and ticker for ticker in tickers)
        or not isinstance(ticker_rows, dict)
        or set(ticker_rows) != set(tickers)
    ):
        raise ValueError("announcement receipt universe is invalid")
    if expected_tickers is not None and list(expected_tickers) != tickers:
        raise ValueError("announcement receipt universe mismatch")
    try:
        as_of_time = datetime.fromisoformat(str(receipt["as_of_time"]))
    except (KeyError, ValueError) as exc:
        raise ValueError("announcement receipt as_of_time is invalid") from exc
    if as_of_time.tzinfo is None:
        raise ValueError("announcement receipt as_of_time must be timezone-aware")
    if (
        receipt_ref.available_at != as_of_time
        or receipt_ref.published_at != as_of_time
        or receipt_ref.period_end != as_of_time
    ):
        raise ValueError("announcement receipt time binding mismatch")
    if expected_as_of_time is not None and expected_as_of_time != as_of_time:
        raise ValueError("announcement receipt as_of_time mismatch")

    facts_by_ticker: Dict[str, List[MetricFact]] = {}
    manifest: Dict[str, EvidenceRef] = {}
    statuses: Dict[str, ProviderStatus] = {}
    diagnostics_by_ticker: Dict[str, AnnouncementDiagnostics] = {}
    seen_evidence: set[str] = set()
    provider = AnnouncementProvider()
    full_manifest = archive.build_manifest()
    for ticker in tickers:
        row = ticker_rows[ticker]
        if not isinstance(row, dict):
            raise ValueError(f"announcement receipt row is invalid for {ticker}")
        try:
            status = ProviderStatus(row["status"])
            diagnostics = _diagnostics_from_dict(row["diagnostics"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"announcement receipt state is invalid for {ticker}") from exc
        evidence_ids = row.get("evidence_ids")
        if (
            not isinstance(evidence_ids, list)
            or evidence_ids != sorted(evidence_ids)
            or len(evidence_ids) != len(set(evidence_ids))
            or not all(isinstance(item, str) and item for item in evidence_ids)
        ):
            raise ValueError(f"announcement receipt evidence list is invalid for {ticker}")
        if seen_evidence.intersection(evidence_ids):
            raise ValueError("announcement receipt reuses evidence across tickers")
        seen_evidence.update(evidence_ids)
        facts: List[MetricFact] = []
        for evidence_id in evidence_ids:
            ref = full_manifest.get(evidence_id)
            raw = archive.read(evidence_id)
            if ref is None or raw is None:
                raise ValueError(f"announcement evidence missing or tampered: {evidence_id}")
            fact = provider.replay_archived_fact(ticker, raw, ref, as_of_time)
            facts.append(fact)
            manifest[evidence_id] = ref
        _validate_state(status, diagnostics, len(facts))
        facts_by_ticker[ticker] = facts
        statuses[ticker] = status
        diagnostics_by_ticker[ticker] = diagnostics

    universe_health = receipt.get("universe_health")
    if not isinstance(universe_health, dict) or universe_health.get("healthy") is not True:
        raise ValueError("announcement receipt health is invalid")
    result = ServiceResult(
        facts_by_ticker=facts_by_ticker,
        manifest=manifest,
        statuses=statuses,
        diagnostics_by_ticker=diagnostics_by_ticker,
        universe_health=universe_health,
        receipt_id=receipt_id,
        snapshot_sha256=receipt_ref.content_sha256,
        mode="OFFLINE_REPLAY",
        requested_tickers=tickers,
        as_of_time=as_of_time,
    )
    result.seal()
    return result


def _canonical_json(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _build_receipt(
    result: ServiceResult,
    tickers: Sequence[str],
    as_of_time: datetime,
) -> Dict[str, object]:
    if as_of_time.tzinfo is None:
        raise ValueError("announcement receipt as_of_time must be timezone-aware")
    if len(tickers) != len(set(tickers)) or set(tickers) != set(result.statuses):
        raise ValueError("announcement result does not exactly cover requested universe")
    rows: Dict[str, object] = {}
    seen_evidence: set[str] = set()
    for ticker in tickers:
        facts = result.facts_by_ticker.get(ticker, [])
        diagnostics = result.diagnostics_by_ticker.get(ticker)
        status = result.statuses[ticker]
        if diagnostics is None:
            raise ValueError(f"announcement diagnostics missing for {ticker}")
        if any(
            not isinstance(fact, MetricFact)
            or fact.name != "exchange_announcement"
            or fact.status != "available"
            or fact.unit is not None
            or len(fact.evidence_ids) != 1
            for fact in facts
        ):
            raise ValueError(f"announcement facts are non-canonical for {ticker}")
        evidence_ids = sorted(fact.evidence_ids[0] for fact in facts)
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError(f"duplicate announcement evidence for {ticker}")
        if seen_evidence.intersection(evidence_ids):
            raise ValueError("announcement evidence reused across tickers")
        seen_evidence.update(evidence_ids)
        if any(evidence_id not in result.manifest for evidence_id in evidence_ids):
            raise ValueError(f"announcement fact has unresolved evidence for {ticker}")
        _validate_state(status, diagnostics, len(facts))
        rows[ticker] = {
            "status": status.value,
            "diagnostics": diagnostics.to_dict(),
            "evidence_ids": evidence_ids,
        }
    if set(result.manifest) != seen_evidence:
        raise ValueError("announcement manifest contains unreferenced evidence")
    return {
        "schema_version": 1,
        "source_mode": "LIVE_ACCEPTED",
        "requested_tickers": list(tickers),
        "as_of_time": as_of_time.isoformat(),
        "universe_health": _thaw_json(result.universe_health),
        "tickers": rows,
    }


def _diagnostics_from_dict(raw: object) -> AnnouncementDiagnostics:
    if not isinstance(raw, dict):
        raise ValueError("diagnostics must be an object")
    allowed = {
        "terminal_cause", "pages_requested", "request_attempts", "raw_items",
        "eligible_items", "future_filtered", "parse_failures", "duplicate_items",
        "total_hits", "last_error",
    }
    if set(raw) != allowed:
        raise ValueError("diagnostics fields mismatch")
    counts = [
        raw[name] for name in (
            "pages_requested", "request_attempts", "raw_items", "eligible_items",
            "future_filtered", "parse_failures", "duplicate_items",
        )
    ]
    if any(type(value) is not int or value < 0 for value in counts):
        raise ValueError("diagnostics counters must be non-negative integers")
    if raw["total_hits"] is not None and (
        type(raw["total_hits"]) is not int or raw["total_hits"] < 0
    ):
        raise ValueError("diagnostics total_hits is invalid")
    if raw["last_error"] is not None and not isinstance(raw["last_error"], str):
        raise ValueError("diagnostics last_error is invalid")
    return AnnouncementDiagnostics(
        terminal_cause=AnnouncementTerminalCause(raw["terminal_cause"]),
        pages_requested=raw["pages_requested"],
        request_attempts=raw["request_attempts"],
        raw_items=raw["raw_items"],
        eligible_items=raw["eligible_items"],
        future_filtered=raw["future_filtered"],
        parse_failures=raw["parse_failures"],
        duplicate_items=raw["duplicate_items"],
        total_hits=raw["total_hits"],
        last_error=raw["last_error"],
    )


def _validate_state(
    status: ProviderStatus,
    diagnostics: AnnouncementDiagnostics,
    fact_count: int,
) -> None:
    terminal_cause = diagnostics.terminal_cause
    if diagnostics.pages_requested < 1 or diagnostics.request_attempts < 1:
        raise ValueError("announcement state has no successful provider attempt")
    if diagnostics.request_attempts < diagnostics.pages_requested:
        raise ValueError("announcement request/page counters are inconsistent")
    if (
        diagnostics.eligible_items > diagnostics.raw_items
        or diagnostics.duplicate_items > diagnostics.eligible_items
        or diagnostics.future_filtered
        + diagnostics.parse_failures
        + diagnostics.eligible_items
        > diagnostics.raw_items
        or fact_count > diagnostics.eligible_items - diagnostics.duplicate_items
    ):
        raise ValueError("announcement item diagnostics are inconsistent")
    if diagnostics.total_hits is not None and diagnostics.total_hits < diagnostics.raw_items:
        raise ValueError("announcement total_hits is inconsistent")

    if fact_count:
        valid = (
            status == ProviderStatus.COMPLETE
            and terminal_cause == AnnouncementTerminalCause.EVENTS_FOUND
        ) or (
            status == ProviderStatus.PARTIAL
            and terminal_cause in {
                AnnouncementTerminalCause.UPSTREAM_FAILURE,
                AnnouncementTerminalCause.PARSE_FAILURE,
                AnnouncementTerminalCause.PAGINATION_LIMIT,
            }
        )
    else:
        valid = (
            status == ProviderStatus.AVAILABLE_NO_EVENT
            and terminal_cause in {
                AnnouncementTerminalCause.TRUE_NO_DATA,
                AnnouncementTerminalCause.NO_EVENT_BEFORE_AS_OF,
            }
        ) or (
            status == ProviderStatus.UNAVAILABLE
            and terminal_cause in {
                AnnouncementTerminalCause.UPSTREAM_FAILURE,
                AnnouncementTerminalCause.PARSE_FAILURE,
                AnnouncementTerminalCause.PAGINATION_LIMIT,
            }
        )
    if terminal_cause == AnnouncementTerminalCause.TRUE_NO_DATA and (
        diagnostics.raw_items != 0
        or diagnostics.eligible_items != 0
        or diagnostics.future_filtered != 0
        or diagnostics.parse_failures != 0
        or diagnostics.duplicate_items != 0
        or diagnostics.total_hits not in {None, 0}
    ):
        valid = False
    if terminal_cause == AnnouncementTerminalCause.NO_EVENT_BEFORE_AS_OF and (
        diagnostics.raw_items < 1
        or diagnostics.future_filtered < 1
        or diagnostics.eligible_items != 0
        or diagnostics.parse_failures != 0
    ):
        valid = False
    if terminal_cause == AnnouncementTerminalCause.UPSTREAM_FAILURE and not diagnostics.last_error:
        valid = False
    if terminal_cause == AnnouncementTerminalCause.PARSE_FAILURE and not (
        diagnostics.parse_failures or diagnostics.last_error
    ):
        valid = False
    if not valid:
        raise ValueError(
            "announcement status/terminal-cause/fact combination is invalid"
        )


def _freeze_json(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze_json(item) for key, item in value.items()})
    if isinstance(value, list | tuple):
        return tuple(_freeze_json(item) for item in value)
    return value


def _thaw_json(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value


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
