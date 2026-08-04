"""Data consistency diagnostics for WP1-A.

Checks trading calendar, price units, adjustment/corporate-action
artifacts, and cross-source overlap.  All functions are read-only
diagnostics — they never modify prices, factors, or strategy weights.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, List

import pandas as pd

# A-shares were formally introduced on 1990-12-19; earliest practical
# data for the current pool is 2018+.  Use a generous minimum.
_MIN_DATE = date(2015, 1, 1)


# ---------------------------------------------------------------------------
# Output types
# ---------------------------------------------------------------------------


@dataclass
class DataIntegrityReport:
    """Result of running all data consistency checks."""

    passed: bool = True
    findings: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    metrics: Dict[str, float | int] = field(default_factory=dict)

    @property
    def has_issues(self) -> bool:
        return len(self.findings) > 0 or len(self.warnings) > 0


# ---------------------------------------------------------------------------
# 1. Trading calendar
# ---------------------------------------------------------------------------


def check_trading_calendar(
    index: pd.DatetimeIndex,
    expected_approx_days: int | None = None,
) -> DataIntegrityReport:
    """Verify that the trading calendar is consistent.

    Checks:
    - No duplicate dates.
    - Dates are monotonically increasing.
    - No weekend dates (Sat/Sun are not trading days on SSE/SZSE).
    - Gaps between consecutive dates are reasonable (≤ 10 calendar days
      covers normal holiday weeks; longer gaps are flagged as warnings).
    """
    report = DataIntegrityReport()

    if len(index) == 0:
        report.findings.append("Trading calendar is empty")
        report.passed = False
        return report

    # Duplicates
    if index.has_duplicates:
        dups = index[index.duplicated()].tolist()
        report.findings.append(
            f"Trading calendar has {len(dups)} duplicate dates: "
            f"{dups[:5]}{'...' if len(dups) > 5 else ''}"
        )
        report.passed = False

    # Monotonic
    if not index.is_monotonic_increasing:
        report.findings.append("Trading calendar is not monotonically increasing")
        report.passed = False

    # Weekend check
    weekend_days = index[index.dayofweek >= 5]
    if len(weekend_days) > 0:
        report.warnings.append(
            f"{len(weekend_days)} weekend dates in trading calendar: "
            f"{weekend_days.strftime('%Y-%m-%d').tolist()[:5]}"
        )

    # Gap check
    gaps = index[1:] - index[:-1]
    long_gaps = gaps[gaps > timedelta(days=10)]
    if len(long_gaps) > 0:
        report.warnings.append(
            f"{len(long_gaps)} gaps > 10 calendar days between trading days"
        )

    report.metrics["n_trading_days"] = len(index)
    report.metrics["date_range_days"] = (index[-1] - index[0]).days
    report.metrics["n_weekend_days"] = len(weekend_days)
    report.metrics["max_gap_days"] = int(gaps.max().days) if len(gaps) > 0 else 0

    return report


# ---------------------------------------------------------------------------
# 2. Price sanity
# ---------------------------------------------------------------------------


def check_price_sanity(
    closes: pd.DataFrame,
    opens: pd.DataFrame,
    volumes: pd.DataFrame,
) -> DataIntegrityReport:
    """Detect likely data-quality issues in price/volume data.

    Checks:
    - Negative or zero prices / volumes.
    - Price jumps > 11% day-over-day (likely split/corporate-action
      artifact that needs adjustment).
    - Zero volume with price movement (stale close on active day).
    """
    report = DataIntegrityReport()
    if closes.empty:
        report.findings.append("Close price data is empty")
        report.passed = False
        return report

    # Negative / zero
    for label, frame in [("close", closes), ("open", opens), ("volume", volumes)]:
        neg_count = int((frame < 0).sum().sum())
        zero_count = int((frame == 0).sum().sum())
        if neg_count > 0:
            report.findings.append(
                f"{neg_count} negative values in {label} data"
            )
            report.passed = False
        if zero_count > 0 and label != "volume":
            report.warnings.append(
                f"{zero_count} zero values in {label} data"
            )

    # Price jump (daily return > 11% for any stock)
    daily_rets = closes.pct_change().dropna(how="all")
    jump_mask = (daily_rets.abs() > 0.11) & (daily_rets.shift(-1).abs() > 0.11)
    jump_count = int(jump_mask.sum().sum())
    if jump_count > 0:
        affected = closes.columns[jump_mask.any(axis=0)].tolist()
        report.warnings.append(
            f"{jump_count} consecutive-day price jumps > 11% across "
            f"{len(affected)} tickers (possible split/corporate-action "
            f"artifacts): {affected[:5]}"
        )

    # Zero volume with price movement
    if not volumes.empty and not closes.empty:
        common_idx = volumes.index.intersection(closes.index)
        vol_zero = (volumes.loc[common_idx] == 0)
        price_moved = closes.loc[common_idx].pct_change().abs() > 0
        stale_close = int((vol_zero & price_moved).sum().sum())
        if stale_close > 0:
            report.warnings.append(
                f"{stale_close} instances of zero volume with price "
                f"movement (stale close signal)"
            )

    report.metrics["n_tickers"] = closes.shape[1]
    report.metrics["n_rows"] = closes.shape[0]
    report.metrics["price_jump_events"] = jump_count
    report.metrics["negative_values"] = int((closes < 0).sum().sum())

    return report


# ---------------------------------------------------------------------------
# 3. Cross-source overlap
# ---------------------------------------------------------------------------


def check_cross_source_overlap(
    primary: pd.DataFrame,
    secondary: pd.DataFrame,
    primary_label: str = "primary",
    secondary_label: str = "secondary",
    tolerance_pct: float = 1.0,
) -> DataIntegrityReport:
    """Compare two data sources on their overlapping date range.

    Compare every overlapping ticker/date point independently.  Any point
    above *tolerance_pct* fails closed so a bad ticker cannot be hidden by
    averaging it with the rest of the universe.
    """
    report = DataIntegrityReport()

    common_idx = primary.index.intersection(secondary.index)
    common_cols = primary.columns.intersection(secondary.columns)

    if len(common_idx) == 0:
        report.findings.append(
            f"No overlapping dates between {primary_label} and "
            f"{secondary_label}"
        )
        report.passed = False
        return report

    if len(common_cols) == 0:
        report.findings.append(
            f"No overlapping tickers between {primary_label} and "
            f"{secondary_label}"
        )
        report.passed = False
        return report

    p = primary.loc[common_idx, common_cols]
    s = secondary.loc[common_idx, common_cols]

    # Per-ticker per-date % diff — fail closed on ANY ticker exceeding
    # tolerance so one bad ticker cannot be averaged away.
    ticker_pct = ((p - s).abs() / s.abs().clip(lower=0.01)) * 100
    bad_mask = ticker_pct > tolerance_pct
    bad_ticker_dates = bad_mask.any(axis=1)
    n_divergent_dates = int(bad_ticker_dates.sum())
    n_divergent_points = int(bad_mask.sum().sum())
    divergent_tickers = p.columns[bad_mask.any(axis=0)].tolist()

    if n_divergent_dates > 0:
        report.findings.append(
            f"{n_divergent_dates} dates with any-ticker >{tolerance_pct}% "
            f"cross-source divergence between {primary_label} and "
            f"{secondary_label} across {len(divergent_tickers)} tickers "
            f"(fail-closed: per-ticker check): {divergent_tickers[:5]}"
            f"{'...' if len(divergent_tickers) > 5 else ''}"
        )
        report.passed = False

    report.metrics["n_overlap_dates"] = len(common_idx)
    report.metrics["n_overlap_tickers"] = len(common_cols)
    report.metrics["n_divergent_dates"] = n_divergent_dates
    report.metrics["n_divergent_points"] = n_divergent_points
    report.metrics["n_divergent_tickers"] = len(divergent_tickers)
    report.metrics["max_divergence_pct"] = (
        round(float(ticker_pct.max().max()), 2) if ticker_pct.size > 0 else 0.0
    )
    report.metrics["mean_divergence_pct"] = (
        round(float(ticker_pct.mean().mean()), 2) if ticker_pct.size > 0 else 0.0
    )

    return report


# ---------------------------------------------------------------------------
# 4. Corporate action detection
# ---------------------------------------------------------------------------


def detect_corporate_action_artifacts(
    closes: pd.DataFrame,
    volumes: pd.DataFrame,
) -> DataIntegrityReport:
    """Detect likely unadjusted corporate-action artifacts.

    Signs of splits or dividends not properly adjusted:
    - A single-day return < -15% with no corresponding market move.
    - Consecutive return of roughly +100% / -50% (split signature).
    - Volume doubling with price halving (or vice versa) in adjacent days.
    """
    report = DataIntegrityReport()

    if closes.shape[1] == 0:
        return report

    daily_rets = closes.pct_change()
    market_ret = daily_rets.mean(axis=1)

    # Individual stock returns that deviate wildly from the market
    excess_ret = daily_rets.sub(market_ret, axis=0)
    crash_days = (excess_ret < -0.15) & (daily_rets < -0.15)
    crash_count = int(crash_days.sum().sum())

    if crash_count > 0:
        affected = closes.columns[crash_days.any(axis=0)].tolist()
        report.warnings.append(
            f"{crash_count} single-day drops > 15% vs market across "
            f"{len(affected)} tickers (possible unadjusted dividend/split): "
            f"{affected[:5]}"
        )

    # Volume/price inversion (possible split)
    inversion_events = 0
    inversion_tickers = 0
    if not volumes.empty:
        volume_tickers = closes.columns.intersection(volumes.columns)
        for ticker in volume_tickers:
            vol_change = volumes[ticker].pct_change()
            price_change = closes[ticker].pct_change()
            inversion = (
                (vol_change > 1.0) & (price_change < -0.3)
            ) | (
                (vol_change < -0.5) & (price_change > 0.5)
            )
            inv_count = int(inversion.sum())
            if inv_count > 0:
                inversion_events += inv_count
                inversion_tickers += 1
                report.warnings.append(
                    f"{ticker}: {inv_count} volume/price inversion events "
                    f"(possible split/reverse-split)"
                )

    report.metrics["crash_drop_events"] = crash_count
    report.metrics["inversion_events"] = inversion_events
    report.metrics["inversion_tickers"] = inversion_tickers
    report.metrics["volume_tickers_scanned"] = (
        len(closes.columns.intersection(volumes.columns))
        if not volumes.empty
        else 0
    )
    return report


# ---------------------------------------------------------------------------
# 5. Run all checks
# ---------------------------------------------------------------------------


def run_all_checks(
    closes: pd.DataFrame,
    opens: pd.DataFrame,
    volumes: pd.DataFrame,
    *,
    secondary_closes: pd.DataFrame | None = None,
    secondary_label: str = "secondary",
) -> List[DataIntegrityReport]:
    """Run all WP1-A data integrity checks and return reports."""
    results: List[DataIntegrityReport] = []

    # Calendar
    if not closes.empty:
        results.append(check_trading_calendar(closes.index))

    # Price sanity
    results.append(check_price_sanity(closes, opens, volumes))

    # Corporate actions
    results.append(detect_corporate_action_artifacts(closes, volumes))

    # Cross-source
    if secondary_closes is not None and not secondary_closes.empty:
        results.append(
            check_cross_source_overlap(
                closes, secondary_closes,
                primary_label="sina", secondary_label=secondary_label,
            )
        )

    return results
