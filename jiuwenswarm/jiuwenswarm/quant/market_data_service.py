"""Shared, fail-closed market-data contract and deterministic diagnostics.

This module intentionally contains no network access.  Providers and entry
adapters must first construct a :class:`MarketDataBundle`; the same validation
and compact diagnostic output can then be used by both production paths.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from jiuwenswarm.quant.data_integrity import (
    DataIntegrityReport,
    check_cross_source_overlap,
    check_price_sanity,
    check_trading_calendar,
    detect_corporate_action_artifacts,
)
from jiuwenswarm.quant.market_index import MarketIndex
from jiuwenswarm.quant.market_width import compute_breadth, compute_sector_states
from jiuwenswarm.quant.regime_fusion import RegimeFusion


@dataclass(frozen=True)
class ProviderEvidence:
    """Declared economic conventions for one upstream provider."""

    name: str
    source_endpoint: str
    price_adjustment: str
    raw_volume_unit: str
    volume_multiplier_to_shares: float
    raw_price_unit: str = "CNY_per_share"


@dataclass(frozen=True)
class MarketDataBundle:
    """Canonical point-in-time inputs required by WP1-A diagnostics.

    The OHLCV frames are already normalized to ``CNY_per_share`` and
    ``shares``.  ``provider_evidence`` records how every source represented in
    ``provider_ledger`` was converted to those canonical units.
    """

    opens: pd.DataFrame
    highs: pd.DataFrame
    lows: pd.DataFrame
    closes: pd.DataFrame
    volumes: pd.DataFrame
    secondary_closes: pd.DataFrame
    benchmark_closes: pd.Series
    provider_ledger: Mapping[str, str]
    provider_stats: Mapping[str, Mapping[str, Any]]
    provider_evidence: Mapping[str, ProviderEvidence]
    calendar_id: str
    adjustment_policy: str
    secondary_label: str
    as_of_time: datetime
    retrieved_at: datetime


@dataclass(frozen=True)
class MarketDiagnostics:
    """JSON-safe diagnostic result; raw market matrices are never included."""

    passed: bool
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    integrity_reports: tuple[dict[str, Any], ...]
    breadth: dict[str, Any]
    sector_states: dict[str, dict[str, Any]]
    regimes: dict[str, Any]
    provenance: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return _json_safe(
            {
                "passed": self.passed,
                "blockers": self.blockers,
                "warnings": self.warnings,
                "integrity_reports": self.integrity_reports,
                "breadth": self.breadth,
                "sector_states": self.sector_states,
                "regimes": self.regimes,
                "provenance": self.provenance,
            }
        )


class MarketDataContractError(RuntimeError):
    """Raised when a caller attempts to continue with blocked diagnostics."""


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _frame_contract_blockers(
    label: str,
    frame: Any,
    expected_tickers: list[str],
    reference_index: pd.DatetimeIndex | None = None,
) -> list[str]:
    blockers: list[str] = []
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return [f"{label} frame is missing or empty"]
    if list(frame.columns) != expected_tickers:
        missing = sorted(set(expected_tickers) - {str(column) for column in frame.columns})
        extra = sorted({str(column) for column in frame.columns} - set(expected_tickers))
        blockers.append(
            f"{label} columns do not exactly match expected tickers; "
            f"missing={missing}, extra={extra}"
        )
    if not isinstance(frame.index, pd.DatetimeIndex):
        blockers.append(f"{label} index must be a DatetimeIndex")
    elif frame.index.has_duplicates or not frame.index.is_monotonic_increasing:
        blockers.append(f"{label} index must be unique and monotonically increasing")
    if reference_index is not None and not frame.index.equals(reference_index):
        blockers.append(f"{label} index does not match canonical close calendar")
    if int(frame.isna().sum().sum()) > 0:
        blockers.append(f"{label} contains missing values")
    return blockers


def _contract_blockers(
    bundle: MarketDataBundle,
    expected_tickers: list[str],
    *,
    minimum_rows: int,
    minimum_secondary_overlap_days: int,
    minimum_benchmark_rows: int,
) -> tuple[list[str], dict[str, int]]:
    blockers: list[str] = []
    blockers.extend(_frame_contract_blockers("closes", bundle.closes, expected_tickers))
    close_index = (
        bundle.closes.index
        if isinstance(bundle.closes, pd.DataFrame)
        and isinstance(bundle.closes.index, pd.DatetimeIndex)
        else None
    )
    blockers.extend(
        _frame_contract_blockers(
            "opens",
            bundle.opens,
            expected_tickers,
            close_index,
        )
    )
    blockers.extend(
        _frame_contract_blockers(
            "highs",
            bundle.highs,
            expected_tickers,
            close_index,
        )
    )
    blockers.extend(
        _frame_contract_blockers(
            "lows",
            bundle.lows,
            expected_tickers,
            close_index,
        )
    )
    blockers.extend(
        _frame_contract_blockers(
            "volumes",
            bundle.volumes,
            expected_tickers,
            close_index,
        )
    )

    if isinstance(bundle.closes, pd.DataFrame):
        if len(bundle.closes) < minimum_rows:
            blockers.append(
                f"closes has {len(bundle.closes)} rows; minimum is {minimum_rows}"
            )
        if not bundle.closes.empty and bool((bundle.closes <= 0).any().any()):
            blockers.append("closes contains non-positive prices")
    if (
        isinstance(bundle.opens, pd.DataFrame)
        and not bundle.opens.empty
        and bool((bundle.opens <= 0).any().any())
    ):
        blockers.append("opens contains non-positive prices")
    if (
        isinstance(bundle.highs, pd.DataFrame)
        and not bundle.highs.empty
        and bool((bundle.highs <= 0).any().any())
    ):
        blockers.append("highs contains non-positive prices")
    if (
        isinstance(bundle.lows, pd.DataFrame)
        and not bundle.lows.empty
        and bool((bundle.lows <= 0).any().any())
    ):
        blockers.append("lows contains non-positive prices")
    if (
        isinstance(bundle.volumes, pd.DataFrame)
        and not bundle.volumes.empty
        and bool((bundle.volumes < 0).any().any())
    ):
        blockers.append("volumes contains negative values")

    aligned_ohlc = all(
        isinstance(frame, pd.DataFrame)
        and list(frame.columns) == expected_tickers
        and close_index is not None
        and frame.index.equals(close_index)
        and not frame.isna().any().any()
        for frame in (bundle.opens, bundle.highs, bundle.lows, bundle.closes)
    )
    if aligned_ohlc:
        expected_high_floor = pd.concat(
            [bundle.opens, bundle.closes],
            keys=["open", "close"],
        ).groupby(level=1).max()
        expected_low_ceiling = pd.concat(
            [bundle.opens, bundle.closes],
            keys=["open", "close"],
        ).groupby(level=1).min()
        invalid_ohlc = (
            (bundle.highs < expected_high_floor)
            | (bundle.lows > expected_low_ceiling)
            | (bundle.highs < bundle.lows)
        )
        if bool(invalid_ohlc.any().any()):
            blockers.append(
                f"OHLC relationship is invalid at {int(invalid_ohlc.sum().sum())} points"
            )

    expected_set = set(expected_tickers)
    ledger = {str(key): str(value) for key, value in bundle.provider_ledger.items()}
    if set(ledger) != expected_set:
        blockers.append(
            "provider ledger does not exactly cover expected tickers; "
            f"missing={sorted(expected_set - set(ledger))}, "
            f"extra={sorted(set(ledger) - expected_set)}"
        )
    empty_ledger = sorted(ticker for ticker, provider in ledger.items() if not provider)
    if empty_ledger:
        blockers.append(f"provider ledger has empty providers: {empty_ledger}")

    if not str(bundle.calendar_id).strip():
        blockers.append("calendar_id is missing")
    if not str(bundle.adjustment_policy).strip():
        blockers.append("adjustment_policy is missing")
    if not str(bundle.secondary_label).strip():
        blockers.append("secondary source label is missing")

    for label, timestamp in (
        ("as_of_time", bundle.as_of_time),
        ("retrieved_at", bundle.retrieved_at),
    ):
        if (
            not isinstance(timestamp, datetime)
            or timestamp.tzinfo is None
            or timestamp.utcoffset() is None
        ):
            blockers.append(f"{label} must be a timezone-aware datetime")
    if (
        isinstance(bundle.as_of_time, datetime)
        and isinstance(bundle.retrieved_at, datetime)
        and bundle.as_of_time.tzinfo is not None
        and bundle.retrieved_at.tzinfo is not None
        and bundle.retrieved_at < bundle.as_of_time
    ):
        blockers.append("retrieved_at cannot precede as_of_time")

    as_of_date: pd.Timestamp | None = None
    if (
        isinstance(bundle.as_of_time, datetime)
        and bundle.as_of_time.tzinfo is not None
        and bundle.as_of_time.utcoffset() is not None
    ):
        as_of_date = (
            pd.Timestamp(bundle.as_of_time)
            .tz_convert("Asia/Shanghai")
            .tz_localize(None)
            .normalize()
        )
        dated_inputs = (
            ("closes", bundle.closes),
            ("secondary_closes", bundle.secondary_closes),
            ("benchmark_closes", bundle.benchmark_closes),
        )
        for label, values in dated_inputs:
            if (
                isinstance(values, (pd.DataFrame, pd.Series))
                and not values.empty
                and isinstance(values.index, pd.DatetimeIndex)
            ):
                latest = values.index.max()
                if latest.tz is not None:
                    latest = latest.tz_convert("Asia/Shanghai").tz_localize(None)
                if latest.normalize() > as_of_date:
                    blockers.append(f"{label} contains dates after as_of_time")

    used_providers = set(ledger.values())
    missing_evidence = sorted(used_providers - set(bundle.provider_evidence))
    if missing_evidence:
        blockers.append(f"provider evidence missing for: {missing_evidence}")
    missing_stats = sorted(used_providers - set(bundle.provider_stats))
    if missing_stats:
        blockers.append(f"provider stats missing for: {missing_stats}")
    for provider in sorted(used_providers.intersection(bundle.provider_evidence)):
        evidence = bundle.provider_evidence[provider]
        if evidence.name != provider:
            blockers.append(
                f"provider evidence name mismatch: key={provider}, name={evidence.name}"
            )
        if not evidence.source_endpoint.strip():
            blockers.append(f"provider {provider} source endpoint is missing")
        if evidence.price_adjustment != bundle.adjustment_policy:
            blockers.append(
                f"provider {provider} adjustment {evidence.price_adjustment} "
                f"does not match bundle policy {bundle.adjustment_policy}"
            )
        if not evidence.raw_price_unit.strip() or not evidence.raw_volume_unit.strip():
            blockers.append(f"provider {provider} unit metadata is incomplete")
        multiplier = evidence.volume_multiplier_to_shares
        if not np.isfinite(multiplier) or multiplier <= 0:
            blockers.append(
                f"provider {provider} has invalid volume multiplier: {multiplier}"
            )

    overlap_counts: dict[str, int] = {}
    secondary = bundle.secondary_closes
    primary_columns = (
        set(bundle.closes.columns)
        if isinstance(bundle.closes, pd.DataFrame)
        else set()
    )
    if not isinstance(secondary, pd.DataFrame) or secondary.empty:
        blockers.append("secondary overlap prices are missing or empty")
    else:
        for ticker in expected_tickers:
            if ticker not in secondary.columns or ticker not in primary_columns:
                overlap_counts[ticker] = 0
                continue
            primary_valid = bundle.closes[ticker].dropna()
            secondary_valid = secondary[ticker].dropna()
            overlap_counts[ticker] = len(
                primary_valid.index.intersection(secondary_valid.index)
            )
        insufficient = {
            ticker: count
            for ticker, count in overlap_counts.items()
            if count < minimum_secondary_overlap_days
        }
        if insufficient:
            sample = dict(list(insufficient.items())[:5])
            blockers.append(
                "secondary overlap is below "
                f"{minimum_secondary_overlap_days} days for "
                f"{len(insufficient)} tickers: {sample}"
            )

    benchmark = bundle.benchmark_closes
    if not isinstance(benchmark, pd.Series) or benchmark.empty:
        blockers.append("benchmark close evidence is missing or empty")
    else:
        valid_benchmark = benchmark.dropna()
        if not isinstance(benchmark.index, pd.DatetimeIndex):
            blockers.append("benchmark index must be a DatetimeIndex")
        elif benchmark.index.has_duplicates or not benchmark.index.is_monotonic_increasing:
            blockers.append("benchmark index must be unique and monotonically increasing")
        if len(valid_benchmark) < minimum_benchmark_rows:
            blockers.append(
                f"benchmark has {len(valid_benchmark)} rows; "
                f"minimum is {minimum_benchmark_rows}"
            )
        if bool((valid_benchmark <= 0).any()):
            blockers.append("benchmark contains non-positive prices")
        if close_index is not None:
            benchmark_overlap = len(close_index.intersection(valid_benchmark.index))
            if benchmark_overlap < minimum_benchmark_rows:
                blockers.append(
                    f"benchmark overlaps the canonical calendar on only "
                    f"{benchmark_overlap} rows"
                )

    return blockers, overlap_counts


def _report_payload(name: str, report: DataIntegrityReport) -> dict[str, Any]:
    return {
        "check": name,
        "passed": report.passed,
        "findings": list(report.findings),
        "warnings": list(report.warnings),
        "metrics": dict(report.metrics),
    }


def diagnose_market_data(
    bundle: MarketDataBundle,
    expected_tickers: Sequence[str],
    *,
    minimum_rows: int = 81,
    minimum_secondary_overlap_days: int = 20,
    minimum_benchmark_rows: int = 60,
    cross_source_tolerance_pct: float = 1.0,
) -> MarketDiagnostics:
    """Validate a canonical bundle and return compact deterministic evidence."""

    expected = [str(ticker) for ticker in expected_tickers]
    blockers: list[str] = []
    if not expected or len(expected) != len(set(expected)):
        blockers.append("expected_tickers must be non-empty and unique")

    contract_blockers, overlap_counts = _contract_blockers(
        bundle,
        expected,
        minimum_rows=minimum_rows,
        minimum_secondary_overlap_days=minimum_secondary_overlap_days,
        minimum_benchmark_rows=minimum_benchmark_rows,
    )
    blockers.extend(contract_blockers)

    ledger = {str(key): str(value) for key, value in bundle.provider_ledger.items()}
    provider_summary = dict(sorted(Counter(ledger.values()).items()))
    provenance = {
        "n_stocks": len(bundle.closes.columns)
        if isinstance(bundle.closes, pd.DataFrame)
        else 0,
        "n_trading_days": len(bundle.closes)
        if isinstance(bundle.closes, pd.DataFrame)
        else 0,
        "calendar_id": bundle.calendar_id,
        "adjustment_policy": bundle.adjustment_policy,
        "as_of_time": bundle.as_of_time,
        "retrieved_at": bundle.retrieved_at,
        "actual_start_date": bundle.closes.index[0]
        if isinstance(bundle.closes, pd.DataFrame) and not bundle.closes.empty
        else None,
        "actual_end_date": bundle.closes.index[-1]
        if isinstance(bundle.closes, pd.DataFrame) and not bundle.closes.empty
        else None,
        "canonical_units": {
            "open": "CNY_per_share",
            "high": "CNY_per_share",
            "low": "CNY_per_share",
            "close": "CNY_per_share",
            "volume": "shares",
        },
        "provider_ledger": ledger,
        "provider_ledger_summary": provider_summary,
        "provider_stats": bundle.provider_stats,
        "provider_evidence": {
            provider: asdict(evidence)
            for provider, evidence in bundle.provider_evidence.items()
        },
        "secondary_label": bundle.secondary_label,
        "minimum_secondary_overlap_days": min(overlap_counts.values())
        if overlap_counts
        else 0,
        "secondary_overlap_days_by_ticker": overlap_counts,
        "benchmark_name": str(bundle.benchmark_closes.name or "benchmark")
        if isinstance(bundle.benchmark_closes, pd.Series)
        else "benchmark",
    }

    if blockers:
        return MarketDiagnostics(
            passed=False,
            blockers=tuple(blockers),
            warnings=(),
            integrity_reports=(),
            breadth={},
            sector_states={},
            regimes={},
            provenance=_json_safe(provenance),
        )

    named_reports = (
        ("trading_calendar", check_trading_calendar(bundle.closes.index)),
        ("price_sanity", check_price_sanity(bundle.closes, bundle.opens, bundle.volumes)),
        (
            "corporate_actions",
            detect_corporate_action_artifacts(bundle.closes, bundle.volumes),
        ),
        (
            "cross_source_overlap",
            check_cross_source_overlap(
                bundle.closes,
                bundle.secondary_closes,
                primary_label="canonical_primary",
                secondary_label=bundle.secondary_label,
                tolerance_pct=cross_source_tolerance_pct,
            ),
        ),
    )
    warnings: list[str] = []
    for name, report in named_reports:
        blockers.extend(f"{name}: {finding}" for finding in report.findings)
        warnings.extend(f"{name}: {warning}" for warning in report.warnings)

    breadth = _json_safe(asdict(compute_breadth(bundle.closes, bundle.volumes)))
    sector_states = {
        sector: _json_safe(asdict(state))
        for sector, state in compute_sector_states(
            bundle.closes,
            bundle.volumes,
        ).items()
    }
    regime_detail = RegimeFusion.detect_with_detail(
        bundle.closes,
        index_prices=bundle.benchmark_closes,
    )
    regimes = {
        "pool": regime_detail["technical"],
        "benchmark": MarketIndex.detect_from_series(bundle.benchmark_closes),
        "final": regime_detail["final"],
        "consensus": bool(regime_detail["consensus"]),
    }

    return MarketDiagnostics(
        passed=not blockers,
        blockers=tuple(blockers),
        warnings=tuple(warnings),
        integrity_reports=tuple(
            _report_payload(name, report) for name, report in named_reports
        ),
        breadth=breadth,
        sector_states=sector_states,
        regimes=regimes,
        provenance=_json_safe(provenance),
    )


def require_diagnostics_passed(
    diagnostics: MarketDiagnostics,
) -> MarketDiagnostics:
    """Return diagnostics or raise before any downstream quant phase runs."""

    if not diagnostics.passed:
        detail = "; ".join(diagnostics.blockers[:5]) or "unknown blocker"
        raise MarketDataContractError(f"market data diagnostics failed: {detail}")
    return diagnostics
