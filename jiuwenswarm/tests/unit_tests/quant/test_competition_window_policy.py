"""Tests for CompetitionWindowPolicy — embargo, holding, entry/exit rules."""

from __future__ import annotations

import pandas as pd
import pytest

from jiuwenswarm.quant.evaluation_protocol import CompetitionWindowPolicy


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def policy() -> CompetitionWindowPolicy:
    return CompetitionWindowPolicy()


@pytest.fixture
def calendar() -> pd.DatetimeIndex:
    """A 200-day trading calendar (Mon-Fri, no holidays)."""
    return pd.bdate_range("2026-01-05", periods=200, freq="B")


@pytest.fixture
def price_frame(calendar: pd.DatetimeIndex) -> pd.DataFrame:
    """Synthetic OHLC data for 5 tickers aligned with the calendar."""
    return pd.DataFrame(
        {
            "100000.SH": range(1000, 1200),
            "200000.SZ": range(2000, 2200),
            "300000.SH": range(3000, 3200),
            "400000.SZ": range(4000, 4200),
            "500000.SH": range(5000, 5200),
        },
        index=calendar,
        dtype=float,
    )


# ---------------------------------------------------------------------------
# Immutability
# ---------------------------------------------------------------------------

def test_policy_is_immutable(policy: CompetitionWindowPolicy) -> None:
    with pytest.raises(Exception):
        policy.embargo_trading_days = 2  # type: ignore[misc]


def test_default_values_match_competition_rules() -> None:
    p = CompetitionWindowPolicy()
    assert p.embargo_trading_days == 1
    assert p.holding_days == 20
    assert p.entry == "open"
    assert p.exit == "close"
    assert p.total_forward_days == 21


# ---------------------------------------------------------------------------
# Schedule adjustment
# ---------------------------------------------------------------------------

def test_schedule_starts_at_min_history(policy: CompetitionWindowPolicy) -> None:
    starts = policy.adjust_schedule(n_days=500, min_history=80)
    assert starts[0] == 80


def test_schedule_leaves_room_for_embargo_and_holding(
    policy: CompetitionWindowPolicy,
) -> None:
    """Last window's entry + holding must not exceed n_days."""
    n_days = 500
    starts = policy.adjust_schedule(n_days, 80)
    last_start = starts[-1]
    entry_idx = last_start + policy.embargo_trading_days
    exit_idx = entry_idx + policy.holding_days
    assert exit_idx <= n_days, (
        f"Last window exit {exit_idx} exceeds n_days {n_days}"
    )


def test_schedule_no_overlap(policy: CompetitionWindowPolicy) -> None:
    """Windows must be exactly holding_days apart (non-overlapping)."""
    starts = policy.adjust_schedule(n_days=500, min_history=80)
    for a, b in zip(starts, starts[1:]):
        assert b - a == policy.holding_days, f"Overlap or gap at {a} → {b}"


def test_schedule_count_with_embargo(policy: CompetitionWindowPolicy) -> None:
    """With embargo=1, we lose one window compared to no-embargo."""
    starts = policy.adjust_schedule(n_days=500, min_history=80)
    # No-embargo would give: range(80, 500-20+1, 20) → 21 windows
    # With embargo:        range(80, 500-21+1, 20) → 20 windows
    assert len(starts) == 20


def test_schedule_insufficient_data_returns_empty(policy: CompetitionWindowPolicy) -> None:
    """90 days total needs 80 + 21 = 101 → empty schedule."""
    starts = policy.adjust_schedule(n_days=90, min_history=80)
    assert starts == []


# ---------------------------------------------------------------------------
# Window date computation
# ---------------------------------------------------------------------------

def test_get_window_dates_are_sequential(
    policy: CompetitionWindowPolicy, calendar: pd.DatetimeIndex,
) -> None:
    window = policy.get_window(calendar, start_idx=80)
    assert window.decision_date < window.embargo_date < window.entry_date
    assert window.entry_date < window.exit_date


