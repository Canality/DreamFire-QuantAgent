"""Prior-only six-dimensional similar-market neighbor selector.

Research-only.  Returns deterministic neighbor evidence for one query market
state using expanding-prior matured historical states.  Never constructs raw
six-dimensional features, never imports or activates production, and never
throws: every fail-closed branch returns a stable reason code and empty
neighbors.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from math import isfinite
from statistics import median
from typing import Any, Iterable

FEATURE_ORDER: tuple[str, ...] = (
    "benchmark_momentum_20",
    "benchmark_momentum_60",
    "benchmark_volatility_20",
    "ma20_width",
    "industry_dispersion_20",
    "volume_width",
)

_BENCHMARK_FEATURES = FEATURE_ORDER[:3]
_WIDTH_FEATURES = FEATURE_ORDER[3:]

MIN_HISTORY_STATES = 60
NEIGHBOR_COUNT = 5

REASON_OK = "OK"
REASON_BENCHMARK_UNAVAILABLE = "BENCHMARK_UNAVAILABLE"
REASON_MISSING_FEATURE = "MISSING_FEATURE"
REASON_NONFINITE_FEATURE = "NONFINITE_FEATURE"
REASON_ZERO_MAD = "ZERO_MAD"
REASON_INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
REASON_INSUFFICIENT_NEIGHBORS = "INSUFFICIENT_NEIGHBORS"
REASON_INVALID_STATE = "INVALID_STATE"

_HEX64 = re.compile(r"^[0-9a-fA-F]{64}$")


@dataclass(frozen=True)
class MarketFeatureState:
    """One hash-bound market snapshot with precomputed six features.

    Benchmark features are ``None`` when no trusted benchmark artifact exists
    (the repository reality until a separate provider task lands).
    """

    decision_date: str
    label_end_date: str
    market_snapshot_hash: str
    benchmark_momentum_20: float | None
    benchmark_momentum_60: float | None
    benchmark_volatility_20: float | None
    ma20_width: float | None
    industry_dispersion_20: float | None
    volume_width: float | None

    def _features(self) -> tuple[float | None, ...]:
        return tuple(getattr(self, name) for name in FEATURE_ORDER)


@dataclass(frozen=True)
class SimilarityNeighbor:
    """One selected matured prior neighbor and its auditable distance."""

    decision_date: str
    label_end_date: str
    market_snapshot_hash: str
    distance: float
    robust_z: tuple[float, ...]


@dataclass(frozen=True)
class SimilarMarketEvidence:
    """Deterministic, immutable selection result for one research decision."""

    reason_code: str
    decision_date: str
    neighbors: tuple[SimilarityNeighbor, ...]
    qualified_history_count: int
    per_dimension_median: tuple[float, ...] | None
    per_dimension_mad: tuple[float, ...] | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "reason_code": self.reason_code,
            "decision_date": self.decision_date,
            "neighbors": [
                {
                    "decision_date": neighbor.decision_date,
                    "label_end_date": neighbor.label_end_date,
                    "market_snapshot_hash": neighbor.market_snapshot_hash,
                    "distance": neighbor.distance,
                    "robust_z": list(neighbor.robust_z),
                }
                for neighbor in self.neighbors
            ],
            "qualified_history_count": self.qualified_history_count,
            "per_dimension_median": (
                None
                if self.per_dimension_median is None
                else list(self.per_dimension_median)
            ),
            "per_dimension_mad": (
                None if self.per_dimension_mad is None else list(self.per_dimension_mad)
            ),
        }


def _fail(
    reason: str, *, decision_date: str, count: int = 0
) -> SimilarMarketEvidence:
    return SimilarMarketEvidence(
        reason_code=reason,
        decision_date=decision_date,
        neighbors=(),
        qualified_history_count=count,
        per_dimension_median=None,
        per_dimension_mad=None,
    )


def _validate_state(state: MarketFeatureState) -> str | None:
    try:
        decision = date.fromisoformat(state.decision_date)
        label_end = date.fromisoformat(state.label_end_date)
    except (TypeError, ValueError):
        return REASON_INVALID_STATE
    if decision >= label_end:
        return REASON_INVALID_STATE
    if not isinstance(state.market_snapshot_hash, str) or not _HEX64.fullmatch(
        state.market_snapshot_hash
    ):
        return REASON_INVALID_STATE
    for name, value in zip(FEATURE_ORDER, state._features()):
        if value is None:
            if name in _BENCHMARK_FEATURES:
                return REASON_BENCHMARK_UNAVAILABLE
            return REASON_MISSING_FEATURE
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not isfinite(value)
        ):
            return REASON_NONFINITE_FEATURE
    return None


def _history_eligibility(
    state: MarketFeatureState, query_decision: date
) -> str | None:
    """Classify one history record before any feature validation.

    Returns ``"eligible"`` for strictly-prior matured states, ``"ignore"`` for
    future / same-date / unmatured states, or ``None`` when the record's dates
    cannot be read or parsed (fail closed with INVALID_STATE).  Ineligible
    records never reach feature validation, dedup, scale or distance.
    """

    decision_raw = getattr(state, "decision_date", None)
    label_end_raw = getattr(state, "label_end_date", None)
    try:
        decision = date.fromisoformat(decision_raw)
        label_end = date.fromisoformat(label_end_raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(state, MarketFeatureState):
        return None
    if decision < query_decision and label_end < query_decision:
        return "eligible"
    return "ignore"


def select_similar_market_neighbors(
    query: MarketFeatureState,
    history: Iterable[MarketFeatureState],
) -> SimilarMarketEvidence:
    """Select up to five matured prior states most similar to ``query``.

    Only expanding-prior states strictly before the query decision date with
    matured labels enter scale and distance.  Any structural, feature, scale or
    neighbor deficit closes the branch with a stable reason code and empty
    neighbors.
    """

    query_reason = _validate_state(query)
    if query_reason is not None:
        return _fail(query_reason, decision_date=query.decision_date)

    query_decision = date.fromisoformat(query.decision_date)
    raw_states = tuple(history)

    eligible: list[MarketFeatureState] = []
    for state in raw_states:
        eligibility = _history_eligibility(state, query_decision)
        if eligibility is None:
            return _fail(REASON_INVALID_STATE, decision_date=query.decision_date)
        if eligibility == "eligible":
            eligible.append(state)

    for state in eligible:
        reason = _validate_state(state)
        if reason is not None:
            return _fail(reason, decision_date=query.decision_date)

    unique: dict[tuple[str, str], MarketFeatureState] = {}
    for state in eligible:
        key = (state.decision_date, state.market_snapshot_hash)
        existing = unique.get(key)
        if existing is None:
            unique[key] = state
            continue
        if existing != state:
            return _fail(REASON_INVALID_STATE, decision_date=query.decision_date)

    qualified = tuple(unique.values())
    if len(qualified) < MIN_HISTORY_STATES:
        return _fail(
            REASON_INSUFFICIENT_HISTORY,
            decision_date=query.decision_date,
            count=len(qualified),
        )

    columns = tuple(zip(*(state._features() for state in qualified)))
    per_dimension_median = tuple(float(median(column)) for column in columns)
    per_dimension_mad = tuple(
        float(median(abs(value - med) for value in column))
        for column, med in zip(columns, per_dimension_median)
    )
    if any(mad == 0.0 for mad in per_dimension_mad):
        return _fail(
            REASON_ZERO_MAD, decision_date=query.decision_date, count=len(qualified)
        )

    query_features = query._features()
    scored: list[tuple[float, MarketFeatureState, tuple[float, ...]]] = []
    for state in qualified:
        robust_z = tuple(
            float((q - h) / mad)
            for q, h, mad in zip(query_features, state._features(), per_dimension_mad)
        )
        scored.append((float(sum(abs(z) for z in robust_z)), state, robust_z))

    scored.sort(
        key=lambda item: (
            item[0],
            item[1].decision_date,
            item[1].market_snapshot_hash,
        )
    )

    picked: list[SimilarityNeighbor] = []
    picked_ranges: list[tuple[date, date]] = []
    for distance, state, robust_z in scored:
        if len(picked) >= NEIGHBOR_COUNT:
            break
        start = date.fromisoformat(state.decision_date)
        end = date.fromisoformat(state.label_end_date)
        if any(
            start <= other_end and other_start <= end
            for other_start, other_end in picked_ranges
        ):
            continue
        picked.append(
            SimilarityNeighbor(
                decision_date=state.decision_date,
                label_end_date=state.label_end_date,
                market_snapshot_hash=state.market_snapshot_hash,
                distance=distance,
                robust_z=robust_z,
            )
        )
        picked_ranges.append((start, end))

    if len(picked) < NEIGHBOR_COUNT:
        return _fail(
            REASON_INSUFFICIENT_NEIGHBORS,
            decision_date=query.decision_date,
            count=len(qualified),
        )

    return SimilarMarketEvidence(
        reason_code=REASON_OK,
        decision_date=query.decision_date,
        neighbors=tuple(picked),
        qualified_history_count=len(qualified),
        per_dimension_median=per_dimension_median,
        per_dimension_mad=per_dimension_mad,
    )
