#!/usr/bin/env python3
"""Run the frozen WP1-C round without outer-driven tuning or production edits."""

from __future__ import annotations

import argparse
import importlib.util as _iu
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from jiuwenswarm.quant.challenger_mechanisms import (
    CHALLENGER_IDS,
    SECTOR_CANDIDATE,
    TREND_CANDIDATE,
    OverlayResult,
    apply_challenger,
)
from jiuwenswarm.quant.challenger_registry import (
    BASE_STRATEGY_ID,
    WP1B_REVIEW_EVIDENCE_RELATIVE_PATH,
    build_registry,
    canonical_hash,
    file_sha256,
    validate_registry,
)
from jiuwenswarm.quant.nested_evaluation import (
    NestedEvaluationPlan,
    build_git_binding,
    evaluate_nested_promotion,
)
from jiuwenswarm.quant.stock_pool import ALL_STOCKS, SECTOR_MAP


EVALUATION_DIR = Path(__file__).resolve().parent
REPO_ROOT = EVALUATION_DIR.parents[1]
OUTPUT_ROOT = REPO_ROOT / "output" / "challenger_evaluations"
WP1B_TASK = REPO_ROOT / "coordination/active/WP1B-EVALUATION-0804.md"
WP1B_REVIEW = REPO_ROOT / WP1B_REVIEW_EVIDENCE_RELATIVE_PATH

_PB_SPEC = _iu.spec_from_file_location(
    "phase_b_experiment_for_wp1c",
    EVALUATION_DIR / "phase_b_experiment.py",
)
_PB = _iu.module_from_spec(_PB_SPEC)
assert _PB_SPEC.loader is not None
_PB_SPEC.loader.exec_module(_PB)
_UE = _PB._UE


def _overlay(candidate_id: str):
    def apply(
        base_scores: pd.DataFrame,
        closes: pd.DataFrame,
        opens: pd.DataFrame,
        volumes: pd.DataFrame,
    ) -> OverlayResult:
        return apply_challenger(
            candidate_id, base_scores, closes, opens, volumes
        )

    return apply


def _paired_return_delta(
    candidate: Sequence[Mapping[str, Any]],
    baseline: Sequence[Mapping[str, Any]],
    indices: Sequence[int],
) -> np.ndarray:
    return np.array([
        float(candidate[idx]["official"]["total_return"])
        - float(baseline[idx]["official"]["total_return"])
        for idx in indices
    ])


def _require_challenger_rows(
    candidate_id: str,
    rows: Sequence[Mapping[str, Any]],
) -> None:
    if len(rows) != 20:
        raise ValueError(f"{candidate_id} requires exact 20 frozen windows")
    for position, row in enumerate(rows):
        challenger = row.get("challenger")
        if (
            not isinstance(challenger, Mapping)
            or challenger.get("candidate_id") != candidate_id
            or not set(challenger.get("forward_returns", {})).issubset(ALL_STOCKS)
            or len(challenger.get("forward_returns", {})) < 2
        ):
            raise ValueError(
                f"{candidate_id} window {position} lacks exact challenger evidence"
            )


def _trend_prescreen(
    rows: Sequence[Mapping[str, Any]],
    return_delta: np.ndarray,
    inner_indices: Sequence[int],
) -> dict[str, Any]:
    rank_ics: list[float] = []
    target_coverage: list[int] = []
    for idx in inner_indices:
        challenger = rows[idx]["challenger"]
        signal = pd.Series(challenger["diagnostics"]["trend_consistency"])
        target = pd.Series(challenger["forward_returns"])
        if set(signal.index) != set(ALL_STOCKS):
            raise ValueError("trend prescreen requires exact 49-stock signal")
        if not set(target.index).issubset(ALL_STOCKS) or len(target) < 2:
            raise ValueError("trend prescreen target coverage is invalid")
        target_coverage.append(len(target))
        common = [ticker for ticker in ALL_STOCKS if ticker in target.index]
        signal_rank = signal.reindex(common).rank(method="average")
        target_rank = target.reindex(common).rank(method="average")
        correlation = signal_rank.corr(target_rank)
        rank_ics.append(0.0 if pd.isna(correlation) else float(correlation))
    evidence = {
        "median_rank_ic": round(float(np.median(rank_ics)), 8),
        "positive_ic_window_rate": round(float(np.mean(np.array(rank_ics) > 0)), 6),
        "paired_median_return_delta": round(float(np.median(return_delta)), 8),
        "min_forward_target_coverage": min(target_coverage),
    }
    checks = {
        "median_rank_ic_gt_zero": evidence["median_rank_ic"] > 0.0,
        "positive_ic_window_rate_gte_60pct": (
            evidence["positive_ic_window_rate"] >= 0.60
        ),
        "paired_median_return_delta_gt_zero": (
            evidence["paired_median_return_delta"] > 0.0
        ),
    }
    return {"evidence": evidence, "checks": checks, "passed": all(checks.values())}


