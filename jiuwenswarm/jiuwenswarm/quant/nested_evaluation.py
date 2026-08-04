"""Deterministic nested evidence and fail-closed strategy promotion gates."""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np


class PairingError(ValueError):
    """Raised when candidate and baseline windows cannot be paired exactly."""


class OuterResultAccessError(RuntimeError):
    """Raised when an inner selector attempts to access outer evidence."""


@dataclass(frozen=True)
class NestedEvaluationPlan:
    """Frozen WP1-B thresholds and resampling configuration."""

    protocol: str = "competition_nested_v1"
    seed: int = 20260804
    min_inner_windows: int = 8
    min_outer_windows: int = 8
    bootstrap_iterations: int = 2_000
    bootstrap_block_windows: int = 3
    recent_decay: float = 0.90
    median_return_delta_min: float = 0.003
    bootstrap_positive_probability_min: float = 0.80
    utility_win_rate_min: float = 0.60
    p10_return_worsening_max: float = 0.005
    median_drawdown_worsening_max: float = 0.003
    worst_drawdown_worsening_max: float = 0.005

    def __post_init__(self) -> None:
        if self.min_inner_windows < 1 or self.min_outer_windows < 1:
            raise ValueError("Nested split requires positive inner/outer windows")
        if self.bootstrap_iterations < 1:
            raise ValueError("bootstrap_iterations must be positive")
        if self.bootstrap_block_windows < 1:
            raise ValueError("bootstrap_block_windows must be positive")
        if not 0 < self.recent_decay <= 1:
            raise ValueError("recent_decay must be in (0, 1]")


@dataclass(frozen=True)
class InnerCandidateScore:
    name: str
    median_return_delta: float
    utility_win_rate: float
    median_drawdown_delta: float


@dataclass(frozen=True)
class InnerSelectionView:
    """Only information exposed to candidate selection; no outer rows exist."""

    inner_indices: tuple[int, ...]
    candidate_scores: tuple[InnerCandidateScore, ...]


_IDENTITY_FIELDS = (
    "idx",
    "decision_date",
    "embargo_date",
    "entry_date",
    "valuation_dates",
    "exit_date",
)


