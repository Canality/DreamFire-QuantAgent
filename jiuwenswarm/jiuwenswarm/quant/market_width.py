"""Market breadth and sector state diagnostics for WP1-A.

Read-only diagnostics — produces breadth indicators and sector-level
summaries that characterise the current market environment without
modifying factor construction, stock selection, or portfolio weights.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from jiuwenswarm.quant.stock_pool import SECTOR_MAP


# ---------------------------------------------------------------------------
# Output types
# ---------------------------------------------------------------------------


@dataclass
class BreadthSnapshot:
    """Market breadth metrics at a single point in time."""

    date: pd.Timestamp
    n_stocks: int

    # -- Price-based breadth --
    pct_above_ma20: float
    pct_above_ma60: float
    pct_positive_5d: float
    pct_positive_20d: float

    # -- Volume-based breadth --
    pct_volume_above_ma20: float

    # -- Advance/decline --
    advance_count: int
    decline_count: int
    advance_decline_ratio: float

    # -- High/low --
    pct_near_20d_high: float    # within 5% of 20-day high
    pct_near_20d_low: float     # within 5% of 20-day low

    # -- Derived --
    participation_score: float  # 0–1 composite of the above


@dataclass
class SectorState:
    """Cross-sectional sector snapshot."""

    date: pd.Timestamp
    sector: str
    n_stocks: int

    mean_return_5d: float
    mean_return_20d: float
    pct_positive_5d: float
    pct_positive_20d: float
    mean_volume_change_5d: float

    # Relative to full pool
    relative_strength_20d: float
    """Sector mean return minus pool mean return over 20 days."""


# ---------------------------------------------------------------------------
# Breadth computation
# ---------------------------------------------------------------------------


def compute_breadth(
    closes: pd.DataFrame,
    volumes: pd.DataFrame,
    date_idx: int = -1,
) -> BreadthSnapshot:
    """Compute market breadth metrics for a single date.

    Args:
        closes: Close prices (rows = dates, columns = tickers).
        volumes: Volume data (same shape as closes).
        date_idx: Which date to compute for (default: last date).

    Returns:
        ``BreadthSnapshot`` with all breadth indicators populated.
    """
    if date_idx < 0:
        date_idx = len(closes) + date_idx
    if not 0 <= date_idx < len(closes):
        raise IndexError(
            f"date_idx resolves outside closes: {date_idx} for {len(closes)} rows"
        )

    date = closes.index[date_idx]
    n_stocks = closes.shape[1]

    # -- Slice history for moving averages --
    hist_closes = closes.iloc[: date_idx + 1]
    hist_volumes = volumes.iloc[: date_idx + 1] if not volumes.empty else pd.DataFrame()

    current = hist_closes.iloc[-1]

    # -- Price breadth --
    ma20 = hist_closes.tail(20).mean() if len(hist_closes) >= 20 else current
    ma60 = hist_closes.tail(60).mean() if len(hist_closes) >= 60 else current
    pct_above_ma20 = float((current > ma20).mean())
    pct_above_ma60 = float((current > ma60).mean())

    ret_5d = (
        hist_closes.iloc[-1] / hist_closes.iloc[-6] - 1
        if len(hist_closes) >= 6
        else pd.Series(0.0, index=current.index)
    )
    ret_20d = (
        hist_closes.iloc[-1] / hist_closes.iloc[-21] - 1
        if len(hist_closes) >= 21
        else pd.Series(0.0, index=current.index)
    )
    pct_positive_5d = float((ret_5d > 0).mean()) if len(ret_5d) > 0 else 0.0
    pct_positive_20d = float((ret_20d > 0).mean()) if len(ret_20d) > 0 else 0.0

    # -- Volume breadth --
    if not hist_volumes.empty and len(hist_volumes) >= 20:
        vol_ma20 = hist_volumes.tail(20).mean()
        pct_volume_above_ma20 = float((hist_volumes.iloc[-1] > vol_ma20).mean())
    else:
        pct_volume_above_ma20 = 0.5

    # -- Advance/decline --
    daily_ret = closes.iloc[date_idx] / closes.iloc[date_idx - 1] - 1 if date_idx > 0 else pd.Series(0, index=current.index)
    advance_count = int((daily_ret > 0).sum())
    decline_count = int((daily_ret < 0).sum())
    ad_ratio = advance_count / max(decline_count, 1)

    # -- Near highs/lows --
    high_20d = hist_closes.tail(20).max() if len(hist_closes) >= 20 else current
    low_20d = hist_closes.tail(20).min() if len(hist_closes) >= 20 else current
    pct_near_20d_high = float((current >= high_20d * 0.95).mean())
    pct_near_20d_low = float((current <= low_20d * 1.05).mean())

    # -- Participation score (0–1, equally weighted) --
    components = [
        pct_above_ma20,
        pct_positive_5d,
        advance_count / max(n_stocks, 1),
        1.0 - pct_near_20d_low,
    ]
    participation = float(np.clip(np.mean(components), 0.0, 1.0))

    return BreadthSnapshot(
        date=date,
        n_stocks=n_stocks,
        pct_above_ma20=round(pct_above_ma20, 4),
        pct_above_ma60=round(pct_above_ma60, 4),
        pct_positive_5d=round(pct_positive_5d, 4),
        pct_positive_20d=round(pct_positive_20d, 4),
        pct_volume_above_ma20=round(pct_volume_above_ma20, 4),
        advance_count=advance_count,
        decline_count=decline_count,
        advance_decline_ratio=round(ad_ratio, 2),
        pct_near_20d_high=round(pct_near_20d_high, 4),
        pct_near_20d_low=round(pct_near_20d_low, 4),
        participation_score=round(participation, 4),
    )


# ---------------------------------------------------------------------------
# Sector state
# ---------------------------------------------------------------------------


def compute_sector_states(
    closes: pd.DataFrame,
    volumes: pd.DataFrame,
    date_idx: int = -1,
) -> Dict[str, SectorState]:
    """Compute sector-level diagnostics for a single date.

    Returns a dict mapping sector name → ``SectorState``.
    """
    if date_idx < 0:
        date_idx = len(closes) + date_idx

    date = closes.index[date_idx]
    sectors: Dict[str, List[str]] = {}
    for ticker in closes.columns:
        sec = SECTOR_MAP.get(ticker, "未知")
        sectors.setdefault(sec, []).append(ticker)

    pool_ret_20d = closes.iloc[date_idx] / closes.iloc[max(0, date_idx - 20)] - 1
    pool_mean_20d = float(pool_ret_20d.mean())

    result: Dict[str, SectorState] = {}
    for sec, tickers in sectors.items():
        n = len(tickers)
        if n == 0:
            continue

        sec_closes = closes[tickers]
        sec_volumes = volumes[tickers] if not volumes.empty else pd.DataFrame()

        ret_5d = sec_closes.iloc[date_idx] / sec_closes.iloc[max(0, date_idx - 5)] - 1
        ret_20d = sec_closes.iloc[date_idx] / sec_closes.iloc[max(0, date_idx - 20)] - 1
        mean_ret_5d = float(ret_5d.mean())
        mean_ret_20d = float(ret_20d.mean())

        pct_pos_5d = float((ret_5d > 0).mean())
        pct_pos_20d = float((ret_20d > 0).mean())

        vol_change_5d = 0.0
        if not sec_volumes.empty and date_idx >= 5:
            recent = sec_volumes.iloc[date_idx - 4: date_idx + 1].mean()
            prior = sec_volumes.iloc[date_idx - 9: date_idx - 4].mean()
            vol_change_5d = float((recent.mean() / max(prior.mean(), 1)) - 1)

        result[sec] = SectorState(
            date=date,
            sector=sec,
            n_stocks=n,
            mean_return_5d=round(mean_ret_5d, 6),
            mean_return_20d=round(mean_ret_20d, 6),
            pct_positive_5d=round(pct_pos_5d, 4),
            pct_positive_20d=round(pct_pos_20d, 4),
            mean_volume_change_5d=round(vol_change_5d, 4),
            relative_strength_20d=round(mean_ret_20d - pool_mean_20d, 6),
        )

    return result


# ---------------------------------------------------------------------------
# Sector leadership / rotation
# ---------------------------------------------------------------------------


def detect_sector_leadership(
    sector_states: Dict[str, SectorState],
    top_n: int = 3,
) -> List[Tuple[str, float]]:
    """Rank sectors by relative strength and return top N."""
    ranked = sorted(
        sector_states.items(),
        key=lambda kv: kv[1].relative_strength_20d,
        reverse=True,
    )
    return [(sec, state.relative_strength_20d) for sec, state in ranked[:top_n]]


def detect_sector_rotation(
    current: Dict[str, SectorState],
    previous: Dict[str, SectorState],
) -> Dict[str, int]:
    """Detect rank changes between two sector state snapshots.

    Returns a dict of sector → rank_change (positive = improving).
    """
    if not previous:
        return {}

    cur_ranked = sorted(
        current.items(),
        key=lambda kv: kv[1].relative_strength_20d, reverse=True,
    )
    prev_ranked = sorted(
        previous.items(),
        key=lambda kv: kv[1].relative_strength_20d, reverse=True,
    )

    cur_ranks = {sec: i for i, (sec, _) in enumerate(cur_ranked)}
    prev_ranks = {sec: i for i, (sec, _) in enumerate(prev_ranked)}

    rotation: Dict[str, int] = {}
    for sec in cur_ranks:
        if sec in prev_ranks:
            rotation[sec] = prev_ranks[sec] - cur_ranks[sec]

    return rotation
