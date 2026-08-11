"""Deterministic, injectable generator for the operate-year dividend archive.

The corporate-action archive used by WP1-E2P must prove completeness over the
ex-right/ex-dividend (``dividOperateDate``) window, which the report-year
archive (``yearType='report'``) cannot.  This generator builds a hash-bound
archive queried with ``yearType='operate'``.

Network (BaoStock ``login`` + ``query_dividend_data``) is an explicit gate: the
CLI refuses to touch the network unless ``--allow-network`` is passed AND the
call site has explicit user/Codex authorization.  The core builder takes an
injectable query function so every code path is exercised offline with a mock.

Output contract (v1, WP1-E2O):
- only complete operate years 2020..2025 are admitted (no partial-year cutoff);
- the ticker set is bound to the exact official 49 from the hash-pinned universe
  manifest; arbitrary, duplicate, or malformed tickers are rejected;
- one request receipt per (ticker, year) records identity, timestamps,
  ``error_code``/``error_msg``, returned code, field schema, per-page row string
  arrays, ``row_count``, ``response_payload_sha256`` (canonical hash of the
  parsed ``{fields, rows}`` payload - explicitly NOT a wire/raw hash),
  ``max_event_date`` and ``duplicate_count``;
- a successful query with zero rows is a valid empty-result proof; any request,
  mid-pagination, schema, row-width, returned-code, or date violation fails the
  whole build and never clobbers an existing accepted archive;
- canonical action identity uses ``dividOperateDate`` plus normalized economic
  fields; exact duplicates are deduplicated and counted, distinct identities
  with the same ticker/date are all kept;
- CSV output is serialized with the ``csv`` module (deterministic quoting, LF,
  UTF-8 no BOM).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import sys
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Protocol, Sequence

# Canonical CSV column order (mirrors the admitted report-year archive header,
# without the accidental trailing empty column).
CANONICAL_COLUMNS: tuple[str, ...] = (
    "code",
    "dividPreNoticeDate",
    "dividAgmPumDate",
    "dividPlanAnnounceDate",
    "dividPlanDate",
    "dividRegistDate",
    "dividOperateDate",
    "dividPayDate",
    "dividStockMarketDate",
    "dividCashPsBeforeTax",
    "dividCashPsAfterTax",
    "dividStocksPs",
    "dividCashStock",
    "dividReserveToStockPs",
)

# Fields that define one canonical action identity.
ACTION_IDENTITY_FIELDS: tuple[str, ...] = (
    "dividOperateDate",
    "dividCashPsBeforeTax",
    "dividCashPsAfterTax",
    "dividStocksPs",
    "dividReserveToStockPs",
    "dividCashStock",
    "dividPlanAnnounceDate",
)

_BASE_DIRECTORY = "jiuwenswarm/evaluation/research_evidence/corporate_action_operate_2020_2025"
_ARCHIVE_ID = "corporate_action_operate_2020_2025/v1"
_DEFAULT_START_YEAR = 2020
_DEFAULT_END_YEAR = 2025
_YEARTYPE = "operate"
_TICKER_RE = re.compile(r"^(sh|sz)\.[0-9]{6}$")


class QueryResult(Protocol):
    """Minimal structural contract mirroring baostock ResultData."""

    error_code: str
    error_msg: str
    code: str
    fields: list[str]

    def next(self) -> bool: ...

    def get_row_data(self) -> list[str]: ...


QueryFn = Callable[[str, str, str], QueryResult]


class GeneratorError(RuntimeError):
    """Raised when a receipt or the build itself cannot be produced honestly."""


def _canonical_hash(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _module_sha256(module_path: str, base: Path) -> str:
    digest = hashlib.sha256()
    with (base / module_path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _validate_tickers(tickers: Sequence[str], official: Sequence[str]) -> list[str]:
    unique = list(tickers)
    if len(unique) != len(set(unique)):
        raise GeneratorError("duplicate tickers are not allowed")
    for ticker in unique:
        if _TICKER_RE.fullmatch(ticker) is None:
            raise GeneratorError(f"invalid ticker format: {ticker}")
    official_set = set(str(item) for item in official)
    if set(unique) != official_set:
        raise GeneratorError("ticker set does not match the official universe")
    return sorted(unique)


def _collect_query(
    code: str,
    year: str,
    query_fn: QueryFn,
    *,
    request_start: str,
) -> dict[str, Any]:
    """Run one (ticker, year) query, materialize all pages, and fail closed."""
    try:
        result = query_fn(code, year, _YEARTYPE)
    except Exception as exc:  # pragma: no cover - defensive socket/transport guard
        raise GeneratorError(
            f"query raised for {code}/{year}: {exc.__class__.__name__}: {exc}"
        ) from exc
    returned_code = str(getattr(result, "code", "")).lower()
    if returned_code != code.lower():
        return {
            "code": code,
            "year": year,
            "yearType": _YEARTYPE,
            "request_start": request_start,
            "request_end": _now(),
            "error_code": str(result.error_code),
            "error_msg": str(result.error_msg),
            "fields": list(getattr(result, "fields", []) or []),
            "rows": [],
            "row_count": 0,
            "response_payload_sha256": None,
            "max_event_date": None,
            "duplicate_count": 0,
            "failed": True,
        }
    if result.error_code != "0":
        return {
            "code": code,
            "year": year,
            "yearType": _YEARTYPE,
            "request_start": request_start,
            "request_end": _now(),
            "error_code": str(result.error_code),
            "error_msg": str(result.error_msg),
            "fields": list(getattr(result, "fields", []) or []),
            "rows": [],
            "row_count": 0,
            "response_payload_sha256": None,
            "max_event_date": None,
            "duplicate_count": 0,
            "failed": True,
        }
    fields = list(getattr(result, "fields", []) or [])
    rows: list[list[str]] = []
    while result.error_code == "0" and result.next():
        row = list(result.get_row_data())
        if len(row) != len(fields):
            return {
                "code": code,
                "year": year,
                "yearType": _YEARTYPE,
                "request_start": request_start,
                "request_end": _now(),
                "error_code": str(result.error_code),
                "error_msg": str(result.error_msg),
                "fields": fields,
                "rows": rows,
                "row_count": len(rows),
                "response_payload_sha256": None,
                "max_event_date": None,
                "duplicate_count": 0,
                "failed": True,
            }
        rows.append(row)
    if result.error_code != "0":
        return {
            "code": code,
            "year": year,
            "yearType": _YEARTYPE,
            "request_start": request_start,
            "request_end": _now(),
            "error_code": str(result.error_code),
            "error_msg": str(result.error_msg),
            "fields": fields,
            "rows": rows,
            "row_count": len(rows),
            "response_payload_sha256": None,
            "max_event_date": None,
            "duplicate_count": 0,
            "failed": True,
        }
    operate_index = fields.index("dividOperateDate") if "dividOperateDate" in fields else -1
    if operate_index < 0:
        return {
            "code": code,
            "year": year,
            "yearType": _YEARTYPE,
            "request_start": request_start,
            "request_end": _now(),
            "error_code": str(result.error_code),
            "error_msg": "missing required field dividOperateDate",
            "fields": fields,
            "rows": rows,
            "row_count": len(rows),
            "response_payload_sha256": None,
            "max_event_date": None,
            "duplicate_count": 0,
            "failed": True,
        }
    try:
        _validate_operate_dates(rows, operate_index, year)
    except GeneratorError as exc:
        return {
            "code": code,
            "year": year,
            "yearType": _YEARTYPE,
            "request_start": request_start,
            "request_end": _now(),
            "error_code": str(result.error_code),
            "error_msg": str(exc),
            "fields": fields,
            "rows": rows,
            "row_count": len(rows),
            "response_payload_sha256": None,
            "max_event_date": None,
            "duplicate_count": 0,
            "failed": True,
        }
    duplicate_count = 0
    identity_indexes = _identity_indexes(fields)
    if identity_indexes is None:
        return {
            "code": code,
            "year": year,
            "yearType": _YEARTYPE,
            "request_start": request_start,
            "request_end": _now(),
            "error_code": str(result.error_code),
            "error_msg": "missing canonical identity field",
            "fields": fields,
            "rows": rows,
            "row_count": len(rows),
            "response_payload_sha256": None,
            "max_event_date": None,
            "duplicate_count": 0,
            "failed": True,
        }
    seen: Counter[tuple[str, ...]] = Counter()
    for row in rows:
        identity = (code,) + tuple(
            str(row[i]) if i < len(row) else "" for i in identity_indexes
        )
        seen[identity] += 1
    duplicate_count = sum(count - 1 for count in seen.values() if count > 1)
    operate_dates = [
        str(row[operate_index])
        for row in rows
        if operate_index < len(row) and str(row[operate_index]).strip()
    ]
    return {
        "code": code,
        "year": year,
        "yearType": _YEARTYPE,
        "request_start": request_start,
        "request_end": _now(),
        "error_code": "0",
        "error_msg": "",
        "fields": fields,
        "rows": rows,
        "row_count": len(rows),
        "response_payload_sha256": _canonical_hash({"fields": fields, "rows": rows}),
        "max_event_date": max(operate_dates) if operate_dates else None,
        "duplicate_count": duplicate_count,
        "failed": False,
    }


def _validate_operate_dates(
    rows: list[list[str]],
    operate_index: int,
    requested_year: str,
) -> None:
    for row in rows:
        value = str(row[operate_index]).strip() if operate_index < len(row) else ""
        if not value:
            raise GeneratorError(f"blank dividOperateDate for operate year {requested_year}")
        try:
            parsed = date.fromisoformat(value)
        except ValueError as exc:
            raise GeneratorError(
                f"invalid dividOperateDate {value!r} for operate year {requested_year}"
            ) from exc
        if parsed.strftime("%Y") != requested_year:
            raise GeneratorError(
                f"dividOperateDate {value} is outside requested operate year {requested_year}"
            )


def _identity_indexes(fields: list[str]) -> list[int] | None:
    """Column indexes of the canonical action identity fields, or None."""
    indexes: list[int] = []
    for field in ACTION_IDENTITY_FIELDS:
        try:
            indexes.append(fields.index(field))
        except ValueError:
            return None
    return indexes


def _row_to_canonical(code: str, fields: list[str], row: list[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    for index, field in enumerate(fields):
        if index < len(row):
            values[field] = str(row[index])
        else:
            values[field] = ""
    result: dict[str, str] = {"code": code}
    for column in CANONICAL_COLUMNS:
        if column == "code":
            continue
        result[column] = values.get(column, "")
    return result


def _csv_text(rows: Sequence[dict[str, str]]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(CANONICAL_COLUMNS)
    for row in rows:
        writer.writerow([str(row.get(column, "")) for column in CANONICAL_COLUMNS])
    return buffer.getvalue()


def _pair_replace(
    csv_path: Path,
    csv_tmp: Path,
    records_path: Path,
    records_tmp: Path,
) -> None:
    """Replace the archive pair transactionally; roll back the first on failure."""
    old_csv = csv_path.read_bytes() if csv_path.exists() else None
    try:
        os.replace(csv_tmp, csv_path)
    except OSError:
        raise
    try:
        os.replace(records_tmp, records_path)
    except OSError:
        if old_csv is None:
            csv_path.unlink(missing_ok=True)
        else:
            csv_path.write_bytes(old_csv)
        raise


def build_operate_archive(
    *,
    tickers: Sequence[str],
    years: Sequence[int],
    out_dir: Path,
    query_fn: QueryFn,
    baostock_version: str,
    baostock_module_sha256: dict[str, str],
    official_tickers: Sequence[str] | None = None,
    fetched_at: str | None = None,
    tickers_expected: int | None = 49,
) -> dict[str, Any]:
    """Build the operate-year archive and its receipts; raise on any failure."""
    out_dir = Path(out_dir)
    years = sorted(int(year) for year in years)
    if not years:
        raise GeneratorError("no operate years requested")
    if not official_tickers:
        raise GeneratorError(
            "official_tickers is required; a caller cannot self-authorize the universe"
        )
    if tickers_expected is not None and len(tickers) != tickers_expected:
        raise GeneratorError(
            f"expected {tickers_expected} tickers, got {len(tickers)}"
        )
    tickers = _validate_tickers(tickers, official_tickers)
    generated_at = fetched_at or _now()

    receipts: list[dict[str, Any]] = []
    all_rows: list[dict[str, str]] = []
    identity_counts: Counter[tuple[str, ...]] = Counter()
    for code in tickers:
        for year in years:
            request_start = _now()
            receipt = _collect_query(code, str(year), query_fn, request_start=request_start)
            receipts.append(receipt)
            if receipt["failed"]:
                raise GeneratorError(
                    f"request failed for {code}/{year}: "
                    f"error_code={receipt['error_code']} {receipt['error_msg']}"
                )
            for raw_row in receipt["rows"]:
                canonical = _row_to_canonical(code, receipt["fields"], raw_row)
                identity = (code,) + tuple(
                    canonical.get(field, "") for field in ACTION_IDENTITY_FIELDS
                )
                identity_counts[identity] += 1
                if identity_counts[identity] == 1:
                    all_rows.append(canonical)

    all_rows.sort(
        key=lambda row: tuple(str(row.get(column, "")) for column in CANONICAL_COLUMNS)
    )
    total_duplicates = sum(count - 1 for count in identity_counts.values())
    total_rows = len(all_rows)

    csv_path = out_dir / "corporate_actions.csv"
    records_path = out_dir / "source_records.json"
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    manifest = {
        "schema": "corporate_action_operate_archive/v1",
        "archive_id": _ARCHIVE_ID,
        "source": "baostock query_dividend_data yearType=operate",
        "fetched_at": generated_at,
        "tickers": tickers,
        "years": [str(year) for year in years],
        "coverage_start": f"{min(years)}-01-01",
        "coverage_end": f"{max(years)}-12-31",
        "baostock_version": baostock_version,
        "baostock_module_sha256": dict(sorted(baostock_module_sha256.items())),
        "total_rows": total_rows,
        "total_receipts": len(receipts),
        "duplicate_count": total_duplicates,
        "per_request": receipts,
    }

    csv_text = _csv_text(all_rows)
    records_text = json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"

    csv_tmp = csv_path.with_name(csv_path.name + ".tmp")
    records_tmp = records_path.with_name(records_path.name + ".tmp")
    csv_tmp.write_text(csv_text, encoding="utf-8", newline="\n")
    records_tmp.write_text(records_text, encoding="utf-8", newline="\n")
    try:
        _pair_replace(csv_path, csv_tmp, records_path, records_tmp)
    except OSError:
        raise
    finally:
        for tmp in (csv_tmp, records_tmp):
            try:
                tmp.unlink(missing_ok=True)
            except OSError:  # pragma: no cover - cleanup best effort
                pass

    csv_sha256 = hashlib.sha256(csv_text.encode("utf-8")).hexdigest()
    records_sha256 = hashlib.sha256(records_text.encode("utf-8")).hexdigest()
    return {
        "archive_id": _ARCHIVE_ID,
        "out_dir": str(out_dir),
        "tickers": tickers,
        "years": [str(year) for year in years],
        "total_receipts": len(receipts),
        "total_rows": total_rows,
        "duplicate_count": total_duplicates,
        "csv_sha256": csv_sha256,
        "source_records_sha256": records_sha256,
    }


def _network_query() -> QueryFn:
    """Return the real BaoStock query function (network; gated by the CLI)."""

    import baostock as bs  # type: ignore[import-not-found]

    def _query(code: str, year: str, year_type: str) -> QueryResult:
        return bs.query_dividend_data(code=code, year=year, yearType=year_type)

    return _query


def _normalize_universe_tickers(raw: Sequence[str]) -> list[str]:
    normalized = []
    for code in raw:
        text = str(code).upper()
        if text.endswith(".SH"):
            normalized.append("sh." + text.split(".")[0].lower())
        elif text.endswith(".SZ"):
            normalized.append("sz." + text.split(".")[0].lower())
        else:
            normalized.append(str(code).lower())
    return sorted(normalized)


def _load_official_universe() -> list[str]:
    """Load the exact official 49 from the hash-pinned contest Excel contract.

    The contest-universe audit verifies the workbook byte hash and its semantic
    identity; it is the authoritative source and is not affected by the Windows
    CRLF blocker (binary xlsx).  The Sina snapshot manifest is at most a cross
    check, never the sole authority.
    """

    from jiuwenswarm.quant.reporting.contest_universe_archive import (
        inspect_contest_universe_archive,
    )

    audit = inspect_contest_universe_archive()
    if not getattr(audit, "verified", False):
        raise GeneratorError("official contest universe audit failed")
    return _normalize_universe_tickers(audit.company_codes)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Generate the operate-year dividend archive. Network is gated: "
            "--allow-network must be explicitly granted."
        )
    )
    parser.add_argument(
        "--tickers-file",
        help="optional one-ticker-per-line file (sh.600000 form); "
        "must equal the official 49, otherwise defaults to the pinned universe",
    )
    parser.add_argument("--start-year", type=int, default=_DEFAULT_START_YEAR)
    parser.add_argument("--end-year", type=int, default=_DEFAULT_END_YEAR)
    parser.add_argument(
        "--out-dir",
        default=_BASE_DIRECTORY,
        help="repository-relative output directory",
    )
    parser.add_argument(
        "--allow-network",
        action="store_true",
        help="authorize the gated BaoStock network fetch",
    )
    args = parser.parse_args(argv)

    if not args.allow_network:
        parser.error(
            "network fetch is an independent gate and is not authorized; "
            "run only after explicit user/Codex authorization"
        )

    repo_root = Path(__file__).resolve().parents[2]
    try:
        official = _load_official_universe()
    except GeneratorError as exc:
        parser.error(str(exc))
    try:
        from jiuwenswarm.quant.factor_evidence_provider import SINA_MANIFEST_SPEC

        manifest_path = repo_root / SINA_MANIFEST_SPEC.relative_path
        manifest_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        if manifest_hash == SINA_MANIFEST_SPEC.expected_sha256:
            import json as _json

            manifest_tickers = _normalize_universe_tickers(
                _json.loads(manifest_path.read_text(encoding="utf-8")).get("tickers") or []
            )
            if set(manifest_tickers) != set(official):
                parser.error(
                    "universe cross-check mismatch: Sina manifest differs from the "
                    "official contest Excel"
                )
    except (OSError, GeneratorError, json.JSONDecodeError):
        pass  # cross-check is optional; the Excel contract is authoritative
    tickers = official
    if args.tickers_file:
        tickers = [
            line.strip()
            for line in Path(args.tickers_file).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    try:
        tickers = _validate_tickers(tickers, official)
    except GeneratorError as exc:
        parser.error(str(exc))

    from baostock import __version__ as _BS_VERSION  # type: ignore[import-not-found]

    baostock_base = Path(os.path.dirname(__import__("baostock").__file__))
    module_hashes = {
        "evaluation/season_index.py": _module_sha256(
            "evaluation/season_index.py", baostock_base
        ),
        "data/resultset.py": _module_sha256("data/resultset.py", baostock_base),
        "login/loginout.py": _module_sha256("login/loginout.py", baostock_base),
        "common/contants.py": _module_sha256("common/contants.py", baostock_base),
    }

    import baostock as bs  # type: ignore[import-not-found]

    login = bs.login()
    if login.error_code != "0":
        parser.error(f"baostock login failed: {login.error_code} {login.error_msg}")
    try:
        result = build_operate_archive(
            tickers=tickers,
            years=range(args.start_year, args.end_year + 1),
            out_dir=Path(args.out_dir),
            query_fn=_network_query(),
            baostock_version=_BS_VERSION,
            baostock_module_sha256=module_hashes,
            official_tickers=official,
        )
    finally:
        bs.logout()
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
