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
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from jiuwenswarm.quant.market_data_service import (
    MarketDataBundle,
    MarketDiagnostics,
    diagnose_market_data,
)
from jiuwenswarm.quant.stock_pool import ALL_STOCKS


@dataclass(frozen=True)
class SnapshotArtifacts:
    snapshot_id: str
    prices_path: Path
    volumes_path: Path
    manifest_path: Path
    manifest_sha256: str


@dataclass(frozen=True)
class MarketDataSnapshotArtifacts:
    """Files belonging to one complete ``MarketDataBundle`` snapshot."""

    snapshot_id: str
    artifact_paths: Mapping[str, Path]
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


_MARKET_DATA_SCHEMA = "market_data_bundle/v1"
_MARKET_MATRIX_NAMES = (
    "opens",
    "highs",
    "lows",
    "closes",
    "volumes",
    "secondary_closes",
    "benchmark_closes",
)
_MARKET_ARTIFACT_NAMES = (*_MARKET_MATRIX_NAMES, "diagnostics")


def _json_default(value: Any) -> Any:
    if isinstance(value, (datetime, pd.Timestamp)):
        return value.isoformat()
    item = getattr(value, "item", None)
    if callable(item):
        return item()
    raise TypeError(f"value is not JSON serializable: {type(value).__name__}")


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            default=_json_default,
        )
        + "\n"
    ).encode("utf-8")


def _market_matrix_frames(bundle: MarketDataBundle) -> dict[str, pd.DataFrame]:
    benchmark_name = str(bundle.benchmark_closes.name or "close")
    return {
        "opens": bundle.opens,
        "highs": bundle.highs,
        "lows": bundle.lows,
        "closes": bundle.closes,
        "volumes": bundle.volumes,
        "secondary_closes": bundle.secondary_closes,
        "benchmark_closes": bundle.benchmark_closes.rename(benchmark_name).to_frame(),
    }


def _combined_market_content_hash(raw_artifacts: Mapping[str, bytes]) -> str:
    combined = b"".join(
        name.encode("utf-8") + b"\0" + raw_artifacts[name] + b"\0"
        for name in sorted(raw_artifacts)
    )
    return _sha256(combined)


