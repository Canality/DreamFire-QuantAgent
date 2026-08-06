from __future__ import annotations

import ast
import os
import subprocess
import sys
from dataclasses import FrozenInstanceError, replace
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

import jiuwenswarm.quant.factor_evidence_provider as factor_evidence_provider
from jiuwenswarm.quant.candidate_factors import AVAILABLE, FactorSnapshot
from jiuwenswarm.quant.factor_registry import (
    FACTOR_REGISTRY,
    FACTOR_REGISTRY_HASH,
    canonical_hash,
)
from jiuwenswarm.quant.factor_research import (
    FACTOR_RESEARCH_POLICY,
    CanonicalCalendarEvidence,
    FactorDirection,
    FactorResearchInputError,
    MaturedFactorObservation,
    OfficialForwardLabel,
    SectorMetadataEvidence,
    compute_factor_research_snapshot,
)


SHANGHAI = ZoneInfo("Asia/Shanghai")
TICKERS = tuple(f"T{index:03d}" for index in range(49))
SECTORS = tuple(
    (ticker, f"S{min(index // 8, 5)}")
    for index, ticker in enumerate(TICKERS)
)
FACTOR_IDS = tuple(item.factor_id for item in FACTOR_REGISTRY)
TEST_TRUSTED_EVIDENCE_KEYS: set[tuple[str, str, str, str, str]] = set()
TEST_TRUSTED_FACTOR_SNAPSHOTS: set[str] = set()


@pytest.fixture(autouse=True)
def _test_only_trust_roots(monkeypatch: pytest.MonkeyPatch) -> None:
    TEST_TRUSTED_EVIDENCE_KEYS.clear()
    TEST_TRUSTED_FACTOR_SNAPSHOTS.clear()
    monkeypatch.setattr(
        factor_evidence_provider,
        "trusted_evidence_contains",
        lambda **item: (
            item["kind"],
            item["authority"],
            item["source_version"],
            item["source_sha256"],
            item["evidence_hash"],
        )
        in TEST_TRUSTED_EVIDENCE_KEYS,
    )
    monkeypatch.setattr(
        factor_evidence_provider,
        "trusted_factor_snapshot_contains",
        TEST_TRUSTED_FACTOR_SNAPSHOTS.__contains__,
    )


def _aware(day: pd.Timestamp, hour: int = 15, minute: int = 30) -> datetime:
    return datetime(
        day.year,
        day.month,
        day.day,
        hour,
        minute,
        tzinfo=SHANGHAI,
    )


def _frame_nested(frame: pd.DataFrame, *, numeric: bool) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for ticker in frame.index:
        row: dict[str, object] = {}
        for factor_id in frame.columns:
            value = frame.loc[ticker, factor_id]
            row[str(factor_id)] = (
                (float(value) if np.isfinite(float(value)) else None)
                if numeric
                else str(value)
            )
        result[str(ticker)] = row
    return result


def _factor_snapshot(
    day: pd.Timestamp,
    target: np.ndarray,
    *,
    calendar_evidence_hash: str,
    neutral_sign: float = 1.0,
) -> FactorSnapshot:
    values = pd.DataFrame(index=TICKERS, columns=FACTOR_IDS, dtype=float)
    for factor_id in FACTOR_IDS:
        if factor_id == "momentum_10":
            values[factor_id] = -target
        elif factor_id == "momentum_20":
            values[factor_id] = neutral_sign * target
        else:
            values[factor_id] = target
    status = pd.DataFrame(
        AVAILABLE,
        index=TICKERS,
        columns=FACTOR_IDS,
        dtype=object,
    )
    decision_time = _aware(day).isoformat()
    input_hash = canonical_hash({"fixture_day": day.date().isoformat()})
    payload = {
        "decision_time": decision_time,
        "calendar_id": "TEST_CANONICAL",
        "calendar_evidence_hash": calendar_evidence_hash,
        "adjustment_policy": "point_in_time_adjusted",
        "corporate_action_evidence_hash": "b" * 64,
        "forecast_horizon": 20,
        "registry_hash": FACTOR_REGISTRY_HASH,
        "input_hash": input_hash,
        "values": _frame_nested(values, numeric=True),
        "status": _frame_nested(status, numeric=False),
    }
    snapshot = FactorSnapshot(
        decision_time=decision_time,
        calendar_id="TEST_CANONICAL",
        calendar_evidence_hash=calendar_evidence_hash,
        adjustment_policy="point_in_time_adjusted",
        corporate_action_evidence_hash="b" * 64,
        forecast_horizon=20,
        registry_hash=FACTOR_REGISTRY_HASH,
        input_hash=input_hash,
        values=values,
        status=status,
        snapshot_hash=canonical_hash(payload),
    )
    TEST_TRUSTED_FACTOR_SNAPSHOTS.add(
        snapshot.snapshot_hash
    )
    return snapshot


