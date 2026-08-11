"""Tests for the prior-only six-dimensional similar-market neighbor selector."""

from __future__ import annotations

import hashlib
import json
from dataclasses import FrozenInstanceError, is_dataclass, replace
from datetime import date, timedelta
from pathlib import Path

import pytest

from jiuwenswarm.quant.market_similarity import (
    FEATURE_ORDER,
    MIN_HISTORY_STATES,
    NEIGHBOR_COUNT,
    MarketFeatureState,
    REASON_BENCHMARK_UNAVAILABLE,
    REASON_INSUFFICIENT_HISTORY,
    REASON_INSUFFICIENT_NEIGHBORS,
    REASON_INVALID_STATE,
    REASON_MISSING_FEATURE,
    REASON_NONFINITE_FEATURE,
    REASON_OK,
    REASON_ZERO_MAD,
    SimilarMarketEvidence,
    SimilarityNeighbor,
    select_similar_market_neighbors,
)

_REPO_ROOT = Path(__file__).resolve().parents[4]

_QUERY_FEATURES = {
    "benchmark_momentum_20": 0.02,
    "benchmark_momentum_60": 0.04,
    "benchmark_volatility_20": 0.10,
    "ma20_width": 0.20,
    "industry_dispersion_20": 0.30,
    "volume_width": 0.40,
}


def _hash(decision_date: str, tag: str = "a") -> str:
    return hashlib.sha256(f"{decision_date}:{tag}".encode("utf-8")).hexdigest()


def _add_days(value: str, days: int) -> str:
    return (date.fromisoformat(value) + timedelta(days=days)).isoformat()


def make_state(
    decision_date: str,
    *,
    label_span_days: int = 25,
    tag: str = "a",
    benchmark_momentum_20: float | None = 0.02,
    benchmark_momentum_60: float | None = 0.04,
    benchmark_volatility_20: float | None = 0.10,
    ma20_width: float | None = 0.20,
    industry_dispersion_20: float | None = 0.30,
    volume_width: float | None = 0.40,
    market_snapshot_hash: str | None = None,
) -> MarketFeatureState:
    return MarketFeatureState(
        decision_date=decision_date,
        label_end_date=_add_days(decision_date, label_span_days),
        market_snapshot_hash=market_snapshot_hash or _hash(decision_date, tag),
        benchmark_momentum_20=benchmark_momentum_20,
        benchmark_momentum_60=benchmark_momentum_60,
        benchmark_volatility_20=benchmark_volatility_20,
        ma20_width=ma20_width,
        industry_dispersion_20=industry_dispersion_20,
        volume_width=volume_width,
    )


def default_query() -> MarketFeatureState:
    return make_state("2024-06-03")


def far_state(i: int, *, span: int = 5) -> MarketFeatureState:
    decision = _add_days("2020-01-02", i * 7)
    offset = (1.0 + i % 5) * 0.5
    return make_state(
        decision,
        label_span_days=span,
        tag=f"far{i}",
        benchmark_momentum_20=_QUERY_FEATURES["benchmark_momentum_20"] + offset,
        benchmark_momentum_60=_QUERY_FEATURES["benchmark_momentum_60"] + offset,
        benchmark_volatility_20=_QUERY_FEATURES["benchmark_volatility_20"] + offset,
        ma20_width=_QUERY_FEATURES["ma20_width"] + offset,
        industry_dispersion_20=_QUERY_FEATURES["industry_dispersion_20"] + offset,
        volume_width=_QUERY_FEATURES["volume_width"] + offset,
    )


def default_history(near_count: int = 5, total: int = 60) -> list[MarketFeatureState]:
    assert total > near_count
    return [far_state(i) for i in range(total - near_count)] + [
        make_state(
            _add_days("2020-01-02", i * 7),
            label_span_days=5,
            tag=f"near{i}",
        )
        for i in range(total - near_count, total)
    ]


def test_feature_order_is_fixed_six_dimensions() -> None:
    assert FEATURE_ORDER == (
        "benchmark_momentum_20",
        "benchmark_momentum_60",
        "benchmark_volatility_20",
        "ma20_width",
        "industry_dispersion_20",
        "volume_width",
    )


