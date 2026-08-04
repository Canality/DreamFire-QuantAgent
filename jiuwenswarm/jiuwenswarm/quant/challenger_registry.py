"""Canonical WP1-C round-one registry bound to accepted WP1-B evidence."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping

from jiuwenswarm.quant.challenger_mechanisms import (
    CHALLENGER_IDS,
    SECTOR_CANDIDATE,
    TAIL_CANDIDATE,
    TREND_CANDIDATE,
)
from jiuwenswarm.quant.strategy_configs import (
    PRODUCTION_STRATEGY,
    get_strategy_spec,
)


ROUND_ID = "wp1c_round_1_20260804"
BASE_STRATEGY_ID = "phase_b_t2_score_alloc"
ACCEPTED_WP1B_TASK_ID = "WP1B-EVALUATION-0804"
ACCEPTED_WP1B_REVIEW_SHA256 = (
    "35c72c69f1defe417cb218f84f0af55efb520b10af80883fe255e724e0b3284d"
)
ACCEPTED_WP1B_EVALUATION_HASH = (
    "b1cd9a849bcbf53f1f32bad8363c623694782791f797e201f7aeda2296783099"
)
FROZEN_REGISTRY_HASH = (
    "e8add67ec0f556a5bc46bc7c8fdfcfd78cbe2836020b44e8b13ab41e99617a8d"
)


FROZEN_CANDIDATES: dict[str, dict[str, Any]] = {
    TREND_CANDIDATE: {
        "candidate_id": TREND_CANDIDATE,
        "formula_version": "trend_consistency/v1",
        "only_changed_mechanism": "5_10_20_trend_consistency",
        "input_columns": ["decision_time_closes"],
        "minimum_history": {"closes": 21},
        "cutoff_policy": "decision_close_only",
        "formula": (
            "delta=0.15*I(equal_nonzero_sign(r5,r10,r20))*"
            "mean(percent_rank_pm1(r5),percent_rank_pm1(r10),"
            "percent_rank_pm1(r20))"
        ),
        "parameters": {
            "lookbacks": [5, 10, 20],
            "overlay_coefficient": 0.15,
            "agreement": "three_nonzero_signs_exactly_equal",
        },
        "delta_bounds": [-0.15, 0.15],
        "regime_route": "all",
        "inner_prescreen": {
            "median_rank_ic_gt": 0.0,
            "positive_ic_window_rate_gte": 0.60,
            "paired_median_return_delta_gt": 0.0,
        },
        "diagnostic_fields": [
            "r5", "r10", "r20", "q5", "q10", "q20",
            "agreement_gate", "trend_consistency", "score_delta",
        ],
    },
    SECTOR_CANDIDATE: {
        "candidate_id": SECTOR_CANDIDATE,
        "formula_version": "sector_leadership/v1",
        "only_changed_mechanism": "sector_relative_strength_and_breadth",
        "input_columns": ["decision_time_closes", "decision_time_volumes"],
        "minimum_history": {"closes": 21, "volumes": 21},
        "cutoff_policy": "decision_close_only",
        "formula": (
            "delta=0.10*clip(0.5*sector_rs_percent_rank_pm1+"
            "0.5*(2*pct_positive_20d-1),-1,1)"
        ),
        "parameters": {
            "sector_count": 6,
            "relative_strength_weight": 0.5,
            "breadth_weight": 0.5,
            "overlay_coefficient": 0.10,
        },
        "delta_bounds": [-0.10, 0.10],
        "regime_route": "all",
        "inner_prescreen": {
            "top2_forward_best_hit_rate_gte": 0.40,
            "sector_sign_agreement_rate_gte": 0.60,
            "paired_median_return_delta_gt": 0.0,
        },
        "diagnostic_fields": [
            "relative_strength_20d", "pct_positive_20d",
            "sector_rank_score", "sector_leadership_score", "top2_leaders",
            "ticker_leadership_score", "score_delta",
        ],
    },
    TAIL_CANDIDATE: {
        "candidate_id": TAIL_CANDIDATE,
        "formula_version": "asymmetric_tail/v1",
        "only_changed_mechanism": "extreme_only_tail_penalty",
        "input_columns": ["decision_time_closes", "decision_time_opens"],
        "minimum_history": {"closes": 60, "opens": 21},
        "cutoff_policy": "decision_close_only",
        "formula": (
            "delta=-0.20*max(clip((downside_vol20-0.40)/0.20,0,1),"
            "clip((-min_gap20-0.05)/0.05,0,1),"
            "clip((drawdown60-0.20)/0.10,0,1))"
        ),
        "parameters": {
            "downside_vol_trigger": 0.40,
            "downside_vol_full": 0.60,
            "negative_gap_trigger": -0.05,
            "negative_gap_full": -0.10,
            "drawdown_trigger": 0.20,
            "drawdown_full": 0.30,
            "overlay_coefficient": -0.20,
        },
        "delta_bounds": [-0.20, 0.0],
        "regime_route": "all",
        "inner_prescreen": {
            "median_drawdown_delta_lte": -0.001,
            "p10_return_delta_gte": -0.002,
            "median_return_delta_gte": -0.002,
        },
        "diagnostic_fields": [
            "downside_vol_20", "min_gap_20", "drawdown_60", "vol_severity",
            "gap_severity", "drawdown_severity", "tail_severity", "score_delta",
        ],
    },
}


def canonical_hash(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _task_status(path: Path) -> str:
    match = re.search(r"(?m)^status:\s*([A-Z_]+)\s*$", path.read_text(encoding="utf-8"))
    if not match:
        raise ValueError("WP1-B task contract lacks a status")
    return match.group(1)


def _validate_dependency(task_path: Path, review_path: Path) -> None:
    if not task_path.is_file() or _task_status(task_path) not in {"VERIFIED", "CLOSED"}:
        raise ValueError("WP1-B task is not VERIFIED or CLOSED")
    if not review_path.is_file():
        raise ValueError("WP1-B review artifact is missing")
    if file_sha256(review_path) != ACCEPTED_WP1B_REVIEW_SHA256:
        raise ValueError("WP1-B review SHA-256 differs from the accepted evidence")
    review = json.loads(review_path.read_text(encoding="utf-8"))
    if (
        review.get("task_id") != ACCEPTED_WP1B_TASK_ID
        or review.get("verdict") != "ACCEPT"
        or int(review.get("blocking_findings_count", -1)) != 0
    ):
        raise ValueError("WP1-B review is not an unblocked ACCEPT")
    if ACCEPTED_WP1B_EVALUATION_HASH not in json.dumps(review, sort_keys=True):
        raise ValueError("WP1-B review does not bind the accepted evaluation hash")


def _registry_payload() -> dict[str, Any]:
    base_spec = asdict(get_strategy_spec(BASE_STRATEGY_ID))
    base_spec["factor_weights"] = list(base_spec["factor_weights"])
    if PRODUCTION_STRATEGY != "production_six_factor":
        raise ValueError("production strategy pointer changed during WP1-C")
    if (
        base_spec["factor_weights"] != [0.71, 0.0, 0.0, 0.0, 0.0, 0.29]
        or base_spec["score_tilt"] != 0.20
        or base_spec["max_single_stock"] != 0.10
        or base_spec["max_single_sector"] != 0.25
        or base_spec["max_total_weight"] != 0.95
    ):
        raise ValueError("frozen T2 base or portfolio constraints changed")
    return {
        "schema_version": "wp1c_challenger_registry/v1",
        "round_id": ROUND_ID,
        "created_at": "2026-08-04T18:22:20+08:00",
        "base_strategy_id": BASE_STRATEGY_ID,
        "base_strategy": base_spec,
        "base_strategy_hash": canonical_hash(base_spec),
        "wp1b_task_id": ACCEPTED_WP1B_TASK_ID,
        "wp1b_status": "CLOSED",
        "wp1b_review_sha256": ACCEPTED_WP1B_REVIEW_SHA256,
        "wp1b_evidence_hash": ACCEPTED_WP1B_EVALUATION_HASH,
        "competition_policy": {
            "embargo_trading_days": 1,
            "entry": "open",
            "holding_days": 20,
            "exit": "close",
            "shares": "fixed",
        },
        "constraints": {
            "max_single_stock": 0.10,
            "max_single_sector": 0.25,
            "min_cash": 0.05,
        },
        "seed": 20260804,
        "candidate_ids": list(CHALLENGER_IDS),
        "candidates": [FROZEN_CANDIDATES[name] for name in CHALLENGER_IDS],
        "no_scan_no_retune": true_rules(),
        "production_pointer": PRODUCTION_STRATEGY,
        "production_pointer_unchanged": True,
    }


def true_rules() -> list[str]:
    return [
        "exactly_three_candidates",
        "one_mechanism_per_candidate",
        "no_parameter_or_threshold_scan",
        "no_outer_result_formula_access",
        "no_failed_candidate_retune_in_round_one",
        "no_production_pointer_mutation",
    ]


def build_registry(*, task_path: Path, review_path: Path) -> dict[str, Any]:
    """Build the deterministic registry only after exact WP1-B acceptance."""

    _validate_dependency(task_path.resolve(), review_path.resolve())
    payload = _registry_payload()
    registry_hash = canonical_hash(payload)
    if registry_hash != FROZEN_REGISTRY_HASH:
        raise ValueError("challenger registry hash differs from frozen round-one hash")
    return {**payload, "registry_hash": registry_hash}


def validate_registry(
    registry: Mapping[str, Any],
    *,
    task_path: Path,
    review_path: Path,
) -> None:
    """Reject any candidate, formula, evidence or production-pointer drift."""

    expected = build_registry(task_path=task_path, review_path=review_path)
    if dict(registry) != expected:
        raise ValueError("challenger registry differs from frozen canonical payload")
    if list(registry.get("candidate_ids", [])) != list(CHALLENGER_IDS):
        raise ValueError("challenger registry must contain exactly three candidates")