def _replace_snapshot_frames(
    snapshot: FactorSnapshot,
    *,
    values: pd.DataFrame,
    status: pd.DataFrame,
) -> FactorSnapshot:
    payload = {
        "decision_time": snapshot.decision_time,
        "calendar_id": snapshot.calendar_id,
        "calendar_evidence_hash": snapshot.calendar_evidence_hash,
        "adjustment_policy": snapshot.adjustment_policy,
        "corporate_action_evidence_hash": snapshot.corporate_action_evidence_hash,
        "forecast_horizon": snapshot.forecast_horizon,
        "registry_hash": snapshot.registry_hash,
        "input_hash": snapshot.input_hash,
        "values": _frame_nested(values, numeric=True),
        "status": _frame_nested(status, numeric=False),
    }
    replacement = replace(
        snapshot,
        values=values,
        status=status,
        snapshot_hash=canonical_hash(payload),
    )
    TEST_TRUSTED_FACTOR_SNAPSHOTS.add(
        replacement.snapshot_hash
    )
    return replacement


def _trust_evidence(
    kind: str,
    evidence: (
        CanonicalCalendarEvidence
        | SectorMetadataEvidence
        | OfficialForwardLabel
    ),
) -> None:
    TEST_TRUSTED_EVIDENCE_KEYS.add(
        (
            kind,
            evidence.authority,
            evidence.source_version,
            evidence.source_sha256,
            evidence.evidence_hash,
        )
    )


def _sector_evidence(first_day: pd.Timestamp) -> SectorMetadataEvidence:
    evidence = SectorMetadataEvidence(
        authority="PIT_SECTOR_METADATA_ARCHIVE",
        source_version="test-sector/v1",
        source_sha256="c" * 64,
        effective_date=(first_day - pd.Timedelta(days=10)).date().isoformat(),
        observed_at=_aware(first_day - pd.Timedelta(days=5)).isoformat(),
        sectors=SECTORS,
    )
    _trust_evidence("sector_metadata", evidence)
    return evidence


def _calendar_evidence(
    sessions: pd.DatetimeIndex,
) -> CanonicalCalendarEvidence:
    evidence = CanonicalCalendarEvidence(
        authority="SSE_SZSE_OFFICIAL_CALENDAR_ARCHIVE",
        source_version="test-calendar/v1",
        source_sha256="a" * 64,
        calendar_id="TEST_CANONICAL",
        sessions=tuple(item.date().isoformat() for item in sessions),
    )
    _trust_evidence("canonical_calendar", evidence)
    return evidence