def _canonical_hash(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _valid_sha256(value: object) -> bool:
    text = str(value)
    return len(text) == 64 and all(
        char in "0123456789abcdefABCDEF" for char in text
    )


def _verify_config_binding(
    binding: Mapping[str, Any],
    *,
    plan: NestedEvaluationPlan,
    baseline_name: str,
    candidate_names: Sequence[str],
) -> None:
    payload = binding.get("payload")
    if not isinstance(payload, Mapping):
        raise ValueError("config binding requires a canonical payload")
    claimed = str(binding.get("sha256", ""))
    if not _valid_sha256(claimed):
        raise ValueError("config binding requires a SHA-256 sha256")
    actual = _canonical_hash(payload)
    if claimed.lower() != actual:
        raise ValueError("config binding SHA-256 mismatch")
    if payload.get("plan") != asdict(plan):
        raise ValueError("config binding plan differs from evaluated plan")
    strategies = payload.get("strategies")
    expected_strategies = {baseline_name, *candidate_names}
    if not isinstance(strategies, Mapping) or set(strategies) != expected_strategies:
        raise ValueError("config binding does not contain the exact strategy set")
    preregistration = payload.get("preregistration")
    if not isinstance(preregistration, Mapping):
        raise ValueError("config binding requires preregistration metadata")
    if preregistration.get("protocol") != plan.protocol:
        raise ValueError("config preregistration protocol differs from plan")
    if list(preregistration.get("candidate_set", [])) != list(candidate_names):
        raise ValueError("config preregistration candidate set differs from evaluation")


def _verify_snapshot_binding(binding: Mapping[str, Any]) -> bool:
    manifest_path = Path(str(binding.get("manifest_path", ""))).resolve()
    if not manifest_path.is_file():
        raise ValueError(f"snapshot manifest missing: {manifest_path}")
    claimed = str(binding.get("manifest_sha256", ""))
    if not _valid_sha256(claimed) or _file_sha256(manifest_path) != claimed.lower():
        raise ValueError("snapshot manifest SHA-256 mismatch")
    disk_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if disk_manifest != binding.get("manifest"):
        raise ValueError("snapshot binding manifest payload differs from hashed file")
    if disk_manifest.get("snapshot_id") != binding.get("snapshot_id"):
        raise ValueError("snapshot id differs from hashed manifest")
    if int(disk_manifest.get("n_stocks", 0)) != 49:
        raise ValueError("snapshot binding does not cover 49 stocks")
    if int(disk_manifest.get("n_sectors", 0)) != 6:
        raise ValueError("snapshot binding does not cover 6 sectors")

    if not bool(binding.get("verified_wp1a", False)):
        return False
    wp1a = disk_manifest.get("wp1a_binding")
    if not isinstance(wp1a, Mapping) or wp1a.get("status") != "VERIFIED":
        raise ValueError("hashed snapshot manifest is not WP1-A VERIFIED")
    if binding.get("wp1a_binding") != wp1a:
        raise ValueError("WP1-A binding differs from hashed snapshot manifest")
    reports = binding.get("verified_reports")
    if not isinstance(reports, Mapping) or set(reports) != {
        "consistency_report",
        "regime_report",
    }:
        raise ValueError("verified WP1-A binding requires exact report set")
    for label, report in reports.items():
        if not isinstance(report, Mapping):
            raise ValueError(f"invalid WP1-A {label} binding")
        path = Path(str(report.get("path", ""))).resolve()
        report_hash = str(report.get("sha256", ""))
        manifest_path_value = wp1a.get(f"{label}_path")
        manifest_hash = str(wp1a.get(f"{label}_sha256", ""))
        if not manifest_path_value:
            raise ValueError(f"hashed manifest lacks WP1-A {label} path")
        manifest_report_path = Path(str(manifest_path_value))
        if not manifest_report_path.is_absolute():
            manifest_report_path = (
                manifest_path.parent / manifest_report_path
            ).resolve()
        if (
            path != manifest_report_path
            or report_hash.lower() != manifest_hash.lower()
            or not path.is_file()
            or not _valid_sha256(report_hash)
            or _file_sha256(path) != report_hash.lower()
        ):
            raise ValueError(f"WP1-A {label} SHA-256 mismatch")
        try:
            report_payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"WP1-A {label} is not valid JSON") from exc
        if (
            not isinstance(report_payload, Mapping)
            or report_payload.get("status") != "VERIFIED"
        ):
            raise ValueError(f"WP1-A {label} does not have VERIFIED status")
    return True


def _run_git(repo_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo_root), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise ValueError(
            f"Git verification failed for {' '.join(args)}: {result.stderr.strip()}"
        )
    return result.stdout.strip()


def build_git_binding(repo_root: Path) -> dict[str, Any]:
    """Read and bind the actual repository state used by the evaluator."""

    root = repo_root.resolve()
    commit = _run_git(root, "rev-parse", "HEAD")
    status = _run_git(root, "status", "--porcelain", "--untracked-files=all")
    return {
        "repo_root": str(root),
        "commit": commit,
        "dirty": bool(status),
        "status_porcelain_sha256": hashlib.sha256(status.encode("utf-8")).hexdigest(),
    }


def _verify_git_binding(binding: Mapping[str, Any]) -> dict[str, Any]:
    root = Path(str(binding.get("repo_root", ""))).resolve()
    current = build_git_binding(root)
    if dict(binding) != current:
        raise ValueError("Git binding differs from current repository state")
    if len(current["commit"]) != 40 or any(
        char not in "0123456789abcdefABCDEF" for char in current["commit"]
    ):
        raise ValueError("Git binding requires an exact 40-character commit")
    return current


