"""Fixture tests for AnnouncementService — no network calls."""

from __future__ import annotations

import asyncio
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from jiuwenswarm.quant.reporting.announcement_service import (
    AnnouncementService,
    AnnouncementUniverseHealthError,
    ServiceResult,
    run_announcement_service,
)
from jiuwenswarm.quant.reporting.providers.announcement import (
    AnnouncementDiagnostics,
    AnnouncementPage,
    AnnouncementProvider,
    AnnouncementResult,
    AnnouncementTerminalCause,
)
from jiuwenswarm.quant.reporting.providers.archive import EvidenceArchive
from jiuwenswarm.quant.reporting.providers.status import ProviderStatus

UTC = timezone.utc


# ---------------------------------------------------------------------------
# Mock data
# ---------------------------------------------------------------------------

MOCK_ANNOUNCEMENTS = [
    {
        "art_code": "AN202607271827380001",
        "codes": [{"stock_code": "600000"}],
        "notice_date": "2026-07-27",
        "title": "测试公告1：股东大会通知",
    },
    {
        "art_code": "AN202607281827380002",
        "codes": [{"stock_code": "600000"}],
        "notice_date": "2026-07-28",
        "title": "测试公告2：业绩预告",
    },
]

MOCK_EMPTY: list = []


def _empty_result() -> AnnouncementResult:
    return AnnouncementResult(
        status=ProviderStatus.AVAILABLE_NO_EVENT,
        diagnostics=AnnouncementDiagnostics(
            terminal_cause=AnnouncementTerminalCause.TRUE_NO_DATA,
            pages_requested=1,
            request_attempts=1,
            total_hits=0,
        ),
    )


class _StaticProvider:
    def __init__(self, *, event_ticker: str | None = None):
        self.event_ticker = event_ticker
        self.calls: list[str] = []

    async def fetch_rich(self, ticker: str, as_of_time: datetime):
        self.calls.append(ticker)
        if ticker != self.event_ticker:
            return _empty_result()
        fact = SimpleNamespace(evidence_ids=())
        return AnnouncementResult(
            facts=[fact],
            status=ProviderStatus.COMPLETE,
            diagnostics=AnnouncementDiagnostics(
                terminal_cause=AnnouncementTerminalCause.EVENTS_FOUND,
                pages_requested=1,
                request_attempts=1,
                raw_items=1,
                eligible_items=1,
                total_hits=1,
            ),
        )


def _page(items: list, total_hits: int | None = None) -> AnnouncementPage:
    return AnnouncementPage(
        items=items,
        total_hits=len(items) if total_hits is None else total_hits,
    )