def _label(
    calendar: pd.DatetimeIndex,
    decision_index: int,
    target: np.ndarray,
    *,
    calendar_evidence_hash: str,
) -> OfficialForwardLabel:
    decision = calendar[decision_index]
    embargo = calendar[decision_index + 1]
    entry = calendar[decision_index + 2]
    valuations = tuple(
        calendar[decision_index + 2 + offset].date().isoformat()
        for offset in range(20)
    )
    exit_day = calendar[decision_index + 21]
    entry_open = tuple((ticker, 100.0) for ticker in TICKERS)
    exit_close = tuple(
        (ticker, float(100.0 * (1.0 + target[index])))
        for index, ticker in enumerate(TICKERS)
    )
    label = OfficialForwardLabel(
        authority="PIT_OFFICIAL_FORWARD_LABEL_ARCHIVE",
        source_version="test-label/v1",
        source_sha256="d" * 64,
        calendar_id="TEST_CANONICAL",
        calendar_evidence_hash=calendar_evidence_hash,
        decision_date=decision.date().isoformat(),
        embargo_date=embargo.date().isoformat(),
        entry_date=entry.date().isoformat(),
        valuation_dates=valuations,
        exit_date=exit_day.date().isoformat(),
        available_at=_aware(exit_day, 15, 0).isoformat(),
        entry_open=entry_open,
        exit_close=exit_close,
    )
    _trust_evidence("official_forward_label", label)
    return label


def _observations(
    count: int = 8,
    *,
    step: int = 22,
) -> tuple[
    tuple[MaturedFactorObservation, ...],
    CanonicalCalendarEvidence,
    SectorMetadataEvidence,
    datetime,
]:
    calendar = pd.bdate_range("2024-01-02", periods=max(260, count * step + 24))
    calendar_evidence = _calendar_evidence(calendar)
    base_target = np.linspace(-0.08, 0.08, len(TICKERS))
    observations: list[MaturedFactorObservation] = []
    for index in range(count):
        decision_index = index * step
        neutral_sign = 1.0 if index % 2 == 0 else -1.0
        factor_snapshot = _factor_snapshot(
            calendar[decision_index],
            base_target,
            calendar_evidence_hash=calendar_evidence.evidence_hash,
            neutral_sign=neutral_sign,
        )
        label = _label(
            calendar,
            decision_index,
            base_target,
            calendar_evidence_hash=calendar_evidence.evidence_hash,
        )
        observations.append(
            MaturedFactorObservation(
                factor_snapshot=factor_snapshot,
                label=label,
            )
        )
    research_day = calendar[(count - 1) * step + 22]
    return (
        tuple(observations),
        calendar_evidence,
        _sector_evidence(calendar[0]),
        _aware(research_day),
    )


def _metrics(snapshot: object) -> dict[str, object]:
    return {metric.factor_id: metric for metric in snapshot.metrics}  # type: ignore[attr-defined]


def test_policy_is_frozen_single_version_and_official_target_only() -> None:
    policy = FACTOR_RESEARCH_POLICY
    assert policy.policy_id == "wp1_e1_rank_ic_v1"
    assert policy.forecast_horizon == 20
    assert policy.embargo_trading_days == 1
    assert policy.holding_days == 20
    assert policy.min_matured_dates == 8
    assert policy.min_cross_section == 30
    assert policy.min_coverage_ratio == pytest.approx(30 / 49)
    assert policy.min_abs_median_rank_ic == pytest.approx(0.03)
    assert policy.min_direction_consistency == pytest.approx(0.625)
    with pytest.raises(FrozenInstanceError):
        policy.holding_days = 5  # type: ignore[misc]


def test_expected_flipped_and_neutral_directions_are_deterministic() -> None:
    observations, calendar, sectors, decision_time = _observations()
    snapshot = compute_factor_research_snapshot(
        decision_time=decision_time,
        observations=observations,
        calendar_evidence=calendar,
        sector_evidence=sectors,
    )
    metrics = _metrics(snapshot)

    expected = metrics["momentum_5"]
    assert expected.direction is FactorDirection.EXPECTED  # type: ignore[attr-defined]
    assert expected.median_rank_ic > 0.99  # type: ignore[attr-defined]
    assert expected.multiplier == pytest.approx(0.5)  # type: ignore[attr-defined]

    flipped = metrics["momentum_10"]
    assert flipped.direction is FactorDirection.FLIPPED  # type: ignore[attr-defined]
    assert flipped.median_rank_ic < -0.99  # type: ignore[attr-defined]
    assert flipped.multiplier == pytest.approx(0.5)  # type: ignore[attr-defined]

    neutral = metrics["momentum_20"]
    assert neutral.direction is FactorDirection.NEUTRAL  # type: ignore[attr-defined]
    assert neutral.multiplier == 0.0  # type: ignore[attr-defined]


