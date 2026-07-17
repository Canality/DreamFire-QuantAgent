#!/usr/bin/env python3
"""
Quant Investment Pipeline — Direct execution script (development/testing).

This script runs the full pipeline directly through jiuwenswarm.quant,
bypassing the Agent layer. Use this for fast strategy iteration and testing.

For production Agent execution, use:
    jiuwenswarm-app          # start the framework
    jiuwenswarm chat          # interact with the agent

The Agent will auto-discover the quant-investment skill and call
the 6 quant_xxx tools through the QuantFinanceExtension.
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from jiuwenswarm.quant.stock_pool import ALL_STOCKS, SECTOR_MAP, TICKER_NAME_MAP
from jiuwenswarm.quant.factors import FactorCalculator, FactorConfig, PositionSizer, PositionConfig
from jiuwenswarm.quant.backtest_engine import BacktestEngine
from jiuwenswarm.quant.market_regime import MarketRegime


def fetch_data(tickers, start_date, end_date):
    """Fetch real stock data. Tries yfinance first, then akshare. Exits if both fail."""
    prices = {}
    volumes = {}
    errors = []

    # Try yfinance
    yf_ok = False
    try:
        import yfinance as yf
        print(f"[Data] Fetching {len(tickers)} stocks via yfinance...")
        for t in tickers:
            yt = t.replace(".SH", ".SS").replace(".SZ", ".SZ")
            try:
                df = yf.download(yt, start=start_date, end=end_date,
                                 progress=False, auto_adjust=True)
                if df is not None and not df.empty:
                    if isinstance(df.columns, pd.MultiIndex):
                        prices[t] = df["Close"].iloc[:, 0]
                        vol_col = df.get("Volume")
                        if vol_col is not None:
                            volumes[t] = vol_col.iloc[:, 0] if isinstance(vol_col, pd.DataFrame) else vol_col
                    else:
                        prices[t] = df["Close"]
                        volumes[t] = df.get("Volume", pd.Series(dtype=float))
            except Exception as e:
                errors.append(f"yfinance:{t}: {e}")
        yf_ok = len(prices) > 0
        if yf_ok:
            print(f"  yfinance: {len(prices)}/{len(tickers)} stocks fetched")
        else:
            print("  yfinance returned no data")
    except ImportError:
        errors.append("yfinance not installed. Run: pip install yfinance")
        print("  yfinance not installed")

    # Try akshare if yfinance failed
    if not yf_ok:
        ak_ok = False
        try:
            import akshare as ak
            print(f"[Data] Fetching {len(tickers)} stocks via akshare...")
            for t in tickers:
                code = t.replace(".SH", "").replace(".SZ", "")
                try:
                    df = ak.stock_zh_a_hist(
                        symbol=code, period="daily",
                        start_date=start_date.replace("-", ""),
                        end_date=end_date.replace("-", ""),
                        adjust="qfq",
                    )
                    if df is not None and not df.empty:
                        df["日期"] = pd.to_datetime(df["日期"])
                        df = df.set_index("日期")
                        prices[t] = df["收盘"]
                        volumes[t] = df.get("成交量", pd.Series(dtype=float))
                except Exception as e:
                    errors.append(f"akshare:{t}: {e}")
            ak_ok = len(prices) > 0
            if ak_ok:
                print(f"  akshare: {len(prices)}/{len(tickers)} stocks fetched")
            else:
                print("  akshare returned no data")
        except ImportError:
            errors.append("akshare not installed. Run: pip install akshare")
            print("  akshare not installed")

    if not prices:
        print("\n" + "=" * 60)
        print("ERROR: 无法获取真实股票数据。两个数据源均失败:")
        print("=" * 60)
        for e in errors:
            print(f"  - {e}")
        print("\n解决方案:")
        print("  1. pip install yfinance akshare")
        print("  2. 检查网络连接（yfinance需要访问Yahoo Finance, akshare需要访问东方财富）")
        print("  3. 内网环境需配置代理: set HTTPS_PROXY=http://your-proxy:port")
        print("=" * 60)
        sys.exit(1)

    return pd.DataFrame(prices).sort_index(), pd.DataFrame(volumes).sort_index()


def select_stocks(scores, top_n=15):
    """Sector-diversified stock selection."""
    from jiuwenswarm.quant.stock_pool import STOCK_POOL
    selected = []
    selected_set = set()

    # 1 per sector
    for sector in STOCK_POOL:
        sector_stocks = set(STOCK_POOL[sector])
        for t in scores.index:
            if t in sector_stocks and t not in selected_set:
                if scores.loc[t, "composite"] > -0.5:
                    selected.append(t)
                    selected_set.add(t)
                break

    # Fill remaining
    for t in scores.index:
        if len(selected) >= top_n:
            break
        if t not in selected_set and scores.loc[t, "composite"] > 0:
            selected.append(t)
            selected_set.add(t)

    return selected[:top_n]


def main():
    start_date = (datetime.now() - timedelta(days=180)).strftime("%Y-%m-%d")
    end_date = datetime.now().strftime("%Y-%m-%d")

    print("=" * 60)
    print("  Quant Investment Pipeline (JiuwenSwarm Native)")
    print(f"  Period: {start_date} → {end_date}")
    print("=" * 60)

    # Step 1: Data
    print("\n[1/6] Fetching data...")
    prices_df, volumes_df = fetch_data(ALL_STOCKS, start_date, end_date)
    print(f"  {len(prices_df.columns)} stocks, {len(prices_df)} days")

    # Step 2: Factors
    print("\n[2/6] Computing factors...")
    regime = MarketRegime.detect(prices_df)
    print(f"  Market Regime: {regime.upper()}")
    calc = FactorCalculator(FactorConfig())
    calc.regime = regime
    factors = calc.compute_factors(prices_df, volumes_df)
    scores = calc.compute_scores(factors)
    for t in scores.head(10).index:
        print(f"  {t} {TICKER_NAME_MAP.get(t, '?'):<8s} | {scores.loc[t, 'composite']:+.3f} | {scores.loc[t, 'sector']}")

    # Step 3: Selection
    print("\n[3/6] Selecting stocks...")
    tickers = select_stocks(scores)
    print(f"  {len(tickers)} stocks from {len(set(SECTOR_MAP.get(t) for t in tickers))} sectors")

    # Step 4: Position sizing
    print("\n[4/6] Allocating positions...")
    sizer = PositionSizer(PositionConfig())
    weights = sizer.allocate(scores, prices_df)
    for t, w in weights.items():
        print(f"  {t} {TICKER_NAME_MAP.get(t, '?'):<8s} | {w*100:5.1f}% | {SECTOR_MAP.get(t, '?')}")

    # Step 5: Backtest
    print("\n[5/6] Running backtest...")
    engine = BacktestEngine()
    bt = engine.run(prices_df, weights)
    print(f"  Total Return: {bt.total_return*100:+.2f}%")
    print(f"  Ann. Return:  {bt.annualized_return*100:+.2f}%")
    print(f"  Max DD:       {bt.max_drawdown*100:.2f}%")
    print(f"  Sharpe:       {bt.sharpe_ratio:.2f}")
    print(f"  Volatility:   {bt.volatility*100:.2f}%")
    print(f"  Win Rate:     {bt.win_rate*100:.1f}%")

    # Step 6: Output
    print("\n[6/6] Saving results...")
    output_dir = Path(__file__).resolve().parent.parent.parent / "output"
    output_dir.mkdir(exist_ok=True)

    portfolio = []
    for t, w in weights.items():
        portfolio.append({
            "ticker": t,
            "name": TICKER_NAME_MAP.get(t, t),
            "weight": round(w, 4),
            "weight_pct": round(w * 100, 2),
            "sector": SECTOR_MAP.get(t, "?"),
        })

    results = {
        "regime": regime,
        "portfolio": portfolio,
        "backtest": bt.metrics,
        "top_stocks": [
            {"ticker": t, "name": TICKER_NAME_MAP.get(t, t),
             "composite": round(float(scores.loc[t, "composite"]), 3),
             "sector": str(scores.loc[t, "sector"])}
            for t in scores.head(15).index
        ],
    }

    with open(output_dir / "pipeline_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=str)

    print(f"  Results saved to {output_dir / 'pipeline_results.json'}")
    print("\nDone.")


if __name__ == "__main__":
    main()