def _validate_row(row: Mapping[str, Any], *, strategy: str, position: int) -> None:
    missing = [field for field in _IDENTITY_FIELDS if field not in row]
    if missing:
        raise PairingError(f"{strategy} window {position} missing fields: {missing}")
    valuations = list(row["valuation_dates"])
    if len(valuations) != 20:
        raise PairingError(
            f"{strategy} window {position} must contain exact 20 valuation dates"
        )
    if row["entry_date"] != valuations[0] or row["exit_date"] != valuations[-1]:
        raise PairingError(
            f"{strategy} window {position} entry/exit does not bind valuation dates"
        )
    ordered = [
        row["decision_date"],
        row["embargo_date"],
        row["entry_date"],
        *valuations[1:],
    ]
    if ordered != sorted(ordered) or len(set(ordered)) != len(ordered):
        raise PairingError(f"{strategy} window {position} date sequence is not causal")
    if int(row.get("n_stocks_covered", 0)) != 49:
        raise PairingError(f"{strategy} window {position} does not cover 49 stocks")
    if int(row.get("n_sectors_covered", 0)) != 6:
        raise PairingError(f"{strategy} window {position} does not cover 6 sectors")
    if int(row.get("n_forward_closes", 0)) != 20:
        raise PairingError(f"{strategy} window {position} does not contain 20 closes")
    official = row.get("official")
    if not isinstance(official, Mapping):
        raise PairingError(f"{strategy} window {position} lacks official metrics")
    for field in ("total_return", "max_drawdown"):
        if field not in official or not np.isfinite(float(official[field])):
            raise PairingError(
                f"{strategy} window {position} has invalid official {field}"
            )
    selected = row.get("selected_tickers")
    weights = row.get("weights")
    if selected is not None and weights is not None and set(selected) != set(weights):
        raise PairingError(
            f"{strategy} window {position} selection/allocation mismatch"
        )


def _validate_details(
    details: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    baseline_name: str,
    candidate_names: Sequence[str],
) -> int:
    expected_names = {baseline_name, *candidate_names}
    if set(details) != expected_names:
        raise PairingError(
            f"Expected exact strategy set {sorted(expected_names)}, got "
            f"{sorted(details)}"
        )
    n_windows = len(details[baseline_name])
    if n_windows == 0:
        raise PairingError("No evaluation windows")
    for name in sorted(expected_names):
        rows = details[name]
        if len(rows) != n_windows:
            raise PairingError(f"{name} window count differs from baseline")
        for position, row in enumerate(rows):
            _validate_row(row, strategy=name, position=position)
            baseline = details[baseline_name][position]
            if any(row[field] != baseline[field] for field in _IDENTITY_FIELDS):
                raise PairingError(
                    f"{name} window {position} window identity differs from baseline"
                )
    baseline_rows = details[baseline_name]
    if any(int(row["idx"]) != position for position, row in enumerate(baseline_rows)):
        raise PairingError("Baseline window indices are not canonical and contiguous")
    decision_dates = [str(row["decision_date"]) for row in baseline_rows]
    if decision_dates != sorted(decision_dates) or len(set(decision_dates)) != n_windows:
        raise PairingError("Baseline windows are not strictly chronological")
    return n_windows


def _nested_split(n_windows: int, plan: NestedEvaluationPlan) -> tuple[list[int], list[int]]:
    if n_windows < plan.min_inner_windows + plan.min_outer_windows:
        raise ValueError(
            f"Need at least {plan.min_inner_windows + plan.min_outer_windows} "
            f"windows for nested evidence, got {n_windows}"
        )
    split = n_windows // 2
    split = max(plan.min_inner_windows, split)
    split = min(split, n_windows - plan.min_outer_windows)
    return list(range(split)), list(range(split, n_windows))