def test_insufficient_matured_dates_never_borrows_recent_labels() -> None:
    observations, calendar, sectors, decision_time = _observations(count=7)
    snapshot = compute_factor_research_snapshot(
        decision_time=decision_time,
        observations=observations,
        calendar_evidence=calendar,
        sector_evidence=sectors,
    )
    for metric in snapshot.metrics:
        assert metric.direction is FactorDirection.NEUTRAL
        assert metric.multiplier == 0.0
        assert metric.reason == "INSUFFICIENT_MATURED_DATES"


def test_unmatured_label_and_future_factor_snapshot_fail_closed() -> None:
    observations, calendar, sectors, decision_time = _observations()
    final = observations[-1]
    delayed_label = replace(
        final.label,
        available_at=(decision_time + pd.Timedelta(minutes=1)).isoformat(),
    )
    _trust_evidence("official_forward_label", delayed_label)
    with pytest.raises(FactorResearchInputError, match="not matured"):
        compute_factor_research_snapshot(
            decision_time=decision_time,
            observations=observations[:-1]
            + (replace(final, label=delayed_label),),
            calendar_evidence=calendar,
            sector_evidence=sectors,
        )

    future_snapshot = replace(
        final.factor_snapshot,
        decision_time=(decision_time + pd.Timedelta(days=1)).isoformat(),
    )
    TEST_TRUSTED_FACTOR_SNAPSHOTS.add(
        future_snapshot.snapshot_hash
    )
    changed = observations[:-1] + (
        replace(final, factor_snapshot=future_snapshot),
    )
    with pytest.raises((FactorResearchInputError, ValueError)):
        compute_factor_research_snapshot(
            decision_time=decision_time,
            observations=changed,
            calendar_evidence=calendar,
            sector_evidence=sectors,
        )


def test_overlapping_or_malformed_official_windows_fail_closed() -> None:
    observations, calendar, sectors, decision_time = _observations(step=1)
    with pytest.raises(FactorResearchInputError, match="overlap"):
        compute_factor_research_snapshot(
            decision_time=decision_time,
            observations=observations,
            calendar_evidence=calendar,
            sector_evidence=sectors,
        )

    valid, calendar, sectors, decision_time = _observations()
    bad_label = replace(
        valid[0].label,
        valuation_dates=valid[0].label.valuation_dates[:-1],
    )
    with pytest.raises(FactorResearchInputError, match="20 valuation"):
        compute_factor_research_snapshot(
            decision_time=decision_time,
            observations=(replace(valid[0], label=bad_label),) + valid[1:],
            calendar_evidence=calendar,
            sector_evidence=sectors,
        )


