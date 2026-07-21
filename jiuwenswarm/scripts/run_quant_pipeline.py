#!/usr/bin/env python3
"""Direct, fail-closed validation path for the quant investment pipeline."""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from jiuwenswarm.quant.backtest_engine import BacktestEngine
from jiuwenswarm.quant.factors import FactorCalculator, PositionSizer
from jiuwenswarm.quant.market_regime import MarketRegime
from jiuwenswarm.quant.stock_pool import ALL_STOCKS, SECTOR_MAP, TICKER_NAME_MAP
from jiuwenswarm.quant.strategy_configs import (
    production_factor_config,
    production_position_config,
)


def _load_data_provider():
    extension_path = (
        Path(__file__).resolve().parent.parent
        / "jiuwenswarm" / "extensions" / "quant-finance" / "extension.py"
    )
    spec = importlib.util.spec_from_file_location("quant_finance_extension", extension_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load quant data provider: {extension_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fetch_data(tickers: list[str], start_date: str, end_date: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Use the Extension's five-source missing-only fallback chain."""
    provider = _load_data_provider()
    prices, volumes, errors = provider._fetch_real_data(tickers, start_date, end_date)
    missing = [
        ticker for ticker in tickers
        if not provider._ticker_data_usable(prices, volumes, ticker)
    ]
    if missing:
        details = "\n".join(f"  - {error}" for error in errors[-20:])
        raise RuntimeError(
            f"Real-data coverage failed: {len(prices)}/{len(tickers)}; missing {missing}.\n{details}"
        )
    prices_df = pd.DataFrame(prices).sort_index().reindex(columns=tickers)
    volumes_df = pd.DataFrame(volumes).sort_index().reindex(columns=tickers)
    print(f"  Missing-only fallback complete: {len(prices_df.columns)}/{len(tickers)} stocks")
    print(f"  Coverage evidence: {len(prices_df.columns)} stocks, {len(prices_df)} days")
    print(f"  Provider coverage: {provider._last_fetch_provider_stats}")
    return prices_df, volumes_df


def select_stocks(scores: pd.DataFrame, top_n: int = 15) -> list[str]:
    """Select exactly top_n positive-score stocks."""
    selected = [
        ticker for ticker in scores.index
        if float(scores.loc[ticker, "composite"]) > 0
    ][:top_n]
    return selected


def _validate_weights(weights: dict[str, float]) -> dict[str, float]:
    sector_totals: dict[str, float] = {}
    for ticker, weight in weights.items():
        if weight > 0.10 + 1e-9:
            raise RuntimeError(f"Single-stock cap exceeded: {ticker}={weight:.4f}")
        sector = SECTOR_MAP[ticker]
        sector_totals[sector] = sector_totals.get(sector, 0.0) + weight
    over_cap = {sector: value for sector, value in sector_totals.items() if value > 0.25 + 1e-9}
    if over_cap:
        raise RuntimeError(f"Sector cap exceeded: {over_cap}")
    if 1.0 - sum(weights.values()) < 0.05 - 1e-9:
        raise RuntimeError("Cash reserve is below 5%")
    return sector_totals


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=240)).strftime("%Y-%m-%d")
    print("=" * 60)
    print("  Quant Investment Pipeline (direct validation path)")
    print(f"  Requested data: {start_date} -> {end_date}")
    print("=" * 60)

    print("\n[1/6] Fetching data...")
    prices_full, volumes_full = fetch_data(ALL_STOCKS, start_date, end_date)
    if list(prices_full.columns) != list(ALL_STOCKS):
        raise RuntimeError("Data columns do not exactly match the 49-stock competition pool")
    if len(prices_full) < 81:
        raise RuntimeError(f"Insufficient trading days: {len(prices_full)} < 81")

    split_at = len(prices_full) - 20
    prices_train = prices_full.iloc[:split_at]
    prices_test = prices_full.iloc[split_at - 1:]
    volumes_train = volumes_full.reindex(prices_train.index) if not volumes_full.empty else pd.DataFrame()
    train_start = prices_train.index[0].strftime("%Y-%m-%d")
    train_end = prices_train.index[-1].strftime("%Y-%m-%d")
    test_start = prices_test.index[0].strftime("%Y-%m-%d")
    test_end = prices_test.index[-1].strftime("%Y-%m-%d")
    print(f"  Train: {train_start} -> {train_end} ({len(prices_train)} trading days)")
    print(f"  Test:  {test_start} -> {test_end} (20 forward returns)")

    print("\n[2/6] Computing factors on training data...")
    regime = MarketRegime.detect(prices_train)
    calculator = FactorCalculator(production_factor_config())
    calculator.regime = regime
    factors = calculator.compute_factors(prices_train, volumes_train if not volumes_train.empty else None)
    scores = calculator.compute_scores(factors)
    print(f"  Market regime: {regime.upper()}; analyzed {len(scores)} stocks")

    print("\n[3/6] Selecting stocks...")
    tickers = select_stocks(scores)
    sectors_covered = len({SECTOR_MAP[ticker] for ticker in tickers})
    if len(tickers) != 15 or sectors_covered != 6:
        raise RuntimeError(f"Selection coverage failed: {len(tickers)}/15 stocks, {sectors_covered}/6 sectors")
    print(f"  {len(tickers)} stocks from {sectors_covered} sectors")

    print("\n[4/6] Allocating positions...")
    weights = PositionSizer(production_position_config()).allocate(
        scores.loc[tickers], prices_train[tickers]
    )
    if set(weights) != set(tickers):
        raise RuntimeError(f"Selection/allocation mismatch: selected={tickers}, allocated={list(weights)}")
    sector_totals = _validate_weights(weights)
    print(f"  {len(weights)} holdings; cash reserve {(1 - sum(weights.values())) * 100:.2f}%")

    print("\n[5/6] Running forward backtest...")
    backtest = BacktestEngine().run(prices_test, weights)
    print(f"  Total return: {backtest.total_return * 100:+.2f}%")
    print(f"  Max drawdown: {backtest.max_drawdown * 100:.2f}%")
    print(f"  Sharpe: {backtest.sharpe_ratio:.2f}")

    print("\n[6/6] Saving results...")
    output_dir = Path(__file__).resolve().parent.parent.parent / "output"
    output_dir.mkdir(exist_ok=True)
    results = {
        "regime": regime,
        "train_period": f"{train_start} -> {train_end}",
        "test_period": f"{test_start} -> {test_end}",
        "n_train_trading_days": len(prices_train),
        "n_forward_returns": len(prices_test) - 1,
        "n_stocks_fetched": len(prices_full.columns),
        "data_source_chain": "sina -> tencent -> akshare -> baostock -> yfinance",
        "n_stocks_selected": len(tickers),
        "n_sectors_covered": sectors_covered,
        "sector_weights": {sector: round(weight, 4) for sector, weight in sector_totals.items()},
        "portfolio": [
            {
                "ticker": ticker,
                "name": TICKER_NAME_MAP.get(ticker, ticker),
                "weight": round(weight, 4),
                "weight_pct": round(weight * 100, 2),
                "sector": SECTOR_MAP[ticker],
            }
            for ticker, weight in weights.items()
        ],
        "backtest": backtest.metrics,
        "top_stocks": [
            {
                "ticker": ticker,
                "name": TICKER_NAME_MAP.get(ticker, ticker),
                "composite": round(float(scores.loc[ticker, "composite"]), 3),
                "sector": str(scores.loc[ticker, "sector"]),
            }
            for ticker in scores.head(15).index
        ],
    }
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    timestamped_path = output_dir / f"pipeline_results_{run_id}.json"
    for path in (timestamped_path, output_dir / "pipeline_results.json"):
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(results, handle, ensure_ascii=False, indent=2, default=str)
    print(f"  Results saved to {timestamped_path}")
    print("\nDone.")


if __name__ == "__main__":
    main()
