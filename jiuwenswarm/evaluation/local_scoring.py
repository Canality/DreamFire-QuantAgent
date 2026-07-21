#!/usr/bin/env python3
"""Transparent local proxy for the competition's 80/20 scoring dimensions.

The organiser has not published the peer distribution used for portfolio
ranking, nor the token/runtime baselines.  This module therefore:

* estimates the 80 portfolio points from empirical percentiles against one
  frozen local reference strategy;
* scores resources only when both actual measurements and baselines exist;
* reports an interval instead of inventing a precise 100-point total when a
  resource component is pending.

It consumes results produced by the causal, first-open/fixed-share evaluator.
It does not fetch data or run a second, divergent backtest implementation.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

import numpy as np


PORTFOLIO_MAX = 80.0
RETURN_MAX = 56.0
DRAWDOWN_MAX = 24.0
TOKEN_MAX = 10.0
RUNTIME_MAX = 5.0
COMPUTE_MAX = 5.0
COMPUTE_TIERS = {
    "excellent": 5.0,
    "good": 3.0,
    "medium": 1.0,
    "poor": 0.0,
}


@dataclass(frozen=True)
class ComponentScore:
    score: float | None
    maximum: float
    status: str
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": None if self.score is None else round(self.score, 4),
            "max": self.maximum,
            "status": self.status,
            "detail": self.detail,
        }


def empirical_percentile(
    value: float,
    reference: Sequence[float],
    *,
    higher_is_better: bool,
) -> float:
    """Return a tie-aware empirical percentile in [0, 1]."""
    values = np.asarray(reference, dtype=float)
    if values.size == 0 or not np.isfinite(values).all() or not np.isfinite(value):
        raise ValueError("percentile inputs must be finite and non-empty")
    if higher_is_better:
        better_than = np.sum(values < value)
    else:
        better_than = np.sum(values > value)
    ties = np.sum(values == value)
    return float((better_than + 0.5 * ties) / values.size)


def _penalty_score(
    actual: float | None,
    baseline: float | None,
    *,
    maximum: float,
    penalty_per_full_10pct: float,
    label: str,
) -> ComponentScore:
    if actual is None or baseline is None:
        return ComponentScore(
            None,
            maximum,
            "pending_baseline_or_measurement",
            f"{label} requires both actual usage and the organiser baseline",
        )
    if actual < 0 or baseline <= 0:
        raise ValueError(f"invalid {label}: actual={actual}, baseline={baseline}")
    if actual <= baseline:
        return ComponentScore(maximum, maximum, "scored", "at or below baseline")

    excess_ratio = actual / baseline - 1.0
    full_steps = math.floor((excess_ratio + 1e-12) / 0.10)
    score = max(0.0, maximum - full_steps * penalty_per_full_10pct)
    return ComponentScore(
        score,
        maximum,
        "scored",
        f"{full_steps} full 10% step(s) above baseline",
    )


def score_tokens(actual: float | None, baseline: float | None) -> ComponentScore:
    return _penalty_score(
        actual,
        baseline,
        maximum=TOKEN_MAX,
        penalty_per_full_10pct=2.0,
        label="token usage",
    )


def score_runtime(actual: float | None, baseline: float | None) -> ComponentScore:
    return _penalty_score(
        actual,
        baseline,
        maximum=RUNTIME_MAX,
        penalty_per_full_10pct=1.0,
        label="runtime",
    )


def score_compute(tier: str | None) -> ComponentScore:
    if tier is None:
        return ComponentScore(
            None,
            COMPUTE_MAX,
            "pending_assessment",
            "organiser compute-economy tier has not been assessed",
        )
    normalized = tier.strip().lower()
    if normalized not in COMPUTE_TIERS:
        raise ValueError(f"compute tier must be one of {sorted(COMPUTE_TIERS)}")
    return ComponentScore(
        COMPUTE_TIERS[normalized],
        COMPUTE_MAX,
        "scored",
        f"declared assessment tier: {normalized}",
    )


def _official_metrics(rows: Sequence[dict[str, Any]]) -> tuple[np.ndarray, np.ndarray]:
    try:
        returns = np.asarray(
            [row["official"]["total_return"] for row in rows], dtype=float
        )
        drawdowns = np.asarray(
            [row["official"]["max_drawdown"] for row in rows], dtype=float
        )
    except (KeyError, TypeError) as exc:
        raise ValueError("results must contain official return/drawdown window details") from exc
    if not len(returns) or len(returns) != len(drawdowns):
        raise ValueError("strategy details must contain aligned non-empty windows")
    if not np.isfinite(returns).all() or not np.isfinite(drawdowns).all():
        raise ValueError("strategy metrics must be finite")
    return returns, drawdowns


def score_portfolio(
    candidate_rows: Sequence[dict[str, Any]],
    reference_rows: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    """Score every candidate window against one frozen reference ECDF."""
    candidate_returns, candidate_drawdowns = _official_metrics(candidate_rows)
    reference_returns, reference_drawdowns = _official_metrics(reference_rows)

    window_scores: list[dict[str, Any]] = []
    for row, ret, drawdown in zip(candidate_rows, candidate_returns, candidate_drawdowns):
        return_percentile = empirical_percentile(
            float(ret), reference_returns, higher_is_better=True
        )
        drawdown_percentile = empirical_percentile(
            float(drawdown), reference_drawdowns, higher_is_better=False
        )
        return_score = RETURN_MAX * return_percentile
        drawdown_score = DRAWDOWN_MAX * drawdown_percentile
        window_scores.append({
            "decision_date": row.get("decision_date"),
            "test_start": row.get("test_start"),
            "test_end": row.get("test_end"),
            "total_return": round(float(ret), 6),
            "max_drawdown": round(float(drawdown), 6),
            "return_percentile": round(return_percentile, 6),
            "drawdown_percentile": round(drawdown_percentile, 6),
            "return_score": round(return_score, 4),
            "drawdown_score": round(drawdown_score, 4),
            "portfolio_score": round(return_score + drawdown_score, 4),
        })

    totals = np.asarray([row["portfolio_score"] for row in window_scores])
    return_scores = np.asarray([row["return_score"] for row in window_scores])
    drawdown_scores = np.asarray([row["drawdown_score"] for row in window_scores])
    return {
        "method": "frozen_reference_empirical_percentile_v1",
        "weights": {
            "return": {"max": RETURN_MAX, "share_of_portfolio": 0.70},
            "max_drawdown": {"max": DRAWDOWN_MAX, "share_of_portfolio": 0.30},
        },
        "n_windows": len(window_scores),
        "expected_score": round(float(np.mean(totals)), 4),
        "median_score": round(float(np.median(totals)), 4),
        "p10_score": round(float(np.quantile(totals, 0.10)), 4),
        "worst_score": round(float(np.min(totals)), 4),
        "expected_return_score": round(float(np.mean(return_scores)), 4),
        "expected_drawdown_score": round(float(np.mean(drawdown_scores)), 4),
        "max": PORTFOLIO_MAX,
        "window_scores": window_scores,
    }


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read JSON result: {path}: {exc}") from exc


def _strategy_rows(payload: dict[str, Any], strategy: str) -> list[dict[str, Any]]:
    details = payload.get("details")
    if not isinstance(details, dict) or strategy not in details:
        raise ValueError(
            f"result has no details for {strategy!r}; rerun its evaluator with detail output"
        )
    rows = details[strategy]
    if not isinstance(rows, list):
        raise ValueError(f"details for {strategy!r} must be a list")
    return rows


def build_report(
    *,
    results_path: Path,
    strategy: str,
    reference_results_path: Path,
    reference_strategy: str,
    actual_tokens: float | None = None,
    baseline_tokens: float | None = None,
    actual_runtime_seconds: float | None = None,
    baseline_runtime_seconds: float | None = None,
    compute_tier: str | None = None,
) -> dict[str, Any]:
    results = _load_json(results_path)
    reference_results = _load_json(reference_results_path)
    portfolio = score_portfolio(
        _strategy_rows(results, strategy),
        _strategy_rows(reference_results, reference_strategy),
    )

    resource_components = {
        "tokens": score_tokens(actual_tokens, baseline_tokens),
        "runtime": score_runtime(actual_runtime_seconds, baseline_runtime_seconds),
        "compute_economy": score_compute(compute_tier),
    }
    confirmed_resource = sum(
        component.score or 0.0 for component in resource_components.values()
    )
    pending_resource = sum(
        component.maximum
        for component in resource_components.values()
        if component.score is None
    )
    resource_complete = pending_resource == 0
    portfolio_primary = float(portfolio["expected_score"])

    return {
        "schema_version": "local_proxy_score_v1",
        "created_at": datetime.now().astimezone().isoformat(),
        "status": "complete_proxy" if resource_complete else "portfolio_proxy_resource_pending",
        "official_unknowns": [
            "peer return/drawdown distribution or direct conversion formula",
            "official token baseline",
            "official runtime baseline",
            "official compute-economy assessment",
        ],
        "declared_assumptions": [
            "portfolio proxy uses the frozen reference strategy's causal 20-day windows as the empirical ranking distribution",
            "declared dimension caps 10/5/5 override contradictory prose saying baseline performance earns 15/10 points",
            "expected portfolio score is the primary local estimate; median, p10 and worst are robustness diagnostics",
        ],
        "inputs": {
            "results": str(results_path.resolve()),
            "strategy": strategy,
            "results_run_id": results.get("run_id"),
            "results_git": results.get("git"),
            "reference_results": str(reference_results_path.resolve()),
            "reference_strategy": reference_strategy,
            "reference_run_id": reference_results.get("run_id"),
            "reference_snapshot_id": reference_results.get("snapshot_id")
                or reference_results.get("snapshot", {}).get("id"),
        },
        "dimension_1_portfolio": portfolio,
        "dimension_2_resources": {
            "score": round(confirmed_resource, 4) if resource_complete else None,
            "confirmed_subtotal": round(confirmed_resource, 4),
            "pending_max": round(pending_resource, 4),
            "max": 20.0,
            "components": {
                name: component.to_dict()
                for name, component in resource_components.items()
            },
        },
        "local_total_score": (
            round(portfolio_primary + confirmed_resource, 4)
            if resource_complete else None
        ),
        "local_total_score_range": [
            round(portfolio_primary + confirmed_resource, 4),
            round(portfolio_primary + confirmed_resource + pending_resource, 4),
        ],
        "max": 100.0,
        "not_official_score": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--strategy", required=True)
    parser.add_argument("--reference-results", type=Path)
    parser.add_argument("--reference-strategy", default="production_six_factor")
    parser.add_argument("--actual-tokens", type=float)
    parser.add_argument("--baseline-tokens", type=float)
    parser.add_argument("--actual-runtime-seconds", type=float)
    parser.add_argument("--baseline-runtime-seconds", type=float)
    parser.add_argument("--compute-tier", choices=sorted(COMPUTE_TIERS))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    reference_path = args.reference_results or args.results
    report = build_report(
        results_path=args.results,
        strategy=args.strategy,
        reference_results_path=reference_path,
        reference_strategy=args.reference_strategy,
        actual_tokens=args.actual_tokens,
        baseline_tokens=args.baseline_tokens,
        actual_runtime_seconds=args.actual_runtime_seconds,
        baseline_runtime_seconds=args.baseline_runtime_seconds,
        compute_tier=args.compute_tier,
    )
    output = args.output or args.results.with_name(
        f"local_score_{args.strategy}_{datetime.now():%Y%m%d_%H%M%S}.json"
    )
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    portfolio = report["dimension_1_portfolio"]
    print(f"Local portfolio proxy: {portfolio['expected_score']:.2f} / 80")
    print(
        "Robustness: "
        f"median={portfolio['median_score']:.2f}, "
        f"p10={portfolio['p10_score']:.2f}, worst={portfolio['worst_score']:.2f}"
    )
    if report["local_total_score"] is None:
        low, high = report["local_total_score_range"]
        print(f"Resources pending; local total range: {low:.2f} ~ {high:.2f} / 100")
    else:
        print(f"Local total proxy: {report['local_total_score']:.2f} / 100")
    print(f"NOT an official score. Saved: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