def test_canonical_calendar_positions_and_exit_close_boundary() -> None:
    observations, calendar, sectors, decision_time = _observations()
    sessions = pd.DatetimeIndex(pd.to_datetime(list(calendar.sessions)))
    first = observations[0]

    weekend_valuations = tuple(
        value.date().isoformat() for value in sessions[4:24]
    )
    weekend_label = replace(
        first.label,
        embargo_date="2024-01-06",
        entry_date=weekend_valuations[0],
        valuation_dates=weekend_valuations,
        exit_date=weekend_valuations[-1],
        available_at=_aware(sessions[23], 15, 0).isoformat(),
    )
    _trust_evidence("official_forward_label", weekend_label)
    with pytest.raises(FactorResearchInputError, match="canonical"):
        compute_factor_research_snapshot(
            decision_time=decision_time,
            observations=(replace(first, label=weekend_label),) + observations[1:],
            calendar_evidence=calendar,
            sector_evidence=sectors,
        )

    delayed_valuations = tuple(
        value.date().isoformat() for value in sessions[3:23]
    )
    delayed_entry = replace(
        first.label,
        entry_date=delayed_valuations[0],
        valuation_dates=delayed_valuations,
        exit_date=delayed_valuations[-1],
        available_at=_aware(sessions[22], 15, 0).isoformat(),
    )
    _trust_evidence("official_forward_label", delayed_entry)
    with pytest.raises(FactorResearchInputError, match="canonical"):
        compute_factor_research_snapshot(
            decision_time=decision_time,
            observations=(replace(first, label=delayed_entry),) + observations[1:],
            calendar_evidence=calendar,
            sector_evidence=sectors,
        )

    skipped_sessions = tuple(sessions[2:10]) + tuple(sessions[11:23])
    skipped_valuations = tuple(
        value.date().isoformat() for value in skipped_sessions
    )
    skipped_label = replace(
        first.label,
        valuation_dates=skipped_valuations,
        exit_date=skipped_valuations[-1],
        available_at=_aware(sessions[22], 15, 0).isoformat(),
    )
    _trust_evidence("official_forward_label", skipped_label)
    with pytest.raises(FactorResearchInputError, match="canonical"):
        compute_factor_research_snapshot(
            decision_time=decision_time,
            observations=(replace(first, label=skipped_label),) + observations[1:],
            calendar_evidence=calendar,
            sector_evidence=sectors,
        )

    final = observations[-1]
    exact_exit_close = datetime.fromisoformat(final.label.available_at)
    compute_factor_research_snapshot(
        decision_time=exact_exit_close,
        observations=observations,
        calendar_evidence=calendar,
        sector_evidence=sectors,
    )
    premature = replace(
        final.label,
        available_at=(exact_exit_close - pd.Timedelta(minutes=1)).isoformat(),
    )
    with pytest.raises(FactorResearchInputError, match="precedes"):
        compute_factor_research_snapshot(
            decision_time=decision_time,
            observations=observations[:-1] + (replace(final, label=premature),),
            calendar_evidence=calendar,
            sector_evidence=sectors,
        )


def test_arbitrary_evidence_and_constructed_factor_snapshots_are_rejected() -> None:
    observations, calendar, sectors, decision_time = _observations()
    invented_label = replace(
        observations[0].label,
        source_version="invented/v999",
        source_sha256="e" * 64,
    )
    with pytest.raises(FactorResearchInputError, match="trusted source manifest"):
        compute_factor_research_snapshot(
            decision_time=decision_time,
            observations=(
                replace(observations[0], label=invented_label),
            )
            + observations[1:],
            calendar_evidence=calendar,
            sector_evidence=sectors,
        )

    TEST_TRUSTED_FACTOR_SNAPSHOTS.clear()
    with pytest.raises(FactorResearchInputError, match="trusted E0 snapshot"):
        compute_factor_research_snapshot(
            decision_time=decision_time,
            observations=observations,
            calendar_evidence=calendar,
            sector_evidence=sectors,
        )


def test_sector_evidence_is_pit_complete_and_trusted() -> None:
    observations, calendar, sectors, decision_time = _observations()
    future_sector = replace(
        sectors,
        observed_at=(
            datetime.fromisoformat(observations[0].factor_snapshot.decision_time)
            + pd.Timedelta(minutes=1)
        ).isoformat(),
    )
    with pytest.raises(FactorResearchInputError, match="sector metadata"):
        compute_factor_research_snapshot(
            decision_time=decision_time,
            observations=observations,
            calendar_evidence=calendar,
            sector_evidence=future_sector,
        )

    invented_sector = replace(
        sectors,
        source_version="invented/v999",
        source_sha256="f" * 64,
    )
    with pytest.raises(FactorResearchInputError, match="trusted source manifest"):
        compute_factor_research_snapshot(
            decision_time=decision_time,
            observations=observations,
            calendar_evidence=calendar,
            sector_evidence=invented_sector,
        )


