"""Tests for provider contract, status enums, fixtures, and base class."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

from jiuwenswarm.quant.reporting.providers.base import BaseProvider
from jiuwenswarm.quant.reporting.providers.fixtures import (
    MockProvider,
    TickerFilteredMockProvider,
    make_announcement_fact,
    make_evidence_ref,
    make_metric_fact,
)
from jiuwenswarm.quant.reporting.providers.registry import ProviderRegistry
from jiuwenswarm.quant.reporting.providers.status import ProviderCategory, ProviderStatus

UTC = timezone.utc


def _run(coro):
    """Shortcut for running async provider methods in sync tests."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# ProviderStatus
# ---------------------------------------------------------------------------

def test_status_values_match_contract() -> None:
    assert ProviderStatus.COMPLETE == "complete"
    assert ProviderStatus.PARTIAL == "partial"
    assert ProviderStatus.UNAVAILABLE == "unavailable"


def test_status_is_string_enum() -> None:
    assert isinstance(ProviderStatus.COMPLETE, str)


# ---------------------------------------------------------------------------
# ProviderCategory
# ---------------------------------------------------------------------------

def test_category_values_are_distinct() -> None:
    values = [c.value for c in ProviderCategory]
    assert len(values) == len(set(values))


def test_disclosure_category_exists() -> None:
    assert ProviderCategory.DISCLOSURE == "disclosure"


# ---------------------------------------------------------------------------
# BaseProvider validation
# ---------------------------------------------------------------------------

def test_base_provider_rejects_empty_name() -> None:
    with pytest.raises(ValueError, match="name"):
        MockProvider(name="  ")


def test_base_provider_rejects_empty_source_url() -> None:
    with pytest.raises(ValueError, match="source_url"):
        BaseProvider.__init__(
            MockProvider.__new__(MockProvider),
            name="test",
            source_url="",
        )


def test_validate_ticker_format_valid() -> None:
    p = MockProvider()
    p._validate_ticker_format("600000.SH")
    p._validate_ticker_format("000001.SZ")


def test_validate_ticker_format_invalid_code_length() -> None:
    p = MockProvider()
    with pytest.raises(ValueError, match="Invalid ticker"):
        p._validate_ticker_format("60.SH")


def test_validate_ticker_format_invalid_exchange() -> None:
    p = MockProvider()
    with pytest.raises(ValueError, match="Invalid exchange"):
        p._validate_ticker_format("600000.BJ")


def test_validate_ticker_format_no_dot() -> None:
    p = MockProvider()
    with pytest.raises(ValueError, match="Invalid ticker"):
        p._validate_ticker_format("600000")


def test_validate_as_of_time_requires_timezone() -> None:
    p = MockProvider()
    with pytest.raises(ValueError, match="timezone-aware"):
        p._validate_as_of_time(datetime(2026, 7, 30, 12, 0))


def test_validate_as_of_time_rejects_future() -> None:
    p = MockProvider()
    far_future = datetime(2099, 1, 1, tzinfo=UTC)
    with pytest.raises(ValueError, match="future"):
        p._validate_as_of_time(far_future)


# ---------------------------------------------------------------------------
# MockProvider
# ---------------------------------------------------------------------------

def test_mock_provider_returns_seeded_facts() -> None:
    provider = MockProvider()
    fact = make_metric_fact("test_metric", value=42.0, unit="percent")
    provider.seed("600000.SH", "2026-07-30", [fact])

    facts, status = _run(provider.fetch_for_ticker(
        "600000.SH", datetime(2026, 7, 30, 12, 0, tzinfo=UTC),
    ))
    assert status == ProviderStatus.COMPLETE
    assert len(facts) == 1
    assert facts[0].name == "test_metric"
    assert facts[0].value == 42.0


def test_mock_provider_returns_unavailable_for_unseeded() -> None:
    provider = MockProvider()
    facts, status = _run(provider.fetch_for_ticker(
        "000001.SZ", datetime(2026, 7, 30, tzinfo=UTC),
    ))
    assert status == ProviderStatus.UNAVAILABLE
    assert facts == []


def test_mock_provider_supports_all_tickers_by_default() -> None:
    provider = MockProvider()
    assert provider.supports_ticker("600000.SH") is True
    assert provider.supports_ticker("000001.SZ") is True
    assert provider.supports_ticker("999999.SH") is True