def test_embargo_is_exactly_one_day_after_decision(
    policy: CompetitionWindowPolicy, calendar: pd.DatetimeIndex,
) -> None:
    window = policy.get_window(calendar, start_idx=80)
    # On a business-day calendar, embargo_date is the next business day
    assert window.embargo_date == window.decision_date + pd.offsets.BDay(1)


def test_entry_is_after_embargo(
    policy: CompetitionWindowPolicy, calendar: pd.DatetimeIndex,
) -> None:
    window = policy.get_window(calendar, start_idx=80)
    assert window.entry_date == window.embargo_date + pd.offsets.BDay(1)


def test_holding_period_is_exactly_20_days(
    policy: CompetitionWindowPolicy, calendar: pd.DatetimeIndex,
) -> None:
    window = policy.get_window(calendar, start_idx=80)
    assert len(window.valuation_dates) == 20


def test_first_valuation_date_is_entry_date(
    policy: CompetitionWindowPolicy, calendar: pd.DatetimeIndex,
) -> None:
    window = policy.get_window(calendar, start_idx=80)
    assert window.valuation_dates[0] == window.entry_date


def test_last_valuation_date_is_exit_date(
    policy: CompetitionWindowPolicy, calendar: pd.DatetimeIndex,
) -> None:
    window = policy.get_window(calendar, start_idx=80)
    assert window.valuation_dates[-1] == window.exit_date


def test_get_window_across_all_schedule_positions(
    policy: CompetitionWindowPolicy, calendar: pd.DatetimeIndex,
) -> None:
    """Every window from adjust_schedule produces valid dates."""
    starts = policy.adjust_schedule(len(calendar), min_history=80)
    for start_idx in starts:
        window = policy.get_window(calendar, start_idx)
        assert len(window.valuation_dates) == 20
        # All dates are within calendar bounds
        assert window.entry_date in calendar
        assert window.exit_date in calendar


# ---------------------------------------------------------------------------
# Data slicing
# ---------------------------------------------------------------------------

def test_slice_window_returns_correct_shapes(
    policy: CompetitionWindowPolicy, price_frame: pd.DataFrame,
) -> None:
    opens = price_frame.copy()
    closes = price_frame.copy()
    entry_open, test_closes = policy.slice_window(opens, closes, start_idx=80)
    assert len(entry_open) == 5  # 5 tickers
    assert len(test_closes) == policy.holding_days
    assert list(test_closes.columns) == list(price_frame.columns)


def test_slice_window_entry_is_after_embargo(
    policy: CompetitionWindowPolicy, price_frame: pd.DataFrame,
) -> None:
    """Entry open comes from start_idx + embargo_trading_days."""
    opens = price_frame.copy()
    closes = price_frame.copy()
    entry_open, _test_closes = policy.slice_window(opens, closes, start_idx=80)
    # entry_open should equal opens.iloc[81] (start_idx + 1)
    pd.testing.assert_series_equal(
        entry_open, opens.iloc[81], check_names=False,
    )


def test_slice_window_first_close_is_entry_date_close(
    policy: CompetitionWindowPolicy, price_frame: pd.DataFrame,
) -> None:
    opens = price_frame.copy()
    closes = price_frame.copy()
    _entry_open, test_closes = policy.slice_window(opens, closes, start_idx=80)
    # first close = closes.iloc[81], same date as entry open
    pd.testing.assert_series_equal(
        test_closes.iloc[0], closes.iloc[81], check_names=False,
    )


def test_slice_window_last_close_is_exit_date(
    policy: CompetitionWindowPolicy, price_frame: pd.DataFrame,
) -> None:
    opens = price_frame.copy()
    closes = price_frame.copy()
    _entry_open, test_closes = policy.slice_window(opens, closes, start_idx=80)
    # exit = 81 + 20 - 1 = 100 → closes.iloc[100]
    pd.testing.assert_series_equal(
        test_closes.iloc[-1], closes.iloc[100], check_names=False,
    )


# ---------------------------------------------------------------------------
# Embargo validation (negative tests)
# ---------------------------------------------------------------------------

