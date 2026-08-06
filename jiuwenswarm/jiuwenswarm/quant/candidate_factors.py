"""Pure point-in-time computations for the research-only WP1-E0 registry."""

from __future__ import annotations

import inspect
import re
import textwrap
from dataclasses import dataclass
from datetime import datetime, time
from math import sqrt
from numbers import Real
from types import CodeType
from typing import Any, Callable, Sequence
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from jiuwenswarm.quant import factor_evidence_provider
from jiuwenswarm.quant.factor_registry import (
    FACTOR_REGISTRY,
    FactorDefinition,
    canonical_hash,
    registry_hash,
    validate_registry,
)


AVAILABLE = "AVAILABLE"
INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
INVALID_PRICE_WINDOW = "INVALID_PRICE_WINDOW"
ZERO_OR_INVALID_VOLATILITY = "ZERO_OR_INVALID_VOLATILITY"
NON_FINITE_RESULT = "NON_FINITE_RESULT"

_SHANGHAI = ZoneInfo("Asia/Shanghai")
_DECISION_CLOSE = time(15, 0)
_ENGINE_VERSION = "wp1-e0-trend-kernels/1.0.0"
_CALENDAR_AUTHORITY = "SSE_SZSE_OFFICIAL_CALENDAR_ARCHIVE"
_CORPORATE_ACTION_AUTHORITY = "PIT_CORPORATE_ACTION_ARCHIVE"
_ACCEPTED_ADJUSTMENT_POLICIES = frozenset(
    {"point_in_time_adjusted", "verified_no_action_window"}
)
_POLICY_RESULTS = {
    "point_in_time_adjusted": "POINT_IN_TIME_ADJUSTED",
    "verified_no_action_window": "NO_CORPORATE_ACTION_IN_WINDOW",
}
_HASH_RE = re.compile(r"[0-9a-f]{64}")

class FactorInputError(ValueError):
    """Raised when point-in-time input metadata cannot be trusted."""


@dataclass(frozen=True)
class CalendarEvidence:
    """Recomputable binding to an archived official exchange calendar."""

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

    def validate(self, canonical_sessions: pd.DatetimeIndex) -> None:
        if self.authority != _CALENDAR_AUTHORITY:
            raise FactorInputError("calendar evidence authority is not accepted")
        if not self.source_version.strip():
            raise FactorInputError("calendar evidence source_version is missing")
        _validate_evidence_hash(
            self.source_sha256,
            "calendar evidence source_sha256",
        )
        if self.calendar_id != "SSE_SZSE_CANONICAL":
            raise FactorInputError("calendar_id must be SSE_SZSE_CANONICAL")
        try:
            bound_sessions = pd.DatetimeIndex(pd.to_datetime(list(self.sessions)))
        except (TypeError, ValueError) as exc:
            raise FactorInputError("calendar evidence sessions are invalid") from exc
        _validate_sessions(bound_sessions)
        if not canonical_sessions.equals(bound_sessions):
            raise FactorInputError(
                "canonical sessions do not match archived calendar evidence"
            )
        _require_trusted_evidence(
            kind="calendar",
            authority=self.authority,
            source_version=self.source_version,
            source_sha256=self.source_sha256,
            evidence_hash=self.evidence_hash,
        )


