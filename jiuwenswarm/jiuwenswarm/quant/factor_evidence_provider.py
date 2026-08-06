"""Research-only archive inventory and trust boundary for WP1-E evidence.

The repository contains one admitted official calendar archive but still lacks
the remaining authority archives required by WP1-E0/E1.  This module makes that
partial readiness machine-readable and never promotes future scheduled dates
to confirmed historical sessions.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jiuwenswarm.quant import official_calendar_archive


_HASH_RE = re.compile(r"[0-9a-f]{64}")
_INVENTORY_ID = "wp1_factor_evidence_inventory_v1"
_SNAPSHOT_RELATIVE_DIRECTORY = Path(
    "jiuwenswarm/evaluation/data_snapshots/sina_20260721_135352"
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

PINNED_SOURCE_FILES: tuple[PinnedSourceFile, ...] = (
    OFFICIAL_UNIVERSE_SPEC,
    SINA_MANIFEST_SPEC,
    SINA_OPEN_SPEC,
    SINA_HIGH_SPEC,
    SINA_LOW_SPEC,
    SINA_CLOSE_SPEC,
    SINA_VOLUME_SPEC,
    SINA_BENCHMARK_SPEC,
)

_EXPECTED_SNAPSHOT_FILE_NAMES = frozenset(
    spec.relative_path.name for spec in PINNED_SOURCE_FILES[1:]
)
_EXPECTED_MANIFEST_CHILDREN = {
    spec.relative_path.name: spec.expected_sha256
    for spec in PINNED_SOURCE_FILES[2:]
}
_UNAVAILABLE_CAPABILITY_REASONS: tuple[tuple[str, str], ...] = (
    ("PIT_SECTOR", "UNAVAILABLE_NO_HISTORICAL_SECTOR_VERSION"),
    (
        "OFFICIAL_FORWARD_LABEL",
        "UNAVAILABLE_RAW_NO_LEDGER",
    ),
    (
        "PIT_CORPORATE_ACTION",
        "UNAVAILABLE_NO_CORPORATE_ACTION_ARCHIVE",
    ),
    (
        "E0_FACTOR_SNAPSHOT",
        "UNAVAILABLE_UNADJUSTED_INPUT_AND_EMPTY_TRUST_ROOT",
    ),
)
_EVIDENCE_KIND_CAPABILITY = {
    "canonical_calendar": "CANONICAL_CALENDAR",
    "sector_metadata": "PIT_SECTOR",
    "official_forward_label": "OFFICIAL_FORWARD_LABEL",
    "corporate_action": "PIT_CORPORATE_ACTION",
}
_EVIDENCE_KIND_ALIASES = {"calendar": "canonical_calendar"}

# These are the only runtime admission roots consumed by E0/E1.  The calendar
# key is bound to repository-held official source records and only the sequence
# confirmed through the frozen daily-statistics cutoff.  Other roots stay empty.
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
        )
    }
)
_TRUSTED_FACTOR_SNAPSHOT_HASHES: frozenset[str] = frozenset()


def _inventory_hash() -> str:
    return _canonical_hash(
        {
            "inventory_id": _INVENTORY_ID,
            "pinned_source_files": [
                spec.to_dict() for spec in PINNED_SOURCE_FILES
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
    payload = {
        "inventory_id": _INVENTORY_ID,
        "inventory_hash": INVENTORY_HASH,
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
        inventory_hash=INVENTORY_HASH,
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
