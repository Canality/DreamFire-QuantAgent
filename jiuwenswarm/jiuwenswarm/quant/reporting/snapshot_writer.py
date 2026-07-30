"""Immutable, self-verifying market-data snapshots.

Both the direct pipeline and the JiuwenSwarm Extension use this module.  A
snapshot is only valid when prices, volumes, the per-ticker provider ledger,
and every recorded hash agree.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import pandas as pd


@dataclass(frozen=True)
class SnapshotArtifacts:
    snapshot_id: str
    prices_path: Path
    volumes_path: Path
    manifest_path: Path
    manifest_sha256: str


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _csv_bytes(frame: pd.DataFrame) -> bytes:
    return frame.to_csv(lineterminator="\n").encode("utf-8")


def _gzip_bytes(data: bytes) -> bytes:
    return gzip.compress(data, compresslevel=9, mtime=0)


def _write_exclusive(path: Path, data: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(data)


def _validate_inputs(
    prices: pd.DataFrame,
    volumes: pd.DataFrame,
    provider_ledger: Mapping[str, str],
) -> None:
    if prices.empty or volumes.empty:
        raise ValueError("prices and volumes must both be non-empty")
    if not prices.index.equals(volumes.index) or list(prices.columns) != list(volumes.columns):
        raise ValueError("prices and volumes must have identical index and columns")
    expected = {str(column) for column in prices.columns}
    actual = set(provider_ledger)
    if actual != expected:
        raise ValueError(
            "provider ledger must cover snapshot columns exactly; "
            f"missing={sorted(expected - actual)}, extra={sorted(actual - expected)}"
        )
    invalid = sorted(ticker for ticker, provider in provider_ledger.items() if not str(provider).strip())
    if invalid:
        raise ValueError(f"provider ledger contains empty providers: {invalid}")


def write_data_snapshot(
    prices: pd.DataFrame,
    volumes: pd.DataFrame,
    provider_ledger: Mapping[str, str],
    provider_stats: Mapping[str, Mapping[str, Any]],
    output_dir: str | Path,
    snapshot_id: str | None = None,
) -> SnapshotArtifacts:
    """Write an immutable snapshot and return its verified artifacts."""
    _validate_inputs(prices, volumes, provider_ledger)
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)

    prices_raw = _csv_bytes(prices)
    volumes_raw = _csv_bytes(volumes)
    content_hash = _sha256(prices_raw + b"\n--VOLUMES--\n" + volumes_raw)
    generated_at = datetime.now(timezone.utc)
    if snapshot_id is None:
        snapshot_id = f"snap_{generated_at:%Y%m%d_%H%M%S_%f}_{content_hash[:12]}"

    prices_path = destination / f"{snapshot_id}_prices.csv.gz"
    volumes_path = destination / f"{snapshot_id}_volumes.csv.gz"
    manifest_path = destination / f"{snapshot_id}_manifest.json"
    collisions = [
        path for path in (prices_path, volumes_path, manifest_path) if path.exists()
    ]
    if collisions:
        raise FileExistsError(
            "immutable snapshot path already exists: "
            + ", ".join(path.name for path in collisions)
        )
    prices_gzip = _gzip_bytes(prices_raw)
    volumes_gzip = _gzip_bytes(volumes_raw)
    _write_exclusive(prices_path, prices_gzip)
    try:
        _write_exclusive(volumes_path, volumes_gzip)
        manifest = {
            "snapshot_id": snapshot_id,
            "generated_at": generated_at.isoformat(),
            "content_sha256": content_hash,
            "prices_content_sha256": _sha256(prices_raw),
            "volumes_content_sha256": _sha256(volumes_raw),
            "prices_file_sha256": _sha256(prices_gzip),
            "volumes_file_sha256": _sha256(volumes_gzip),
            "n_stocks": len(prices.columns),
            "n_trading_days": len(prices),
            "actual_start_date": str(prices.index[0]),
            "actual_end_date": str(prices.index[-1]),
            "stock_codes": sorted(str(column) for column in prices.columns),
            "prices_file": prices_path.name,
            "volumes_file": volumes_path.name,
            "provider_stats": dict(provider_stats),
            "provider_ledger": dict(provider_ledger),
            "provider_ledger_summary": _ledger_summary(provider_ledger),
        }
        manifest_bytes = (
            json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
        ).encode("utf-8")
        _write_exclusive(manifest_path, manifest_bytes)
    except Exception:
        prices_path.unlink(missing_ok=True)
        volumes_path.unlink(missing_ok=True)
        manifest_path.unlink(missing_ok=True)
        raise

    artifacts = SnapshotArtifacts(
        snapshot_id=snapshot_id,
        prices_path=prices_path,
        volumes_path=volumes_path,
        manifest_path=manifest_path,
        manifest_sha256=_sha256(manifest_bytes),
    )
    verify_snapshot_artifacts(artifacts)
    return artifacts


def load_snapshot_artifacts(manifest_path: str | Path) -> SnapshotArtifacts:
    path = Path(manifest_path)
    manifest = json.loads(path.read_text(encoding="utf-8"))
    return SnapshotArtifacts(
        snapshot_id=str(manifest["snapshot_id"]),
        prices_path=path.parent / str(manifest["prices_file"]),
        volumes_path=path.parent / str(manifest["volumes_file"]),
        manifest_path=path,
        manifest_sha256=_sha256(path.read_bytes()),
    )


def verify_snapshot_artifacts(artifacts: SnapshotArtifacts) -> dict[str, Any]:
    """Fail closed if any archived byte or manifest assertion is inconsistent."""
    manifest = json.loads(artifacts.manifest_path.read_text(encoding="utf-8"))
    if artifacts.manifest_sha256 != _sha256(artifacts.manifest_path.read_bytes()):
        raise ValueError("manifest SHA-256 mismatch")
    if manifest.get("snapshot_id") != artifacts.snapshot_id:
        raise ValueError("snapshot ID mismatch")
    prices_gzip = artifacts.prices_path.read_bytes()
    volumes_gzip = artifacts.volumes_path.read_bytes()
    if _sha256(prices_gzip) != manifest.get("prices_file_sha256"):
        raise ValueError("prices archive SHA-256 mismatch")
    if _sha256(volumes_gzip) != manifest.get("volumes_file_sha256"):
        raise ValueError("volumes archive SHA-256 mismatch")
    prices_raw = gzip.decompress(prices_gzip)
    volumes_raw = gzip.decompress(volumes_gzip)
    if _sha256(prices_raw) != manifest.get("prices_content_sha256"):
        raise ValueError("prices content SHA-256 mismatch")
    if _sha256(volumes_raw) != manifest.get("volumes_content_sha256"):
        raise ValueError("volumes content SHA-256 mismatch")
    if _sha256(prices_raw + b"\n--VOLUMES--\n" + volumes_raw) != manifest.get("content_sha256"):
        raise ValueError("combined content SHA-256 mismatch")
    stock_codes = {str(code) for code in manifest.get("stock_codes", [])}
    ledger = manifest.get("provider_ledger", {})
    if set(ledger) != stock_codes or any(not str(value).strip() for value in ledger.values()):
        raise ValueError("provider ledger does not exactly cover manifest stock codes")
    return manifest


def install_snapshot_in_candidate(
    artifacts: SnapshotArtifacts,
    candidate_root: str | Path,
) -> tuple[str, str]:
    """Copy all snapshot files into a candidate and verify the copied bytes."""
    verify_snapshot_artifacts(artifacts)
    target = Path(candidate_root) / "data_snapshot"
    target.mkdir(parents=True, exist_ok=True)
    for source in (artifacts.prices_path, artifacts.volumes_path, artifacts.manifest_path):
        shutil.copy2(source, target / source.name)
    installed = load_snapshot_artifacts(target / artifacts.manifest_path.name)
    verify_snapshot_artifacts(installed)
    return f"data_snapshot/{artifacts.manifest_path.name}", installed.manifest_sha256


def _ledger_summary(ledger: Mapping[str, str]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for ticker, provider in sorted(ledger.items()):
        result.setdefault(str(provider), []).append(str(ticker))
    return result
