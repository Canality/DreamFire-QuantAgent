"""Official A-share calendar archive and admission tests."""

from __future__ import annotations

import hashlib
import inspect
import json
import shutil
from dataclasses import replace
from pathlib import Path

import pytest

from jiuwenswarm.quant import official_calendar_archive as calendar_archive
from jiuwenswarm.quant.factor_research import (
    FACTOR_RESEARCH_POLICY,
    CanonicalCalendarEvidence,
)


def _copy_archive(destination: Path) -> None:
    source_root = calendar_archive._repository_root()  # type: ignore[attr-defined]
    for spec in calendar_archive.PINNED_CALENDAR_FILES:
        source = source_root / spec.relative_path
        target = destination / spec.relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def _repin(
    monkeypatch: pytest.MonkeyPatch,
    *,
    source_records_path: Path | None = None,
    sessions_path: Path | None = None,
) -> None:
    source_spec = calendar_archive.SOURCE_RECORDS_SPEC
    sessions_spec = calendar_archive.CALENDAR_SESSIONS_SPEC
    if source_records_path is not None:
        source_spec = replace(
            source_spec,
            expected_sha256=hashlib.sha256(
                source_records_path.read_bytes()
            ).hexdigest(),
        )
    if sessions_path is not None:
        sessions_spec = replace(
            sessions_spec,
            expected_sha256=hashlib.sha256(sessions_path.read_bytes()).hexdigest(),
        )
    monkeypatch.setattr(
        calendar_archive,
        "PINNED_CALENDAR_FILES",
        (source_spec, sessions_spec),
    )


def test_official_archive_is_complete_but_future_dates_remain_scheduled() -> None:
    archive = calendar_archive.inspect_official_calendar_archive()

    assert archive.verified is True
    assert archive.archive_id == "sse_szse_a_share_calendar_2024_2026_v1"
    assert archive.coverage_start == "2024-01-01"
    assert archive.coverage_end == "2026-12-31"
    assert archive.confirmation_cutoff == "2026-08-04"
    assert archive.total_calendar_days == 1096
    assert archive.confirmed_session_count == 626
    assert archive.scheduled_session_count == 727
    assert archive.confirmed_sessions[-1] == "2026-08-04"
    assert "2026-08-05" not in archive.confirmed_sessions
    assert "2026-08-05" in archive.scheduled_sessions
    assert archive.status_counts == (
        ("CONFIRMED_CLOSED", 51),
        ("CONFIRMED_OPEN", 626),
        ("SCHEDULED_CLOSED", 48),
        ("SCHEDULED_OPEN", 101),
        ("WEEKEND_CLOSED", 270),
    )
    assert archive.to_dict() == (
        calendar_archive.inspect_official_calendar_archive().to_dict()
    )


def test_confirmed_archive_constructs_the_only_admitted_calendar() -> None:
    archive = calendar_archive.inspect_official_calendar_archive()
    evidence = CanonicalCalendarEvidence(
        authority=archive.authority,
        source_version=archive.source_version,
        source_sha256=archive.source_sha256,
        calendar_id=archive.calendar_id,
        sessions=archive.confirmed_sessions,
    )

    sessions = evidence.validate(policy=FACTOR_RESEARCH_POLICY)
    assert len(sessions) == 626
    assert sessions[-1].date().isoformat() == "2026-08-04"

    future_forgery = CanonicalCalendarEvidence(
        authority=archive.authority,
        source_version=archive.source_version,
        source_sha256=archive.source_sha256,
        calendar_id=archive.calendar_id,
        sessions=archive.scheduled_sessions,
    )
    with pytest.raises(ValueError, match="trusted source manifest"):
        future_forgery.validate(policy=FACTOR_RESEARCH_POLICY)


def test_public_calendar_api_has_no_path_hash_or_cutoff_injection() -> None:
    parameters = tuple(
        inspect.signature(calendar_archive.inspect_official_calendar_archive).parameters
    )
    assert parameters == ()
    with pytest.raises(TypeError):
        calendar_archive.inspect_official_calendar_archive(  # type: ignore[call-arg]
            path="attacker",
            confirmation_cutoff="2099-12-31",
        )


def test_calendar_archive_rejects_missing_tampered_and_extra_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _copy_archive(tmp_path)
    monkeypatch.setattr(calendar_archive, "_repository_root", lambda: tmp_path)
    assert calendar_archive.inspect_official_calendar_archive().verified

    sessions_path = tmp_path / calendar_archive.CALENDAR_SESSIONS_SPEC.relative_path
    original = sessions_path.read_bytes()
    sessions_path.write_bytes(sessions_path.read_bytes() + b"tamper")
    assert not calendar_archive.inspect_official_calendar_archive().verified

    sessions_path.write_bytes(original)
    sessions_path.unlink()
    missing = calendar_archive.inspect_official_calendar_archive()
    assert missing.verified is False
    assert (
        next(
            item
            for item in missing.files
            if item.artifact_id == "official_calendar_sessions"
        ).reason
        == "MISSING_FILE"
    )

    sessions_path.write_bytes(original)
    extra = sessions_path.parent / "attacker.csv"
    extra.write_text("surplus", encoding="utf-8")
    assert "UNEXPECTED_CALENDAR_FILE_SET" in (
        calendar_archive.inspect_official_calendar_archive().errors
    )


