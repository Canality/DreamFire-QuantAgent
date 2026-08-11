"""Public typed real-archive bridge for strictly-prior factor snapshots.

Consumes the hash-verified official calendar, the admitted operate-year
corporate-action archive (``corporate_action_operate_2020_2025/v1`` projected by
``dividOperateDate``), the E0 qfq snapshot, and the official 1+20 forward-label
archive; builds per-decision typed ``FactorSnapshot`` and ``OfficialForwardLabel``
objects and the ``CanonicalCalendarEvidence`` / ``SectorMetadataEvidence`` needed
by public ``compute_factor_research_snapshot``.  All admission is provider-owned
(first capability/readiness, then exact rebuild-and-compare).  No private
``_KERNELS`` access and no trust membership monkeypatching.
"""

from __future__ import annotations

import csv
import hashlib
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from jiuwenswarm.quant import factor_evidence_provider, official_calendar_archive
from jiuwenswarm.quant.candidate_factors import (
    CalendarEvidence,
    CorporateActionEvidence,
    FactorSnapshot,
    PointInTimeFactorInput,
    compute_trend_snapshot,
)
from jiuwenswarm.quant.factor_research import (
    CanonicalCalendarEvidence,
    MaturedFactorObservation,
    OfficialForwardLabel,
    SectorMetadataEvidence,
)

_SHANGHAI = ZoneInfo("Asia/Shanghai")
_OPERATE_POLICY = "scale_invariant_qfq_retrospective"
_OPERATE_RESULT = "SCALE_INVARIANT_QFQ_RETROSPECTIVE"
_OPERATE_AUTHORITY = "BAOSTOCK_QUERY_DIVIDEND_DATA_OPERATE"
_OPERATE_VERSION = "corporate_action_operate_2020_2025/v1"
_OPERATE_CALENDAR_ID = "SSE_SZSE_A_SHARE_CONFIRMED_THROUGH_20260804"
_CALENDAR_AUTHORITY = "SSE_SZSE_OFFICIAL_CALENDAR_ARCHIVE"
_CALENDAR_VERSION = "official_calendar_2024_2026/v1"
_LABEL_AUTHORITY = "PIT_OFFICIAL_FORWARD_LABEL_ARCHIVE"
_LABEL_VERSION = "official_forward_label_2024_2026/v2"
_LABEL_ARCHIVE_EVIDENCE = "c7c3d2b474fa2109a423e8dfe0d6d4f0283a8aff26a9c286c840584f0c6f7eba"
_SECTOR_AUTHORITY = "PIT_SECTOR_METADATA_ARCHIVE"
_SECTOR_VERSION = "competition_universe_static_v1"
_COVERAGE_START = "2020-01-01"
_COVERAGE_END = "2025-12-31"
_FORECAST_HORIZON = 20

# The frozen action identity fields (excluding ticker) - the full 8-tuple is
# (code,) + one value per field below.
_ACTION_IDENTITY_FIELDS: tuple[str, ...] = (
    "dividOperateDate",
    "dividCashPsBeforeTax",
    "dividCashPsAfterTax",
    "dividStocksPs",
    "dividReserveToStockPs",
    "dividCashStock",
    "dividPlanAnnounceDate",
)


class ResearchEvidenceError(RuntimeError):
    """Raised when a real archive cannot be consumed honestly."""


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_hash(payload: object) -> str:
    import json

    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _normalize_sh(ticker: str) -> str:
    """Normalize ``601318.SH`` -> ``sh.601318`` (the qfq/operate/label form)."""
    text = str(ticker).upper()
    if text.endswith(".SH"):
        return "sh." + text.split(".")[0].lower()
    if text.endswith(".SZ"):
        return "sz." + text.split(".")[0].lower()
    return str(ticker).lower()


def load_calendar_evidence() -> CalendarEvidence:
    """Build the full trusted CalendarEvidence over the 626 confirmed sessions."""
    calendar = official_calendar_archive.inspect_official_calendar_archive()
    if not calendar.verified:
        raise ResearchEvidenceError("official calendar archive is not verified")
    if calendar.calendar_id != _OPERATE_CALENDAR_ID:
        raise ResearchEvidenceError("unexpected calendar archive id")
    if len(calendar.confirmed_sessions) != 626:
        raise ResearchEvidenceError("official calendar must contain 626 confirmed sessions")
    return CalendarEvidence(
        authority=calendar.authority,
        source_version=calendar.source_version,
        source_sha256=calendar.source_sha256,
        calendar_id=calendar.calendar_id,
        sessions=tuple(calendar.confirmed_sessions),
    )


