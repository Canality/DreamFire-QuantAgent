#!/usr/bin/env python3
"""
方向 5 验证: 量价相关性因子 IC 分析

测量 volume_corr (过去 20 日收益率与成交量秩相关系数) 的预测力:
  - IC: 因子值与未来 20 日收益的 Spearman 秩相关系数
  - 与其他 4 因子的相关性
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path
import importlib.util as _iu

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def spearman_corr(a: pd.Series, b: pd.Series) -> float:
    """Spearman rank correlation (no scipy dependency)."""
    mask = a.notna() & b.notna()
    a_clean = a[mask].astype(float)
    b_clean = b[mask].astype(float)
    if len(a_clean) < 3:
        return 0.0
    # Rank-transform then Pearson
    ra = a_clean.rank()
    rb = b_clean.rank()
    return float(ra.corr(rb))


def main():
    from jiuwenswarm.quant import FactorCalculator, FactorConfig, ALL_STOCKS

    print("=" * 60)
    print("  方向 5: 量价相关性因子 IC 验证")
    print("=" * 60)

    # ---- Load extension fetch functions ----
    _ext_path = PROJECT_ROOT / "jiuwenswarm" / "extensions" / "quant-finance" / "extension.py"
    _ext_spec = _iu.spec_from_file_location("_qf_ext_ic", str(_ext_path))
    _ext_mod = _iu.module_from_spec(_ext_spec)
    _ext_spec.loader.exec_module(_ext_mod)
    _fetch_akshare = _ext_mod._fetch_akshare
    _fetch_baostock = _ext_mod._fetch_baostock
    _fetch_yfinance = _ext_mod._fetch_yfinance

    lookback_days = 252
    start_date = (datetime.now() - timedelta(days=lookback_days + 30)).strftime("%Y-%m-%d")
    end_date = datetime.now().strftime("%Y-%m-%d")

    # ---- Fetch price + volume in one pass ----
    print(f"\n  Fetching {len(ALL_STOCKS)} stocks via multi-source chain ({start_date} ~ {end_date})...")

    prices_raw, volumes_raw, errors = _fetch_akshare(ALL_STOCKS, start_date, end_date)
    all_prices, all_volumes = dict(prices_raw), dict(volumes_raw)

    missing = [t for t in ALL_STOCKS if t not in all_prices]
    if missing:
        p2, v2, _ = _fetch_baostock(missing, start_date, end_date)
        all_prices.update(p2)
        all_volumes.update(v2)

    still_missing = [t for t in ALL_STOCKS if t not in all_prices]
    if still_missing:
        p3, v3, _ = _fetch_yfinance(still_missing, start_date, end_date)
        all_prices.update(p3)
        all_volumes.update(v3)

    prices_df = pd.DataFrame(all_prices).sort_index().dropna(how="all")
    volume_df = pd.DataFrame(all_volumes).sort_index()

    # Align indices
    common_dates = prices_df.index.intersection(volume_df.index)
    prices_df = prices_df.loc[common_dates]
    volume_df = volume_df.loc[common_dates]

    print(f"  Done: {len(prices_df.columns)} stocks, {len(prices_df)} trading days")

    returns = prices_df.pct_change()
    n_days = len(prices_df)

    # ---- Compute existing 4 factors ----
    calc = FactorCalculator(FactorConfig())
    factors = calc.compute_factors(prices_df, volume_df)

    # ---- Compute volume-price correlation factor ----
    print("\n[1] Computing volume_corr factor...")
    vol_corr_factor = {}
    for ticker in prices_df.columns:
        if ticker not in volume_df.columns:
            vol_corr_factor[ticker] = 0.0
            continue
        ret_20 = returns[ticker].tail(20).dropna()
        vol_20 = volume_df[ticker].tail(20).dropna()
        common_idx = ret_20.index.intersection(vol_20.index)
        if len(common_idx) < 10:
            vol_corr_factor[ticker] = 0.0
            continue
        r = spearman_corr(ret_20[common_idx], vol_20[common_idx])
        vol_corr_factor[ticker] = 0.0 if np.isnan(r) else r

    factors["volume_corr"] = pd.Series(vol_corr_factor)

    # ---- Multi-window IC analysis ----
    min_history = 80
    window_size = 20
    available_starts = list(range(min_history, n_days - window_size))
    step = max(1, len(available_starts) // 8)
    window_starts = available_starts[::step][:8]

    print(f"\n[2] IC analysis on {len(window_starts)} windows...\n")

    target_factors = [
        "momentum_20", "momentum_60", "reversal_5",
        "max_drawdown", "volume_corr"
    ]

    ic_results = {f: [] for f in target_factors}

    for i, start_idx in enumerate(window_starts):
        window_end = start_idx + window_size

        # Factor values computed using data available at window start
        history_prices = prices_df.iloc[:window_end]
        history_volume = volume_df.iloc[:window_end]

        f_slice = calc.compute_factors(history_prices, history_volume)

        # volume_corr on truncated history
        ret_slice = history_prices.pct_change()
        vc = {}
        for ticker in prices_df.columns:
            if ticker not in volume_df.columns:
                vc[ticker] = 0.0
                continue
            r20 = ret_slice[ticker].tail(20).dropna()
            v20 = history_volume[ticker].tail(20).dropna()
            common_idx = r20.index.intersection(v20.index)
            if len(common_idx) < 10:
                vc[ticker] = 0.0
                continue
            r = spearman_corr(r20[common_idx], v20[common_idx])
            vc[ticker] = 0.0 if np.isnan(r) else r
        f_slice["volume_corr"] = pd.Series(vc)

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

        date_label = f"{prices_df.index[window_end].date()}"
        print(f"  Window {i} (before {date_label}): "
              + " | ".join(f"{k}={window_ics.get(k, np.nan):+.3f}" for k in target_factors))

    # ---- Summary ----
    print()
    print("=" * 60)
    print("  IC 汇总")
    print("=" * 60)
    print(f"  {'Factor':<22s} {'Mean IC':>8s} {'Std IC':>8s} {'Min IC':>8s} {'Max IC':>8s} {'Pos%':>6s}")
    print("  " + "-" * 56)

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
        print(f"  {f:<22s} {mean_ic:>+8.4f} {std_ic:>8.4f} {min_ic:>+8.4f} {max_ic:>+8.4f} {pos_pct:>5.0f}%")

        if abs(mean_ic) < 0.03:
            verdicts[f] = "DEAD (|IC|<0.03)"
        elif pos_pct < 60:
            verdicts[f] = "UNSTABLE (pos%<60%)"
        else:
            verdicts[f] = "ALIVE"

    # ---- Factor correlation (full period) ----
    print()
    print("=" * 60)
    print("  因子间相关性 (全期)")
    print("=" * 60)
    corr_cols = [c for c in target_factors if c in factors.columns]
    corr_matrix = factors[corr_cols].corr()
    print(corr_matrix.round(3).to_string())

    # ---- Verdict ----
    print()
    print("=" * 60)
    print("  判定")
    print("=" * 60)
    for f, v in verdicts.items():
        status = "[OK]" if "ALIVE" in v else "[XX]"
        print(f"  {status} {f}: {v}")

    if "volume_corr" in verdicts and "ALIVE" in verdicts["volume_corr"]:
        vc_corr = corr_matrix["volume_corr"].drop("volume_corr").abs()
        max_corr = vc_corr.max()
        max_corr_factor = vc_corr.idxmax()
        if max_corr > 0.7:
            print(f"\n  [WARN] volume_corr 与 {max_corr_factor} 高度相关 (r={max_corr:.3f})")
            print(f"     增量信息有限，不建议加入")
        else:
            print(f"\n  [OK] volume_corr 与现有因子最高相关 r={max_corr:.3f} ({max_corr_factor})")
            print(f"     具有独立预测力，建议加入因子模型，权重 0.10-0.15")
    else:
        print(f"\n  结论: volume_corr 不值得加入因子模型")


if __name__ == "__main__":
    main()
