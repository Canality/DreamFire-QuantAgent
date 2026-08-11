"""WP1-E2C-R1 tests for the research-only strategy-pool replay module."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from evaluation.strategy_pool_replay import (
    MIN_MATURED_WINDOWS,
    PREREGISTERED_THRESHOLDS,
    REASON_BENCHMARK_UNAVAILABLE,
    REASON_DOES_NOT_QUALIFY,
    REASON_QUALIFIED,
    artifact_hash,
    build_deterministic_payload,
    canonical_json,
    compute_decision_set,
    evaluate_candidate,
    prior_matured_decisions,
    run_replay,
    verify_artifact,
    window_hash,
    _to_loader,
    _to_production,
)
from jiuwenswarm.quant.evaluation_protocol import CompetitionWindowPolicy
from jiuwenswarm.quant.factors import PositionConfig, PositionSizer

_REPO_ROOT = Path(__file__).resolve().parents[4]


def _sessions(periods: int, start: str = "2024-01-01") -> pd.DatetimeIndex:
    return pd.DatetimeIndex(pd.bdate_range(start, periods=periods))


def _rows(values: list[tuple[float, float]]) -> dict[str, dict[str, float]]:
    return {f"d{index}": {"total_return": r, "max_drawdown": d} for index, (r, d) in enumerate(values)}


def test_thresholds_match_preregistration() -> None:
    assert PREREGISTERED_THRESHOLDS == {
        "median_return_delta_min": 0.003,
        "paired_utility_win_rate_min": 0.60,
        "recent_four_utility_wins_min": 3,
        "median_drawdown_worsening_max": 0.003,
        "worst_return_worsening_max": 0.005,
    }


def test_ticker_format_round_trip() -> None:
    assert _to_production("sh.601318") == "601318.SH"
    assert _to_loader("601318.SH") == "sh.601318"
    assert _to_loader(_to_production("sz.000858")) == "sz.000858"


def test_decision_set_fail_closed_below_minimum() -> None:
    sessions = _sessions(280)
    labels = [sessions[index].date().isoformat() for index in range(250, 253)]
    policy = CompetitionWindowPolicy()
    with pytest.raises(ValueError, match="insufficient matured"):
        compute_decision_set(sessions, labels, policy)


def test_decision_set_selects_non_overlapping_matured() -> None:
    sessions = _sessions(520)
    label_positions = list(range(250, 520, 20))
    labels = [sessions[index].date().isoformat() for index in label_positions]
    policy = CompetitionWindowPolicy()
    selected = compute_decision_set(sessions, labels, policy)
    assert len(selected) >= 8
    positions = [sessions.get_loc(pd.Timestamp(decision)) for decision in selected]
    for previous, next_position in zip(positions, positions[1:]):
        assert next_position >= previous + policy.holding_days


def test_prior_matured_decisions_excludes_not_yet_realized() -> None:
    policy = CompetitionWindowPolicy()
    selected = ("2025-01-02", "2025-02-01", "2025-03-05")
    positions = {"2025-01-02": 250, "2025-02-01": 270, "2025-03-05": 292}
    matured = prior_matured_decisions("2025-03-05", selected, positions, policy)
    assert "2025-01-02" in matured
    assert "2025-02-01" in matured
    not_matured = prior_matured_decisions("2025-02-01", selected, positions, policy)
    assert "2025-01-02" not in not_matured


def test_evaluate_candidate_qualifies_above_thresholds() -> None:
    production = _rows([(0.01, 0.05)] * 8)
    candidate = _rows([(0.02, 0.05)] * 8)
    result = evaluate_candidate(candidate, production)
    assert result["verdict"] == REASON_QUALIFIED


def test_evaluate_candidate_does_not_qualify_below_thresholds() -> None:
    production = _rows([(0.02, 0.05)] * 8)
    candidate = _rows([(0.01, 0.05)] * 8)
    result = evaluate_candidate(candidate, production)
    assert result["verdict"] == REASON_DOES_NOT_QUALIFY


def test_evaluate_candidate_insufficient_windows_fail_closed() -> None:
    production = _rows([(0.01, 0.05)])
    candidate = _rows([(0.02, 0.05)])
    result = evaluate_candidate(candidate, production)
    assert result["verdict"] == REASON_DOES_NOT_QUALIFY
    assert "insufficient" in result["reason"]


def test_benchmark_unavailable_constant() -> None:
    assert REASON_BENCHMARK_UNAVAILABLE == "BENCHMARK_UNAVAILABLE"


def test_allocation_respects_final_constraints() -> None:
    tickers = [f"sh.{600000 + index:06d}" for index in range(49)]
    sectors = {ticker: f"S{index % 6}" for index, ticker in enumerate(tickers)}
    rng = np.random.default_rng(0)
    closes = pd.DataFrame(
        rng.normal(100.0, 5.0, size=(60, 49)),
        columns=tickers,
        index=pd.date_range("2025-01-01", periods=60),
    )
    scores = pd.DataFrame(
        {"composite": rng.normal(0.0, 1.0, size=49)},
        index=tickers,
    )
    scores["sector"] = [sectors[ticker] for ticker in scores.index]
    scores = scores.sort_values("composite", ascending=False)
    config = PositionConfig(
        top_n_stocks=15,
        max_single_stock=0.10,
        max_single_sector=0.25,
        min_cash=0.05,
    )
    weights = PositionSizer(config).allocate(scores, closes)
    assert sum(weights.values()) <= 0.95 + 1e-9
    assert all(value <= 0.10 + 1e-9 for value in weights.values())
    sector_totals: dict[str, float] = {}
    for ticker, weight in weights.items():
        sector_totals[sectors[ticker]] = sector_totals.get(sectors[ticker], 0.0) + weight
    assert all(value <= 0.25 + 1e-9 for value in sector_totals.values())


def test_readiness_gate_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    import evaluation.strategy_pool_replay as replay

    fake = SimpleNamespace(
        capabilities=[
            SimpleNamespace(
                capability="OFFICIAL_FORWARD_LABEL",
                available=False,
                reason="X",
            )
        ],
        ready_for_e0=True,
        ready_for_e1=True,
    )
    monkeypatch.setattr(replay, "inspect_research_evidence_readiness", lambda: fake)
    with pytest.raises(RuntimeError, match="OFFICIAL_FORWARD_LABEL"):
        run_replay(out_dir=None)


def test_production_import_isolation() -> None:
    for relative in (
        "jiuwenswarm/evaluation/run_multi_agent.py",
        "jiuwenswarm/scripts/run_quant_pipeline.py",
    ):
        source = (_REPO_ROOT / relative).read_text(encoding="utf-8", errors="replace")
        assert "strategy_pool_replay" not in source, relative


def test_evaluate_candidate_fails_closed_with_seven_windows() -> None:
    production = _rows([(0.01, 0.05)] * 7)
    candidate = _rows([(0.02, 0.05)] * 7)
    result = evaluate_candidate(candidate, production)
    assert result["verdict"] == REASON_DOES_NOT_QUALIFY
    assert result["reason"] == "insufficient comparable windows"
    assert result["n_windows"] == 7


def test_evaluate_candidate_evaluable_with_eight_windows() -> None:
    production = _rows([(0.01, 0.05)] * 8)
    candidate = _rows([(0.02, 0.05)] * 8)
    result = evaluate_candidate(candidate, production)
    assert result["verdict"] == REASON_QUALIFIED
    assert result["n_windows"] == MIN_MATURED_WINDOWS


def test_canonical_json_is_deterministic() -> None:
    first = {"b": 1, "a": [2, 1]}
    second = {"a": [2, 1], "b": 1}
    assert canonical_json(first) == canonical_json(second)


def _synthetic_deterministic() -> dict[str, object]:
    windows = [
        {
            "decision_date": "2025-01-14",
            "entry_date": "2025-01-16",
            "exit_date": "2025-02-20",
            "valuation_dates": ["2025-01-16"],
            "candidates": {
                "t2_comparator": {"status": "OK", "total_return": 0.01},
                "similar_market_blend": {"status": "BENCHMARK_UNAVAILABLE"},
            },
        }
    ]
    return build_deterministic_payload(
        inventory_hash="a" * 64,
        decision_set=["2025-01-14"],
        windows=windows,
        candidates={"t2_comparator": {"verdict": "QUALIFIED"}},
    )


def test_artifact_hash_deterministic_and_tamper_detected() -> None:
    first = _synthetic_deterministic()
    payload = {"deterministic": first, "artifact_sha256": artifact_hash(first)}
    assert verify_artifact(payload)
    second = _synthetic_deterministic()
    assert artifact_hash(second) == artifact_hash(first)
    tampered = json.loads(canonical_json(first))
    tampered["windows"][0]["candidates"]["t2_comparator"]["total_return"] = 0.02
    payload_tampered = {
        "deterministic": tampered,
        "artifact_sha256": artifact_hash(first),
    }
    assert not verify_artifact(payload_tampered)


def test_window_hash_detects_tamper() -> None:
    window = {
        "decision_date": "2025-01-14",
        "candidates": {"t2_comparator": {"total_return": 0.01}},
    }
    stored = window_hash(window)
    tampered = dict(window)
    tampered["candidates"] = {"t2_comparator": {"total_return": 0.02}}
    assert window_hash(tampered) != stored


def test_verify_artifact_rejects_missing_deterministic() -> None:
    assert not verify_artifact({"meta": {}})
    assert not verify_artifact({})
