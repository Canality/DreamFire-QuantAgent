"""Market regime detection using CSI 300 index data.

Provides an independent signal source that complements the cross-sectional
stock-pool average used by MarketRegime. The CSI 300 is market-cap weighted
and represents the true "market" better than an equal-weighted average of
49 hand-picked stocks.
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pandas as pd

from jiuwenswarm.quant.market_regime import MarketRegime

logger = logging.getLogger(__name__)

# CSI 300 ticker symbols for different data sources
CSI300_AKSHARE = "000300"       # akshare: pure numeric code
CSI300_BAOSTOCK = "sh.000300"   # baostock: exchange prefix
CSI300_YFINANCE = "000300.SS"   # yfinance: .SS suffix


class MarketIndex:
    """CSI 300 index-based regime detection.

    Uses the same volatility-normalized threshold logic as MarketRegime,
    but operates on a single index price series instead of a basket of stocks.
    """

    @staticmethod
    def detect_from_series(
        index_prices: pd.Series,
        lookback: int = 60,
    ) -> str:
        """Detect regime from a single index price series.

        Args:
            index_prices: Time series of index Close prices.
            lookback: Window for the long-term MA.

        Returns:
            'bull', 'bear', or 'range'.
        """
        series = index_prices.dropna()
        if len(series) < lookback:
            return MarketRegime.RANGE

        ma_long = series.rolling(lookback).mean().iloc[-1]
        ma_short = series.rolling(20).mean().iloc[-1]
        current = series.iloc[-1]

        price_vs_ma = (current - ma_long) / ma_long
        ma_slope = (ma_short - ma_long) / ma_long

        ret = series.pct_change().tail(MarketRegime.VOL_LOOKBACK)
        vol_daily = ret.std()

        if vol_daily == 0 or pd.isna(vol_daily) or len(ret.dropna()) < 5:
            return MarketRegime.RANGE

        price_sigma = price_vs_ma / vol_daily
        slope_sigma = ma_slope / vol_daily
        min_abs = max(0.01, vol_daily * 1.0)

        if abs(price_vs_ma) >= min_abs:
            if price_sigma > MarketRegime.BULL_PRICE_SIGMA and slope_sigma > MarketRegime.BULL_SLOPE_SIGMA:
                return MarketRegime.BULL
            if price_sigma < -MarketRegime.BEAR_PRICE_SIGMA and slope_sigma < -MarketRegime.BEAR_SLOPE_SIGMA:
                return MarketRegime.BEAR

        return MarketRegime.RANGE

    @staticmethod
    def fetch_csi300(
        start_date: str,
        end_date: str,
    ) -> Optional[pd.Series]:
        """Fetch CSI 300 index data via available data sources.

        Tries akshare first, then baostock.
        Returns a Series of Close prices indexed by date, or None if all fail.
        """
        # Tier 1: akshare
        try:
            import akshare as ak
            df = ak.stock_zh_index_daily(symbol=f"sh{CSI300_AKSHARE}")
            if df is not None and not df.empty:
                df["date"] = pd.to_datetime(df["date"])
                df = df.set_index("date").sort_index()
                mask = (df.index >= start_date) & (df.index <= end_date)
                result = df.loc[mask, "close"] if "close" in df.columns else None
                if result is not None and len(result) >= 60:
                    logger.info("[MarketIndex] CSI 300 fetched via akshare: %d days", len(result))
                    return result
        except Exception as e:
            logger.debug("[MarketIndex] akshare CSI 300 failed: %s", e)

        # Tier 2: baostock
        try:
            import baostock as bs
            lg = bs.login()
            rs = bs.query_history_k_data_plus(
                CSI300_BAOSTOCK, "date,close",
                start_date=start_date, end_date=end_date,
                frequency="d", adjustflag="3",
            )
            rows = []
            while (rs.error_code == "0") and rs.next():
                rows.append(rs.get_row_data())
            bs.logout()

            if rows:
                df = pd.DataFrame(rows, columns=rs.fields)
                df["date"] = pd.to_datetime(df["date"])
                df = df.set_index("date").sort_index()
                result = pd.to_numeric(df["close"], errors="coerce").dropna()
                if len(result) >= 60:
                    logger.info("[MarketIndex] CSI 300 fetched via baostock: %d days", len(result))
                    return result
        except Exception as e:
            logger.debug("[MarketIndex] baostock CSI 300 failed: %s", e)

        logger.warning("[MarketIndex] Failed to fetch CSI 300 from any source")
        return None

    @staticmethod
    def detect(
        price_data: pd.DataFrame,
        start_date: str = "2025-01-01",
        end_date: str = "2026-12-31",
        index_prices: Optional[pd.Series] = None,
    ) -> str:
        """Detect regime from CSI 300 index.

        Args:
            price_data: Stock price DataFrame (used to infer date range if
                        index_prices not provided).
            start_date: Fallback start date for index fetch.
            end_date: Fallback end date for index fetch.
            index_prices: Pre-fetched index series (optional). If None, will
                          attempt to fetch automatically.

        Returns:
            'bull', 'bear', or 'range'.
        """
        if index_prices is None:
            # Infer date range from price_data if possible
            if price_data is not None and not price_data.empty:
                start_date = str(price_data.index[0].date())
                end_date = str(price_data.index[-1].date())
            index_prices = MarketIndex.fetch_csi300(start_date, end_date)

        if index_prices is None or len(index_prices) < 60:
            return MarketRegime.RANGE

        return MarketIndex.detect_from_series(index_prices)