def load_canonical_calendar_evidence() -> CanonicalCalendarEvidence:
    """Build the trusted CanonicalCalendarEvidence over the full 626 sessions."""
    calendar = official_calendar_archive.inspect_official_calendar_archive()
    if not calendar.verified:
        raise ResearchEvidenceError("official calendar archive is not verified")
    if calendar.calendar_id != _OPERATE_CALENDAR_ID:
        raise ResearchEvidenceError("unexpected calendar archive id")
    return CanonicalCalendarEvidence(
        authority=_CALENDAR_AUTHORITY,
        source_version=_CALENDAR_VERSION,
        source_sha256=official_calendar_archive.ARCHIVE_SOURCE_SHA256,
        calendar_id=_OPERATE_CALENDAR_ID,
        sessions=tuple(calendar.confirmed_sessions),
    )


def load_sector_metadata_evidence() -> SectorMetadataEvidence:
    """Build the trusted SectorMetadataEvidence from the contest workbook.

    The provider-owned admission uses the pinned contest-workbook hash as the
    archive evidence; the typed evidence_hash binds the 49x6 sector projection
    with tickers normalized to the qfq ``sh.601318`` form so it matches the
    factor snapshots and labels.
    """

    from jiuwenswarm.quant.reporting import contest_universe_archive

    audit = contest_universe_archive.inspect_contest_universe_archive()
    if not audit.verified:
        raise ResearchEvidenceError("contest universe archive is not verified")
    sectors = tuple(
        sorted(
            (_normalize_sh(member.ticker), member.group_name)
            for member in audit.members
        )
    )
    if len(sectors) != 49 or len({t for t, _ in sectors}) != 49:
        raise ResearchEvidenceError("contest universe must bind 49 unique tickers")
    if len({name for _, name in sectors}) != 6:
        raise ResearchEvidenceError("contest universe must bind six sectors")
    archive_hash = factor_evidence_provider.OFFICIAL_UNIVERSE_SPEC.expected_sha256
    return SectorMetadataEvidence(
        authority=_SECTOR_AUTHORITY,
        source_version=_SECTOR_VERSION,
        source_sha256=archive_hash,
        archive_evidence_sha256=archive_hash,
        effective_date="2024-01-01",
        observed_at="2024-01-01T00:00:00+08:00",
        sectors=sectors,
    )


def load_operate_events() -> dict[str, tuple[tuple[str, ...], ...]]:
    """Return ticker -> sorted full 8-tuple action identities from the operate CSV."""
    if not factor_evidence_provider.OPERATE_CORPORATE_ACTION_SPECS:
        raise ResearchEvidenceError("operate archive is not pinned")
    csv_spec = factor_evidence_provider.OPERATE_CORPORATE_ACTION_SPECS[0]
    csv_path = _repository_root() / csv_spec.relative_path
    if _sha256(csv_path) != csv_spec.expected_sha256:
        raise ResearchEvidenceError("operate archive CSV hash mismatch")
    events: dict[str, list[tuple[str, ...]]] = {}
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            code = str(row["code"])
            identity = (code,) + tuple(str(row[field]) for field in _ACTION_IDENTITY_FIELDS)
            events.setdefault(code, []).append(identity)
    return {code: tuple(sorted(items)) for code, items in events.items()}


