#!/usr/bin/env python3
"""Sealed holdout validation: 2-factor model on first holdout window only.

Model: momentum_20 (w=0.71) + volume_trend (w=0.29)
Selection: naked top 15
Allocation: single-stock 10% + sector 25%
"""

import json, sys, time
from pathlib import Path

import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

_EVAL_DIR = Path(__file__).resolve().parent
if str(_EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(_EVAL_DIR))
import scoring as _scoring

from jiuwenswarm.quant.factors import (
    FactorCalculator, FactorConfig, PositionConfig, PositionSizer,
)
from jiuwenswarm.quant.backtest_engine import BacktestEngine
from jiuwenswarm.quant.regime_fusion import RegimeFusion
from jiuwenswarm.quant.market_index import MarketIndex
from jiuwenswarm.quant.stock_pool import ALL_STOCKS, SECTOR_MAP

HORIZON = 20
MIN_HISTORY = 80
HOLDOUT_WINDOWS = 2

# -- 2-factor config: Goone's IC-ratio weights -------------------
TWO_FACTOR_CONFIG = FactorConfig(
    w_momentum_20=0.71,   # IC +0.0787
    w_momentum_60=0.0,    # REJECT (IC -0.0748)
    w_max_drawdown=0.0,   # REJECT
    w_reversal_5=0.0,     # REJECT
    w_volume_corr=0.0,    # REJECT (Pos% 54.5%)
    w_volume_trend=0.29,  # IC +0.0315
)

POS_CONFIG = PositionConfig(
    max_single_stock=0.10,
    max_single_sector=0.25,
)


