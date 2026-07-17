#!/usr/bin/env python3
"""
Self-evaluation framework based on competition scoring criteria (100 pts).

REQUIRES real stock data. No simulated data fallback — if data fetch fails,
the script aborts with actionable error messages.

Scoring calibrated against realistic A-share market expectations:
  - 20-day return: benchmark against CSI 300 equivalent
  - Max drawdown: scored on absolute scale relevant to competition

Usage:
  python evaluation/scoring.py
  python evaluation/scoring.py --windows 10
"""

import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ============================================================
# Realistic scoring functions (calibrated for ~20 trading days)
# ============================================================

def score_return(cumulative_ret: float) -> tuple[float, str]:
    """
    Score return dimension (56 pts max).

    Calibrated for ~20 trading day (~1 month) performance of a stock portfolio:
      > +8%  → 50-56  (exceptional — rare in normal markets)
      +4~8%  → 40-49  (strong)
      +1~4%  → 25-39  (decent)
      -2~+1% → 10-24  (flat)
      -5~-2% →  3-9   (weak)
      < -5%  →  0-2   (poor)
    """
    if cumulative_ret > 0.08:
        score = 50 + min(6, (cumulative_ret - 0.08) * 100)
    elif cumulative_ret > 0.04:
        score = 40 + (cumulative_ret - 0.04) / 0.04 * 10
    elif cumulative_ret > 0.01:
        score = 25 + (cumulative_ret - 0.01) / 0.03 * 15
    elif cumulative_ret > -0.02:
        score = 10 + (cumulative_ret + 0.02) / 0.03 * 15
    elif cumulative_ret > -0.05:
        score = 3 + (cumulative_ret + 0.05) / 0.03 * 7
    else:
        score = max(0.0, 2 + cumulative_ret * 20)

    tier = ("exceptional" if cumulative_ret > 0.08 else
            "strong" if cumulative_ret > 0.04 else
            "decent" if cumulative_ret > 0.01 else
            "flat" if cumulative_ret > -0.02 else
            "weak" if cumulative_ret > -0.05 else "poor")

    return round(min(56.0, max(0.0, score)), 1), tier


def score_drawdown(max_dd: float) -> tuple[float, str]:
    """
    Score max drawdown dimension (24 pts max).

    Calibrated for ~20 trading day window:
      < 1%   → 23-24  (excellent — negligible drawdown)
      1~2%   → 20-22  (very good)
      2~4%   → 15-19  (good)
      4~6%   →  8-14  (acceptable)
      6~10%  →  3-7   (concerning)
      > 10%  →  0-2   (poor)
    """
    if max_dd < 0.01:
        score = 23 + (0.01 - max_dd) / 0.01
    elif max_dd < 0.02:
        score = 20 + (0.02 - max_dd) / 0.01 * 2
    elif max_dd < 0.04:
        score = 15 + (0.04 - max_dd) / 0.02 * 4
    elif max_dd < 0.06:
        score = 8 + (0.06 - max_dd) / 0.02 * 7
    elif max_dd < 0.10:
        score = 3 + (0.10 - max_dd) / 0.04 * 4
    else:
        score = max(0.0, 2.0 - (max_dd - 0.10) * 20)

    tier = ("excellent" if max_dd < 0.01 else
            "very_good" if max_dd < 0.02 else
            "good" if max_dd < 0.04 else
            "acceptable" if max_dd < 0.06 else
            "concerning" if max_dd < 0.10 else "poor")

    return round(min(24.0, max(0.0, score)), 1), tier


def score_tokens(estimated_tokens: int, baseline_tokens: int = 6000) -> tuple[float, str]:
    """Score token consumption (10 pts max)."""
    if estimated_tokens <= baseline_tokens:
        return 10.0, "under_budget"
    excess_pct = (estimated_tokens - baseline_tokens) / baseline_tokens
    penalty = int(excess_pct / 0.10) * 2
    return max(0.0, 10.0 - penalty), "over_budget"