def build_corporate_action_evidence(
    *,
    window_sessions: pd.DatetimeIndex,
    tickers: Sequence[str],
) -> CorporateActionEvidence:
    """Per-window CorporateActionEvidence projected by dividOperateDate.

    ``window_sessions`` must be a strictly-prior window inside
    [2020-01-01, 2025-12-31]; in-window actions are the full 8-tuple identities
    from the hash-verified operate archive, preserving same-day multi-actions.
    """

    if not isinstance(window_sessions, pd.DatetimeIndex) or len(window_sessions) == 0:
        raise ResearchEvidenceError("window_sessions must be a non-empty DatetimeIndex")
    window_start = window_sessions[0].date().isoformat()
    window_end = window_sessions[-1].date().isoformat()
    if not (_COVERAGE_START <= window_start and window_end <= _COVERAGE_END):
        raise ResearchEvidenceError(
            "decision window is outside the operate archive coverage "
            "[2020-01-01, 2025-12-31]"
        )
    if not factor_evidence_provider.OPERATE_CORPORATE_ACTION_SPECS:
        raise ResearchEvidenceError("operate archive is not pinned")
    operate = factor_evidence_provider.inspect_corporate_action_operate_archive()
    if not operate.verified:
        raise ResearchEvidenceError("operate archive is not verified")
    csv_spec = factor_evidence_provider.OPERATE_CORPORATE_ACTION_SPECS[0]
    records_spec = factor_evidence_provider.OPERATE_CORPORATE_ACTION_SPECS[1]
    tickers_sorted = tuple(sorted({str(t) for t in tickers}))
    try:
        in_window = factor_evidence_provider.operate_window_projection(
            window_start=window_start,
            window_end=window_end,
            tickers=tickers_sorted,
        )
    except ValueError as exc:
        raise ResearchEvidenceError(str(exc)) from exc
    return CorporateActionEvidence(
        authority=_OPERATE_AUTHORITY,
        source_version=_OPERATE_VERSION,
        source_sha256=records_spec.expected_sha256,
        archive_evidence_sha256=csv_spec.expected_sha256,
        policy=_OPERATE_POLICY,
        window_start=window_start,
        window_end=window_end,
        ticker_results=tuple(
            (ticker, _OPERATE_RESULT) for ticker in tickers_sorted
        ),
        in_window_actions=tuple(sorted(in_window)),
    )


def load_wide_closes(session_dates: Sequence[str]) -> pd.DataFrame:
    """Wide close DataFrame reindexed to the exact window session dates."""
    if not factor_evidence_provider.E0_SNAPSHOT_CSV_SPEC:
        raise ResearchEvidenceError("E0 qfq snapshot is not pinned")
    spec = factor_evidence_provider.E0_SNAPSHOT_CSV_SPEC
    qfq_path = _repository_root() / spec.relative_path
    if _sha256(qfq_path) != spec.expected_sha256:
        raise ResearchEvidenceError("E0 qfq snapshot hash mismatch")

    by_date: dict[str, dict[str, str]] = {}
    with qfq_path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            by_date.setdefault(str(row["date"]), {})[str(row["code"])] = str(row["close"])
    if not session_dates:
        raise ResearchEvidenceError("no session dates requested")
    first_date = str(session_dates[0])
    tickers = sorted(by_date.get(first_date, {}).keys())
    index = pd.DatetimeIndex(pd.to_datetime(list(session_dates)))
    frame = pd.DataFrame(
        {
            ticker: [float(by_date[date][ticker]) for date in session_dates]
            for ticker in tickers
        },
        index=index,
        dtype=float,
    )
    return frame


def build_factor_input(
    *,
    decision_date: str,
    lookback: int = 251,
) -> PointInTimeFactorInput:
    """Strictly-prior 251-session PointInTimeFactorInput ending at decision_date.

    ``decision_date`` may be a plain session date (``YYYY-MM-DD``) or a full
    tz-aware decision timestamp; the decision session is always the normalized
    trading-day date and the decision_time is always the exact 15:00 Asia/Shanghai
    close (no string truncation of a supplied timestamp).
    """

    if lookback < 251:
        raise ResearchEvidenceError("lookback must be at least 251 for full 12-factor coverage")
    calendar = load_calendar_evidence()
    sessions = pd.DatetimeIndex(pd.to_datetime(list(calendar.sessions)))
    decision_ts = pd.Timestamp(decision_date)
    if decision_ts.tzinfo is not None:
        decision = pd.Timestamp(decision_ts.tz_convert(_SHANGHAI).date())
    else:
        decision = decision_ts.normalize()
    try:
        position = int(sessions.get_loc(decision))
    except (KeyError, TypeError) as exc:
        raise ResearchEvidenceError(
            f"decision date {decision.date().isoformat()} is not a confirmed calendar session"
        ) from exc
    if position < lookback - 1:
        raise ResearchEvidenceError(
            f"decision date {decision.date().isoformat()} has fewer than {lookback} prior sessions"
        )
    window = sessions[position - lookback + 1 : position + 1]
    closes = load_wide_closes([d.date().isoformat() for d in window])
    corporate = build_corporate_action_evidence(
        window_sessions=window,
        tickers=list(closes.columns),
    )
    decision_time = datetime(
        decision.year,
        decision.month,
        decision.day,
        15,
        0,
        tzinfo=_SHANGHAI,
    )
    return PointInTimeFactorInput(
        closes=closes,
        canonical_sessions=window,
        decision_time=decision_time,
        adjustment_policy=_OPERATE_POLICY,
        calendar_evidence=calendar,
        corporate_action_evidence=corporate,
        forecast_horizon=_FORECAST_HORIZON,
    )


