"""Market regime detection for dynamic factor weight adjustment."""

import numpy as np
import pandas as pd


class MarketRegime:
    """Detect market regime from index-level price data."""

    BULL = "bull"
    BEAR = "bear"
    RANGE = "range"

    @staticmethod
    def detect(price_data: pd.DataFrame, lookback: int = 60) -> str:
        """
        Classify regime using 60d MA position and slope.
        Returns 'bull', 'bear', or 'range'.
        """
        if price_data.empty:
            return MarketRegime.RANGE

        market = price_data.mean(axis=1)
        if len(market) < lookback:
            return MarketRegime.RANGE

        ma_60 = market.rolling(lookback).mean().iloc[-1]
        ma_20 = market.rolling(20).mean().iloc[-1]
        current = market.iloc[-1]

        price_vs_ma = (current - ma_60) / ma_60
        ma_slope = (ma_20 - ma_60) / ma_60

        if price_vs_ma > 0.03 and ma_slope > 0.005:
            return MarketRegime.BULL
        elif price_vs_ma < -0.03 and ma_slope < -0.005:
            return MarketRegime.BEAR
        else:
            return MarketRegime.RANGE