def write_market_data_snapshot(
    bundle: MarketDataBundle,
    diagnostics: MarketDiagnostics,
    output_dir: str | Path,
    snapshot_id: str | None = None,
    *,
    minimum_rows: int = 81,
) -> MarketDataSnapshotArtifacts:
    """Persist a verified full-bundle snapshot without weakening legacy APIs.

    ``minimum_rows`` may be reduced to the factor engine's 61-row lookback for
    a decision-time evidence slice.  It may never be reduced below that
    strategy invariant, and the chosen policy is recorded in the manifest.
    """

    tickers = [str(column) for column in bundle.closes.columns]
    if tickers != list(ALL_STOCKS):
        raise ValueError("market-data snapshot requires the exact official 49-ticker pool")
    if (
        not isinstance(minimum_rows, int)
        or isinstance(minimum_rows, bool)
        or minimum_rows < 61
    ):
        raise ValueError("market-data snapshot minimum_rows cannot be below 61")
    diagnostic_policy = {
        "minimum_rows": minimum_rows,
        "minimum_secondary_overlap_days": 20,
        "minimum_benchmark_rows": 60,
        "cross_source_tolerance_pct": 1.0,
    }
    recomputed = diagnose_market_data(bundle, tickers, **diagnostic_policy)
    if recomputed.to_dict() != diagnostics.to_dict():
        raise ValueError("diagnostics do not match the supplied market-data bundle")
    if not diagnostics.passed:
        raise ValueError("blocked market-data diagnostics cannot be snapshotted")

    frames = _market_matrix_frames(bundle)
    raw_artifacts = {name: _csv_bytes(frame) for name, frame in frames.items()}
    raw_artifacts["diagnostics"] = _json_bytes(diagnostics.to_dict())
    content_hash = _combined_market_content_hash(raw_artifacts)
    generated_at = datetime.now(timezone.utc)
    if snapshot_id is None:
        snapshot_id = (
            f"market_{generated_at:%Y%m%d_%H%M%S_%f}_{content_hash[:12]}"
        )

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    artifact_paths = {
        name: destination
        / (
            f"{snapshot_id}_{name}.csv.gz"
            if name != "diagnostics"
            else f"{snapshot_id}_{name}.json"
        )
        for name in _MARKET_ARTIFACT_NAMES
    }
    manifest_path = destination / f"{snapshot_id}_manifest.json"
    collisions = [
        path
        for path in (*artifact_paths.values(), manifest_path)
        if path.exists()
    ]
    if collisions:
        raise FileExistsError(
            "immutable market-data snapshot path already exists: "
            + ", ".join(path.name for path in collisions)
        )

    file_bytes = {
        name: _gzip_bytes(raw) if name != "diagnostics" else raw
        for name, raw in raw_artifacts.items()
    }
    written: list[Path] = []
    try:
        for name in _MARKET_ARTIFACT_NAMES:
            path = artifact_paths[name]
            _write_exclusive(path, file_bytes[name])
            written.append(path)
        manifest = {
            "schema": _MARKET_DATA_SCHEMA,
            "snapshot_id": snapshot_id,
            "generated_at": generated_at.isoformat(),
            "content_sha256": content_hash,
            "n_stocks": len(tickers),
            "n_trading_days": len(bundle.closes),
            "actual_start_date": str(bundle.closes.index[0]),
            "actual_end_date": str(bundle.closes.index[-1]),
            "stock_codes": tickers,
            "calendar_id": bundle.calendar_id,
            "adjustment_policy": bundle.adjustment_policy,
            "secondary_label": bundle.secondary_label,
            "as_of_time": bundle.as_of_time.isoformat(),
            "retrieved_at": bundle.retrieved_at.isoformat(),
            "provider_ledger": dict(bundle.provider_ledger),
            "provider_ledger_summary": _ledger_summary(bundle.provider_ledger),
            "provider_stats": dict(bundle.provider_stats),
            "provider_evidence": {
                name: asdict(evidence)
                for name, evidence in bundle.provider_evidence.items()
            },
            "diagnostics_passed": diagnostics.passed,
            "diagnostic_policy": diagnostic_policy,
            "diagnostic_blockers": list(diagnostics.blockers),
            "diagnostic_warnings": list(diagnostics.warnings),
            "artifacts": {
                name: {
                    "file": artifact_paths[name].name,
                    "format": "json" if name == "diagnostics" else "csv.gz",
                    "file_sha256": _sha256(file_bytes[name]),
                    "content_sha256": _sha256(raw_artifacts[name]),
                    "rows": (
                        None if name == "diagnostics" else len(frames[name])
                    ),
                    "columns": (
                        None
                        if name == "diagnostics"
                        else [str(column) for column in frames[name].columns]
                    ),
                }
                for name in _MARKET_ARTIFACT_NAMES
            },
        }
        manifest_bytes = _json_bytes(manifest)
        _write_exclusive(manifest_path, manifest_bytes)
        written.append(manifest_path)
    except Exception:
        for path in written:
            path.unlink(missing_ok=True)
        raise

    artifacts = MarketDataSnapshotArtifacts(
        snapshot_id=snapshot_id,
        artifact_paths=artifact_paths,
        manifest_path=manifest_path,
        manifest_sha256=_sha256(manifest_bytes),
    )
    verify_market_data_snapshot(artifacts)
    return artifacts


def load_market_data_snapshot(
    manifest_path: str | Path,
    *,
    expected_manifest_sha256: str,
) -> MarketDataSnapshotArtifacts:
    """Load a full snapshot only when its manifest matches a trusted hash."""

    path = Path(manifest_path)
    actual_hash = _sha256(path.read_bytes())
    if actual_hash != expected_manifest_sha256:
        raise ValueError("market-data manifest SHA-256 mismatch")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("schema") != _MARKET_DATA_SCHEMA:
        raise ValueError("unsupported market-data snapshot schema")
    recorded = manifest.get("artifacts", {})
    if set(recorded) != set(_MARKET_ARTIFACT_NAMES):
        raise ValueError("market-data artifact set does not match schema")
    return MarketDataSnapshotArtifacts(
        snapshot_id=str(manifest["snapshot_id"]),
        artifact_paths={
            name: path.parent / str(recorded[name]["file"])
            for name in _MARKET_ARTIFACT_NAMES
        },
        manifest_path=path,
        manifest_sha256=expected_manifest_sha256,
    )