def compute_49x12_snapshot(*, decision_date: str) -> FactorSnapshot:
    """Compute a strictly-prior 49-stock x 12-factor snapshot via the public API."""
    return compute_trend_snapshot(build_factor_input(decision_date=decision_date))


def verify_factor_snapshot(snapshot: FactorSnapshot) -> bool:
    """Provider-gated authoritative projection check for a typed FactorSnapshot.

    First the provider-owned E0 archive admission is consulted
    (trusted_factor_snapshot_contains(snapshot.archive_evidence_sha256), which
    requires current E0 CSV/records readiness and ready_for_e0).  Then the
    authoritative snapshot is recomputed from the pinned archives and the full
    typed payload (input_hash + snapshot_hash) must match exactly.
    """

    if not factor_evidence_provider.trusted_factor_snapshot_contains(
        snapshot.archive_evidence_sha256
    ):
        raise ResearchEvidenceError("E0 archive is not admitted")
    authoritative = compute_49x12_snapshot(decision_date=snapshot.decision_time)
    if snapshot.input_hash != authoritative.input_hash:
        raise ResearchEvidenceError("factor snapshot input does not match the archive projection")
    if snapshot.snapshot_hash != authoritative.snapshot_hash:
        raise ResearchEvidenceError("factor snapshot payload does not match the archive projection")
    return True


def _load_label_archive() -> dict[str, dict[str, Any]]:
    """Read the hash-verified forward-label CSV + source_records into rows.

    Returns a dict keyed by decision_date with the parsed CSV row plus the
    verified source_records metadata.  The CSV bytes must equal
    FORWARD_LABEL_CSV_SPEC and the records bytes must equal
    FORWARD_LABEL_RECORDS_SPEC.
    """

    csv_spec = factor_evidence_provider.FORWARD_LABEL_CSV_SPEC
    records_spec = factor_evidence_provider.FORWARD_LABEL_RECORDS_SPEC
    csv_path = _repository_root() / csv_spec.relative_path
    records_path = _repository_root() / records_spec.relative_path
    if _sha256(csv_path) != csv_spec.expected_sha256:
        raise ResearchEvidenceError("forward-label CSV hash mismatch")
    if _sha256(records_path) != records_spec.expected_sha256:
        raise ResearchEvidenceError("forward-label source_records hash mismatch")
    records = _json_loads(records_path)
    if records.get("schema") != "official_forward_label/v2":
        raise ResearchEvidenceError("forward-label source_records schema mismatch")
    expected_evidence = records.get("evidence_sha256")
    recomputed_evidence = _canonical_hash(
        {k: v for k, v in records.items() if k != "evidence_sha256"}
    )
    if expected_evidence != recomputed_evidence:
        raise ResearchEvidenceError("forward-label evidence_sha256 not recomputable")
    if records.get("e0_csv_sha256") != factor_evidence_provider.E0_SNAPSHOT_CSV_SPEC.expected_sha256:
        raise ResearchEvidenceError("forward-label E0 CSV identity mismatch")
    if records.get("e0_records_sha256") != factor_evidence_provider.E0_SNAPSHOT_RECORDS_SPEC.expected_sha256:
        raise ResearchEvidenceError("forward-label E0 records identity mismatch")
    if records.get("calendar_source_sha256") != official_calendar_archive.ARCHIVE_SOURCE_SHA256:
        raise ResearchEvidenceError("forward-label calendar source identity mismatch")
    if records.get("calendar_evidence_sha256") != official_calendar_archive.EXPECTED_CALENDAR_EVIDENCE_SHA256:
        raise ResearchEvidenceError("forward-label calendar evidence identity mismatch")
    per_decision = records.get("per_decision")
    if not isinstance(per_decision, dict):
        raise ResearchEvidenceError("forward-label source_records per_decision missing")
    rows_by_decision: dict[str, dict[str, Any]] = {}
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            decision = str(row["decision_date"])
            if decision in rows_by_decision:
                raise ResearchEvidenceError(f"duplicate label decision {decision}")
            rows_by_decision[decision] = dict(row)
    if len(rows_by_decision) != 604 or len(per_decision) != 604:
        raise ResearchEvidenceError("forward-label archive must contain exactly 604 decisions")
    if set(rows_by_decision) != set(per_decision):
        raise ResearchEvidenceError("forward-label CSV decisions differ from source_records")
    if records.get("embargo_trading_days") != 1 or records.get("holding_days") != 20:
        raise ResearchEvidenceError("forward-label 1+20 params mismatch")
    for decision, row in rows_by_decision.items():
        expected_row_hash = (per_decision.get(decision) or {}).get("canonical_row_hash")
        if expected_row_hash != _canonical_hash(row):
            raise ResearchEvidenceError(
                f"forward-label CSV row for {decision} does not match source_records"
            )
    return {"rows": rows_by_decision, "records": records}


