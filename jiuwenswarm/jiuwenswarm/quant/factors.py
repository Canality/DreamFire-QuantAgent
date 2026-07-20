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
    """Weights for 5 alpha factors + 1 risk constraint.

    Factor selection based on IC analysis:
      - 5 alpha factors: momentum_20 (IC=+0.084), momentum_60 (IC=+0.055),
        reversal_5 (IC=-0.094), max_drawdown (IC=-0.114), volume_corr (IC=+0.049)
      - 1 risk constraint: volatility (excluded from composite, applied as
        hard filter in stock selection: vol_z > 2.0 → excluded)

    Weights are proportional to |IC|, with volume_corr up-weighted
    for its exceptional stability (Std IC=0.094, lowest of all factors).
    """

    # IC-weighted base weights (sum to 1.0)
    w_momentum_20: float = 0.34   # IC=+0.084 → largest weight
    w_momentum_60: float = 0.18   # IC=+0.055
    w_max_drawdown: float = 0.18  # IC=-0.114 (inverted: low drawdown = high score)
    w_reversal_5: float = 0.10    # IC=-0.094 (volatile → low weight)
    w_volume_corr: float = 0.20   # IC=+0.049 (lowest std → up-weighted for stability)

    # Volatility constraint (not a composite weight)
    vol_exclusion_sigma: float = 2.0  # exclude stocks with vol_z > 2.0

    def get_regime_weights(self, regime: str) -> Dict[str, float]:
        """Return factor weights adjusted for market regime.

        reversal_5_z is flipped: higher score = stronger 5-day momentum.
        volume_corr_z is regime-invariant (stable across all market states).
        """
        base = {
            "momentum_20_z": self.w_momentum_20,
            "momentum_60_z": self.w_momentum_60,
            "reversal_5_z": -self.w_reversal_5,
            "max_drawdown_z": -self.w_max_drawdown,
            "volume_corr_z": self.w_volume_corr,
        }

        if regime == MarketRegime.BULL:
            adjustments = {
                "momentum_20_z": 1.5, "momentum_60_z": 1.5,
                "reversal_5_z": 0.3,
                "max_drawdown_z": 0.7,
                "volume_corr_z": 1.0,  # regime-invariant
            }
        elif regime == MarketRegime.BEAR:
            adjustments = {
                "momentum_20_z": 0.3, "momentum_60_z": 0.3,
                "reversal_5_z": 1.5,
                "max_drawdown_z": 2.0,
                "volume_corr_z": 1.0,
            }
        else:  # RANGE
            adjustments = {
                "momentum_20_z": 0.8, "momentum_60_z": 0.7,
                "reversal_5_z": 1.3,
                "max_drawdown_z": 1.0,
                "volume_corr_z": 1.0,
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

            # Volume-price correlation: Spearman rank corr of 20d returns vs volume
            # Positive = volume confirms price direction (healthy trend)
            # Negative = volume diverges from price (trend weakness)
            returns = price_data.pct_change()
            vol_corr = {}
            for ticker in price_data.columns:
                if ticker not in volume_data.columns:
                    vol_corr[ticker] = 0.0
                    continue
                ret_20 = returns[ticker].tail(20).dropna()
                vol_20 = volume_data[ticker].tail(20).dropna()
                common_idx = ret_20.index.intersection(vol_20.index)
                if len(common_idx) < 10:
                    vol_corr[ticker] = 0.0
                    continue
                # Rank correlation: rank both series, then Pearson
                ra = ret_20[common_idx].rank()
                rb = vol_20[common_idx].rank()
                r = ra.corr(rb)
                vol_corr[ticker] = 0.0 if pd.isna(r) else float(r)
            factors["volume_corr"] = pd.Series(vol_corr, index=factors.index)
        else:
            factors["volume_trend"] = 1.0
            factors["volume_corr"] = 0.0

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
            scores[col].fillna(0) * wt
            for col, wt in weights.items()
            if col in scores.columns
        )
        scores["sector"] = scores.index.map(SECTOR_MAP)
        scores = scores.sort_values("composite", ascending=False)

        return scores

    def filter_high_volatility(
        self, scores: pd.DataFrame, max_sigma: float | None = None,
    ) -> pd.DataFrame:
        """Exclude stocks with excessive volatility (hard constraint).

        Unlike the composite score which uses soft penalty weights, this
        is a binary filter: stocks with vol_z > max_sigma are removed.
        This reduces drawdown risk without distorting alpha factor rankings.

        Args:
            scores: DataFrame from compute_scores() with 'volatility_z' column.
            max_sigma: Exclusion threshold. Defaults to config value (2.0).

        Returns:
            scores with high-vol stocks removed.
        """
        if "volatility_z" not in scores.columns:
            return scores
        threshold = max_sigma if max_sigma is not None else self.config.vol_exclusion_sigma
        keep = scores["volatility_z"].fillna(0) <= threshold
        excluded = (~keep).sum()
        if excluded > 0:
            import logging
            logging.getLogger(__name__).debug(
                "[FactorCalc] Vol constraint excluded %d/%d stocks (vol_z > %.1f)",
                excluded, len(scores), threshold,
            )
        return scores[keep]

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