def _sector_prescreen(
    rows: Sequence[Mapping[str, Any]],
    return_delta: np.ndarray,
    inner_indices: Sequence[int],
) -> dict[str, Any]:
    hits: list[bool] = []
    sign_agreements: list[bool] = []
    target_coverage: list[int] = []
    sectors = sorted(set(SECTOR_MAP.values()))
    for idx in inner_indices:
        challenger = rows[idx]["challenger"]
        diagnostics = challenger["diagnostics"]
        leadership = diagnostics["sector_leadership_score"]
        top2 = diagnostics["top2_leaders"]
        forward = pd.Series(challenger["forward_returns"])
        target_coverage.append(len(forward))
        forward_by_sector = {
            sector: float(np.mean([
                forward[ticker]
                for ticker in ALL_STOCKS
                if SECTOR_MAP[ticker] == sector and ticker in forward.index
            ]))
            for sector in sectors
        }
        if not all(np.isfinite(value) for value in forward_by_sector.values()):
            raise ValueError("sector prescreen lacks a finite target in every sector")
        best_sector = max(forward_by_sector, key=forward_by_sector.__getitem__)
        hits.append(best_sector in top2)
        sign_agreements.extend(
            np.sign(float(leadership[sector]))
            == np.sign(float(forward_by_sector[sector]))
            for sector in sectors
        )
    evidence = {
        "top2_forward_best_hit_rate": round(float(np.mean(hits)), 6),
        "sector_sign_agreement_rate": round(float(np.mean(sign_agreements)), 6),
        "paired_median_return_delta": round(float(np.median(return_delta)), 8),
        "min_forward_target_coverage": min(target_coverage),
    }
    checks = {
        "top2_forward_best_hit_rate_gte_40pct": (
            evidence["top2_forward_best_hit_rate"] >= 0.40
        ),
        "sector_sign_agreement_rate_gte_60pct": (
            evidence["sector_sign_agreement_rate"] >= 0.60
        ),
        "paired_median_return_delta_gt_zero": (
            evidence["paired_median_return_delta"] > 0.0
        ),
    }
    return {"evidence": evidence, "checks": checks, "passed": all(checks.values())}


def _tail_prescreen(
    rows: Sequence[Mapping[str, Any]],
    baseline: Sequence[Mapping[str, Any]],
    return_delta: np.ndarray,
    inner_indices: Sequence[int],
) -> dict[str, Any]:
    drawdown_delta = np.array([
        float(rows[idx]["official"]["max_drawdown"])
        - float(baseline[idx]["official"]["max_drawdown"])
        for idx in inner_indices
    ])
    evidence = {
        "median_drawdown_delta": round(float(np.median(drawdown_delta)), 8),
        "p10_return_delta": round(float(np.quantile(return_delta, 0.10)), 8),
        "median_return_delta": round(float(np.median(return_delta)), 8),
    }
    checks = {
        "median_drawdown_delta_lte_minus_10bp": (
            evidence["median_drawdown_delta"] <= -0.001
        ),
        "p10_return_delta_gte_minus_20bp": evidence["p10_return_delta"] >= -0.002,
        "median_return_delta_gte_minus_20bp": (
            evidence["median_return_delta"] >= -0.002
        ),
    }
    return {"evidence": evidence, "checks": checks, "passed": all(checks.values())}