def test_success_selects_five_non_overlapping_neighbors() -> None:
    query = default_query()
    result = select_similar_market_neighbors(query, default_history())
    assert result.reason_code == REASON_OK
    assert result.decision_date == query.decision_date
    assert result.qualified_history_count == 60
    assert len(result.neighbors) == NEIGHBOR_COUNT
    # The five exact-feature states are the closest; selected in date order.
    expected_dates = [_add_days("2020-01-02", i * 7) for i in range(55, 60)]
    assert [n.decision_date for n in result.neighbors] == expected_dates
    # Closed intervals [decision_date, label_end_date] are pairwise disjoint.
    for i, a in enumerate(result.neighbors):
        a_start = date.fromisoformat(a.decision_date)
        a_end = date.fromisoformat(a.label_end_date)
        for b in result.neighbors[i + 1 :]:
            b_start = date.fromisoformat(b.decision_date)
            b_end = date.fromisoformat(b.label_end_date)
            assert not (a_start <= b_end and b_start <= a_end)
    for n in result.neighbors:
        assert n.distance == 0.0
        assert len(n.robust_z) == 6
        assert all(z == 0.0 for z in n.robust_z)
        assert len(n.market_snapshot_hash) == 64
        int(n.market_snapshot_hash, 16)
    assert result.per_dimension_median is not None
    assert result.per_dimension_mad is not None
    assert len(result.per_dimension_median) == 6
    assert len(result.per_dimension_mad) == 6


def test_exactly_sixty_history_states_succeeds() -> None:
    result = select_similar_market_neighbors(default_query(), default_history(total=60))
    assert result.reason_code == REASON_OK
    assert result.qualified_history_count == 60


def test_insufficient_history_below_sixty() -> None:
    history = [far_state(i) for i in range(59)]
    result = select_similar_market_neighbors(default_query(), history)
    assert result.reason_code == REASON_INSUFFICIENT_HISTORY
    assert result.qualified_history_count == 59
    assert result.neighbors == ()


def test_poison_states_never_enter_selection() -> None:
    query = default_query()
    clean = select_similar_market_neighbors(query, default_history())
    poison_future = make_state(
        _add_days(query.decision_date, 1), label_span_days=5, tag="future"
    )
    poison_same_date = make_state(query.decision_date, label_span_days=5, tag="same")
    poison_unmatured = make_state(
        _add_days(query.decision_date, -30), label_span_days=500, tag="un"
    )
    poisoned = select_similar_market_neighbors(
        query, [*default_history(), poison_future, poison_same_date, poison_unmatured]
    )
    assert poisoned.reason_code == clean.reason_code
    assert poisoned.neighbors == clean.neighbors
    assert poisoned.qualified_history_count == 60


@pytest.mark.parametrize(
    "build_poison",
    [
        # future with broken feature, hash, and duplicate conflict
        lambda query: [make_state("2027-01-01", benchmark_momentum_20=None, tag="f1")],
        lambda query: [make_state("2027-01-01", market_snapshot_hash="short", tag="f2")],
        lambda query: [
            make_state("2027-01-01", market_snapshot_hash="c" * 64, ma20_width=0.2),
            make_state("2027-01-01", market_snapshot_hash="c" * 64, ma20_width=0.9),
        ],
        # same-date with broken feature and hash
        lambda query: [
            make_state(query.decision_date, benchmark_momentum_20=None, tag="s1")
        ],
        lambda query: [
            make_state(query.decision_date, market_snapshot_hash="short", tag="s2")
        ],
        # unmatured with broken feature and hash
        lambda query: [
            make_state(
                _add_days(query.decision_date, -30),
                label_span_days=500,
                benchmark_momentum_20=None,
                tag="u1",
            )
        ],
        lambda query: [
            make_state(
                _add_days(query.decision_date, -30),
                label_span_days=500,
                market_snapshot_hash="short",
                tag="u2",
            )
        ],
    ],
)
def test_ineligible_poison_records_with_bad_fields_do_not_affect_result(
    build_poison,
) -> None:
    query = default_query()
    clean = select_similar_market_neighbors(query, default_history())
    assert clean.reason_code == REASON_OK
    poisoned = select_similar_market_neighbors(
        query, [*default_history(), *build_poison(query)]
    )
    assert poisoned.reason_code == REASON_OK
    assert poisoned.neighbors == clean.neighbors
    assert poisoned.qualified_history_count == clean.qualified_history_count


def test_wrong_history_object_none_fails_closed() -> None:
    history = [*default_history(), None]
    result = select_similar_market_neighbors(default_query(), history)
    assert result.reason_code == REASON_INVALID_STATE
    assert result.neighbors == ()


def test_wrong_history_object_dict_fails_closed() -> None:
    history = [*default_history(), {"decision_date": "2020-01-02"}]
    result = select_similar_market_neighbors(default_query(), history)
    assert result.reason_code == REASON_INVALID_STATE
    assert result.neighbors == ()