def _json_loads(path: Path) -> dict:
    import json

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ResearchEvidenceError("forward-label source_records unreadable") from exc
    if not isinstance(payload, dict):
        raise ResearchEvidenceError("forward-label source_records must be an object")
    return payload


def _build_forward_label(
    decision: str,
    row: dict,
    calendar: CanonicalCalendarEvidence,
) -> OfficialForwardLabel:
    sessions = pd.DatetimeIndex(pd.to_datetime(list(calendar.sessions)))
    decision_ts = pd.Timestamp(decision)
    try:
        position = int(sessions.get_loc(decision_ts))
    except (KeyError, TypeError) as exc:
        raise ResearchEvidenceError(f"label decision {decision} absent from calendar") from exc
    window = sessions[position : position + 22]
    if len(window) != 22:
        raise ResearchEvidenceError(f"label decision {decision} has no complete 1+20 window")
    embargo = window[1].date().isoformat()
    entry = window[2].date().isoformat()
    valuations = tuple(s.date().isoformat() for s in window[2:22])
    exit_day = window[21].date().isoformat()
    if str(row.get("entry_open_date", "")) != entry:
        raise ResearchEvidenceError(
            f"label decision {decision} CSV entry_open_date does not match the "
            "canonical entry session (one full embargo day)"
        )
    if str(row.get("exit_close_date", "")) != exit_day:
        raise ResearchEvidenceError(
            f"label decision {decision} CSV exit_close_date does not match the canonical exit session"
        )
    csv_valuations = [
        value for value in str(row.get("valuation_dates", "")).split("|") if value
    ]
    if tuple(csv_valuations) != valuations:
        raise ResearchEvidenceError(
            f"label decision {decision} CSV valuation dates do not match the canonical window"
        )
    entry_open: list[tuple[str, float | None]] = []
    exit_close: list[tuple[str, float | None]] = []
    for key, value in row.items():
        if key.endswith("_entry_open"):
            ticker = key[: -len("_entry_open")]
            entry_open.append((ticker, None if value == "" else float(value)))
        elif key.endswith("_exit_close"):
            ticker = key[: -len("_exit_close")]
            exit_close.append((ticker, None if value == "" else float(value)))
    if sorted(t for t, _ in entry_open) != sorted(t for t, _ in exit_close) or len(entry_open) != 49:
        raise ResearchEvidenceError(f"label decision {decision} must bind exactly 49 tickers")
    available_at = f"{exit_day}T15:00:00+08:00"
    return OfficialForwardLabel(
        authority=_LABEL_AUTHORITY,
        source_version=_LABEL_VERSION,
        source_sha256=factor_evidence_provider.FORWARD_LABEL_RECORDS_SPEC.expected_sha256,
        archive_evidence_sha256=_LABEL_ARCHIVE_EVIDENCE,
        calendar_id=calendar.calendar_id,
        calendar_evidence_hash=calendar.evidence_hash,
        decision_date=decision,
        embargo_date=embargo,
        entry_date=entry,
        valuation_dates=valuations,
        exit_date=exit_day,
        available_at=available_at,
        entry_open=tuple(sorted(entry_open)),
        exit_close=tuple(sorted(exit_close)),
    )


