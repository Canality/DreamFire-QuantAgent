#!/usr/bin/env python3
"""
Round 4 续: 一批 4 候选 IC 验证

候选 3: volume_trend — 成交量 20 日变化趋势 (后10均/前10均 - 1)
候选 4: skewness_20 — 20 日收益率偏度
候选 5: sector_rel_mom — 个股动量 - 板块平均动量
候选 6: amihud_20 — Amihud 非流动性指标

全部要求: Mean IC > 0.03, Pos% > 60%, 与最高相关因子 r < 0.7
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
    mask = a.notna() & b.notna()
    a_clean = a[mask].astype(float)
    b_clean = b[mask].astype(float)
    if len(a_clean) < 3:
        return 0.0
    return float(a_clean.rank().corr(b_clean.rank()))


def main():
    from jiuwenswarm.quant import FactorCalculator, FactorConfig, ALL_STOCKS
    from jiuwenswarm.quant.stock_pool import STOCK_POOL, SECTOR_MAP

    print("=" * 60)
    print("  Round 4 续: 4 候选 IC 验证")
    print("=" * 60)

    # ---- Fetch data ----
    _ext_path = PROJECT_ROOT / "jiuwenswarm" / "extensions" / "quant-finance" / "extension.py"
    _ext_spec = _iu.spec_from_file_location("_qf_ext_r4b", str(_ext_path))
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

    print(f"  Done: {len(prices_df.columns)} stocks, {len(prices_df)} days")

    # ---- Existing factors ----
    calc = FactorCalculator(FactorConfig())

    # ---- New factor computations ----
    def compute_volume_trend(vol_series):
        """Volume trend: late 10d avg / early 10d avg - 1."""
        v = vol_series.tail(20)
        if len(v) < 15: return 0.0
        v_early = v.iloc[:10].mean()
        v_late = v.iloc[-10:].mean()
        if v_early < 1: return 1.0  # huge growth
        return float(v_late / v_early - 1.0)

    def compute_skewness(ret_series):
        """Return skewness over past 20 days."""
        r = ret_series.tail(20).dropna()
        if len(r) < 10: return 0.0
        std = r.std()
        if std < 0.001: return 0.0
        return float(r.skew())

    def compute_sector_rel_mom(price_series, ticker):
        """Stock momentum minus sector average momentum."""
        if len(price_series) < 21: return 0.0
        mom = price_series.iloc[-1] / price_series.iloc[-21] - 1
        sector = SECTOR_MAP.get(ticker, "")
        if not sector: return mom
        # Compute sector average from all stocks in same sector
        sector_stocks = STOCK_POOL.get(sector, [])
        sector_moms = []
        for s in sector_stocks:
            if s in prices_df.columns and s != ticker:
                s_price = prices_df[s].dropna()
                if len(s_price) >= 21:
                    s_mom = s_price.iloc[-1] / s_price.iloc[-21] - 1
                    if not np.isnan(s_mom):
                        sector_moms.append(s_mom)
        if len(sector_moms) < 1: return mom  # no peers, return raw mom
        sector_avg = np.mean(sector_moms)
        return float(mom - sector_avg)

    def compute_amihud(ret_series, vol_series, price_series):
        """Amihud illiquidity: mean of |ret| / (volume * close)."""
        r = ret_series.tail(20).dropna()
        v = vol_series.tail(20).dropna()
        p = price_series.tail(20).dropna()
        common = r.index.intersection(v.index).intersection(p.index)
        if len(common) < 10: return 0.0
        amihud_vals = abs(r[common]) / ((v[common] * p[common]).replace(0, np.nan) + 1)
        return float(amihud_vals.mean())

    # ---- Multi-window IC analysis ----
    n_days = len(prices_df)
    min_history = 80
    window_size = 20
    available_starts = list(range(min_history, n_days - window_size))
    step = max(1, len(available_starts) // 8)
    window_starts = available_starts[::step][:8]

    # Existing + new factors
    existing = ["momentum_20", "momentum_60", "reversal_5", "max_drawdown", "volume_corr"]
    new_candidates = ["volume_trend", "skewness_20", "sector_rel_mom", "amihud_20"]
    all_factors = existing + new_candidates

    print(f"\n  IC analysis on {len(window_starts)} windows:\n")

    ic_results = {f: [] for f in all_factors}

    for i, start_idx in enumerate(window_starts):
        window_end = start_idx + window_size
        history_prices = prices_df.iloc[:window_end]
        history_volume = volume_df.iloc[:window_end]
        hist_returns = history_prices.pct_change()

        # Existing factors
        f_slice = calc.compute_factors(history_prices, history_volume)

        # New factors per stock
        vt, sk, sr, am = {}, {}, {}, {}
        for ticker in prices_df.columns:
            if ticker not in history_prices.columns:
                vt[ticker] = 0.0; sk[ticker] = 0.0; sr[ticker] = 0.0; am[ticker] = 0.0
                continue
            tp = history_prices[ticker].dropna()
            tv = history_volume[ticker].dropna() if ticker in history_volume.columns else pd.Series()
            tr = tp.pct_change()
            vt[ticker] = compute_volume_trend(tv) if len(tv) > 10 else 0.0
            sk[ticker] = compute_skewness(tr)
            sr[ticker] = compute_sector_rel_mom(tp, ticker)
            am[ticker] = compute_amihud(tr, tv, tp) if len(tv) > 10 else 0.0

        f_slice["volume_trend"] = pd.Series(vt)
        f_slice["skewness_20"] = pd.Series(sk)
        f_slice["sector_rel_mom"] = pd.Series(sr)
        f_slice["amihud_20"] = pd.Series(am)

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

        # IC
        window_ics = {}
        for factor_name in all_factors:
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
        new_str = " | ".join(
            f"{k}={window_ics.get(k, np.nan):+.3f}" for k in new_candidates
        )
        print(f"  Window {i} ({date_label})")
        print(f"    New: {new_str}")

    # ---- Summary ----
    print()
    print("=" * 60)
    print("  IC 汇总")
    print("=" * 60)
    print(f"  {'Factor':<22s} {'Mean IC':>8s} {'Std IC':>8s} {'Min IC':>8s} {'Max IC':>8s} {'Pos%':>6s}  Verdict")
    print("  " + "-" * 75)

    verdicts = {}
    for f in all_factors:
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
    base_factors = calc.compute_factors(prices_df, volume_df)
    full_vt, full_sk, full_sr, full_am = {}, {}, {}, {}
    for ticker in prices_df.columns:
        tp = prices_df[ticker].dropna()
        tv = volume_df[ticker].dropna() if ticker in volume_df.columns else pd.Series()
        full_vt[ticker] = compute_volume_trend(tv) if len(tv) > 10 else 0.0
        full_sk[ticker] = compute_skewness(tp.pct_change())
        full_sr[ticker] = compute_sector_rel_mom(tp, ticker)
        full_am[ticker] = compute_amihud(tp.pct_change(), tv, tp) if len(tv) > 10 else 0.0
    base_factors["volume_trend"] = pd.Series(full_vt)
    base_factors["skewness_20"] = pd.Series(full_sk)
    base_factors["sector_rel_mom"] = pd.Series(full_sr)
    base_factors["amihud_20"] = pd.Series(full_am)

    print()
    print("=" * 60)
    print("  因子间相关性 (全期)")
    print("=" * 60)
    corr_cols = [c for c in all_factors if c in base_factors.columns]
    corr_matrix = base_factors[corr_cols].corr()
    print(corr_matrix.round(3).to_string())

    # ---- New factor verdicts ----
    print()
    print("=" * 60)
    print("  新因子最终判定")
    print("=" * 60)

    for new_f in new_candidates:
        print(f"\n  --- {new_f} ---")
        vals = [v for v in ic_results[new_f] if not np.isnan(v)]
        if not vals:
            print(f"  [SKIP] No valid IC data")
            continue
        mean_ic = np.mean(vals)
        std_ic = np.std(vals)
        pos_pct = sum(1 for v in vals if v > 0) / len(vals) * 100
        v = verdicts.get(new_f, "UNKNOWN")

        if "ALIVE" not in v:
            print(f"  [SKIP] {v}")
            continue

        # Check collinearity
        if new_f in corr_matrix.columns:
            new_corr = corr_matrix[new_f].drop(new_f).abs()
            max_corr = new_corr.max()
            max_corr_factor = new_corr.idxmax()
            if max_corr > 0.7:
                print(f"  [WARN] 与 {max_corr_factor} 高度相关 (r={max_corr:.3f})")
                print(f"         IC={mean_ic:+.4f} 但不独立，不建议加入")
            else:
                print(f"  [PASS] IC={mean_ic:+.4f}, Pos={pos_pct:.0f}%, max_corr={max_corr:.3f} ({max_corr_factor})")
                wt = 0.15 if abs(mean_ic) > 0.06 else 0.10
                print(f"         独立于现有因子，建议加入，权重 {wt:.2f}")


if __name__ == "__main__":
    main()