def test_self_consistent_wrong_market_source_still_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _copy_archive(tmp_path)
    source_path = tmp_path / calendar_archive.SOURCE_RECORDS_SPEC.relative_path
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    payload["sources"][0]["title"] = "港股通交易日历"
    source_path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    _repin(monkeypatch, source_records_path=source_path)
    monkeypatch.setattr(calendar_archive, "_repository_root", lambda: tmp_path)

    audit = calendar_archive.inspect_official_calendar_archive()
    assert audit.verified is False
    assert "UNTRUSTED_OR_WRONG_MARKET_SOURCE" in audit.errors


def test_coordinated_repin_cannot_substitute_an_opaque_daily_result_hash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _copy_archive(tmp_path)
    source_path = tmp_path / calendar_archive.SOURCE_RECORDS_SPEC.relative_path
    sessions_path = tmp_path / calendar_archive.CALENDAR_SESSIONS_SPEC.relative_path
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    target = next(
        record for record in payload["daily_query_ledger"] if record["result_rows"] == 3
    )
    original_hash = target["canonical_result_sha256"]
    forged_hash = "a" * 64
    target["canonical_result_sha256"] = forged_hash
    canonical_jsonl = "".join(
        json.dumps(
            record,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
        for record in payload["daily_query_ledger"]
    ).encode("utf-8")
    daily_source = next(
        source
        for source in payload["sources"]
        if source["record_kind"] == "DAILY_MARKET_STATISTICS_API"
    )
    daily_source["raw_sha256"] = hashlib.sha256(canonical_jsonl).hexdigest()
    source_path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    sessions_path.write_text(
        sessions_path.read_text(encoding="utf-8").replace(
            original_hash,
            forged_hash,
            1,
        ),
        encoding="utf-8",
    )
    _repin(
        monkeypatch,
        source_records_path=source_path,
        sessions_path=sessions_path,
    )
    monkeypatch.setattr(calendar_archive, "_repository_root", lambda: tmp_path)

    audit = calendar_archive.inspect_official_calendar_archive()
    assert audit.verified is False
    assert "DAILY_RESULT_PAYLOAD_HASH_MISMATCH" in audit.errors


def test_self_consistent_future_confirmation_and_truncation_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _copy_archive(tmp_path)
    sessions_path = tmp_path / calendar_archive.CALENDAR_SESSIONS_SPEC.relative_path
    original = sessions_path.read_text(encoding="utf-8")
    forged = original.replace(
        "2026-08-05,WEDNESDAY,OPEN,SCHEDULED_OPEN,NONE,2026,,,,",
        "2026-08-05,WEDNESDAY,OPEN,CONFIRMED_OPEN,NONE,2026,3,20260805,"
        "主板|科创板|股票," + "a" * 64,
    )
    sessions_path.write_text(forged, encoding="utf-8")
    _repin(monkeypatch, sessions_path=sessions_path)
    monkeypatch.setattr(calendar_archive, "_repository_root", lambda: tmp_path)
    assert "CONFIRMATION_STATUS_MISMATCH" in (
        calendar_archive.inspect_official_calendar_archive().errors
    )

    sessions_path.write_text(
        "\n".join(original.splitlines()[:-1]) + "\n", encoding="utf-8"
    )
    _repin(monkeypatch, sessions_path=sessions_path)
    truncated = calendar_archive.inspect_official_calendar_archive()
    assert truncated.verified is False
    assert "CALENDAR_DAY_COUNT_MISMATCH" in truncated.errors


def test_symlinked_calendar_file_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _copy_archive(tmp_path)
    sessions_path = tmp_path / calendar_archive.CALENDAR_SESSIONS_SPEC.relative_path
    real_path = sessions_path.with_name("real-sessions.csv")
    sessions_path.replace(real_path)
    try:
        sessions_path.symlink_to(real_path.name)
    except OSError as exc:  # Windows may not grant symlink permission.
        pytest.skip(f"symlink creation unavailable: {exc}")
    monkeypatch.setattr(calendar_archive, "_repository_root", lambda: tmp_path)

    audit = calendar_archive.inspect_official_calendar_archive()
    assert audit.verified is False
    assert (
        next(
            item
            for item in audit.files
            if item.artifact_id == "official_calendar_sessions"
        ).reason
        == "SYMLINK_REJECTED"
    )


def test_contest_window_is_scheduled_not_historical_confirmation() -> None:
    archive = calendar_archive.inspect_official_calendar_archive()
    scheduled = archive.scheduled_sessions
    decision_index = scheduled.index("2026-08-21")

    assert scheduled[decision_index + 1] == "2026-08-24"
    assert scheduled[decision_index + 2] == "2026-08-25"
    assert scheduled[decision_index + 21] == "2026-09-21"
    assert all(
        day not in archive.confirmed_sessions for day in scheduled[decision_index:]
    )
