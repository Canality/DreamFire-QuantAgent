"""Deterministic v2 full-embargo official 1+20 forward-label archive generator.

Reads ONLY the pinned E0 qfq snapshot and the official 626-session calendar and
writes the causally-correct archive:

    decision close -> one full trading-session embargo -> following entry open
    -> twentieth valuation close

Each of the 604 decisions (canonical confirmed sessions 2024-01-02..2026-07-03)
binds the canonical calendar positions [decision, embargo, entry, 20
valuations, exit] and the 49 per-ticker entry-open / exit-close prices from the
hash-verified qfq rows.  It never reads the old archive's prices and never
touches the network.  Same input twice produces byte-identical output.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import sys
from pathlib import Path
from typing import Any

_ENGINE_VERSION = "generate_official_forward_labels/1.0.0"
_LABEL_SCHEMA = "official_forward_label/v2"
_DECISION_START = "2024-01-02"
_DECISION_END = "2026-07-03"
_EMBARGO = 1
_HOLDING = 20


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_hash(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _require_imports():
    sys.path.insert(0, str(_repository_root() / "jiuwenswarm"))
    from jiuwenswarm.quant import factor_evidence_provider, official_calendar_archive

    return factor_evidence_provider, official_calendar_archive


def _load_qfq_prices(qfq_path: Path) -> tuple[dict[str, dict[str, dict[str, str]]], list[str]]:
    """Return {(date): {ticker: {open, close}}} and the sorted ticker list."""
    by_date: dict[str, dict[str, dict[str, str]]] = {}
    tickers: set[str] = set()
    with qfq_path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            date = str(row["date"])
            code = str(row["code"])
            tickers.add(code)
            by_date.setdefault(date, {})[code] = {
                "open": str(row["open"]),
                "close": str(row["close"]),
            }
    return by_date, sorted(tickers)


def _main() -> int:
    provider, calendar_archive = _require_imports()
    qfq_spec = provider.E0_SNAPSHOT_CSV_SPEC
    qfq_records_spec = provider.E0_SNAPSHOT_RECORDS_SPEC
    qfq_path = _repository_root() / qfq_spec.relative_path
    if _sha256(qfq_path) != qfq_spec.expected_sha256:
        raise RuntimeError("E0 qfq CSV hash mismatch")
    qfq_records_path = _repository_root() / qfq_records_spec.relative_path
    if _sha256(qfq_records_path) != qfq_records_spec.expected_sha256:
        raise RuntimeError("E0 qfq source_records hash mismatch")

    calendar = calendar_archive.inspect_official_calendar_archive()
    if not calendar.verified:
        raise RuntimeError("official calendar archive is not verified")
    sessions = list(calendar.confirmed_sessions)
    calendar_sessions = [str(s) for s in sessions]
    calendar_index = {s: i for i, s in enumerate(calendar_sessions)}
    decision_start_idx = calendar_index.get(_DECISION_START)
    decision_end_idx = calendar_index.get(_DECISION_END)
    if decision_start_idx is None or decision_end_idx is None:
        raise RuntimeError("decision boundary not in the canonical calendar")
    if decision_end_idx + _EMBARGO + _HOLDING + 1 > len(calendar_sessions):
        raise RuntimeError("canonical calendar ends before the last decision exit")
    decision_positions = list(range(decision_start_idx, decision_end_idx + 1))
    if len(decision_positions) != 604:
        raise RuntimeError(f"expected 604 decisions, got {len(decision_positions)}")

    qfq, tickers = _load_qfq_prices(qfq_path)
    if len(tickers) != 49:
        raise RuntimeError(f"expected 49 tickers, got {len(tickers)}")

    rows: list[dict[str, str]] = []
    per_decision: dict[str, dict[str, Any]] = {}
    for pos in decision_positions:
        decision = calendar_sessions[pos]
        embargo = calendar_sessions[pos + 1]
        entry = calendar_sessions[pos + 2]
        valuations = calendar_sessions[pos + 2 : pos + 2 + _HOLDING]
        exit_day = calendar_sessions[pos + _EMBARGO + _HOLDING]
        if len(valuations) != _HOLDING:
            raise RuntimeError(f"decision {decision} has an incomplete 1+20 window")
        entry_row = qfq.get(entry)
        exit_row = qfq.get(exit_day)
        if entry_row is None or exit_row is None:
            raise RuntimeError(f"decision {decision} missing qfq entry/exit dates")
        row: dict[str, str] = {
            "decision_date": decision,
            "embargo_date": embargo,
            "entry_open_date": entry,
            "exit_close_date": exit_day,
            "valuation_dates": "|".join(valuations),
        }
        for ticker in tickers:
            if ticker not in entry_row or ticker not in exit_row:
                raise RuntimeError(f"decision {decision} missing qfq price for {ticker}")
            row[f"{ticker}_entry_open"] = entry_row[ticker]["open"]
            row[f"{ticker}_exit_close"] = exit_row[ticker]["close"]
        canonical_row_hash = _canonical_hash(row)
        rows.append(row)
        per_decision[decision] = {
            "embargo_date": embargo,
            "entry_open_date": entry,
            "valuation_dates": valuations,
            "exit_close_date": exit_day,
            "canonical_row_hash": canonical_row_hash,
            "matured": True,
        }

    first_decision = rows[0]["decision_date"]
    last_decision = rows[-1]["decision_date"]
    source_records = {
        "schema": _LABEL_SCHEMA,
        "engine_version": _ENGINE_VERSION,
        "source": "calendar CONFIRMED_OPEN + baostock qfq snapshot (v2 full-embargo)",
        "e0_csv_sha256": qfq_spec.expected_sha256,
        "e0_records_sha256": qfq_records_spec.expected_sha256,
        "calendar_source_sha256": calendar_archive.ARCHIVE_SOURCE_SHA256,
        "calendar_evidence_sha256": calendar_archive.EXPECTED_CALENDAR_EVIDENCE_SHA256,
        "decision_count": len(rows),
        "ticker_count": len(tickers),
        "embargo_trading_days": _EMBARGO,
        "holding_days": _HOLDING,
        "first_decision": first_decision,
        "last_decision": last_decision,
        "per_decision": per_decision,
    }
    evidence_payload = {k: v for k, v in source_records.items() if k != "evidence_sha256"}
    source_records["evidence_sha256"] = _canonical_hash(evidence_payload)

    out_dir = (
        _repository_root()
        / "jiuwenswarm"
        / "evaluation"
        / "research_evidence"
        / "official_forward_label_2024_2026_v2"
    )
    if "--out-dir" in sys.argv:
        out_dir = Path(sys.argv[sys.argv.index("--out-dir") + 1])
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "forward_labels.csv"
    records_path = out_dir / "source_records.json"

    columns = [
        "decision_date",
        "embargo_date",
        "entry_open_date",
        "exit_close_date",
        "valuation_dates",
    ] + [f"{ticker}_entry_open" for ticker in tickers] + [
        f"{ticker}_exit_close" for ticker in tickers
    ]
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(columns)
    for row in rows:
        writer.writerow([row[col] for col in columns])
    csv_text = buffer.getvalue()
    records_text = json.dumps(source_records, ensure_ascii=False, indent=2, sort_keys=True) + "\n"

    csv_tmp = csv_path.with_suffix(csv_path.suffix + ".tmp")
    records_tmp = records_path.with_suffix(records_path.suffix + ".tmp")
    csv_tmp.write_text(csv_text, encoding="utf-8", newline="\n")
    records_tmp.write_text(records_text, encoding="utf-8", newline="\n")
    os.replace(csv_tmp, csv_path)
    os.replace(records_tmp, records_path)

    print(
        json.dumps(
            {
                "engine_version": _ENGINE_VERSION,
                "out_dir": str(out_dir),
                "decision_count": len(rows),
                "ticker_count": len(tickers),
                "first_decision": first_decision,
                "last_decision": last_decision,
                "forward_labels_csv_sha256": _sha256(csv_path),
                "source_records_json_sha256": _sha256(records_path),
                "evidence_sha256": source_records["evidence_sha256"],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
