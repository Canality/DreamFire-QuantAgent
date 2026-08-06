"""Research-only point-in-time factor efficacy snapshots for WP1-E1.

The module deliberately has no production imports or exports.  Runtime trust
roots are empty until separate Provider tasks freeze real archived sources, so
the public computation fails closed rather than accepting caller assertions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, time
from enum import Enum
from numbers import Real
from typing import Any, Sequence
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from jiuwenswarm.quant import factor_evidence_provider
from jiuwenswarm.quant.candidate_factors import AVAILABLE, FactorSnapshot
from jiuwenswarm.quant.factor_registry import (
    FACTOR_REGISTRY,
    FACTOR_REGISTRY_HASH,
    FactorDefinition,
    canonical_hash,
)


_SHANGHAI = ZoneInfo("Asia/Shanghai")
_DECISION_CLOSE = time(15, 0)
_HASH_RE = re.compile(r"[0-9a-f]{64}")
_CALENDAR_AUTHORITY = "SSE_SZSE_OFFICIAL_CALENDAR_ARCHIVE"
_SECTOR_AUTHORITY = "PIT_SECTOR_METADATA_ARCHIVE"
_LABEL_AUTHORITY = "PIT_OFFICIAL_FORWARD_LABEL_ARCHIVE"

class FactorResearchInputError(ValueError):
    """Raised when WP1-E1 evidence is incomplete, untrusted or non-causal."""


class FactorDirection(str, Enum):
    """Direction supported by the frozen rank-IC evidence rule."""

    EXPECTED = "EXPECTED"
    NEUTRAL = "NEUTRAL"
    FLIPPED = "FLIPPED"


@dataclass(frozen=True)
class FactorResearchPolicy:
    """Single preregistered WP1-E1 threshold and shrinkage policy."""

    policy_id: str = "wp1_e1_rank_ic_v1"
    cadence: str = "NON_OVERLAPPING_OFFICIAL_WINDOWS"
    forecast_horizon: int = 20
    embargo_trading_days: int = 1
    holding_days: int = 20
    expected_universe_size: int = 49
    expected_sector_count: int = 6
    min_cross_section: int = 30
    min_coverage_ratio: float = 30 / 49
    min_names_per_sector: int = 2
    min_matured_dates: int = 8
    min_abs_median_rank_ic: float = 0.03
    min_direction_consistency: float = 0.625
    full_strength_abs_median_rank_ic: float = 0.10
    full_strength_direction_consistency: float = 0.75
    full_strength_coverage_ratio: float = 0.80
    full_strength_matured_dates: int = 16

    def __post_init__(self) -> None:
        if self.policy_id != "wp1_e1_rank_ic_v1":
            raise ValueError("unexpected factor research policy_id")
        if self.cadence != "NON_OVERLAPPING_OFFICIAL_WINDOWS":
            raise ValueError("factor research cadence must be non-overlapping")
        if (
            self.forecast_horizon != 20
            or self.embargo_trading_days != 1
            or self.holding_days != 20
        ):
            raise ValueError("factor research must use the official 1+20 target")
        if self.expected_universe_size != 49 or self.expected_sector_count != 6:
            raise ValueError("factor research requires the exact 49/6 universe")
        if self.min_cross_section != 30:
            raise ValueError("factor research min_cross_section must remain 30")
        if not np.isclose(
            self.min_coverage_ratio,
            self.min_cross_section / self.expected_universe_size,
        ):
            raise ValueError("coverage ratio must equal 30/49")
        for value, label in (
            (self.min_abs_median_rank_ic, "minimum IC"),
            (self.min_direction_consistency, "minimum consistency"),
            (self.full_strength_abs_median_rank_ic, "full-strength IC"),
            (
                self.full_strength_direction_consistency,
                "full-strength consistency",
            ),
            (self.full_strength_coverage_ratio, "full-strength coverage"),
        ):
            if not 0 < value <= 1:
                raise ValueError(f"{label} must be in (0, 1]")
        if self.min_matured_dates < 1 or self.full_strength_matured_dates < 1:
            raise ValueError("matured-date thresholds must be positive")

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "cadence": self.cadence,
            "forecast_horizon": self.forecast_horizon,
            "embargo_trading_days": self.embargo_trading_days,
            "holding_days": self.holding_days,
            "expected_universe_size": self.expected_universe_size,
            "expected_sector_count": self.expected_sector_count,
            "min_cross_section": self.min_cross_section,
            "min_coverage_ratio": self.min_coverage_ratio,
            "min_names_per_sector": self.min_names_per_sector,
            "min_matured_dates": self.min_matured_dates,
            "min_abs_median_rank_ic": self.min_abs_median_rank_ic,
            "min_direction_consistency": self.min_direction_consistency,
            "full_strength_abs_median_rank_ic": (
                self.full_strength_abs_median_rank_ic
            ),
            "full_strength_direction_consistency": (
                self.full_strength_direction_consistency
            ),
            "full_strength_coverage_ratio": self.full_strength_coverage_ratio,
            "full_strength_matured_dates": self.full_strength_matured_dates,
        }


FACTOR_RESEARCH_POLICY = FactorResearchPolicy()


def _validate_sha256(value: object, label: str) -> str:
    text = str(value)
    if _HASH_RE.fullmatch(text) is None or text == "0" * 64:
        raise FactorResearchInputError(f"{label} must be a lowercase SHA-256")
    return text


def _as_aware_shanghai(value: object, label: str) -> pd.Timestamp:
    try:
        timestamp = pd.Timestamp(value)
    except (TypeError, ValueError) as exc:
        raise FactorResearchInputError(f"{label} is invalid") from exc
    if timestamp.tzinfo is None:
        raise FactorResearchInputError(f"{label} must be timezone-aware")
    return timestamp.tz_convert(_SHANGHAI)


def _as_date(value: object, label: str) -> pd.Timestamp:
    try:
        timestamp = pd.Timestamp(value)
    except (TypeError, ValueError) as exc:
        raise FactorResearchInputError(f"{label} is invalid") from exc
    if timestamp.tzinfo is not None or timestamp != timestamp.normalize():
        raise FactorResearchInputError(f"{label} must be a timezone-naive date")
    return timestamp


def _require_trusted_research_evidence(
    *,
    kind: str,
    authority: str,
    source_version: str,
    source_sha256: str,
    evidence_hash: str,
) -> None:
    if not factor_evidence_provider.trusted_evidence_contains(
        kind=kind,
        authority=authority,
        source_version=source_version,
        source_sha256=source_sha256,
        evidence_hash=evidence_hash,
    ):
        raise FactorResearchInputError(
            f"{kind} evidence is not present in the trusted source manifest"
        )


@dataclass(frozen=True)
class CanonicalCalendarEvidence:
    """Trusted exchange-session sequence shared by E0 snapshots and labels."""

    authority: str
    source_version: str
    source_sha256: str
    calendar_id: str
    sessions: tuple[str, ...]

    @property
    def evidence_hash(self) -> str:
        return canonical_hash(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "authority": self.authority,
            "source_version": self.source_version,
            "source_sha256": self.source_sha256,
            "calendar_id": self.calendar_id,
            "sessions": list(self.sessions),
        }

    def validate(self, *, policy: FactorResearchPolicy) -> pd.DatetimeIndex:
        if self.authority != _CALENDAR_AUTHORITY:
            raise FactorResearchInputError("calendar authority is not accepted")
        if not self.source_version.strip():
            raise FactorResearchInputError("calendar source_version is missing")
        _validate_sha256(self.source_sha256, "calendar source_sha256")
        if not self.calendar_id.strip():
            raise FactorResearchInputError("calendar_id is missing")
        sessions = pd.DatetimeIndex(
            [_as_date(value, "calendar session") for value in self.sessions]
        )
        if len(sessions) < policy.embargo_trading_days + policy.holding_days + 1:
            raise FactorResearchInputError(
                "calendar does not contain a complete official window"
            )
        if (
            sessions.has_duplicates
            or not sessions.is_monotonic_increasing
            or bool((sessions.dayofweek >= 5).any())
        ):
            raise FactorResearchInputError(
                "calendar sessions must be unique increasing weekdays"
            )
        _require_trusted_research_evidence(
            kind="canonical_calendar",
            authority=self.authority,
            source_version=self.source_version,
            source_sha256=self.source_sha256,
            evidence_hash=self.evidence_hash,
        )
        return sessions


@dataclass(frozen=True)
class SectorMetadataEvidence:
    """Versioned point-in-time sector mapping used for neutralization."""

    authority: str
    source_version: str
    source_sha256: str
    effective_date: str
    observed_at: str
    sectors: tuple[tuple[str, str], ...]

    @property
    def evidence_hash(self) -> str:
        return canonical_hash(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "authority": self.authority,
            "source_version": self.source_version,
            "source_sha256": self.source_sha256,
            "effective_date": self.effective_date,
            "observed_at": self.observed_at,
            "sectors": [list(item) for item in self.sectors],
        }

    def validate(
        self,
        *,
        cutoff: pd.Timestamp,
        policy: FactorResearchPolicy,
    ) -> tuple[str, ...]:
        if self.authority != _SECTOR_AUTHORITY:
            raise FactorResearchInputError("sector metadata authority is not accepted")
        if not self.source_version.strip():
            raise FactorResearchInputError("sector metadata source_version is missing")
        _validate_sha256(self.source_sha256, "sector metadata source_sha256")
        effective = _as_date(self.effective_date, "sector metadata effective_date")
        observed = _as_aware_shanghai(
            self.observed_at,
            "sector metadata observed_at",
        )
        if effective > cutoff.tz_localize(None).normalize() or observed > cutoff:
            raise FactorResearchInputError(
                "sector metadata was not available at the factor decision"
            )
        tickers = tuple(item[0] for item in self.sectors)
        if (
            len(tickers) != policy.expected_universe_size
            or tickers != tuple(sorted(tickers))
            or len(set(tickers)) != len(tickers)
            or any(not ticker for ticker in tickers)
        ):
            raise FactorResearchInputError(
                "sector metadata must bind 49 unique sorted tickers"
            )
        sector_names = tuple(item[1] for item in self.sectors)
        unique_sectors = set(sector_names)
        if len(unique_sectors) != policy.expected_sector_count or any(
            not sector for sector in sector_names
        ):
            raise FactorResearchInputError("sector metadata must bind six sectors")
        counts = pd.Series(sector_names).value_counts()
        if bool((counts < policy.min_names_per_sector).any()):
            raise FactorResearchInputError(
                "sector metadata has too few names in a sector"
            )
        _require_trusted_research_evidence(
            kind="sector_metadata",
            authority=self.authority,
            source_version=self.source_version,
            source_sha256=self.source_sha256,
            evidence_hash=self.evidence_hash,
        )
        return tickers


def _validate_price_pairs(
    pairs: tuple[tuple[str, float | None], ...],
    *,
    expected_tickers: tuple[str, ...],
    label: str,
) -> dict[str, float | None]:
    tickers = tuple(item[0] for item in pairs)
    if tickers != expected_tickers:
        raise FactorResearchInputError(f"{label} does not exactly cover tickers")
    result: dict[str, float | None] = {}
    for ticker, value in pairs:
        if value is None:
            result[ticker] = None
            continue
        if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
            raise FactorResearchInputError(f"{label} prices must be real or missing")
        numeric = float(value)
        if not np.isfinite(numeric) or numeric <= 0.0:
            raise FactorResearchInputError(
                f"{label} prices must be finite and positive"
            )
        result[ticker] = numeric
    return result


@dataclass(frozen=True)
class OfficialForwardLabel:
    """Hash-bound per-ticker official entry-open to exit-close label."""

    authority: str
    source_version: str
    source_sha256: str
    calendar_id: str
    calendar_evidence_hash: str
    decision_date: str
    embargo_date: str
    entry_date: str
    valuation_dates: tuple[str, ...]
    exit_date: str
    available_at: str
    entry_open: tuple[tuple[str, float | None], ...]
    exit_close: tuple[tuple[str, float | None], ...]

    @property
    def evidence_hash(self) -> str:
        return canonical_hash(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "authority": self.authority,
            "source_version": self.source_version,
            "source_sha256": self.source_sha256,
            "calendar_id": self.calendar_id,
            "calendar_evidence_hash": self.calendar_evidence_hash,
            "decision_date": self.decision_date,
            "embargo_date": self.embargo_date,
            "entry_date": self.entry_date,
            "valuation_dates": list(self.valuation_dates),
            "exit_date": self.exit_date,
            "available_at": self.available_at,
            "entry_open": [list(item) for item in self.entry_open],
            "exit_close": [list(item) for item in self.exit_close],
        }

    def validate(
        self,
        *,
        research_decision: pd.Timestamp,
        expected_tickers: tuple[str, ...],
        calendar_evidence: CanonicalCalendarEvidence,
        canonical_sessions: pd.DatetimeIndex,
        policy: FactorResearchPolicy,
    ) -> pd.Series:
        if self.authority != _LABEL_AUTHORITY:
            raise FactorResearchInputError("forward-label authority is not accepted")
        if not self.source_version.strip():
            raise FactorResearchInputError("forward-label source_version is missing")
        _validate_sha256(self.source_sha256, "forward-label source_sha256")
        if (
            self.calendar_id != calendar_evidence.calendar_id
            or self.calendar_evidence_hash != calendar_evidence.evidence_hash
        ):
            raise FactorResearchInputError(
                "forward label does not bind the trusted canonical calendar"
            )
        decision = _as_date(self.decision_date, "label decision_date")
        embargo = _as_date(self.embargo_date, "label embargo_date")
        entry = _as_date(self.entry_date, "label entry_date")
        exit_day = _as_date(self.exit_date, "label exit_date")
        valuations = tuple(
            _as_date(value, "label valuation_date")
            for value in self.valuation_dates
        )
        if len(valuations) != policy.holding_days:
            raise FactorResearchInputError("label must contain exactly 20 valuation dates")
        try:
            decision_position = int(canonical_sessions.get_loc(decision))
        except (KeyError, TypeError) as exc:
            raise FactorResearchInputError(
                "label decision is absent from the canonical calendar"
            ) from exc
        expected_window = canonical_sessions[
            decision_position : decision_position
            + policy.embargo_trading_days
            + policy.holding_days
            + 1
        ]
        if len(expected_window) != policy.embargo_trading_days + policy.holding_days + 1:
            raise FactorResearchInputError(
                "canonical calendar ends before the official label exit"
            )
        expected_embargo = expected_window[1]
        expected_valuations = tuple(expected_window[2:])
        if not (
            embargo == expected_embargo
            and entry == expected_valuations[0]
            and valuations == expected_valuations
            and exit_day == expected_valuations[-1]
        ):
            raise FactorResearchInputError(
                "label does not match canonical decision/embargo/20-session positions"
            )
        available = _as_aware_shanghai(self.available_at, "label available_at")
        exit_close = exit_day.tz_localize(_SHANGHAI) + pd.Timedelta(hours=15)
        if available < exit_close:
            raise FactorResearchInputError(
                "label available_at precedes the official exit close"
            )
        if available > research_decision:
            raise FactorResearchInputError("forward label is not matured")
        opens = _validate_price_pairs(
            self.entry_open,
            expected_tickers=expected_tickers,
            label="entry_open",
        )
        exits = _validate_price_pairs(
            self.exit_close,
            expected_tickers=expected_tickers,
            label="exit_close",
        )
        _require_trusted_research_evidence(
            kind="official_forward_label",
            authority=self.authority,
            source_version=self.source_version,
            source_sha256=self.source_sha256,
            evidence_hash=self.evidence_hash,
        )
        returns = {
            ticker: (
                None
                if opens[ticker] is None or exits[ticker] is None
                else float(exits[ticker] / opens[ticker] - 1.0)
            )
            for ticker in expected_tickers
        }
        return pd.Series(returns, index=expected_tickers, dtype=float)


@dataclass(frozen=True)
class MaturedFactorObservation:
    """One historical E0 snapshot paired with its matured official label."""

    factor_snapshot: FactorSnapshot
    label: OfficialForwardLabel

    @property
    def observation_hash(self) -> str:
        return canonical_hash(
            {
                "factor_snapshot_hash": self.factor_snapshot.snapshot_hash,
                "label_evidence_hash": self.label.evidence_hash,
            }
        )


@dataclass(frozen=True)
class FactorResearchMetric:
    """One factor's aggregate point-in-time evidence and shrinkage result."""

    factor_id: str
    total_matured_dates: int
    valid_ic_dates: int
    median_coverage: float | None
    median_rank_ic: float | None
    direction_consistency: float | None
    direction: FactorDirection
    multiplier: float
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "factor_id": self.factor_id,
            "total_matured_dates": self.total_matured_dates,
            "valid_ic_dates": self.valid_ic_dates,
            "median_coverage": self.median_coverage,
            "median_rank_ic": self.median_rank_ic,
            "direction_consistency": self.direction_consistency,
            "direction": self.direction.value,
            "multiplier": self.multiplier,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class FactorResearchSnapshot:
    """Immutable, canonical WP1-E1 output for one research decision."""

    decision_time: str
    policy_hash: str
    registry_hash: str
    calendar_evidence_hash: str
    sector_evidence_hash: str
    observation_hashes: tuple[str, ...]
    metrics: tuple[FactorResearchMetric, ...]
    snapshot_hash: str

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "decision_time": self.decision_time,
            "policy_hash": self.policy_hash,
            "registry_hash": self.registry_hash,
            "calendar_evidence_hash": self.calendar_evidence_hash,
            "sector_evidence_hash": self.sector_evidence_hash,
            "observation_hashes": list(self.observation_hashes),
            "metrics": [metric.to_dict() for metric in self.metrics],
        }
        if canonical_hash(payload) != self.snapshot_hash:
            raise ValueError("factor research snapshot hash mismatch")
        return {**payload, "snapshot_hash": self.snapshot_hash}


