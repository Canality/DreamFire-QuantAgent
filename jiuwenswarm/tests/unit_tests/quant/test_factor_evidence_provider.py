"""Fail-closed archive and trust-boundary tests for WP1 evidence providers."""

from __future__ import annotations

import hashlib
import inspect
import json
import shutil
import sys
from pathlib import Path

import pytest
from jiuwenswarm.quant import factor_evidence_provider as provider

EXPECTED_CAPABILITIES = {
    "CANONICAL_CALENDAR": (
        True,
        "AVAILABLE_OFFICIAL_SSE_SZSE_CONFIRMED_ARCHIVE",
    ),
    "PIT_SECTOR": (
        True,
        "AVAILABLE_STATIC_COMPETITION_SECTORS",
    ),
    "OFFICIAL_FORWARD_LABEL": (
        True,
        "AVAILABLE_OFFICIAL_1_20_FORWARD_LABEL_ARCHIVE",
    ),
    "PIT_CORPORATE_ACTION": (
        True,
        "AVAILABLE_BAOSTOCK_DIVIDEND_ARCHIVE",
    ),
    "E0_FACTOR_SNAPSHOT": (
        True,
        "AVAILABLE_BAOSTOCK_QFQ_SNAPSHOT_ARCHIVE",
    ),
    "PIT_CORPORATE_ACTION_OPERATE": (
        True,
        "AVAILABLE_BAOSTOCK_OPERATE_DIVIDEND_ARCHIVE",
    ),
}


def _copy_inventory(destination: Path) -> None:
    source_root = provider._repository_root()  # type: ignore[attr-defined]
    for spec in provider.PINNED_SOURCE_FILES:
        source = source_root / spec.relative_path
        target = destination / spec.relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def test_current_bytes_admit_only_the_official_calendar_capability() -> None:
    readiness = provider.inspect_research_evidence_readiness()

    assert readiness.inventory_id == "wp1_factor_evidence_inventory_v1"
    assert readiness.source_bytes_verified is True
    assert len(readiness.sources) == 14
    assert all(item.verified for item in readiness.sources)
    assert readiness.calendar_archive_verified is True
    assert readiness.calendar_confirmation_cutoff == "2026-08-04"
    assert readiness.calendar_confirmed_session_count == 626
    assert readiness.calendar_scheduled_session_count == 727
    assert {
        item.capability: (
            item.available,
            item.reason,
        )
        for item in readiness.capabilities
    } == {
        capability: (
            expected[0],
            expected[1],
        )
        if isinstance(expected, tuple)
        else (False, expected)
        for capability, expected in EXPECTED_CAPABILITIES.items()
    }
    assert readiness.ready_for_e0 is True
    assert readiness.ready_for_e1 is True
    assert readiness.trusted_evidence_key_count == 5
    assert readiness.trusted_factor_snapshot_count == 1
    assert readiness.to_dict() == provider.inspect_research_evidence_readiness().to_dict()


def test_public_readiness_api_has_no_path_hash_or_allowlist_injection() -> None:
    assert tuple(inspect.signature(provider.inspect_research_evidence_readiness).parameters) == ()
    with pytest.raises(TypeError):
        provider.inspect_research_evidence_readiness(  # type: ignore[call-arg]
            path="attacker"
        )

    trust_parameters = tuple(
        inspect.signature(provider.trusted_evidence_contains).parameters
    )
    assert trust_parameters == (
        "kind",
        "authority",
        "source_version",
        "source_sha256",
        "evidence_hash",
    )
    assert "path" not in trust_parameters
    assert "allowlist" not in trust_parameters


def test_real_operate_archive_is_admitted_and_capability_available() -> None:
    readiness = provider.inspect_research_evidence_readiness()
    operate = next(
        item
        for item in readiness.capabilities
        if item.capability == "PIT_CORPORATE_ACTION_OPERATE"
    )
    assert operate.available is True
    assert operate.reason == "AVAILABLE_BAOSTOCK_OPERATE_DIVIDEND_ARCHIVE"
    parsed = provider.inspect_corporate_action_operate_archive()
    assert parsed.verified is True
    assert parsed.receipt_count == 294
    assert parsed.ticker_count == 49
    assert parsed.total_rows > 0
    assert provider._operate_key_admitted() is True
    assert len(provider.OPERATE_CORPORATE_ACTION_SPECS) == 2