@dataclass(frozen=True)
class CorporateActionEvidence:
    """Recomputable ticker/window binding to archived corporate-action results."""

    authority: str
    source_version: str
    source_sha256: str
    policy: str
    window_start: str
    window_end: str
    ticker_results: tuple[tuple[str, str], ...]

    @property
    def evidence_hash(self) -> str:
        return canonical_hash(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "authority": self.authority,
            "source_version": self.source_version,
            "source_sha256": self.source_sha256,
            "policy": self.policy,
            "window_start": self.window_start,
            "window_end": self.window_end,
            "ticker_results": [list(item) for item in self.ticker_results],
        }

    def validate(
        self,
        *,
        adjustment_policy: str,
        tickers: Sequence[str],
        sessions: pd.DatetimeIndex,
    ) -> None:
        if self.authority != _CORPORATE_ACTION_AUTHORITY:
            raise FactorInputError(
                "corporate-action evidence authority is not accepted"
            )
        if not self.source_version.strip():
            raise FactorInputError(
                "corporate-action evidence source_version is missing"
            )
        _validate_evidence_hash(
            self.source_sha256,
            "corporate-action evidence source_sha256",
        )
        if self.policy != adjustment_policy:
            raise FactorInputError(
                "corporate-action evidence policy does not match input policy"
            )
        try:
            window_start = pd.Timestamp(self.window_start)
            window_end = pd.Timestamp(self.window_end)
        except (TypeError, ValueError) as exc:
            raise FactorInputError(
                "corporate-action evidence window is invalid"
            ) from exc
        if (
            window_start != window_start.normalize()
            or window_end != window_end.normalize()
            or window_start > sessions[0]
            or window_end < sessions[-1]
        ):
            raise FactorInputError(
                "corporate-action evidence does not cover the input window"
            )
        expected_tickers = tuple(sorted(tickers))
        result_tickers = tuple(item[0] for item in self.ticker_results)
        if result_tickers != expected_tickers:
            raise FactorInputError(
                "corporate-action evidence does not exactly cover tickers"
            )
        expected_result = _POLICY_RESULTS[adjustment_policy]
        if any(result != expected_result for _, result in self.ticker_results):
            raise FactorInputError(
                "corporate-action evidence result does not satisfy policy"
            )
        _require_trusted_evidence(
            kind="corporate_action",
            authority=self.authority,
            source_version=self.source_version,
            source_sha256=self.source_sha256,
            evidence_hash=self.evidence_hash,
        )


@dataclass(frozen=True)
class PointInTimeFactorInput:
    """Explicit session-by-ticker input and its decision-time evidence."""

    closes: pd.DataFrame
    canonical_sessions: pd.DatetimeIndex
    decision_time: datetime
    adjustment_policy: str
    calendar_evidence: CalendarEvidence
    corporate_action_evidence: CorporateActionEvidence
    forecast_horizon: int = 20

    def validate(self) -> None:
        """Validate causality, calendar, and corporate-action boundaries."""

        if (
            not isinstance(self.decision_time, datetime)
            or self.decision_time.tzinfo is None
            or self.decision_time.utcoffset() is None
        ):
            raise FactorInputError("decision_time must be timezone-aware")
        if self.forecast_horizon != 20:
            raise FactorInputError("official forecast horizon must be 20")
        if self.adjustment_policy not in _ACCEPTED_ADJUSTMENT_POLICIES:
            raise FactorInputError(
                "corporate-action policy must be point_in_time_adjusted or "
                "verified_no_action_window"
            )
        _validate_wide_closes(self.closes)
        _validate_sessions(self.canonical_sessions)
        self.calendar_evidence.validate(self.canonical_sessions)
        if not self.closes.index.equals(self.canonical_sessions):
            raise FactorInputError(
                "closes must exactly match verified canonical sessions"
            )
        self.corporate_action_evidence.validate(
            adjustment_policy=self.adjustment_policy,
            tickers=tuple(str(ticker) for ticker in self.closes.columns),
            sessions=self.canonical_sessions,
        )

        decision_local = self.decision_time.astimezone(_SHANGHAI)
        decision_date = pd.Timestamp(decision_local.date())
        latest = self.canonical_sessions[-1]
        if latest > decision_date:
            raise FactorInputError("closes contain sessions after decision_time")
        if latest != decision_date:
            raise FactorInputError(
                "final canonical session must equal the decision session"
            )
        if decision_local.time() < _DECISION_CLOSE:
            raise FactorInputError(
                "decision_time must be at or after the decision close"
            )


