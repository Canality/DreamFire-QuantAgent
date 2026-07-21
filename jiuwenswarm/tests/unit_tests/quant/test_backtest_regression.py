"""Regression tests for backtest first-day return and transaction cost.

Codex minimal reproduction:
  - 50% position, first day +10%  → actual portfolio +5%  (old code: 0%)
  - 50% position, cost 1%         → actual portfolio -0.5% (old code: 0%)
  - Two days +10% each            → actual +10.25%         (old code: +5%)
"""

import pandas as pd
import numpy as np
from jiuwenswarm.quant.backtest_engine import BacktestEngine


def _make_prices(ticker_returns):
    """Build a price DataFrame from per-day returns for one ticker."""
    prices = [100.0]
    for r in ticker_returns:
        prices.append(prices[-1] * (1 + r))
    dates = pd.date_range("2026-01-05", periods=len(prices), freq="B")
    return pd.DataFrame({"TEST": prices}, index=dates)


def test_first_day_return_included():
    """50% position, first day +10% → total_return = +5%."""
    prices = _make_prices([0.10])  # 1 day: 100 → 110
    weights = {"TEST": 0.50}
    bt = BacktestEngine(transaction_cost=0.0)
    result = bt.run(prices, weights)
    assert abs(result.total_return - 0.05) < 0.001, (
        f"Expected +5%%, got {result.total_return*100:.2f}%%"
    )


def test_transaction_cost_not_excluded():
    """50% position, cost 1%, first day flat → total_return ≈ -0.5%."""
    prices = _make_prices([0.0])  # 1 day: no change
    weights = {"TEST": 0.50}
    bt = BacktestEngine(transaction_cost=0.01)
    result = bt.run(prices, weights)
    # cost on 50% position = 0.5% of portfolio
    expected = -0.005
    assert abs(result.total_return - expected) < 0.001, (
        f"Expected {expected*100:.1f}%%, got {result.total_return*100:.2f}%%"
    )


def test_two_day_compound():
    """50% position, +10% two days → +10.25%."""
    prices = _make_prices([0.10, 0.10])  # 100 → 110 → 121
    weights = {"TEST": 0.50}
    bt = BacktestEngine(transaction_cost=0.0)
    result = bt.run(prices, weights)
    # Day 1: 50% * 10% = +5%, nav = 1.05
    # Day 2: 50% * 10% = +5%, nav = 1.05 * 1.05 = 1.1025
    # total_return = 10.25%
    assert abs(result.total_return - 0.1025) < 0.001, (
        f"Expected +10.25%%, got {result.total_return*100:.2f}%%"
    )


def test_drawdown_includes_initial_point():
    """Drawdown captures decline from initial capital, not just from nav[0]."""
    prices = _make_prices([-0.05])  # one day, -5%
    weights = {"TEST": 1.0}
    bt = BacktestEngine(transaction_cost=0.0)
    result = bt.run(prices, weights)
    # full position drops 5% on day 1 → drawdown should be ~5%
    assert result.max_drawdown > 0.04, (
        f"Expected drawdown ~5%%, got {result.max_drawdown*100:.2f}%%"
    )