def test_mock_provider_tracks_fetch_count() -> None:
    provider = MockProvider()
    assert provider._fetch_count == 0
    _run(provider.fetch_for_ticker("600000.SH", datetime(2026, 7, 30, tzinfo=UTC)))
    assert provider._fetch_count == 1


def test_mock_provider_category_is_configurable() -> None:
    p = MockProvider(category=ProviderCategory.FUNDAMENTAL)
    assert p.category == ProviderCategory.FUNDAMENTAL


# ---------------------------------------------------------------------------
# TickerFilteredMockProvider
# ---------------------------------------------------------------------------

def test_filtered_provider_supports_only_listed_tickers() -> None:
    p = TickerFilteredMockProvider(supported={"600000.SH", "000001.SZ"})
    assert p.supports_ticker("600000.SH") is True
    assert p.supports_ticker("000001.SZ") is True
    assert p.supports_ticker("600036.SH") is False


# ---------------------------------------------------------------------------
# ProviderRegistry
# ---------------------------------------------------------------------------

def test_registry_register_and_list() -> None:
    reg = ProviderRegistry()
    p1 = MockProvider(name="p1")
    p2 = MockProvider(name="p2")
    reg.register(p1)
    reg.register(p2)
    assert reg.list_all() == ["p1", "p2"]


def test_registry_duplicate_rejected() -> None:
    reg = ProviderRegistry()
    reg.register(MockProvider(name="dup"))
    with pytest.raises(ValueError, match="already registered"):
        reg.register(MockProvider(name="dup"))


def test_registry_get() -> None:
    reg = ProviderRegistry()
    p = MockProvider(name="test-p")
    reg.register(p)
    assert reg.get("test-p") is p


def test_registry_get_unknown_raises() -> None:
    reg = ProviderRegistry()
    with pytest.raises(KeyError, match="not found"):
        reg.get("nonexistent")


def test_registry_find_for_ticker() -> None:
    reg = ProviderRegistry()
    p1 = TickerFilteredMockProvider({"600000.SH"}, name="p1")
    p2 = TickerFilteredMockProvider({"000001.SZ"}, name="p2")
    reg.register(p1)
    reg.register(p2)
    assert reg.find_for_ticker("600000.SH") == [p1]
    assert reg.find_for_ticker("000001.SZ") == [p2]
    assert reg.find_for_ticker("999999.SH") == []


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------

def test_make_metric_fact_defaults() -> None:
    fact = make_metric_fact("revenue", value=1.5e9, unit="CNY")
    assert fact.name == "revenue"
    assert fact.value == 1.5e9
    assert fact.unit == "CNY"
    assert fact.status == "available"
    assert fact.evidence_ids == ("test-evidence-1",)


def test_make_announcement_fact_has_unique_evidence_id() -> None:
    dt = datetime(2026, 7, 15, tzinfo=UTC)
    f1 = make_announcement_fact("公告A", dt, ticker="600000.SH")
    f2 = make_announcement_fact("公告A", dt, ticker="600000.SH")
    # Same inputs produce same evidence_id
    assert f1.evidence_ids == f2.evidence_ids
    # Different titles produce different evidence_ids
    f3 = make_announcement_fact("公告B", dt, ticker="600000.SH")
    assert f1.evidence_ids != f3.evidence_ids


def test_make_evidence_ref_has_sha256() -> None:
    ref = make_evidence_ref("ev-1", content="hello")
    assert len(ref.content_sha256) == 64
    assert ref.evidence_id == "ev-1"
    assert ref.source_type == "disclosure"


# ---------------------------------------------------------------------------
# AnnouncementProvider unit tests (no network)
# ---------------------------------------------------------------------------

def test_announcement_provider_category() -> None:
    from jiuwenswarm.quant.reporting.providers.announcement import (
        AnnouncementProvider,
    )
    p = AnnouncementProvider()
    assert p.category == ProviderCategory.DISCLOSURE


def test_announcement_provider_supports_valid_tickers() -> None:
    from jiuwenswarm.quant.reporting.providers.announcement import (
        AnnouncementProvider,
    )
    p = AnnouncementProvider()
    assert p.supports_ticker("600000.SH") is True
    assert p.supports_ticker("000001.SZ") is True


