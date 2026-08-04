"""Cryptographic binding for immutable run-scoped candidate packages."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


BINDING_SCHEMA = "candidate_artifact_binding/v1"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_sha256(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _load_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"candidate artifact is not a JSON object: {path.name}")
    return payload


def _binding_payload(candidate: Path) -> dict[str, Any]:
    candidate = candidate.resolve()
    report_manifest_path = candidate / "report_manifest.json"
    evidence_manifest_path = candidate / "evidence_manifest.json"
    portfolio_meta_path = candidate / "portfolio_meta.json"
    portfolio_path = candidate / "Portfolio.json"
    portfolio_report_path = candidate / "portfolio_report.md"
    required = (
        report_manifest_path,
        evidence_manifest_path,
        portfolio_meta_path,
        portfolio_path,
        portfolio_report_path,
    )
    missing = [path.name for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"candidate core artifacts missing: {missing}")

    snapshot_dir = candidate / "data_snapshot"
    snapshot_manifests = sorted(snapshot_dir.glob("*_manifest.json"))
    if len(snapshot_manifests) != 1:
        raise ValueError(
            "candidate binding requires exactly one market snapshot manifest; "
            f"got {len(snapshot_manifests)}"
        )
    snapshot_manifest_path = snapshot_manifests[0]
    snapshot_manifest = _load_object(snapshot_manifest_path)
    report_manifest = _load_object(report_manifest_path)
    evidence_manifest = _load_object(evidence_manifest_path)
    refs = evidence_manifest.get("evidence_refs")
    if not isinstance(refs, dict):
        raise ValueError("candidate evidence_refs must be an object")

    company_reports_dir = candidate / "company_reports"
    report_files = sorted(company_reports_dir.glob("*.md"))
    report_hashes = {
        path.name: _sha256(path)
        for path in report_files
    }
    report_tree_sha256 = _canonical_sha256(report_hashes)
    quality_metrics = report_manifest.get("quality_metrics") or {}
    if not isinstance(quality_metrics, dict):
        raise ValueError("candidate quality_metrics must be an object")

    candidate_id = str(report_manifest.get("candidate_id") or "")
    if not candidate_id or candidate_id != candidate.name:
        raise ValueError("candidate id does not match its immutable directory")

    return {
        "schema": BINDING_SCHEMA,
        "candidate_id": candidate_id,
        "candidate_relpath": f"submission_candidates/{candidate_id}",
        "snapshot_id": snapshot_manifest.get("snapshot_id"),
        "snapshot_manifest_file": snapshot_manifest_path.name,
        "snapshot_manifest_sha256": _sha256(snapshot_manifest_path),
        "report_manifest_sha256": _sha256(report_manifest_path),
        "evidence_manifest_sha256": _sha256(evidence_manifest_path),
        "portfolio_meta_sha256": _sha256(portfolio_meta_path),
        "portfolio_json_sha256": _sha256(portfolio_path),
        "portfolio_report_sha256": _sha256(portfolio_report_path),
        "company_report_hashes": report_hashes,
        "company_reports_tree_sha256": report_tree_sha256,
        "report_count": len(report_hashes),
        "evidence_count": len(refs),
        "announcement_facts": sum(
            1
            for ref in refs.values()
            if isinstance(ref, dict) and ref.get("source_type") != "market_data"
        ),
        "disclosure_reports": int(
            quality_metrics.get("report_grade_disclosure") or 0
        ),
    }


def write_candidate_binding(candidate_path: str | Path) -> dict[str, Any]:
    """Write and return the binding for one completed candidate core."""
    candidate = Path(candidate_path).resolve()
    payload = _binding_payload(candidate)
    document = {
        **payload,
        "binding_sha256": _canonical_sha256(payload),
    }
    binding_path = candidate / "candidate_binding.json"
    if binding_path.exists():
        raise FileExistsError(
            f"immutable candidate binding already exists: {binding_path}"
        )
    binding_path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {
        **document,
        "candidate_binding_file_sha256": _sha256(binding_path),
    }


def verify_candidate_binding(
    candidate_path: str | Path,
    expected: dict[str, Any],
) -> tuple[bool, list[str]]:
    """Recompute a candidate binding and compare it with the run artifact."""
    failures: list[str] = []
    candidate = Path(candidate_path).resolve()
    binding_path = candidate / "candidate_binding.json"
    try:
        stored = _load_object(binding_path)
        payload = _binding_payload(candidate)
        actual = {
            **payload,
            "binding_sha256": _canonical_sha256(payload),
            "candidate_binding_file_sha256": _sha256(binding_path),
        }
        if stored != {key: value for key, value in actual.items()
                      if key != "candidate_binding_file_sha256"}:
            failures.append("stored candidate binding does not match candidate files")
        if expected != actual:
            mismatched = sorted(
                key
                for key in set(expected) | set(actual)
                if expected.get(key) != actual.get(key)
            )
            failures.append(
                "run artifact candidate binding mismatch: " + ", ".join(mismatched)
            )
    except Exception as exc:  # noqa: BLE001 - verifier reports malformed artifacts
        failures.append(f"candidate binding verification failed: {exc}")
    return not failures, failures
