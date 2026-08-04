"""Competition window policy: embargo, holding period, and entry/exit rules.

This module is the single source of truth for the official competition time
protocol.  Every evaluation script imports it so the embargo is defined in
exactly one place and cannot drift between direct, unified-baseline, Phase B,
and formal paths.
"""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Iterable
from typing import List, NamedTuple

import pandas as pd


class WindowDates(NamedTuple):
    """All dates for a single competition evaluation window."""

    decision_date: pd.Timestamp   # last date whose close enters the decision
    embargo_date: pd.Timestamp    # trading day whose data must NOT enter the decision
    entry_date: pd.Timestamp      # buy at this day's open
    exit_date: pd.Timestamp       # value at this day's close
    valuation_dates: List[pd.Timestamp]  # 20 close dates for daily NAV


@dataclass(frozen=True)
class CompetitionWindowPolicy:
    """Official competition time protocol.

    Immutable so every consumer sees the same rules.  The defaults match the
    confirmed 2026 competition schedule:

    * One full trading-day embargo between decision-close and entry-open.
    * Buy once at entry-open; hold fixed shares for 20 trading days.
    * Value at each close; final valuation at the 20th close.
    """

    embargo_trading_days: int = 1
    holding_days: int = 20
    entry: str = "open"
    exit: str = "close"

    # ------------------------------------------------------------------
    # Derived quantities
    # ------------------------------------------------------------------

    @property
    def total_forward_days(self) -> int:
        """Total trading days consumed by embargo + holding."""
        return self.embargo_trading_days + self.holding_days

    # ------------------------------------------------------------------
    # Schedule construction
    # ------------------------------------------------------------------

    def adjust_schedule(self, n_days: int, min_history: int) -> list[int]:
        """Return non-overlapping window *start* indices.

        Each ``start`` is the index of the **embargo day** (the first
        forward day whose data must not enter the decision).  History ends
        at ``start - 1``; the entry-open is at ``start + embargo_trading_days``.

        Windows are spaced by *holding_days* so they never overlap.
        """
        return list(range(
            min_history,
            n_days - self.total_forward_days + 1,
            self.holding_days,
        ))

    # ------------------------------------------------------------------
    # Per-window date computation
    # ------------------------------------------------------------------

    def get_window(
        self, calendar: pd.DatetimeIndex, start_idx: int,
    ) -> WindowDates:
        """Compute every date for the window whose embargo day is *start_idx*.

        Args:
            calendar: The sorted trading-day index shared by all price frames.
            start_idx: Position of the embargo day within *calendar*.

        Returns:
            A ``WindowDates`` with all five date slots populated.
        """
        decision_date = calendar[start_idx - 1]
        embargo_date = calendar[start_idx]
        entry_idx = start_idx + self.embargo_trading_days
        entry_date = calendar[entry_idx]
        exit_idx = entry_idx + self.holding_days - 1
        exit_date = calendar[exit_idx]
        valuation_dates = [
            calendar[entry_idx + i] for i in range(self.holding_days)
        ]
        return WindowDates(
            decision_date=decision_date,
            embargo_date=embargo_date,
            entry_date=entry_date,
            exit_date=exit_date,
            valuation_dates=valuation_dates,
        )

    # ------------------------------------------------------------------
    # Data slicing
    # ------------------------------------------------------------------

    def slice_window(
        self,
        opens: pd.DataFrame,
        closes: pd.DataFrame,
        start_idx: int,
    ) -> tuple[pd.Series, pd.DataFrame]:
        """Return ``(entry_open, test_closes)`` for an embargo-compliant window.

        Args:
            opens: DataFrame of open prices (rows = calendar days).
            closes: DataFrame of close prices (rows = calendar days).
            start_idx: Embargo-day index (same semantics as *adjust_schedule*).

        Returns:
            ``entry_open`` – the open prices on the entry date.
            ``test_closes`` – the ``holding_days`` close prices for valuation.
        """
        entry_idx = start_idx + self.embargo_trading_days
        exit_idx = entry_idx + self.holding_days
        test_closes = closes.iloc[entry_idx:exit_idx]
        entry_open = opens.iloc[entry_idx]
        return entry_open, test_closes

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate_embargo(self, history_len: int, start_idx: int) -> None:
        """Raise ``ValueError`` if the decision history covers the embargo day.

        Args:
            history_len: Number of rows in the history slice (``len(history)``).
            start_idx: The embargo-day index.
        """
        if history_len > start_idx:
            raise ValueError(
                f"Embargo violation: decision history has {history_len} rows "
                f"but must end at index {start_idx - 1} "
                f"(embargo day is at index {start_idx})"
            )

    @staticmethod
    def _shanghai_timestamp(value: object) -> pd.Timestamp:
        timestamp = pd.Timestamp(value)
        if timestamp.tzinfo is None:
            return timestamp.tz_localize("Asia/Shanghai")
        return timestamp.tz_convert("Asia/Shanghai")

    def validate_decision_inputs(
        self,
        window: WindowDates,
        *,
        price_last_timestamp: object,
        factor_timestamps: Iterable[object] = (),
        evidence_timestamps: Iterable[object] = (),
    ) -> None:
        """Fail closed when any decision input crosses the information cutoff.

        Daily prices and factors may use the decision date but never the
        embargo date. Timestamped evidence must be available no later than the
        decision-day 15:00 Asia/Shanghai close.
        """

        decision_day = self._shanghai_timestamp(window.decision_date).normalize()
        decision_close = decision_day + pd.Timedelta(hours=15)
        price_last = self._shanghai_timestamp(price_last_timestamp)
        if price_last > decision_close:
            raise ValueError(
                f"price timestamp {price_last.isoformat()} exceeds decision close "
                f"{decision_close.isoformat()}"
            )
        for value in factor_timestamps:
            timestamp = self._shanghai_timestamp(value)
            if timestamp > decision_close:
                raise ValueError(
                    f"factor timestamp {timestamp.isoformat()} exceeds decision "
                    f"close {decision_close.isoformat()}"
                )
        for value in evidence_timestamps:
            timestamp = self._shanghai_timestamp(value)
            if timestamp > decision_close:
                raise ValueError(
                    f"evidence timestamp {timestamp.isoformat()} exceeds decision "
                    f"close {decision_close.isoformat()}"
                )

    def serialize_window(self, window: WindowDates) -> dict[str, object]:
        """Return the exact machine-readable competition date sequence."""

        valuation_dates = [str(value.date()) for value in window.valuation_dates]
        if len(valuation_dates) != self.holding_days:
            raise ValueError(
                f"Expected {self.holding_days} valuation dates, got "
                f"{len(valuation_dates)}"
            )
        if window.entry_date != window.valuation_dates[0]:
            raise ValueError("Entry date must equal the first valuation date")
        if window.exit_date != window.valuation_dates[-1]:
            raise ValueError("Exit date must equal the final valuation date")
        return {
            "decision_date": str(window.decision_date.date()),
            "embargo_date": str(window.embargo_date.date()),
            "entry_date": str(window.entry_date.date()),
            "valuation_dates": valuation_dates,
            "exit_date": str(window.exit_date.date()),
        }

    def __repr__(self) -> str:
        return (
            f"CompetitionWindowPolicy(embargo={self.embargo_trading_days}d, "
            f"holding={self.holding_days}d, entry={self.entry}, exit={self.exit})"
        )