def main():
    print("=" * 60)
    print("  Sealed Holdout Validation — 2-Factor Model")
    print("  momentum_20 (0.71) + volume_trend (0.29)")
    print("=" * 60)

    # --- fetch data ---
    print("\n[Fetch] Real data...")
    t0 = time.time()
    prices_df, volumes_df = _scoring.fetch_real_data(ALL_STOCKS)
    index_prices = MarketIndex.fetch_csi300(
        str(prices_df.index[0].date()), str(prices_df.index[-1].date()))
    print(f"  Done in {time.time() - t0:.0f}s: {len(prices_df.columns)} stocks, "
          f"{len(prices_df)} days")

    # --- fail-closed ---
    fetched_set = set(prices_df.columns)
    if fetched_set != set(ALL_STOCKS):
        missing = set(ALL_STOCKS) - fetched_set
        print(f"FATAL: Missing tickers: {sorted(missing)[:5]}")
        sys.exit(1)
    sectors_present = set(SECTOR_MAP.get(t, "") for t in prices_df.columns)
    if len(sectors_present) < 6:
        print(f"FATAL: Only {len(sectors_present)}/6 sectors")
        sys.exit(1)

    # --- find holdout windows ---
    n_days = len(prices_df)
    starts = list(range(MIN_HISTORY, n_days - HORIZON + 1, HORIZON))
    if len(starts) <= HOLDOUT_WINDOWS:
        print(f"FATAL: Need >{HOLDOUT_WINDOWS} windows, got {len(starts)}")
        sys.exit(1)
    dev_starts = starts[:-HOLDOUT_WINDOWS]
    holdout_starts = starts[-HOLDOUT_WINDOWS:]

    print(f"\n  Dev windows: {len(dev_starts)}, "
          f"Holdout windows: {len(holdout_starts)} (SEALED)")
    print(f"  Opening ONLY holdout window 0 for validation.")
    print(f"  Holdout window 1 remains SEALED.")

    # --- run holdout window 0 only ---
    start_idx = holdout_starts[0]
    backtest_prices = prices_df.iloc[start_idx - 1:start_idx + HORIZON]
    history = prices_df.iloc[:start_idx]

    idx_slice = (index_prices[index_prices.index <= history.index[-1]]
                 if index_prices is not None else None)
    regime = RegimeFusion.detect(history, index_prices=idx_slice)

    calc = FactorCalculator(TWO_FACTOR_CONFIG)
    calc.regime = regime

    history_vol = None
    if volumes_df is not None:
        candidate = volumes_df[volumes_df.index <= history.index[-1]]
        if not candidate.empty:
            history_vol = candidate

    factors = calc.compute_factors(history, history_vol)
    scores = calc.filter_high_volatility(calc.compute_scores(factors))

    # Naked top 15 selection
    selected = []
    for ticker in scores.index:
        if len(selected) >= 15:
            break
        if scores.loc[ticker, "composite"] > 0:
            selected.append(ticker)

    if not selected:
        print("FATAL: No stocks selected")
        sys.exit(1)

    weights = PositionSizer(POS_CONFIG).allocate(
        scores.loc[selected], history)

    bt = BacktestEngine().run(backtest_prices, weights)

    # --- sector breakdown ---
    sector_w = {}
    for t, w in weights.items():
        sec = SECTOR_MAP.get(t, "其他")
        sector_w[sec] = sector_w.get(sec, 0.0) + w

    # --- print results ---
    print(f"\n{'='*60}")
    print(f"  HOLDOUT WINDOW 0 RESULTS")
    print(f"{'='*60}")
    print(f"  Decision date : {prices_df.index[start_idx - 1].date()}")
    print(f"  Test period   : {prices_df.index[start_idx].date()} ~ "
          f"{prices_df.index[start_idx + HORIZON - 1].date()}")
    print(f"  Regime        : {regime}")
    print(f"  Stocks selected: {len(selected)}")
    print(f"  Total weight  : {sum(weights.values()):.4f}")
    print(f"  Cash          : {1 - sum(weights.values()):.4f}")
    print(f"  Max single    : {max(weights.values()):.4f}")
    print(f"  Max sector    : {max(sector_w.values()):.4f}")
    print(f"  ---")
    print(f"  Total Return  : {bt.total_return*100:+.2f}%")
    print(f"  Max Drawdown  : {bt.max_drawdown*100:.2f}%")
    print(f"  Sharpe        : {bt.sharpe_ratio:.2f}")
    print(f"  Ann. Return   : {bt.annualized_return*100:.2f}%")
    print(f"  Ann. Vol      : {bt.metrics.get('annualized_volatility', 0)*100:.2f}%")

    # --- sector detail ---
    print(f"\n  Sector allocation:")
    for sec, w in sorted(sector_w.items(), key=lambda x: -x[1]):
        print(f"    {sec}: {w*100:.1f}%")

    # --- position detail ---
    print(f"\n  Top positions:")
    for t, w in sorted(weights.items(), key=lambda x: -x[1])[:5]:
        print(f"    {t}: {w*100:.2f}% (score={scores.loc[t,'composite']:.3f})")

    # --- summary for Goone ---
    print(f"\n{'='*60}")
    print(f"  SUMMARY FOR GOONE")
    print(f"{'='*60}")
    print(f"  Model      : momentum_20 (0.71) + volume_trend (0.29)")
    print(f"  Selection  : naked top 15")
    print(f"  Allocation : single 10% + sector 25%")
    print(f"  Window     : {prices_df.index[start_idx].date()} ~ "
          f"{prices_df.index[start_idx + HORIZON - 1].date()}")
    print(f"  Return     : {bt.total_return*100:+.2f}%")
    print(f"  Drawdown   : {bt.max_drawdown*100:.2f}%")
    print(f"  Sharpe     : {bt.sharpe_ratio:.2f}")

    # --- save ---
    result = {
        "model": "momentum_20 (0.71) + volume_trend (0.29)",
        "selection": "naked top 15",
        "allocation": "single 10% + sector 25%",
        "window": {
            "decision_date": str(prices_df.index[start_idx - 1].date()),
            "test_start": str(prices_df.index[start_idx].date()),
            "test_end": str(prices_df.index[start_idx + HORIZON - 1].date()),
        },
        "regime": regime,
        "n_selected": len(selected),
        "total_return": float(bt.total_return),
        "max_drawdown": float(bt.max_drawdown),
        "sharpe": float(bt.sharpe_ratio),
        "total_weight": float(sum(weights.values())),
        "max_single_w": float(max(weights.values())),
        "max_sector_w": float(max(sector_w.values())),
        "sector_weights": {s: float(w) for s, w in sector_w.items()},
        "top_positions": [
            {"ticker": t, "weight": float(w), "score": float(scores.loc[t, "composite"])}
            for t, w in sorted(weights.items(), key=lambda x: -x[1])[:5]
        ],
    }
    path = "evaluation/holdout_validation.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"\nSaved to {path}")


if __name__ == "__main__":
    main()
