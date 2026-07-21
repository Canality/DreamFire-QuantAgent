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

    def run_open_to_close(
        self,
        entry_open: pd.Series,
        close_data: pd.DataFrame,
        weights: Dict[str, float],
    ) -> BacktestResult:
        """Buy once at the first-day open and value fixed shares at each close.

        This matches the competition protocol.  It intentionally differs from
        :meth:`run`, whose weighted daily-return calculation behaves like a
        daily-rebalanced portfolio.
        """
        if close_data.empty:
            raise ValueError("No close data available for the holding period.")

        available = [ticker for ticker in weights if ticker in close_data.columns]
        if set(available) != set(weights):
            missing = sorted(set(weights) - set(available))
            raise ValueError(f"Portfolio tickers missing from close data: {missing}")

        opens = pd.to_numeric(entry_open.reindex(available), errors="coerce")
        invalid_open = opens.index[opens.isna() | (opens <= 0)].tolist()
        if invalid_open:
            raise ValueError(f"Missing or invalid first-day open: {invalid_open}")

        closes = close_data[available].apply(pd.to_numeric, errors="coerce")
        # During a suspension the latest observable close remains the position's
        # valuation.  Seed from entry open so the first close is always defined.
        seeded = pd.concat([
            pd.DataFrame([opens], index=[close_data.index[0] - pd.Timedelta(microseconds=1)]),
            closes,
        ]).ffill()
        closes = seeded.iloc[1:]
        if closes.isna().any().any() or (closes <= 0).any().any():
            bad = closes.columns[closes.isna().any() | (closes <= 0).any()].tolist()
            raise ValueError(f"Missing or invalid holding-period close: {bad}")

        active_weights = pd.Series({ticker: float(weights[ticker]) for ticker in available})
        total_weight = float(active_weights.sum())
        if total_weight <= 0 or total_weight > 1.0 + 1e-9:
            raise ValueError(f"Invalid total portfolio weight: {total_weight}")

        invested = self.initial_capital * active_weights
        shares = invested / opens
        transaction_fee = self.transaction_cost * float(invested.sum())
        cash = self.initial_capital - float(invested.sum()) - transaction_fee
        nav = closes.mul(shares, axis=1).sum(axis=1) + cash

        initial_nav = pd.Series(
            [self.initial_capital],
            index=[close_data.index[0] - pd.Timedelta(microseconds=1)],
        )
        nav_full = pd.concat([initial_nav, nav])
        daily_returns = nav_full.pct_change().iloc[1:]
        total_ret = float(nav.iloc[-1] / self.initial_capital - 1.0)
        n_days = len(nav)
        ann_ret = (1 + total_ret) ** (252 / max(n_days, 1)) - 1
        ann_vol = float(daily_returns.std() * np.sqrt(252))
        sharpe = ann_ret / max(ann_vol, 1e-10)
        drawdowns = (nav_full - nav_full.cummax()) / nav_full.cummax()
        max_dd = float(abs(drawdowns.min()))
        win_rate = float((daily_returns > 0).sum() / max(len(daily_returns), 1))

        individual_path = pd.concat([
            pd.DataFrame([opens], index=[initial_nav.index[0]]),
            closes,
        ])
        individual_returns = individual_path.pct_change().iloc[1:]
        metrics = {
            "total_return": round(total_ret, 6),
            "annualized_return": round(ann_ret, 6),
            "max_drawdown": round(max_dd, 6),
            "sharpe_ratio": round(sharpe, 4),
            "annualized_volatility": round(ann_vol, 6),
            "win_rate": round(win_rate, 4),
            "n_trading_days": n_days,
            "n_stocks_held": len(available),
            "valuation_method": "first_open_fixed_shares_daily_close",
        }
        return BacktestResult(
            total_return=total_ret,
            annualized_return=ann_ret,
            max_drawdown=max_dd,
            sharpe_ratio=sharpe,
            volatility=ann_vol,
            win_rate=win_rate,
            start_value=self.initial_capital,
            end_value=float(nav.iloc[-1]),
            nav_series=nav,
            daily_returns=daily_returns,
            individual_returns=individual_returns,
            metrics=metrics,
        )