def _make_patch_target():
    return (
        "jiuwenswarm.quant.reporting.providers.announcement"
        ".AnnouncementProvider._fetch_page"
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAnnouncementServiceFixture:
    """Tests using mocked _fetch_page — no network."""

    def test_run_populates_facts_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            archive = EvidenceArchive(Path(tmp))
            provider = AnnouncementProvider()
            svc = AnnouncementService(provider, archive)
            now = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)

            with patch(_make_patch_target(), return_value=_page(MOCK_ANNOUNCEMENTS)):
                result = asyncio.run(svc.run(["600000.SH"], now))

            assert isinstance(result, ServiceResult)
            assert len(result.facts_by_ticker["600000.SH"]) == 2
            assert result.statuses["600000.SH"] == ProviderStatus.COMPLETE
            assert result.total_facts == 2
            assert len(result.manifest) == 2
            assert (
                result.diagnostics_by_ticker["600000.SH"].terminal_cause
                == AnnouncementTerminalCause.EVENTS_FOUND
            )
            assert result.terminal_cause_counts == {"events_found": 1}
            # Verify archive has the files
            for eid in result.manifest:
                assert archive.exists(eid)

    def test_run_filters_by_pit(self) -> None:
        """Facts with notice_date > as_of_time are excluded."""
        with tempfile.TemporaryDirectory() as tmp:
            archive = EvidenceArchive(Path(tmp))
            provider = AnnouncementProvider()
            svc = AnnouncementService(provider, archive)
            # Set as_of_time before both announcements
            past = datetime(2026, 7, 26, 12, 0, tzinfo=UTC)

            with patch(_make_patch_target(), return_value=_page(MOCK_ANNOUNCEMENTS)):
                result = asyncio.run(svc.run(["600000.SH"], past))

            # Both announcements are dated 7/27 and 7/28, past is 7/26
            assert result.total_facts == 0
            assert result.statuses["600000.SH"] == ProviderStatus.AVAILABLE_NO_EVENT
            assert len(result.manifest) == 0
            assert (
                result.diagnostics_by_ticker["600000.SH"].terminal_cause
                == AnnouncementTerminalCause.NO_EVENT_BEFORE_AS_OF
            )

    def test_run_empty_response_is_no_event(self) -> None:
        """Empty API response → AVAILABLE_NO_EVENT."""
        with tempfile.TemporaryDirectory() as tmp:
            archive = EvidenceArchive(Path(tmp))
            provider = AnnouncementProvider()
            svc = AnnouncementService(provider, archive)
            now = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)

            with patch(_make_patch_target(), return_value=_page(MOCK_EMPTY, 0)):
                result = asyncio.run(svc.run(["600000.SH"], now))

            assert result.total_facts == 0
            assert result.statuses["600000.SH"] == ProviderStatus.AVAILABLE_NO_EVENT
            assert result.tickers_with_events == 0
            assert (
                result.diagnostics_by_ticker["600000.SH"].terminal_cause
                == AnnouncementTerminalCause.TRUE_NO_DATA
            )

    def test_run_multiple_tickers(self) -> None:
        """Two tickers, both with facts."""
        with tempfile.TemporaryDirectory() as tmp:
            archive = EvidenceArchive(Path(tmp))
            provider = AnnouncementProvider()
            svc = AnnouncementService(provider, archive)
            now = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)

            with patch(_make_patch_target(), return_value=_page(MOCK_ANNOUNCEMENTS)):
                result = asyncio.run(
                    svc.run(["600000.SH", "000001.SZ"], now),
                )

            assert result.total_facts == 4  # 2 per ticker
            assert len(result.manifest) == 4
            assert result.tickers_with_events == 2
            for ticker in ("600000.SH", "000001.SZ"):
                assert result.statuses[ticker] == ProviderStatus.COMPLETE

    def test_sync_wrapper(self) -> None:
        """run_announcement_service() sync wrapper works."""
        with tempfile.TemporaryDirectory() as tmp:
            with patch(_make_patch_target(), return_value=_page(MOCK_ANNOUNCEMENTS)):
                result = run_announcement_service(
                    ["600000.SH"],
                    datetime(2026, 7, 30, 12, 0, tzinfo=UTC),
                    Path(tmp),
                )
            assert result.total_facts == 2
            assert len(result.manifest) == 2

    def test_evidence_ref_urls_are_detail_pages(self) -> None:
        """Every EvidenceRef source_url is a specific detail page."""
        with tempfile.TemporaryDirectory() as tmp:
            archive = EvidenceArchive(Path(tmp))
            provider = AnnouncementProvider()
            svc = AnnouncementService(provider, archive)
            now = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)

            with patch(_make_patch_target(), return_value=_page(MOCK_ANNOUNCEMENTS)):
                result = asyncio.run(svc.run(["600000.SH"], now))

            for eid, ref in result.manifest.items():
                assert "data.eastmoney.com" in ref.source_url, (
                    f"Expected detail URL, got: {ref.source_url}"
                )
                assert "notices/detail" in ref.source_url

    def test_archive_written_content_matches_raw_payload(self) -> None:
        """Archived content is the raw JSON from the API."""
        with tempfile.TemporaryDirectory() as tmp:
            archive = EvidenceArchive(Path(tmp))
            provider = AnnouncementProvider()
            svc = AnnouncementService(provider, archive)
            now = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)

            with patch(_make_patch_target(), return_value=_page(MOCK_ANNOUNCEMENTS)):
                result = asyncio.run(svc.run(["600000.SH"], now))

            for eid in result.manifest:
                content = archive.read(eid)
                assert content is not None
                # Should be valid JSON matching the original announcement
                parsed = json.loads(content)
                assert "art_code" in parsed
                assert "title" in parsed

    def test_required_universe_all_empty_retries_with_fresh_provider(self) -> None:
        tickers = [f"{index:06d}.SH" for index in range(49)]
        primary = _StaticProvider()
        retry = _StaticProvider(event_ticker=tickers[0])
        with tempfile.TemporaryDirectory() as tmp:
            service = AnnouncementService(
                primary,
                EvidenceArchive(Path(tmp)),
                retry_provider_factory=lambda: retry,
            )
            result = asyncio.run(
                service.run(
                    tickers,
                    datetime(2026, 7, 30, 12, 0, tzinfo=UTC),
                    required_universe=tickers,
                )
            )

        assert result.total_facts == 1
        assert primary.calls == tickers
        assert retry.calls == tickers
        assert result.universe_health["healthy"] is True
        assert result.universe_health["recovered_after_retry"] is True
        assert len(result.universe_health["attempts"]) == 2
        assert result.universe_health["attempts"][0]["all_empty"] is True
        assert result.universe_health["attempts"][1]["all_empty"] is False

    def test_required_universe_repeated_all_empty_fails_closed(self) -> None:
        tickers = [f"{index:06d}.SH" for index in range(49)]
        with tempfile.TemporaryDirectory() as tmp:
            service = AnnouncementService(
                _StaticProvider(),
                EvidenceArchive(Path(tmp)),
                retry_provider_factory=_StaticProvider,
            )
            with pytest.raises(AnnouncementUniverseHealthError) as caught:
                asyncio.run(
                    service.run(
                        tickers,
                        datetime(2026, 7, 30, 12, 0, tzinfo=UTC),
                        required_universe=tickers,
                    )
                )

        diagnostics = caught.value.diagnostics
        assert diagnostics["healthy"] is False
        assert diagnostics["terminal_cause"] == "required_universe_all_empty"
        assert len(diagnostics["attempts"]) == 2
        assert all(attempt["terminal_cause_counts"] == {"true_no_data": 49}
                   for attempt in diagnostics["attempts"])
        assert len(diagnostics["attempts"][0]["diagnostics_by_ticker"]) == 49

    def test_required_universe_must_match_exact_ticker_set(self) -> None:
        required = [f"{index:06d}.SH" for index in range(49)]
        with tempfile.TemporaryDirectory() as tmp:
            service = AnnouncementService(
                _StaticProvider(),
                EvidenceArchive(Path(tmp)),
                retry_provider_factory=_StaticProvider,
            )
            with pytest.raises(ValueError, match="required announcement universe"):
                asyncio.run(
                    service.run(
                        required[:-1],
                        datetime(2026, 7, 30, 12, 0, tzinfo=UTC),
                        required_universe=required,
                    )
                )
