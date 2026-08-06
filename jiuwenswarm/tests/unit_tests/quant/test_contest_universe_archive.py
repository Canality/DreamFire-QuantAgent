"""Tests for the fixed contest workbook's semantic audit boundary."""

from __future__ import annotations

import hashlib
import inspect
import shutil
import zipfile
from pathlib import Path

import pytest

from jiuwenswarm.quant import stock_pool
from jiuwenswarm.quant.reporting import contest_universe_archive as archive_module
from jiuwenswarm.quant.reporting.contest_universe_archive import (
    CONTEST_FIXED_METADATA,
    CONTEST_UNIVERSE_AUTHORITY,
    CONTEST_UNIVERSE_EVIDENCE_SHA256,
    CONTEST_UNIVERSE_REL_PATH,
    CONTEST_UNIVERSE_SHA256,
    _inspect_at_root,
    inspect_contest_universe_archive,
)


def _copy_official_workbook(root: Path) -> Path:
    source = archive_module._resolve_project_root() / CONTEST_UNIVERSE_REL_PATH
    destination = root / CONTEST_UNIVERSE_REL_PATH
    destination.parent.mkdir(parents=True)
    shutil.copy2(source, destination)
    return destination


def _rewrite_zip_member(path: Path, member_name: str, old: bytes, new: bytes) -> None:
    rewritten = path.with_suffix(".rewritten.xlsx")
    with zipfile.ZipFile(path, "r") as source, zipfile.ZipFile(rewritten, "w") as target:
        for member in source.infolist():
            data = source.read(member.filename)
            if member.filename == member_name:
                assert old in data
                data = data.replace(old, new, 1)
            target.writestr(member, data)
    rewritten.replace(path)


def test_official_archive_is_exact_fixed_metadata() -> None:
    audit = inspect_contest_universe_archive()

    assert audit.verified
    assert audit.issues == ()
    assert audit.capability == CONTEST_FIXED_METADATA
    assert audit.authority == CONTEST_UNIVERSE_AUTHORITY
    assert audit.source_sha256 == CONTEST_UNIVERSE_SHA256
    assert audit.source_version == f"sha256:{CONTEST_UNIVERSE_SHA256.lower()}"
    assert audit.pit_sector_eligible is False
    assert len(audit.members) == 49
    assert len(set(audit.company_codes)) == 49
    assert audit.group_names == tuple(stock_pool.STOCK_POOL)
    assert audit.group_counts == (8, 9, 8, 12, 8, 4)
    assert len(audit.evidence_hash) == 64
    assert audit.evidence_hash == CONTEST_UNIVERSE_EVIDENCE_SHA256
    assert audit.workbook_created == "2023-05-12T11:15:00Z"
    assert audit.workbook_modified == "2026-07-21T06:58:23Z"
    assert not hasattr(audit, "observed_at")
    assert not hasattr(audit, "effective_date")


def test_archive_semantics_exactly_match_stock_pool_compatibility_surface() -> None:
    audit = inspect_contest_universe_archive()

    assert audit.company_codes == tuple(sorted(stock_pool.ALL_STOCKS))
    assert audit.company_names == stock_pool.TICKER_NAME_MAP
    assert audit.sectors == stock_pool.SECTOR_MAP


def test_public_inspector_accepts_no_caller_path_hash_or_timestamp() -> None:
    assert tuple(inspect.signature(inspect_contest_universe_archive).parameters) == ()


def test_archive_evidence_hash_is_deterministic() -> None:
    first = inspect_contest_universe_archive()
    second = inspect_contest_universe_archive()
    assert first.evidence_hash == second.evidence_hash


def test_missing_archive_fails_closed(tmp_path: Path) -> None:
    audit = _inspect_at_root(tmp_path)
    assert not audit.verified
    assert audit.members == ()
    assert "missing" in audit.issues[0]


def test_tampered_archive_hash_fails_closed(tmp_path: Path) -> None:
    workbook = _copy_official_workbook(tmp_path)
    workbook.write_bytes(workbook.read_bytes() + b"tampered")

    audit = _inspect_at_root(tmp_path)
    assert not audit.verified
    assert "hash mismatch" in audit.issues[0]
    assert audit.evidence_hash == ""


def test_symlink_archive_fails_closed(tmp_path: Path) -> None:
    source = archive_module._resolve_project_root() / CONTEST_UNIVERSE_REL_PATH
    destination = tmp_path / CONTEST_UNIVERSE_REL_PATH
    destination.parent.mkdir(parents=True)
    try:
        destination.symlink_to(source)
    except OSError as exc:
        pytest.skip(f"symlink creation is unavailable: {exc}")

    audit = _inspect_at_root(tmp_path)
    assert not audit.verified
    assert "symlink" in audit.issues[0]


