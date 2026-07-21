"""Time-causality tests for the walk-forward IC evaluator."""

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd


MODULE_PATH = (
    Path(__file__).resolve().parents[3] / "evaluation" / "ic_walk_forward.py"
)
SPEC = importlib.util.spec_from_file_location("ic_walk_forward", MODULE_PATH)
IC = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(IC)


def test_schedule_is_non_overlapping_and_seals_tail():
    development, holdout = IC.build_schedule(
        n_days=240, min_history=80, horizon=20, holdout_windows=2,
    )
    all_starts = development + holdout
    assert all(b - a == 20 for a, b in zip(all_starts, all_starts[1:]))
    assert holdout == all_starts[-2:]
    assert set(development).isdisjoint(holdout)


def test_forward_return_starts_at_decision_close_and_has_full_horizon():
    index = pd.date_range("2026-01-01", periods=30, freq="B")
    prices = pd.DataFrame({"A": np.arange(100.0, 130.0)}, index=index)
    result = IC.forward_returns(prices, start_idx=5, horizon=20)
    expected = prices["A"].iloc[24] / prices["A"].iloc[4] - 1.0
    assert abs(result["A"] - expected) < 1e-12


def test_missing_endpoint_is_excluded_not_replaced_with_zero():
    index = pd.date_range("2026-01-01", periods=30, freq="B")
    prices = pd.DataFrame({"A": np.arange(100.0, 130.0)}, index=index)
    prices.loc[index[24], "A"] = np.nan
    result = IC.forward_returns(prices, start_idx=5, horizon=20)
    assert np.isnan(result["A"])
