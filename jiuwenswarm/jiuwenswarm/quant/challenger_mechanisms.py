"""Pure, preregistered WP1-C score overlays for evaluation-only research."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from jiuwenswarm.quant.market_width import compute_sector_states
from jiuwenswarm.quant.stock_pool import ALL_STOCKS, SECTOR_MAP


TREND_CANDIDATE = "wp1c_r1_trend_consistency_v1"
SECTOR_CANDIDATE = "wp1c_r1_sector_leadership_v1"
TAIL_CANDIDATE = "wp1c_r1_asymmetric_tail_v1"
CHALLENGER_IDS = (TREND_CANDIDATE, SECTOR_CANDIDATE, TAIL_CANDIDATE)


@dataclass(frozen=True)
class OverlayResult:
    """One adjusted score frame plus JSON-serializable mechanism diagnostics."""

    candidate_id: str
    adjusted_scores: pd.DataFrame
    diagnostics: dict[str, Any]


def _validate_base_scores(base_scores: pd.DataFrame) -> pd.DataFrame:
    if base_scores.empty or "composite" not in base_scores:
        raise ValueError("base scores require a non-empty composite column")
    if not base_scores.index.is_unique:
        raise ValueError("base score tickers must be unique")
    unknown = sorted(set(base_scores.index) - set(ALL_STOCKS))
    if unknown:
        raise ValueError(f"base scores contain out-of-universe tickers: {unknown}")
    if not np.isfinite(base_scores["composite"].astype(float)).all():
        raise ValueError("base composite scores must be finite")
    return base_scores.copy(deep=True)


def _validate_history(
    frame: pd.DataFrame,
    *,
    label: str,
    min_rows: int,
) -> pd.DataFrame:
    if len(frame) < min_rows:
        raise ValueError(f"{label} requires at least {min_rows} decision-time rows")
    if not isinstance(frame.index, pd.DatetimeIndex):
        raise ValueError(f"{label} requires a DatetimeIndex")
    if not frame.index.is_monotonic_increasing or not frame.index.is_unique:
        raise ValueError(f"{label} index must be unique and chronological")
    if set(frame.columns) != set(ALL_STOCKS):
        raise ValueError(f"{label} must contain the exact 49-stock universe")
    ordered = frame.reindex(columns=ALL_STOCKS).astype(float)
    relevant = ordered.tail(min_rows)
    if not np.isfinite(relevant.to_numpy()).all():
        raise ValueError(f"{label} contains missing or non-finite decision inputs")
    return ordered


def _percent_rank(values: pd.Series) -> pd.Series:
    """Average-tie inclusive percentile rank mapped exactly into [-1, 1]."""

    numeric = values.astype(float)
    if not np.isfinite(numeric).all():
        raise ValueError("percent-rank inputs must be finite")
    if len(numeric) < 2:
        return pd.Series(0.0, index=numeric.index)
    ranks = numeric.rank(method="average")
    percentile = (ranks - 1.0) / (len(numeric) - 1.0)
    return (2.0 * (percentile - 0.5)).clip(-1.0, 1.0)


def apply_trend_consistency(
    base_scores: pd.DataFrame,
    closes: pd.DataFrame,
) -> OverlayResult:
    """Apply the frozen 5/10/20-day sign-consistent trend overlay."""

    adjusted = _validate_base_scores(base_scores)
    history = _validate_history(closes, label="closes", min_rows=21)
    returns = {
        horizon: history.iloc[-1] / history.iloc[-horizon - 1] - 1.0
        for horizon in (5, 10, 20)
    }
    ranks = {horizon: _percent_rank(values) for horizon, values in returns.items()}
    signs = pd.DataFrame({horizon: np.sign(values) for horizon, values in returns.items()})
    agreement = signs.ne(0.0).all(axis=1) & signs.eq(signs.iloc[:, 0], axis=0).all(axis=1)
    consistency = (
        (ranks[5] + ranks[10] + ranks[20]) / 3.0
    ).where(agreement, 0.0).clip(-1.0, 1.0)
    delta = (0.15 * consistency).clip(-0.15, 0.15)
    adjusted["composite"] = adjusted["composite"].astype(float) + delta.reindex(
        adjusted.index
    )
    adjusted = adjusted.sort_values("composite", ascending=False)
    return OverlayResult(
        candidate_id=TREND_CANDIDATE,
        adjusted_scores=adjusted,
        diagnostics={
            "r5": returns[5].astype(float).to_dict(),
            "r10": returns[10].astype(float).to_dict(),
            "r20": returns[20].astype(float).to_dict(),
            "q5": ranks[5].astype(float).to_dict(),
            "q10": ranks[10].astype(float).to_dict(),
            "q20": ranks[20].astype(float).to_dict(),
            "agreement_gate": agreement.astype(bool).to_dict(),
            "trend_consistency": consistency.astype(float).to_dict(),
            "score_delta": delta.astype(float).to_dict(),
        },
    )


def apply_sector_leadership(
    base_scores: pd.DataFrame,
    closes: pd.DataFrame,
    volumes: pd.DataFrame,
) -> OverlayResult:
    """Apply the frozen six-sector relative-strength and breadth tilt."""

    adjusted = _validate_base_scores(base_scores)
    history = _validate_history(closes, label="closes", min_rows=21)
    history_volume = _validate_history(volumes, label="volumes", min_rows=21)
    if not history.index.equals(history_volume.index):
        raise ValueError("sector close/volume histories must share an exact calendar")
    states = compute_sector_states(history, history_volume)
    expected_sectors = set(SECTOR_MAP.values())
    if set(states) != expected_sectors or len(states) != 6:
        raise ValueError("sector leadership requires the exact six-sector map")
    strength = pd.Series({
        sector: state.relative_strength_20d for sector, state in states.items()
    })
    breadth = pd.Series({
        sector: state.pct_positive_20d for sector, state in states.items()
    })
    sector_rank = _percent_rank(strength)
    breadth_score = (2.0 * breadth - 1.0).clip(-1.0, 1.0)
    leadership = (0.5 * sector_rank + 0.5 * breadth_score).clip(-1.0, 1.0)
    ticker_leadership = pd.Series({
        ticker: float(leadership[SECTOR_MAP[ticker]]) for ticker in ALL_STOCKS
    })
    delta = (0.10 * ticker_leadership).clip(-0.10, 0.10)
    adjusted["composite"] = adjusted["composite"].astype(float) + delta.reindex(
        adjusted.index
    )
    adjusted = adjusted.sort_values("composite", ascending=False)
    leaders = leadership.sort_values(ascending=False).head(2).index.tolist()
    return OverlayResult(
        candidate_id=SECTOR_CANDIDATE,
        adjusted_scores=adjusted,
        diagnostics={
            "relative_strength_20d": strength.astype(float).to_dict(),
            "pct_positive_20d": breadth.astype(float).to_dict(),
            "sector_rank_score": sector_rank.astype(float).to_dict(),
            "sector_leadership_score": leadership.astype(float).to_dict(),
            "top2_leaders": leaders,
            "ticker_leadership_score": ticker_leadership.astype(float).to_dict(),
            "score_delta": delta.astype(float).to_dict(),
        },
    )


def apply_asymmetric_tail(
    base_scores: pd.DataFrame,
    closes: pd.DataFrame,
    opens: pd.DataFrame,
) -> OverlayResult:
    """Apply the frozen extreme-only downside volatility/gap/drawdown penalty."""

    adjusted = _validate_base_scores(base_scores)
    history = _validate_history(closes, label="closes", min_rows=60)
    history_open = _validate_history(opens, label="opens", min_rows=21)
    if not history.index.equals(history_open.index):
        raise ValueError("tail close/open histories must share an exact calendar")
    daily_returns = history.pct_change().tail(20)
    downside = daily_returns.clip(upper=0.0).std() * np.sqrt(252.0)
    gaps = (history_open / history.shift(1) - 1.0).tail(20)
    min_gap = gaps.min()
    trailing = history.tail(60)
    drawdown = (trailing / trailing.cummax() - 1.0).min().abs()
    if not all(
        np.isfinite(values).all() for values in (downside, min_gap, drawdown)
    ):
        raise ValueError("tail-risk inputs produced non-finite diagnostics")
    vol_severity = ((downside - 0.40) / 0.20).clip(0.0, 1.0)
    gap_severity = ((-min_gap - 0.05) / 0.05).clip(0.0, 1.0)
    drawdown_severity = ((drawdown - 0.20) / 0.10).clip(0.0, 1.0)
    severity = pd.concat(
        [vol_severity, gap_severity, drawdown_severity], axis=1
    ).max(axis=1)
    delta = (-0.20 * severity).clip(-0.20, 0.0)
    adjusted["composite"] = adjusted["composite"].astype(float) + delta.reindex(
        adjusted.index
    )
    adjusted = adjusted.sort_values("composite", ascending=False)
    return OverlayResult(
        candidate_id=TAIL_CANDIDATE,
        adjusted_scores=adjusted,
        diagnostics={
            "downside_vol_20": downside.astype(float).to_dict(),
            "min_gap_20": min_gap.astype(float).to_dict(),
            "drawdown_60": drawdown.astype(float).to_dict(),
            "vol_severity": vol_severity.astype(float).to_dict(),
            "gap_severity": gap_severity.astype(float).to_dict(),
            "drawdown_severity": drawdown_severity.astype(float).to_dict(),
            "tail_severity": severity.astype(float).to_dict(),
            "score_delta": delta.astype(float).to_dict(),
        },
    )


def apply_challenger(
    candidate_id: str,
    base_scores: pd.DataFrame,
    closes: pd.DataFrame,
    opens: pd.DataFrame,
    volumes: pd.DataFrame,
) -> OverlayResult:
    """Dispatch exactly one registered mechanism; composition is impossible."""

    if candidate_id == TREND_CANDIDATE:
        return apply_trend_consistency(base_scores, closes)
    if candidate_id == SECTOR_CANDIDATE:
        return apply_sector_leadership(base_scores, closes, volumes)
    if candidate_id == TAIL_CANDIDATE:
        return apply_asymmetric_tail(base_scores, closes, opens)
    raise ValueError(f"Unknown or unregistered WP1-C candidate: {candidate_id!r}")