def load_forward_labels() -> tuple[OfficialForwardLabel, ...]:
    """Load the COMPLETE 604-label archive (no maturity pre-filter)."""
    archive = _load_label_archive()
    calendar = load_canonical_calendar_evidence()
    labels = tuple(
        _build_forward_label(decision, row, calendar)
        for decision, row in sorted(archive["rows"].items())
    )
    return labels


def verify_forward_label(label: OfficialForwardLabel) -> bool:
    """Provider-gated authoritative projection check for a typed label.

    First the provider-owned label archive admission is consulted
    (trusted_evidence_contains with the pinned records hash + archive evidence
    manifest identity).  Then the authoritative label is rebuilt from the pinned
    CSV + trusted calendar and the FULL typed payload / evidence_hash must match.
    """

    if not factor_evidence_provider.trusted_evidence_contains(
        kind="official_forward_label",
        authority=_LABEL_AUTHORITY,
        source_version=_LABEL_VERSION,
        source_sha256=factor_evidence_provider.FORWARD_LABEL_RECORDS_SPEC.expected_sha256,
        evidence_hash=_LABEL_ARCHIVE_EVIDENCE,
    ):
        raise ResearchEvidenceError("official forward-label archive is not admitted")
    archive = _load_label_archive()
    calendar = load_canonical_calendar_evidence()
    if label.decision_date not in archive["rows"]:
        raise ResearchEvidenceError(f"label decision {label.decision_date} absent from archive")
    authoritative = _build_forward_label(
        label.decision_date,
        archive["rows"][label.decision_date],
        calendar,
    )
    if label.to_dict() != authoritative.to_dict():
        raise ResearchEvidenceError(
            "label payload does not match the authoritative archive projection"
        )
    return True


def verify_sector_metadata(evidence: SectorMetadataEvidence) -> bool:
    """Provider-gated authoritative projection check for typed sector metadata.

    First the provider-owned official-universe archive admission is consulted
    (trusted_evidence_contains with the pinned contest-workbook hash).  Then the
    authoritative normalized 49x6 sector mapping is rebuilt from the pinned
    workbook and the FULL typed payload / evidence_hash must match, so a caller
    that swaps sector assignments while preserving counts and the archive hash
    is rejected.
    """

    archive_hash = factor_evidence_provider.OFFICIAL_UNIVERSE_SPEC.expected_sha256
    if not factor_evidence_provider.trusted_evidence_contains(
        kind="sector_metadata",
        authority=_SECTOR_AUTHORITY,
        source_version=_SECTOR_VERSION,
        source_sha256=archive_hash,
        evidence_hash=archive_hash,
    ):
        raise ResearchEvidenceError("official universe archive is not admitted")
    authoritative = load_sector_metadata_evidence()
    if evidence.to_dict() != authoritative.to_dict():
        raise ResearchEvidenceError(
            "sector metadata payload does not match the authoritative workbook projection"
        )
    return True


def build_factor_research_observations(
    decision_dates: Sequence[str],
) -> tuple[MaturedFactorObservation, ...]:
    """Build strictly-prior matured observations (snapshot + label) for decisions."""
    labels = {label.decision_date: label for label in load_forward_labels()}
    observations = []
    for decision in decision_dates:
        if decision not in labels:
            raise ResearchEvidenceError(f"decision {decision} has no forward label")
        snapshot = compute_49x12_snapshot(decision_date=decision)
        verify_factor_snapshot(snapshot)
        observations.append(MaturedFactorObservation(snapshot, labels[decision]))
    return tuple(observations)