def test_fixed_inventory_rejects_tampering_missing_and_extra_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _copy_inventory(tmp_path)
    monkeypatch.setattr(provider, "_repository_root", lambda: tmp_path)
    assert provider.inspect_research_evidence_readiness().source_bytes_verified

    open_path = tmp_path / provider.SINA_OPEN_SPEC.relative_path
    original_open = open_path.read_bytes()
    open_path.write_bytes(original_open + b"tamper")
    tampered = provider.inspect_research_evidence_readiness()
    assert tampered.source_bytes_verified is False
    assert next(item for item in tampered.sources if item.artifact_id == "sina_open").reason == "SHA256_MISMATCH"

    open_path.write_bytes(original_open)
    close_path = tmp_path / provider.SINA_CLOSE_SPEC.relative_path
    original_close = close_path.read_bytes()
    close_path.unlink()
    missing = provider.inspect_research_evidence_readiness()
    assert missing.source_bytes_verified is False
    assert next(item for item in missing.sources if item.artifact_id == "sina_close").reason == "MISSING_FILE"

    close_path.write_bytes(original_close)
    extra = close_path.parent / "unregistered.csv"
    extra.write_text("not pinned", encoding="utf-8")
    surplus = provider.inspect_research_evidence_readiness()
    assert surplus.source_bytes_verified is False
    assert "UNEXPECTED_SNAPSHOT_FILE_SET" in surplus.inventory_errors


def test_fixed_inventory_rejects_symlinked_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _copy_inventory(tmp_path)
    open_path = tmp_path / provider.SINA_OPEN_SPEC.relative_path
    real_path = open_path.with_name("real-open.csv.gz")
    open_path.replace(real_path)
    try:
        open_path.symlink_to(real_path.name)
    except OSError as exc:  # Windows may not grant symlink permission.
        pytest.skip(f"symlink creation unavailable: {exc}")
    monkeypatch.setattr(provider, "_repository_root", lambda: tmp_path)

    readiness = provider.inspect_research_evidence_readiness()
    assert readiness.source_bytes_verified is False
    assert next(item for item in readiness.sources if item.artifact_id == "sina_open").reason == "SYMLINK_REJECTED"


def test_calendar_root_is_exact_and_other_caller_claims_are_rejected() -> None:
    assert isinstance(provider._TRUSTED_EVIDENCE_KEYS, frozenset)  # type: ignore[attr-defined]
    assert isinstance(provider._TRUSTED_FACTOR_SNAPSHOT_HASHES, frozenset)  # type: ignore[attr-defined]
    calendar = provider.official_calendar_archive.inspect_official_calendar_archive()
    assert provider.trusted_evidence_contains(
        kind="calendar",
        authority=calendar.authority,
        source_version=calendar.source_version,
        source_sha256=calendar.source_sha256,
        evidence_hash=calendar.evidence_hash,
    )
    assert provider.trusted_evidence_contains(
        kind="canonical_calendar",
        authority=calendar.authority,
        source_version=calendar.source_version,
        source_sha256=calendar.source_sha256,
        evidence_hash=calendar.evidence_hash,
    )
    assert not provider.trusted_evidence_contains(
        kind="calendar",
        authority="SSE_SZSE_OFFICIAL_CALENDAR_ARCHIVE",
        source_version="caller/v1",
        source_sha256="a" * 64,
        evidence_hash="b" * 64,
    )
    assert not provider.trusted_factor_snapshot_contains("c" * 64)
    assert not provider.trusted_factor_snapshot_contains("not-a-hash")


