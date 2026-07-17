"""Fundamental factor data: PE, PB, ROE via baostock.

Provides per-stock valuation and profitability metrics that complement
the technical factor model. All data is sector-neutral Z-scored for
cross-sector comparability.
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pandas as pd

from jiuwenswarm.quant.stock_pool import STOCK_POOL

logger = logging.getLogger(__name__)


class FundamentalData:
    """Fetch and compute fundamental factors for the stock pool."""

    @staticmethod
    def fetch_pe_pb(tickers: list[str]) -> Optional[pd.DataFrame]:
        """Fetch latest PE(TTM) and PB(MRQ) via baostock daily K-line.

        Returns DataFrame with columns [pe_ttm, pb_mrq], indexed by ticker.
        """
        try:
            import baostock as bs
        except ImportError:
            logger.warning("[Fundamental] baostock not installed")
            return None

        lg = bs.login()
        if lg.error_code != "0":
            logger.warning("[Fundamental] baostock login failed: %s", lg.error_msg)
            return None

        pe_data = {}
        pb_data = {}
        today = pd.Timestamp.now().strftime("%Y-%m-%d")
        start = (pd.Timestamp.now() - pd.Timedelta(days=10)).strftime("%Y-%m-%d")

        for ticker in tickers:
            code = ticker.replace(".SH", ".sh").replace(".SZ", ".sz")
            try:
                rs = bs.query_history_k_data_plus(
                    code, "date,peTTM,pbMRQ",
                    start_date=start, end_date=today,
                    frequency="d", adjustflag="3",
                )
                if rs.error_code != "0":
                    continue
                rows = []
                while rs.next():
                    rows.append(rs.get_row_data())
                if rows:
                    # Use the most recent non-empty value
                    for r in reversed(rows):
                        pe = float(r[1]) if r[1] and r[1] != "" else None
                        pb = float(r[2]) if r[2] and r[2] != "" else None
                        if pe and pe > 0:
                            pe_data[ticker] = pe
                        if pb and pb > 0:
                            pb_data[ticker] = pb
                        if ticker in pe_data and ticker in pb_data:
                            break
            except Exception:
                continue

        bs.logout()

        if not pe_data:
            logger.warning("[Fundamental] No PE/PB data fetched")
            return None

        df = pd.DataFrame({
            "pe_ttm": pd.Series(pe_data, dtype=float),
            "pb_mrq": pd.Series(pb_data, dtype=float),
        })
        df.index.name = "ticker"
        logger.info("[Fundamental] PE/PB fetched: %d stocks", len(df))
        return df

    @staticmethod
    def fetch_roe(tickers: list[str]) -> Optional[pd.Series]:
        """Fetch latest quarterly ROE via baostock query_profit_data.

        Returns Series of roeAvg indexed by ticker.
        """
        try:
            import baostock as bs
        except ImportError:
            return None

        lg = bs.login()
        if lg.error_code != "0":
            return None

        # Try Q1 2026, then Q4 2025, then Q3 2025
        now = pd.Timestamp.now()
        quarters = []
        for offset in range(4):
            q_date = now - pd.DateOffset(months=3 * offset)
            quarters.append((q_date.year, (q_date.month - 1) // 3 + 1))

        roe_data = {}
        for ticker in tickers:
            code = ticker.replace(".SH", ".sh").replace(".SZ", ".sz")
            for year, quarter in quarters:
                try:
                    rs = bs.query_profit_data(code=code, year=year, quarter=quarter)
                    rows = []
                    while (rs.error_code == "0") and rs.next():
                        rows.append(rs.get_row_data())
                    if rows and rows[0][3]:  # roeAvg is column index 3
                        roe_data[ticker] = float(rows[0][3])
                        break
                except Exception:
                    continue

        bs.logout()

        if not roe_data:
            logger.warning("[Fundamental] No ROE data fetched")
            return None

        result = pd.Series(roe_data, dtype=float, name="roe")
        result.index.name = "ticker"
        logger.info("[Fundamental] ROE fetched: %d stocks", len(result))
        return result

    @staticmethod
    def compute_scores(
        pe_pb_df: Optional[pd.DataFrame],
        roe_series: Optional[pd.Series],
    ) -> pd.DataFrame:
        """Compute sector-neutral Z-scores for fundamental factors.

        PE and PB are inverted (lower = better), ROE is raw (higher = better).

        Returns DataFrame with columns [pe_ttm_z, pb_mrq_z, roe_z],
        indexed by ticker.
        """
        tickers = set()
        if pe_pb_df is not None:
            tickers.update(pe_pb_df.index)
        if roe_series is not None:
            tickers.update(roe_series.index)

        if not tickers:
            return pd.DataFrame()

        scores = pd.DataFrame(index=sorted(tickers))
        scores.index.name = "ticker"

        def _sector_z(series: pd.Series) -> pd.Series:
            """Z-score within each sector."""
            result = pd.Series(0.0, index=series.index)
            for sector, stocks in STOCK_POOL.items():
                sector_mask = series.index.isin(stocks)
                if sector_mask.sum() < 2:
                    continue
                raw = series[sector_mask]
                result[sector_mask] = (raw - raw.mean()) / (raw.std() + 1e-10)
            return result

        # PE: invert so lower PE = higher score
        if pe_pb_df is not None and "pe_ttm" in pe_pb_df.columns:
            scores["pe_ttm_z"] = -_sector_z(pe_pb_df["pe_ttm"])

        # PB: invert so lower PB = higher score
        if pe_pb_df is not None and "pb_mrq" in pe_pb_df.columns:
            scores["pb_mrq_z"] = -_sector_z(pe_pb_df["pb_mrq"])

        # ROE: higher = better (no inversion)
        if roe_series is not None and len(roe_series) > 0:
            scores["roe_z"] = _sector_z(roe_series)

        return scores
