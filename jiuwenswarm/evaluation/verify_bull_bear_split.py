#!/usr/bin/env python3
"""
方向 7 验证: Bull/Bear 权重分离 + 独立选股对比

验证两个 Agent 用独立 FactorConfig 时的选股差异:
  - Bull: 动量导向 (mom_20=0.50, mom_60=0.25, reversal_5=0.10, max_dd=-0.15)
  - Bear: 防御导向 (mom_20=0.12, mom_60=0.08, reversal_5=0.30, max_dd=-0.50)
  - 对比 top 15 重叠度
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
    from jiuwenswarm.quant.market_regime import MarketRegime
    from jiuwenswarm.quant.regime_fusion import RegimeFusion
    from jiuwenswarm.quant.market_index import MarketIndex
    from jiuwenswarm.quant.stock_pool import STOCK_POOL

    print("=" * 60)
    print("  方向 7: Bull/Bear 权重分离 — 独立选股对比")
    print("=" * 60)

    # ---- Fetch data ----
    _ext_path = PROJECT_ROOT / "jiuwenswarm" / "extensions" / "quant-finance" / "extension.py"
    _ext_spec = _iu.spec_from_file_location("_qf_ext_d7", str(_ext_path))
    _ext_mod = _iu.module_from_spec(_ext_spec)
    _ext_spec.loader.exec_module(_ext_mod)
    _fetch_akshare = _ext_mod._fetch_akshare
    _fetch_baostock = _ext_mod._fetch_baostock
    _fetch_yfinance = _ext_mod._fetch_yfinance

    lookback_days = 252
    start_date = (datetime.now() - timedelta(days=lookback_days + 30)).strftime("%Y-%m-%d")
    end_date = datetime.now().strftime("%Y-%m-%d")

    print(f"\n  Fetching {len(ALL_STOCKS)} stocks...")
    prices_raw, volumes_raw, errors = _fetch_akshare(ALL_STOCKS, start_date, end_date)
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

    # Fetch CSI 300 for regime
    index_prices = MarketIndex.fetch_csi300(
        str(prices_df.index[0].date()), str(prices_df.index[-1].date())
    )

    n_days = len(prices_df)
    print(f"  Done: {len(prices_df.columns)} stocks, {n_days} days")

    # ---- Define separate configs ----
    # Bull: momentum-heavy (Round 2 verified direction)
    class BullConfig(FactorConfig):
        def __init__(self):
            super().__init__()
        def get_regime_weights(self, regime):
            # Fixed weights regardless of regime
            return {
                "momentum_20_z": 0.50,
                "momentum_60_z": 0.25,
                "reversal_5_z": -0.10,
                "max_drawdown_z": -0.15,
            }

    # Bear: defense-heavy
    class BearConfig(FactorConfig):
        def __init__(self):
            super().__init__()
        def get_regime_weights(self, regime):
            return {
                "momentum_20_z": 0.12,
                "momentum_60_z": 0.08,
                "reversal_5_z": -0.30,
                "max_drawdown_z": -0.50,
            }

    bull_calc = FactorCalculator(BullConfig())
    bear_calc = FactorCalculator(BearConfig())

    # ---- Multi-window overlap analysis ----
    min_history = 80
    window_size = 20
    available_starts = list(range(min_history, n_days - window_size))
    step = max(1, len(available_starts) // 8)
    window_starts = available_starts[::step][:8]

    print(f"\n  Overlap analysis on {len(window_starts)} windows:\n")

    all_bull_picks = []
    all_bear_picks = []
    overlaps = []
    spearman_rs = []

    for i, start_idx in enumerate(window_starts):
        window_end = start_idx + window_size
        history_prices = prices_df.iloc[:window_end]
        history_volume = volume_df.iloc[:window_end]

        # Regime detection
        idx_slice = index_prices[index_prices.index <= history_prices.index[-1]] if index_prices is not None else None
        regime = RegimeFusion.detect(history_prices, index_prices=idx_slice)

        # Compute factors (same for both configs, only weights differ)
        factors = bull_calc.compute_factors(history_prices, history_volume)

        # Bull scoring
        bull_calc.regime = regime
        bull_scores = bull_calc.compute_scores(factors.copy())
        bull_scores = bull_calc.filter_high_volatility(bull_scores)

        # Bear scoring
        bear_calc.regime = regime
        bear_scores = bear_calc.compute_scores(factors.copy())
        bear_scores = bear_calc.filter_high_volatility(bear_scores)

        # Stock selection (sector-diversified)
        def select_top_n(scores, n=15):
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
                if t not in selected_set and scores.loc[t, "composite"] > 0:
                    selected.append(t)
            return selected[:n]

        bull_top15 = select_top_n(bull_scores)
        bear_top15 = select_top_n(bear_scores)

        # Overlap
        bull_set = set(bull_top15)
        bear_set = set(bear_top15)
        common = bull_set & bear_set
        overlap_pct = len(common) / 15 * 100

        # Spearman r between bull and bear composite scores
        common_stocks = bull_scores.index.intersection(bear_scores.index)
        if len(common_stocks) > 5:
            r = bull_scores.loc[common_stocks, "composite"].corr(
                bear_scores.loc[common_stocks, "composite"], method='pearson')
        else:
            r = float('nan')
        spearman_rs.append(r)

        overlaps.append(overlap_pct)
        all_bull_picks.extend(bull_top15)
        all_bear_picks.extend(bear_top15)

        # Show differences
        bull_only = bull_set - bear_set
        bear_only = bear_set - bull_set

        date_label = history_prices.index[-1].date()
        print(f"  Window {i} ({date_label}) regime={regime:5s}  overlap={overlap_pct:.0f}%  r={r:+.3f}")
        if bull_only:
            print(f"    Bull only ({len(bull_only)}): {', '.join(sorted(bull_only)[:5])}")
        if bear_only:
            print(f"    Bear only ({len(bear_only)}): {', '.join(sorted(bear_only)[:5])}")

    # ---- Summary ----
    print()
    print("=" * 60)
    print("  汇总")
    print("=" * 60)
    mean_overlap = np.mean(overlaps)
    mean_r = np.nanmean(spearman_rs)
    bull_unique = len(set(all_bull_picks) - set(all_bear_picks))
    bear_unique = len(set(all_bear_picks) - set(all_bull_picks))

    print(f"  平均 Overlap: {mean_overlap:.0f}% ({15 - mean_overlap/100*15:.0f}/15 只不同)")
    print(f"  平均 Spearman r: {mean_r:.3f}")
    print(f"  Bull 独有股: {bull_unique} 只")
    print(f"  Bear 独有股: {bear_unique} 只")
    print(f"  窗口明细 Overlap: {[f'{o:.0f}%' for o in overlaps]}")

    # Verdict
    print()
    if mean_overlap < 50:
        print("  [OK] overlap < 50% — Bull 和 Bear 确实在做不同的判断")
        print("  建议: 正式实现 Bull/Bear 独立 FactorConfig")
    elif mean_overlap < 70:
        print("  [MAYBE] overlap 50-70% — 有一定差异化，但不够显著")
        print("  建议: 考虑加大权重差异后重测")
    else:
        print("  [SKIP] overlap > 70% — 两套权重选股高度重合，差异化不足")
        print("  建议: 放弃方向 7，Bull/Bear 差异应在分析逻辑层面体现（非权重层面）")


if __name__ == "__main__":
    main()