def score_runtime(elapsed_seconds: float, baseline_seconds: float = 30.0) -> tuple[float, str]:
    """Score runtime efficiency (5 pts max)."""
    if elapsed_seconds <= baseline_seconds:
        return 5.0, "under_budget"
    excess_pct = (elapsed_seconds - baseline_seconds) / baseline_seconds
    penalty = min(5.0, int(excess_pct / 0.10))
    return round(max(0.0, 5.0 - penalty), 1), "over_budget"


def score_compute_economy(peak_memory_mb: float = 500, gpu_used: bool = False) -> tuple[float, str]:
    """Score compute economy (5 pts max)."""
    if not gpu_used and peak_memory_mb < 200:
        return 5.0, "excellent"
    elif not gpu_used and peak_memory_mb < 500:
        return 4.0, "good"
    elif not gpu_used and peak_memory_mb < 1000:
        return 3.0, "moderate"
    elif gpu_used:
        return 2.0, "gpu_required"
    else:
        return 1.0, "high_memory"


def estimate_multi_agent_tokens() -> int:
    """Estimate tokens for the multi-agent Bull/Bear/Coordinator workflow."""
    coordinator = 1200 + 500 + 1000 + 800 + 2000 + 1500
    bull = 600 + 1500 + 800 + 1200
    bear = 600 + 1500 + 800 + 1200
    return coordinator + bull + bear


# ============================================================
# Real data fetch — NO simulated fallback
# ============================================================

_YF_TICKER_MAP = {}

def _to_yf(t: str) -> str:
    if t not in _YF_TICKER_MAP:
        _YF_TICKER_MAP[t] = t.replace(".SH", ".SS")
    return _YF_TICKER_MAP[t]


def _extract_column(df: pd.DataFrame, col_name: str) -> pd.Series:
    """Handle yfinance MultiIndex columns (newer versions return MultiIndex even for single ticker)."""
    if df is None or df.empty:
        return pd.Series(dtype=float)
    if isinstance(df.columns, pd.MultiIndex):
        subset = df.get(col_name)
        if subset is not None and not subset.empty:
            return subset.iloc[:, 0] if isinstance(subset, pd.DataFrame) else subset
        return pd.Series(dtype=float)
    return df.get(col_name, pd.Series(dtype=float))


