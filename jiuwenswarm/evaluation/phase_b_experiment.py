#!/usr/bin/env python3
"""WP1-B competition-aligned nested evaluation and promotion evidence."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util as _iu
import json
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from jiuwenswarm.quant.nested_evaluation import (
    NestedEvaluationPlan,
    build_git_binding,
    evaluate_nested_promotion,
)
from jiuwenswarm.quant.strategy_configs import STRATEGY_SPECS

_EVAL_DIR = Path(__file__).resolve().parent
_UE_SPEC = _iu.spec_from_file_location(
    "unified_baseline_evaluation",
    _EVAL_DIR / "unified_baseline_evaluation.py",
)
_UE = _iu.module_from_spec(_UE_SPEC)
assert _UE_SPEC.loader is not None
_UE_SPEC.loader.exec_module(_UE)

WP1B_OUTPUT_ROOT = _UE.REPO_ROOT / "output" / "wp1b_evaluations"
BASELINE = "production_six_factor"
CANDIDATES = (
    "phase_b_t0_control",
    "phase_b_t1_shrink",
    "phase_b_t2_score_alloc",
    "phase_b_t3_joint",
)
PHASE_B_BASELINES = (BASELINE, *CANDIDATES)
DEFAULT_PLAN = NestedEvaluationPlan()

PREREGISTRATION = {
    "protocol": "competition_nested_v1",
    "legacy_next_day_entry": "RESEARCH_ONLY",
    "legacy_phase_b_conclusion": (
        "Deprecated: historical +0.91pp and mutable latest results cannot promote"
    ),
    "outer_results_may_select_candidate": False,
    "candidate_set": list(CANDIDATES),
    "selection": (
        "Choose one frozen candidate using inner windows only; evaluate the "
        "locked candidate on untouched chronological outer windows"
    ),
    "official_window": {
        "decision": "close",
        "embargo_trading_days": 1,
        "entry": "open",
        "holding_days": 20,
        "exit": "close",
        "shares": "fixed",
    },
    "thresholds": asdict(DEFAULT_PLAN),
    "promotion_rule": (
        "Statistical gates plus exact pairing, current protocol, verified WP1-A "
        "snapshot provenance and clean Git state; any failure is fail-closed"
    ),
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_sha256(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_snapshot_binding(
    snapshot_dir: Path,
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    """Bind the manifest and recognize only explicit verified WP1-A metadata."""

    manifest_path = snapshot_dir / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError(f"Snapshot manifest missing: {manifest_path}")
    manifest = snapshot["manifest"]
    disk_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest != disk_manifest:
        raise ValueError("Loaded snapshot manifest differs from hashed manifest file")
    wp1a = manifest.get("wp1a_binding")
    verified_reports: dict[str, dict[str, str]] | None = None
    if isinstance(wp1a, dict) and wp1a.get("status") == "VERIFIED":
        verified_reports = {}
        for label in ("consistency_report", "regime_report"):
            path_value = wp1a.get(f"{label}_path")
            hash_value = str(wp1a.get(f"{label}_sha256", "")).lower()
            if not path_value:
                raise ValueError(f"WP1-A binding missing {label}_path")
            report_path = Path(str(path_value))
            if not report_path.is_absolute():
                report_path = (snapshot_dir / report_path).resolve()
            if not report_path.is_file() or _sha256(report_path) != hash_value:
                raise ValueError(f"WP1-A {label} hash/path mismatch")
            verified_reports[label] = {
                "path": str(report_path),
                "sha256": hash_value,
            }
    verified_wp1a = verified_reports is not None
    return {
        "snapshot_id": manifest["snapshot_id"],
        "manifest_path": str(manifest_path.resolve()),
        "manifest_sha256": _sha256(manifest_path),
        "manifest": manifest,
        "source": manifest.get("source"),
        "adjustment": manifest.get("adjustment"),
        "n_stocks": manifest.get("n_stocks"),
        "n_sectors": manifest.get("n_sectors"),
        "verified_wp1a": verified_wp1a,
        "wp1a_binding": wp1a if isinstance(wp1a, dict) else None,
        "verified_reports": verified_reports,
    }


def build_config_binding(plan: NestedEvaluationPlan) -> dict[str, Any]:
    payload = {
        "preregistration": PREREGISTRATION,
        "plan": asdict(plan),
        "strategies": {
            name: asdict(STRATEGY_SPECS[name]) for name in PHASE_B_BASELINES
        },
    }
    return {"sha256": _canonical_sha256(payload), "payload": payload}


def write_research_artifact(report: dict[str, Any], output_dir: Path) -> Path:
    """Write exactly one immutable artifact; never update a latest pointer."""

    output_dir.mkdir(parents=True, exist_ok=True)
    run_id = str(report.get("run_id", "")).strip()
    if not run_id or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for char in run_id):
        raise ValueError(f"Unsafe run_id: {run_id!r}")
    path = output_dir / f"{run_id}.json"
    with path.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False, allow_nan=False)
        handle.write("\n")
    return path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--datalen", type=int, default=500)
    parser.add_argument("--seed", type=int, default=DEFAULT_PLAN.seed)
    parser.add_argument(
        "--bootstrap-iterations",
        type=int,
        default=DEFAULT_PLAN.bootstrap_iterations,
    )
    parser.add_argument("--output-dir", type=Path, default=WP1B_OUTPUT_ROOT)
    args = parser.parse_args()

    started = time.time()
    plan = NestedEvaluationPlan(
        seed=args.seed,
        bootstrap_iterations=args.bootstrap_iterations,
    )
    print("=" * 78)
    print("WP1-B: competition-aligned nested evaluation")
    print(json.dumps(PREREGISTRATION, ensure_ascii=False, indent=2))
    print("=" * 78)

    snapshot_dir = (
        args.snapshot.resolve()
        if args.snapshot
        else _UE.create_snapshot(args.datalen)
    )
    snapshot = _UE.load_snapshot(snapshot_dir)
    opens, closes, volumes, index_close = _UE._prepare_frames(snapshot)
    starts = _UE.build_schedule(len(index_close))
    details: dict[str, list[dict[str, Any]]] = {}
    summaries: dict[str, dict[str, Any]] = {}
    for name in PHASE_B_BASELINES:
        print(f"[Run] {name}: {STRATEGY_SPECS[name].description}")
        rows = _UE.evaluate_strategy(
            name,
            opens,
            closes,
            volumes,
            index_close,
            starts,
        )
        details[name] = rows
        summaries[name] = _UE.summarize(rows)

    snapshot_binding = build_snapshot_binding(snapshot_dir, snapshot)
    config_binding = build_config_binding(plan)
    nested = evaluate_nested_promotion(
        details=details,
        baseline_name=BASELINE,
        candidate_names=CANDIDATES,
        git_state=build_git_binding(_UE.REPO_ROOT),
        snapshot_binding=snapshot_binding,
        config_binding=config_binding,
        plan=plan,
    )

    run_id = datetime.now().strftime("wp1b_%Y%m%d_%H%M%S")
    report = {
        "schema": "wp1b_evaluation_run/v1",
        "run_id": run_id,
        "created_at": datetime.now().astimezone().isoformat(),
        "preregistration": PREREGISTRATION,
        "snapshot_binding": snapshot_binding,
        "config_binding": config_binding,
        "summaries": summaries,
        "nested_evidence": nested,
        "details": details,
        "status": nested["status"],
        "promotion_eligible": nested["promotion_eligible"],
        "legacy_latest_files_modified": False,
        "elapsed_seconds": round(time.time() - started, 2),
    }
    path = write_research_artifact(report, args.output_dir.resolve())
    print(json.dumps({
        "status": report["status"],
        "promotion_eligible": report["promotion_eligible"],
        "selected_candidate": nested["selected_candidate"],
        "evaluation_hash": nested["evaluation_hash"],
        "artifact": str(path),
    }, ensure_ascii=False, indent=2))
    print("Legacy phase_b_latest.json and historical phase_b_*.json were not modified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
