from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from jiuwenswarm.quant.challenger_mechanisms import (
    SECTOR_CANDIDATE,
    TAIL_CANDIDATE,
    TREND_CANDIDATE,
    apply_asymmetric_tail,
    apply_challenger,
    apply_sector_leadership,
    apply_trend_consistency,
)
from jiuwenswarm.quant.stock_pool import ALL_STOCKS, SECTOR_MAP


def _history(rows: int = 80) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    index = pd.bdate_range("2025-01-02", periods=rows)
    values = {}
    for position, ticker in enumerate(ALL_STOCKS):
        daily = 0.0005 + position * 0.00005
        values[ticker] = 100.0 * np.power(1.0 + daily, np.arange(rows))
    closes = pd.DataFrame(values, index=index)
    opens = closes.copy()
    volumes = pd.DataFrame(1_000_000.0, index=index, columns=ALL_STOCKS)
    return closes, opens, volumes


def _base_scores() -> pd.DataFrame:
    return pd.DataFrame({
        "composite": np.linspace(-0.5, 0.5, len(ALL_STOCKS)),
        "sector": [SECTOR_MAP[ticker] for ticker in ALL_STOCKS],
    }, index=ALL_STOCKS)


def test_trend_formula_has_exact_bounds_and_does_not_mutate_base() -> None:
    closes, _, _ = _history()
    base = _base_scores()
    before = base.copy(deep=True)
    result = apply_trend_consistency(base, closes)
    delta = pd.Series(result.diagnostics["score_delta"])
    assert result.candidate_id == TREND_CANDIDATE
    assert delta.min() == pytest.approx(-0.15)
    assert delta.max() == pytest.approx(0.15)
    assert all(result.diagnostics["agreement_gate"].values())
    pd.testing.assert_frame_equal(base, before)


def test_trend_disagreement_gets_exactly_zero_delta() -> None:
    closes, _, _ = _history()
    ticker = ALL_STOCKS[0]
    path = np.full(len(closes), 100.0)
    path[-21:] = np.concatenate([
        np.linspace(120.0, 90.0, 11),
        np.linspace(91.0, 110.0, 10),
    ])
    closes[ticker] = path
    result = apply_trend_consistency(_base_scores(), closes)
    assert result.diagnostics["agreement_gate"][ticker] is False
    assert result.diagnostics["score_delta"][ticker] == 0.0


def test_sector_formula_reuses_exact_six_sector_state_and_is_bounded() -> None:
    closes, _, volumes = _history()
    result = apply_sector_leadership(_base_scores(), closes, volumes)
    leadership = result.diagnostics["sector_leadership_score"]
    delta = pd.Series(result.diagnostics["score_delta"])
    assert result.candidate_id == SECTOR_CANDIDATE
    assert set(leadership) == set(SECTOR_MAP.values())
    assert len(leadership) == 6
    assert -0.10 <= delta.min() <= delta.max() <= 0.10
    assert len(result.diagnostics["top2_leaders"]) == 2


def test_tail_formula_is_zero_below_triggers_and_minus_point_two_at_extreme() -> None:
    closes, opens, _ = _history()
    flat = pd.DataFrame(100.0, index=closes.index, columns=ALL_STOCKS)
    no_penalty = apply_asymmetric_tail(_base_scores(), flat, flat)
    assert set(no_penalty.diagnostics["score_delta"].values()) == {0.0}

    ticker = ALL_STOCKS[0]
    extreme_closes = flat.copy()
    extreme_opens = flat.copy()
    extreme_opens.loc[extreme_opens.index[-1], ticker] = 80.0
    extreme_closes.loc[extreme_closes.index[-1], ticker] = 60.0
    extreme = apply_asymmetric_tail(
        _base_scores(), extreme_closes, extreme_opens
    )
    assert extreme.candidate_id == TAIL_CANDIDATE
    assert extreme.diagnostics["tail_severity"][ticker] == 1.0
    assert extreme.diagnostics["score_delta"][ticker] == -0.20


@pytest.mark.parametrize(
    "candidate_id",
    [TREND_CANDIDATE, SECTOR_CANDIDATE, TAIL_CANDIDATE],
)
def test_dispatch_applies_exactly_one_mechanism(candidate_id: str) -> None:
    closes, opens, volumes = _history()
    result = apply_challenger(
        candidate_id, _base_scores(), closes, opens, volumes
    )
    assert result.candidate_id == candidate_id


def test_unknown_candidate_and_incomplete_universe_fail_closed() -> None:
    closes, opens, volumes = _history()
    with pytest.raises(ValueError, match="Unknown or unregistered"):
        apply_challenger("fourth_candidate", _base_scores(), closes, opens, volumes)
    with pytest.raises(ValueError, match="exact 49-stock"):
        apply_trend_consistency(_base_scores(), closes.drop(columns=ALL_STOCKS[-1]))


def test_missing_or_misaligned_history_fails_closed() -> None:
    closes, opens, volumes = _history()
    with pytest.raises(ValueError, match="at least 21"):
        apply_trend_consistency(_base_scores(), closes.tail(20))
    shifted = opens.copy()
    shifted.index = shifted.index + pd.Timedelta(days=1)
    with pytest.raises(ValueError, match="exact calendar"):
        apply_asymmetric_tail(_base_scores(), closes, shifted)
    volumes.iloc[-1, 0] = np.nan
    with pytest.raises(ValueError, match="non-finite"):
        apply_sector_leadership(_base_scores(), closes, volumes)