def test_bool_feature_on_query_fails_closed() -> None:
    query = make_state("2024-06-03", ma20_width=True)
    result = select_similar_market_neighbors(query, [])
    assert result.reason_code == REASON_NONFINITE_FEATURE
    assert result.neighbors == ()


def test_bool_feature_on_eligible_history_fails_closed() -> None:
    history = [make_state("2020-01-02", ma20_width=True)]
    result = select_similar_market_neighbors(default_query(), history)
    assert result.reason_code == REASON_NONFINITE_FEATURE
    assert result.neighbors == ()


def test_bool_feature_on_ineligible_history_is_ignored() -> None:
    query = default_query()
    clean = select_similar_market_neighbors(query, default_history())
    poison = make_state("2027-01-01", ma20_width=True, tag="boolf")
    result = select_similar_market_neighbors(query, [*default_history(), poison])
    assert result.reason_code == REASON_OK
    assert result.neighbors == clean.neighbors


def test_tie_break_equal_distance_orders_by_date() -> None:
    d1 = _add_days("2020-01-02", 55 * 7)
    d2 = _add_days("2020-01-02", 56 * 7)
    near1 = make_state(d1, label_span_days=5, tag="nearA")
    near2 = make_state(d2, label_span_days=5, tag="nearB")
    history = [far_state(i) for i in range(55)] + [near1, near2] + [
        far_state(i) for i in (55, 56, 57)
    ]
    result = select_similar_market_neighbors(default_query(), history)
    assert result.reason_code == REASON_OK
    assert result.neighbors[0].decision_date == d1
    assert result.neighbors[1].decision_date == d2
    assert result.neighbors[0].distance == 0.0
    assert result.neighbors[1].distance == 0.0


def test_tie_break_same_date_orders_by_hash() -> None:
    d = _add_days("2020-01-02", 55 * 7)
    near_states = [
        make_state(d, label_span_days=5, tag="zzz"),
        make_state(d, label_span_days=5, tag="aaa"),
        make_state(d, label_span_days=5, tag="mmm"),
    ]
    history = [far_state(i) for i in range(57)] + near_states
    result = select_similar_market_neighbors(default_query(), history)
    assert result.reason_code == REASON_OK
    smallest_hash = min(s.market_snapshot_hash for s in near_states)
    assert result.neighbors[0].decision_date == d
    assert result.neighbors[0].market_snapshot_hash == smallest_hash


def test_zero_mad_closes_branch() -> None:
    query = default_query()
    history = []
    for i in range(60):
        decision = _add_days("2020-01-02", i * 7)
        offset = (1.0 + i % 5) * 0.5
        history.append(
            make_state(
                decision,
                label_span_days=5,
                tag=f"zero{i}",
                benchmark_momentum_20=0.02 + offset,
                benchmark_momentum_60=0.04 + offset,
                benchmark_volatility_20=0.10 + offset,
                ma20_width=0.20 + offset,
                industry_dispersion_20=0.30 + offset,
                volume_width=0.5,
            )
        )
    result = select_similar_market_neighbors(query, history)
    assert result.reason_code == REASON_ZERO_MAD
    assert result.neighbors == ()


def test_insufficient_neighbors_when_all_intervals_overlap() -> None:
    query = default_query()
    history = [
        make_state(
            _add_days("2024-01-02", i),
            label_span_days=60,
            tag=f"ov{i}",
            benchmark_momentum_20=0.02 + (i % 5) * 0.1,
            benchmark_momentum_60=0.04 + (i % 5) * 0.1,
            benchmark_volatility_20=0.10 + (i % 5) * 0.1,
            ma20_width=0.20 + (i % 5) * 0.1,
            industry_dispersion_20=0.30 + (i % 5) * 0.1,
            volume_width=0.40 + (i % 5) * 0.1,
        )
        for i in range(60)
    ]
    result = select_similar_market_neighbors(query, history)
    assert result.reason_code == REASON_INSUFFICIENT_NEIGHBORS
    assert result.qualified_history_count == 60
    assert result.neighbors == ()


def test_benchmark_unavailable_on_query_benchmark_missing() -> None:
    query = make_state("2024-06-03", benchmark_momentum_20=None)
    result = select_similar_market_neighbors(query, [])
    assert result.reason_code == REASON_BENCHMARK_UNAVAILABLE
    assert result.neighbors == ()


def test_benchmark_unavailable_on_history_benchmark_missing() -> None:
    query = default_query()
    history = [make_state("2020-01-02", benchmark_volatility_20=None)]
    result = select_similar_market_neighbors(query, history)
    assert result.reason_code == REASON_BENCHMARK_UNAVAILABLE
    assert result.neighbors == ()