def test_membership_alone_cannot_bypass_unavailable_archives(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    key = (
        "canonical_calendar",
        "SSE_SZSE_OFFICIAL_CALENDAR_ARCHIVE",
        "future-provider/v1",
        "a" * 64,
        "b" * 64,
    )

    def _unavailable(root: object, spec) -> provider.SourceFileVerification:
        return provider.SourceFileVerification(
            artifact_id=spec.artifact_id,
            relative_path=str(spec.relative_path),
            expected_sha256=spec.expected_sha256,
            actual_sha256="0" * 64,
            verified=False,
            reason="SIMULATED_UNAVAILABLE",
        )

    # Render the archives unavailable FIRST, then confirm allowlist membership
    # alone cannot bypass admission.
    monkeypatch.setattr(provider, "_verify_source_file", _unavailable)
    monkeypatch.setattr(provider, "_TRUSTED_EVIDENCE_KEYS", frozenset({key}))
    monkeypatch.setattr(
        provider,
        "_TRUSTED_FACTOR_SNAPSHOT_HASHES",
        frozenset({"c" * 64}),
    )

    readiness = provider.inspect_research_evidence_readiness()
    assert readiness.source_bytes_verified is False
    assert readiness.ready_for_e0 is False
    assert readiness.ready_for_e1 is False
    assert readiness.trusted_evidence_key_count == 1
    assert readiness.trusted_factor_snapshot_count == 1
    assert not provider.trusted_evidence_contains(
        kind=key[0],
        authority=key[1],
        source_version=key[2],
        source_sha256=key[3],
        evidence_hash=key[4],
    )
    assert not provider.trusted_factor_snapshot_contains("c" * 64)


def _pin_operate_specs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    csv_path: Path,
    records_path: Path,
    *,
    admit_key: bool = True,
) -> None:
    csv_spec = provider.PinnedSourceFile(
        artifact_id="operate_corporate_actions_csv",
        relative_path=csv_path.relative_to(tmp_path),
        expected_sha256=hashlib.sha256(csv_path.read_bytes()).hexdigest(),
    )
    records_spec = provider.PinnedSourceFile(
        artifact_id="operate_corporate_actions_records",
        relative_path=records_path.relative_to(tmp_path),
        expected_sha256=hashlib.sha256(records_path.read_bytes()).hexdigest(),
    )
    monkeypatch.setattr(
        provider,
        "OPERATE_CORPORATE_ACTION_SPECS",
        (csv_spec, records_spec),
    )
    if admit_key:
        key = provider._operate_trusted_key()
        assert key is not None
        monkeypatch.setattr(
            provider,
            "_TRUSTED_EVIDENCE_KEYS",
            provider._TRUSTED_EVIDENCE_KEYS | {key},
        )


def _operate_receipt(
    code: str,
    year: str,
    *,
    rows: list[list[str]] | None = None,
) -> dict:
    rows = rows or []
    fields = list(provider._OPERATE_CANONICAL_COLUMNS[1:])
    return {
        "code": code,
        "year": year,
        "yearType": "operate",
        "request_start": "2026-08-10T00:00:00+00:00",
        "request_end": "2026-08-10T00:00:05+00:00",
        "error_code": "0",
        "error_msg": "",
        "fields": fields,
        "rows": rows,
        "row_count": len(rows),
        "response_payload_sha256": provider._canonical_hash(
            {"fields": fields, "rows": rows}
        ),
        "max_event_date": None,
        "duplicate_count": 0,
        "failed": False,
    }


def _write_operate_archive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    manifest_mutator=None,
    csv_lines: list[list[str]] | None = None,
    receipt_mutator=None,
    admit_key: bool = True,
) -> tuple[Path, Path, tuple[str, ...]]:
    _copy_inventory(tmp_path)
    manifest_copy = tmp_path / provider.SINA_MANIFEST_SPEC.relative_path
    manifest_copy.write_bytes(
        manifest_copy.read_text(encoding="utf-8").replace("\r\n", "\n").encode("utf-8")
    )
    monkeypatch.setattr(provider, "_repository_root", lambda: tmp_path)
    directory = tmp_path / provider._OPERATE_ARCHIVE_RELATIVE_DIRECTORY
    directory.mkdir(parents=True, exist_ok=True)
    csv_path = directory / "corporate_actions.csv"
    records_path = directory / "source_records.json"
    official = provider._official_operate_tickers(tmp_path)
    receipts = []
    for code in official:
        for year in provider._OPERATE_YEARS:
            receipt = _operate_receipt(code, year)
            if receipt_mutator is not None:
                receipt_mutator(receipt)
            receipts.append(receipt)
    manifest = {
        "schema": provider._OPERATE_SCHEMA,
        "archive_id": provider._OPERATE_ARCHIVE_ID,
        "source": "baostock query_dividend_data yearType=operate",
        "fetched_at": "2026-08-10T00:00:00+00:00",
        "tickers": list(official),
        "years": list(provider._OPERATE_YEARS),
        "coverage_start": provider._OPERATE_COVERAGE_START,
        "coverage_end": provider._OPERATE_COVERAGE_END,
        "baostock_version": "0.9.3",
        "baostock_module_sha256": {"season_index.py": "a" * 64},
        "total_rows": sum(len(r["rows"]) for r in receipts),
        "total_receipts": len(receipts),
        "duplicate_count": 0,
        "per_request": receipts,
    }
    if manifest_mutator is not None:
        manifest_mutator(manifest)
    if csv_lines is None:
        csv_text = ",".join(provider._OPERATE_CANONICAL_COLUMNS) + "\n"
    else:
        csv_text = (
            ",".join(provider._OPERATE_CANONICAL_COLUMNS)
            + "\n"
            + "\n".join(",".join(line) for line in csv_lines)
            + "\n"
        )
    csv_path.write_text(csv_text, encoding="utf-8", newline="\n")
    records_path.write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    _pin_operate_specs(monkeypatch, tmp_path, csv_path, records_path, admit_key=admit_key)
    return csv_path, records_path, official