def _validate_factor_snapshot(
    snapshot: FactorSnapshot,
    *,
    expected_tickers: tuple[str, ...],
    research_decision: pd.Timestamp,
    calendar_evidence: CanonicalCalendarEvidence,
) -> pd.Timestamp:
    try:
        snapshot.to_dict()
    except (TypeError, ValueError) as exc:
        raise FactorResearchInputError("E0 factor snapshot is not self-consistent") from exc
    if not factor_evidence_provider.trusted_factor_snapshot_contains(
        snapshot.snapshot_hash
    ):
        raise FactorResearchInputError("factor observation lacks a trusted E0 snapshot")
    if snapshot.registry_hash != FACTOR_REGISTRY_HASH:
        raise FactorResearchInputError("factor snapshot registry hash mismatch")
    if snapshot.forecast_horizon != 20:
        raise FactorResearchInputError("factor snapshot horizon is not official 20")
    if (
        snapshot.calendar_id != calendar_evidence.calendar_id
        or snapshot.calendar_evidence_hash != calendar_evidence.evidence_hash
    ):
        raise FactorResearchInputError(
            "factor snapshot does not bind the trusted canonical calendar"
        )
    factor_ids = tuple(item.factor_id for item in FACTOR_REGISTRY)
    if (
        tuple(snapshot.values.index) != expected_tickers
        or tuple(snapshot.status.index) != expected_tickers
        or tuple(snapshot.values.columns) != factor_ids
        or tuple(snapshot.status.columns) != factor_ids
    ):
        raise FactorResearchInputError(
            "factor snapshot does not match the exact universe and Registry"
        )
    factor_decision = _as_aware_shanghai(
        snapshot.decision_time,
        "factor snapshot decision_time",
    )
    if factor_decision.time() < _DECISION_CLOSE:
        raise FactorResearchInputError("factor snapshot precedes decision close")
    if factor_decision > research_decision:
        raise FactorResearchInputError("factor snapshot is after research decision")
    return factor_decision