@dataclass(frozen=True)
class FactorSnapshot:
    """Raw factor values, unavailability reasons, and immutable audit hashes."""

    decision_time: str
    calendar_id: str
    calendar_evidence_hash: str
    adjustment_policy: str
    corporate_action_evidence_hash: str
    forecast_horizon: int
    registry_hash: str
    input_hash: str
    values: pd.DataFrame
    status: pd.DataFrame
    snapshot_hash: str

    def to_dict(self) -> dict[str, Any]:
        """Serialize unavailable values as null, never as fabricated zero."""

        payload = {
            "decision_time": self.decision_time,
            "calendar_id": self.calendar_id,
            "calendar_evidence_hash": self.calendar_evidence_hash,
            "adjustment_policy": self.adjustment_policy,
            "corporate_action_evidence_hash": self.corporate_action_evidence_hash,
            "forecast_horizon": self.forecast_horizon,
            "registry_hash": self.registry_hash,
            "input_hash": self.input_hash,
            "values": _frame_to_nested(self.values, null_non_finite=True),
            "status": _frame_to_nested(self.status, null_non_finite=False),
        }
        if canonical_hash(payload) != self.snapshot_hash:
            raise ValueError("snapshot hash mismatch; payload was mutated")
        return {**payload, "snapshot_hash": self.snapshot_hash}


def _validate_evidence_hash(value: str, label: str) -> None:
    if (
        not isinstance(value, str)
        or _HASH_RE.fullmatch(value) is None
        or value == "0" * 64
    ):
        raise FactorInputError(f"{label} must be a lowercase SHA-256")


