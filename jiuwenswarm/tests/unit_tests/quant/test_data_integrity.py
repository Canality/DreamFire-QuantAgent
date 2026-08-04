"""Tests for WP1-A data integrity diagnostics."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from jiuwenswarm.quant.data_integrity import (
    DataIntegrityReport,
    check_cross_source_overlap,
    check_price_sanity,
    check_trading_calendar,
    detect_corporate_action_artifacts,
    run_all_checks,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def clean_calendar() -> pd.DatetimeIndex:
    return pd.bdate_range("2026-01-05", periods=200, freq="B")


@pytest.fixture
def clean_prices(clean_calendar: pd.DatetimeIndex) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    n = len(clean_calendar)
    data = 10 + np.cumsum(rng.normal(0.001, 0.02, (n, 5)), axis=0)
    cols = [f"{c:06d}.SH" for c in range(100000, 600000, 100000)]
    return pd.DataFrame(
        100 * np.exp(data),
        index=clean_calendar,
        columns=cols,
    )


# ---------------------------------------------------------------------------
# Trading calendar
# ---------------------------------------------------------------------------


class TestTradingCalendar:
    def test_clean_calendar_passes(self, clean_calendar: pd.DatetimeIndex) -> None:
        report = check_trading_calendar(clean_calendar)
        assert report.passed
        assert len(report.findings) == 0

    def test_empty_calendar_fails(self) -> None:
        report = check_trading_calendar(pd.DatetimeIndex([]))
        assert not report.passed

    def test_duplicate_dates_found(self) -> None:
        idx = pd.DatetimeIndex([
            pd.Timestamp("2026-01-05"),
            pd.Timestamp("2026-01-05"),
            pd.Timestamp("2026-01-06"),
        ])
        report = check_trading_calendar(idx)
        assert not report.passed
        assert any("duplicate" in f.lower() for f in report.findings)

    def test_weekend_dates_warned(self) -> None:
        idx = pd.bdate_range("2026-01-05", periods=10, freq="B").union(
            pd.DatetimeIndex([pd.Timestamp("2026-01-10")])  # Saturday
        ).sort_values()
        report = check_trading_calendar(idx)
        assert report.passed  # weekend is just a warning
        assert any("weekend" in w.lower() for w in report.warnings)

    def test_metrics_populated(self, clean_calendar: pd.DatetimeIndex) -> None:
        report = check_trading_calendar(clean_calendar)
        assert report.metrics["n_trading_days"] == 200
        assert report.metrics["n_weekend_days"] == 0


# ---------------------------------------------------------------------------
# Price sanity
# ---------------------------------------------------------------------------


class TestPriceSanity:
    def test_clean_prices_pass(self, clean_prices: pd.DataFrame) -> None:
        opens = clean_prices * 0.99
        volumes = pd.DataFrame(1e6, index=clean_prices.index, columns=clean_prices.columns)
        report = check_price_sanity(clean_prices, opens, volumes)
        assert report.passed

    def test_negative_prices_found(self, clean_prices: pd.DataFrame) -> None:
        bad = clean_prices.copy()
        bad.iloc[50, 0] = -1.0
        opens = clean_prices * 0.99
        volumes = pd.DataFrame(1e6, index=bad.index, columns=bad.columns)
        report = check_price_sanity(bad, opens, volumes)
        assert not report.passed
        assert any("negative" in f.lower() for f in report.findings)

    def test_empty_data_fails(self) -> None:
        empty = pd.DataFrame()
        report = check_price_sanity(empty, empty, empty)
        assert not report.passed


# ---------------------------------------------------------------------------
# Cross-source overlap
# ---------------------------------------------------------------------------


class TestCrossSource:
    def test_identical_sources_no_divergence(self) -> None:
        idx = pd.bdate_range("2026-01-05", periods=100)
        p = pd.DataFrame({"600000.SH": range(1000, 1100), "000001.SZ": range(2000, 2100)}, index=idx, dtype=float)
        s = p.copy()
        report = check_cross_source_overlap(p, s)
        assert report.passed
        assert report.metrics["n_divergent_dates"] == 0

    def test_divergent_sources_fail_closed(self) -> None:
        idx = pd.bdate_range("2026-01-05", periods=100)
        p = pd.DataFrame({"600000.SH": range(1000, 1100), "000001.SZ": range(2000, 2100)}, index=idx, dtype=float)
        s = p.copy()
        s.iloc[50, 0] *= 1.5  # 50% divergence on one date
        report = check_cross_source_overlap(p, s, tolerance_pct=1.0)
        assert not report.passed
        assert len(report.findings) > 0
        assert report.metrics["n_divergent_points"] == 1
        assert report.metrics["n_divergent_tickers"] == 1

    def test_no_overlap_fails(self) -> None:
        idx1 = pd.bdate_range("2026-01-05", periods=50)
        idx2 = pd.bdate_range("2026-06-01", periods=50)
        cols = ["600000.SH"]
        p = pd.DataFrame({c: range(50) for c in cols}, index=idx1, dtype=float)
        s = pd.DataFrame({c: range(50) for c in cols}, index=idx2, dtype=float)
        report = check_cross_source_overlap(p, s)
        assert not report.passed

    def test_one_of_49_divergence_fail_closed(self) -> None:
        """One bad ticker among 49 must trigger fail-closed, not averaged away."""
        idx = pd.bdate_range("2026-01-05", periods=100)
        n = 49
        cols = [f"T{i:03d}" for i in range(n)]
        rng = np.random.default_rng(123)
        base = 100 + np.cumsum(rng.normal(0, 0.5, (len(idx), n)), axis=0)
        p = pd.DataFrame(base, index=idx, columns=cols, dtype=float)
        s = p.copy()
        # Inject 50% divergence on ONE ticker (T048, the 49th) on ONE date
        s.iloc[50, 48] *= 1.50
        report = check_cross_source_overlap(p, s, tolerance_pct=1.0)
        assert not report.passed, (
            "one-of-49 divergence must fail closed; got passed=True"
        )
        assert len(report.findings) > 0
        assert any("per-ticker" in f.lower() for f in report.findings), (
            "findings should mention per-ticker detection"
        )


# ---------------------------------------------------------------------------
# Corporate actions
# ---------------------------------------------------------------------------


class TestCorporateActions:
    def test_clean_data_no_artifacts(self, clean_prices: pd.DataFrame) -> None:
        volumes = pd.DataFrame(1e6, index=clean_prices.index, columns=clean_prices.columns)
        report = detect_corporate_action_artifacts(clean_prices, volumes)
        assert report.metrics["crash_drop_events"] == 0

    def test_crash_drop_detected(self, clean_prices: pd.DataFrame) -> None:
        bad = clean_prices.copy()
        # Simulate a dividend drop: -20% on one ticker only (isolated)
        # so excess_ret (vs market mean) is also large negative
        bad.iloc[-1, 0] = bad.iloc[-2, 0] * 0.75  # -25% drop
        volumes = pd.DataFrame(1e6, index=bad.index, columns=bad.columns)
        report = detect_corporate_action_artifacts(bad, volumes)
        assert report.metrics["crash_drop_events"] > 0

    def test_inversion_scanned_beyond_10th_ticker(self) -> None:
        """Volume/price inversion on ticker #12 (beyond first 10) must be detected."""
        idx = pd.bdate_range("2026-01-05", periods=30)
        n_tickers = 15
        cols = [f"tkr_{i:03d}" for i in range(n_tickers)]
        data = np.random.default_rng(99).normal(0.001, 0.02, (len(idx), n_tickers))
        closes = pd.DataFrame(
            100 * np.exp(np.cumsum(data, axis=0)), index=idx, columns=cols
        )
        volumes = pd.DataFrame(1e6, index=idx, columns=cols, dtype=float)
        # Inject inversion on ticker #12 (index 11): volume doubles, price halves
        volumes.iloc[20, 11] = volumes.iloc[19, 11] * 3.0  # >100% volume increase
        closes.iloc[20, 11] = closes.iloc[19, 11] * 0.5   # -50% price
        report = detect_corporate_action_artifacts(closes, volumes)
        assert len(report.warnings) > 0
        assert any(cols[11] in w for w in report.warnings), (
            f"Expected inversion warning for {cols[11]} (ticker #12)"
        )
        assert report.metrics["volume_tickers_scanned"] == n_tickers
        assert report.metrics["inversion_tickers"] == 1

    def test_missing_volume_column_does_not_abort_full_scan(self) -> None:
        """Partial volume input must not raise while scanning shared tickers."""
        idx = pd.bdate_range("2026-01-05", periods=3)
        closes = pd.DataFrame(
            {"A": [100.0, 50.0, 50.0], "B": [100.0, 100.0, 100.0]},
            index=idx,
        )
        volumes = pd.DataFrame({"A": [1.0, 3.0, 3.0]}, index=idx)
        report = detect_corporate_action_artifacts(closes, volumes)
        assert report.metrics["volume_tickers_scanned"] == 1
        assert report.metrics["inversion_tickers"] == 1


# ---------------------------------------------------------------------------
# run_all_checks
# ---------------------------------------------------------------------------


class TestRunAllChecks:
    def test_returns_reports(self, clean_prices: pd.DataFrame) -> None:
        opens = clean_prices * 0.99
        volumes = pd.DataFrame(1e6, index=clean_prices.index, columns=clean_prices.columns)
        results = run_all_checks(clean_prices, opens, volumes)
        assert len(results) >= 3  # calendar + price + corp_action
        assert all(isinstance(r, DataIntegrityReport) for r in results)
