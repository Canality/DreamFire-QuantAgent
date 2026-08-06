"""Point-in-time exchange announcement provider via Eastmoney API.

Fetches structured announcements for A-share tickers and returns them as
``MetricFact`` instances with PIT filtering (only announcements published
on or before *as_of_time* are visible).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Tuple

import requests
from zoneinfo import ZoneInfo

from jiuwenswarm.quant.reporting.models import EvidenceRef, MetricFact
from jiuwenswarm.quant.reporting.providers.base import BaseProvider
from jiuwenswarm.quant.reporting.providers.status import ProviderCategory, ProviderStatus

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ANNOUNCEMENT_API = (
    "https://np-anotice-stock.eastmoney.com/api/security/ann"
)
DEFAULT_PAGE_SIZE = 30
DEFAULT_MAX_PAGES = 12
REQUEST_TIMEOUT = 15.0
ASIA_SH = ZoneInfo("Asia/Shanghai")

# Conservative: an announcement dated "2026-07-30" may not become publicly
# visible until market close (15:00 CST).  We default available_at to
# 23:59:59 CST on the notice date.
_CONSERVATIVE_HOUR = 23
_CONSERVATIVE_MINUTE = 59
_CONSERVATIVE_SECOND = 59


# ---------------------------------------------------------------------------
# Rich return type
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AnnouncementPage:
    """One validated page from the upstream announcement API."""

    items: List[Dict] = field(default_factory=list)
    total_hits: Optional[int] = None


class _AnnouncementPayloadError(ValueError):
    """Upstream responded, but its payload violated the page contract."""


class AnnouncementTerminalCause(str, Enum):
    """Machine-readable reason why a ticker fetch stopped."""

    EVENTS_FOUND = "events_found"
    TRUE_NO_DATA = "true_no_data"
    NO_EVENT_BEFORE_AS_OF = "no_event_before_as_of"
    UPSTREAM_FAILURE = "upstream_failure"
    PARSE_FAILURE = "parse_failure"
    PAGINATION_LIMIT = "pagination_limit"


@dataclass(frozen=True)
class AnnouncementDiagnostics:
    """Bounded fetch accounting used to distinguish zero-evidence causes."""

    terminal_cause: AnnouncementTerminalCause = AnnouncementTerminalCause.TRUE_NO_DATA
    pages_requested: int = 0
    request_attempts: int = 0
    raw_items: int = 0
    eligible_items: int = 0
    future_filtered: int = 0
    parse_failures: int = 0
    duplicate_items: int = 0
    total_hits: Optional[int] = None
    last_error: Optional[str] = None

    def to_dict(self) -> Dict[str, object]:
        return {
            "terminal_cause": self.terminal_cause.value,
            "pages_requested": self.pages_requested,
            "request_attempts": self.request_attempts,
            "raw_items": self.raw_items,
            "eligible_items": self.eligible_items,
            "future_filtered": self.future_filtered,
            "parse_failures": self.parse_failures,
            "duplicate_items": self.duplicate_items,
            "total_hits": self.total_hits,
            "last_error": self.last_error,
        }


@dataclass(frozen=True)
class AnnouncementResult:
    """Full result from a single ``fetch_for_ticker`` call.

    Callers can archive raw responses and build EvidenceRefs in one pass.
    """

    facts: List[MetricFact] = field(default_factory=list)
    status: ProviderStatus = ProviderStatus.AVAILABLE_NO_EVENT
    raw_payloads: Dict[str, str] = field(default_factory=dict)
    """evidence_id → raw JSON string (for one-shot archiving)."""

    evidence_refs: List[EvidenceRef] = field(default_factory=list)
    """One EvidenceRef per fact, built with conservative available_at."""

    diagnostics: AnnouncementDiagnostics = field(default_factory=AnnouncementDiagnostics)
    """Fetch, filter, parse, and terminal-cause accounting."""


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------


class AnnouncementProvider(BaseProvider):
    """Real point-in-time announcement provider.

    Fetches exchange announcements from Eastmoney's public API, filters
    by *as_of_time*, and returns each announcement as a ``MetricFact``
    with an ``EvidenceRef`` id.

    PIT contract:
        An announcement whose ``notice_date`` is strictly after
        *as_of_time* is excluded.  The ``available_at`` for an
        announcement dated ``YYYY-MM-DD`` is conservatively set to
        ``YYYY-MM-DD 23:59:59 Asia/Shanghai`` — it is NOT assumed
        that the announcement was visible at 00:00.
    """

    def __init__(
        self,
        name: str = "eastmoney-announcements",
        timeout: float = REQUEST_TIMEOUT,
        max_retries: int = 2,
        page_size: int = DEFAULT_PAGE_SIZE,
        max_pages: int = DEFAULT_MAX_PAGES,
    ):
        if page_size <= 0:
            raise ValueError("page_size must be positive")
        if max_pages <= 0:
            raise ValueError("max_pages must be positive")
        super().__init__(
            name=name,
            source_url=ANNOUNCEMENT_API,
            timeout=timeout,
            max_retries=max_retries,
        )
        self._page_size = page_size
        self._max_pages = max_pages

    # ------------------------------------------------------------------
    # BaseProvider interface
    # ------------------------------------------------------------------

    @property
    def category(self) -> ProviderCategory:
        return ProviderCategory.DISCLOSURE

    async def fetch_for_ticker(
        self, ticker: str, as_of_time: datetime,
    ) -> Tuple[List[MetricFact], ProviderStatus]:
        """Fetch announcements.  Use :meth:`fetch_rich` for archive support."""
        result = await self.fetch_rich(ticker, as_of_time)
        return list(result.facts), result.status

    async def fetch_rich(
        self, ticker: str, as_of_time: datetime,
    ) -> AnnouncementResult:
        """Fetch announcements with raw payloads and EvidenceRefs.

        This is the preferred interface — callers can archive
        ``raw_payloads`` and ``evidence_refs`` in one pass.
        """
        self._validate_ticker_format(ticker)
        self._validate_as_of_time(as_of_time)

        code = ticker.split(".")[0]
        end_date = as_of_time.astimezone(ASIA_SH).date().isoformat()
        facts: List[MetricFact] = []
        raw_payloads: Dict[str, str] = {}
        evidence_refs: List[EvidenceRef] = []
        retrieved_at = datetime.now(ASIA_SH)
        seen_event_keys: set[str] = set()
        pages_requested = 0
        request_attempts = 0
        raw_items = 0
        eligible_items = 0
        future_filtered = 0
        parse_failures = 0
        duplicate_items = 0
        total_hits: Optional[int] = None
        last_error: Optional[str] = None
        terminal_cause: AnnouncementTerminalCause | None = None

        for page_index in range(1, self._max_pages + 1):
            pages_requested += 1
            page: AnnouncementPage | None = None
            last_exception: Exception | None = None
            for attempt in range(self.max_retries + 1):
                request_attempts += 1
                try:
                    page = await asyncio.to_thread(
                        self._fetch_page,
                        code,
                        page_index,
                        end_date,
                    )
                    break
                except Exception as exc:  # noqa: BLE001 - mapped to provider status
                    last_exception = exc
                    last_error = f"{type(exc).__name__}: {str(exc)[:240]}"
                    if attempt < self.max_retries:
                        await asyncio.sleep(0.5 * (attempt + 1))

            if page is None:
                terminal_cause = (
                    AnnouncementTerminalCause.PARSE_FAILURE
                    if isinstance(last_exception, _AnnouncementPayloadError)
                    else AnnouncementTerminalCause.UPSTREAM_FAILURE
                )
                break

            if page.total_hits is not None:
                if total_hits is not None and page.total_hits != total_hits:
                    terminal_cause = AnnouncementTerminalCause.PARSE_FAILURE
                    last_error = (
                        "Announcement total_hits changed across pages: "
                        f"expected={total_hits}, page={page_index}, "
                        f"reported={page.total_hits}"
                    )
                    break
                total_hits = page.total_hits
            items = page.items
            raw_items += len(items)
            if total_hits is not None:
                page_offset = (page_index - 1) * self._page_size
                expected_items = min(
                    self._page_size,
                    max(total_hits - page_offset, 0),
                )
                if len(items) < expected_items:
                    terminal_cause = AnnouncementTerminalCause.PARSE_FAILURE
                    last_error = (
                        "Incomplete announcement page: "
                        f"page={page_index}, items={len(items)}, "
                        f"expected_items={expected_items}, "
                        f"total_hits={total_hits}"
                    )
                    break
            if not items:
                break

            for ann in items:
                if not isinstance(ann, dict):
                    parse_failures += 1
                    continue
                try:
                    self._validate_payload_ownership(ticker, ann)
                except ValueError:
                    parse_failures += 1
                    continue
                notice_date = self._parse_notice_date(ann.get("notice_date"))
                if notice_date is None:
                    parse_failures += 1
                    continue

                # notice_date is conservatively end-of-day Asia/Shanghai.
                if notice_date > as_of_time:
                    future_filtered += 1
                    continue

                title_raw = ann.get("title")
                if not isinstance(title_raw, str) or not title_raw.strip():
                    parse_failures += 1
                    continue
                title = title_raw.strip()
                eligible_items += 1

                event_key = self._make_dedup_key(code, ann)
                if event_key in seen_event_keys:
                    duplicate_items += 1
                    continue
                seen_event_keys.add(event_key)

                # Keep the most recent bounded eligible set in upstream order.
                if len(facts) >= self._page_size:
                    continue
                evidence_id = self._make_evidence_id(code, ann)
                ev_ref = self._build_evidence_ref(
                    ticker,
                    ann,
                    evidence_id,
                    retrieved_at,
                )
                facts.append(MetricFact(
                    name="exchange_announcement",
                    value=title,
                    unit=None,
                    status="available",
                    evidence_ids=(evidence_id,),
                ))
                raw_payloads[evidence_id] = json.dumps(
                    ann,
                    sort_keys=True,
                    ensure_ascii=False,
                )
                evidence_refs.append(ev_ref)

            if len(facts) >= self._page_size:
                terminal_cause = AnnouncementTerminalCause.EVENTS_FOUND
                break
            if total_hits is not None and page_index * self._page_size >= total_hits:
                break
            if len(items) < self._page_size:
                break
        else:
            terminal_cause = AnnouncementTerminalCause.PAGINATION_LIMIT

        if terminal_cause not in {
            AnnouncementTerminalCause.UPSTREAM_FAILURE,
            AnnouncementTerminalCause.PARSE_FAILURE,
            AnnouncementTerminalCause.PAGINATION_LIMIT,
        }:
            if parse_failures:
                terminal_cause = AnnouncementTerminalCause.PARSE_FAILURE
            elif facts:
                terminal_cause = AnnouncementTerminalCause.EVENTS_FOUND
            elif raw_items == 0:
                terminal_cause = AnnouncementTerminalCause.TRUE_NO_DATA
            elif future_filtered:
                terminal_cause = AnnouncementTerminalCause.NO_EVENT_BEFORE_AS_OF
            else:
                terminal_cause = AnnouncementTerminalCause.TRUE_NO_DATA

        if facts:
            status = (
                ProviderStatus.COMPLETE
                if terminal_cause == AnnouncementTerminalCause.EVENTS_FOUND
                else ProviderStatus.PARTIAL
            )
        elif terminal_cause in {
            AnnouncementTerminalCause.TRUE_NO_DATA,
            AnnouncementTerminalCause.NO_EVENT_BEFORE_AS_OF,
        }:
            status = ProviderStatus.AVAILABLE_NO_EVENT
        else:
            status = ProviderStatus.UNAVAILABLE

        diagnostics = AnnouncementDiagnostics(
            terminal_cause=terminal_cause,
            pages_requested=pages_requested,
            request_attempts=request_attempts,
            raw_items=raw_items,
            eligible_items=eligible_items,
            future_filtered=future_filtered,
            parse_failures=parse_failures,
            duplicate_items=duplicate_items,
            total_hits=total_hits,
            last_error=last_error,
        )
        return AnnouncementResult(
            facts=facts,
            status=status,
            raw_payloads=raw_payloads,
            evidence_refs=evidence_refs,
            diagnostics=diagnostics,
        )

    def supports_ticker(self, ticker: str) -> bool:
        try:
            self._validate_ticker_format(ticker)
            return True
        except ValueError:
            return False

    @classmethod
    def replay_archived_fact(
        cls,
        ticker: str,
        raw_content: str | bytes,
        ref: EvidenceRef,
        as_of_time: datetime,
    ) -> MetricFact:
        """Rebuild one fact from immutable archive bytes without network access.

        The archived payload remains authoritative.  Receipt fields never carry
        a second copy of the title, date, or evidence identity that could drift
        from the bytes protected by ``EvidenceRef.content_sha256``.
        """
        if as_of_time.tzinfo is None:
            raise ValueError("offline replay as_of_time must be timezone-aware")
        try:
            content = (
                raw_content.decode("utf-8")
                if isinstance(raw_content, bytes)
                else raw_content
            )
            announcement = json.loads(content)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("archived announcement is not valid UTF-8 JSON") from exc
        if not isinstance(announcement, dict):
            raise ValueError("archived announcement must be a JSON object")

        code = ticker.split(".")[0]
        cls._validate_payload_ownership(ticker, announcement)
        expected_id = cls._make_evidence_id(code, announcement)
        if ref.evidence_id != expected_id:
            raise ValueError("archived announcement evidence_id mismatch")
        expected_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        if ref.content_sha256 != expected_hash:
            raise ValueError("archived announcement content hash mismatch")
        if ref.source_type != "disclosure" or ref.evidence_id != expected_id:
            raise ValueError("archived announcement source_type mismatch")

        notice_date = cls._parse_notice_date(announcement.get("notice_date"))
        if notice_date is None:
            raise ValueError("archived announcement notice_date is invalid")
        if notice_date > as_of_time:
            raise ValueError("archived announcement is future evidence")
        if ref.available_at != notice_date or ref.available_at > as_of_time:
            raise ValueError("archived announcement availability mismatch")

        title_raw = announcement.get("title")
        if not isinstance(title_raw, str) or not title_raw.strip():
            raise ValueError("archived announcement title is invalid")
        return MetricFact(
            name="exchange_announcement",
            value=title_raw.strip(),
            unit=None,
            status="available",
            evidence_ids=(ref.evidence_id,),
        )

    @staticmethod
    def _validate_payload_ownership(ticker: str, announcement: Dict) -> None:
        """Require an explicit, well-formed owner matching the request ticker."""
        code = ticker.split(".")[0]
        codes = announcement.get("codes")
        if not isinstance(codes, list) or not codes:
            raise ValueError("announcement payload has no ticker ownership")
        owners: set[str] = set()
        for row in codes:
            if not isinstance(row, dict):
                raise ValueError("announcement payload ownership is malformed")
            owner = str(row.get("stock_code") or "").strip()
            if not owner.isdigit() or len(owner) != 6:
                raise ValueError("announcement payload ownership is malformed")
            owners.add(owner)
        if code not in owners:
            raise ValueError("announcement payload ticker ownership mismatch")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fetch_page(
        self,
        code: str,
        page_index: int,
        end_date: str,
    ) -> AnnouncementPage:
        """Synchronous HTTP fetch (runs in a thread via asyncio.to_thread).

        Returns the raw list of announcement dicts from the API response.
        Does NOT pre-compute evidence IDs — that's done in the consumption
        loop so dedup is per-fact, not per-page.
        """
        params = {
            "sr": "-1",
            "page_size": str(self._page_size),
            "page_index": str(page_index),
            "ann_type": "A",
            "client_source": "web",
            "stock_list": code,
            # Reduce request volume by asking upstream for the historical
            # cutoff as well. Client-side available_at filtering remains the
            # authoritative PIT guard, including same-day announcements.
            "end_time": end_date,
        }
        response = requests.get(
            self.source_url, params=params, timeout=self.timeout,
        )
        response.raise_for_status()
        try:
            payload = response.json()
        except Exception as exc:  # noqa: BLE001 - normalized as payload failure
            raise _AnnouncementPayloadError(
                f"Announcement response is not valid JSON: {str(exc)[:120]}"
            ) from exc
        if not isinstance(payload, dict) or "data" not in payload:
            raise _AnnouncementPayloadError(
                f"Unexpected payload shape: {str(payload)[:120]}"
            )
        data = payload["data"]
        if not isinstance(data, dict):
            raise _AnnouncementPayloadError("Unexpected announcement data shape")
        items: List[Dict] = data.get("list")
        if not isinstance(items, list):
            raise _AnnouncementPayloadError("Unexpected announcement list shape")
        total_hits_raw = data.get("total_hits")
        try:
            total_hits = int(total_hits_raw) if total_hits_raw is not None else None
        except (TypeError, ValueError) as exc:
            raise _AnnouncementPayloadError(
                f"Invalid total_hits: {total_hits_raw!r}"
            ) from exc
        if total_hits is not None and total_hits < 0:
            raise _AnnouncementPayloadError(f"Invalid total_hits: {total_hits}")
        return AnnouncementPage(items=items, total_hits=total_hits)

    @staticmethod
    def _parse_notice_date(raw: object) -> Optional[datetime]:
        """Parse Eastmoney notice_date → Asia/Shanghai datetime.

        An announcement dated "2026-07-30" is assigned
        ``available_at = 2026-07-30 23:59:59 Asia/Shanghai`` — the
        conservative assumption is that it becomes visible only by
        end of day, not at midnight.
        """
        if not isinstance(raw, str) or not raw:
            return None
        try:
            raw = raw.strip()[:10]
            dt_naive = datetime.strptime(raw, "%Y-%m-%d")
            return dt_naive.replace(
                hour=_CONSERVATIVE_HOUR,
                minute=_CONSERVATIVE_MINUTE,
                second=_CONSERVATIVE_SECOND,
                tzinfo=ASIA_SH,
            )
        except (ValueError, IndexError):
            return None

    @staticmethod
    def _make_evidence_id(code: str, ann: Dict) -> str:
        """Deterministic evidence ID from announcement content."""
        raw = json.dumps(ann, sort_keys=True, ensure_ascii=False)
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
        notice_date = str(ann.get("notice_date") or "unknown")[:10]
        return f"ann-{code}-{notice_date}-{digest}"

    @staticmethod
    def _make_dedup_key(code: str, ann: Dict) -> str:
        """Return a stable event identity independent of payload metadata drift."""
        art_code = str(ann.get("art_code") or "").strip()
        if art_code:
            return f"art:{art_code}"
        fallback = {
            "code": code,
            "notice_date": str(ann.get("notice_date") or "")[:10],
            "title": str(ann.get("title") or "").strip(),
        }
        raw = json.dumps(fallback, sort_keys=True, ensure_ascii=False)
        return "fallback:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _build_detail_url(self, ann: Dict) -> str:
        """Construct a specific announcement detail page URL.

        Uses ``art_code`` and ``stock_code`` from the API response to build
        a resolvable URL, e.g.::

            https://data.eastmoney.com/notices/detail/600000/AN20260727xxx.html

        Falls back to the list-API URL with query params if the required
        fields are missing.
        """
        art_code = str(ann.get("art_code") or "").strip()
        codes = ann.get("codes")
        stock_code = ""
        if isinstance(codes, list) and codes and isinstance(codes[0], dict):
            stock_code = str(codes[0].get("stock_code") or "").strip()

        if art_code and stock_code:
            return (
                f"https://data.eastmoney.com/notices/detail/"
                f"{stock_code}/{art_code}.html"
            )
        # Fallback: list-API URL with query params (still better than
        # the bare API endpoint)
        return f"{self.source_url}?stock_list={stock_code or '?'}&sr=-1"

    def _build_evidence_ref(
        self,
        ticker: str,
        ann: Dict,
        evidence_id: str,
        retrieved_at: datetime,
    ) -> EvidenceRef:
        """Construct a verifiable EvidenceRef for a single announcement."""
        raw = json.dumps(ann, sort_keys=True, ensure_ascii=False)
        notice_date = self._parse_notice_date(ann.get("notice_date"))
        period_end = None
        if notice_date is not None:
            period_end = notice_date.replace(
                hour=0, minute=0, second=0, microsecond=0,
            )
        detail_url = self._build_detail_url(ann)
        return EvidenceRef(
            evidence_id=evidence_id,
            source_type="disclosure",
            source_name=self.name,
            source_url=detail_url,
            period_end=period_end,
            published_at=notice_date,
            available_at=notice_date or retrieved_at,
            retrieved_at=retrieved_at,
            content_sha256=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        )
