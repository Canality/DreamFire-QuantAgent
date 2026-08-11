"""Research-only archive inventory and trust boundary for WP1-E evidence.

The repository contains one admitted official calendar archive but still lacks
the remaining authority archives required by WP1-E0/E1.  This module makes that
partial readiness machine-readable and never promotes future scheduled dates
to confirmed historical sessions.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from jiuwenswarm.quant import official_calendar_archive

_HASH_RE = re.compile(r"[0-9a-f]{64}")
_INVENTORY_ID = "wp1_factor_evidence_inventory_v1"
_SNAPSHOT_RELATIVE_DIRECTORY = Path(
    "jiuwenswarm/evaluation/data_snapshots/sina_20260721_135352"
)
_OPERATE_ARCHIVE_RELATIVE_DIRECTORY = Path(
    "jiuwenswarm/evaluation/research_evidence/corporate_action_operate_2020_2025"
)


def _canonical_hash(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class PinnedSourceFile:
    """One immutable repository-relative source-byte expectation."""

    artifact_id: str
    relative_path: Path
    expected_sha256: str

    def __post_init__(self) -> None:
        if not self.artifact_id.strip():
            raise ValueError("artifact_id is missing")
        if self.relative_path.is_absolute() or ".." in self.relative_path.parts:
            raise ValueError("source file path must be repository-relative")
        if _HASH_RE.fullmatch(self.expected_sha256) is None:
            raise ValueError("source file hash must be lowercase SHA-256")

    def to_dict(self) -> dict[str, str]:
        return {
            "artifact_id": self.artifact_id,
            "relative_path": self.relative_path.as_posix(),
            "expected_sha256": self.expected_sha256,
        }


OFFICIAL_UNIVERSE_SPEC = PinnedSourceFile(
    artifact_id="official_competition_universe",
    relative_path=Path("赛题文档/上市公司列表.xlsx"),
    expected_sha256=(
        "c021d69b5c3bf3ea0c4626811df5ed9a02cd4c67e1068ad2f0ce35d759210617"
    ),
)
SINA_MANIFEST_SPEC = PinnedSourceFile(
    artifact_id="sina_manifest",
    relative_path=_SNAPSHOT_RELATIVE_DIRECTORY / "manifest.json",
    expected_sha256=(
        "59bc1092018cc21894f3e331ee708d6644ed7669297f2f011cff6ab267518961"
    ),
)
SINA_OPEN_SPEC = PinnedSourceFile(
    artifact_id="sina_open",
    relative_path=_SNAPSHOT_RELATIVE_DIRECTORY / "stocks_open.csv.gz",
    expected_sha256=(
        "b3f33a2e4af92db2f4906f0337424ab9a41dcda804db5d9f10766aee45b87a74"
    ),
)
SINA_HIGH_SPEC = PinnedSourceFile(
    artifact_id="sina_high",
    relative_path=_SNAPSHOT_RELATIVE_DIRECTORY / "stocks_high.csv.gz",
    expected_sha256=(
        "8fafb147c4f66c38cd118bf65a62f159fb416b1f5f490c2449dce66ef805e0db"
    ),
)
SINA_LOW_SPEC = PinnedSourceFile(
    artifact_id="sina_low",
    relative_path=_SNAPSHOT_RELATIVE_DIRECTORY / "stocks_low.csv.gz",
    expected_sha256=(
        "1053ccf006f0e03622771af26cde62939da3157c030d1055ca6a5b8d6169c123"
    ),
)
SINA_CLOSE_SPEC = PinnedSourceFile(
    artifact_id="sina_close",
    relative_path=_SNAPSHOT_RELATIVE_DIRECTORY / "stocks_close.csv.gz",
    expected_sha256=(
        "1aaeec24f2811a707268736b2b2b88b9c0ccbf07a6ca6885b742a864208fff18"
    ),
)
SINA_VOLUME_SPEC = PinnedSourceFile(
    artifact_id="sina_volume",
    relative_path=_SNAPSHOT_RELATIVE_DIRECTORY / "stocks_volume.csv.gz",
    expected_sha256=(
        "322e64c1e4dd85168e16ea8ab9708c856c69c8572f34a854da9e35efade497a3"
    ),
)
SINA_BENCHMARK_SPEC = PinnedSourceFile(
    artifact_id="sina_csi300",
    relative_path=_SNAPSHOT_RELATIVE_DIRECTORY / "csi300_ohlcv.csv.gz",
    expected_sha256=(
        "187ca57952514ab54b4ad48c809ac00b2f4fa90679f4b65d60cf6d927fbc02cd"
    ),
)

CORPORATE_ACTION_CSV_SPEC = PinnedSourceFile(
    artifact_id="corporate_action_csv",
    relative_path=Path(
        "jiuwenswarm/evaluation/research_evidence/corporate_action_2020_2026/corporate_actions.csv"
    ),
    expected_sha256=(
        "9e453033e2d8f14c86987d25ab99b6a4b8c9a3b5c69c67ea0f3b57eaeb81f014"
    ),
)
CORPORATE_ACTION_RECORDS_SPEC = PinnedSourceFile(
    artifact_id="corporate_action_source_records",
    relative_path=Path(
        "jiuwenswarm/evaluation/research_evidence/corporate_action_2020_2026/source_records.json"
    ),
    expected_sha256=(
        "dcd0b4e7700ebf581eb3529611bcf0702e0aafa527381b6ed859387d6db8887c"
    ),
)
E0_SNAPSHOT_CSV_SPEC = PinnedSourceFile(
    artifact_id="e0_factor_snapshot_csv",
    relative_path=Path(
        "jiuwenswarm/evaluation/research_evidence/e0_factor_snapshot_2020_2026/qfq_ohlcv.csv"
    ),
    expected_sha256=(
        "53be223892d577e21b4cd7c2034a894bd321e7b90f6593de421e6554d58b440e"
    ),
)
E0_SNAPSHOT_RECORDS_SPEC = PinnedSourceFile(
    artifact_id="e0_factor_snapshot_source_records",
    relative_path=Path(
        "jiuwenswarm/evaluation/research_evidence/e0_factor_snapshot_2020_2026/source_records.json"
    ),
    expected_sha256=(
        "184388562f6de36dbcf4b1f9d4b5b544b36e21f882e0ced0fdc771a337ed58a2"
    ),
)
FORWARD_LABEL_CSV_SPEC = PinnedSourceFile(
    artifact_id="official_forward_label_csv",
    relative_path=Path(
        "jiuwenswarm/evaluation/research_evidence/official_forward_label_2024_2026_v2/forward_labels.csv"
    ),
    expected_sha256=(
        "d29961065d89adbf55580b1c40387bb287901f30af27503394a511f0c8be675f"
    ),
)
FORWARD_LABEL_RECORDS_SPEC = PinnedSourceFile(
    artifact_id="official_forward_label_source_records",
    relative_path=Path(
        "jiuwenswarm/evaluation/research_evidence/official_forward_label_2024_2026_v2/source_records.json"
    ),
    expected_sha256=(
        "41a672eb1cb8868cd6644125f63e906b36fdb0db00c684c49d3049acd8bd0b2e"
    ),
)

PINNED_SOURCE_FILES: tuple[PinnedSourceFile, ...] = (
    OFFICIAL_UNIVERSE_SPEC,
    SINA_MANIFEST_SPEC,
    SINA_OPEN_SPEC,
    SINA_HIGH_SPEC,
    SINA_LOW_SPEC,
    SINA_CLOSE_SPEC,
    SINA_VOLUME_SPEC,
    SINA_BENCHMARK_SPEC,
    CORPORATE_ACTION_CSV_SPEC,
    CORPORATE_ACTION_RECORDS_SPEC,
    E0_SNAPSHOT_CSV_SPEC,
    E0_SNAPSHOT_RECORDS_SPEC,
    FORWARD_LABEL_CSV_SPEC,
    FORWARD_LABEL_RECORDS_SPEC,
)

# Hash-pinned operate-year archive specs, derived from the real generated bytes
# by WP1-E2O-N1 (BaoStock yearType=operate fetch, 49 official tickers x
# 2020..2025, 294 successful unique receipts).  Never predicted; recomputed from
# the actual corporate_actions.csv / source_records.json files.
OPERATE_CORPORATE_ACTION_SPECS: tuple[PinnedSourceFile, ...] = (
    PinnedSourceFile(
        artifact_id="operate_corporate_actions_csv",
        relative_path=_OPERATE_ARCHIVE_RELATIVE_DIRECTORY / "corporate_actions.csv",
        expected_sha256=(
            "b69c5f2d06ec853a9696e0947a72d59cb27e6982b1aa513314e70952e8f7f5ae"
        ),
    ),
    PinnedSourceFile(
        artifact_id="operate_corporate_actions_records",
        relative_path=_OPERATE_ARCHIVE_RELATIVE_DIRECTORY / "source_records.json",
        expected_sha256=(
            "210fc66c9001f9c9b958ec1119be1dc092afe884df5fc79afc695a62be392e56"
        ),
    ),
)

_OPERATE_ARCHIVE_ID = "corporate_action_operate_2020_2025/v1"
_OPERATE_SCHEMA = "corporate_action_operate_archive/v1"
_OPERATE_YEARS = tuple(str(year) for year in range(2020, 2026))
_OPERATE_RECEIPT_COUNT = 49 * 6  # 49 tickers x 6 complete operate years
_OPERATE_COVERAGE_START = "2020-01-01"
_OPERATE_COVERAGE_END = "2025-12-31"
_OPERATE_CANONICAL_COLUMNS: tuple[str, ...] = (
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
_OPERATE_ACTION_IDENTITY_FIELDS: tuple[str, ...] = (
    "dividOperateDate",
    "dividCashPsBeforeTax",
    "dividCashPsAfterTax",
    "dividStocksPs",
    "dividReserveToStockPs",
    "dividCashStock",
    "dividPlanAnnounceDate",
)

_SINA_SNAPSHOT_SPECS = (
    SINA_MANIFEST_SPEC,
    SINA_OPEN_SPEC,
    SINA_HIGH_SPEC,
    SINA_LOW_SPEC,
    SINA_CLOSE_SPEC,
    SINA_VOLUME_SPEC,
    SINA_BENCHMARK_SPEC,
)

_EXPECTED_SNAPSHOT_FILE_NAMES = frozenset(
    spec.relative_path.name for spec in _SINA_SNAPSHOT_SPECS
)
_EXPECTED_MANIFEST_CHILDREN = {
    spec.relative_path.name: spec.expected_sha256
    for spec in _SINA_SNAPSHOT_SPECS[1:]
}
_UNAVAILABLE_CAPABILITY_REASONS: tuple[tuple[str, str], ...] = ()
_EVIDENCE_KIND_CAPABILITY = {
    "canonical_calendar": "CANONICAL_CALENDAR",
    "sector_metadata": "PIT_SECTOR",
    "official_forward_label": "OFFICIAL_FORWARD_LABEL",
    "corporate_action": "PIT_CORPORATE_ACTION",
    "corporate_action_operate": "PIT_CORPORATE_ACTION_OPERATE",
}
_EVIDENCE_KIND_ALIASES = {"calendar": "canonical_calendar"}

# These are the only runtime admission roots consumed by E0/E1.  The calendar
# key is bound to repository-held official source records and only the sequence
# confirmed through the frozen daily-statistics cutoff.  The operate key binds
# the hash-pinned operate-year archive admitted by WP1-E2O-N1.
_TRUSTED_EVIDENCE_KEYS: frozenset[
    tuple[str, str, str, str, str]
] = frozenset(
    {
        (
            "canonical_calendar",
            "SSE_SZSE_OFFICIAL_CALENDAR_ARCHIVE",
            "official_calendar_2024_2026/v1",
            official_calendar_archive.ARCHIVE_SOURCE_SHA256,
            official_calendar_archive.EXPECTED_CALENDAR_EVIDENCE_SHA256,
        ),
        (
            "corporate_action",
            "BAOSTOCK_QUERY_DIVIDEND_DATA",
            "corporate_action_2020_2026/v1",
            CORPORATE_ACTION_RECORDS_SPEC.expected_sha256,
            CORPORATE_ACTION_CSV_SPEC.expected_sha256,
        ),
        (
            "official_forward_label",
            "PIT_OFFICIAL_FORWARD_LABEL_ARCHIVE",
            "official_forward_label_2024_2026/v2",
            FORWARD_LABEL_RECORDS_SPEC.expected_sha256,
            "c7c3d2b474fa2109a423e8dfe0d6d4f0283a8aff26a9c286c840584f0c6f7eba",
        ),
        (
            "sector_metadata",
            "PIT_SECTOR_METADATA_ARCHIVE",
            "competition_universe_static_v1",
            OFFICIAL_UNIVERSE_SPEC.expected_sha256,
            OFFICIAL_UNIVERSE_SPEC.expected_sha256,
        ),
        (
            "corporate_action_operate",
            "BAOSTOCK_QUERY_DIVIDEND_DATA_OPERATE",
            "corporate_action_operate_2020_2025/v1",
            "210fc66c9001f9c9b958ec1119be1dc092afe884df5fc79afc695a62be392e56",
            "b69c5f2d06ec853a9696e0947a72d59cb27e6982b1aa513314e70952e8f7f5ae",
        ),
    }
)
_TRUSTED_FACTOR_SNAPSHOT_HASHES: frozenset[str] = frozenset(
    {
        "53be223892d577e21b4cd7c2034a894bd321e7b90f6593de421e6554d58b440e",
    }
)


def _inventory_hash() -> str:
    return _canonical_hash(
        {
            "inventory_id": _INVENTORY_ID,
            "pinned_source_files": [
                spec.to_dict() for spec in PINNED_SOURCE_FILES
            ],
            "operate_corporate_action_specs": [
                spec.to_dict() for spec in OPERATE_CORPORATE_ACTION_SPECS
            ],
            "official_calendar_archive_source_sha256": (
                official_calendar_archive.ARCHIVE_SOURCE_SHA256
            ),
            "official_calendar_evidence_sha256": (
                official_calendar_archive.EXPECTED_CALENDAR_EVIDENCE_SHA256
            ),
            "unavailable_capability_reasons": [
                list(item) for item in _UNAVAILABLE_CAPABILITY_REASONS
            ],
        }
    )


INVENTORY_HASH = _inventory_hash()


@dataclass(frozen=True)
class SourceFileVerification:
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
class CapabilityDisposition:
    capability: str
    available: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability": self.capability,
            "available": self.available,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class ResearchEvidenceReadiness:
    """Deterministic audit result for the frozen repository inventory."""

    inventory_id: str
    inventory_hash: str
    source_bytes_verified: bool
    sources: tuple[SourceFileVerification, ...]
    inventory_errors: tuple[str, ...]
    calendar_archive_verified: bool
    calendar_archive_source_sha256: str
    calendar_evidence_hash: str
    calendar_confirmation_cutoff: str
    calendar_confirmed_session_count: int
    calendar_scheduled_session_count: int
    calendar_errors: tuple[str, ...]
    capabilities: tuple[CapabilityDisposition, ...]
    trusted_evidence_key_count: int
    trusted_factor_snapshot_count: int
    ready_for_e0: bool
    ready_for_e1: bool
    audit_hash: str

    def _payload(self) -> dict[str, Any]:
        return {
            "inventory_id": self.inventory_id,
            "inventory_hash": self.inventory_hash,
            "source_bytes_verified": self.source_bytes_verified,
            "sources": [item.to_dict() for item in self.sources],
            "inventory_errors": list(self.inventory_errors),
            "calendar_archive_verified": self.calendar_archive_verified,
            "calendar_archive_source_sha256": self.calendar_archive_source_sha256,
            "calendar_evidence_hash": self.calendar_evidence_hash,
            "calendar_confirmation_cutoff": self.calendar_confirmation_cutoff,
            "calendar_confirmed_session_count": (
                self.calendar_confirmed_session_count
            ),
            "calendar_scheduled_session_count": (
                self.calendar_scheduled_session_count
            ),
            "calendar_errors": list(self.calendar_errors),
            "capabilities": [item.to_dict() for item in self.capabilities],
            "trusted_evidence_key_count": self.trusted_evidence_key_count,
            "trusted_factor_snapshot_count": self.trusted_factor_snapshot_count,
            "ready_for_e0": self.ready_for_e0,
            "ready_for_e1": self.ready_for_e1,
        }

    def to_dict(self) -> dict[str, Any]:
        payload = self._payload()
        if _canonical_hash(payload) != self.audit_hash:
            raise ValueError("research evidence readiness hash mismatch")
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


def _verify_source_file(root: Path, spec: PinnedSourceFile) -> SourceFileVerification:
    path = root / spec.relative_path
    base = {
        "artifact_id": spec.artifact_id,
        "relative_path": spec.relative_path.as_posix(),
        "expected_sha256": spec.expected_sha256,
    }
    if _has_symlink_component(root, spec.relative_path):
        return SourceFileVerification(
            **base,
            actual_sha256=None,
            verified=False,
            reason="SYMLINK_REJECTED",
        )
    if not path.exists():
        return SourceFileVerification(
            **base,
            actual_sha256=None,
            verified=False,
            reason="MISSING_FILE",
        )
    if not path.is_file():
        return SourceFileVerification(
            **base,
            actual_sha256=None,
            verified=False,
            reason="NOT_REGULAR_FILE",
        )
    resolved_root = root.resolve()
    try:
        path.resolve().relative_to(resolved_root)
    except ValueError:
        return SourceFileVerification(
            **base,
            actual_sha256=None,
            verified=False,
            reason="PATH_ESCAPE_REJECTED",
        )
    actual = _sha256_file(path)
    return SourceFileVerification(
        **base,
        actual_sha256=actual,
        verified=actual == spec.expected_sha256,
        reason="VERIFIED" if actual == spec.expected_sha256 else "SHA256_MISMATCH",
    )


def _snapshot_inventory_errors(
    root: Path,
    sources: tuple[SourceFileVerification, ...],
) -> tuple[str, ...]:
    errors: list[str] = []
    snapshot_directory = root / _SNAPSHOT_RELATIVE_DIRECTORY
    if _has_symlink_component(root, _SNAPSHOT_RELATIVE_DIRECTORY):
        errors.append("SYMLINKED_SNAPSHOT_DIRECTORY")
        return tuple(errors)
    if not snapshot_directory.is_dir():
        errors.append("MISSING_SNAPSHOT_DIRECTORY")
        return tuple(errors)
    actual_names = frozenset(item.name for item in snapshot_directory.iterdir())
    if actual_names != _EXPECTED_SNAPSHOT_FILE_NAMES:
        errors.append("UNEXPECTED_SNAPSHOT_FILE_SET")

    by_id = {item.artifact_id: item for item in sources}
    manifest_verification = by_id["sina_manifest"]
    if not manifest_verification.verified:
        errors.append("UNVERIFIED_SNAPSHOT_MANIFEST")
        return tuple(errors)
    manifest_path = root / SINA_MANIFEST_SPEC.relative_path
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        errors.append("INVALID_SNAPSHOT_MANIFEST_JSON")
        return tuple(errors)
    expected_metadata = {
        "snapshot_id": "sina_20260721_135352",
        "created_at": "2026-07-21T13:53:56.130653+08:00",
        "source": "Sina CN_MarketDataService.getKLineData",
        "adjustment": "raw/unadjusted",
        "requested_rows": 500,
        "n_stocks": 49,
        "n_sectors": 6,
    }
    if any(manifest.get(key) != value for key, value in expected_metadata.items()):
        errors.append("UNEXPECTED_SNAPSHOT_METADATA")
    tickers = manifest.get("tickers")
    if (
        not isinstance(tickers, list)
        or len(tickers) != 49
        or len(set(tickers)) != 49
        or any(not isinstance(ticker, str) or not ticker for ticker in tickers)
    ):
        errors.append("INVALID_SNAPSHOT_TICKER_SET")
    declared_files = manifest.get("files")
    if not isinstance(declared_files, dict) or set(declared_files) != set(
        _EXPECTED_MANIFEST_CHILDREN
    ):
        errors.append("INVALID_MANIFEST_CHILD_SET")
    else:
        for name, expected_sha256 in _EXPECTED_MANIFEST_CHILDREN.items():
            entry = declared_files.get(name)
            if not isinstance(entry, dict) or entry.get("sha256") != expected_sha256:
                errors.append("MANIFEST_CHILD_HASH_MISMATCH")
                break
    return tuple(dict.fromkeys(errors))


def _inspect_at_root(root: Path) -> ResearchEvidenceReadiness:
    sources = tuple(_verify_source_file(root, spec) for spec in PINNED_SOURCE_FILES)
    inventory_errors = _snapshot_inventory_errors(root, sources)
    source_bytes_verified = (
        all(item.verified for item in sources) and not inventory_errors
    )
    calendar = official_calendar_archive._inspect_at_root(root)
    corporate_action_ok = all(
        item.verified
        for item in sources
        if item.artifact_id
        in {"corporate_action_csv", "corporate_action_source_records"}
    )
    e0_snapshot_ok = bool(
        _TRUSTED_FACTOR_SNAPSHOT_HASHES
        and all(
            item.verified
            for item in sources
            if item.artifact_id
            in {"e0_factor_snapshot_csv", "e0_factor_snapshot_source_records"}
        )
    )
    forward_label_ok = all(
        item.verified
        for item in sources
        if item.artifact_id
        in {"official_forward_label_csv", "official_forward_label_source_records"}
    )
    pit_sector_ok = any(
        item.artifact_id == "official_competition_universe" and item.verified
        for item in sources
    )
    operate_corporate_action = inspect_corporate_action_operate_archive()
    operate_key_admitted = _operate_key_admitted()
    operate_corporate_action_ok = bool(
        OPERATE_CORPORATE_ACTION_SPECS
        and operate_corporate_action.verified
        and operate_key_admitted
    )
    if OPERATE_CORPORATE_ACTION_SPECS and not operate_key_admitted:
        operate_reason = "UNAVAILABLE_OPERATE_TRUST_KEY_MISSING"
    elif operate_corporate_action_ok:
        operate_reason = "AVAILABLE_BAOSTOCK_OPERATE_DIVIDEND_ARCHIVE"
    else:
        operate_reason = "UNAVAILABLE_PENDING_OPERATE_ARCHIVE_FETCH"
    capabilities = (
        CapabilityDisposition(
            capability="CANONICAL_CALENDAR",
            available=calendar.verified,
            reason=(
                "AVAILABLE_OFFICIAL_SSE_SZSE_CONFIRMED_ARCHIVE"
                if calendar.verified
                else "UNAVAILABLE_INVALID_OFFICIAL_CALENDAR_ARCHIVE"
            ),
        ),
        CapabilityDisposition(
            capability="PIT_CORPORATE_ACTION",
            available=corporate_action_ok,
            reason=(
                "AVAILABLE_BAOSTOCK_DIVIDEND_ARCHIVE"
                if corporate_action_ok
                else "UNAVAILABLE_INVALID_CORPORATE_ACTION_ARCHIVE"
            ),
        ),
        CapabilityDisposition(
            capability="E0_FACTOR_SNAPSHOT",
            available=e0_snapshot_ok,
            reason=(
                "AVAILABLE_BAOSTOCK_QFQ_SNAPSHOT_ARCHIVE"
                if e0_snapshot_ok
                else "UNAVAILABLE_INVALID_E0_FACTOR_SNAPSHOT_ARCHIVE"
            ),
        ),
        CapabilityDisposition(
            capability="OFFICIAL_FORWARD_LABEL",
            available=forward_label_ok,
            reason=(
                "AVAILABLE_OFFICIAL_1_20_FORWARD_LABEL_ARCHIVE"
                if forward_label_ok
                else "UNAVAILABLE_INVALID_FORWARD_LABEL_ARCHIVE"
            ),
        ),
        CapabilityDisposition(
            capability="PIT_SECTOR",
            available=pit_sector_ok,
            reason=(
                "AVAILABLE_STATIC_COMPETITION_SECTORS"
                if pit_sector_ok
                else "UNAVAILABLE_INVALID_COMPETITION_UNIVERSE"
            ),
        ),
        CapabilityDisposition(
            capability="PIT_CORPORATE_ACTION_OPERATE",
            available=operate_corporate_action_ok,
            reason=operate_reason,
        ),
        *tuple(
            CapabilityDisposition(capability=name, available=False, reason=reason)
            for name, reason in _UNAVAILABLE_CAPABILITY_REASONS
        ),
    )
    available = {item.capability: item.available for item in capabilities}
    ready_for_e0 = bool(
        source_bytes_verified
        and available["CANONICAL_CALENDAR"]
        and available["PIT_CORPORATE_ACTION"]
        and available["E0_FACTOR_SNAPSHOT"]
        and _TRUSTED_EVIDENCE_KEYS
        and _TRUSTED_FACTOR_SNAPSHOT_HASHES
    )
    ready_for_e1 = bool(
        ready_for_e0
        and available["PIT_SECTOR"]
        and available["OFFICIAL_FORWARD_LABEL"]
    )
    current_inventory_hash = _inventory_hash()
    payload = {
        "inventory_id": _INVENTORY_ID,
        "inventory_hash": current_inventory_hash,
        "source_bytes_verified": source_bytes_verified,
        "sources": [item.to_dict() for item in sources],
        "inventory_errors": list(inventory_errors),
        "calendar_archive_verified": calendar.verified,
        "calendar_archive_source_sha256": calendar.source_sha256,
        "calendar_evidence_hash": calendar.evidence_hash,
        "calendar_confirmation_cutoff": calendar.confirmation_cutoff,
        "calendar_confirmed_session_count": calendar.confirmed_session_count,
        "calendar_scheduled_session_count": calendar.scheduled_session_count,
        "calendar_errors": list(calendar.errors),
        "capabilities": [item.to_dict() for item in capabilities],
        "trusted_evidence_key_count": len(_TRUSTED_EVIDENCE_KEYS),
        "trusted_factor_snapshot_count": len(_TRUSTED_FACTOR_SNAPSHOT_HASHES),
        "ready_for_e0": ready_for_e0,
        "ready_for_e1": ready_for_e1,
    }
    return ResearchEvidenceReadiness(
        inventory_id=_INVENTORY_ID,
        inventory_hash=current_inventory_hash,
        source_bytes_verified=source_bytes_verified,
        sources=sources,
        inventory_errors=inventory_errors,
        calendar_archive_verified=calendar.verified,
        calendar_archive_source_sha256=calendar.source_sha256,
        calendar_evidence_hash=calendar.evidence_hash,
        calendar_confirmation_cutoff=calendar.confirmation_cutoff,
        calendar_confirmed_session_count=calendar.confirmed_session_count,
        calendar_scheduled_session_count=calendar.scheduled_session_count,
        calendar_errors=calendar.errors,
        capabilities=capabilities,
        trusted_evidence_key_count=len(_TRUSTED_EVIDENCE_KEYS),
        trusted_factor_snapshot_count=len(_TRUSTED_FACTOR_SNAPSHOT_HASHES),
        ready_for_e0=ready_for_e0,
        ready_for_e1=ready_for_e1,
        audit_hash=_canonical_hash(payload),
    )


def inspect_research_evidence_readiness() -> ResearchEvidenceReadiness:
    """Rehash the fixed repository inventory and report honest readiness."""

    return _inspect_at_root(_repository_root())


def trusted_evidence_contains(
    *,
    kind: str,
    authority: str,
    source_version: str,
    source_sha256: str,
    evidence_hash: str,
) -> bool:
    """Return membership in the provider-owned immutable structured root."""

    if (
        not kind.strip()
        or not authority.strip()
        or not source_version.strip()
        or _HASH_RE.fullmatch(source_sha256) is None
        or _HASH_RE.fullmatch(evidence_hash) is None
    ):
        return False
    normalized_kind = _EVIDENCE_KIND_ALIASES.get(kind, kind)
    key = (
        normalized_kind,
        authority,
        source_version,
        source_sha256,
        evidence_hash,
    )
    if key not in _TRUSTED_EVIDENCE_KEYS:
        return False
    capability = _EVIDENCE_KIND_CAPABILITY.get(normalized_kind)
    if capability is None:
        return False
    readiness = inspect_research_evidence_readiness()
    availability = {
        item.capability: item.available for item in readiness.capabilities
    }
    return bool(
        readiness.source_bytes_verified and availability.get(capability, False)
    )


def trusted_factor_snapshot_contains(snapshot_hash: str) -> bool:
    """Return membership in the provider-owned immutable E0 snapshot root."""

    if (
        _HASH_RE.fullmatch(str(snapshot_hash)) is None
        or snapshot_hash not in _TRUSTED_FACTOR_SNAPSHOT_HASHES
    ):
        return False
    return inspect_research_evidence_readiness().ready_for_e0


@dataclass(frozen=True)
class OperateCorporateActionArchive:
    """Fail-closed parse of the operate-year dividend archive and its receipts."""

    present: bool
    receipt_count: int
    ticker_count: int
    years: tuple[str, ...]
    total_rows: int
    duplicate_count: int
    coverage_start: str
    coverage_end: str
    errors: tuple[str, ...]
    verified: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "present": self.present,
            "receipt_count": self.receipt_count,
            "ticker_count": self.ticker_count,
            "years": list(self.years),
            "total_rows": self.total_rows,
            "duplicate_count": self.duplicate_count,
            "coverage_start": self.coverage_start,
            "coverage_end": self.coverage_end,
            "errors": list(self.errors),
            "verified": self.verified,
            "reason": self.reason,
        }


def _operate_archive_result(
    *,
    present: bool,
    receipt_count: int = 0,
    ticker_count: int = 0,
    years: tuple[str, ...] = (),
    total_rows: int = 0,
    duplicate_count: int = 0,
    coverage_start: str = "",
    coverage_end: str = "",
    errors: tuple[str, ...],
    verified: bool,
    reason: str,
) -> OperateCorporateActionArchive:
    return OperateCorporateActionArchive(
        present=present,
        receipt_count=receipt_count,
        ticker_count=ticker_count,
        years=years,
        total_rows=total_rows,
        duplicate_count=duplicate_count,
        coverage_start=coverage_start,
        coverage_end=coverage_end,
        errors=errors,
        verified=verified,
        reason=reason,
    )


def _normalize_operate_tickers(raw: Any) -> list[str]:
    normalized: list[str] = []
    for code in raw:
        text = str(code).upper()
        if text.endswith(".SH"):
            normalized.append("sh." + text.split(".")[0].lower())
        elif text.endswith(".SZ"):
            normalized.append("sz." + text.split(".")[0].lower())
        else:
            normalized.append(str(code).lower())
    return normalized


def _official_operate_tickers(root: Path) -> tuple[str, ...] | None:
    """Return the official 49 in baostock 'sh.600000' query form.

    The authority is the hash-pinned contest Excel contract, whose audit
    independently verifies the workbook byte hash and its fixed semantic
    identity.  It is a binary file so it is not coupled to the Windows CRLF
    blocker.  The Sina snapshot manifest is at most an optional cross check and
    is not required for the authority to resolve.
    """

    from jiuwenswarm.quant.reporting.contest_universe_archive import (
        inspect_contest_universe_archive,
    )

    try:
        audit = inspect_contest_universe_archive()
    except Exception:  # noqa: BLE001 - the workbook audit is a fixed trusted root
        return None
    if not getattr(audit, "verified", False):
        return None
    codes = _normalize_operate_tickers(getattr(audit, "company_codes", ()) or ())
    if len(codes) != 49 or len(set(codes)) != 49:
        return None
    return tuple(sorted(codes))


def _operate_trusted_key() -> tuple[str, str, str, str, str] | None:
    """Derive the operate trusted-evidence identity from the pinned specs."""
    if not OPERATE_CORPORATE_ACTION_SPECS:
        return None
    by_id = {spec.artifact_id: spec for spec in OPERATE_CORPORATE_ACTION_SPECS}
    records = by_id.get("operate_corporate_actions_records")
    csv_spec = by_id.get("operate_corporate_actions_csv")
    if records is None or csv_spec is None:
        return None
    return (
        "corporate_action_operate",
        "BAOSTOCK_QUERY_DIVIDEND_DATA_OPERATE",
        "corporate_action_operate_2020_2025/v1",
        records.expected_sha256,
        csv_spec.expected_sha256,
    )


def _operate_key_admitted() -> bool:
    key = _operate_trusted_key()
    return key is not None and key in _TRUSTED_EVIDENCE_KEYS


def operate_window_projection(
    *,
    window_start: str,
    window_end: str,
    tickers: Sequence[str],
) -> tuple[tuple[str, ...], ...]:
    """Authoritative sorted full 8-tuple operate projection for an exact window.

    Fails closed unless the operate archive is pinned and its CSV bytes hash to
    the pinned value; the projection is recomputed only from those verified
    bytes.  Caller-provided hashes and trust monkeypatches are never authority.
    """

    if not OPERATE_CORPORATE_ACTION_SPECS:
        raise ValueError("operate archive is not pinned")
    csv_spec = OPERATE_CORPORATE_ACTION_SPECS[0]
    csv_path = _repository_root() / csv_spec.relative_path
    if _sha256_file(csv_path) != csv_spec.expected_sha256:
        raise ValueError("operate archive CSV hash mismatch")
    ticker_set = frozenset(str(item) for item in tickers)
    events: list[tuple[str, ...]] = []
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            code = str(row["code"])
            if code not in ticker_set:
                continue
            operate_date = str(row["dividOperateDate"])
            if not (window_start <= operate_date <= window_end):
                continue
            events.append(
                (code,) + tuple(str(row[field]) for field in _OPERATE_ACTION_IDENTITY_FIELDS)
            )
    return tuple(sorted(events))


def _read_operate_csv(
    csv_path: Path,
    official: tuple[str, ...] | None,
) -> tuple[tuple[str, ...], int, list[dict[str, str]]]:
    errors: list[str] = []
    data_rows = 0
    rows: list[dict[str, str]] = []
    try:
        with csv_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.reader(handle)
            header = next(reader, None)
            if header != list(_OPERATE_CANONICAL_COLUMNS):
                return ("OPERATE_CSV_HEADER_MISMATCH",), 0, rows
            official_set = set(official) if official is not None else None
            identities: set[tuple[str, ...]] = set()
            for row in reader:
                if not row:
                    continue
                if len(row) != len(_OPERATE_CANONICAL_COLUMNS):
                    return ("OPERATE_CSV_ROW_WIDTH_MISMATCH",), data_rows, rows
                values = dict(zip(_OPERATE_CANONICAL_COLUMNS, row))
                code = values["code"]
                operate_date = values["dividOperateDate"]
                if official_set is not None and code not in official_set:
                    return ("OPERATE_CSV_UNKNOWN_TICKER",), data_rows, rows
                try:
                    date.fromisoformat(operate_date)
                except ValueError:
                    return ("OPERATE_CSV_INVALID_DATE",), data_rows, rows
                if not (
                    _OPERATE_COVERAGE_START
                    <= operate_date
                    <= _OPERATE_COVERAGE_END
                ):
                    return ("OPERATE_CSV_DATE_OUT_OF_BOUNDS",), data_rows, rows
                identity = (values["code"],) + tuple(
                    values.get(field, "") for field in _OPERATE_ACTION_IDENTITY_FIELDS
                )
                if identity in identities:
                    return ("OPERATE_CSV_DUPLICATE_ACTION",), data_rows, rows
                identities.add(identity)
                rows.append(values)
                data_rows += 1
    except (OSError, UnicodeDecodeError, csv.Error, StopIteration):
        return ("OPERATE_CSV_UNREADABLE",), 0, rows
    return tuple(errors), data_rows, rows


def _operate_identity_indexes(fields: list[str]) -> list[int] | None:
    """Column indexes of the canonical action identity fields, or None."""
    indexes: list[int] = []
    for field in _OPERATE_ACTION_IDENTITY_FIELDS:
        try:
            indexes.append(fields.index(field))
        except ValueError:
            return None
    return indexes


def _receipt_deep_errors(receipt: dict[str, Any]) -> list[str]:
    """Independently verify one receipt's content against its recorded hash."""
    errors: list[str] = []
    if receipt.get("yearType") != "operate":
        errors.append("OPERATE_RECEIPT_WRONG_YEARTYPE")
    if receipt.get("failed") is not False:
        errors.append("OPERATE_RECEIPT_FAILED_FLAG")
    if receipt.get("error_code") != "0":
        errors.append("OPERATE_RECEIPT_NONZERO_CODE")
    fields = receipt.get("fields")
    rows = receipt.get("rows")
    if not isinstance(fields, list) or not isinstance(rows, list):
        return [*errors, "OPERATE_RECEIPT_BAD_SCHEMA"]
    missing = [
        field
        for field in _OPERATE_CANONICAL_COLUMNS[1:]
        if field not in fields
    ]
    if missing:
        errors.append("OPERATE_RECEIPT_MISSING_REQUIRED_FIELD")
    if receipt.get("row_count") != len(rows):
        errors.append("OPERATE_RECEIPT_ROW_COUNT_MISMATCH")
    for row in rows:
        if not isinstance(row, list) or len(row) != len(fields):
            return [*errors, "OPERATE_RECEIPT_ROW_WIDTH_MISMATCH"]
    stored_hash = str(receipt.get("response_payload_sha256") or "")
    computed_hash = _canonical_hash({"fields": fields, "rows": rows})
    if stored_hash != computed_hash:
        errors.append("OPERATE_RECEIPT_PAYLOAD_HASH_MISMATCH")
    identity_indexes = _operate_identity_indexes(fields)
    if identity_indexes is None:
        return [*errors, "OPERATE_RECEIPT_MISSING_IDENTITY_FIELD"]
    if "dividOperateDate" not in fields:
        return [*errors, "OPERATE_RECEIPT_MISSING_OPERATE_DATE_FIELD"]
    operate_index = fields.index("dividOperateDate")
    year = str(receipt.get("year") or "")
    code = str(receipt.get("code") or "")
    seen: Counter[tuple[str, ...]] = Counter()
    for row in rows:
        operate_date = str(row[operate_index]).strip()
        try:
            parsed = date.fromisoformat(operate_date)
        except ValueError:
            errors.append("OPERATE_RECEIPT_INVALID_DATE")
            continue
        if parsed.strftime("%Y") != year:
            errors.append("OPERATE_RECEIPT_DATE_YEAR_MISMATCH")
        seen[(code,) + tuple(str(row[i]) for i in identity_indexes)] += 1
    recomputed_duplicates = sum(count - 1 for count in seen.values() if count > 1)
    if recomputed_duplicates != int(receipt.get("duplicate_count") or 0):
        errors.append("OPERATE_RECEIPT_DUPLICATE_COUNT_MISMATCH")
    return errors