def test_operate_inspector_fails_closed_without_specs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(provider, "OPERATE_CORPORATE_ACTION_SPECS", ())
    parsed = provider.inspect_corporate_action_operate_archive()
    assert parsed.present is False
    assert parsed.reason == "UNAVAILABLE_PENDING_OPERATE_ARCHIVE_FETCH"
    assert "OPERATE_ARCHIVE_NOT_PINNED" in parsed.errors


def test_real_operate_archive_rejects_tampered_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = (
        Path(__file__).resolve().parents[3]
        / "evaluation"
        / "research_evidence"
        / "corporate_action_operate_2020_2025"
    )
    destination = tmp_path / provider._OPERATE_ARCHIVE_RELATIVE_DIRECTORY
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source / "corporate_actions.csv", destination / "corporate_actions.csv")
    shutil.copy2(source / "source_records.json", destination / "source_records.json")
    monkeypatch.setattr(provider, "_repository_root", lambda: tmp_path)
    csv_path = destination / "corporate_actions.csv"
    csv_path.write_bytes(csv_path.read_bytes() + b"tamper")
    parsed = provider.inspect_corporate_action_operate_archive()
    assert parsed.verified is False
    assert "SHA256_MISMATCH" in parsed.errors


def test_operate_inspector_admits_a_valid_empty_archive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_operate_archive(tmp_path, monkeypatch)
    parsed = provider.inspect_corporate_action_operate_archive()
    assert parsed.verified is True
    assert parsed.reason == "AVAILABLE_BAOSTOCK_OPERATE_DIVIDEND_ARCHIVE"
    assert parsed.receipt_count == 294
    assert parsed.ticker_count == 49
    assert parsed.years == provider._OPERATE_YEARS


def test_operate_inspector_rejects_tampered_pinned_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    csv_path, _, _ = _write_operate_archive(tmp_path, monkeypatch)
    csv_path.write_bytes(csv_path.read_bytes() + b"tamper")
    parsed = provider.inspect_corporate_action_operate_archive()
    assert parsed.verified is False
    assert "SHA256_MISMATCH" in parsed.errors


