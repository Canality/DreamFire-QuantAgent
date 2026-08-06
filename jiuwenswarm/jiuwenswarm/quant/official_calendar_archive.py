"""Fail-closed reader for the archived official A-share session calendar.

The archive separates dates confirmed by an SSE daily market-statistics result
from future dates that are only scheduled by annual SSE/SZSE notices.  Only the
confirmed sequence is eligible for the E0/E1 trust root.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


_HASH_RE = re.compile(r"[0-9a-f]{64}")
_ARCHIVE_ID = "sse_szse_a_share_calendar_2024_2026_v1"
_AUTHORITY = "SSE_SZSE_OFFICIAL_CALENDAR_ARCHIVE"
_SOURCE_VERSION = "official_calendar_2024_2026/v1"
_CALENDAR_ID = "SSE_SZSE_A_SHARE_CONFIRMED_THROUGH_20260804"
_COVERAGE_START = date(2024, 1, 1)
_COVERAGE_END = date(2026, 12, 31)
_CONFIRMATION_CUTOFF = date(2026, 8, 4)
_RELATIVE_DIRECTORY = Path(
    "jiuwenswarm/evaluation/research_evidence/official_calendar_2024_2026"
)
_EXPECTED_COLUMNS = (
    "date",
    "weekday",
    "scheduled_status",
    "confirmation_status",
    "closure_reason",
    "source_year",
    "sse_daily_result_rows",
    "sse_daily_trade_date",
    "sse_daily_product_names",
    "sse_daily_result_sha256",
)
_EXPECTED_SOURCE_IDS = frozenset(
    {
        "sse_annual_2024",
        "szse_annual_2024",
        "sse_annual_2025",
        "szse_annual_2025",
        "sse_annual_2026",
        "szse_annual_2026",
        "sse_rule_2023",
        "sse_rule_2026",
        "szse_rule_2026",
        "sse_daily_statistics_confirmation_20240101_20260804",
    }
)
_ALLOWED_HOSTS = frozenset(
    {
        "www.sse.com.cn",
        "www.szse.cn",
        "docs.static.szse.cn",
        "query.sse.com.cn",
    }
)
_EXPECTED_RULE_TEXT = (
    "本所交易日为每周一至周五。国家法定假日和本所公告的休市日，本所市场休市。"
)
_EXPECTED_PRODUCTS = "主板|科创板|股票"
_EMPTY_RESULT_HASH = hashlib.sha256(b"[]").hexdigest()
_RESULT_ROW_KEYS = frozenset(
    {
        "AVG_PE_RATIO",
        "LIST_COM_NUM",
        "NEGO_ISSUE_VOL",
        "NEGO_VALUE",
        "PRODUCT_NAME",
        "SECURITY_NUM",
        "TOTAL_ISSUE_VOL",
        "TOTAL_TRADE_AMT",
        "TOTAL_VALUE",
        "TRADE_DATE",
    }
)
_RESULT_NUMERIC_KEYS = _RESULT_ROW_KEYS - {"PRODUCT_NAME", "TRADE_DATE"}


def _canonical_hash(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _archive_source_hash(
    files: tuple[PinnedCalendarFile, ...] | None = None,
) -> str:
    active = files if files is not None else PINNED_CALENDAR_FILES
    hashes = {item.artifact_id: item.expected_sha256 for item in active}
    return _canonical_hash(
        {
            "archive_id": _ARCHIVE_ID,
            "source_records_sha256": hashes.get("official_calendar_source_records"),
            "calendar_sessions_sha256": hashes.get("official_calendar_sessions"),
        }
    )


@dataclass(frozen=True)
class PinnedCalendarFile:
    artifact_id: str
    relative_path: Path
    expected_sha256: str

    def __post_init__(self) -> None:
        if not self.artifact_id.strip():
            raise ValueError("calendar artifact id is missing")
        if self.relative_path.is_absolute() or ".." in self.relative_path.parts:
            raise ValueError("calendar path must be repository-relative")
        if _HASH_RE.fullmatch(self.expected_sha256) is None:
            raise ValueError("calendar file hash must be lowercase SHA-256")


SOURCE_RECORDS_SPEC = PinnedCalendarFile(
    artifact_id="official_calendar_source_records",
    relative_path=_RELATIVE_DIRECTORY / "source_records.json",
    expected_sha256=(
        "2f7ecd6c9c00d772295e668191eeb7adb608932fa05a867f985defcfba3dc7e3"
    ),
)
CALENDAR_SESSIONS_SPEC = PinnedCalendarFile(
    artifact_id="official_calendar_sessions",
    relative_path=_RELATIVE_DIRECTORY / "calendar_sessions.csv",
    expected_sha256=(
        "4ab22d62b1438d0a49147c547bc383813c6fbd3defe068f400e253d55775852b"
    ),
)
PINNED_CALENDAR_FILES = (SOURCE_RECORDS_SPEC, CALENDAR_SESSIONS_SPEC)
_EXPECTED_DIRECTORY_MEMBERS = frozenset(
    item.relative_path.name for item in PINNED_CALENDAR_FILES
)

ARCHIVE_SOURCE_SHA256 = _archive_source_hash(
    (SOURCE_RECORDS_SPEC, CALENDAR_SESSIONS_SPEC)
)

# Filled only from the independently generated, reviewed archive.  It is not
# recomputed from mutable runtime bytes and therefore cannot self-authorize a
# caller's self-consistent replacement.
EXPECTED_CALENDAR_EVIDENCE_SHA256 = (
    "c845b13e4f43cb42538cea1da8cd68708dbda3cecf170966af3b0ae573e2ddaa"
)


@dataclass(frozen=True)
class CalendarFileVerification:
    artifact_id: str
    relative_path: str
    expected_sha256: str
    actual_sha256: str | None
    verified: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "relative_path": self.relative_path,
            "expected_sha256": self.expected_sha256,
            "actual_sha256": self.actual_sha256,
            "verified": self.verified,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class OfficialCalendarArchive:
    archive_id: str
    authority: str
    source_version: str
    source_sha256: str
    calendar_id: str
    coverage_start: str
    coverage_end: str
    confirmation_cutoff: str
    total_calendar_days: int
    source_record_count: int
    confirmed_session_count: int
    scheduled_session_count: int
    confirmed_sessions: tuple[str, ...]
    scheduled_sessions: tuple[str, ...]
    status_counts: tuple[tuple[str, int], ...]
    files: tuple[CalendarFileVerification, ...]
    errors: tuple[str, ...]
    verified: bool
    evidence_hash: str
    audit_hash: str

    def _payload(self) -> dict[str, Any]:
        return {
            "archive_id": self.archive_id,
            "authority": self.authority,
            "source_version": self.source_version,
            "source_sha256": self.source_sha256,
            "calendar_id": self.calendar_id,
            "coverage_start": self.coverage_start,
            "coverage_end": self.coverage_end,
            "confirmation_cutoff": self.confirmation_cutoff,
            "total_calendar_days": self.total_calendar_days,
            "source_record_count": self.source_record_count,
            "confirmed_session_count": self.confirmed_session_count,
            "scheduled_session_count": self.scheduled_session_count,
            "confirmed_sessions": list(self.confirmed_sessions),
            "scheduled_sessions": list(self.scheduled_sessions),
            "status_counts": [list(item) for item in self.status_counts],
            "files": [item.to_dict() for item in self.files],
            "errors": list(self.errors),
            "verified": self.verified,
            "evidence_hash": self.evidence_hash,
        }

    def to_dict(self) -> dict[str, Any]:
        payload = self._payload()
        if _canonical_hash(payload) != self.audit_hash:
            raise ValueError("official calendar audit hash mismatch")
        return {**payload, "audit_hash": self.audit_hash}


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _has_symlink_component(root: Path, relative_path: Path) -> bool:
    current = root
    if current.is_symlink():
        return True
    for part in relative_path.parts:
        current = current / part
        if current.is_symlink():
            return True
    return False


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _verify_file(root: Path, spec: PinnedCalendarFile) -> CalendarFileVerification:
    path = root / spec.relative_path
    base = {
        "artifact_id": spec.artifact_id,
        "relative_path": spec.relative_path.as_posix(),
        "expected_sha256": spec.expected_sha256,
    }
    try:
        if _has_symlink_component(root, spec.relative_path):
            return CalendarFileVerification(
                **base,
                actual_sha256=None,
                verified=False,
                reason="SYMLINK_REJECTED",
            )
        if not path.exists():
            return CalendarFileVerification(
                **base,
                actual_sha256=None,
                verified=False,
                reason="MISSING_FILE",
            )
        if not path.is_file():
            return CalendarFileVerification(
                **base,
                actual_sha256=None,
                verified=False,
                reason="NOT_REGULAR_FILE",
            )
        path.resolve().relative_to(root.resolve())
        actual = _sha256_file(path)
    except ValueError:
        return CalendarFileVerification(
            **base,
            actual_sha256=None,
            verified=False,
            reason="PATH_ESCAPE_REJECTED",
        )
    except (OSError, RuntimeError):
        return CalendarFileVerification(
            **base,
            actual_sha256=None,
            verified=False,
            reason="FILE_IO_ERROR",
        )
    return CalendarFileVerification(
        **base,
        actual_sha256=actual,
        verified=actual == spec.expected_sha256,
        reason="VERIFIED" if actual == spec.expected_sha256 else "SHA256_MISMATCH",
    )


def _parse_iso_date(value: object, label: str, errors: list[str]) -> date | None:
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        errors.append(f"INVALID_{label}")
        return None


def _valid_first_party_url(value: object) -> bool:
    try:
        parsed = urlparse(str(value))
        return bool(
            parsed.scheme == "https"
            and parsed.hostname in _ALLOWED_HOSTS
            and parsed.port is None
            and parsed.username is None
            and parsed.password is None
            and not any(
                token in parsed.path.casefold()
                for token in ("hkexsc", "szhk", "hongkongconnect")
            )
        )
    except ValueError:
        return False


def _valid_retrieval_time(value: object) -> bool:
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.date() <= date(2026, 8, 5)


def _validate_query_ledger(
    payload: dict[str, Any],
    daily_source: dict[str, Any],
    errors: list[str],
) -> dict[date, dict[str, Any]]:
    ledger = payload.get("daily_query_ledger")
    if not isinstance(ledger, list):
        errors.append("DAILY_QUERY_LEDGER_NOT_A_LIST")
        return {}
    expected_dates = []
    current = _COVERAGE_START
    while current <= _CONFIRMATION_CUTOFF:
        if current.weekday() < 5:
            expected_dates.append(current)
        current += timedelta(days=1)
    if len(ledger) != len(expected_dates):
        errors.append("DAILY_QUERY_LEDGER_COUNT_MISMATCH")
    expected_keys = {
        "canonical_result_rows",
        "canonical_result_sha256",
        "date",
        "product_names",
        "result_rows",
        "result_trade_dates",
    }
    by_date: dict[date, dict[str, Any]] = {}
    for index, record in enumerate(ledger):
        if not isinstance(record, dict) or set(record) != expected_keys:
            errors.append("INVALID_DAILY_QUERY_RECORD")
            continue
        parsed = _parse_iso_date(record.get("date"), "DAILY_QUERY_DATE", errors)
        expected = expected_dates[index] if index < len(expected_dates) else None
        if parsed is None or parsed != expected or parsed in by_date:
            errors.append("DAILY_QUERY_DATE_SEQUENCE_MISMATCH")
            continue
        rows = record.get("result_rows")
        products = record.get("product_names")
        trade_dates = record.get("result_trade_dates")
        result_hash = str(record.get("canonical_result_sha256", ""))
        result_payload = record.get("canonical_result_rows")
        payload_valid = isinstance(result_payload, list)
        if payload_valid:
            try:
                actual_result_hash = _canonical_hash(result_payload)
            except (TypeError, ValueError):
                payload_valid = False
                actual_result_hash = ""
        else:
            actual_result_hash = ""
        if actual_result_hash != result_hash:
            errors.append("DAILY_RESULT_PAYLOAD_HASH_MISMATCH")
        payload_products: list[str] = []
        payload_trade_dates: list[str] = []
        if payload_valid:
            for result_row in result_payload:
                if (
                    not isinstance(result_row, dict)
                    or set(result_row) != _RESULT_ROW_KEYS
                ):
                    payload_valid = False
                    continue
                payload_products.append(str(result_row.get("PRODUCT_NAME", "")))
                payload_trade_dates.append(str(result_row.get("TRADE_DATE", "")))
                for field in _RESULT_NUMERIC_KEYS:
                    value = result_row.get(field)
                    try:
                        parsed_number = (
                            Decimal(value) if isinstance(value, str) else None
                        )
                    except InvalidOperation:
                        parsed_number = None
                    if (
                        parsed_number is None
                        or not parsed_number.is_finite()
                        or parsed_number < 0
                    ):
                        payload_valid = False
        closed = (
            rows == 0 and products == [] and trade_dates == [] and result_payload == []
        )
        opened = (
            rows == 3
            and products == ["主板", "科创板", "股票"]
            and trade_dates == [parsed.strftime("%Y%m%d")]
            and payload_valid
            and len(result_payload) == 3
            and payload_products == ["股票", "主板", "科创板"]
            and payload_trade_dates == [parsed.strftime("%Y%m%d")] * 3
        )
        if (
            isinstance(rows, bool)
            or not (closed or opened)
            or _HASH_RE.fullmatch(result_hash) is None
        ):
            errors.append("INVALID_DAILY_QUERY_RECORD")
        by_date[parsed] = record
    try:
        canonical_jsonl = "".join(
            json.dumps(
                record,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            + "\n"
            for record in ledger
            if isinstance(record, dict)
        ).encode("utf-8")
    except (TypeError, ValueError):
        errors.append("INVALID_DAILY_QUERY_RECORD")
        canonical_jsonl = b""
    if not canonical_jsonl or hashlib.sha256(
        canonical_jsonl
    ).hexdigest() != daily_source.get("raw_sha256"):
        errors.append("DAILY_QUERY_LEDGER_HASH_MISMATCH")
    return by_date


def _validate_source_records(
    path: Path,
) -> tuple[
    list[str],
    dict[date, str],
    dict[date, dict[str, Any]],
    int,
]:
    errors: list[str] = []
    closures: dict[date, str] = {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return ["INVALID_SOURCE_RECORDS_JSON"], closures, {}, 0
    expected_metadata = {
        "schema_version": 1,
        "archive_id": _ARCHIVE_ID,
        "coverage_start": _COVERAGE_START.isoformat(),
        "coverage_end": _COVERAGE_END.isoformat(),
        "confirmation_cutoff": _CONFIRMATION_CUTOFF.isoformat(),
        "representation": (
            "normalized_first_party_records_with_daily_query_payload_ledger"
        ),
    }
    if any(payload.get(key) != value for key, value in expected_metadata.items()):
        errors.append("SOURCE_RECORD_METADATA_MISMATCH")
    if not _valid_retrieval_time(payload.get("retrieved_at")):
        errors.append("SOURCE_RECORD_METADATA_MISMATCH")
    sources = payload.get("sources")
    if not isinstance(sources, list):
        return [*errors, "SOURCE_RECORDS_NOT_A_LIST"], closures, {}, 0
    by_id = {
        item.get("source_id"): item
        for item in sources
        if isinstance(item, dict) and isinstance(item.get("source_id"), str)
    }
    if len(by_id) != len(sources) or set(by_id) != set(_EXPECTED_SOURCE_IDS):
        errors.append("UNEXPECTED_SOURCE_RECORD_SET")
    for source_id, record in by_id.items():
        expected_authority = "SZSE" if source_id.startswith("szse_") else "SSE"
        if (
            not _valid_first_party_url(record.get("url"))
            or record.get("authority") != expected_authority
            or str(record.get("market")) != "A_SHARE"
            or "港股通" in str(record.get("title", ""))
            or not _valid_retrieval_time(record.get("retrieved_at"))
        ):
            errors.append("UNTRUSTED_OR_WRONG_MARKET_SOURCE")
        raw_hash = str(record.get("raw_sha256", ""))
        normalized_hash = str(record.get("normalized_text_sha256", ""))
        normalized_text = str(record.get("normalized_text", ""))
        if (
            _HASH_RE.fullmatch(raw_hash) is None
            or _HASH_RE.fullmatch(normalized_hash) is None
            or hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()
            != normalized_hash
        ):
            errors.append("SOURCE_RECORD_HASH_MISMATCH")
        if record.get("record_kind") == "TRADING_DAY_RULE":
            if (
                normalized_text != _EXPECTED_RULE_TEXT
                or record.get("clause_id") != "2.4.1"
            ):
                errors.append("TRADING_DAY_RULE_MISMATCH")
        if record.get("record_kind") == "ANNUAL_CLOSURE_NOTICE":
            year = record.get("year")
            spans = record.get("closure_spans")
            published = _parse_iso_date(
                record.get("published_at"), "ANNUAL_NOTICE_PUBLISHED_AT", errors
            )
            if (
                year not in {2024, 2025, 2026}
                or not isinstance(spans, list)
                or record.get("effective_from") != f"{year}-01-01"
                or record.get("effective_to") != f"{year}-12-31"
                or published is None
                or published >= date(year, 1, 1)
            ):
                errors.append("INVALID_ANNUAL_CLOSURE_RECORD")
                continue
            for span in spans:
                if not isinstance(span, dict):
                    errors.append("INVALID_CLOSURE_SPAN")
                    continue
                start = _parse_iso_date(span.get("start"), "CLOSURE_START", errors)
                end = _parse_iso_date(span.get("end"), "CLOSURE_END", errors)
                closure_id = str(span.get("closure_id", ""))
                if start is None or end is None or start > end or not closure_id:
                    errors.append("INVALID_CLOSURE_SPAN")
                    continue
                current = start
                while current <= end:
                    if current.year == year:
                        existing = closures.get(current)
                        if existing is not None and existing != closure_id:
                            errors.append("SSE_SZSE_CLOSURE_DISAGREEMENT")
                        closures[current] = closure_id
                    current += timedelta(days=1)
    for year in (2024, 2025, 2026):
        annual = [
            item
            for item in sources
            if isinstance(item, dict)
            and item.get("record_kind") == "ANNUAL_CLOSURE_NOTICE"
            and item.get("year") == year
        ]
        if len(annual) != 2 or {item.get("authority") for item in annual} != {
            "SSE",
            "SZSE",
        }:
            errors.append("MISSING_CROSS_EXCHANGE_ANNUAL_NOTICE")
        elif annual[0].get("closure_spans") != annual[1].get("closure_spans"):
            errors.append("SSE_SZSE_CLOSURE_DISAGREEMENT")
    daily = by_id.get("sse_daily_statistics_confirmation_20240101_20260804", {})
    if any(
        daily.get(key) != value
        for key, value in {
            "authority": "SSE",
            "record_kind": "DAILY_MARKET_STATISTICS_API",
            "effective_from": "2024-01-01",
            "effective_to": "2026-08-04",
            "query_weekday_count": 677,
            "confirmed_open_count": 626,
            "confirmed_closed_count": 51,
            "normalized_text": (
                "COMMON_SSE_SJ_GPSJ_GPSJZM_TJSJ_L|"
                "PRODUCT_NAME=股票,主板,科创板|type=inParams|"
                "TRADE_DATE=YYYY-MM-DD|canonical_result_rows="
                "API_RESULT_PRESERVE_ORDER_SORT_KEYS_JSON"
            ),
            "normalization_policy": (
                "canonical_sse_result_rows_preserve_api_order_sort_keys_json_v2"
            ),
        }.items()
    ):
        errors.append("DAILY_CONFIRMATION_SOURCE_MISMATCH")
    query_ledger = _validate_query_ledger(payload, daily, errors)
    return (
        list(dict.fromkeys(errors)),
        closures,
        query_ledger,
        len(sources),
    )


def _validate_calendar_rows(
    path: Path,
    closures: dict[date, str],
    query_ledger: dict[date, dict[str, Any]],
) -> tuple[list[str], tuple[str, ...], tuple[str, ...], Counter[str], int]:
    errors: list[str] = []
    confirmed: list[str] = []
    scheduled: list[str] = []
    statuses: Counter[str] = Counter()
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if tuple(reader.fieldnames or ()) != _EXPECTED_COLUMNS:
                return ["CALENDAR_COLUMNS_MISMATCH"], (), (), statuses, 0
            rows = list(reader)
    except (OSError, UnicodeDecodeError, csv.Error):
        return ["INVALID_CALENDAR_CSV"], (), (), statuses, 0
    expected_days = (_COVERAGE_END - _COVERAGE_START).days + 1
    if len(rows) != expected_days:
        errors.append("CALENDAR_DAY_COUNT_MISMATCH")
    for offset, row in enumerate(rows):
        expected_date = _COVERAGE_START + timedelta(days=offset)
        parsed = _parse_iso_date(row.get("date"), "CALENDAR_DATE", errors)
        if parsed != expected_date:
            errors.append("CALENDAR_DATE_SEQUENCE_MISMATCH")
            continue
        weekend = expected_date.weekday() >= 5
        holiday = expected_date in closures
        expected_open = not weekend and not holiday
        expected_scheduled_status = "OPEN" if expected_open else "CLOSED"
        expected_reason = "WEEKEND" if weekend else closures.get(expected_date, "NONE")
        if (
            row.get("weekday") != expected_date.strftime("%A").upper()
            or row.get("scheduled_status") != expected_scheduled_status
            or row.get("closure_reason") != expected_reason
            or row.get("source_year") != str(expected_date.year)
        ):
            errors.append("SCHEDULE_DERIVATION_MISMATCH")
        if expected_date <= _CONFIRMATION_CUTOFF and weekend:
            expected_confirmation = "WEEKEND_CLOSED"
        elif expected_date <= _CONFIRMATION_CUTOFF and expected_open:
            expected_confirmation = "CONFIRMED_OPEN"
        elif expected_date <= _CONFIRMATION_CUTOFF:
            expected_confirmation = "CONFIRMED_CLOSED"
        elif expected_open:
            expected_confirmation = "SCHEDULED_OPEN"
        else:
            expected_confirmation = "SCHEDULED_CLOSED"
        confirmation = str(row.get("confirmation_status", ""))
        if confirmation != expected_confirmation:
            errors.append("CONFIRMATION_STATUS_MISMATCH")
        rows_value = str(row.get("sse_daily_result_rows", ""))
        trade_date = str(row.get("sse_daily_trade_date", ""))
        products = str(row.get("sse_daily_product_names", ""))
        result_hash = str(row.get("sse_daily_result_sha256", ""))
        query_record = query_ledger.get(expected_date)
        if confirmation == "CONFIRMED_OPEN":
            if (
                query_record is None
                or rows_value != "3"
                or trade_date != expected_date.strftime("%Y%m%d")
                or products != _EXPECTED_PRODUCTS
                or _HASH_RE.fullmatch(result_hash) is None
                or rows_value != str(query_record.get("result_rows"))
                or trade_date != "|".join(query_record.get("result_trade_dates", []))
                or products != "|".join(query_record.get("product_names", []))
                or result_hash != query_record.get("canonical_result_sha256")
            ):
                errors.append("INVALID_CONFIRMED_OPEN_RESULT")
            confirmed.append(expected_date.isoformat())
        elif confirmation == "CONFIRMED_CLOSED":
            if (
                query_record is None
                or rows_value != "0"
                or trade_date
                or products
                or result_hash != _EMPTY_RESULT_HASH
                or query_record.get("result_rows") != 0
                or query_record.get("product_names") != []
                or query_record.get("result_trade_dates") != []
                or result_hash != query_record.get("canonical_result_sha256")
            ):
                errors.append("INVALID_CONFIRMED_CLOSED_RESULT")
        elif (
            any((rows_value, trade_date, products, result_hash))
            or query_record is not None
        ):
            errors.append("UNEXPECTED_UNCONFIRMED_QUERY_RESULT")
        if expected_open:
            scheduled.append(expected_date.isoformat())
        statuses[confirmation] += 1
    return (
        list(dict.fromkeys(errors)),
        tuple(confirmed),
        tuple(scheduled),
        statuses,
        len(rows),
    )


def _calendar_evidence_hash(confirmed_sessions: tuple[str, ...]) -> str:
    return _canonical_hash(
        {
            "authority": _AUTHORITY,
            "source_version": _SOURCE_VERSION,
            "source_sha256": ARCHIVE_SOURCE_SHA256,
            "calendar_id": _CALENDAR_ID,
            "sessions": list(confirmed_sessions),
        }
    )


def _inspect_at_root(root: Path) -> OfficialCalendarArchive:
    files = tuple(_verify_file(root, spec) for spec in PINNED_CALENDAR_FILES)
    errors: list[str] = []
    directory = root / _RELATIVE_DIRECTORY
    try:
        if _has_symlink_component(root, _RELATIVE_DIRECTORY):
            errors.append("SYMLINKED_CALENDAR_DIRECTORY")
        elif not directory.is_dir():
            errors.append("MISSING_CALENDAR_DIRECTORY")
        elif (
            frozenset(item.name for item in directory.iterdir())
            != _EXPECTED_DIRECTORY_MEMBERS
        ):
            errors.append("UNEXPECTED_CALENDAR_FILE_SET")
    except OSError:
        errors.append("CALENDAR_DIRECTORY_IO_ERROR")
    source_count = 0
    closures: dict[date, str] = {}
    query_ledger: dict[date, dict[str, Any]] = {}
    confirmed: tuple[str, ...] = ()
    scheduled: tuple[str, ...] = ()
    statuses: Counter[str] = Counter()
    total_days = 0
    if all(item.verified for item in files) and not errors:
        source_errors, closures, query_ledger, source_count = _validate_source_records(
            root / SOURCE_RECORDS_SPEC.relative_path
        )
        errors.extend(source_errors)
        row_errors, confirmed, scheduled, statuses, total_days = (
            _validate_calendar_rows(
                root / CALENDAR_SESSIONS_SPEC.relative_path,
                closures,
                query_ledger,
            )
        )
        errors.extend(row_errors)
    if _archive_source_hash() != ARCHIVE_SOURCE_SHA256:
        errors.append("ARCHIVE_SOURCE_HASH_MISMATCH")
    evidence_hash = _calendar_evidence_hash(confirmed)
    if confirmed and evidence_hash != EXPECTED_CALENDAR_EVIDENCE_SHA256:
        errors.append("CALENDAR_EVIDENCE_HASH_MISMATCH")
    errors = list(dict.fromkeys(errors))
    verified = bool(all(item.verified for item in files) and not errors)
    status_counts = tuple(sorted(statuses.items()))
    base = {
        "archive_id": _ARCHIVE_ID,
        "authority": _AUTHORITY,
        "source_version": _SOURCE_VERSION,
        "source_sha256": ARCHIVE_SOURCE_SHA256,
        "calendar_id": _CALENDAR_ID,
        "coverage_start": _COVERAGE_START.isoformat(),
        "coverage_end": _COVERAGE_END.isoformat(),
        "confirmation_cutoff": _CONFIRMATION_CUTOFF.isoformat(),
        "total_calendar_days": total_days,
        "source_record_count": source_count,
        "confirmed_session_count": len(confirmed),
        "scheduled_session_count": len(scheduled),
        "confirmed_sessions": list(confirmed),
        "scheduled_sessions": list(scheduled),
        "status_counts": [list(item) for item in status_counts],
        "files": [item.to_dict() for item in files],
        "errors": errors,
        "verified": verified,
        "evidence_hash": evidence_hash,
    }
    return OfficialCalendarArchive(
        archive_id=_ARCHIVE_ID,
        authority=_AUTHORITY,
        source_version=_SOURCE_VERSION,
        source_sha256=ARCHIVE_SOURCE_SHA256,
        calendar_id=_CALENDAR_ID,
        coverage_start=_COVERAGE_START.isoformat(),
        coverage_end=_COVERAGE_END.isoformat(),
        confirmation_cutoff=_CONFIRMATION_CUTOFF.isoformat(),
        total_calendar_days=total_days,
        source_record_count=source_count,
        confirmed_session_count=len(confirmed),
        scheduled_session_count=len(scheduled),
        confirmed_sessions=confirmed,
        scheduled_sessions=scheduled,
        status_counts=status_counts,
        files=files,
        errors=tuple(errors),
        verified=verified,
        evidence_hash=evidence_hash,
        audit_hash=_canonical_hash(base),
    )


def inspect_official_calendar_archive() -> OfficialCalendarArchive:
    """Verify and load the one fixed repository-held official calendar."""

    return _inspect_at_root(_repository_root())