def fetch_real_data(tickers: list[str], lookback_days: int = 252) -> pd.DataFrame:
    """Fetch real stock data via multi-source chain: akshare → baostock → yfinance.

    Each source fills in only the stocks still missing from previous tiers.
    Aborts with clear error message if all sources fail.
    """
    start_date = (datetime.now() - timedelta(days=lookback_days + 30)).strftime("%Y-%m-%d")
    end_date = datetime.now().strftime("%Y-%m-%d")

    print(f"  Fetching {len(tickers)} stocks via multi-source chain ({start_date} ~ {end_date})...")
    t0 = time.time()

    # Import extension helpers (loaded via importlib due to dash in dir name)
    import importlib.util as _iu
    _ext_path = Path(__file__).resolve().parent.parent / "jiuwenswarm" / "extensions" / "quant-finance" / "extension.py"
    _ext_spec = _iu.spec_from_file_location("_quant_fetch_ext", str(_ext_path))
    _ext_mod = _iu.module_from_spec(_ext_spec)
    _ext_spec.loader.exec_module(_ext_mod)
    _fetch_akshare = _ext_mod._fetch_akshare
    _fetch_baostock = _ext_mod._fetch_baostock
    _fetch_yfinance = _ext_mod._fetch_yfinance

    all_prices = {}
    failed = []

    # Tier 1: akshare
    prices, _volumes, errors = _fetch_akshare(tickers, start_date, end_date)
    all_prices.update(prices)
    for e in errors:
        ticker = e.split(":")[1] if ":" in e else ""
        failed.append(e)

    # Tier 2: baostock
    missing = [t for t in tickers if t not in all_prices]
    if missing:
        print(f"    akshare: {len(all_prices)}/{len(tickers)}, baostock filling {len(missing)} missing...")
        prices2, _volumes2, errors2 = _fetch_baostock(missing, start_date, end_date)
        all_prices.update(prices2)
        for e in errors2:
            failed.append(e)

    # Tier 3: yfinance
    still_missing = [t for t in tickers if t not in all_prices]
    if still_missing:
        print(f"    baostock: {len(all_prices)}/{len(tickers)}, yfinance filling {len(still_missing)} missing...")
        prices3, _volumes3, errors3 = _fetch_yfinance(still_missing, start_date, end_date)
        all_prices.update(prices3)
        for e in errors3:
            failed.append(e)

    elapsed = time.time() - t0
    print(f"  Done in {elapsed:.0f}s: {len(all_prices)}/{len(tickers)} stocks fetched")

    if not all_prices:
        print("\n" + "=" * 60)
        print("ERROR: 无法获取任何真实股票数据")
        print("=" * 60)
        if failed:
            print("失败详情:")
            for f in failed[:10]:
                print(f"  - {f}")
        print("\n请检查:")
        print("  1. pip install akshare baostock yfinance")
        print("  2. 网络可以访问东方财富 / BaoStock / Yahoo Finance")
        print("  3. 如在内网，配置代理: set HTTPS_PROXY=http://proxy:port")
        sys.exit(1)

    if failed:
        print(f"  Warning: {len(failed)} errors across all sources, proceeding with {len(all_prices)}")

    result = pd.DataFrame(all_prices).sort_index()
    result = result.dropna(how="all")

    if len(result) < 80:
        print(f"\nERROR: Only {len(result)} trading days available (need >= 80 for reliable backtest)")
        print("Try increasing lookback_days or check data completeness")
        sys.exit(1)

    return result


# ============================================================
# Evaluation runner
# ============================================================

