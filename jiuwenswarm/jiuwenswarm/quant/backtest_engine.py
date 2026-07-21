"""
Backtest Engine for evaluating quantitative strategies on A-share data.

Computes: cumulative return, max drawdown, Sharpe ratio, win rate,
          and daily portfolio NAV series.
"""

from dataclasses import dataclass
from typing import Dict, Optional

import numpy as np
import pandas as pd


@dataclass
class BacktestResult:
    """Container for backtest results."""
    total_return: float
    annualized_return: float
    max_drawdown: float
    sharpe_ratio: float
    volatility: float
    win_rate: float
    start_value: float
    end_value: float
    nav_series: pd.Series
    daily_returns: pd.Series
    individual_returns: pd.DataFrame
    metrics: Dict[str, float]


class BacktestEngine:
    """Simple vectorized backtest engine."""

    def __init__(self, initial_capital: float = 1_000_000.0,
                 transaction_cost: float = 0.0003):
        self.initial_capital = initial_capital
        self.transaction_cost = transaction_cost

    def run(self, price_data: pd.DataFrame,
            weights: Dict[str, float],
            start_date: Optional[str] = None,
            end_date: Optional[str] = None) -> BacktestResult:
        """Run vectorized backtest."""
        if start_date:
            price_data = price_data[price_data.index >= start_date]
        if end_date:
            price_data = price_data[price_data.index <= end_date]

        if price_data.empty:
            raise ValueError("No price data available for the specified period.")

        available = [t for t in weights if t in price_data.columns]
        if not available:
            raise ValueError("None of the portfolio stocks are in price data.")

        active_weights = {t: weights[t] for t in available}
        # Do NOT renormalize — PositionSizer outputs weights that already
        # respect cash reserve and sector/single-stock caps. Renormalizing
        # would erase the cash buffer and amplify capped positions.
        w_sum = sum(active_weights.values())
        if w_sum <= 0:
            raise ValueError("No valid weights after filtering available stocks.")

        daily_returns_all = price_data[available].pct_change().dropna()
        if daily_returns_all.empty:
            raise ValueError("Not enough price data points.")

        cost = self.transaction_cost
        portfolio_returns = pd.Series(0.0, index=daily_returns_all.index)

        for ticker, weight in active_weights.items():
            portfolio_returns += daily_returns_all[ticker].fillna(0) * weight

        portfolio_returns.iloc[0] -= cost * sum(active_weights.values())

        nav = (1 + portfolio_returns).cumprod()
        nav = nav * self.initial_capital

        # total_return uses initial_capital as denominator so first-day
        # return and transaction cost are properly included
        total_ret = nav.iloc[-1] / self.initial_capital - 1
        n_days = len(portfolio_returns)
        ann_ret = (1 + total_ret) ** (252 / max(n_days, 1)) - 1
        ann_vol = portfolio_returns.std() * np.sqrt(252)
        sharpe = ann_ret / max(ann_vol, 1e-10)

        # Prepend initial NAV so drawdown sequence includes the starting point
        nav_full = pd.concat([
            pd.Series([self.initial_capital],
                       index=[nav.index[0] - pd.Timedelta(days=1)]),
            nav
        ])
        cummax = nav_full.cummax()
        drawdowns = (nav_full - cummax) / cummax
        max_dd = abs(drawdowns.min())

        win_rate = (portfolio_returns > 0).sum() / max(len(portfolio_returns), 1)

        metrics = {
            "total_return": round(total_ret, 6),
            "annualized_return": round(ann_ret, 6),
            "max_drawdown": round(max_dd, 6),
            "sharpe_ratio": round(sharpe, 4),
            "annualized_volatility": round(ann_vol, 6),
            "win_rate": round(win_rate, 4),
            "n_trading_days": n_days,
            "n_stocks_held": len(available),
        }

        return BacktestResult(
            total_return=total_ret,
            annualized_return=ann_ret,
            max_drawdown=max_dd,
            sharpe_ratio=sharpe,
            volatility=ann_vol,
            win_rate=win_rate,
            start_value=self.initial_capital,
            end_value=nav.iloc[-1],
            nav_series=nav,
            daily_returns=portfolio_returns,
            individual_returns=daily_returns_all,
            metrics=metrics,
        )