def test_announcement_provider_rejects_invalid_tickers() -> None:
    from jiuwenswarm.quant.reporting.providers.announcement import (
        AnnouncementProvider,
    )
    p = AnnouncementProvider()
    assert p.supports_ticker("BAD") is False
    assert p.supports_ticker("") is False


def test_announcement_parse_notice_date_uses_asia_shanghai() -> None:
    from jiuwenswarm.quant.reporting.providers.announcement import (
        AnnouncementProvider,
    )
    dt = AnnouncementProvider._parse_notice_date("2026-07-30")
    assert dt is not None
    assert dt.year == 2026
    assert dt.month == 7
    assert dt.day == 30
    assert dt.tzinfo is not None
    # Must be Asia/Shanghai, NOT UTC
    assert str(dt.tzinfo) == "Asia/Shanghai" or "Shanghai" in str(dt.tzinfo)
    # Conservative: end of day (23:59:59), not midnight
    assert dt.hour == 23
    assert dt.minute == 59


def test_announcement_parse_notice_date_none() -> None:
    from jiuwenswarm.quant.reporting.providers.announcement import (
        AnnouncementProvider,
    )
    assert AnnouncementProvider._parse_notice_date(None) is None
    assert AnnouncementProvider._parse_notice_date("") is None


def test_announcement_evidence_id_is_stable() -> None:
    from jiuwenswarm.quant.reporting.providers.announcement import (
        AnnouncementProvider,
    )
    ann = {"notice_date": "2026-07-30", "title": "test"}
    eid1 = AnnouncementProvider._make_evidence_id("600000", ann)
    eid2 = AnnouncementProvider._make_evidence_id("600000", dict(ann))
    assert eid1 == eid2  # deterministic
    assert eid1.startswith("ann-600000-2026-07-30-")


def test_announcement_detail_url_uses_art_code() -> None:
    """EvidenceRef source_url must be a specific detail page, not generic API."""
    from jiuwenswarm.quant.reporting.providers.announcement import (
        AnnouncementProvider,
    )
    p = AnnouncementProvider()
    ann = {
        "art_code": "AN202607271827389433",
        "codes": [{"stock_code": "600000"}],
        "notice_date": "2026-07-28",
        "title": "测试公告",
    }
    url = p._build_detail_url(ann)
    assert "AN202607271827389433" in url
    assert "600000" in url
    assert "data.eastmoney.com" in url
    assert "notices/detail" in url


def test_announcement_detail_url_fallback() -> None:
    """Without art_code, fall back to list-API URL."""
    from jiuwenswarm.quant.reporting.providers.announcement import (
        AnnouncementProvider,
    )
    p = AnnouncementProvider()
    ann: dict = {}
    url = p._build_detail_url(ann)
    # Falls back to something with the API base
    assert "np-anotice-stock" in url or "stock_list" in url


@pytest.mark.skip(reason="Real network smoke test — run manually for re-verification")
def test_announcement_fetch_rich_returns_raw_payloads() -> None:
    """fetch_rich() provides raw JSON payloads + EvidenceRefs for archiving."""
    from jiuwenswarm.quant.reporting.providers.announcement import (
        AnnouncementProvider, AnnouncementResult,
    )
    p = AnnouncementProvider()
    now = datetime.now(UTC)
    result = _run(p.fetch_rich("600000.SH", now))
    assert isinstance(result, AnnouncementResult)
    assert isinstance(result.facts, list)
    assert isinstance(result.raw_payloads, dict)
    assert isinstance(result.evidence_refs, list)
    assert result.status in (
        ProviderStatus.COMPLETE,
        ProviderStatus.AVAILABLE_NO_EVENT,
        ProviderStatus.UNAVAILABLE,
    )


def test_announcement_ava_fetch_no_events_is_distinct() -> None:
    """AVAILABLE_NO_EVENT ≠ UNAVAILABLE."""
    from jiuwenswarm.quant.reporting.providers.announcement import (
        AnnouncementPage,
        AnnouncementProvider,
        AnnouncementTerminalCause,
    )
    p = AnnouncementProvider()
    with patch.object(
        p,
        "_fetch_page",
        return_value=AnnouncementPage(items=[], total_hits=0),
    ):
        result = _run(p.fetch_rich(
            "600000.SH", datetime(2025, 4, 18, tzinfo=UTC),
        ))
    assert result.status == ProviderStatus.AVAILABLE_NO_EVENT
    assert result.diagnostics.terminal_cause == AnnouncementTerminalCause.TRUE_NO_DATA
    assert result.facts == []