def _rank_ic(
    values: pd.Series,
    status: pd.Series,
    targets: pd.Series,
    sectors: pd.Series,
    *,
    policy: FactorResearchPolicy,
) -> tuple[float, float] | None:
    numeric_values = pd.to_numeric(values, errors="coerce")
    numeric_targets = pd.to_numeric(targets, errors="coerce")
    common = (
        status.eq(AVAILABLE)
        & np.isfinite(numeric_values)
        & np.isfinite(numeric_targets)
    )
    count = int(common.sum())
    coverage = count / policy.expected_universe_size
    if count < policy.min_cross_section or coverage < policy.min_coverage_ratio:
        return None
    common_sectors = sectors[common]
    counts = common_sectors.value_counts()
    if len(counts) != policy.expected_sector_count or bool(
        (counts < policy.min_names_per_sector).any()
    ):
        return None
    factor = numeric_values[common].astype(float)
    target = numeric_targets[common].astype(float)
    factor_residual = factor - factor.groupby(common_sectors).transform("mean")
    target_residual = target - target.groupby(common_sectors).transform("mean")
    factor_rank = factor_residual.rank(method="average")
    target_rank = target_residual.rank(method="average")
    if factor_rank.nunique() < 2 or target_rank.nunique() < 2:
        return None
    correlation = float(np.corrcoef(factor_rank, target_rank)[0, 1])
    if not np.isfinite(correlation):
        return None
    return correlation, coverage