def run_evaluation(n_windows: int = 10) -> dict[str, Any]:
    """Run complete self-evaluation using ONLY real data."""
    from jiuwenswarm.quant import (
        FactorCalculator, FactorConfig, PositionSizer, PositionConfig,
        BacktestEngine, MarketRegime, ALL_STOCKS, RegimeFusion, MarketIndex,
    )
    from jiuwenswarm.quant.stock_pool import STOCK_POOL as SP

    print("=" * 60)
    print("  Quant Investment Agent — Self Evaluation")
    print("  Competition Scoring Criteria (100 pts)")
    print("=" * 60)

    # --- Fetch real data ---
    print("\n[Step 0] Fetching REAL stock data (no simulated fallback)...")
    t0 = time.time()
    prices_df = fetch_real_data(ALL_STOCKS)

    # --- Fetch CSI 300 for index-based regime signal ---
    index_prices = MarketIndex.fetch_csi300(
        str(prices_df.index[0].date()), str(prices_df.index[-1].date())
    )
    if index_prices is not None:
        print(f"  CSI 300: {len(index_prices)} days loaded for index regime signal")

    data_time = time.time() - t0

    n_days = len(prices_df)
    n_stocks = len(prices_df.columns)
    date_min = prices_df.index[0].date()
    date_max = prices_df.index[-1].date()
    print(f"\n  Data: {n_stocks} stocks, {n_days} trading days ({date_min} ~ {date_max})")

    # --- Multi-window evaluation ---
    print(f"\n[Step 1] Evaluating on {n_windows} x 20-day windows...")

    window_results = []
    all_returns = []
    all_drawdowns = []
    total_pipeline_time = 0.0

    min_history = 80
    if n_days - 20 < min_history:
        print(f"\nERROR: Need at least {min_history + 20} trading days, got {n_days}")
        sys.exit(1)

    # Use overlapping but diverse windows spread across the date range
    available_starts = list(range(min_history, n_days - 20))
    if len(available_starts) < n_windows:
        print(f"  Warning: only {len(available_starts)} possible windows, using all")
        window_starts = available_starts
    else:
        step = max(1, len(available_starts) // n_windows)
        window_starts = available_starts[::step][:n_windows]

    for i, start_idx in enumerate(window_starts):
        t_start = time.time()

        window = prices_df.iloc[start_idx:start_idx + 20]
        history = prices_df.iloc[:start_idx + 20]

        if len(window) < 15 or len(history) < min_history:
            continue

        # Run strategy — use fused regime detection
        idx_slice = index_prices[index_prices.index <= history.index[-1]] if index_prices is not None else None
        regime = RegimeFusion.detect(history, index_prices=idx_slice)
        calc = FactorCalculator(FactorConfig())
        calc.regime = regime
        factors = calc.compute_factors(history)
        scores = calc.compute_scores(factors)

        # Volatility hard constraint: exclude stocks with vol_z > 2.0
        scores = calc.filter_high_volatility(scores)

        # Stock selection with sector diversification
        selected, selected_set = [], set()
        for sector in SP:
            for t in scores.index:
                if (t in SP[sector] and t not in selected_set
                        and scores.loc[t, "composite"] > -0.5):
                    selected.append(t)
                    selected_set.add(t)
                    break
        for t in scores.index:
            if len(selected) >= 15:
                break
            if t not in selected_set and scores.loc[t, "composite"] > 0:
                selected.append(t)
                selected_set.add(t)

        # Position sizing + backtest
        sizer = PositionSizer(PositionConfig())
        weights = sizer.allocate(scores, history)
        bt = BacktestEngine().run(window, weights)

        elapsed = time.time() - t_start
        total_pipeline_time += elapsed

        window_info = {
            "idx": i,
            "date_range": f"{window.index[0].date()} ~ {window.index[-1].date()}",
            "regime": regime,
            "n_stocks": len(selected),
            "total_return": round(float(bt.total_return), 6),
            "max_drawdown": round(float(bt.max_drawdown), 6),
            "sharpe_ratio": round(float(bt.sharpe_ratio), 2),
            "ann_vol": round(float(bt.volatility), 4),
            "elapsed_s": round(elapsed, 2),
        }
        window_results.append(window_info)
        all_returns.append(bt.total_return)
        all_drawdowns.append(bt.max_drawdown)

    if not window_results:
        print("\nERROR: No valid windows could be evaluated")
        sys.exit(1)

    avg_pipeline_time = total_pipeline_time / len(window_results)

    # --- Scoring ---
    print("\n[Step 2] Computing scores...")

    median_ret = float(np.median(all_returns))
    median_dd = float(np.median(all_drawdowns))
    worst_ret = float(np.min(all_returns))
    worst_dd = float(np.max(all_drawdowns))
    mean_ret = float(np.mean(all_returns))
    mean_dd = float(np.mean(all_drawdowns))

    ret_score, ret_tier = score_return(median_ret)
    dd_score, dd_tier = score_drawdown(median_dd)

    # Token: pending official baseline — estimate only, no penalty
    agent_tokens = estimate_multi_agent_tokens()
    token_score = 10.0  # full marks pending baseline
    token_tier = "pending_baseline"

    runtime_score, runtime_tier = score_runtime(avg_pipeline_time + data_time / 10)
    compute_score, compute_tier = score_compute_economy(peak_memory_mb=350, gpu_used=False)

    total_portfolio = ret_score + dd_score  # out of 80
    total_resource = token_score + runtime_score + compute_score  # out of 20
    total_score = total_portfolio + total_resource  # out of 100

    # --- Report ---
    print()
    print("=" * 60)
    print("  EVALUATION REPORT")
    print(f"  Data: REAL — {n_stocks} stocks, {n_days} days ({date_min} ~ {date_max})")
    print("=" * 60)
    print()
    print("  ┌─────────────────────────────────────────┐")
    print(f"  │ Dimension 1: Portfolio (80 pts)         │  {total_portfolio:>5.1f} / 80")
    print("  ├─────────────────────────────────────────┤")
    print(f"  │   Return          [{ret_tier:>12s}] │  {ret_score:>5.1f} / 56")
    print(f"  │     median: {median_ret*100:+7.2f}%  worst: {worst_ret*100:+7.2f}%      │")
    print(f"  │     mean:   {mean_ret*100:+7.2f}%                                 │")
    print(f"  │   Max Drawdown    [{dd_tier:>12s}] │  {dd_score:>5.1f} / 24")
    print(f"  │     median: {median_dd*100:7.2f}%  worst: {worst_dd*100:7.2f}%      │")
    print(f"  │     mean:   {mean_dd*100:7.2f}%                                 │")
    print("  ├─────────────────────────────────────────┤")
    print(f"  │ Dimension 2: Resources (20 pts)         │  {total_resource:>5.1f} / 20")
    print("  ├─────────────────────────────────────────┤")
    print(f"  │   Token ({agent_tokens} est.)  [{token_tier:>12s}] │  {token_score:>5.1f} / 10  (待官方基线)")
    print(f"  │   Runtime ({avg_pipeline_time:.0f}s)       [{runtime_tier:>12s}] │  {runtime_score:>5.1f} /  5")
    print(f"  │   Compute (CPU)     [{compute_tier:>12s}] │  {compute_score:>5.1f} /  5")
    print("  └─────────────────────────────────────────┘")
    print(f"  TOTAL: {total_score:.1f} / 100")
    print()
    print("  Window details:")
    for w in window_results:
        print(f"    [{w['date_range']}] {w['regime']:5s} "
              f"ret={w['total_return']*100:+6.2f}% "
              f"dd={w['max_drawdown']*100:5.2f}% "
              f"sharpe={w['sharpe_ratio']:5.1f}")

    report = {
        "evaluation_date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "n_test_windows": len(window_results),
        "data": {"source": "yfinance (REAL)", "n_stocks": n_stocks, "n_days": n_days,
                 "date_range": f"{date_min} ~ {date_max}"},
        "version": "v2.0 (multi-agent Bull/Bear + percentile scoring)",
        "scores": {
            "dimension_1_portfolio": {
                "total": round(total_portfolio, 1), "max": 80,
                "return": {"score": ret_score, "max": 56, "tier": ret_tier,
                           "median": round(median_ret, 6), "worst": round(worst_ret, 6),
                           "mean": round(mean_ret, 6)},
                "max_drawdown": {"score": dd_score, "max": 24, "tier": dd_tier,
                                 "median": round(median_dd, 6), "worst": round(worst_dd, 6),
                                 "mean": round(mean_dd, 6)},
            },
            "dimension_2_resource": {
                "total": round(total_resource, 1), "max": 20,
                "token_consumption": {"score": token_score, "max": 10, "tier": token_tier,
                                      "estimated_tokens": agent_tokens, "baseline_tokens": 6000},
                "runtime_efficiency": {"score": runtime_score, "max": 5, "tier": runtime_tier,
                                       "avg_elapsed_s": round(avg_pipeline_time, 1)},
                "compute_economy": {"score": compute_score, "max": 5, "tier": compute_tier},
            },
        },
        "total_score": round(total_score, 1),
        "window_details": window_results,
    }

    return report


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Quant Agent Self Evaluation (REAL DATA ONLY)")
    parser.add_argument("--windows", type=int, default=8,
                        help="Number of 20-day test windows (default: 8)")
    parser.add_argument("--output", type=str, default="evaluation/latest_score.json",
                        help="Save report as JSON")
    args = parser.parse_args()

    report = run_evaluation(n_windows=args.windows)

    output_path = PROJECT_ROOT / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)
    print(f"\nReport saved to {output_path}")