def test_repinning_hash_cannot_hide_duplicate_semantics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workbook = _copy_official_workbook(tmp_path)
    _rewrite_zip_member(
        workbook,
        "xl/sharedStrings.xml",
        "601318 中国平安".encode(),
        "600036 中国平安".encode(),
    )
    repinned_hash = hashlib.sha256(workbook.read_bytes()).hexdigest().upper()
    monkeypatch.setattr(archive_module, "CONTEST_UNIVERSE_SHA256", repinned_hash)

    audit = _inspect_at_root(tmp_path)
    assert not audit.verified
    assert "49 unique" in audit.issues[0]


def test_repinning_hash_cannot_relabel_contest_groups(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workbook = _copy_official_workbook(tmp_path)
    _rewrite_zip_member(
        workbook,
        "xl/sharedStrings.xml",
        "金融板块".encode(),
        "银行板块".encode(),
    )
    repinned_hash = hashlib.sha256(workbook.read_bytes()).hexdigest().upper()
    monkeypatch.setattr(archive_module, "CONTEST_UNIVERSE_SHA256", repinned_hash)

    audit = _inspect_at_root(tmp_path)
    assert not audit.verified
    assert "headers changed" in audit.issues[0]


def test_repinning_hash_cannot_add_formula(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workbook = _copy_official_workbook(tmp_path)
    _rewrite_zip_member(
        workbook,
        "xl/worksheets/sheet1.xml",
        b"<v>0</v>",
        b"<f>1</f><v>0</v>",
    )
    repinned_hash = hashlib.sha256(workbook.read_bytes()).hexdigest().upper()
    monkeypatch.setattr(archive_module, "CONTEST_UNIVERSE_SHA256", repinned_hash)

    audit = _inspect_at_root(tmp_path)
    assert not audit.verified
    assert "formula cells are not allowed" in audit.issues[0]


def test_repinning_hash_cannot_hide_data_in_extra_sheet(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workbook = _copy_official_workbook(tmp_path)
    _rewrite_zip_member(
        workbook,
        "xl/worksheets/sheet2.xml",
        b"<sheetData/>",
        b'<sheetData><row r="1"><c r="A1" t="s"><v>0</v></c></row></sheetData>',
    )
    repinned_hash = hashlib.sha256(workbook.read_bytes()).hexdigest().upper()
    monkeypatch.setattr(archive_module, "CONTEST_UNIVERSE_SHA256", repinned_hash)

    audit = _inspect_at_root(tmp_path)
    assert not audit.verified
    assert "Sheet2 must be empty" in audit.issues[0]


def test_repinning_byte_hash_cannot_rename_a_company(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workbook = _copy_official_workbook(tmp_path)
    _rewrite_zip_member(
        workbook,
        "xl/sharedStrings.xml",
        "601318 中国平安".encode(),
        "601318 平安伪名".encode(),
    )
    repinned_hash = hashlib.sha256(workbook.read_bytes()).hexdigest().upper()
    monkeypatch.setattr(archive_module, "CONTEST_UNIVERSE_SHA256", repinned_hash)

    audit = _inspect_at_root(tmp_path)
    assert not audit.verified
    assert audit.members == ()
    assert "semantic identity changed" in audit.issues[0]


def test_repinning_byte_hash_cannot_swap_cross_group_memberships(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workbook = _copy_official_workbook(tmp_path)
    placeholder = b"__PIT_SECTOR_SWAP_PLACEHOLDER__"
    rewritten = workbook.with_suffix(".rewritten.xlsx")
    with zipfile.ZipFile(workbook, "r") as source, zipfile.ZipFile(rewritten, "w") as target:
        for member in source.infolist():
            data = source.read(member.filename)
            if member.filename == "xl/sharedStrings.xml":
                first = "601318 中国平安".encode()
                second = "600519 贵州茅台".encode()
                assert first in data and second in data
                data = data.replace(first, placeholder, 1)
                data = data.replace(second, first, 1)
                data = data.replace(placeholder, second, 1)
            target.writestr(member, data)
    rewritten.replace(workbook)
    repinned_hash = hashlib.sha256(workbook.read_bytes()).hexdigest().upper()
    monkeypatch.setattr(archive_module, "CONTEST_UNIVERSE_SHA256", repinned_hash)

    audit = _inspect_at_root(tmp_path)
    assert not audit.verified
    assert audit.members == ()
    assert "semantic identity changed" in audit.issues[0]