def _announcement(date: str, title: str, suffix: str) -> dict:
    return {
        "art_code": f"AN{suffix}",
        "codes": [{"stock_code": "600000"}],
        "notice_date": date,
        "title": title,
    }


def test_announcement_provider_paginates_to_historical_as_of() -> None:
    from jiuwenswarm.quant.reporting.providers.announcement import (
        AnnouncementPage,
        AnnouncementProvider,
        AnnouncementTerminalCause,
    )

    provider = AnnouncementProvider(page_size=2, max_pages=4, max_retries=0)
    pages = {
        1: AnnouncementPage(
            items=[
                _announcement("2026-07-30", "future-1", "001"),
                _announcement("2026-07-29", "future-2", "002"),
            ],
            total_hits=6,
        ),
        2: AnnouncementPage(
            items=[
                _announcement("2026-01-01", "future-3", "003"),
                _announcement("2025-04-17", "eligible-1", "004"),
            ],
            total_hits=6,
        ),
        3: AnnouncementPage(
            items=[
                _announcement("2025-04-16", "eligible-2", "005"),
                _announcement("2025-04-15", "eligible-3", "006"),
            ],
            total_hits=6,
        ),
    }
    requested_pages = []

    def fake_page(_code: str, page_index: int, end_date: str):
        requested_pages.append((page_index, end_date))
        return pages[page_index]

    as_of = datetime(2025, 4, 18, 16, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    with patch.object(provider, "_fetch_page", side_effect=fake_page):
        result = _run(provider.fetch_rich("600000.SH", as_of))

    assert requested_pages == [
        (1, "2025-04-18"),
        (2, "2025-04-18"),
        (3, "2025-04-18"),
    ]
    assert [fact.value for fact in result.facts] == ["eligible-1", "eligible-2"]
    assert result.status == ProviderStatus.COMPLETE
    assert result.diagnostics.terminal_cause == AnnouncementTerminalCause.EVENTS_FOUND
    assert result.diagnostics.pages_requested == 3
    assert result.diagnostics.future_filtered == 3
    assert result.diagnostics.eligible_items == 3
    assert all(ref.available_at <= as_of for ref in result.evidence_refs)


def test_announcement_provider_distinguishes_no_event_before_as_of() -> None:
    from jiuwenswarm.quant.reporting.providers.announcement import (
        AnnouncementPage,
        AnnouncementProvider,
        AnnouncementTerminalCause,
    )

    provider = AnnouncementProvider(page_size=2, max_pages=2, max_retries=0)
    page = AnnouncementPage(
        items=[
            _announcement("2026-07-30", "future-1", "101"),
            _announcement("2026-07-29", "future-2", "102"),
        ],
        total_hits=2,
    )
    with patch.object(provider, "_fetch_page", return_value=page):
        result = _run(provider.fetch_rich(
            "600000.SH", datetime(2025, 4, 18, tzinfo=UTC),
        ))

    assert result.status == ProviderStatus.AVAILABLE_NO_EVENT
    assert (
        result.diagnostics.terminal_cause
        == AnnouncementTerminalCause.NO_EVENT_BEFORE_AS_OF
    )
    assert result.diagnostics.future_filtered == 2


def test_announcement_provider_reports_upstream_failure() -> None:
    from jiuwenswarm.quant.reporting.providers.announcement import (
        AnnouncementProvider,
        AnnouncementTerminalCause,
    )

    provider = AnnouncementProvider(max_retries=0)
    with patch.object(provider, "_fetch_page", side_effect=TimeoutError("timeout")):
        result = _run(provider.fetch_rich(
            "600000.SH", datetime(2025, 4, 18, tzinfo=UTC),
        ))

    assert result.status == ProviderStatus.UNAVAILABLE
    assert result.diagnostics.terminal_cause == AnnouncementTerminalCause.UPSTREAM_FAILURE
    assert result.diagnostics.last_error == "TimeoutError: timeout"


def test_announcement_provider_reports_parse_failure() -> None:
    from jiuwenswarm.quant.reporting.providers.announcement import (
        AnnouncementPage,
        AnnouncementProvider,
        AnnouncementTerminalCause,
    )

    provider = AnnouncementProvider(page_size=2, max_pages=1, max_retries=0)
    page = AnnouncementPage(
        items=[
            _announcement("not-a-date", "bad-date", "201"),
            _announcement("2025-04-17", "", "202"),
        ],
        total_hits=2,
    )
    with patch.object(provider, "_fetch_page", return_value=page):
        result = _run(provider.fetch_rich(
            "600000.SH", datetime(2025, 4, 18, tzinfo=UTC),
        ))

    assert result.status == ProviderStatus.UNAVAILABLE
    assert result.diagnostics.terminal_cause == AnnouncementTerminalCause.PARSE_FAILURE
    assert result.diagnostics.parse_failures == 2


def test_announcement_provider_fails_closed_at_page_cap() -> None:
    from jiuwenswarm.quant.reporting.providers.announcement import (
        AnnouncementPage,
        AnnouncementProvider,
        AnnouncementTerminalCause,
    )

    provider = AnnouncementProvider(page_size=2, max_pages=1, max_retries=0)
    page = AnnouncementPage(
        items=[
            _announcement("2026-07-30", "future-1", "301"),
            _announcement("2026-07-29", "future-2", "302"),
        ],
        total_hits=120,
    )
    with patch.object(provider, "_fetch_page", return_value=page):
        result = _run(provider.fetch_rich(
            "600000.SH", datetime(2025, 4, 18, tzinfo=UTC),
        ))

    assert result.status == ProviderStatus.UNAVAILABLE
    assert result.diagnostics.terminal_cause == AnnouncementTerminalCause.PAGINATION_LIMIT
    assert result.diagnostics.pages_requested == 1


def test_announcement_provider_fails_closed_on_premature_empty_page() -> None:
    from jiuwenswarm.quant.reporting.providers.announcement import (
        AnnouncementPage,
        AnnouncementProvider,
        AnnouncementTerminalCause,
    )

    provider = AnnouncementProvider(page_size=2, max_pages=2, max_retries=0)
    with patch.object(
        provider,
        "_fetch_page",
        return_value=AnnouncementPage(items=[], total_hits=3),
    ):
        result = _run(provider.fetch_rich(
            "600000.SH", datetime(2025, 4, 18, tzinfo=UTC),
        ))

    assert result.status == ProviderStatus.UNAVAILABLE
    assert (
        result.diagnostics.terminal_cause
        == AnnouncementTerminalCause.PARSE_FAILURE
    )


def test_announcement_provider_fails_closed_on_missing_final_partial_page() -> None:
    from jiuwenswarm.quant.reporting.providers.announcement import (
        AnnouncementPage,
        AnnouncementProvider,
        AnnouncementTerminalCause,
    )

    provider = AnnouncementProvider(page_size=2, max_pages=3, max_retries=0)
    pages = {
        1: AnnouncementPage(
            items=[
                _announcement("2026-07-30", "future-1", "351"),
                _announcement("2026-07-29", "future-2", "352"),
            ],
            total_hits=3,
        ),
        2: AnnouncementPage(items=[], total_hits=3),
    }
    with patch.object(
        provider,
        "_fetch_page",
        side_effect=lambda _code, page_index, _end_date: pages[page_index],
    ):
        result = _run(provider.fetch_rich(
            "600000.SH", datetime(2025, 4, 18, tzinfo=UTC),
        ))

    assert result.status == ProviderStatus.UNAVAILABLE
    assert (
        result.diagnostics.terminal_cause
        == AnnouncementTerminalCause.PARSE_FAILURE
    )


def test_announcement_provider_fails_closed_when_total_hits_changes() -> None:
    from jiuwenswarm.quant.reporting.providers.announcement import (
        AnnouncementPage,
        AnnouncementProvider,
        AnnouncementTerminalCause,
    )

    provider = AnnouncementProvider(page_size=2, max_pages=3, max_retries=0)
    pages = {
        1: AnnouncementPage(
            items=[
                _announcement("2026-07-30", "future-1", "361"),
                _announcement("2026-07-29", "future-2", "362"),
            ],
            total_hits=3,
        ),
        2: AnnouncementPage(items=[], total_hits=2),
    }
    with patch.object(
        provider,
        "_fetch_page",
        side_effect=lambda _code, page_index, _end_date: pages[page_index],
    ):
        result = _run(provider.fetch_rich(
            "600000.SH", datetime(2025, 4, 18, tzinfo=UTC),
        ))

    assert result.status == ProviderStatus.UNAVAILABLE
    assert (
        result.diagnostics.terminal_cause
        == AnnouncementTerminalCause.PARSE_FAILURE
    )
    assert result.diagnostics.total_hits == 3


def test_announcement_provider_classifies_malformed_payload_as_parse_failure() -> None:
    from jiuwenswarm.quant.reporting.providers.announcement import (
        AnnouncementProvider,
        AnnouncementTerminalCause,
    )

    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"data": None}

    provider = AnnouncementProvider(max_retries=0)
    with patch(
        "jiuwenswarm.quant.reporting.providers.announcement.requests.get",
        return_value=Response(),
    ):
        result = _run(provider.fetch_rich(
            "600000.SH", datetime(2025, 4, 18, tzinfo=UTC),
        ))

    assert result.status == ProviderStatus.UNAVAILABLE
    assert (
        result.diagnostics.terminal_cause
        == AnnouncementTerminalCause.PARSE_FAILURE
    )
    assert result.diagnostics.last_error is not None