def _expected_sign(definition: FactorDefinition) -> float:
    if definition.expected_direction == "POSITIVE":
        return 1.0
    if definition.expected_direction == "NEGATIVE":
        return -1.0
    raise FactorResearchInputError(
        f"unsupported expected direction for {definition.factor_id}"
    )


def _neutral_metric(
    definition: FactorDefinition,
    *,
    total_dates: int,
    rank_ics: Sequence[float],
    coverages: Sequence[float],
    reason: str,
) -> FactorResearchMetric:
    return FactorResearchMetric(
        factor_id=definition.factor_id,
        total_matured_dates=total_dates,
        valid_ic_dates=len(rank_ics),
        median_coverage=(
            None if not coverages else float(np.median(np.asarray(coverages)))
        ),
        median_rank_ic=(
            None if not rank_ics else float(np.median(np.asarray(rank_ics)))
        ),
        direction_consistency=None,
        direction=FactorDirection.NEUTRAL,
        multiplier=0.0,
        reason=reason,
    )


def _aggregate_metric(
    definition: FactorDefinition,
    *,
    total_dates: int,
    rank_ics: Sequence[float],
    coverages: Sequence[float],
    policy: FactorResearchPolicy,
) -> FactorResearchMetric:
    if total_dates < policy.min_matured_dates:
        return _neutral_metric(
            definition,
            total_dates=total_dates,
            rank_ics=rank_ics,
            coverages=coverages,
            reason="INSUFFICIENT_MATURED_DATES",
        )
    if len(rank_ics) < policy.min_matured_dates:
        return _neutral_metric(
            definition,
            total_dates=total_dates,
            rank_ics=rank_ics,
            coverages=coverages,
            reason="INSUFFICIENT_VALID_IC_DATES",
        )

    median_ic = float(np.median(np.asarray(rank_ics, dtype=float)))
    expected_sign = _expected_sign(definition)
    oriented = np.asarray(rank_ics, dtype=float) * expected_sign
    oriented_median = median_ic * expected_sign
    if abs(oriented_median) < policy.min_abs_median_rank_ic:
        return _neutral_metric(
            definition,
            total_dates=total_dates,
            rank_ics=rank_ics,
            coverages=coverages,
            reason="WEAK_MEDIAN_IC",
        )

    if oriented_median > 0.0:
        direction = FactorDirection.EXPECTED
        consistency = float(np.mean(oriented > 0.0))
        reason = "QUALIFIED_EXPECTED"
    else:
        direction = FactorDirection.FLIPPED
        consistency = float(np.mean(oriented < 0.0))
        reason = "QUALIFIED_FLIPPED"
    if consistency < policy.min_direction_consistency:
        neutral = _neutral_metric(
            definition,
            total_dates=total_dates,
            rank_ics=rank_ics,
            coverages=coverages,
            reason="UNSTABLE_DIRECTION",
        )
        return FactorResearchMetric(
            **{
                **neutral.to_dict(),
                "direction": FactorDirection.NEUTRAL,
                "direction_consistency": consistency,
            }
        )

    median_coverage = float(np.median(np.asarray(coverages, dtype=float)))
    strength_terms = (
        min(1.0, abs(median_ic) / policy.full_strength_abs_median_rank_ic),
        min(
            1.0,
            consistency / policy.full_strength_direction_consistency,
        ),
        min(1.0, median_coverage / policy.full_strength_coverage_ratio),
        min(1.0, len(rank_ics) / policy.full_strength_matured_dates),
    )
    multiplier = float(np.clip(np.prod(strength_terms), 0.0, 1.0))
    return FactorResearchMetric(
        factor_id=definition.factor_id,
        total_matured_dates=total_dates,
        valid_ic_dates=len(rank_ics),
        median_coverage=median_coverage,
        median_rank_ic=median_ic,
        direction_consistency=consistency,
        direction=direction,
        multiplier=multiplier,
        reason=reason,
    )