def test_coverage_and_constant_rank_failures_are_neutral_not_zero_ic() -> None:
    observations, calendar, sectors, decision_time = _observations()
    changed: list[MaturedFactorObservation] = []
    for observation in observations:
        values = observation.factor_snapshot.values.copy()
        status = observation.factor_snapshot.status.copy()
        values.loc[TICKERS[:20], "momentum_5"] = np.nan
        status.loc[TICKERS[:20], "momentum_5"] = "INVALID_PRICE_WINDOW"
        values.loc[:, "momentum_60"] = 1.0
        replacement = _replace_snapshot_frames(
            observation.factor_snapshot,
            values=values,
            status=status,
        )
        changed.append(replace(observation, factor_snapshot=replacement))

    snapshot = compute_factor_research_snapshot(
        decision_time=decision_time,
        observations=tuple(changed),
        calendar_evidence=calendar,
        sector_evidence=sectors,
    )
    metrics = _metrics(snapshot)
    for factor_id in ("momentum_5", "momentum_60"):
        metric = metrics[factor_id]
        assert metric.direction is FactorDirection.NEUTRAL  # type: ignore[attr-defined]
        assert metric.multiplier == 0.0  # type: ignore[attr-defined]
        assert metric.median_rank_ic is None  # type: ignore[attr-defined]


def test_snapshot_hash_is_deterministic_and_policy_is_not_injectable() -> None:
    observations, calendar, sectors, decision_time = _observations()
    first = compute_factor_research_snapshot(
        decision_time=decision_time,
        observations=observations,
        calendar_evidence=calendar,
        sector_evidence=sectors,
    )
    second = compute_factor_research_snapshot(
        decision_time=decision_time,
        observations=observations,
        calendar_evidence=calendar,
        sector_evidence=sectors,
    )
    assert first.to_dict() == second.to_dict()
    assert first.snapshot_hash == second.snapshot_hash
    assert first.policy_hash == canonical_hash(FACTOR_RESEARCH_POLICY.to_dict())

    with pytest.raises(TypeError, match="policy"):
        compute_factor_research_snapshot(  # type: ignore[call-arg]
            decision_time=decision_time,
            observations=observations,
            calendar_evidence=calendar,
            sector_evidence=sectors,
            policy=replace(FACTOR_RESEARCH_POLICY, min_matured_dates=1),
        )


def test_research_module_is_absent_from_production_import_paths() -> None:
    repo_root = Path(__file__).resolve().parents[4]
    production_paths = (
        "jiuwenswarm/jiuwenswarm/quant/__init__.py",
        "jiuwenswarm/jiuwenswarm/quant/factors.py",
        "jiuwenswarm/jiuwenswarm/quant/strategy_configs.py",
        "jiuwenswarm/jiuwenswarm/extensions/quant-finance/extension.py",
        "jiuwenswarm/scripts/run_quant_pipeline.py",
        "jiuwenswarm/evaluation/run_multi_agent.py",
    )
    forbidden = {
        "jiuwenswarm.quant.factor_research",
        "jiuwenswarm.quant.factor_evidence_provider",
    }
    for relative in production_paths:
        tree = ast.parse((repo_root / relative).read_text(encoding="utf-8"))
        imports = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module is not None
        }
        imports.update(
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        )
        assert imports.isdisjoint(forbidden), relative
        assert not any(
            isinstance(node, ast.ImportFrom)
            and node.level > 0
            and (
                node.module in {"factor_research", "factor_evidence_provider"}
                or any(
                    alias.name in {"factor_research", "factor_evidence_provider"}
                    for alias in node.names
                )
            )
            for node in ast.walk(tree)
        ), relative

    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "jiuwenswarm")
    probe = """
import importlib
import sys

for module in (
    "jiuwenswarm.quant",
    "jiuwenswarm.quant.factors",
    "jiuwenswarm.quant.strategy_configs",
    "scripts.run_quant_pipeline",
    "evaluation.run_multi_agent",
):
    importlib.import_module(module)
    assert "jiuwenswarm.quant.factor_research" not in sys.modules, module
    assert "jiuwenswarm.quant.factor_evidence_provider" not in sys.modules, module
"""
    completed = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=repo_root,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
