#!/usr/bin/env python3
"""
Round 4 IC 验证: up_days_ratio + vol_expansion

候选 1: up_days_ratio — 过去 20 日上涨天数占比（上涨的均匀程度）
候选 2: vol_expansion — 前半段 vs 后半段波动率对比（趋势生命周期）

阈值: Mean IC > 0.03, Pos% > 60%, 与最高相关因子 r < 0.7
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path
import importlib.util as _iu

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def spearman_corr(a, b):
    """Spearman rank correlation (no scipy)."""
    mask = a.notna() & b.notna()
    a_clean = a[mask].astype(float)
    b_clean = b[mask].astype(float)
    if len(a_clean) < 3:
        return 0.0
    ra, rb = a_clean.rank(), b_clean.rank()
    return float(ra.corr(rb))


def main():
    from jiuwenswarm.quant import FactorCalculator, FactorConfig, ALL_STOCKS

    print("=" * 60)
    print("  Round 4: up_days_ratio + vol_expansion IC 验证")
    print("=" * 60)

    # ---- Load fetch functions ----
    _ext_path = PROJECT_ROOT / "jiuwenswarm" / "extensions" / "quant-finance" / "extension.py"
    _ext_spec = _iu.spec_from_file_location("_qf_ext_r4", str(_ext_path))
    _ext_mod = _iu.module_from_spec(_ext_spec)
    _ext_spec.loader.exec_module(_ext_mod)
    _fetch_akshare = _ext_mod._fetch_akshare
    _fetch_baostock = _ext_mod._fetch_baostock
    _fetch_yfinance = _ext_mod._fetch_yfinance

    lookback_days = 252
    start_date = (datetime.now() - timedelta(days=lookback_days + 30)).strftime("%Y-%m-%d")
    end_date = datetime.now().strftime("%Y-%m-%d")

    print(f"\n  Fetching {len(ALL_STOCKS)} stocks...")
    prices_raw, volumes_raw, _ = _fetch_akshare(ALL_STOCKS, start_date, end_date)
    all_prices, all_volumes = dict(prices_raw), dict(volumes_raw)
    missing = [t for t in ALL_STOCKS if t not in all_prices]
    if missing:
        p2, v2, _ = _fetch_baostock(missing, start_date, end_date)
        all_prices.update(p2); all_volumes.update(v2)
    still_missing = [t for t in ALL_STOCKS if t not in all_prices]
    if still_missing:
        p3, v3, _ = _fetch_yfinance(still_missing, start_date, end_date)
        all_prices.update(p3); all_volumes.update(v3)

    prices_df = pd.DataFrame(all_prices).sort_index().dropna(how="all")
    volume_df = pd.DataFrame(all_volumes).sort_index()
    common_dates = prices_df.index.intersection(volume_df.index)
    prices_df, volume_df = prices_df.loc[common_dates], volume_df.loc[common_dates]
    returns = prices_df.pct_change()

    print(f"  Done: {len(prices_df.columns)} stocks, {len(prices_df)} days")

    # ---- Compute existing 5 factors for correlation reference ----
    calc = FactorCalculator(FactorConfig())
    base_factors = calc.compute_factors(prices_df, volume_df)

    # ---- Define new factor computation functions ----
    def compute_up_days_ratio(price_slice):
        """Ratio of up-days in the past 20 trading days."""
        ret_slice = price_slice.pct_change()
        up_days = (ret_slice.tail(20) > 0).sum()
        n = min(len(ret_slice.tail(20)), 20)
        return float(up_days) / max(n, 1)  # 0.0 to 1.0

    def compute_vol_expansion(price_slice):
        """Volatility change: late 10d vol / early 10d vol - 1."""
        ret_slice = price_slice.pct_change().tail(20)
        if len(ret_slice) < 15:
            return 0.0
        vol_early = ret_slice.iloc[:10].std()
        vol_late = ret_slice.iloc[-10:].std()
        if vol_early < 0.001:
            return 0.0
        return float(vol_late / vol_early - 1.0)

    # ---- Multi-window IC analysis ----
    n_days = len(prices_df)
    min_history = 80
    window_size = 20
    available_starts = list(range(min_history, n_days - window_size))
    step = max(1, len(available_starts) // 8)
    window_starts = available_starts[::step][:8]

    target_factors = [
        "momentum_20", "momentum_60", "reversal_5",
        "max_drawdown", "volume_corr",
        "up_days_ratio", "vol_expansion",
    ]

    print(f"\n  IC analysis on {len(window_starts)} windows:\n")

    ic_results = {f: [] for f in target_factors}

    for i, start_idx in enumerate(window_starts):
        window_end = start_idx + window_size
        history_prices = prices_df.iloc[:window_end]
        history_volume = volume_df.iloc[:window_end]
        hist_returns = history_prices.pct_change()

        # Compute existing factors on truncated history
        f_slice = calc.compute_factors(history_prices, history_volume)

        # Compute new factors
        udr = {}
        vex = {}
        for ticker in prices_df.columns:
            if ticker in history_prices.columns:
                ticker_price = history_prices[ticker].dropna()
                udr[ticker] = compute_up_days_ratio(ticker_price)
                vex[ticker] = compute_vol_expansion(ticker_price)
            else:
                udr[ticker] = 0.0
                vex[ticker] = 0.0
        f_slice["up_days_ratio"] = pd.Series(udr)
        f_slice["vol_expansion"] = pd.Series(vex)

        # Forward 20-day returns
        fwd_ret = {}
        for ticker in prices_df.columns:
            try:
                p_start = prices_df[ticker].iloc[window_end]
                p_end = prices_df[ticker].iloc[min(window_end + window_size - 1, n_days - 1)]
                fwd_ret[ticker] = p_end / p_start - 1
            except (IndexError, KeyError):
                fwd_ret[ticker] = 0.0
        fwd_series = pd.Series(fwd_ret)

        # IC per factor
        window_ics = {}
        for factor_name in target_factors:
            if factor_name not in f_slice.columns:
                window_ics[factor_name] = np.nan
                continue
            factor_vals = f_slice[factor_name].dropna()
            common = factor_vals.index.intersection(fwd_series.dropna().index)
            if len(common) < 10:
                window_ics[factor_name] = np.nan
                continue
            ic = spearman_corr(factor_vals[common].astype(float),
                               fwd_series[common].astype(float))
            window_ics[factor_name] = 0.0 if np.isnan(ic) else round(float(ic), 4)
            ic_results[factor_name].append(window_ics[factor_name])

        date_label = history_prices.index[-1].date()
        new_line = f"  up_days={window_ics.get('up_days_ratio', np.nan):+.3f}  vol_exp={window_ics.get('vol_expansion', np.nan):+.3f}"
        old_line = " | ".join(
            f"{k}={window_ics.get(k, np.nan):+.3f}"
            for k in ["momentum_20", "momentum_60", "reversal_5", "max_drawdown", "volume_corr"]
        )
        print(f"  Window {i} ({date_label})")
        print(f"    Existing: {old_line}")
        print(f"    New:      {new_line}")

    # ---- Summary ----
    print()
    print("=" * 60)
    print("  IC 汇总")
    print("=" * 60)
    print(f"  {'Factor':<22s} {'Mean IC':>8s} {'Std IC':>8s} {'Min IC':>8s} {'Max IC':>8s} {'Pos%':>6s}  Verdict")
    print("  " + "-" * 70)

    verdicts = {}
    for f in target_factors:
        vals = [v for v in ic_results[f] if not np.isnan(v)]
        if not vals:
            continue
        mean_ic = np.mean(vals)
        std_ic = np.std(vals)
        min_ic = np.min(vals)
        max_ic = np.max(vals)
        pos_pct = sum(1 for v in vals if v > 0) / len(vals) * 100

        if abs(mean_ic) < 0.03:
            verdict = "DEAD |IC|<0.03"
        elif pos_pct < 60:
            verdict = "UNSTABLE"
        else:
            verdict = "ALIVE"
        verdicts[f] = verdict

        print(f"  {f:<22s} {mean_ic:>+8.4f} {std_ic:>8.4f} {min_ic:>+8.4f} {max_ic:>+8.4f} {pos_pct:>5.0f}%  {verdict}")

    # ---- Factor correlation (full period) ----
    # Compute new factors on full data
    full_udr = {}
    full_vex = {}
    for ticker in prices_df.columns:
        if ticker in prices_df.columns:
            full_udr[ticker] = compute_up_days_ratio(prices_df[ticker].dropna())
            full_vex[ticker] = compute_vol_expansion(prices_df[ticker].dropna())
        else:
            full_udr[ticker] = 0.0; full_vex[ticker] = 0.0
    base_factors["up_days_ratio"] = pd.Series(full_udr)
    base_factors["vol_expansion"] = pd.Series(full_vex)

    print()
    print("=" * 60)
    print("  因子间相关性 (全期)")
    print("=" * 60)
    corr_cols = [c for c in target_factors if c in base_factors.columns]
    corr_matrix = base_factors[corr_cols].corr()
    print(corr_matrix.round(3).to_string())

    # ---- Verdict for new factors ----
    print()
    print("=" * 60)
    print("  新因子判定")
    print("=" * 60)

    for new_f in ["up_days_ratio", "vol_expansion"]:
        print(f"\n  --- {new_f} ---")
        v = verdicts.get(new_f, "UNKNOWN")

        if "ALIVE" not in v:
            print(f"  [SKIP] {new_f}: {v} — 不值得加入")
            continue

        # Check collinearity
        if new_f in corr_matrix.columns:
            new_corr = corr_matrix[new_f].drop(new_f).abs()
            max_corr = new_corr.max()
            max_corr_factor = new_corr.idxmax()
            if max_corr > 0.7:
                print(f"  [WARN] {new_f} 与 {max_corr_factor} 高度相关 (r={max_corr:.3f})，增量信息有限")
            else:
                print(f"  [OK] {new_f} 与现有因子最高相关 r={max_corr:.3f} ({max_corr_factor})")
                print(f"       具有独立预测力，Mean IC={ic_results[new_f]['mean' if isinstance(ic_results[new_f], dict) else 0]:.4f}")

                # Weight recommendation
                mean_ic_new = np.mean([x for x in ic_results[new_f] if not np.isnan(x)])
                std_ic_new = np.std([x for x in ic_results[new_f] if not np.isnan(x)])
                # Weight proportional to IC, penalized by std
                if abs(mean_ic_new) > 0.05:
                    wt = 0.15
                elif abs(mean_ic_new) > 0.03:
                    wt = 0.10
                else:
                    wt = 0.05
                print(f"       建议权重: {wt:.2f}")


if __name__ == "__main__":
    main()