def evaluate_inner_prescreens(
    details: Mapping[str, Sequence[Mapping[str, Any]]],
    construction_failures: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    """Evaluate frozen mechanism-specific gates on inner rows 0-9 only."""

    failed = dict(construction_failures or {})
    if (
        set(details) | set(failed) != {BASE_STRATEGY_ID, *CHALLENGER_IDS}
        or set(details) & set(failed)
        or BASE_STRATEGY_ID in failed
    ):
        raise ValueError("inner prescreen requires the exact frozen strategy set")
    baseline = details[BASE_STRATEGY_ID]
    if len(baseline) != 20:
        raise ValueError("inner prescreen requires exact 20 baseline windows")
    inner_indices = list(range(10))
    result: dict[str, dict[str, Any]] = {}
    for candidate_id in CHALLENGER_IDS:
        if candidate_id in failed:
            result[candidate_id] = {
                "candidate_id": candidate_id,
                "inner_indices": list(range(10)),
                "evidence": {"construction_failure": dict(failed[candidate_id])},
                "checks": {"construction_succeeded": False},
                "passed": False,
            }
            continue
        rows = details[candidate_id]
        _require_challenger_rows(candidate_id, rows)
        return_delta = _paired_return_delta(rows, baseline, inner_indices)
        if candidate_id == TREND_CANDIDATE:
            prescreen = _trend_prescreen(rows, return_delta, inner_indices)
        elif candidate_id == SECTOR_CANDIDATE:
            prescreen = _sector_prescreen(rows, return_delta, inner_indices)
        else:
            prescreen = _tail_prescreen(
                rows, baseline, return_delta, inner_indices
            )
        result[candidate_id] = {
            "candidate_id": candidate_id,
            "inner_indices": inner_indices,
            **prescreen,
        }
    return result


def _config_binding(
    registry: Mapping[str, Any],
    candidate_id: str,
    plan: NestedEvaluationPlan,
) -> dict[str, Any]:
    candidate = next(
        item for item in registry["candidates"] if item["candidate_id"] == candidate_id
    )
    payload = {
        "preregistration": {
            "protocol": plan.protocol,
            "candidate_set": [candidate_id],
            "registry_hash": registry["registry_hash"],
            "wp1b_evidence_hash": registry["wp1b_evidence_hash"],
        },
        "plan": asdict(plan),
        "strategies": {
            BASE_STRATEGY_ID: registry["base_strategy"],
            candidate_id: candidate,
        },
    }
    return {"sha256": canonical_hash(payload), "payload": payload}


def evaluate_round(
    *,
    details: Mapping[str, Sequence[Mapping[str, Any]]],
    registry: Mapping[str, Any],
    git_state: Mapping[str, Any],
    snapshot_binding: Mapping[str, Any],
    construction_failures: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Prescreen all three, then run each passing formula through WP1-B once."""

    validate_registry(registry, task_path=WP1B_TASK, review_path=WP1B_REVIEW)
    construction = dict(construction_failures or {})
    inner = evaluate_inner_prescreens(details, construction)
    plan = NestedEvaluationPlan()
    outer: dict[str, dict[str, Any]] = {}
    failures: dict[str, dict[str, Any]] = {
        candidate_id: dict(failure)
        for candidate_id, failure in construction.items()
    }
    for candidate_id in CHALLENGER_IDS:
        if not inner[candidate_id]["passed"]:
            if candidate_id not in failures:
                failures[candidate_id] = {
                    "stage": "INNER_PRESCREEN",
                    "failed_checks": [
                        name
                        for name, passed in inner[candidate_id]["checks"].items()
                        if not passed
                    ],
                }
            continue
        outer[candidate_id] = evaluate_nested_promotion(
            details={
                BASE_STRATEGY_ID: details[BASE_STRATEGY_ID],
                candidate_id: details[candidate_id],
            },
            baseline_name=BASE_STRATEGY_ID,
            candidate_names=[candidate_id],
            git_state=git_state,
            snapshot_binding=snapshot_binding,
            config_binding=_config_binding(registry, candidate_id, plan),
            plan=plan,
        )
        if outer[candidate_id]["status"] == "DOES_NOT_QUALIFY":
            failures[candidate_id] = {
                "stage": "OUTER_WP1B_GATE",
                "failed_checks": [
                    name
                    for name, passed in outer[candidate_id]["checks"].items()
                    if not passed
                ],
            }
    promotion_eligible = [
        candidate_id
        for candidate_id, result in outer.items()
        if result["promotion_eligible"]
    ]
    if promotion_eligible:
        status = "PROMOTION_ELIGIBLE"
    elif any(result["status"] == "RESEARCH_ONLY" for result in outer.values()):
        status = "RESEARCH_ONLY"
    else:
        status = "DOES_NOT_QUALIFY"
    deterministic = {
        "registry_hash": registry["registry_hash"],
        "snapshot_manifest_sha256": snapshot_binding["manifest_sha256"],
        "git": dict(git_state),
        "inner": inner,
        "outer_evaluation_hashes": {
            name: result["evaluation_hash"] for name, result in outer.items()
        },
        "detail_hashes": {
            name: canonical_hash(list(rows)) for name, rows in sorted(details.items())
        },
        "failures": failures,
        "status": status,
    }
    return {
        "schema": "wp1c_challenger_round/v1",
        "registry_hash": registry["registry_hash"],
        "inner": inner,
        "outer": outer,
        "failures": failures,
        "promotion_eligible_candidates": promotion_eligible,
        "production_pointer_updated": False,
        "status": status,
        "round_hash": canonical_hash(deterministic),
        "deterministic_inputs": deterministic,
    }


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")


def write_round_artifacts(
    *,
    run_id: str,
    registry: Mapping[str, Any],
    details: Mapping[str, Sequence[Mapping[str, Any]]],
    result: Mapping[str, Any],
    snapshot_binding: Mapping[str, Any],
    git_state: Mapping[str, Any],
    output_root: Path,
) -> Path:
    """Create one immutable evidence tree; never mutate a latest pointer."""

    if not run_id or any(
        char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
        for char in run_id
    ):
        raise ValueError(f"Unsafe run_id: {run_id!r}")
    run_dir = output_root.resolve() / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    _write_json(run_dir / "preregistration.json", dict(registry))
    for candidate_id, prescreen in result["inner"].items():
        _write_json(run_dir / "inner" / f"{candidate_id}.json", prescreen)
    for candidate_id, outer in result["outer"].items():
        _write_json(run_dir / "outer" / f"{candidate_id}.json", outer)
    for candidate_id, failure in result["failures"].items():
        _write_json(run_dir / "failures" / f"{candidate_id}.json", failure)
    for strategy, rows in details.items():
        _write_json(run_dir / "details" / f"{strategy}.json", list(rows))
    decision = {
        "status": result["status"],
        "round_hash": result["round_hash"],
        "promotion_eligible_candidates": result["promotion_eligible_candidates"],
        "production_pointer_updated": False,
        "outer_evaluation_hashes": result["deterministic_inputs"][
            "outer_evaluation_hashes"
        ],
        "failed_candidates": result["failures"],
    }
    _write_json(run_dir / "promotion_decision.json", decision)
    _write_json(
        run_dir / "reproduction.json",
        result["deterministic_inputs"],
    )
    evidence_files = sorted(
        path for path in run_dir.rglob("*.json") if path.name != "manifest.json"
    )
    manifest = {
        "schema": "wp1c_challenger_evidence_manifest/v1",
        "run_id": run_id,
        "created_at": datetime.now().astimezone().isoformat(),
        "round_hash": result["round_hash"],
        "status": result["status"],
        "registry_hash": registry["registry_hash"],
        "snapshot_binding": dict(snapshot_binding),
        "git": dict(git_state),
        "production_pointer_updated": False,
        "legacy_latest_files_modified": False,
        "files": {
            path.relative_to(run_dir).as_posix(): file_sha256(path)
            for path in evidence_files
        },
    }
    _write_json(run_dir / "manifest.json", manifest)
    return run_dir


def verify_round_artifacts(
    run_dir: Path,
    *,
    task_path: Path = WP1B_TASK,
    review_path: Path = WP1B_REVIEW,
) -> dict[str, Any]:
    """Recompute the exact immutable evidence tree and registry binding."""

    root = run_dir.resolve()
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise ValueError("challenger evidence manifest is missing or unsafe")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    claimed = manifest.get("files")
    if not isinstance(claimed, Mapping):
        raise ValueError("challenger manifest lacks file hashes")
    actual_files = {
        path.relative_to(root).as_posix(): path
        for path in root.rglob("*.json")
        if path.name != "manifest.json"
    }
    if set(actual_files) != set(claimed):
        raise ValueError("challenger evidence file set differs from manifest")
    for relative, path in actual_files.items():
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"unsafe challenger evidence file: {relative}")
        if file_sha256(path) != claimed[relative]:
            raise ValueError(f"challenger evidence SHA-256 mismatch: {relative}")
    registry = json.loads(
        (root / "preregistration.json").read_text(encoding="utf-8")
    )
    validate_registry(registry, task_path=task_path, review_path=review_path)
    decision = json.loads(
        (root / "promotion_decision.json").read_text(encoding="utf-8")
    )
    reproduction = json.loads(
        (root / "reproduction.json").read_text(encoding="utf-8")
    )
    if (
        manifest.get("registry_hash") != registry.get("registry_hash")
        or manifest.get("round_hash") != decision.get("round_hash")
        or manifest.get("status") != decision.get("status")
        or manifest.get("production_pointer_updated") is not False
        or manifest.get("legacy_latest_files_modified") is not False
        or decision.get("production_pointer_updated") is not False
    ):
        raise ValueError("challenger manifest/decision/registry binding mismatch")
    if canonical_hash(reproduction) != manifest["round_hash"]:
        raise ValueError("challenger reproduction payload differs from round hash")
    if (
        reproduction.get("registry_hash") != manifest["registry_hash"]
        or reproduction.get("git") != manifest.get("git")
        or reproduction.get("snapshot_manifest_sha256")
        != manifest.get("snapshot_binding", {}).get("manifest_sha256")
    ):
        raise ValueError("challenger reproduction inputs differ from manifest")
    detail_hashes = reproduction.get("detail_hashes", {})
    for strategy, expected_hash in detail_hashes.items():
        detail_path = root / "details" / f"{strategy}.json"
        detail_payload = json.loads(detail_path.read_text(encoding="utf-8"))
        if canonical_hash(detail_payload) != expected_hash:
            raise ValueError(f"challenger detail hash mismatch: {strategy}")
    inner_payload = {
        path.stem: json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((root / "inner").glob("*.json"))
    }
    failure_payload = {
        path.stem: json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((root / "failures").glob("*.json"))
    }
    outer_hashes = {
        path.stem: json.loads(path.read_text(encoding="utf-8"))["evaluation_hash"]
        for path in sorted((root / "outer").glob("*.json"))
    } if (root / "outer").is_dir() else {}
    if (
        inner_payload != reproduction.get("inner")
        or failure_payload != reproduction.get("failures")
        or outer_hashes != reproduction.get("outer_evaluation_hashes")
    ):
        raise ValueError("challenger evidence payload differs from reproduction")
    return {
        "passed": True,
        "run_id": manifest["run_id"],
        "round_hash": manifest["round_hash"],
        "registry_hash": manifest["registry_hash"],
        "files_verified": len(actual_files),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=OUTPUT_ROOT)
    args = parser.parse_args()

    registry = build_registry(task_path=WP1B_TASK, review_path=WP1B_REVIEW)
    validate_registry(registry, task_path=WP1B_TASK, review_path=WP1B_REVIEW)
    snapshot_dir = args.snapshot.resolve()
    snapshot = _UE.load_snapshot(snapshot_dir)
    opens, closes, volumes, index_close = _UE._prepare_frames(snapshot)
    starts = _UE.build_schedule(len(index_close))
    if len(starts) != 20:
        raise ValueError(f"WP1-C requires exact 20 windows, got {len(starts)}")
    details: dict[str, list[dict[str, Any]]] = {
        BASE_STRATEGY_ID: _UE.evaluate_strategy(
            BASE_STRATEGY_ID, opens, closes, volumes, index_close, starts
        )
    }
    construction_failures: dict[str, dict[str, Any]] = {}
    for candidate_id in CHALLENGER_IDS:
        try:
            details[candidate_id] = _UE.evaluate_strategy(
                BASE_STRATEGY_ID,
                opens,
                closes,
                volumes,
                index_close,
                starts,
                score_overlay=_overlay(candidate_id),
            )
        except (ValueError, RuntimeError) as exc:
            construction_failures[candidate_id] = {
                "stage": "CONSTRUCTION",
                "error_type": type(exc).__name__,
                "message": str(exc),
            }
    snapshot_binding = _PB.build_snapshot_binding(snapshot_dir, snapshot)
    git_state = build_git_binding(REPO_ROOT)
    result = evaluate_round(
        details=details,
        registry=registry,
        git_state=git_state,
        snapshot_binding=snapshot_binding,
        construction_failures=construction_failures,
    )
    run_id = datetime.now().strftime("wp1c_%Y%m%d_%H%M%S")
    run_dir = write_round_artifacts(
        run_id=run_id,
        registry=registry,
        details=details,
        result=result,
        snapshot_binding=snapshot_binding,
        git_state=git_state,
        output_root=args.output_root,
    )
    verification = verify_round_artifacts(run_dir)
    print(json.dumps({
        "status": result["status"],
        "round_hash": result["round_hash"],
        "inner_passed": [
            name for name, item in result["inner"].items() if item["passed"]
        ],
        "outer_evaluation_hashes": result["deterministic_inputs"][
            "outer_evaluation_hashes"
        ],
        "production_pointer_updated": False,
        "artifact": str(run_dir),
        "artifact_verification": verification,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