def test_validate_embargo_passes_when_history_ends_before_embargo(
    policy: CompetitionWindowPolicy,
) -> None:
    """history_len == start_idx → history ends at start_idx-1 → OK."""
    policy.validate_embargo(history_len=80, start_idx=80)


def test_validate_embargo_passes_when_history_shorter(
    policy: CompetitionWindowPolicy,
) -> None:
    policy.validate_embargo(history_len=79, start_idx=80)


def test_validate_embargo_fails_when_history_covers_embargo_day(
    policy: CompetitionWindowPolicy,
) -> None:
    """If history_len > start_idx, the embargo day's data entered the decision."""
    with pytest.raises(ValueError, match="Embargo violation"):
        policy.validate_embargo(history_len=81, start_idx=80)


def test_validate_embargo_fails_well_above_start(
    policy: CompetitionWindowPolicy,
) -> None:
    with pytest.raises(ValueError, match="Embargo violation"):
        policy.validate_embargo(history_len=100, start_idx=80)


def test_serialized_window_contains_exact_valuation_dates(
    policy: CompetitionWindowPolicy, calendar: pd.DatetimeIndex,
) -> None:
    window = policy.get_window(calendar, start_idx=80)
    payload = policy.serialize_window(window)
    assert payload["decision_date"] == str(calendar[79].date())
    assert payload["embargo_date"] == str(calendar[80].date())
    assert payload["entry_date"] == str(calendar[81].date())
    assert payload["valuation_dates"] == [
        str(value.date()) for value in calendar[81:101]
    ]
    assert payload["exit_date"] == payload["valuation_dates"][-1]


def test_embargo_day_factor_timestamp_fails_closed(
    policy: CompetitionWindowPolicy, calendar: pd.DatetimeIndex,
) -> None:
    window = policy.get_window(calendar, start_idx=80)
    with pytest.raises(ValueError, match="factor timestamp"):
        policy.validate_decision_inputs(
            window,
            price_last_timestamp=window.decision_date,
            factor_timestamps=[window.embargo_date],
        )


def test_decision_day_post_close_price_and_factor_fail_closed(
    policy: CompetitionWindowPolicy, calendar: pd.DatetimeIndex,
) -> None:
    window = policy.get_window(calendar, start_idx=80)
    with pytest.raises(ValueError, match="price timestamp"):
        policy.validate_decision_inputs(
            window,
            price_last_timestamp=window.decision_date + pd.Timedelta(hours=16),
        )
    with pytest.raises(ValueError, match="factor timestamp"):
        policy.validate_decision_inputs(
            window,
            price_last_timestamp=window.decision_date,
            factor_timestamps=[window.decision_date + pd.Timedelta(hours=16)],
        )


def test_post_close_or_embargo_evidence_fails_closed(
    policy: CompetitionWindowPolicy, calendar: pd.DatetimeIndex,
) -> None:
    window = policy.get_window(calendar, start_idx=80)
    with pytest.raises(ValueError, match="evidence timestamp"):
        policy.validate_decision_inputs(
            window,
            price_last_timestamp=window.decision_date,
            evidence_timestamps=[window.decision_date + pd.Timedelta(hours=16)],
        )

    with pytest.raises(ValueError, match="evidence timestamp"):
        policy.validate_decision_inputs(
            window,
            price_last_timestamp=window.decision_date,
            evidence_timestamps=[window.embargo_date],
        )


def test_decision_day_pre_close_evidence_is_allowed(
    policy: CompetitionWindowPolicy, calendar: pd.DatetimeIndex,
) -> None:
    window = policy.get_window(calendar, start_idx=80)
    policy.validate_decision_inputs(
        window,
        price_last_timestamp=window.decision_date,
        factor_timestamps=[window.decision_date],
        evidence_timestamps=[window.decision_date + pd.Timedelta(hours=14)],
    )


# ---------------------------------------------------------------------------
# Repr
# ---------------------------------------------------------------------------

def test_repr_includes_parameters() -> None:
    p = CompetitionWindowPolicy()
    text = repr(p)
    assert "embargo=1d" in text
    assert "holding=20d" in text
    assert "entry=open" in text
    assert "exit=close" in text