def _reconstruct_operate_rows(
    receipts: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """Rebuild the deduplicated canonical CSV rows exactly from receipts."""
    identity_counts: Counter[tuple[str, ...]] = Counter()
    rows: list[dict[str, str]] = []
    for receipt in receipts:
        if not isinstance(receipt, dict):
            continue
        code = str(receipt.get("code") or "")
        fields = receipt.get("fields")
        if not isinstance(fields, list):
            continue
        for raw_row in receipt.get("rows") or []:
            values: dict[str, str] = {}
            for index, field in enumerate(fields):
                values[field] = (
                    str(raw_row[index]) if index < len(raw_row) else ""
                )
            canonical: dict[str, str] = {"code": code}
            for column in _OPERATE_CANONICAL_COLUMNS:
                if column == "code":
                    continue
                canonical[column] = values.get(column, "")
            identity = (code,) + tuple(
                canonical.get(field, "") for field in _OPERATE_ACTION_IDENTITY_FIELDS
            )
            identity_counts[identity] += 1
            if identity_counts[identity] == 1:
                rows.append(canonical)
    rows.sort(
        key=lambda row: tuple(row.get(column, "") for column in _OPERATE_CANONICAL_COLUMNS)
    )
    return rows


def _validate_operate_manifest(
    manifest: dict[str, Any],
    csv_path: Path,
    root: Path,
) -> tuple[str, ...]:
    errors: list[str] = []
    if manifest.get("schema") != _OPERATE_SCHEMA:
        errors.append("OPERATE_SCHEMA_MISMATCH")
    if manifest.get("archive_id") != _OPERATE_ARCHIVE_ID:
        errors.append("OPERATE_ARCHIVE_ID_MISMATCH")
    if manifest.get("years") != list(_OPERATE_YEARS):
        errors.append("OPERATE_YEARS_MISMATCH")
    if manifest.get("coverage_start") != _OPERATE_COVERAGE_START or manifest.get(
        "coverage_end"
    ) != _OPERATE_COVERAGE_END:
        errors.append("OPERATE_COVERAGE_MISMATCH")
    official = _official_operate_tickers(root)
    tickers = manifest.get("tickers")
    if official is None:
        errors.append("UNVERIFIED_OFFICIAL_UNIVERSE")
    elif not isinstance(tickers, list) or {str(item) for item in tickers} != set(
        official
    ):
        errors.append("OPERATE_TICKER_SET_MISMATCH")
    receipts = manifest.get("per_request")
    if not isinstance(receipts, list):
        errors.append("OPERATE_RECEIPTS_MISSING")
        receipts = []
    pairs: set[tuple[str, str]] = set()
    success_count = 0
    for receipt in receipts:
        if not isinstance(receipt, dict):
            continue
        pairs.add((str(receipt.get("code")), str(receipt.get("year"))))
        deep = _receipt_deep_errors(receipt)
        errors.extend(deep)
        if receipt.get("error_code") == "0" and receipt.get("failed") is False:
            success_count += 1
    if len(receipts) != _OPERATE_RECEIPT_COUNT:
        errors.append("OPERATE_RECEIPT_COUNT_MISMATCH")
    if len(pairs) != _OPERATE_RECEIPT_COUNT:
        errors.append("OPERATE_RECEIPT_NOT_UNIQUE")
    if success_count != _OPERATE_RECEIPT_COUNT:
        errors.append("OPERATE_RECEIPT_FAILED")
    if official is not None:
        expected_pairs = {
            (ticker, year) for ticker in official for year in _OPERATE_YEARS
        }
        if pairs != expected_pairs:
            errors.append("OPERATE_RECEIPT_COVERAGE_MISMATCH")
    total_rows = int(manifest.get("total_rows") or 0)
    duplicate_count = int(manifest.get("duplicate_count") or 0)
    csv_errors, csv_data_rows, csv_rows = _read_operate_csv(csv_path, official)
    errors.extend(csv_errors)
    if csv_data_rows != total_rows:
        errors.append("OPERATE_CSV_ROW_COUNT_MISMATCH")
    receipt_rows = sum(
        int(receipt.get("row_count") or 0)
        for receipt in receipts
        if isinstance(receipt, dict)
    )
    if receipt_rows != total_rows + duplicate_count:
        errors.append("OPERATE_CSV_MANIFEST_INCONSISTENT")
    recomputed_duplicates = sum(
        int(receipt.get("duplicate_count") or 0)
        for receipt in receipts
        if isinstance(receipt, dict)
    )
    if recomputed_duplicates != duplicate_count:
        errors.append("OPERATE_DUPLICATE_COUNT_MISMATCH")
    reconstructed = _reconstruct_operate_rows(receipts)
    if len(reconstructed) != total_rows:
        errors.append("OPERATE_RECONSTRUCT_ROW_COUNT_MISMATCH")
    elif reconstructed != csv_rows:
        errors.append("OPERATE_CSV_RECEIPT_PROJECTION_MISMATCH")
    return tuple(dict.fromkeys(errors))


def _inspect_corporate_action_operate_at_root(root: Path) -> OperateCorporateActionArchive:
    """Fully validate the operate archive at an explicit root; fail closed."""

    if not OPERATE_CORPORATE_ACTION_SPECS:
        return _operate_archive_result(
            present=False,
            errors=("OPERATE_ARCHIVE_NOT_PINNED",),
            verified=False,
            reason="UNAVAILABLE_PENDING_OPERATE_ARCHIVE_FETCH",
        )
    sources = tuple(_verify_source_file(root, spec) for spec in OPERATE_CORPORATE_ACTION_SPECS)
    if not all(item.verified for item in sources):
        reasons = tuple(item.reason for item in sources if not item.verified)
        return _operate_archive_result(
            present=True,
            errors=reasons,
            verified=False,
            reason="UNAVAILABLE_INVALID_OPERATE_ARCHIVE",
        )
    directory = root / _OPERATE_ARCHIVE_RELATIVE_DIRECTORY
    csv_path = directory / "corporate_actions.csv"
    records_path = directory / "source_records.json"
    try:
        manifest = json.loads(records_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return _operate_archive_result(
            present=True,
            errors=("INVALID_OPERATE_MANIFEST",),
            verified=False,
            reason="UNAVAILABLE_INVALID_OPERATE_ARCHIVE",
        )
    errors = _validate_operate_manifest(manifest, csv_path, root)
    if errors:
        return _operate_archive_result(
            present=True,
            errors=errors,
            verified=False,
            reason="UNAVAILABLE_INVALID_OPERATE_ARCHIVE",
        )
    years = tuple(str(item) for item in (manifest.get("years") or []))
    return _operate_archive_result(
        present=True,
        receipt_count=int(manifest.get("total_receipts") or 0),
        ticker_count=len(manifest.get("tickers") or []),
        years=years,
        total_rows=int(manifest.get("total_rows") or 0),
        duplicate_count=int(manifest.get("duplicate_count") or 0),
        coverage_start=str(manifest.get("coverage_start") or ""),
        coverage_end=str(manifest.get("coverage_end") or ""),
        errors=(),
        verified=True,
        reason="AVAILABLE_BAOSTOCK_OPERATE_DIVIDEND_ARCHIVE",
    )


def inspect_corporate_action_operate_archive() -> OperateCorporateActionArchive:
    """Validate the operate-year archive at the repository root; fail closed.

    The pinned ``OPERATE_CORPORATE_ACTION_SPECS`` are filled by the WP1-E2O
    network-fetch gate only after the real archive is generated, so offline this
    always reports present=False / UNAVAILABLE_PENDING_OPERATE_ARCHIVE_FETCH.
    """

    return _inspect_corporate_action_operate_at_root(_repository_root())