def verify_market_data_snapshot(
    artifacts: MarketDataSnapshotArtifacts,
) -> dict[str, Any]:
    """Recompute every recorded hash and reject any inconsistent artifact."""

    manifest_bytes = artifacts.manifest_path.read_bytes()
    if artifacts.manifest_sha256 != _sha256(manifest_bytes):
        raise ValueError("market-data manifest SHA-256 mismatch")
    manifest = json.loads(manifest_bytes.decode("utf-8"))
    if manifest.get("schema") != _MARKET_DATA_SCHEMA:
        raise ValueError("unsupported market-data snapshot schema")
    if manifest.get("snapshot_id") != artifacts.snapshot_id:
        raise ValueError("market-data snapshot ID mismatch")
    diagnostic_policy = manifest.get("diagnostic_policy")
    if diagnostic_policy is None:
        # Backward compatibility for v1 snapshots written before the policy
        # field existed: those always used the original 81-row default.
        diagnostic_policy = {
            "minimum_rows": 81,
            "minimum_secondary_overlap_days": 20,
            "minimum_benchmark_rows": 60,
            "cross_source_tolerance_pct": 1.0,
        }
    expected_policy_keys = {
        "minimum_rows",
        "minimum_secondary_overlap_days",
        "minimum_benchmark_rows",
        "cross_source_tolerance_pct",
    }
    if set(diagnostic_policy) != expected_policy_keys:
        raise ValueError("market-data diagnostic policy is incomplete")
    if (
        not isinstance(diagnostic_policy["minimum_rows"], int)
        or isinstance(diagnostic_policy["minimum_rows"], bool)
        or diagnostic_policy["minimum_rows"] < 61
        or diagnostic_policy["minimum_secondary_overlap_days"] != 20
        or diagnostic_policy["minimum_benchmark_rows"] != 60
        or diagnostic_policy["cross_source_tolerance_pct"] != 1.0
    ):
        raise ValueError("market-data diagnostic policy is outside safe bounds")
    if manifest.get("n_trading_days", 0) < diagnostic_policy["minimum_rows"]:
        raise ValueError("market-data snapshot is shorter than its diagnostic policy")
    recorded = manifest.get("artifacts", {})
    if set(recorded) != set(_MARKET_ARTIFACT_NAMES):
        raise ValueError("market-data artifact set does not match schema")
    if set(artifacts.artifact_paths) != set(_MARKET_ARTIFACT_NAMES):
        raise ValueError("market-data artifact paths do not match schema")

    raw_artifacts: dict[str, bytes] = {}
    for name in _MARKET_ARTIFACT_NAMES:
        path = artifacts.artifact_paths[name]
        entry = recorded[name]
        if path.name != entry.get("file"):
            raise ValueError(f"{name} artifact filename mismatch")
        archived = path.read_bytes()
        if _sha256(archived) != entry.get("file_sha256"):
            raise ValueError(f"{name} artifact SHA-256 mismatch")
        raw = archived if name == "diagnostics" else gzip.decompress(archived)
        if _sha256(raw) != entry.get("content_sha256"):
            raise ValueError(f"{name} content SHA-256 mismatch")
        raw_artifacts[name] = raw

    if _combined_market_content_hash(raw_artifacts) != manifest.get("content_sha256"):
        raise ValueError("combined market-data content SHA-256 mismatch")
    diagnostics = json.loads(raw_artifacts["diagnostics"].decode("utf-8"))
    if diagnostics.get("passed") is not True or manifest.get("diagnostics_passed") is not True:
        raise ValueError("market-data diagnostics are not passed")
    stock_codes = [str(code) for code in manifest.get("stock_codes", [])]
    ledger = manifest.get("provider_ledger", {})
    if len(stock_codes) != 49 or len(set(stock_codes)) != 49:
        raise ValueError("market-data manifest does not contain exact 49 tickers")
    if set(ledger) != set(stock_codes) or any(
        not str(value).strip() for value in ledger.values()
    ):
        raise ValueError("market-data provider ledger does not cover 49 tickers")
    return manifest


def install_market_data_snapshot_in_candidate(
    artifacts: MarketDataSnapshotArtifacts,
    candidate_root: str | Path,
) -> tuple[str, str]:
    """Install every full-bundle artifact and verify with the trusted hash."""

    verify_market_data_snapshot(artifacts)
    target = Path(candidate_root) / "data_snapshot"
    target.mkdir(parents=True, exist_ok=True)
    sources = (*artifacts.artifact_paths.values(), artifacts.manifest_path)
    collisions = [target / source.name for source in sources if (target / source.name).exists()]
    if collisions:
        raise FileExistsError(
            "immutable candidate snapshot path already exists: "
            + ", ".join(path.name for path in collisions)
        )
    installed_paths: list[Path] = []
    try:
        for source in sources:
            destination = target / source.name
            shutil.copy2(source, destination)
            installed_paths.append(destination)
        installed = load_market_data_snapshot(
            target / artifacts.manifest_path.name,
            expected_manifest_sha256=artifacts.manifest_sha256,
        )
        verify_market_data_snapshot(installed)
    except Exception:
        for path in installed_paths:
            path.unlink(missing_ok=True)
        raise
    return f"data_snapshot/{artifacts.manifest_path.name}", installed.manifest_sha256
