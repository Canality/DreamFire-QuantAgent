"""Fail-closed archive and trust-boundary tests for WP1 evidence providers."""

from __future__ import annotations

import inspect
import shutil
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
    assert readiness.ready_for_e0 is False
    assert readiness.ready_for_e1 is False
    assert readiness.trusted_evidence_key_count == 4
    assert readiness.trusted_factor_snapshot_count == 0
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
        "calendar",
        "SSE_SZSE_OFFICIAL_CALENDAR_ARCHIVE",
        "future-provider/v1",
        "a" * 64,
        "b" * 64,
    )
    monkeypatch.setattr(provider, "_TRUSTED_EVIDENCE_KEYS", frozenset({key}))
    monkeypatch.setattr(
        provider,
        "_TRUSTED_FACTOR_SNAPSHOT_HASHES",
        frozenset({"c" * 64}),
    )

    assert not provider.trusted_evidence_contains(
        kind=key[0],
        authority=key[1],
        source_version=key[2],
        source_sha256=key[3],
        evidence_hash=key[4],
    )
    assert not provider.trusted_factor_snapshot_contains("c" * 64)
    readiness = provider.inspect_research_evidence_readiness()
    assert readiness.source_bytes_verified
    assert readiness.trusted_evidence_key_count == 1
    assert readiness.trusted_factor_snapshot_count == 1
    assert readiness.ready_for_e0 is False
    assert readiness.ready_for_e1 is False