def compute_factor_research_snapshot(
    *,
    decision_time: datetime,
    observations: Sequence[MaturedFactorObservation],
    calendar_evidence: CanonicalCalendarEvidence,
    sector_evidence: SectorMetadataEvidence,
) -> FactorResearchSnapshot:
    """Build one deterministic WP1-E1 snapshot from matured observations only."""

    policy = FACTOR_RESEARCH_POLICY
    research_decision = _as_aware_shanghai(decision_time, "research decision_time")
    if research_decision.time() < _DECISION_CLOSE:
        raise FactorResearchInputError("research decision precedes decision close")
    records = tuple(observations)
    if any(not isinstance(item, MaturedFactorObservation) for item in records):
        raise FactorResearchInputError("observations must be matured factor records")
    canonical_sessions = calendar_evidence.validate(policy=policy)

    preliminary_cutoff = research_decision
    if records:
        preliminary_cutoff = min(
            _as_aware_shanghai(
                item.factor_snapshot.decision_time,
                "factor snapshot decision_time",
            )
            for item in records
        )
    expected_tickers = sector_evidence.validate(
        cutoff=preliminary_cutoff,
        policy=policy,
    )
    sectors = pd.Series(dict(sector_evidence.sectors), index=expected_tickers)

    previous_factor_decision: pd.Timestamp | None = None
    previous_exit: pd.Timestamp | None = None
    targets_by_observation: list[pd.Series] = []
    observation_hashes: list[str] = []
    for record in records:
        factor_decision = _validate_factor_snapshot(
            record.factor_snapshot,
            expected_tickers=expected_tickers,
            research_decision=research_decision,
            calendar_evidence=calendar_evidence,
        )
        targets = record.label.validate(
            research_decision=research_decision,
            expected_tickers=expected_tickers,
            calendar_evidence=calendar_evidence,
            canonical_sessions=canonical_sessions,
            policy=policy,
        )
        label_decision = _as_date(
            record.label.decision_date,
            "label decision_date",
        )
        if factor_decision.tz_localize(None).normalize() != label_decision:
            raise FactorResearchInputError(
                "factor snapshot and forward label decision dates differ"
            )
        if record.factor_snapshot.calendar_id != record.label.calendar_id:
            raise FactorResearchInputError(
                "factor snapshot and forward label calendars differ"
            )
        label_entry = _as_date(record.label.entry_date, "label entry_date")
        label_exit = _as_date(record.label.exit_date, "label exit_date")
        if (
            previous_factor_decision is not None
            and factor_decision <= previous_factor_decision
        ):
            raise FactorResearchInputError(
                "factor observations must be strictly chronological"
            )
        if previous_exit is not None and label_entry <= previous_exit:
            raise FactorResearchInputError(
                "official factor research windows overlap"
            )
        previous_factor_decision = factor_decision
        previous_exit = label_exit
        targets_by_observation.append(targets)
        observation_hashes.append(record.observation_hash)

    rank_ics: dict[str, list[float]] = {
        definition.factor_id: [] for definition in FACTOR_REGISTRY
    }
    coverages: dict[str, list[float]] = {
        definition.factor_id: [] for definition in FACTOR_REGISTRY
    }
    for record, targets in zip(records, targets_by_observation, strict=True):
        for definition in FACTOR_REGISTRY:
            result = _rank_ic(
                record.factor_snapshot.values[definition.factor_id],
                record.factor_snapshot.status[definition.factor_id],
                targets,
                sectors,
                policy=policy,
            )
            if result is None:
                continue
            rank_ic, coverage = result
            rank_ics[definition.factor_id].append(rank_ic)
            coverages[definition.factor_id].append(coverage)

    metrics = tuple(
        _aggregate_metric(
            definition,
            total_dates=len(records),
            rank_ics=rank_ics[definition.factor_id],
            coverages=coverages[definition.factor_id],
            policy=policy,
        )
        for definition in FACTOR_REGISTRY
    )
    decision_text = research_decision.isoformat()
    policy_hash = canonical_hash(policy.to_dict())
    payload = {
        "decision_time": decision_text,
        "policy_hash": policy_hash,
        "registry_hash": FACTOR_REGISTRY_HASH,
        "calendar_evidence_hash": calendar_evidence.evidence_hash,
        "sector_evidence_hash": sector_evidence.evidence_hash,
        "observation_hashes": observation_hashes,
        "metrics": [metric.to_dict() for metric in metrics],
    }
    return FactorResearchSnapshot(
        decision_time=decision_text,
        policy_hash=policy_hash,
        registry_hash=FACTOR_REGISTRY_HASH,
        calendar_evidence_hash=calendar_evidence.evidence_hash,
        sector_evidence_hash=sector_evidence.evidence_hash,
        observation_hashes=tuple(observation_hashes),
        metrics=metrics,
        snapshot_hash=canonical_hash(payload),
    )