def test_announcement_provider_contains_malformed_scalar_items() -> None:
    from jiuwenswarm.quant.reporting.providers.announcement import (
        AnnouncementPage,
        AnnouncementProvider,
        AnnouncementTerminalCause,
    )

    provider = AnnouncementProvider(page_size=3, max_pages=1, max_retries=0)
    page = AnnouncementPage(
        items=[
            {"notice_date": 20250417, "title": "bad-date-type"},
            {"notice_date": "2025-04-17", "title": 123},
            {
                "art_code": 401,
                "codes": [{"stock_code": 600000}],
                "notice_date": "2025-04-17",
                "title": "usable-event",
            },
        ],
        total_hits=3,
    )
    with patch.object(provider, "_fetch_page", return_value=page):
        result = _run(provider.fetch_rich(
            "600000.SH", datetime(2025, 4, 18, tzinfo=UTC),
        ))

    assert result.status == ProviderStatus.PARTIAL
    assert (
        result.diagnostics.terminal_cause
        == AnnouncementTerminalCause.PARSE_FAILURE
    )
    assert result.diagnostics.parse_failures == 2
    assert [fact.value for fact in result.facts] == ["usable-event"]


def test_announcement_provider_deduplicates_stable_art_code() -> None:
    from jiuwenswarm.quant.reporting.providers.announcement import (
        AnnouncementPage,
        AnnouncementProvider,
    )

    provider = AnnouncementProvider(page_size=3, max_pages=1, max_retries=0)
    duplicate = _announcement("2025-04-17", "same-event", "401")
    duplicate_variant = {
        **duplicate,
        "metadata_added_later": "must-not-create-a-second-event",
    }
    page = AnnouncementPage(
        items=[
            duplicate,
            duplicate_variant,
            _announcement("2025-04-16", "other-event", "402"),
        ],
        total_hits=3,
    )
    with patch.object(provider, "_fetch_page", return_value=page):
        result = _run(provider.fetch_rich(
            "600000.SH", datetime(2025, 4, 18, tzinfo=UTC),
        ))

    assert [fact.value for fact in result.facts] == ["same-event", "other-event"]
    assert result.diagnostics.duplicate_items == 1


def test_announcement_fetch_page_sends_historical_end_time() -> None:
    from jiuwenswarm.quant.reporting.providers.announcement import (
        ANNOUNCEMENT_API,
        AnnouncementProvider,
    )

    captured = {}

    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"data": {"list": [], "total_hits": 0}}

    def fake_get(url, *, params, timeout):
        captured.update({"url": url, "params": params, "timeout": timeout})
        return Response()

    provider = AnnouncementProvider(timeout=7.5)
    with patch(
        "jiuwenswarm.quant.reporting.providers.announcement.requests.get",
        side_effect=fake_get,
    ):
        page = provider._fetch_page("600000", 3, "2025-04-18")

    assert page.items == []
    assert page.total_hits == 0
    assert captured["url"] == ANNOUNCEMENT_API
    assert captured["params"]["page_index"] == "3"
    assert captured["params"]["end_time"] == "2025-04-18"
    assert captured["timeout"] == 7.5
