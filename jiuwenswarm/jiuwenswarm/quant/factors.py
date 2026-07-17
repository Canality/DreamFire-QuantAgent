"""
Multi-factor model: 8 factors across trend, counter-trend, and risk categories.
Includes sector-neutral Z-score normalization and regime-weighted composite scoring.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from jiuwenswarm.quant.market_regime import MarketRegime
from jiuwenswarm.quant.stock_pool import STOCK_POOL, SECTOR_MAP


@dataclass
class FactorConfig:
    """Weights for each factor. Supports regime-based dynamic weights.

    11 factors: 8 technical + 3 fundamental (PE, PB, ROE).
    """

    # Technical factor base weights
    w_momentum_20: float = 0.12
    w_momentum_60: float = 0.08
    w_turnover_mom: float = 0.06
    w_reversal_5: float = 0.14
    w_rsi: float = 0.07
    w_volatility: float = 0.12
    w_volume_trend: float = 0.08
    w_max_drawdown: float = 0.12

    # Fundamental factor base weights
    w_pe_ttm: float = 0.07
    w_pb_mrq: float = 0.07
    w_roe: float = 0.07

    def get_regime_weights(self, regime: str) -> Dict[str, float]:
        """Return factor weights adjusted for market regime."""
        base = {
            "momentum_20_z": self.w_momentum_20,
            "momentum_60_z": self.w_momentum_60,
            "turnover_momentum_z": self.w_turnover_mom,
            "reversal_5_z": self.w_reversal_5,
            "rsi_z": self.w_rsi,
            "volatility_z": -self.w_volatility,
            "volume_trend_z": self.w_volume_trend,
            "max_drawdown_z": -self.w_max_drawdown,
            "pe_ttm_z": self.w_pe_ttm,
            "pb_mrq_z": self.w_pb_mrq,
            "roe_z": self.w_roe,
        }

        if regime == MarketRegime.BULL:
            adjustments = {
                "momentum_20_z": 1.5, "momentum_60_z": 1.5,
                "turnover_momentum_z": 1.3,
                "reversal_5_z": 0.3, "rsi_z": 0.5,
                "volatility_z": 0.7, "max_drawdown_z": 0.7,
                "pe_ttm_z": 0.7, "pb_mrq_z": 0.7, "roe_z": 1.2,
            }
        elif regime == MarketRegime.BEAR:
            adjustments = {
                "momentum_20_z": 0.3, "momentum_60_z": 0.3,
                "turnover_momentum_z": 0.5,
                "reversal_5_z": 1.5, "rsi_z": 1.3,
                "volatility_z": 1.5, "max_drawdown_z": 2.0,
                "volume_trend_z": 0.5,
                "pe_ttm_z": 1.5, "pb_mrq_z": 1.5, "roe_z": 1.5,
            }
        else:  # RANGE
            adjustments = {
                "momentum_20_z": 0.8, "momentum_60_z": 0.7,
                "reversal_5_z": 1.3, "rsi_z": 1.1,
                "volatility_z": 1.1, "max_drawdown_z": 1.0,
                "pe_ttm_z": 1.2, "pb_mrq_z": 1.2, "roe_z": 1.1,
            }

        result = {}
        for k, v in base.items():
            adj = adjustments.get(k, 1.0)
            result[k] = v * adj
        return result


@dataclass
class PositionConfig:
    max_single_stock: float = 0.10
    max_single_sector: float = 0.25
    min_cash: float = 0.05
    max_drawdown_exit: float = 0.15
    top_n_stocks: int = 15


@dataclass
class StrategyResult:
    selected_stocks: Dict[str, float]
    all_scores: pd.DataFrame
    metrics: Dict[str, float]
    report_sections: Dict[str, str] = field(default_factory=dict)


class FactorCalculator:
    """Calculate multi-factor scores with market regime awareness."""

    def __init__(self, config: Optional[FactorConfig] = None):
        self.config = config or FactorConfig()
        self.regime = MarketRegime.RANGE

    def compute_factors(self, price_data: pd.DataFrame,
                        volume_data: Optional[pd.DataFrame] = None) -> pd.DataFrame:
        """Compute all 8 factor values for each stock."""
        returns = price_data.pct_change()
        factors = pd.DataFrame(index=price_data.columns)
        factors.index.name = "ticker"

        # --- Trend Factors ---

        if len(price_data) >= 21:
            mom_20 = price_data.iloc[-1] / price_data.iloc[-21] - 1
        else:
            mom_20 = price_data.iloc[-1] / price_data.iloc[0] - 1
        factors["momentum_20"] = mom_20.reindex(factors.index)

        if len(price_data) >= 61:
            mom_60 = price_data.iloc[-1] / price_data.iloc[-61] - 1
        else:
            mom_60 = price_data.iloc[-1] / price_data.iloc[0] - 1
        factors["momentum_60"] = mom_60.reindex(factors.index)

        vol_20 = returns.tail(20).std() * np.sqrt(252)
        factors["turnover_momentum"] = (
            factors["momentum_20"] / (vol_20.reindex(factors.index) + 0.01)
        )

        # --- Counter-Trend Factors ---

        if len(price_data) >= 6:
            rev_5 = -(price_data.iloc[-1] / price_data.iloc[-6] - 1)
        else:
            rev_5 = pd.Series(0.0, index=factors.index)
        factors["reversal_5"] = rev_5.reindex(factors.index)

        factors["rsi"] = self._calc_rsi(price_data, period=14)

        # --- Risk Factors ---

        factors["volatility"] = vol_20.reindex(factors.index)

        if volume_data is not None and not volume_data.empty:
            v5 = volume_data.tail(5).mean()
            v20 = volume_data.tail(20).mean().replace(0, np.nan)
            factors["volume_trend"] = (v5 / v20).reindex(factors.index)
        else:
            factors["volume_trend"] = 1.0

        max_dd = self._calc_max_drawdown(price_data.tail(60))
        factors["max_drawdown"] = pd.Series(max_dd, index=factors.index)

        return factors

    def compute_scores(
        self,
        factors: pd.DataFrame,
        fundamental_z: Optional[pd.DataFrame] = None,
    ) -> pd.DataFrame:
        """Z-score normalize within sector, then regime-weighted composite.

        Args:
            factors: Raw technical factor values per stock.
            fundamental_z: Pre-computed fundamental Z-scores (PE, PB, ROE).
                           If None, only technical factors are used.
        """
        scores = factors.copy()

        # Z-score technical factors within each sector
        for col in factors.columns:
            col_scores = pd.Series(index=factors.index, dtype=float)
            for sector, stocks in STOCK_POOL.items():
                sector_stocks = [s for s in stocks if s in factors.index]
                if len(sector_stocks) < 2:
                    col_scores.loc[sector_stocks] = 0.0
                    continue
                raw = factors.loc[sector_stocks, col]
                z = (raw - raw.mean()) / (raw.std() + 1e-10)
                col_scores.loc[sector_stocks] = z
            scores[f"{col}_z"] = col_scores

        # Merge fundamental Z-scores if provided
        if fundamental_z is not None:
            for col in fundamental_z.columns:
                if col not in scores.columns:
                    scores[col] = 0.0
                for ticker in fundamental_z.index:
                    if ticker in scores.index:
                        scores.loc[ticker, col] = fundamental_z.loc[ticker, col]

        weights = self.config.get_regime_weights(self.regime)

        scores["composite"] = sum(
            scores[col].fillna(0) * wt for col, wt in weights.items()
        )
        scores["sector"] = scores.index.map(SECTOR_MAP)
        scores = scores.sort_values("composite", ascending=False)

        return scores

    @staticmethod
    def _calc_rsi(prices: pd.DataFrame, period: int = 14) -> pd.Series:
        result = {}
        for ticker in prices.columns:
            price = prices[ticker].dropna()
            if len(price) < period + 1:
                result[ticker] = 50.0
                continue
            delta = price.diff()
            gain = delta.clip(lower=0)
            loss = (-delta).clip(lower=0)
            avg_gain = gain.rolling(period).mean().iloc[-1]
            avg_loss = loss.rolling(period).mean().iloc[-1]
            if avg_loss == 0:
                result[ticker] = 100.0
            else:
                rs = avg_gain / avg_loss
                result[ticker] = 100.0 - (100.0 / (1.0 + rs))
        return pd.Series(result)

    @staticmethod
    def _calc_max_drawdown(prices: pd.DataFrame) -> dict:
        result = {}
        for ticker in prices.columns:
            cummax = prices[ticker].cummax()
            drawdown = (prices[ticker] - cummax) / cummax
            result[ticker] = abs(drawdown.min()) if not drawdown.empty else 0.0
        return result


class PositionSizer:
    """Risk-parity position sizing with constraints."""

    def __init__(self, config: Optional[PositionConfig] = None):
        self.config = config or PositionConfig()

    def allocate(self, scores: pd.DataFrame,
                 price_data: pd.DataFrame) -> Dict[str, float]:
        """Allocate positions using risk-parity among top-N stocks."""
        cfg = self.config
        top_n = scores.head(cfg.top_n_stocks)

        returns = price_data.tail(20).pct_change()
        vols = {}
        for ticker in top_n.index:
            if ticker in returns.columns:
                vols[ticker] = returns[ticker].std()
            else:
                vols[ticker] = 0.02

        inv_vol = {t: 1.0 / max(v, 0.005) for t, v in vols.items()}
        total_inv_vol = sum(inv_vol.values())
        raw_weights = {t: v / total_inv_vol for t, v in inv_vol.items()}

        weights = self._apply_constraints(raw_weights, top_n["sector"].to_dict(),
                                          scores["composite"].to_dict())
        return weights

    def _apply_constraints(self, raw_weights: Dict[str, float],
                           sectors: Dict[str, str],
                           scores: Dict[str, float]) -> Dict[str, float]:
        cfg = self.config
        weights = dict(raw_weights)

        for ticker in list(weights.keys()):
            if weights[ticker] > cfg.max_single_stock:
                excess = weights[ticker] - cfg.max_single_stock
                weights[ticker] = cfg.max_single_stock
                others = [t for t in weights if t != ticker]
                if others:
                    redist = excess / len(others)
                    for t in others:
                        weights[t] += redist

        sector_totals = {}
        for ticker, w in weights.items():
            sector = sectors.get(ticker, "其他")
            sector_totals[sector] = sector_totals.get(sector, 0.0) + w

        for sector, total in sector_totals.items():
            if total > cfg.max_single_sector:
                scale = cfg.max_single_sector / total
                for ticker in weights:
                    if sectors.get(ticker) == sector:
                        weights[ticker] *= scale

        target_sum = 1.0 - cfg.min_cash
        current_sum = sum(weights.values())
        if current_sum > 0:
            weights = {t: w / current_sum * target_sum for t, w in weights.items()}

        weights = {t: round(w, 4) for t, w in weights.items()}
        return dict(sorted(weights.items(), key=lambda x: x[1], reverse=True))
