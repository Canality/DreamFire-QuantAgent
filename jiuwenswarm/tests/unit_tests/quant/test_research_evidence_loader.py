"""Real-archive integration tests for the WP1-E2P-R1 public loader bridge.

All tests consume the already-admitted archives (official calendar, operate-year
corporate actions, E0 qfq) through the public research_evidence_loader API and
public compute_trend_snapshot - no private kernels and no trust monkeypatching.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from jiuwenswarm.quant import research_evidence_loader as loader
from jiuwenswarm.quant.candidate_factors import (
    AVAILABLE,
    FactorInputError,
    compute_trend_snapshot,
)
from jiuwenswarm.quant.factor_research import (
    FactorResearchInputError,
    MaturedFactorObservation,
    compute_factor_research_snapshot,
)
from jiuwenswarm.quant.official_calendar_archive import (
    EXPECTED_CALENDAR_EVIDENCE_SHA256,
)

# A confirmed 2025 session with 251 prior sessions (calendar starts 2024-01-02).
_DECISION = "2025-07-16"


def _sessions(decision_date: str = _DECISION, lookback: int = 251) -> pd.DatetimeIndex:
    calendar = loader.load_calendar_evidence()
    sessions = pd.DatetimeIndex(pd.to_datetime(list(calendar.sessions)))
    position = int(sessions.get_loc(pd.Timestamp(decision_date)))
    return sessions[position - lookback + 1 : position + 1]


def test_calendar_evidence_is_full_626_and_trusted() -> None:
    calendar = loader.load_calendar_evidence()
    assert calendar.calendar_id == "SSE_SZSE_A_SHARE_CONFIRMED_THROUGH_20260804"
    assert len(calendar.sessions) == 626
    assert calendar.evidence_hash == EXPECTED_CALENDAR_EVIDENCE_SHA256


def test_real_49x12_snapshot_via_public_api() -> None:
    snapshot = loader.compute_49x12_snapshot(decision_date=_DECISION)
    assert snapshot.values.shape == (49, 12)
    assert snapshot.status.shape == (49, 12)
    assert int((snapshot.status == AVAILABLE).sum().sum()) == 49 * 12
    assert int((~snapshot.values.isna()).sum().sum()) == 49 * 12
    assert snapshot.forecast_horizon == 20


def test_uniform_rescale_preserves_all_12_kernels() -> None:
    factor_input = loader.build_factor_input(decision_date=_DECISION)
    original = compute_trend_snapshot(factor_input)
    scaled_input = replace(factor_input, closes=factor_input.closes * 1.5)
    scaled = compute_trend_snapshot(scaled_input)
    pd.testing.assert_frame_equal(original.status, scaled.status)
    for factor_id in original.values.columns:
        left = original.values[factor_id].to_numpy(dtype=float)
        right = scaled.values[factor_id].to_numpy(dtype=float)
        np.testing.assert_allclose(left, right, rtol=1e-9, equal_nan=True)


def test_step_rescale_changes_at_least_one_kernel() -> None:
    factor_input = loader.build_factor_input(decision_date=_DECISION)
    original = compute_trend_snapshot(factor_input)
    closes = factor_input.closes.copy()
    midpoint = len(closes) // 2
    closes.iloc[:midpoint] = closes.iloc[:midpoint] * 1.5
    stepped = compute_trend_snapshot(replace(factor_input, closes=closes))
    max_delta = 0.0
    for factor_id in original.values.columns:
        left = original.values[factor_id].to_numpy(dtype=float)
        right = stepped.values[factor_id].to_numpy(dtype=float)
        finite = np.isfinite(left) & np.isfinite(right)
        max_delta = max(max_delta, float(np.max(np.abs(left[finite] - right[finite]))) if finite.any() else 0.0)
    assert max_delta > 1e-6


def test_eight_same_day_multi_action_groups_are_preserved() -> None:
    window = _sessions()
    evidence = loader.build_corporate_action_evidence(
        window_sessions=window,
        tickers=list(loader.load_wide_closes([d.date().isoformat() for d in window]).columns),
    )
    sh601318 = [
        action
        for action in evidence.in_window_actions
        if action[0] == "sh.601318" and action[1] == "2025-06-30"
    ]
    assert len(sh601318) == 2  # both same-day actions of sh.601318/2025-06-30
    assert sh601318[0] != sh601318[1]  # distinct full 8-tuple identities


def test_delete_or_modify_in_window_action_changes_evidence_hash() -> None:
    window = _sessions()
    tickers = list(loader.load_wide_closes([d.date().isoformat() for d in window]).columns)
    evidence = loader.build_corporate_action_evidence(window_sessions=window, tickers=tickers)
    sh601318 = [
        action
        for action in evidence.in_window_actions
        if action[0] == "sh.601318" and action[1] == "2025-06-30"
    ]
    assert len(sh601318) == 2
    without_one = tuple(
        action
        for action in evidence.in_window_actions
        if action != sh601318[0]
    )
    deleted = replace(evidence, in_window_actions=without_one)
    assert deleted.evidence_hash != evidence.evidence_hash
    modified_tuple = list(sh601318[0])
    modified_tuple[2] = "0.5"
    modified_actions = tuple(
        tuple(modified_tuple) if action == sh601318[0] else action
        for action in evidence.in_window_actions
    )
    modified = replace(evidence, in_window_actions=modified_actions)
    assert modified.evidence_hash != evidence.evidence_hash


def _factor_input_with(evidence: object):
    return replace(loader.build_factor_input(decision_date=_DECISION), corporate_action_evidence=evidence)


def test_delete_same_day_action_fails_compute_trend_snapshot() -> None:
    window = _sessions()
    tickers = list(loader.load_wide_closes([d.date().isoformat() for d in window]).columns)
    evidence = loader.build_corporate_action_evidence(window_sessions=window, tickers=tickers)
    first = evidence.in_window_actions[0]
    deleted = replace(evidence, in_window_actions=tuple(a for a in evidence.in_window_actions if a != first))
    with pytest.raises(FactorInputError, match="authoritative operate projection"):
        compute_trend_snapshot(_factor_input_with(deleted))


def test_modify_same_day_action_fails_compute_trend_snapshot() -> None:
    window = _sessions()
    tickers = list(loader.load_wide_closes([d.date().isoformat() for d in window]).columns)
    evidence = loader.build_corporate_action_evidence(window_sessions=window, tickers=tickers)
    first = list(evidence.in_window_actions[0])
    first[2] = "9.99"
    modified = replace(
        evidence,
        in_window_actions=(tuple(first),) + tuple(evidence.in_window_actions[1:]),
    )
    with pytest.raises(FactorInputError, match="authoritative operate projection"):
        compute_trend_snapshot(_factor_input_with(modified))


def test_duplicate_action_fails_compute_trend_snapshot() -> None:
    window = _sessions()
    tickers = list(loader.load_wide_closes([d.date().isoformat() for d in window]).columns)
    evidence = loader.build_corporate_action_evidence(window_sessions=window, tickers=tickers)
    duplicated = (evidence.in_window_actions[0],) + evidence.in_window_actions
    dup = replace(evidence, in_window_actions=duplicated)
    with pytest.raises(FactorInputError, match="authoritative operate projection"):
        compute_trend_snapshot(_factor_input_with(dup))


def test_reordered_actions_fail_compute_trend_snapshot() -> None:
    window = _sessions()
    tickers = list(loader.load_wide_closes([d.date().isoformat() for d in window]).columns)
    evidence = loader.build_corporate_action_evidence(window_sessions=window, tickers=tickers)
    if len(evidence.in_window_actions) < 2:
        pytest.skip("window has fewer than two actions")
    reordered = (evidence.in_window_actions[1], evidence.in_window_actions[0]) + evidence.in_window_actions[2:]
    reord = replace(evidence, in_window_actions=reordered)
    with pytest.raises(FactorInputError, match="authoritative operate projection"):
        compute_trend_snapshot(_factor_input_with(reord))


def test_broadened_window_fails_compute_trend_snapshot() -> None:
    window = _sessions()
    tickers = list(loader.load_wide_closes([d.date().isoformat() for d in window]).columns)
    evidence = loader.build_corporate_action_evidence(window_sessions=window, tickers=tickers)
    broadened = replace(evidence, window_start="2020-01-01", window_end="2025-12-31")
    with pytest.raises(FactorInputError, match="must exactly cover the input window"):
        compute_trend_snapshot(_factor_input_with(broadened))


def test_narrowed_window_fails_compute_trend_snapshot() -> None:
    window = _sessions()
    tickers = list(loader.load_wide_closes([d.date().isoformat() for d in window]).columns)
    evidence = loader.build_corporate_action_evidence(window_sessions=window, tickers=tickers)
    narrowed = replace(evidence, window_end=window[-2].date().isoformat())
    with pytest.raises(FactorInputError, match="must exactly cover the input window"):
        compute_trend_snapshot(_factor_input_with(narrowed))


def test_coverage_gate_rejects_outside_window() -> None:
    with pytest.raises(loader.ResearchEvidenceError, match="operate archive coverage"):
        window = pd.DatetimeIndex(pd.date_range("2026-01-05", periods=30, freq="B"))
        loader.build_corporate_action_evidence(window_sessions=window, tickers=["sh.600000"])


def test_calendar_non_contiguous_slice_fails() -> None:
    calendar = loader.load_calendar_evidence()
    sessions = pd.DatetimeIndex(pd.to_datetime(list(calendar.sessions)))
    window = list(sessions[100:120])
    window.pop(10)  # remove a middle session -> not a contiguous slice
    gap = pd.DatetimeIndex(window)
    with pytest.raises(FactorInputError, match="contiguous slice"):
        calendar.validate(gap)


def test_wrong_trust_tuple_fails_admission() -> None:
    window = _sessions()
    tickers = list(loader.load_wide_closes([d.date().isoformat() for d in window]).columns)
    evidence = loader.build_corporate_action_evidence(window_sessions=window, tickers=tickers)
    wrong = replace(evidence, source_version="invented/v999")
    factor_input = replace(
        loader.build_factor_input(decision_date=_DECISION),
        corporate_action_evidence=wrong,
    )
    with pytest.raises(FactorInputError, match="trusted source manifest"):
        compute_trend_snapshot(factor_input)


def test_operate_archive_tamper_is_detected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(loader, "_sha256", lambda path: "0" * 64)
    with pytest.raises(loader.ResearchEvidenceError, match="hash mismatch"):
        loader.load_operate_events()


def test_operate_archive_unverified_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    from jiuwenswarm.quant import factor_evidence_provider as provider

    class _Unverified:
        verified = False

    monkeypatch.setattr(
        provider,
        "inspect_corporate_action_operate_archive",
        lambda: _Unverified(),
    )
    window = _sessions()
    tickers = list(loader.load_wide_closes([d.date().isoformat() for d in window]).columns)
    with pytest.raises(loader.ResearchEvidenceError, match="not verified"):
        loader.build_corporate_action_evidence(window_sessions=window, tickers=tickers)


def test_future_rows_fail_closed() -> None:
    factor_input = loader.build_factor_input(decision_date=_DECISION)
    future = pd.Timestamp(_DECISION) + pd.Timedelta(days=3)
    closes = factor_input.closes.copy()
    extra_row = closes.iloc[-1:].copy()
    extra_row.index = pd.DatetimeIndex([future])
    closes = pd.concat([closes, extra_row])
    bad = replace(factor_input, closes=closes)
    with pytest.raises(FactorInputError):
        compute_trend_snapshot(bad)


def _eight_decisions() -> list[str]:
    cal = loader.load_canonical_calendar_evidence()
    sessions = pd.DatetimeIndex(pd.to_datetime(list(cal.sessions)))
    return [sessions[p].date().isoformat() for p in range(250, 250 + 8 * 30, 30)]


def test_load_forward_labels_full_archive_604() -> None:
    labels = loader.load_forward_labels()
    assert len(labels) == 604
    assert labels[0].decision_date == "2024-01-02"
    assert len({lab.decision_date for lab in labels}) == 604
    for lab in labels:
        assert len(lab.entry_open) == 49
        assert len(lab.exit_close) == 49


def test_verify_factor_snapshot_accepts_real_snapshot() -> None:
    snap = loader.compute_49x12_snapshot(decision_date=_DECISION)
    assert loader.verify_factor_snapshot(snap) is True


def test_verify_factor_snapshot_rejects_tampered_input_hash() -> None:
    snap = loader.compute_49x12_snapshot(decision_date=_DECISION)
    tampered = replace(snap, input_hash="0" * 64)
    with pytest.raises(loader.ResearchEvidenceError, match="input does not match"):
        loader.verify_factor_snapshot(tampered)


def test_verify_forward_label_accepts_real_label() -> None:
    label = loader.load_forward_labels()[0]
    assert loader.verify_forward_label(label) is True


def test_verify_forward_label_rejects_tampered_price() -> None:
    label = loader.load_forward_labels()[0]
    first = label.entry_open[0]
    tampered_open = tuple(
        (first[0], 999.0) if ticker == first[0] else (ticker, value)
        for (ticker, value) in label.entry_open
    )
    tampered = replace(label, entry_open=tampered_open)
    with pytest.raises(loader.ResearchEvidenceError, match="authoritative archive projection"):
        loader.verify_forward_label(tampered)


def test_verify_forward_label_rejects_tampered_field() -> None:
    label = loader.load_forward_labels()[0]
    with pytest.raises(loader.ResearchEvidenceError, match="authoritative archive projection"):
        loader.verify_forward_label(replace(label, available_at="2030-01-01T15:00:00+08:00"))
    with pytest.raises(loader.ResearchEvidenceError, match="authoritative archive projection"):
        loader.verify_forward_label(replace(label, calendar_id="WRONG_CALENDAR"))


def test_real_8_observation_factor_research_integration() -> None:
    decisions = _eight_decisions()
    labels = {lab.decision_date: lab for lab in loader.load_forward_labels()}
    observations = []
    max_exit = None
    for decision in decisions:
        snapshot = loader.compute_49x12_snapshot(decision_date=decision)
        loader.verify_factor_snapshot(snapshot)
        label = labels[decision]
        loader.verify_forward_label(label)
        observations.append(MaturedFactorObservation(snapshot, label))
        exit_ts = pd.Timestamp(label.exit_date)
        if max_exit is None or exit_ts > max_exit:
            max_exit = exit_ts
    research_dt = (
        pd.Timestamp(max_exit)
        .tz_localize("Asia/Shanghai")
        .replace(hour=15, minute=0, second=0)
        .to_pydatetime()
    )
    calendar = loader.load_canonical_calendar_evidence()
    sectors = loader.load_sector_metadata_evidence()
    result = compute_factor_research_snapshot(
        decision_time=research_dt,
        observations=observations,
        calendar_evidence=calendar,
        sector_evidence=sectors,
    )
    assert len(result.metrics) == 12
    assert len({metric.factor_id for metric in result.metrics}) == 12
    assert result.snapshot_hash


def test_verify_sector_metadata_accepts_real() -> None:
    evidence = loader.load_sector_metadata_evidence()
    assert loader.verify_sector_metadata(evidence) is True


def test_verify_sector_metadata_rejects_swapped_sectors() -> None:
    evidence = loader.load_sector_metadata_evidence()
    swapped = list(evidence.sectors)
    ticker0, sector0 = swapped[0]
    ticker1, sector1 = swapped[1]
    swapped[0] = (ticker0, sector1)
    swapped[1] = (ticker1, sector0)
    forged = replace(evidence, sectors=tuple(sorted(swapped)))
    # structural counts preserved: 49 tickers, 6 sectors, min group counts
    assert len({t for t, _ in forged.sectors}) == 49
    assert len({name for _, name in forged.sectors}) == 6
    with pytest.raises(loader.ResearchEvidenceError, match="authoritative workbook projection"):
        loader.verify_sector_metadata(forged)


def test_sector_swap_rejected_in_factor_research_path() -> None:
    decisions = _eight_decisions()
    labels = {lab.decision_date: lab for lab in loader.load_forward_labels()}
    observations = []
    max_exit = None
    for decision in decisions:
        snapshot = loader.compute_49x12_snapshot(decision_date=decision)
        label = labels[decision]
        observations.append(MaturedFactorObservation(snapshot, label))
        exit_ts = pd.Timestamp(label.exit_date)
        if max_exit is None or exit_ts > max_exit:
            max_exit = exit_ts
    research_dt = (
        pd.Timestamp(max_exit)
        .tz_localize("Asia/Shanghai")
        .replace(hour=15, minute=0, second=0)
        .to_pydatetime()
    )
    calendar = loader.load_canonical_calendar_evidence()
    sectors = loader.load_sector_metadata_evidence()
    swapped = list(sectors.sectors)
    ticker0, sector0 = swapped[0]
    ticker1, sector1 = swapped[1]
    swapped[0] = (ticker0, sector1)
    swapped[1] = (ticker1, sector0)
    forged = replace(sectors, sectors=tuple(sorted(swapped)))
    with pytest.raises(FactorResearchInputError, match="authoritative workbook projection"):
        compute_factor_research_snapshot(
            decision_time=research_dt,
            observations=observations,
            calendar_evidence=calendar,
            sector_evidence=forged,
        )


def test_verify_sector_metadata_rejects_wrong_fields() -> None:
    evidence = loader.load_sector_metadata_evidence()
    with pytest.raises(loader.ResearchEvidenceError, match="authoritative workbook projection"):
        loader.verify_sector_metadata(replace(evidence, effective_date="2030-01-01"))
    with pytest.raises(loader.ResearchEvidenceError, match="authoritative workbook projection"):
        loader.verify_sector_metadata(replace(evidence, observed_at="2030-01-01T00:00:00+08:00"))
    with pytest.raises(loader.ResearchEvidenceError, match="authoritative workbook projection"):
        loader.verify_sector_metadata(replace(evidence, source_version="invented/v1"))
    with pytest.raises(loader.ResearchEvidenceError, match="authoritative workbook projection"):
        loader.verify_sector_metadata(replace(evidence, archive_evidence_sha256="0" * 64))
    reordered = replace(evidence, sectors=tuple(reversed(evidence.sectors)))
    with pytest.raises(loader.ResearchEvidenceError, match="authoritative workbook projection"):
        loader.verify_sector_metadata(reordered)


_GENERATOR = (
    Path(__file__).resolve().parents[3] / "scripts" / "generate_official_forward_labels.py"
)
_V2_DIR = (
    Path(__file__).resolve().parents[3]
    / "evaluation"
    / "research_evidence"
    / "official_forward_label_2024_2026_v2"
)


def _run_generator(out_dir: Path) -> None:
    result = subprocess.run(
        [sys.executable, str(_GENERATOR), "--out-dir", str(out_dir)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_v2_generator_deterministic_byte_equal(tmp_path: Path) -> None:
    out_a = tmp_path / "a"
    out_b = tmp_path / "b"
    _run_generator(out_a)
    _run_generator(out_b)
    assert (out_a / "forward_labels.csv").read_bytes() == (
        out_b / "forward_labels.csv"
    ).read_bytes()
    assert (out_a / "source_records.json").read_bytes() == (
        out_b / "source_records.json"
    ).read_bytes()


def test_v2_generator_matches_committed(tmp_path: Path) -> None:
    out = tmp_path / "committed"
    _run_generator(out)
    assert (out / "forward_labels.csv").read_bytes() == (
        _V2_DIR / "forward_labels.csv"
    ).read_bytes()
    assert (out / "source_records.json").read_bytes() == (
        _V2_DIR / "source_records.json"
    ).read_bytes()


def test_v2_archive_604x49_coverage() -> None:
    labels = loader.load_forward_labels()
    assert len(labels) == 604
    for label in labels:
        assert len(label.entry_open) == 49
        assert len(label.exit_close) == 49
        assert {t for t, _ in label.entry_open} == {t for t, _ in label.exit_close}


def test_v2_entry_exit_calendar_positions() -> None:
    calendar = loader.load_canonical_calendar_evidence()
    sessions = pd.DatetimeIndex(pd.to_datetime(list(calendar.sessions)))
    labels = loader.load_forward_labels()
    for label in labels:
        position = int(sessions.get_loc(pd.Timestamp(label.decision_date)))
        assert label.entry_date == sessions[position + 2].date().isoformat()
        assert label.exit_date == sessions[position + 21].date().isoformat()
        assert label.valuation_dates == tuple(
            sessions[position + 2 + offset].date().isoformat()
            for offset in range(20)
        )


def test_v2_entry_exit_prices_match_qfq() -> None:
    labels = loader.load_forward_labels()
    # sample the first and last label: verify entry_open / exit_close against qfq
    for label in (labels[0], labels[-1]):
        entry = label.entry_date
        exit_day = label.exit_date
        for ticker, open_value in label.entry_open:
            qfq_open = _qfq_price(entry, ticker, "open")
            if open_value is not None:
                assert abs(open_value - qfq_open) < 1e-9
        for ticker, close_value in label.exit_close:
            qfq_close = _qfq_price(exit_day, ticker, "close")
            if close_value is not None:
                assert abs(close_value - qfq_close) < 1e-9


def _repository_root_path() -> Path:
    return Path(__file__).resolve().parents[3]


def _qfq_price(date: str, ticker: str, field: str) -> float:
    import csv as _csv

    qfq_path = _repository_root_path() / "evaluation" / "research_evidence" / (
        "e0_factor_snapshot_2020_2026/qfq_ohlcv.csv"
    )
    with qfq_path.open("r", encoding="utf-8", newline="") as handle:
        for row in _csv.DictReader(handle):
            if row["date"] == date and row["code"] == ticker:
                return float(row[field])
    raise AssertionError(f"qfq row missing for {date} {ticker}")


def test_v2_old_decision_plus_one_entry_rejected() -> None:
    # The old archive used decision+1 (the embargo session) as entry.  The v2
    # loader's _build_forward_label must reject a CSV row that does so.
    labels = loader.load_forward_labels()
    label = labels[0]
    row = {
        "decision_date": label.decision_date,
        "embargo_date": label.decision_date,
        "entry_open_date": label.decision_date,  # wrong: must be decision+2
        "exit_close_date": label.exit_date,
        "valuation_dates": "",
        **{f"{t}_entry_open": "100.0" for t, _ in label.entry_open},
        **{f"{t}_exit_close": "100.0" for t, _ in label.exit_close},
    }
    calendar = loader.load_canonical_calendar_evidence()
    with pytest.raises(loader.ResearchEvidenceError, match="entry_open_date"):
        loader._build_forward_label(label.decision_date, row, calendar)


def test_v2_csv_records_row_hash_mismatch_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_json = loader._json_loads

    def tampered_json(path: Path) -> dict:
        records = real_json(path)
        first = next(iter(records["per_decision"]))
        records["per_decision"][first]["canonical_row_hash"] = "0" * 64
        records["evidence_sha256"] = loader._canonical_hash(
            {k: v for k, v in records.items() if k != "evidence_sha256"}
        )
        return records

    monkeypatch.setattr(loader, "_json_loads", tampered_json)
    with pytest.raises(loader.ResearchEvidenceError, match="does not match source_records"):
        loader.load_forward_labels()


def test_v2_label_source_version_and_legacy_v1_rejected() -> None:
    labels = loader.load_forward_labels()
    assert labels[0].source_version == "official_forward_label_2024_2026/v2"
    loader.verify_forward_label(labels[0])
    legacy = replace(labels[0], source_version="official_forward_label_2020_2026/v1")
    with pytest.raises(loader.ResearchEvidenceError, match="authoritative archive projection"):
        loader.verify_forward_label(legacy)