def test_operate_inspector_rejects_wrong_years(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def mutate(manifest: dict) -> None:
        manifest["years"] = ["2025"]

    _write_operate_archive(tmp_path, monkeypatch, manifest_mutator=mutate)
    parsed = provider.inspect_corporate_action_operate_archive()
    assert parsed.verified is False
    assert "OPERATE_YEARS_MISMATCH" in parsed.errors


def test_operate_inspector_rejects_wrong_receipt_count(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def mutate(manifest: dict) -> None:
        manifest["per_request"] = manifest["per_request"][:-1]

    _write_operate_archive(tmp_path, monkeypatch, manifest_mutator=mutate)
    parsed = provider.inspect_corporate_action_operate_archive()
    assert parsed.verified is False
    assert "OPERATE_RECEIPT_COUNT_MISMATCH" in parsed.errors


def test_operate_inspector_rejects_failed_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def mutate(manifest: dict) -> None:
        manifest["per_request"][0]["error_code"] = "10004006"

    _write_operate_archive(tmp_path, monkeypatch, manifest_mutator=mutate)
    parsed = provider.inspect_corporate_action_operate_archive()
    assert parsed.verified is False
    assert "OPERATE_RECEIPT_FAILED" in parsed.errors


def test_operate_inspector_rejects_duplicate_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def mutate(manifest: dict) -> None:
        manifest["per_request"][1] = dict(manifest["per_request"][0])

    _write_operate_archive(tmp_path, monkeypatch, manifest_mutator=mutate)
    parsed = provider.inspect_corporate_action_operate_archive()
    assert parsed.verified is False
    assert "OPERATE_RECEIPT_NOT_UNIQUE" in parsed.errors


def test_operate_inspector_rejects_wrong_universe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def mutate(manifest: dict) -> None:
        manifest["tickers"] = [f"sh.{700000 + i:06d}" for i in range(49)]

    _write_operate_archive(tmp_path, monkeypatch, manifest_mutator=mutate)
    parsed = provider.inspect_corporate_action_operate_archive()
    assert parsed.verified is False
    assert "OPERATE_TICKER_SET_MISMATCH" in parsed.errors


def test_operate_inspector_rejects_csv_manifest_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def mutate(manifest: dict) -> None:
        manifest["total_rows"] = 5

    _write_operate_archive(tmp_path, monkeypatch, manifest_mutator=mutate)
    parsed = provider.inspect_corporate_action_operate_archive()
    assert parsed.verified is False
    assert "OPERATE_CSV_ROW_COUNT_MISMATCH" in parsed.errors


def test_operate_inspector_rejects_unknown_ticker_in_csv(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_operate_archive(
        tmp_path,
        monkeypatch,
        csv_lines=[["sh.999999"] + [""] * (len(provider._OPERATE_CANONICAL_COLUMNS) - 1)],
    )
    parsed = provider.inspect_corporate_action_operate_archive()
    assert parsed.verified is False
    assert "OPERATE_CSV_UNKNOWN_TICKER" in parsed.errors


def test_operate_inspector_rejects_invalid_date_in_csv(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, _, official = _write_operate_archive(tmp_path, monkeypatch)
    csv_path = tmp_path / provider._OPERATE_ARCHIVE_RELATIVE_DIRECTORY / "corporate_actions.csv"
    csv_row = [official[0]] + [""] * (len(provider._OPERATE_CANONICAL_COLUMNS) - 1)
    csv_row[provider._OPERATE_CANONICAL_COLUMNS.index("dividOperateDate")] = "2026-01-01"
    csv_path.write_text(
        ",".join(provider._OPERATE_CANONICAL_COLUMNS)
        + "\n"
        + ",".join(csv_row)
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    _pin_operate_specs(
        monkeypatch,
        tmp_path,
        csv_path,
        tmp_path / provider._OPERATE_ARCHIVE_RELATIVE_DIRECTORY / "source_records.json",
    )
    parsed = provider.inspect_corporate_action_operate_archive()
    assert parsed.verified is False
    assert "OPERATE_CSV_DATE_OUT_OF_BOUNDS" in parsed.errors


def test_operate_inspector_rejects_payload_hash_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def mutate(manifest: dict) -> None:
        manifest["per_request"][0]["response_payload_sha256"] = "b" * 64

    _write_operate_archive(tmp_path, monkeypatch, manifest_mutator=mutate)
    parsed = provider.inspect_corporate_action_operate_archive()
    assert parsed.verified is False
    assert "OPERATE_RECEIPT_PAYLOAD_HASH_MISMATCH" in parsed.errors


def test_operate_inspector_rejects_failed_flag_with_zero_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def mutate(manifest: dict) -> None:
        manifest["per_request"][0]["failed"] = True

    _write_operate_archive(tmp_path, monkeypatch, manifest_mutator=mutate)
    parsed = provider.inspect_corporate_action_operate_archive()
    assert parsed.verified is False
    assert "OPERATE_RECEIPT_FAILED_FLAG" in parsed.errors


def test_operate_inspector_rejects_row_count_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def mutate(manifest: dict) -> None:
        manifest["per_request"][0]["row_count"] = 5

    _write_operate_archive(tmp_path, monkeypatch, manifest_mutator=mutate)
    parsed = provider.inspect_corporate_action_operate_archive()
    assert parsed.verified is False
    assert "OPERATE_RECEIPT_ROW_COUNT_MISMATCH" in parsed.errors


def test_operate_inspector_rejects_receipt_date_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def mutate(manifest: dict) -> None:
        receipt = manifest["per_request"][0]  # official[0] / year=2020
        fields = receipt["fields"]
        op_index = fields.index("dividOperateDate")
        row = [""] * len(fields)
        row[op_index] = "2021-06-30"  # wrong year for the 2020 receipt
        receipt["rows"] = [row]
        receipt["row_count"] = 1
        receipt["response_payload_sha256"] = provider._canonical_hash(
            {"fields": fields, "rows": receipt["rows"]}
        )
        manifest["total_rows"] = 1

    _write_operate_archive(tmp_path, monkeypatch, manifest_mutator=mutate)
    parsed = provider.inspect_corporate_action_operate_archive()
    assert parsed.verified is False
    assert "OPERATE_RECEIPT_DATE_YEAR_MISMATCH" in parsed.errors


def test_operate_inspector_rejects_receipt_duplicate_count_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def mutate(manifest: dict) -> None:
        manifest["per_request"][0]["duplicate_count"] = 1  # rows empty -> recomputed 0

    _write_operate_archive(tmp_path, monkeypatch, manifest_mutator=mutate)
    parsed = provider.inspect_corporate_action_operate_archive()
    assert parsed.verified is False
    assert "OPERATE_RECEIPT_DUPLICATE_COUNT_MISMATCH" in parsed.errors


def test_operate_inspector_rejects_receipt_csv_substitution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    official = provider._official_operate_tickers(provider._repository_root())

    def mutate(manifest: dict) -> None:
        receipt = manifest["per_request"][0]
        fields = receipt["fields"]
        op_index = fields.index("dividOperateDate")
        row = [""] * len(fields)
        row[op_index] = "2020-06-30"
        receipt["rows"] = [row]
        receipt["row_count"] = 1
        receipt["response_payload_sha256"] = provider._canonical_hash(
            {"fields": fields, "rows": receipt["rows"]}
        )
        manifest["total_rows"] = 1

    csv_row = [official[0]] + [""] * (len(provider._OPERATE_CANONICAL_COLUMNS) - 1)
    csv_row[provider._OPERATE_CANONICAL_COLUMNS.index("dividOperateDate")] = "2020-07-01"
    _write_operate_archive(
        tmp_path,
        monkeypatch,
        manifest_mutator=mutate,
        csv_lines=[csv_row],
    )
    parsed = provider.inspect_corporate_action_operate_archive()
    assert parsed.verified is False
    assert "OPERATE_CSV_RECEIPT_PROJECTION_MISMATCH" in parsed.errors


def test_operate_capability_requires_trusted_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_operate_archive(tmp_path, monkeypatch, admit_key=False)
    readiness = provider.inspect_research_evidence_readiness()
    operate = next(
        item
        for item in readiness.capabilities
        if item.capability == "PIT_CORPORATE_ACTION_OPERATE"
    )
    assert operate.available is False
    assert operate.reason == "UNAVAILABLE_OPERATE_TRUST_KEY_MISSING"


def test_operate_capability_admitted_with_trusted_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_operate_archive(tmp_path, monkeypatch, admit_key=True)
    readiness = provider.inspect_research_evidence_readiness()
    operate = next(
        item
        for item in readiness.capabilities
        if item.capability == "PIT_CORPORATE_ACTION_OPERATE"
    )
    assert operate.available is True
    assert operate.reason == "AVAILABLE_BAOSTOCK_OPERATE_DIVIDEND_ARCHIVE"


def test_operate_inspector_rejects_short_receipt_row(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def mutate(manifest: dict) -> None:
        receipt = manifest["per_request"][0]
        fields = receipt["fields"]
        op_index = fields.index("dividOperateDate")
        short_row = [""] * op_index + ["2020-06-30"]
        receipt["rows"] = [short_row]
        receipt["row_count"] = 1
        receipt["response_payload_sha256"] = provider._canonical_hash(
            {"fields": fields, "rows": receipt["rows"]}
        )
        manifest["total_rows"] = 1

    _write_operate_archive(tmp_path, monkeypatch, manifest_mutator=mutate)
    parsed = provider.inspect_corporate_action_operate_archive()
    assert parsed.verified is False
    assert "OPERATE_RECEIPT_ROW_WIDTH_MISMATCH" in parsed.errors


def test_operate_inspector_rejects_extra_width_receipt_row(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def mutate(manifest: dict) -> None:
        receipt = manifest["per_request"][0]
        fields = receipt["fields"]
        op_index = fields.index("dividOperateDate")
        long_row = [""] * (len(fields) + 1)
        long_row[op_index] = "2020-06-30"
        receipt["rows"] = [long_row]
        receipt["row_count"] = 1
        receipt["response_payload_sha256"] = provider._canonical_hash(
            {"fields": fields, "rows": receipt["rows"]}
        )
        manifest["total_rows"] = 1

    _write_operate_archive(tmp_path, monkeypatch, manifest_mutator=mutate)
    parsed = provider.inspect_corporate_action_operate_archive()
    assert parsed.verified is False
    assert "OPERATE_RECEIPT_ROW_WIDTH_MISMATCH" in parsed.errors


def test_generator_archive_is_accepted_by_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _scripts = Path(__file__).resolve().parents[3] / "scripts"
    if str(_scripts) not in sys.path:
        sys.path.insert(0, str(_scripts))
    import fetch_corporate_action_operate as loader

    official = provider._official_operate_tickers(provider._repository_root())
    fields = list(provider._OPERATE_CANONICAL_COLUMNS[1:])
    op_index = fields.index("dividOperateDate")
    action = [""] * len(fields)
    action[op_index] = "2020-06-30"
    rows_by_query = {
        (official[0], "2020"): [list(action)],
        (official[1], "2020"): [list(action)],
    }

    class _Result:
        def __init__(self, rows: list[list[str]], code: str) -> None:
            self.error_code = "0"
            self.error_msg = ""
            self.code = code
            self.fields = fields
            self._rows = [list(row) for row in rows]
            self._i = 0

        def next(self) -> bool:
            return self._i < len(self._rows)

        def get_row_data(self) -> list[str]:
            row = self._rows[self._i]
            self._i += 1
            return row

    out_dir = tmp_path / provider._OPERATE_ARCHIVE_RELATIVE_DIRECTORY
    loader.build_operate_archive(
        tickers=official,
        years=[int(year) for year in provider._OPERATE_YEARS],
        out_dir=out_dir,
        query_fn=lambda code, year, yt: _Result(
            rows_by_query.get((code, year), []), code
        ),
        baostock_version="0.9.3",
        baostock_module_sha256={"a.py": "0" * 64},
        official_tickers=official,
        fetched_at="2026-08-10T00:00:00+00:00",
        tickers_expected=49,
    )
    monkeypatch.setattr(provider, "_repository_root", lambda: tmp_path)
    csv_path = out_dir / "corporate_actions.csv"
    records_path = out_dir / "source_records.json"
    _pin_operate_specs(monkeypatch, tmp_path, csv_path, records_path, admit_key=True)
    parsed = provider.inspect_corporate_action_operate_archive()
    assert parsed.verified is True
    assert parsed.total_rows == 2  # the two cross-ticker actions coexist


def test_forward_label_v2_identity_admitted_and_legacy_v1_rejected() -> None:
    evidence = "c7c3d2b474fa2109a423e8dfe0d6d4f0283a8aff26a9c286c840584f0c6f7eba"
    records_hash = provider.FORWARD_LABEL_RECORDS_SPEC.expected_sha256
    v2_tuple = (
        "official_forward_label",
        "PIT_OFFICIAL_FORWARD_LABEL_ARCHIVE",
        "official_forward_label_2024_2026/v2",
        records_hash,
        evidence,
    )
    v1_tuple = (
        "official_forward_label",
        "PIT_OFFICIAL_FORWARD_LABEL_ARCHIVE",
        "official_forward_label_2020_2026/v1",
        records_hash,
        evidence,
    )
    assert v2_tuple in provider._TRUSTED_EVIDENCE_KEYS
    assert v1_tuple not in provider._TRUSTED_EVIDENCE_KEYS
    assert provider.trusted_evidence_contains(
        kind="official_forward_label",
        authority="PIT_OFFICIAL_FORWARD_LABEL_ARCHIVE",
        source_version="official_forward_label_2024_2026/v2",
        source_sha256=records_hash,
        evidence_hash=evidence,
    )
    assert not provider.trusted_evidence_contains(
        kind="official_forward_label",
        authority="PIT_OFFICIAL_FORWARD_LABEL_ARCHIVE",
        source_version="official_forward_label_2020_2026/v1",
        source_sha256=records_hash,
        evidence_hash=evidence,
    )
