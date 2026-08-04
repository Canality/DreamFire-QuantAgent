"""Tests for WP1-A market width and sector state diagnostics."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from jiuwenswarm.quant.market_width import (
    BreadthSnapshot,
    SectorState,
    compute_breadth,
    compute_sector_states,
    detect_sector_leadership,
    detect_sector_rotation,
)



@pytest.fixture
def prices_5t_200d() -> pd.DataFrame:
    """5 tickers × 200 trading days of random-walk prices."""
    rng = np.random.default_rng(42)
    dates = pd.bdate_range("2026-01-05", periods=200)
    n = len(dates)
    data = np.cumsum(rng.normal(0.001, 0.02, (n, 5)), axis=0)
    prices = pd.DataFrame(
        100 * np.exp(data),
        index=dates,
        columns=["600000.SH", "000001.SZ", "000002.SZ", "600036.SH", "600519.SH"],
    )
    return prices


@pytest.fixture
def volumes_5t_200d(prices_5t_200d: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        np.random.default_rng(1).integers(1e6, 5e6, size=prices_5t_200d.shape),
        index=prices_5t_200d.index,
        columns=prices_5t_200d.columns,
        dtype=float,
    )


# ---------------------------------------------------------------------------
# Breadth
# ---------------------------------------------------------------------------


class TestBreadth:
    def test_returns_snapshot(self, prices_5t_200d: pd.DataFrame, volumes_5t_200d: pd.DataFrame) -> None:
        snap = compute_breadth(prices_5t_200d, volumes_5t_200d)
        assert isinstance(snap, BreadthSnapshot)
        assert snap.n_stocks == 5
        assert 0 <= snap.participation_score <= 1

    def test_advance_decline_sums_to_n(self, prices_5t_200d: pd.DataFrame, volumes_5t_200d: pd.DataFrame) -> None:
        snap = compute_breadth(prices_5t_200d, volumes_5t_200d)
        assert snap.advance_count + snap.decline_count <= snap.n_stocks

    def test_metrics_in_range(self, prices_5t_200d: pd.DataFrame, volumes_5t_200d: pd.DataFrame) -> None:
        snap = compute_breadth(prices_5t_200d, volumes_5t_200d)
        for attr in ["pct_above_ma20", "pct_positive_5d", "pct_near_20d_high"]:
            val = getattr(snap, attr)
            assert 0 <= val <= 1, f"{attr}={val} out of [0,1]"

    def test_exact_5d_20d_endpoint_intervals(self) -> None:
        """5d/20d returns must be endpoint-to-endpoint: close[t]/close[t-N]-1."""
        dates = pd.bdate_range("2026-01-05", periods=21)
        # Both true endpoint returns are negative: t20/t15-1 and t20/t0-1.
        # The old tail(N).pct_change().sum() implementation omitted the first
        # interval and classified both as positive.
        prices = np.full(21, 50.0)
        prices[0] = 100.0
        prices[15] = 100.0
        prices[20] = 60.0
        closes = pd.DataFrame({"A": prices}, index=dates)
        volumes = pd.DataFrame(1e6, index=dates, columns=["A"], dtype=float)
        snap = compute_breadth(closes, volumes, date_idx=20)
        assert snap.pct_positive_5d == 0.0
        assert snap.pct_positive_20d == 0.0

    def test_short_history_returns_zero(self) -> None:
        """When history < required intervals, breadth returns should be 0."""
        dates = pd.bdate_range("2026-01-05", periods=3)
        closes = pd.DataFrame({"A": [100, 101, 102]}, index=dates)
        volumes = pd.DataFrame(1e6, index=dates, columns=["A"], dtype=float)
        snap = compute_breadth(closes, volumes, date_idx=2)
        assert snap.pct_positive_5d == 0.0
        assert snap.pct_positive_20d == 0.0

    def test_date_idx_boundary_zero(self, prices_5t_200d: pd.DataFrame, volumes_5t_200d: pd.DataFrame) -> None:
        """date_idx=0 (first date) must not crash and return valid snapshot."""
        snap = compute_breadth(prices_5t_200d, volumes_5t_200d, date_idx=0)
        assert isinstance(snap, BreadthSnapshot)
        assert snap.n_stocks == 5
        assert 0 <= snap.participation_score <= 1

    def test_date_idx_out_of_range_fails_explicitly(
        self,
        prices_5t_200d: pd.DataFrame,
        volumes_5t_200d: pd.DataFrame,
    ) -> None:
        with pytest.raises(IndexError, match="outside closes"):
            compute_breadth(
                prices_5t_200d,
                volumes_5t_200d,
                date_idx=len(prices_5t_200d),
            )
        with pytest.raises(IndexError, match="outside closes"):
            compute_breadth(
                prices_5t_200d,
                volumes_5t_200d,
                date_idx=-(len(prices_5t_200d) + 1),
            )


# ---------------------------------------------------------------------------
# Sector state
# ---------------------------------------------------------------------------


class TestSectorState:
    def test_returns_dict(self, prices_5t_200d: pd.DataFrame, volumes_5t_200d: pd.DataFrame) -> None:
        states = compute_sector_states(prices_5t_200d, volumes_5t_200d)
        assert isinstance(states, dict)
        for s in states.values():
            assert isinstance(s, SectorState)
            assert s.n_stocks > 0

    def test_relative_strength_sums_approximately_zero(self, prices_5t_200d: pd.DataFrame, volumes_5t_200d: pd.DataFrame) -> None:
        states = compute_sector_states(prices_5t_200d, volumes_5t_200d)
        weighted_sum = sum(
            s.relative_strength_20d * s.n_stocks for s in states.values()
        ) / sum(s.n_stocks for s in states.values())
        assert abs(weighted_sum) < 0.01


class TestSectorLeadership:
    def test_returns_top_n(self, prices_5t_200d: pd.DataFrame, volumes_5t_200d: pd.DataFrame) -> None:
        states = compute_sector_states(prices_5t_200d, volumes_5t_200d)
        leaders = detect_sector_leadership(states, top_n=2)
        assert len(leaders) <= 2
        # Sorted descending
        if len(leaders) >= 2:
            assert leaders[0][1] >= leaders[1][1]


class TestSectorRotation:
    def test_detects_rank_changes(self, prices_5t_200d: pd.DataFrame, volumes_5t_200d: pd.DataFrame) -> None:
        states_today = compute_sector_states(prices_5t_200d, volumes_5t_200d, date_idx=-1)
        states_yesterday = compute_sector_states(prices_5t_200d, volumes_5t_200d, date_idx=-2)
        rotation = detect_sector_rotation(states_today, states_yesterday)
        assert isinstance(rotation, dict)

    def test_empty_previous_returns_empty(self) -> None:
        assert detect_sector_rotation({}, {}) == {}
