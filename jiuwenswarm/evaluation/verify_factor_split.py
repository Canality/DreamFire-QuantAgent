#!/usr/bin/env python3
"""
方向 8 验证: Bull/Bear 因子分离 — 不是同一因子两套权重，而是两批因子

Bull: momentum_20 + momentum_60 + volume_corr (3 趋势因子)
Bear: max_drawdown + reversal_5 + volume_corr_reversed (3 风控因子)

测量: Bull-only top 15 vs Bear-only top 15 overlap
目标: overlap < 60% → 因子分离成功
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path
import importlib.util as _iu

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def main():
    from jiuwenswarm.quant import FactorCalculator, FactorConfig, ALL_STOCKS
    from jiuwenswarm.quant.stock_pool import STOCK_POOL, SECTOR_MAP
    from jiuwenswarm.quant.market_index import MarketIndex

    print("=" * 60)
    print("  方向 8: Bull/Bear 因子分离验证")
    print("=" * 60)

    # ---- Fetch data ----
    _ext_path = PROJECT_ROOT / "jiuwenswarm" / "extensions" / "quant-finance" / "extension.py"
    _ext_spec = _iu.spec_from_file_location("_qf_ext_d8", str(_ext_path))
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
    prices_df = prices_df.loc[common_dates]
    volume_df = volume_df.loc[common_dates]

    index_prices = MarketIndex.fetch_csi300(
        str(prices_df.index[0].date()), str(prices_df.index[-1].date())
    )

    n_days = len(prices_df)
    print(f"  Done: {len(prices_df.columns)} stocks, {n_days} days")

    # ---- Bull Config: 3 trend factors only ----
    class BullTrendConfig(FactorConfig):
        """Bull: only trend factors. Weights sum to 1.0."""
        def get_regime_weights(self, regime):
            return {
                "momentum_20_z": 0.50,
                "momentum_60_z": 0.25,
                "volume_corr_z": 0.25,
                # max_drawdown and reversal_5 excluded entirely
            }

    # ---- Bear Config: 3 risk factors only ----
    class BearRiskConfig(FactorConfig):
        """Bear: only risk factors. volume_corr REVERSED (divergence = risk)."""
        def get_regime_weights(self, regime):
            return {
                "max_drawdown_z": -0.45,   # low drawdown = high score
                "reversal_5_z": 0.35,       # positive reversal = mean-reversion = safe
                "volume_corr_z": -0.20,     # REVERSED: high corr = trending = risk
            }

    bull_calc = FactorCalculator(BullTrendConfig())
    bear_calc = FactorCalculator(BearRiskConfig())

    # ---- Multi-window overlap analysis ----
    min_history = 80
    window_size = 20
    available_starts = list(range(min_history, n_days - window_size))
    step = max(1, len(available_starts) // 8)
    window_starts = available_starts[::step][:8]

    print(f"\n  因子集差异:")
    print(f"    Bull: momentum_20, momentum_60, volume_corr (3 trend)")
    print(f"    Bear: max_drawdown, reversal_5, volume_corr_REVERSED (3 risk)")
    print(f"\n  Overlap on {len(window_starts)} windows:\n")

    def select_sector_diversified(scores, n=15):
        selected, selected_set = [], set()
        for sector in STOCK_POOL:
            for t in scores.index:
                if (t in STOCK_POOL[sector] and t not in selected_set
                        and scores.loc[t, "composite"] > -0.5):
                    selected.append(t)
                    selected_set.add(t)
                    break
        for t in scores.index:
            if len(selected) >= n:
                break
            if t not in selected_set:
                selected.append(t)
        return selected[:n]

    overlaps = []
    spearman_rs = []
    all_bull_picks = []
    all_bear_picks = []

    for i, start_idx in enumerate(window_starts):
        window_end = start_idx + window_size
        history_prices = prices_df.iloc[:window_end]
        history_volume = volume_df.iloc[:window_end]

        # Compute factors once (same raw factors for both, different subsets used)
        base_calc = FactorCalculator(FactorConfig())
        factors = base_calc.compute_factors(history_prices, history_volume)

        # Bull scoring (only uses columns that exist in its weight map)
        bull_scores = bull_calc.compute_scores(factors.copy())
        bull_scores = bull_calc.filter_high_volatility(bull_scores)

        # Bear scoring
        bear_scores = bear_calc.compute_scores(factors.copy())
        bear_scores = bear_calc.filter_high_volatility(bear_scores)

        bull_top15 = select_sector_diversified(bull_scores)
        bear_top15 = select_sector_diversified(bear_scores)

        bull_set, bear_set = set(bull_top15), set(bear_top15)
        common = bull_set & bear_set
        overlap_pct = len(common) / 15 * 100

        # Spearman r
        common_idx = bull_scores.index.intersection(bear_scores.index)
        if len(common_idx) > 5:
            r = bull_scores.loc[common_idx, "composite"].corr(
                bear_scores.loc[common_idx, "composite"])
        else:
            r = float('nan')

        overlaps.append(overlap_pct)
        spearman_rs.append(r)
        all_bull_picks.extend(bull_top15)
        all_bear_picks.extend(bear_top15)

        date_label = history_prices.index[-1].date()
        print(f"  Window {i} ({date_label})  overlap={overlap_pct:.0f}%  r={r:+.3f}")

    # ---- Summary ----
    print()
    print("=" * 60)
    print("  汇总")
    print("=" * 60)
    mean_overlap = np.mean(overlaps)
    mean_r = np.nanmean(spearman_rs)
    bull_unique = len(set(all_bull_picks) - set(all_bear_picks))
    bear_unique = len(set(all_bear_picks) - set(all_bull_picks))

    print(f"  平均 Overlap: {mean_overlap:.0f}%")
    print(f"  平均 Spearman r: {mean_r:.3f}")
    print(f"  Bull 独有: {bull_unique} 只")
    print(f"  Bear 独有: {bear_unique} 只")
    print(f"  窗口明细: {[f'{o:.0f}%' for o in overlaps]}")

    # Comparison with direction 4/7
    print()
    print("  对比历史:")
    print(f"    方向 4 (双视角 regime weight):  r=0.83-0.93")
    print(f"    方向 7 (权重分离 base weight):  r=0.89, overlap=79%")
    print(f"    方向 8 (因子集分离):            r={mean_r:.3f}, overlap={mean_overlap:.0f}%")

    print()
    if mean_overlap < 50:
        print("  [OK] overlap < 50% — 因子分离成功！")
        print("  Bull 和 Bear 确实在看不同的东西，选出不同的股票")
        print("  建议: 正式实现因子分离架构")
    elif mean_overlap < 65:
        print("  [OK] overlap < 65% — 因子分离有效")
        print("  相比方向 7 的 79%，差异化显著提升")
        print("  建议: 实现因子分离，可选增强 Bear 因子")
    elif mean_overlap < 75:
        print("  [MAYBE] 有改进但不够显著")
    else:
        print("  [SKIP] 仍然高度重叠 — 价格因子天然收敛")


if __name__ == "__main__":
    main()