def _paired_arrays(
    candidate: Sequence[Mapping[str, Any]],
    baseline: Sequence[Mapping[str, Any]],
    indices: Sequence[int],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    return_delta = np.array([
        float(candidate[idx]["official"]["total_return"])
        - float(baseline[idx]["official"]["total_return"])
        for idx in indices
    ])
    drawdown_delta = np.array([
        float(candidate[idx]["official"]["max_drawdown"])
        - float(baseline[idx]["official"]["max_drawdown"])
        for idx in indices
    ])
    utility_delta = 0.70 * return_delta - 0.30 * drawdown_delta
    return return_delta, drawdown_delta, utility_delta


def _inner_view(
    details: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    baseline_name: str,
    candidate_names: Sequence[str],
    inner_indices: Sequence[int],
) -> InnerSelectionView:
    baseline = details[baseline_name]
    scores: list[InnerCandidateScore] = []
    for name in candidate_names:
        returns, drawdowns, utility = _paired_arrays(
            details[name], baseline, inner_indices
        )
        scores.append(InnerCandidateScore(
            name=name,
            median_return_delta=float(np.median(returns)),
            utility_win_rate=float(np.mean(utility > 0)),
            median_drawdown_delta=float(np.median(drawdowns)),
        ))
    return InnerSelectionView(
        inner_indices=tuple(inner_indices),
        candidate_scores=tuple(scores),
    )


def _default_selector(view: InnerSelectionView) -> str:
    selected = max(
        view.candidate_scores,
        key=lambda item: (
            item.median_return_delta,
            item.utility_win_rate,
            -item.median_drawdown_delta,
            item.name,
        ),
    )
    return selected.name


def _select_candidate(
    view: InnerSelectionView,
    *,
    selection_metric: str,
) -> str:
    if selection_metric != "median_return_delta":
        if "outer" in selection_metric.lower():
            raise OuterResultAccessError(
                "Inner selector attempted to access outer results"
            )
        raise OuterResultAccessError(
            f"Unregistered inner selection metric: {selection_metric}"
        )
    selected = _default_selector(view)
    allowed = {item.name for item in view.candidate_scores}
    if selected not in allowed:
        raise ValueError(f"Inner selector returned unknown candidate {selected!r}")
    return selected


def moving_block_bootstrap(
    return_delta: np.ndarray,
    utility_delta: np.ndarray,
    *,
    iterations: int,
    block_windows: int,
    seed: int,
) -> dict[str, Any]:
    """Circular moving-block bootstrap preserving short serial dependence."""

    n = len(return_delta)
    if n == 0:
        raise ValueError("Bootstrap requires at least one paired outer window")
    block = min(block_windows, n)
    rng = np.random.default_rng(seed)
    median_samples = np.empty(iterations, dtype=float)
    utility_win_samples = np.empty(iterations, dtype=float)
    for sample_idx in range(iterations):
        sampled: list[int] = []
        while len(sampled) < n:
            start = int(rng.integers(0, n))
            sampled.extend((start + offset) % n for offset in range(block))
        indices = np.array(sampled[:n], dtype=int)
        median_samples[sample_idx] = float(np.median(return_delta[indices]))
        utility_win_samples[sample_idx] = float(np.mean(utility_delta[indices] > 0))
    return {
        "method": "circular_moving_block",
        "seed": seed,
        "iterations": iterations,
        "block_windows": block,
        "median_return_delta_ci95": [
            round(float(value), 8)
            for value in np.quantile(median_samples, [0.025, 0.975])
        ],
        "probability_median_delta_gt_zero": round(
            float(np.mean(median_samples > 0)), 6
        ),
        "utility_win_rate_ci95": [
            round(float(value), 8)
            for value in np.quantile(utility_win_samples, [0.025, 0.975])
        ],
    }


def _regime_stability(
    paired_table: Sequence[Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for regime in sorted({str(row["regime"]) for row in paired_table}):
        rows = [row for row in paired_table if row["regime"] == regime]
        deltas = np.array([float(row["return_delta"]) for row in rows])
        utilities = np.array([float(row["utility_delta"]) for row in rows])
        result[regime] = {
            "n_windows": len(rows),
            "median_return_delta": round(float(np.median(deltas)), 8),
            "p10_return_delta": round(float(np.quantile(deltas, 0.10)), 8),
            "utility_win_rate": round(float(np.mean(utilities > 0)), 6),
        }
    return result


def evaluate_nested_promotion(
    *,
    details: Mapping[str, Sequence[Mapping[str, Any]]],
    baseline_name: str,
    candidate_names: Sequence[str],
    git_state: Mapping[str, Any],
    snapshot_binding: Mapping[str, Any],
    config_binding: Mapping[str, Any],
    plan: NestedEvaluationPlan | None = None,
    selection_metric: str = "median_return_delta",
) -> dict[str, Any]:
    """Select on inner windows and judge promotion only on untouched outer rows."""

    frozen_plan = plan or NestedEvaluationPlan()
    if not candidate_names or len(set(candidate_names)) != len(candidate_names):
        raise ValueError("candidate_names must be unique and non-empty")
    _verify_config_binding(
        config_binding,
        plan=frozen_plan,
        baseline_name=baseline_name,
        candidate_names=candidate_names,
    )
    verified_wp1a = _verify_snapshot_binding(snapshot_binding)
    verified_git = _verify_git_binding(git_state)
    n_windows = _validate_details(
        details,
        baseline_name=baseline_name,
        candidate_names=candidate_names,
    )
    inner_indices, outer_indices = _nested_split(n_windows, frozen_plan)
    inner_view = _inner_view(
        details,
        baseline_name=baseline_name,
        candidate_names=candidate_names,
        inner_indices=inner_indices,
    )
    selected = _select_candidate(
        inner_view,
        selection_metric=selection_metric,
    )
    baseline = details[baseline_name]
    candidate = details[selected]
    returns, drawdowns, utilities = _paired_arrays(
        candidate, baseline, outer_indices
    )

    paired_table: list[dict[str, Any]] = []
    for idx, return_delta, drawdown_delta, utility_delta in zip(
        outer_indices, returns, drawdowns, utilities
    ):
        row = candidate[idx]
        paired_table.append({
            "window_index": idx,
            "decision_date": row["decision_date"],
            "embargo_date": row["embargo_date"],
            "entry_date": row["entry_date"],
            "valuation_dates": list(row["valuation_dates"]),
            "exit_date": row["exit_date"],
            "regime": row["regime"],
            "baseline_return": float(baseline[idx]["official"]["total_return"]),
            "candidate_return": float(row["official"]["total_return"]),
            "return_delta": round(float(return_delta), 8),
            "baseline_max_drawdown": float(
                baseline[idx]["official"]["max_drawdown"]
            ),
            "candidate_max_drawdown": float(row["official"]["max_drawdown"]),
            "drawdown_delta": round(float(drawdown_delta), 8),
            "utility_delta": round(float(utility_delta), 8),
        })

    bootstrap = moving_block_bootstrap(
        returns,
        utilities,
        iterations=frozen_plan.bootstrap_iterations,
        block_windows=frozen_plan.bootstrap_block_windows,
        seed=frozen_plan.seed,
    )
    candidate_returns = np.array([
        float(candidate[idx]["official"]["total_return"]) for idx in outer_indices
    ])
    baseline_returns = np.array([
        float(baseline[idx]["official"]["total_return"]) for idx in outer_indices
    ])
    candidate_drawdowns = np.array([
        float(candidate[idx]["official"]["max_drawdown"]) for idx in outer_indices
    ])
    baseline_drawdowns = np.array([
        float(baseline[idx]["official"]["max_drawdown"]) for idx in outer_indices
    ])
    recent_weights = np.array([
        frozen_plan.recent_decay ** age
        for age in reversed(range(len(outer_indices)))
    ])
    recent_weights /= recent_weights.sum()
    evidence = {
        "n_outer_windows": len(outer_indices),
        "median_return_delta": round(float(np.median(returns)), 8),
        "mean_return_delta": round(float(np.mean(returns)), 8),
        "p10_candidate_return": round(float(np.quantile(candidate_returns, 0.10)), 8),
        "p10_baseline_return": round(float(np.quantile(baseline_returns, 0.10)), 8),
        "worst_candidate_return": round(float(np.min(candidate_returns)), 8),
        "worst_baseline_return": round(float(np.min(baseline_returns)), 8),
        "median_drawdown_delta": round(float(np.median(drawdowns)), 8),
        "worst_candidate_drawdown": round(float(np.max(candidate_drawdowns)), 8),
        "worst_baseline_drawdown": round(float(np.max(baseline_drawdowns)), 8),
        "worst_drawdown_delta": round(
            float(np.max(candidate_drawdowns) - np.max(baseline_drawdowns)), 8
        ),
        "max_paired_drawdown_delta": round(float(np.max(drawdowns)), 8),
        "utility_win_rate": round(float(np.mean(utilities > 0)), 6),
        "recent_weighted_return_delta": round(
            float(np.sum(returns * recent_weights)), 8
        ),
        "recent_weighted_utility_delta": round(
            float(np.sum(utilities * recent_weights)), 8
        ),
        "regime_stability": _regime_stability(paired_table),
    }
    statistical_checks = {
        "median_return_delta": (
            evidence["median_return_delta"]
            >= frozen_plan.median_return_delta_min
        ),
        "bootstrap_positive_probability": (
            bootstrap["probability_median_delta_gt_zero"]
            >= frozen_plan.bootstrap_positive_probability_min
        ),
        "utility_win_rate": (
            evidence["utility_win_rate"] >= frozen_plan.utility_win_rate_min
        ),
        "p10_return_noninferiority": (
            evidence["p10_candidate_return"]
            >= evidence["p10_baseline_return"]
            - frozen_plan.p10_return_worsening_max
        ),
        "median_drawdown_noninferiority": (
            evidence["median_drawdown_delta"]
            <= frozen_plan.median_drawdown_worsening_max
        ),
        "worst_drawdown_noninferiority": (
            evidence["worst_drawdown_delta"]
            <= frozen_plan.worst_drawdown_worsening_max
        ),
    }
    operational_checks = {
        "clean_git": not bool(verified_git["dirty"]),
        "verified_wp1a_snapshot": verified_wp1a,
        "outer_evidence_present": len(outer_indices) >= frozen_plan.min_outer_windows,
        "protocol_current": frozen_plan.protocol == "competition_nested_v1",
        "preregistered_plan": frozen_plan == NestedEvaluationPlan(),
    }
    checks = {**statistical_checks, **operational_checks}
    statistical_qualified = all(statistical_checks.values())
    promotion_eligible = statistical_qualified and all(operational_checks.values())
    if promotion_eligible:
        status = "PROMOTION_ELIGIBLE"
    elif statistical_qualified and not all(operational_checks.values()):
        status = "RESEARCH_ONLY"
    else:
        status = "DOES_NOT_QUALIFY"

    result: dict[str, Any] = {
        "schema": "nested_promotion_evidence/v1",
        "plan": asdict(frozen_plan),
        "baseline": baseline_name,
        "candidate_names": list(candidate_names),
        "split": {
            "inner_indices": inner_indices,
            "outer_indices": outer_indices,
        },
        "inner_selection": {
            "scores": [asdict(item) for item in inner_view.candidate_scores],
            "selection_metric": selection_metric,
            "selection_uses_outer_results": False,
        },
        "selected_candidate": selected,
        "paired_table": paired_table,
        "bootstrap": bootstrap,
        "evidence": evidence,
        "checks": checks,
        "statistical_qualified": statistical_qualified,
        "promotion_eligible": promotion_eligible,
        "status": status,
        "git": verified_git,
        "snapshot_binding": dict(snapshot_binding),
        "config_binding": dict(config_binding),
        "details_hash": _canonical_hash({
            name: list(rows) for name, rows in sorted(details.items())
        }),
    }
    result["evaluation_hash"] = _canonical_hash(result)
    return result
