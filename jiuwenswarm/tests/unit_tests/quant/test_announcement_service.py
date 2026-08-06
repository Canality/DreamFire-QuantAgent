"""Fixture tests for AnnouncementService — no network calls."""

from __future__ import annotations

import asyncio
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from jiuwenswarm.quant.reporting.announcement_service import (
    AnnouncementService,
    AnnouncementUniverseHealthError,
    ServiceResult,
    announcement_snapshot_projection,
    replay_announcement_service,
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
from jiuwenswarm.quant.reporting.models import MetricFact

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
        code = ticker.split(".")[0]
        announcement = {
            "art_code": f"AN-{code}",
            "codes": [{"stock_code": code}],
            "notice_date": "2026-07-29",
            "title": "fresh retry event",
        }
        raw = json.dumps(announcement, sort_keys=True, ensure_ascii=False)
        evidence_id = AnnouncementProvider._make_evidence_id(code, announcement)
        provider = AnnouncementProvider()
        ref = provider._build_evidence_ref(
            ticker,
            announcement,
            evidence_id,
            as_of_time,
        )
        fact = MetricFact(
            name="exchange_announcement",
            value="fresh retry event",
            unit=None,
            status="available",
            evidence_ids=(evidence_id,),
        )
        return AnnouncementResult(
            facts=[fact],
            status=ProviderStatus.COMPLETE,
            raw_payloads={evidence_id: raw},
            evidence_refs=[ref],
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


def _owned_page(code: str, *_args) -> AnnouncementPage:
    items = json.loads(json.dumps(MOCK_ANNOUNCEMENTS))
    for item in items:
        item["codes"] = [{"stock_code": code}]
    return _page(items)


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

            with patch(_make_patch_target(), side_effect=_owned_page):
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

    def test_receipt_replays_same_snapshot_without_network(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            archive_root = Path(tmp)
            archive = EvidenceArchive(archive_root)
            service = AnnouncementService(AnnouncementProvider(), archive)
            now = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)
            tickers = ["600000.SH", "000001.SZ"]
            with patch(_make_patch_target(), return_value=_page(MOCK_ANNOUNCEMENTS)):
                live = asyncio.run(service.run(tickers, now))

            with patch(_make_patch_target(), side_effect=AssertionError("network used")):
                replay = replay_announcement_service(
                    archive_root,
                    live.receipt_id,
                    expected_tickers=tickers,
                    expected_as_of_time=now,
                )

            assert live.mode == "LIVE_ACCEPTED"
            assert replay.mode == "OFFLINE_REPLAY"
            assert replay.snapshot_sha256 == live.snapshot_sha256
            assert replay.statuses == live.statuses
            assert replay.facts_by_ticker == live.facts_by_ticker
            assert announcement_snapshot_projection(replay)["receipt_id"] == live.receipt_id

    def test_replay_fails_closed_on_missing_tampered_future_or_mismatch(self) -> None:
        now = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)
        with tempfile.TemporaryDirectory() as tmp:
            archive_root = Path(tmp)
            archive = EvidenceArchive(archive_root)
            with patch(_make_patch_target(), return_value=_page(MOCK_ANNOUNCEMENTS)):
                live = asyncio.run(
                    AnnouncementService(AnnouncementProvider(), archive).run(
                        ["600000.SH"], now
                    )
                )
            assert live.receipt_id is not None
            with pytest.raises(ValueError, match="universe mismatch"):
                replay_announcement_service(
                    archive_root,
                    live.receipt_id,
                    expected_tickers=["000001.SZ"],
                )
            with pytest.raises(ValueError, match="as_of_time mismatch"):
                replay_announcement_service(
                    archive_root,
                    live.receipt_id,
                    expected_as_of_time=datetime(2026, 7, 29, 12, 0, tzinfo=UTC),
                )

            evidence_id = next(iter(live.manifest))
            evidence_path = archive_root / evidence_id[:2] / f"{evidence_id}.json"
            evidence_path.write_text("{}", encoding="utf-8")
            with pytest.raises(ValueError, match="missing or tampered"):
                replay_announcement_service(archive_root, live.receipt_id)

        future = datetime(2026, 7, 26, 12, 0, tzinfo=UTC)
        with tempfile.TemporaryDirectory() as tmp:
            archive_root = Path(tmp)
            archive = EvidenceArchive(archive_root)
            with patch(_make_patch_target(), return_value=_page(MOCK_ANNOUNCEMENTS)):
                empty_live = asyncio.run(
                    AnnouncementService(AnnouncementProvider(), archive).run(
                        ["600000.SH"], future
                    )
                )
            assert empty_live.statuses["600000.SH"] == ProviderStatus.AVAILABLE_NO_EVENT
            assert replay_announcement_service(
                archive_root, empty_live.receipt_id
            ).facts_by_ticker["600000.SH"] == ()

    def test_archived_fact_rejects_future_availability(self) -> None:
        provider = AnnouncementProvider()
        announcement = MOCK_ANNOUNCEMENTS[0]
        raw = json.dumps(announcement, sort_keys=True, ensure_ascii=False)
        evidence_id = provider._make_evidence_id("600000", announcement)
        ref = provider._build_evidence_ref(
            "600000.SH",
            announcement,
            evidence_id,
            datetime(2026, 7, 28, 12, 0, tzinfo=UTC),
        )
        with pytest.raises(ValueError, match="future evidence"):
            provider.replay_archived_fact(
                "600000.SH",
                raw,
                ref,
                datetime(2026, 7, 26, 12, 0, tzinfo=UTC),
            )

    def test_cross_ticker_payload_never_becomes_a_fact(self) -> None:
        now = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)
        with tempfile.TemporaryDirectory() as tmp:
            archive_root = Path(tmp)
            with patch(_make_patch_target(), return_value=_page(MOCK_ANNOUNCEMENTS)):
                live = asyncio.run(
                    AnnouncementService(
                        AnnouncementProvider(), EvidenceArchive(archive_root)
                    ).run(["000001.SZ"], now)
                )
            assert live.facts_by_ticker["000001.SZ"] == ()
            assert live.statuses["000001.SZ"] == ProviderStatus.UNAVAILABLE
            replay = replay_announcement_service(archive_root, live.receipt_id)
            assert replay.facts_by_ticker["000001.SZ"] == ()
            assert replay.statuses["000001.SZ"] == ProviderStatus.UNAVAILABLE

    def test_accepted_result_is_deeply_immutable(self) -> None:
        now = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)
        with tempfile.TemporaryDirectory() as tmp:
            with patch(_make_patch_target(), return_value=_page(MOCK_ANNOUNCEMENTS)):
                result = asyncio.run(
                    AnnouncementService(
                        AnnouncementProvider(), EvidenceArchive(Path(tmp))
                    ).run(["600000.SH"], now)
                )
            before = announcement_snapshot_projection(result)
            with pytest.raises(TypeError):
                result.statuses["600000.SH"] = ProviderStatus.UNAVAILABLE
            with pytest.raises(TypeError):
                result.facts_by_ticker["600000.SH"] = ()
            with pytest.raises(TypeError):
                result.universe_health["healthy"] = False
            with pytest.raises(TypeError):
                result.universe_health["attempts"][0]["all_empty"] = True
            with pytest.raises(AttributeError):
                result.requested_tickers = ("000001.SZ",)
            assert announcement_snapshot_projection(result) == before

    def test_zero_request_no_event_is_rejected(self) -> None:
        class _ZeroCallProvider:
            async def fetch_rich(self, _ticker: str, _as_of_time: datetime):
                return AnnouncementResult(
                    status=ProviderStatus.AVAILABLE_NO_EVENT,
                    diagnostics=AnnouncementDiagnostics(
                        terminal_cause=AnnouncementTerminalCause.TRUE_NO_DATA
                    ),
                )

        with tempfile.TemporaryDirectory() as tmp:
            with pytest.raises(ValueError, match="no successful provider attempt"):
                asyncio.run(
                    AnnouncementService(
                        _ZeroCallProvider(), EvidenceArchive(Path(tmp))
                    ).run(
                        ["600000.SH"],
                        datetime(2026, 7, 30, 12, 0, tzinfo=UTC),
                    )
                )

    def test_missing_receipt_cannot_be_accepted_by_idempotent_rerun(self) -> None:
        now = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)
        with tempfile.TemporaryDirectory() as tmp:
            archive_root = Path(tmp)
            service = AnnouncementService(
                AnnouncementProvider(), EvidenceArchive(archive_root)
            )
            with patch(_make_patch_target(), return_value=_page(MOCK_ANNOUNCEMENTS)):
                first = asyncio.run(service.run(["600000.SH"], now))
            receipt_path = (
                archive_root / first.receipt_id[:2] / f"{first.receipt_id}.json"
            )
            receipt_path.unlink()
            second_service = AnnouncementService(
                AnnouncementProvider(), EvidenceArchive(archive_root)
            )
            with patch(_make_patch_target(), return_value=_page(MOCK_ANNOUNCEMENTS)):
                with pytest.raises(ValueError, match="missing or corrupted"):
                    asyncio.run(second_service.run(["600000.SH"], now))

    def test_live_fact_must_equal_archived_payload_reconstruction(self) -> None:
        now = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)

        class _ForgedFactProvider:
            async def fetch_rich(self, ticker: str, as_of_time: datetime):
                announcement = {
                    "art_code": "AN-CANONICAL",
                    "codes": [{"stock_code": "600000"}],
                    "notice_date": "2026-07-29",
                    "title": "archived canonical title",
                }
                raw = json.dumps(announcement, sort_keys=True, ensure_ascii=False)
                evidence_id = AnnouncementProvider._make_evidence_id(
                    "600000", announcement
                )
                ref = AnnouncementProvider()._build_evidence_ref(
                    ticker, announcement, evidence_id, as_of_time
                )
                return AnnouncementResult(
                    facts=[MetricFact(
                        name="exchange_announcement",
                        value="LIVE FORGED TITLE",
                        unit=None,
                        status="available",
                        evidence_ids=(evidence_id,),
                    )],
                    status=ProviderStatus.COMPLETE,
                    raw_payloads={evidence_id: raw},
                    evidence_refs=[ref],
                    diagnostics=AnnouncementDiagnostics(
                        terminal_cause=AnnouncementTerminalCause.EVENTS_FOUND,
                        pages_requested=1,
                        request_attempts=1,
                        raw_items=1,
                        eligible_items=1,
                        total_hits=1,
                    ),
                )

        with tempfile.TemporaryDirectory() as tmp:
            with pytest.raises(ValueError, match="differs from archived payload"):
                asyncio.run(
                    AnnouncementService(
                        _ForgedFactProvider(), EvidenceArchive(Path(tmp))
                    ).run(["600000.SH"], now)
                )

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
