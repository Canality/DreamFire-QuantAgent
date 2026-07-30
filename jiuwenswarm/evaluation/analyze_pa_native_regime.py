#!/usr/bin/env python3
"""Analyze an incomplete PA-native run without imputing it as a valid strategy.

The static-neutral counterfactual asks a narrow attribution question: because
every valid PA decision was neutral, what would a fixed 75% exposure have done?
It is not a PA strategy score and cannot repair invalid PA windows.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

import pa_native_regime_experiment as experiment


EVAL_DIR = Path(__file__).resolve().parent


def _resource_summary(decisions: list[dict[str, Any]]) -> dict[str, Any]:
    prompt = sum(float(row.get("usage", {}).get("prompt_tokens", 0)) for row in decisions)
    hit = sum(
        float(row.get("usage", {}).get("cached_prompt_tokens", 0)) for row in decisions
    )
    completion = sum(
        float(row.get("usage", {}).get("completion_tokens", 0)) for row in decisions
    )
    miss = max(0.0, prompt - hit)
    pricing = {
        "as_of": "2026-07-21",
        "model_assumption": "deepseek-v4-flash via deepseek-chat alias",
        "usd_per_million_cache_hit_input": 0.0028,
        "usd_per_million_cache_miss_input": 0.14,
        "usd_per_million_output": 0.28,
        "source": "https://api-docs.deepseek.com/quick_start/pricing",
    }
    estimated_cost = (
        hit / 1_000_000 * pricing["usd_per_million_cache_hit_input"]
        + miss / 1_000_000 * pricing["usd_per_million_cache_miss_input"]
        + completion / 1_000_000 * pricing["usd_per_million_output"]
    )
    return {
        "api_calls_are_embedded_in_two_stage_runs": True,
        "prompt_tokens": int(prompt),
        "cache_hit_input_tokens": int(hit),
        "cache_miss_input_tokens": int(miss),
        "completion_tokens": int(completion),
        "total_tokens": int(prompt + completion),
        "summed_window_latency_seconds": round(
            sum(float(row.get("elapsed_seconds", 0)) for row in decisions), 3
        ),
        "pricing": pricing,
        "estimated_cost_usd": round(estimated_cost, 6),
    }


def _bootstrap_median_ci(values: np.ndarray, seed: int = 20260721) -> list[float]:
    rng = np.random.default_rng(seed)
    samples = np.array(
        [np.median(rng.choice(values, size=len(values), replace=True)) for _ in range(10_000)]
    )
    return [round(float(x), 6) for x in np.quantile(samples, [0.025, 0.975])]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    run = json.loads(args.run.read_text(encoding="utf-8"))
    decisions = list(run.get("decisions") or [])
    if len(decisions) != 21:
        raise ValueError(f"Expected 21 attempted windows, got {len(decisions)}")
    valid = [row for row in decisions if row.get("success")]
    invalid = [row for row in decisions if not row.get("success")]

    snapshot_dir = experiment.SNAPSHOT_DEFAULT.resolve()
    snapshot, _index_ohlcv, starts = experiment._load_market(snapshot_dir)
    phase_b = json.loads(experiment.PHASE_B_LATEST.read_text(encoding="utf-8"))
    t2_rows = phase_b["details"]["phase_b_t2_score_alloc"]
    opens, closes, _volumes, _index_close = experiment._UE._prepare_frames(snapshot)

    # This is deliberately independent of PA validity/confidence: all 21 rows
    # are set to neutral so it measures fixed 75% exposure, not an imputed PA run.
    neutral = [
        {
            "idx": row["idx"],
            "decision_date": row["decision_date"],
            "normalized_direction": "neutral",
            "confidence": 0.0,
        }
        for row in decisions
    ]
    fixed_75 = experiment._scale_t2_rows(
        neutral, t2_rows, opens, closes, starts, "pa_m1"
    )
    comparison = experiment._paired(fixed_75, t2_rows)
    deltas = np.array(
        [
            (candidate["official"]["total_return"] - baseline["official"]["total_return"])
            * 100
            for candidate, baseline in zip(fixed_75, t2_rows)
        ]
    )
    comparison["median_return_delta_pp_bootstrap_95pct_ci"] = _bootstrap_median_ci(deltas)

    report = {
        "created_at": datetime.now().astimezone().isoformat(),
        "source_run": str(args.run.resolve()),
        "source_run_id": run.get("run_id"),
        "source_evaluation_status": run.get("evaluation_status"),
        "pa_validity": {
            "attempted_windows": len(decisions),
            "valid_windows": len(valid),
            "invalid_windows": len(invalid),
            "valid_rate": round(len(valid) / len(decisions), 6),
            "valid_direction_counts": {
                direction: sum(
                    1 for row in valid if row.get("normalized_direction") == direction
                )
                for direction in ("bullish", "neutral", "bearish")
            },
            "invalid_windows_detail": [
                {
                    "idx": row["idx"],
                    "stage": (row.get("exception") or {}).get("stage"),
                    "category": (row.get("exception") or {}).get("category"),
                    "message": (row.get("exception") or {}).get("message"),
                }
                for row in invalid
            ],
        },
        "resources": _resource_summary(decisions),
        "static_neutral_counterfactual": {
            "label": "fixed_75pct_T2_not_a_PA_strategy_score",
            "reason": (
                "All valid PA outputs were neutral. This counterfactual isolates the "
                "effect of constant deleveraging and does not impute failed PA windows."
            ),
            "t2_summary": experiment._UE.summarize(t2_rows),
            "fixed_75pct_summary": experiment._UE.summarize(fixed_75),
            "comparison_to_t2": comparison,
            "details": fixed_75,
        },
        "conclusion_guard": (
            "PA-native has no valid 21-window portfolio score. Any fixed-75% advantage "
            "belongs to static exposure reduction, not to PA timing."
        ),
    }
    output = args.output or EVAL_DIR / "pa_native_regime_analysis_latest.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "output": str(output),
        "pa_validity": report["pa_validity"],
        "resources": report["resources"],
        "static_neutral_comparison": comparison,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
