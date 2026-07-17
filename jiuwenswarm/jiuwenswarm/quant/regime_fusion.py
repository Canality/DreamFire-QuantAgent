"""Multi-signal regime fusion.

Combines independent market regime signals via weighted voting:
  - S_tech:  technical (stock-pool average, vol-normalized)
  - S_index: macro (CSI 300 index)

When signals agree, the consensus is returned. When they disagree,
a conservative 'range' is returned — better to admit uncertainty
than to act on conflicting signals.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd

from jiuwenswarm.quant.market_regime import MarketRegime
from jiuwenswarm.quant.market_index import MarketIndex


class RegimeFusion:
    """Weighted multi-signal regime detector.

    Usage:
        regime = RegimeFusion.detect(price_data)
        # or with pre-fetched index:
        regime = RegimeFusion.detect(price_data, index_prices=csi300_series)
    """

    # Initial weights (will be tuned via backtest)
    W_TECH: float = 0.5
    W_INDEX: float = 0.3
    # W_MODEL: float = 0.2  # reserved for Phase 3

    @staticmethod
    def detect(
        price_data: pd.DataFrame,
        index_prices: Optional[pd.Series] = None,
        lookback: int = 60,
    ) -> str:
        """Fuse technical and index-based regime signals.

        Args:
            price_data: Stock Close prices, columns = tickers.
            index_prices: Pre-fetched CSI 300 series (optional).
            lookback: MA window for both detectors.

        Returns:
            'bull', 'bear', or 'range'.
        """
        # Phase 1: technical signal (always available)
        s_tech = MarketRegime.detect(price_data, lookback=lookback)

        # Phase 2: index signal
        s_index = MarketIndex.detect(price_data, index_prices=index_prices)

        # Simple voting → fused signal
        if s_tech == s_index:
            fused = s_tech
        elif s_tech != MarketRegime.RANGE and s_index == MarketRegime.RANGE:
            fused = s_tech if RegimeFusion.W_TECH >= RegimeFusion.W_INDEX else MarketRegime.RANGE
        elif s_index != MarketRegime.RANGE and s_tech == MarketRegime.RANGE:
            fused = s_index if RegimeFusion.W_INDEX >= RegimeFusion.W_TECH else MarketRegime.RANGE
        else:
            fused = MarketRegime.RANGE

        # Volatility anomaly override: if recent vol has spiked to >2x
        # historical, directional signals (bull/bear) are unreliable.
        # High-vol bull = choppy market, not trending up.
        # High-vol bear = panic selling, often near a bottom.
        # Both cases: downgrade to range.
        if fused in (MarketRegime.BULL, MarketRegime.BEAR):
            market = price_data.mean(axis=1)
            recent_vol = market.pct_change().tail(10).std()
            historical_vol = market.pct_change().tail(60).std()
            if historical_vol > 0 and recent_vol > historical_vol * 2.0:
                return MarketRegime.RANGE

        return fused

    @staticmethod
    def detect_with_detail(
        price_data: pd.DataFrame,
        index_prices: Optional[pd.Series] = None,
        lookback: int = 60,
    ) -> dict:
        """Same as detect() but returns detail dict with all signals."""
        s_tech = MarketRegime.detect(price_data, lookback=lookback)
        s_index = MarketIndex.detect(price_data, index_prices=index_prices)
        s_final = RegimeFusion.detect(price_data, index_prices, lookback)

        return {
            "final": s_final,
            "technical": s_tech,
            "index": s_index,
            "consensus": s_tech == s_index,
        }