def test_missing_feature_closes_branch() -> None:
    query = make_state("2024-06-03", ma20_width=None)
    result = select_similar_market_neighbors(query, [])
    assert result.reason_code == REASON_MISSING_FEATURE
    assert result.neighbors == ()


def test_nonfinite_feature_inf_closes_branch() -> None:
    query = make_state("2024-06-03", benchmark_momentum_20=float("inf"))
    result = select_similar_market_neighbors(query, [])
    assert result.reason_code == REASON_NONFINITE_FEATURE
    assert result.neighbors == ()


def test_nonfinite_feature_nan_closes_branch() -> None:
    query = make_state("2024-06-03", benchmark_volatility_20=float("nan"))
    result = select_similar_market_neighbors(query, [])
    assert result.reason_code == REASON_NONFINITE_FEATURE
    assert result.neighbors == ()


def test_invalid_state_bad_hash() -> None:
    query = make_state("2024-06-03", market_snapshot_hash="short")
    result = select_similar_market_neighbors(query, [])
    assert result.reason_code == REASON_INVALID_STATE
    assert result.neighbors == ()


def test_invalid_state_bad_date() -> None:
    query = MarketFeatureState(
        decision_date="not-a-date",
        label_end_date="2024-06-04",
        market_snapshot_hash="a" * 64,
        **_QUERY_FEATURES,  # type: ignore[arg-type]
    )
    result = select_similar_market_neighbors(query, [])
    assert result.reason_code == REASON_INVALID_STATE
    assert result.neighbors == ()


def test_invalid_state_decision_at_or_after_label_end() -> None:
    query = MarketFeatureState(
        decision_date="2024-06-03",
        label_end_date="2024-06-03",
        market_snapshot_hash="a" * 64,
        **_QUERY_FEATURES,  # type: ignore[arg-type]
    )
    result = select_similar_market_neighbors(query, [])
    assert result.reason_code == REASON_INVALID_STATE
    assert result.neighbors == ()


def test_duplicate_conflict_fails_closed() -> None:
    base = far_state(0)
    shared_hash = "b" * 64
    dup1 = make_state(
        base.decision_date,
        market_snapshot_hash=shared_hash,
        ma20_width=0.2,
    )
    dup2 = make_state(
        base.decision_date,
        market_snapshot_hash=shared_hash,
        ma20_width=0.9,
    )
    history = [dup1, dup2] + [far_state(i) for i in range(1, 59)]
    result = select_similar_market_neighbors(default_query(), history)
    assert result.reason_code == REASON_INVALID_STATE
    assert result.neighbors == ()


def test_identical_duplicate_is_deduped() -> None:
    base = far_state(0)
    dup = replace(base)
    history = [base, dup] + [far_state(i) for i in range(1, 59)] + [far_state(59)]
    result = select_similar_market_neighbors(default_query(), history)
    assert result.reason_code == REASON_OK
    assert result.qualified_history_count == 60


def test_structures_are_frozen_and_immutable() -> None:
    for cls in (MarketFeatureState, SimilarityNeighbor, SimilarMarketEvidence):
        assert is_dataclass(cls)
    state = make_state("2024-06-03")
    with pytest.raises(FrozenInstanceError):
        state.ma20_width = 1.0  # type: ignore[misc]
    result = select_similar_market_neighbors(default_query(), default_history())
    assert isinstance(result.neighbors, tuple)
    with pytest.raises(FrozenInstanceError):
        result.neighbors[0].distance = 1.0  # type: ignore[misc]


def test_evidence_to_dict_is_json_serializable() -> None:
    result = select_similar_market_neighbors(default_query(), default_history())
    payload = result.to_dict()
    assert payload["reason_code"] == REASON_OK
    assert len(payload["neighbors"]) == NEIGHBOR_COUNT
    assert len(payload["per_dimension_median"]) == 6
    json.dumps(payload)


def test_min_history_and_neighbor_count_constants() -> None:
    assert MIN_HISTORY_STATES == 60
    assert NEIGHBOR_COUNT == 5


@pytest.mark.parametrize(
    "relative_path",
    [
        "jiuwenswarm/scripts/run_quant_pipeline.py",
        "jiuwenswarm/jiuwenswarm/extensions/quant-finance/extension.py",
        "jiuwenswarm/jiuwenswarm/quant/__init__.py",
    ],
)
def test_forbidden_files_do_not_mention_market_similarity(relative_path: str) -> None:
    source = (_REPO_ROOT / relative_path).read_text(encoding="utf-8")
    assert "market_similarity" not in source