def _require_trusted_evidence(
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
        raise FactorInputError(
            f"{kind} evidence is not present in the trusted source manifest"
        )


def _validate_sessions(sessions: Any) -> None:
    if not isinstance(sessions, pd.DatetimeIndex) or len(sessions) == 0:
        raise FactorInputError("canonical sessions must be a non-empty DatetimeIndex")
    if sessions.tz is not None:
        raise FactorInputError("canonical sessions must be timezone-naive session dates")
    if sessions.has_duplicates or not sessions.is_monotonic_increasing:
        raise FactorInputError("canonical sessions must be unique and increasing")
    if not sessions.equals(sessions.normalize()):
        raise FactorInputError("canonical sessions must be normalized session dates")
    if bool((sessions.dayofweek >= 5).any()):
        raise FactorInputError("canonical sessions cannot contain weekends")


def _validate_wide_closes(closes: Any) -> None:
    if not isinstance(closes, pd.DataFrame) or closes.empty:
        raise FactorInputError("closes must be a non-empty DataFrame")
    if not isinstance(closes.index, pd.DatetimeIndex):
        raise FactorInputError("closes index must be a DatetimeIndex")
    if closes.index.has_duplicates or not closes.index.is_monotonic_increasing:
        raise FactorInputError("closes index must be unique and increasing")
    if closes.columns.has_duplicates or len(closes.columns) == 0:
        raise FactorInputError("ticker columns must be non-empty and unique")
    if any(not isinstance(ticker, str) or not ticker for ticker in closes.columns):
        raise FactorInputError("ticker columns must be non-empty strings")
    for ticker in closes.columns:
        for value in closes[ticker].array:
            try:
                missing = bool(pd.isna(value))
            except (TypeError, ValueError):
                missing = False
            if missing:
                continue
            if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
                raise FactorInputError(
                    f"close values for {ticker} must be real numeric or missing"
                )


def _numeric_closes(closes: pd.DataFrame) -> pd.DataFrame:
    """Return ticker-canonical floats after strict non-numeric rejection."""

    ordered = closes.reindex(columns=sorted(str(item) for item in closes.columns))
    converted = {
        ticker: pd.to_numeric(ordered[ticker], errors="raise").astype(float)
        for ticker in ordered.columns
    }
    return pd.DataFrame(converted, index=ordered.index, dtype=float)


def _momentum(prices: np.ndarray, lookback: int) -> float:
    return float(prices[-1] / prices[-lookback - 1] - 1.0)


def _risk_adjusted_momentum(prices: np.ndarray, lookback: int) -> float:
    momentum = _momentum(prices, lookback)
    returns = prices[-lookback:] / prices[-lookback - 1 : -1] - 1.0
    annualized_volatility = float(np.std(returns, ddof=1) * sqrt(252.0))
    if not np.isfinite(annualized_volatility) or annualized_volatility <= 0.0:
        raise ZeroDivisionError("zero or invalid volatility")
    return float(momentum / annualized_volatility)


def _trend_consistency(prices: np.ndarray) -> float:
    signs = [np.sign(_momentum(prices, lookback)) for lookback in (5, 10, 20)]
    return float(np.mean(signs))


def _price_vs_moving_average(prices: np.ndarray, lookback: int) -> float:
    return float(prices[-1] / np.mean(prices[-lookback:]) - 1.0)


def _momentum_acceleration(prices: np.ndarray) -> float:
    return float(_momentum(prices, 20) - _momentum(prices, 60) / 3.0)


_KERNELS: dict[str, tuple[Callable[..., float], dict[str, int]]] = {
    **{
        f"momentum_{lookback}": (_momentum, {"lookback": lookback})
        for lookback in (5, 10, 20, 60, 120, 250)
    },
    **{
        f"risk_adjusted_momentum_{lookback}": (
            _risk_adjusted_momentum,
            {"lookback": lookback},
        )
        for lookback in (20, 60)
    },
    "trend_consistency_5_10_20": (_trend_consistency, {}),
    "price_vs_ma20": (_price_vs_moving_average, {"lookback": 20}),
    "price_vs_ma60": (_price_vs_moving_average, {"lookback": 60}),
    "momentum_acceleration": (_momentum_acceleration, {}),
}

def _function_dependency_closure(
    root: Callable[..., float],
) -> tuple[Callable[..., float], ...]:
    """Discover all same-module helper functions reached by one kernel."""

    pending = [root]
    discovered: dict[str, Callable[..., float]] = {}
    while pending:
        function = pending.pop()
        identity = f"{function.__module__}.{function.__qualname__}"
        if identity in discovered:
            continue
        discovered[identity] = function
        for name in sorted(_code_global_names(function.__code__)):
            dependency = function.__globals__.get(name)
            if (
                inspect.isfunction(dependency)
                and dependency.__module__ == __name__
            ):
                pending.append(dependency)
    return tuple(discovered[key] for key in sorted(discovered))


def _code_global_names(code: CodeType) -> frozenset[str]:
    """Return global names from ``code`` and every nested code object.

    Comprehension bytecode changed in Python 3.12. Walking ``co_consts`` keeps
    source bindings identical when a helper reference is nested on Python
    3.9/3.11 but inlined into the outer code object on Python 3.12+.
    """

    names = set(code.co_names)
    for constant in code.co_consts:
        if isinstance(constant, CodeType):
            names.update(_code_global_names(constant))
    return frozenset(names)


def implementation_hash_for(definition: FactorDefinition) -> str:
    """Bind metadata, generic-kernel source, and its frozen parameters."""

    try:
        kernel, parameters = _KERNELS[definition.factor_id]
    except KeyError as exc:
        raise ValueError(f"no implementation for {definition.factor_id}") from exc
    metadata = definition.to_dict()
    metadata.pop("implementation_hash")
    bound_functions = _function_dependency_closure(kernel)
    kernel_sources = [
        {
            "name": function.__name__,
            "source": textwrap.dedent(inspect.getsource(function)).replace(
                "\r\n",
                "\n",
            ),
        }
        for function in bound_functions
    ]
    return canonical_hash(
        {
            "engine_version": _ENGINE_VERSION,
            "metadata": metadata,
            "kernel_sources": kernel_sources,
            "bound_parameters": parameters,
        }
    )


def verify_implementation_hashes(
    registry: Sequence[FactorDefinition] = FACTOR_REGISTRY,
) -> None:
    """Recompute every kernel binding and reject any mismatch."""

    validate_registry(registry)
    for definition in registry:
        actual = implementation_hash_for(definition)
        if actual != definition.implementation_hash:
            raise ValueError(
                f"implementation hash mismatch for {definition.factor_id}: "
                f"expected={definition.implementation_hash}, actual={actual}"
            )


def _frame_payload(frame: pd.DataFrame) -> dict[str, Any]:
    numeric = _numeric_closes(frame)
    return {
        "sessions": [timestamp.date().isoformat() for timestamp in frame.index],
        "tickers": list(numeric.columns),
        "values": [
            [float(value) if np.isfinite(value) else None for value in row]
            for row in numeric.to_numpy(dtype=float)
        ],
    }


def _frame_to_nested(
    frame: pd.DataFrame,
    *,
    null_non_finite: bool,
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for ticker in frame.index:
        row: dict[str, Any] = {}
        for factor_id in frame.columns:
            value = frame.loc[ticker, factor_id]
            if null_non_finite:
                row[str(factor_id)] = (
                    float(value) if np.isfinite(float(value)) else None
                )
            else:
                row[str(factor_id)] = str(value)
        result[str(ticker)] = row
    return result


def compute_trend_snapshot(
    inputs: PointInTimeFactorInput,
) -> FactorSnapshot:
    """Compute all registered raw factors without fitting or imputation."""

    inputs.validate()
    registry = FACTOR_REGISTRY
    validate_registry(registry)
    verify_implementation_hashes(registry)

    factor_ids = [definition.factor_id for definition in registry]
    numeric = _numeric_closes(inputs.closes)
    tickers = list(numeric.columns)
    values = pd.DataFrame(np.nan, index=tickers, columns=factor_ids, dtype=float)
    status = pd.DataFrame(
        INSUFFICIENT_HISTORY,
        index=tickers,
        columns=factor_ids,
        dtype=object,
    )
    for definition in registry:
        if len(numeric) < definition.minimum_lookback:
            continue
        window = numeric.iloc[-definition.minimum_lookback :]
        for ticker in tickers:
            prices = window[ticker].to_numpy(dtype=float)
            if not bool(np.isfinite(prices).all()) or bool((prices <= 0.0).any()):
                status.loc[ticker, definition.factor_id] = INVALID_PRICE_WINDOW
                continue
            try:
                kernel, parameters = _KERNELS[definition.factor_id]
                value = float(kernel(prices, **parameters))
            except ZeroDivisionError:
                status.loc[
                    ticker,
                    definition.factor_id,
                ] = ZERO_OR_INVALID_VOLATILITY
                continue
            if not np.isfinite(value):
                status.loc[ticker, definition.factor_id] = NON_FINITE_RESULT
                continue
            values.loc[ticker, definition.factor_id] = value
            status.loc[ticker, definition.factor_id] = AVAILABLE

    decision_time = inputs.decision_time.astimezone(_SHANGHAI).isoformat()
    current_registry_hash = registry_hash(registry)
    calendar_evidence_hash = inputs.calendar_evidence.evidence_hash
    corporate_action_evidence_hash = (
        inputs.corporate_action_evidence.evidence_hash
    )
    input_hash = canonical_hash(
        {
            "decision_time": decision_time,
            "calendar_id": inputs.calendar_evidence.calendar_id,
            "calendar_evidence_hash": calendar_evidence_hash,
            "adjustment_policy": inputs.adjustment_policy,
            "corporate_action_evidence_hash": corporate_action_evidence_hash,
            "forecast_horizon": inputs.forecast_horizon,
            "registry_hash": current_registry_hash,
            "closes": _frame_payload(numeric),
        }
    )
    snapshot_payload = {
        "decision_time": decision_time,
        "calendar_id": inputs.calendar_evidence.calendar_id,
        "calendar_evidence_hash": calendar_evidence_hash,
        "adjustment_policy": inputs.adjustment_policy,
        "corporate_action_evidence_hash": corporate_action_evidence_hash,
        "forecast_horizon": inputs.forecast_horizon,
        "registry_hash": current_registry_hash,
        "input_hash": input_hash,
        "values": _frame_to_nested(values, null_non_finite=True),
        "status": _frame_to_nested(status, null_non_finite=False),
    }
    snapshot_hash = canonical_hash(snapshot_payload)
    return FactorSnapshot(
        decision_time=decision_time,
        calendar_id=inputs.calendar_evidence.calendar_id,
        calendar_evidence_hash=calendar_evidence_hash,
        adjustment_policy=inputs.adjustment_policy,
        corporate_action_evidence_hash=corporate_action_evidence_hash,
        forecast_horizon=inputs.forecast_horizon,
        registry_hash=current_registry_hash,
        input_hash=input_hash,
        values=values,
        status=status,
        snapshot_hash=snapshot_hash,
    )
