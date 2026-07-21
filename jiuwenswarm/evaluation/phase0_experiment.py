#!/usr/bin/env python3
"""Phase 0: controlled selection x sector-cap experiment.

The experiment uses non-overlapping 20-trading-day development windows.
The final windows are sealed and their returns are not calculated here.
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

from jiuwenswarm.quant.backtest_engine import BacktestEngine
from jiuwenswarm.quant.factors import (
    FactorCalculator,
    FactorConfig,
    PositionConfig,
    PositionSizer,
)
from jiuwenswarm.quant.market_index import MarketIndex
from jiuwenswarm.quant.regime_fusion import RegimeFusion
from jiuwenswarm.quant.stock_pool import ALL_STOCKS, SECTOR_MAP, STOCK_POOL

EVALUATION_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = EVALUATION_DIR.parent
if str(EVALUATION_DIR) not in sys.path:
    sys.path.insert(0, str(EVALUATION_DIR))

import scoring as _scoring

fetch_real_data = _scoring.fetch_real_data

HORIZON = 20
MIN_HISTORY = 80
DEFAULT_LOOKBACK_DAYS = 500
DEFAULT_HOLDOUT_WINDOWS = 2
SP = {sector: set(tickers) for sector, tickers in STOCK_POOL.items()}

PREREGISTRATION = {
    "hypothesis": (
        "Selection max-3/sector and allocation sector-cap have separable "
        "effects on out-of-sample return and drawdown."
    ),
    "correctness_thresholds": {
        "stock_coverage": "49/49 exact ticker match",
        "sector_coverage": "6/6 exact sector match",
        "max_single_stock": 0.10,
        "max_total_weight": 0.95,
        "max_single_sector_when_enabled": 0.25,
        "window_overlap": 0,
        "holdout_policy": "sealed; dates recorded, returns not evaluated",
    },
    "performance_threshold": (
        "No performance winner is preregistered; compare all four groups "
        "on the same development windows."
    ),
}


def _git_state() -> dict:
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


def _window_schedule(n_days: int, holdout_windows: int) -> tuple[list[int], list[int]]:
    starts = list(range(MIN_HISTORY, n_days - HORIZON + 1, HORIZON))
    if len(starts) <= holdout_windows:
        raise ValueError(
            f"Need more than {holdout_windows} complete windows; got {len(starts)}"
        )
    return starts[:-holdout_windows], starts[-holdout_windows:]


def _window_descriptor(prices_df, start_idx: int) -> dict:
    return {
        "decision_date": str(prices_df.index[start_idx - 1].date()),
        "test_start": str(prices_df.index[start_idx].date()),
        "test_end": str(prices_df.index[start_idx + HORIZON - 1].date()),
        "n_forward_returns": HORIZON,
    }


def run_experiment(
    name,
    max_per_sector,
    max_single_sector,
    prices_df,
    volumes_df,
    index_prices,
    window_starts,
):
    results = []
    for i, start_idx in enumerate(window_starts):
        # Include the decision-date close so pct_change yields exactly twenty
        # future daily returns, beginning with decision close -> first test close.
        backtest_prices = prices_df.iloc[start_idx - 1:start_idx + HORIZON]
        history = prices_df.iloc[:start_idx]

        idx_slice = (
            index_prices[index_prices.index <= history.index[-1]]
            if index_prices is not None else None
        )
        regime = RegimeFusion.detect(history, index_prices=idx_slice)
        calc = FactorCalculator(FactorConfig())
        calc.regime = regime

        history_vol = None
        if volumes_df is not None:
            candidate = volumes_df[volumes_df.index <= history.index[-1]]
            if not candidate.empty:
                history_vol = candidate

        factors = calc.compute_factors(history, history_vol)
        scores = calc.filter_high_volatility(calc.compute_scores(factors))

        selected = []
        sector_counts = {sector: 0 for sector in SP}
        for ticker in scores.index:
            if len(selected) >= 15:
                break
            if scores.loc[ticker, "composite"] <= 0:
                continue
            sector = SECTOR_MAP.get(ticker, "")
            if sector_counts.get(sector, 0) >= max_per_sector:
                continue
            selected.append(ticker)
            sector_counts[sector] = sector_counts.get(sector, 0) + 1

        if not selected:
            raise AssertionError(f"{name} window {i}: no stocks selected")

        position_config = PositionConfig(
            max_single_stock=0.10,
            max_single_sector=max_single_sector,
        )
        weights = PositionSizer(position_config).allocate(
            scores.loc[selected], history,
        )

        sector_weights = {}
        for ticker, weight in weights.items():
            sector = SECTOR_MAP.get(ticker, "其他")
            sector_weights[sector] = sector_weights.get(sector, 0.0) + weight

        max_stock = max(weights.values()) if weights else 0.0
        max_sector = max(sector_weights.values()) if sector_weights else 0.0
        total_weight = sum(weights.values())
        if max_stock > 0.10 + 1e-9:
            raise AssertionError(f"{name} window {i}: stock cap {max_stock}")
        if total_weight > 0.95 + 1e-9:
            raise AssertionError(f"{name} window {i}: total weight {total_weight}")
        if max_single_sector <= 0.25 and max_sector > 0.25 + 1e-9:
            raise AssertionError(f"{name} window {i}: sector cap {max_sector}")
        if set(weights) != set(selected):
            raise AssertionError(f"{name} window {i}: selection/allocation mismatch")

        backtest = BacktestEngine().run(backtest_prices, weights)
        descriptor = _window_descriptor(prices_df, start_idx)
        results.append({
            "idx": i,
            **descriptor,
            "regime": regime,
            "n_selected": len(selected),
            "selected_tickers": selected,
            "weights": {ticker: float(weight) for ticker, weight in weights.items()},
            "sector_weights": {
                sector: round(float(weight), 6)
                for sector, weight in sector_weights.items()
            },
            "total_weight": round(float(total_weight), 6),
            "cash": round(float(1.0 - total_weight), 6),
            "max_stock_w": round(float(max_stock), 6),
            "max_sector_w": round(float(max_sector), 6),
            "total_return": round(float(backtest.total_return), 6),
            "annualized_return": round(float(backtest.annualized_return), 6),
            "max_drawdown": round(float(backtest.max_drawdown), 6),
            "volatility": round(float(backtest.volatility), 6),
            "sharpe": round(float(backtest.sharpe_ratio), 4),
            "n_trading_days": backtest.metrics["n_trading_days"],
        })
    return results


def summarize(name, results):
    returns = [result["total_return"] for result in results]
    drawdowns = [result["max_drawdown"] for result in results]
    return {
        "name": name,
        "median_ret_pct": round(float(np.median(returns)) * 100, 2),
        "worst_ret_pct": round(float(min(returns)) * 100, 2),
        "median_dd_pct": round(float(np.median(drawdowns)) * 100, 2),
        "worst_dd_pct": round(float(max(drawdowns)) * 100, 2),
        "max_stock_pct": round(max(r["max_stock_w"] for r in results) * 100, 2),
        "max_sector_pct": round(max(r["max_sector_w"] for r in results) * 100, 2),
        "median_invested_pct": round(
            float(np.median([r["total_weight"] for r in results])) * 100, 2,
        ),
        "positive_windows": sum(1 for value in returns if value > 0),
        "n_windows": len(results),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lookback-days", type=int, default=DEFAULT_LOOKBACK_DAYS)
    parser.add_argument(
        "--holdout-windows", type=int, default=DEFAULT_HOLDOUT_WINDOWS,
    )
    args = parser.parse_args()

    run_id = datetime.now().strftime("phase0_%Y%m%d_%H%M%S")
    print("=" * 72)
    print("Phase 0: preregistered constraint isolation")
    print(json.dumps(PREREGISTRATION, ensure_ascii=False, indent=2))
    print("=" * 72)

    started = time.time()
    prices_df, volumes_df = fetch_real_data(
        ALL_STOCKS, lookback_days=args.lookback_days,
    )
    fetched_set = set(prices_df.columns)
    required_set = set(ALL_STOCKS)
    if fetched_set != required_set:
        missing = sorted(required_set - fetched_set)
        extra = sorted(fetched_set - required_set)
        raise SystemExit(f"FATAL: ticker mismatch; missing={missing}; extra={extra}")
    sectors_present = {SECTOR_MAP.get(ticker) for ticker in prices_df.columns}
    expected_sectors = set(STOCK_POOL)
    if sectors_present != expected_sectors:
        raise SystemExit(
            f"FATAL: sector mismatch; got={sorted(sectors_present)}; "
            f"expected={sorted(expected_sectors)}"
        )

    development_starts, holdout_starts = _window_schedule(
        len(prices_df), args.holdout_windows,
    )
    index_prices = MarketIndex.fetch_csi300(
        str(prices_df.index[0].date()), str(prices_df.index[-1].date()),
    )

    configs = [
        ("A: naked, single 10% only", 99, 1.0),
        ("B: max-3/sec, single 10% only", 3, 1.0),
        ("C: naked, single 10% + sector 25%", 99, 0.25),
        ("D: max-3/sec, single 10% + sector 25%", 3, 0.25),
    ]
    details = {}
    summaries = []
    for label, max_per_sector, max_sector in configs:
        print(f"[Run] {label}")
        results = run_experiment(
            label, max_per_sector, max_sector, prices_df, volumes_df,
            index_prices, development_starts,
        )
        details[label] = results
        summaries.append(summarize(label, results))

    report = {
        "run_id": run_id,
        "created_at": datetime.now().astimezone().isoformat(),
        "git": _git_state(),
        "preregistration": PREREGISTRATION,
        "data": {
            "source_chain": "akshare -> baostock -> yfinance, missing-only",
            "lookback_days_requested": args.lookback_days,
            "n_stocks": len(prices_df.columns),
            "tickers": list(prices_df.columns),
            "n_sectors": len(sectors_present),
            "sectors": sorted(sectors_present),
            "n_trading_days": len(prices_df),
            "date_start": str(prices_df.index[0].date()),
            "date_end": str(prices_df.index[-1].date()),
        },
        "protocol": {
            "min_history": MIN_HISTORY,
            "horizon": HORIZON,
            "development_windows": [
                _window_descriptor(prices_df, start)
                for start in development_starts
            ],
            "sealed_holdout_windows": [
                _window_descriptor(prices_df, start)
                for start in holdout_starts
            ],
        },
        "summaries": summaries,
        "details": details,
        "elapsed_seconds": round(time.time() - started, 2),
    }

    immutable_path = EVALUATION_DIR / f"{run_id}.json"
    latest_path = EVALUATION_DIR / "phase0_results.json"
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
