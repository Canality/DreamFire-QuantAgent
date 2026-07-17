"""Market regime detection for dynamic factor weight adjustment.

Uses volatility-normalized thresholds so that the same signal strength
(e.g. "2 standard deviations away from MA60") has consistent meaning
across high-vol and low-vol environments.
"""

import numpy as np
import pandas as pd


class MarketRegime:
    """Detect market regime from index-level price data.

    Regime is determined by two volatility-normalized metrics:
      - price_sigma: current price deviation from long-term MA, in units
        of daily return standard deviation
      - slope_sigma: short-term vs long-term MA slope, in same units

    Both must exceed their respective thresholds for a BULL or BEAR call.
    """

    BULL = "bull"
    BEAR = "bear"
    RANGE = "range"

    # --- Volatility-normalized thresholds ---
    # Price deviation from MA must exceed this many daily-return std devs.
    BULL_PRICE_SIGMA: float = 2.0
    BULL_SLOPE_SIGMA: float = 0.5
    BEAR_PRICE_SIGMA: float = 2.0
    BEAR_SLOPE_SIGMA: float = 0.5

    # Lookback window for computing the normalisation volatility.
    VOL_LOOKBACK: int = 20

    @staticmethod
    def detect(price_data: pd.DataFrame, lookback: int = 60) -> str:
        """Classify regime using long-term MA position, short-term MA slope,
        and volatility-normalized thresholds.

        Args:
            price_data: DataFrame of Close prices, columns = tickers.
            lookback: window for the long-term moving average (default 60).

        Returns:
            'bull', 'bear', or 'range'.
        """
        if price_data.empty:
            return MarketRegime.RANGE

        # Cross-sectional mean as the "market" price series
        market = price_data.mean(axis=1)
        if len(market) < lookback:
            return MarketRegime.RANGE

        ma_long = market.rolling(lookback).mean().iloc[-1]
        ma_short = market.rolling(20).mean().iloc[-1]
        current = market.iloc[-1]

        # Raw percentage metrics (unchanged)
        price_vs_ma = (current - ma_long) / ma_long
        ma_slope = (ma_short - ma_long) / ma_long

        # --- Volatility-normalized thresholds ---
        ret = market.pct_change().tail(MarketRegime.VOL_LOOKBACK)
        vol_daily = ret.std()

        # Guard: insufficient or zero volatility → cannot normalise
        if vol_daily == 0 or pd.isna(vol_daily) or len(ret.dropna()) < 5:
            return MarketRegime.RANGE

        price_sigma = price_vs_ma / vol_daily
        slope_sigma = ma_slope / vol_daily

        # Minimum absolute deviation: 1% of price, or 1 daily std dev,
        # whichever is larger. Prevents false signals in ultra-low vol.
        min_abs = max(0.01, vol_daily * 1.0)

        if abs(price_vs_ma) >= min_abs:
            if price_sigma > MarketRegime.BULL_PRICE_SIGMA and slope_sigma > MarketRegime.BULL_SLOPE_SIGMA:
                return MarketRegime.BULL
            if price_sigma < -MarketRegime.BEAR_PRICE_SIGMA and slope_sigma < -MarketRegime.BEAR_SLOPE_SIGMA:
                return MarketRegime.BEAR

        return MarketRegime.RANGE
