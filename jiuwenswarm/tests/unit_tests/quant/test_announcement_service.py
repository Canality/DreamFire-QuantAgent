"""Fixture tests for AnnouncementService — no network calls."""

from __future__ import annotations

import asyncio
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from jiuwenswarm.quant.reporting.announcement_service import (
    AnnouncementService,
    ServiceResult,
    run_announcement_service,
)
from jiuwenswarm.quant.reporting.providers.announcement import (
    AnnouncementPage,
    AnnouncementProvider,
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
