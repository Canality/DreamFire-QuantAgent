#!/usr/bin/env python3
"""Leakage-resistant walk-forward IC evaluation for the current six factors.

Default behavior evaluates non-overlapping development windows and seals the
last two windows.  Holdout returns are deliberately not calculated or stored.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from jiuwenswarm.quant.factors import FactorCalculator, FactorConfig
from jiuwenswarm.quant.stock_pool import ALL_STOCKS, SECTOR_MAP, STOCK_POOL

EVALUATION_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = EVALUATION_DIR.parent
if str(EVALUATION_DIR) not in sys.path:
    sys.path.insert(0, str(EVALUATION_DIR))

import scoring as _scoring

fetch_real_data = _scoring.fetch_real_data

DEFAULT_LOOKBACK_DAYS = 500
DEFAULT_MIN_HISTORY = 80
DEFAULT_HORIZON = 20
DEFAULT_HOLDOUT_WINDOWS = 2

FACTOR_DIRECTIONS = {
    "momentum_20": 1,
    "momentum_60": 1,
    "reversal_5": -1,
    "max_drawdown": -1,
    "volume_corr": 1,
    "volume_trend": 1,
}

PREREGISTRATION = {
    "hypothesis": (
        "At least one current factor has stable direction-adjusted predictive "
        "rank correlation on non-overlapping development windows."
    ),
    "candidate_thresholds": {
        "mean_aligned_ic_min": 0.03,
        "positive_aligned_windows_min": 0.60,
        "minimum_cross_section": 30,
    },
    "window_policy": "non-overlapping 20-day forward returns",
    "missing_policy": "drop missing endpoints; never replace missing return with zero",
    "holdout_policy": "last windows sealed; dates only, no factor IC or return",
}


def git_state() -> dict:
    def run(*args: str) -> str:
        result = subprocess.run(
            ["git", *args], cwd=PROJECT_ROOT, check=False,
            capture_output=True, text=True,
        )
        return result.stdout.strip()

    return {
        "commit": run("rev-parse", "HEAD") or "unknown",
        "dirty": bool(run("status", "--porcelain")),
    }


def build_schedule(
    n_days: int,
    min_history: int,
    horizon: int,
    holdout_windows: int,
) -> tuple[list[int], list[int]]:
    starts = list(range(min_history, n_days - horizon + 1, horizon))
    if len(starts) <= holdout_windows:
        raise ValueError(
            f"Need more than {holdout_windows} complete windows; got {len(starts)}"
        )
    return starts[:-holdout_windows], starts[-holdout_windows:]


def describe_window(index: pd.Index, start_idx: int, horizon: int) -> dict:
    return {
        "decision_date": str(index[start_idx - 1].date()),
        "forward_start": str(index[start_idx].date()),
        "forward_end": str(index[start_idx + horizon - 1].date()),
        "horizon_returns": horizon,
    }


def forward_returns(
    prices: pd.DataFrame,
    start_idx: int,
    horizon: int,
) -> pd.Series:
    """Return from decision close to the final close after `horizon` returns."""
    decision_close = prices.iloc[start_idx - 1]
    final_close = prices.iloc[start_idx + horizon - 1]
    result = final_close / decision_close - 1.0
    valid = decision_close.notna() & final_close.notna()
    return result.where(valid)


def spearman_ic(factor: pd.Series, future: pd.Series) -> tuple[float, int]:
    common = factor.dropna().index.intersection(future.dropna().index)
    if len(common) < PREREGISTRATION["candidate_thresholds"]["minimum_cross_section"]:
        return float("nan"), len(common)
    value = factor.loc[common].astype(float).rank().corr(
        future.loc[common].astype(float).rank(),
    )
    return float(value), len(common)


def evaluate(
    prices_df: pd.DataFrame,
    volumes_df: pd.DataFrame | None,
    development_starts: list[int],
    horizon: int,
) -> tuple[list[dict], dict]:
    details = []
    by_factor = {factor: [] for factor in FACTOR_DIRECTIONS}

    for window_idx, start_idx in enumerate(development_starts):
        history = prices_df.iloc[:start_idx]
        history_volume = None
        if volumes_df is not None:
            candidate = volumes_df[volumes_df.index <= history.index[-1]]
            if not candidate.empty:
                history_volume = candidate

        factors = FactorCalculator(FactorConfig()).compute_factors(
            history, history_volume,
        )
        future = forward_returns(prices_df, start_idx, horizon)
        factor_results = {}
        for factor, direction in FACTOR_DIRECTIONS.items():
            raw_ic, n_cross_section = spearman_ic(factors[factor], future)
            aligned_ic = raw_ic * direction if np.isfinite(raw_ic) else raw_ic
            factor_results[factor] = {
                "raw_ic": None if not np.isfinite(raw_ic) else round(raw_ic, 6),
                "aligned_ic": (
                    None if not np.isfinite(aligned_ic) else round(aligned_ic, 6)
                ),
                "n_cross_section": n_cross_section,
            }
            if np.isfinite(aligned_ic):
                by_factor[factor].append(float(aligned_ic))

        details.append({
            "idx": window_idx,
            **describe_window(prices_df.index, start_idx, horizon),
            "history_days": len(history),
            "factors": factor_results,
        })

    summaries = {}
    thresholds = PREREGISTRATION["candidate_thresholds"]
    for factor, values in by_factor.items():
        if not values:
            summaries[factor] = {"verdict": "INSUFFICIENT_DATA", "n_windows": 0}
            continue
        mean_ic = float(np.mean(values))
        std_ic = float(np.std(values, ddof=1)) if len(values) > 1 else 0.0
        positive_rate = sum(value > 0 for value in values) / len(values)
        passes = (
            mean_ic >= thresholds["mean_aligned_ic_min"]
            and positive_rate >= thresholds["positive_aligned_windows_min"]
        )
        summaries[factor] = {
            "direction": FACTOR_DIRECTIONS[factor],
            "mean_aligned_ic": round(mean_ic, 6),
            "std_aligned_ic": round(std_ic, 6),
            "icir": None if std_ic == 0 else round(mean_ic / std_ic, 4),
            "positive_rate": round(positive_rate, 4),
            "min_aligned_ic": round(min(values), 6),
            "max_aligned_ic": round(max(values), 6),
            "n_windows": len(values),
            "verdict": "CANDIDATE" if passes else "REJECT",
        }
    return details, summaries


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lookback-days", type=int, default=DEFAULT_LOOKBACK_DAYS)
    parser.add_argument("--min-history", type=int, default=DEFAULT_MIN_HISTORY)
    parser.add_argument("--horizon", type=int, default=DEFAULT_HORIZON)
    parser.add_argument(
        "--holdout-windows", type=int, default=DEFAULT_HOLDOUT_WINDOWS,
    )
    args = parser.parse_args()

    run_id = datetime.now().strftime("ic_walk_forward_%Y%m%d_%H%M%S")
    print("=" * 72)
    print("Walk-forward IC preregistration")
    print(json.dumps(PREREGISTRATION, ensure_ascii=False, indent=2))
    print("=" * 72)
    started = time.time()

    prices_df, volumes_df = fetch_real_data(
        ALL_STOCKS, lookback_days=args.lookback_days,
    )
    actual = set(prices_df.columns)
    required = set(ALL_STOCKS)
    if actual != required:
        raise SystemExit(
            f"FATAL: ticker mismatch; missing={sorted(required - actual)}; "
            f"extra={sorted(actual - required)}"
        )
    sectors = {SECTOR_MAP.get(ticker) for ticker in prices_df.columns}
    if sectors != set(STOCK_POOL):
        raise SystemExit(f"FATAL: sector mismatch: {sorted(sectors)}")

    development, holdout = build_schedule(
        len(prices_df), args.min_history, args.horizon, args.holdout_windows,
    )
    details, summaries = evaluate(
        prices_df, volumes_df, development, args.horizon,
    )

    report = {
        "run_id": run_id,
        "created_at": datetime.now().astimezone().isoformat(),
        "git": git_state(),
        "preregistration": PREREGISTRATION,
        "data": {
            "source_chain": "akshare -> baostock -> yfinance, missing-only",
            "lookback_days_requested": args.lookback_days,
            "n_stocks": len(prices_df.columns),
            "n_sectors": len(sectors),
            "n_trading_days": len(prices_df),
            "date_start": str(prices_df.index[0].date()),
            "date_end": str(prices_df.index[-1].date()),
        },
        "protocol": {
            "min_history": args.min_history,
            "horizon": args.horizon,
            "development_windows": [
                describe_window(prices_df.index, start, args.horizon)
                for start in development
            ],
            "sealed_holdout_windows": [
                describe_window(prices_df.index, start, args.horizon)
                for start in holdout
            ],
        },
        "summaries": summaries,
        "details": details,
        "elapsed_seconds": round(time.time() - started, 2),
    }

    immutable_path = EVALUATION_DIR / f"{run_id}.json"
    latest_path = EVALUATION_DIR / "ic_walk_forward_latest.json"
    for path in (immutable_path, latest_path):
        path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8",
        )
    print(json.dumps(summaries, ensure_ascii=False, indent=2))
    print(f"Saved immutable artifact: {immutable_path}")
    print(f"Updated latest artifact:   {latest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
