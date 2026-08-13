"""WP1-E4-R1 tests for the research-only full dynamic selector replay module.

Covers location.json's negative-coverage map: decision-set drift, future-window
and whole-replay-verdict mutation independence, one-shot call counts, variant
independence, A0 == production identity, composition determinism (tie-break,
excluded slot, invalid weights, missing composite, selection==allocation, final
constraints, 49-stock / six-sector coverage), Block Bootstrap binding, resource
fail-closed validation, artifact tamper and production/direct/formal isolation.

All tests are self-contained: the E2C-shaped payload is synthetic (same shape the
accepted E2C artifact uses), closes are a seeded synthetic 251-session frame over
the official 49 production tickers, and the model is an injected callable.  No
network, no real model, no untracked ``output/`` artifact and no direct/formal/
RPC/E2E run.
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from evaluation.dynamic_selector_replay import (
    BASE_SLOT_STATE,
    BOOTSTRAP_BLOCK_WINDOWS,
    BOOTSTRAP_ITERATIONS,
    BOOTSTRAP_SEED,
    COMPARISON_BASELINE,
    ELIGIBLE_SLOTS,
    EXPECTED_DECISION_SET,
    FALLBACK_SLOT,
    GLOBALLY_EXCLUDED_SLOTS,
    RESEARCH_SCHEMA,
    RESOURCE_CEILING_PROCESS_PEAK_RSS_MB_MAX,
    RESOURCE_CEILING_TOTAL_WALL_TIME_SECONDS_MAX,
    SAMPLER_INTERVAL_SECONDS,
    SELECTED_VARIANT,
    SELECTOR_VERSION,
    UNIVERSE_SIZE,
    VARIANTS,
    _blend_frames,
    _check_a0_matches_e2c_production,
    _to_loader,
    _to_production,
    _validate_decision_set,
    _validate_final_weights,
    artifact_hash,
    blended_scores,
    build_resource_record,
    canonical_json,
    compose_portfolio,
    decision_composition,
    run_selector_replay,
    selector_identity_hash,
    selector_summary,
    slot_composite_scores,
    verify_resource_record,
    verify_selector_payload,
    window_hash,
)
from jiuwenswarm.quant.factors import SECTOR_MAP
from jiuwenswarm.quant.nested_evaluation import NestedEvaluationPlan

_REPO_ROOT = Path(__file__).resolve().parents[4]

_DECISION_SET = EXPECTED_DECISION_SET


def _decision_time(decision_date: str) -> datetime:
    from evaluation.strategy_fusion_replay import _decision_time as resolve

    return resolve(decision_date)


# ---------------------------------------------------------------------------
# Synthetic E2C-shaped payload (same shape the accepted E2C artifact uses).
# ---------------------------------------------------------------------------


def _synthetic_window(decision_date: str, *, exit_date: str | None = None) -> dict[str, object]:
    content: dict[str, object] = {
        "decision_date": decision_date,
        "entry_date": decision_date,
        "exit_date": exit_date if exit_date is not None else decision_date,
        "valuation_dates": [decision_date],
        "candidates": {
            "production_six_factor": {
                "status": "OK",
                "total_return": 0.02,
                "max_drawdown": 0.05,
            },
            "t2_comparator": {
                "status": "OK",
                "total_return": 0.025,
                "max_drawdown": 0.048,
            },
        },
    }
    content["window_hash"] = window_hash(content)
    return content


def _window_exit_dates() -> dict[str, str]:
    exits: dict[str, str] = {}
    for index, decision in enumerate(_DECISION_SET):
        if index + 1 < len(_DECISION_SET):
            exits[decision] = (
                date.fromisoformat(_DECISION_SET[index + 1]) - timedelta(days=1)
            ).isoformat()
        else:
            exits[decision] = (
                date.fromisoformat(decision) + timedelta(days=21)
            ).isoformat()
    return exits


def _synthetic_payload() -> dict[str, object]:
    exits = _window_exit_dates()
    windows = [
        _synthetic_window(decision, exit_date=exits[decision])
        for decision in _DECISION_SET
    ]
    candidates = {
        "production_six_factor": {"status": "OK", "n_windows": 12},
        "t2_comparator": {"verdict": "QUALIFIED", "n_windows": 12},
    }
    deterministic = {
        "inventory_hash": "2" * 64,
        "decision_set": list(_DECISION_SET),
        "windows": windows,
        "candidates": candidates,
    }
    return {
        "task_id": "SYNTHETIC",
        "deterministic": deterministic,
        "artifact_sha256": artifact_hash(deterministic),
    }


def _rehash(payload: dict[str, object]) -> dict[str, object]:
    deterministic = payload["deterministic"]
    for window in deterministic["windows"]:
        window["window_hash"] = window_hash(window)
    payload["artifact_sha256"] = artifact_hash(deterministic)
    return payload


def _copy(payload: dict[str, object]) -> dict[str, object]:
    return json.loads(canonical_json(payload))


# ---------------------------------------------------------------------------
# Synthetic 251-session close frame over the official 49 production tickers.
# ---------------------------------------------------------------------------


def _synthetic_closes(
    n_sessions: int = 251, seed: int = 0, sigma: float = 0.005
) -> pd.DataFrame:
    prod_tickers = sorted(SECTOR_MAP.keys())
    loader_tickers = [_to_loader(ticker) for ticker in prod_tickers]
    rng = np.random.default_rng(seed)
    paths = np.cumsum(rng.normal(0.0, sigma, size=(n_sessions, len(prod_tickers))), axis=0)
    base = 100.0 * np.exp(paths)
    return pd.DataFrame(
        base,
        columns=loader_tickers,
        index=pd.bdate_range("2024-01-01", periods=n_sessions),
    )


# ---------------------------------------------------------------------------
# Frozen constants and global eligibility.
# ---------------------------------------------------------------------------


def test_frozen_constants_and_identity() -> None:
    assert ELIGIBLE_SLOTS == ("production_six_factor", "t2_comparator")
    assert FALLBACK_SLOT == "production_six_factor"
    assert GLOBALLY_EXCLUDED_SLOTS == (
        "trend_short_5_10_20",
        "trend_medium_20_60",
        "trend_long_120_250",
        "similar_market_blend",
    )
    assert VARIANTS == ("A0_no_agent", "A1_alpha_only", "A2_alpha_risk")
    assert SELECTED_VARIANT == "A2_alpha_risk"
    assert COMPARISON_BASELINE == "A0_no_agent"
    assert BASE_SLOT_STATE == {"production_six_factor": 1.0, "t2_comparator": 0.0}
    assert len(EXPECTED_DECISION_SET) == 12
    assert EXPECTED_DECISION_SET[0] == "2025-01-14"
    assert EXPECTED_DECISION_SET[-1] == "2025-12-11"
    assert RESEARCH_SCHEMA == "research_selector_resource/v1"
    assert isinstance(SELECTOR_VERSION, str) and SELECTOR_VERSION


def test_bootstrap_binding_matches_nested_evaluation_plan() -> None:
    plan = NestedEvaluationPlan()
    assert BOOTSTRAP_SEED == plan.seed == 20260804
    assert BOOTSTRAP_ITERATIONS == plan.bootstrap_iterations == 2000
    assert BOOTSTRAP_BLOCK_WINDOWS == plan.bootstrap_block_windows == 3


def test_resource_ceilings_and_sampler_interval() -> None:
    assert RESOURCE_CEILING_TOTAL_WALL_TIME_SECONDS_MAX == 1800.0
    assert RESOURCE_CEILING_PROCESS_PEAK_RSS_MB_MAX == 2048.0
    assert SAMPLER_INTERVAL_SECONDS == 0.05


def test_ticker_format_round_trip() -> None:
    assert _to_production("sh.601318") == "601318.SH"
    assert _to_loader("601318.SH") == "sh.601318"
    assert _to_loader(_to_production("sh.600036")) == "sh.600036"


# ---------------------------------------------------------------------------
# Decision inventory exactness.
# ---------------------------------------------------------------------------


def test_decision_set_accepts_the_frozen_inventory() -> None:
    _validate_decision_set(list(EXPECTED_DECISION_SET))
    _validate_decision_set(tuple(EXPECTED_DECISION_SET))


def test_decision_set_drift_fails_closed() -> None:
    with pytest.raises(RuntimeError, match="drift"):
        _validate_decision_set(list(EXPECTED_DECISION_SET)[:-1])
    with pytest.raises(RuntimeError, match="drift"):
        _validate_decision_set(list(EXPECTED_DECISION_SET) + ["2026-01-08"])
    with pytest.raises(RuntimeError, match="drift"):
        _validate_decision_set(["2025-01-14"])


# ---------------------------------------------------------------------------
# Final slot weights validation.
# ---------------------------------------------------------------------------


def test_final_weights_must_be_valid() -> None:
    good = _validate_final_weights(BASE_SLOT_STATE)
    assert good == {"production_six_factor": 1.0, "t2_comparator": 0.0}
    with pytest.raises(ValueError, match="cover exactly"):
        _validate_final_weights({"production_six_factor": 1.0})
    with pytest.raises(ValueError, match="non-negative"):
        _validate_final_weights({"production_six_factor": 1.1, "t2_comparator": -0.1})
    with pytest.raises(ValueError, match="finite"):
        _validate_final_weights(
            {"production_six_factor": float("nan"), "t2_comparator": 0.0}
        )
    with pytest.raises(ValueError, match="sum to 1.0"):
        _validate_final_weights({"production_six_factor": 0.5, "t2_comparator": 0.2})


# ---------------------------------------------------------------------------
# Composition: A0 identity, blend, tie-break, constraints.
# ---------------------------------------------------------------------------


def _a0_loader_weights() -> dict[str, float]:
    closes = _synthetic_closes()
    weights_prod, _ = compose_portfolio(BASE_SLOT_STATE, closes)
    return {_to_loader(t): w for t, w in weights_prod.items()}


def test_a0_equals_production_composite_exactly() -> None:
    closes = _synthetic_closes()
    weights_prod, blended = compose_portfolio(BASE_SLOT_STATE, closes)
    # A0 blend is the production composite exactly (t2 weight 0).
    assert set(weights_prod) == set(blended.index) & set(weights_prod)
    # The blend universe keeps the top-15 selection and all six sectors.
    assert len(blended) >= 15
    assert blended["sector"].nunique() == 6


def test_a0_mismatch_vs_e2c_production_fails_closed() -> None:
    payload = _synthetic_payload()
    window = payload["deterministic"]["windows"][0]
    decision = window["decision_date"]
    window["candidates"]["production_six_factor"]["weights"] = {"sh.601318": 0.2}
    # A matching A0 passes the identity check.
    good_composition = {"A0_no_agent": {"weights_loader": {"sh.601318": 0.2}}}
    _check_a0_matches_e2c_production(payload, decision, good_composition)
    # Any A0 weight drift from the accepted E2C production portfolio fails closed.
    bad_composition = {"A0_no_agent": {"weights_loader": {"sh.601318": 0.1}}}
    with pytest.raises(AssertionError, match="does not equal"):
        _check_a0_matches_e2c_production(payload, decision, bad_composition)


def test_composition_is_deterministic_and_tie_break_fixed() -> None:
    closes = _synthetic_closes()
    weights_a, blended_a = compose_portfolio(
        {"production_six_factor": 0.6, "t2_comparator": 0.4}, closes
    )
    weights_b, blended_b = compose_portfolio(
        {"production_six_factor": 0.6, "t2_comparator": 0.4}, closes
    )
    assert weights_a == weights_b
    # The blended frame order is fixed: composite descending, ties by the
    # loader-built close-frame row order.
    assert blended_a["composite"].tolist() == blended_b["composite"].tolist()
    order = {ticker: index for index, ticker in enumerate(closes.rename(columns=_to_production).columns)}
    for first, second in zip(blended_a.index, blended_a.index[1:]):
        if blended_a["composite"].loc[first] == blended_a["composite"].loc[second]:
            assert order[first] < order[second]


def test_excluded_or_zero_weight_slot_contributes_nothing() -> None:
    closes = _synthetic_closes()
    # t2 weight 0 -> blend is exactly the production composite.
    weights_zero, blended_zero = compose_portfolio(BASE_SLOT_STATE, closes)
    production_scores = slot_composite_scores(
        closes.rename(columns=_to_production), "production_six_factor"
    )
    assert blended_zero["composite"].loc[production_scores.index].equals(
        production_scores["composite"]
    )


def test_invalid_final_weights_fail_closed() -> None:
    closes = _synthetic_closes()
    for bad in (
        {"production_six_factor": 1.0},
        {"production_six_factor": 1.1, "t2_comparator": -0.1},
        {"production_six_factor": float("nan"), "t2_comparator": 0.0},
        {"production_six_factor": 0.5, "t2_comparator": 0.2},
    ):
        with pytest.raises(ValueError):
            compose_portfolio(bad, closes)


def test_missing_slot_composite_fails_closed() -> None:
    closes = _synthetic_closes()
    closes_prod = closes.rename(columns=_to_production)
    production = slot_composite_scores(closes_prod, "production_six_factor")
    t2 = slot_composite_scores(closes_prod, "phase_b_t2_score_alloc")
    # Drop one stock from the t2 frame so the two slots cover different sets.
    t2_missing = t2.drop(t2.index[0])
    with pytest.raises(ValueError, match="identical post-filter eligible"):
        _blend_frames(BASE_SLOT_STATE, {"production_six_factor": production, "t2_comparator": t2_missing}, closes_prod)


def test_selection_set_equals_allocation_keys() -> None:
    closes = _synthetic_closes()
    for weights in (
        {"production_six_factor": 1.0, "t2_comparator": 0.0},
        {"production_six_factor": 0.6, "t2_comparator": 0.4},
    ):
        weights_prod, blended = compose_portfolio(weights, closes)
        top_n = blended.head(15)
        assert set(weights_prod) == set(top_n.index)


def test_post_normalization_constraints_hold() -> None:
    closes = _synthetic_closes()
    for weights in (
        {"production_six_factor": 1.0, "t2_comparator": 0.0},
        {"production_six_factor": 0.5, "t2_comparator": 0.5},
    ):
        weights_prod, _ = compose_portfolio(weights, closes)
        assert sum(weights_prod.values()) <= 0.95 + 1e-9
        assert all(v <= 0.10 + 1e-9 for v in weights_prod.values())
        assert sum(weights_prod.values()) >= 0.0


def test_coverage_49_stock_six_sector_source_universe() -> None:
    closes = _synthetic_closes()
    closes_prod = closes.rename(columns=_to_production)
    assert len(closes_prod.columns) == UNIVERSE_SIZE
    blended = blended_scores(BASE_SLOT_STATE, closes_prod)
    assert blended["sector"].nunique() == 6
    # The blend universe is a subset of the official 49.
    assert set(blended.index) <= set(closes_prod.columns)


def test_source_universe_must_be_49_stocks() -> None:
    closes = _synthetic_closes()
    closes_prod = closes.rename(columns=_to_production).iloc[:, :40]
    with pytest.raises(ValueError, match="official 49"):
        blended_scores(BASE_SLOT_STATE, closes_prod)


def test_source_losing_a_full_sector_fails_closed() -> None:
    closes_prod = _synthetic_closes().rename(columns=_to_production)
    assert len(closes_prod.columns) == UNIVERSE_SIZE
    first = sorted(SECTOR_MAP)[0]
    sector = SECTOR_MAP[first]
    keep = [ticker for ticker in closes_prod.columns if SECTOR_MAP[ticker] != sector]
    reduced = closes_prod[keep]
    # A whole sector missing from the source frame is source-coverage loss: the
    # source no longer covers the official 49 stocks across six sectors.
    assert len(reduced.columns) < UNIVERSE_SIZE
    assert len({SECTOR_MAP[ticker] for ticker in reduced.columns}) < 6
    with pytest.raises(ValueError, match="official 49"):
        blended_scores(BASE_SLOT_STATE, reduced)


def test_identical_shared_post_filter_exclusions_pass() -> None:
    closes_prod = _synthetic_closes().rename(columns=_to_production)
    assert len(closes_prod.columns) == UNIVERSE_SIZE
    frames = {
        "production_six_factor": slot_composite_scores(
            closes_prod, "production_six_factor"
        ),
        "t2_comparator": slot_composite_scores(
            closes_prod, "phase_b_t2_score_alloc"
        ),
    }
    dropped_prod = set(closes_prod.columns) - set(
        frames["production_six_factor"].index
    )
    dropped_t2 = set(closes_prod.columns) - set(frames["t2_comparator"].index)
    # Contract v2: the frozen composite recipe (compute_factors ->
    # compute_scores -> filter_high_volatility) drops the SAME official tickers
    # from BOTH slots.  A shared post-filter exclusion is accepted and is not
    # source-coverage loss; the gate is that the two slots' eligible ticker sets
    # are identical.
    assert dropped_prod
    assert dropped_t2 == dropped_prod
    blended = _blend_frames(BASE_SLOT_STATE, frames, closes_prod)
    # The blend universe is exactly the common eligible set (a proper subset of
    # the official 49 because of the shared exclusion), and the source frame
    # still covers the official 49 stocks.
    assert set(blended.index) == set(frames["production_six_factor"].index)
    assert len(blended.index) < UNIVERSE_SIZE
    assert blended["sector"].nunique() == 6


def test_decision_record_binds_eligible_and_excluded() -> None:
    payload = _synthetic_payload()
    closes = _synthetic_closes()
    decision = _DECISION_SET[0]

    def noop(_role: str, _summary: object) -> str:
        return "[]"

    composition = decision_composition(
        payload, decision, noop, closes_loader=closes
    )
    eligible = composition["eligible_universe"]
    excluded = composition["excluded_stocks"]
    all_loader = sorted(closes.columns)
    assert eligible == sorted(eligible)
    assert excluded == sorted(excluded)
    assert set(eligible) | set(excluded) == set(all_loader)
    assert set(eligible) & set(excluded) == set()
    assert len(eligible) + len(excluded) == len(all_loader)
    # The shared post-filter exclusion is present on the synthetic seed-0 data,
    # so the excluded list is non-empty and the eligible list is a proper subset.
    assert set(excluded)
    assert len(eligible) < len(all_loader)


# ---------------------------------------------------------------------------
# One-shot bundle, variant independence, PIT mutation independence.
# ---------------------------------------------------------------------------


def _counting_and_proposal_model(calls: list[str]):
    def model(role: str, summary: object) -> str:
        calls.append(role)
        return "[]"

    return model


def test_decision_composition_calls_model_once_per_role() -> None:
    payload = _synthetic_payload()
    closes = _synthetic_closes()
    calls: list[str] = []
    decision = _DECISION_SET[3]
    decision_composition(
        payload, decision, _counting_and_proposal_model(calls), closes_loader=closes
    )
    assert calls == ["alpha", "risk_evidence"]
    assert len(calls) == 2


def test_all_variants_always_evaluated_and_a0_is_baseline() -> None:
    payload = _synthetic_payload()
    closes = _synthetic_closes()
    decision = _DECISION_SET[3]
    from evaluation.strategy_fusion_replay import build_evidence_registry

    registry = build_evidence_registry(payload, decision)
    evidence_ids = sorted(registry)

    def model(role: str, _summary: object) -> str:
        if role == "alpha":
            t2_ref = next(i for i in evidence_ids if "t2_comparator" in i)
            return json.dumps(
                [
                    {
                        "slot": "t2_comparator",
                        "signal": "strengthen",
                        "confidence": "high",
                        "evidence_ids": [t2_ref],
                        "rationale": "r",
                    }
                ]
            )
        return json.dumps(
            [
                {
                    "slot": "production_six_factor",
                    "signal": "hold",
                    "confidence": "medium",
                    "evidence_ids": [],
                    "rationale": "keep",
                }
            ]
        )

    composition = decision_composition(
        payload, decision, model, closes_loader=closes
    )
    assert set(composition) == set(VARIANTS) | {"eligible_universe", "excluded_stocks"}
    # A0 is the production hard fallback exactly.
    assert composition["A0_no_agent"]["weights_loader"] == _a0_loader_weights()
    # A1/A2 tilt towards t2 relative to A0.
    a0_t2 = composition["A0_no_agent"]["final_weights"]["t2_comparator"]
    a1_t2 = composition["A1_alpha_only"]["final_weights"]["t2_comparator"]
    a2_t2 = composition["A2_alpha_risk"]["final_weights"]["t2_comparator"]
    assert a0_t2 == 0.0
    assert a1_t2 > a0_t2
    assert a2_t2 >= a1_t2
    assert composition["A1_alpha_only"]["final_weights"]["production_six_factor"] < 1.0
    # The decision-level eligible/excluded record is complete and consistent:
    # every loader ticker is exactly one of eligible or excluded.
    eligible = composition["eligible_universe"]
    excluded = composition["excluded_stocks"]
    all_loader = sorted(closes.columns)
    assert eligible == sorted(eligible)
    assert excluded == sorted(excluded)
    assert set(eligible) | set(excluded) == set(all_loader)
    assert set(eligible) & set(excluded) == set()
    assert len(eligible) + len(excluded) == len(all_loader)


def test_decision_composition_rejects_tampered_payload() -> None:
    payload = _synthetic_payload()
    payload["deterministic"]["windows"][0]["candidates"]["t2_comparator"][
        "total_return"
    ] = 0.99
    with pytest.raises(RuntimeError, match="integrity"):
        decision_composition(
            payload,
            _DECISION_SET[0],
            _counting_and_proposal_model([]),
            closes_loader=_synthetic_closes(),
        )


def test_future_window_and_whole_replay_mutation_leave_early_composition_unchanged() -> None:
    payload = _synthetic_payload()
    closes = _synthetic_closes()
    early = _DECISION_SET[2]

    def model(role: str, _summary: object) -> str:
        return "[]"

    before = decision_composition(payload, early, model, closes_loader=closes)

    mutated = _copy(payload)
    later = _DECISION_SET[-1]
    for window in mutated["deterministic"]["windows"]:
        if window["decision_date"] == later:
            window["candidates"]["t2_comparator"]["total_return"] = 9.99
    mutated["deterministic"]["candidates"]["t2_comparator"]["verdict"] = "DOES_NOT_QUALIFY"
    mutated["deterministic"]["candidates"]["production_six_factor"]["status"] = "FAILED"
    new_decision = "2026-01-08"
    mutated["deterministic"]["windows"].append(
        _synthetic_window(new_decision, exit_date="2026-02-05")
    )
    mutated["deterministic"]["decision_set"].append(new_decision)
    _rehash(mutated)

    after = decision_composition(mutated, early, model, closes_loader=closes)
    assert after == before


# ---------------------------------------------------------------------------
# Selector aggregate and Block Bootstrap.
# ---------------------------------------------------------------------------


def _synthetic_windows(n: int = 12) -> list[dict[str, object]]:
    windows = []
    for index in range(n):
        windows.append(
            {
                "decision_date": _DECISION_SET[index],
                "variants": {
                    "A2_alpha_risk": {
                        "total_return": 0.02 + index * 0.001,
                        "max_drawdown": 0.05,
                    },
                    "A0_no_agent": {"total_return": 0.01, "max_drawdown": 0.05},
                },
            }
        )
    return windows


def test_selector_summary_bootstrap_is_deterministic() -> None:
    first = selector_summary(_synthetic_windows())
    second = selector_summary(_synthetic_windows())
    assert first == second
    assert first["n_windows"] == 12
    assert first["selected_variant"] == SELECTED_VARIANT
    assert first["comparison_baseline"] == COMPARISON_BASELINE
    assert first["bootstrap_binding"] == {
        "method": "circular_moving_block",
        "seed": BOOTSTRAP_SEED,
        "iterations": BOOTSTRAP_ITERATIONS,
        "block_windows": BOOTSTRAP_BLOCK_WINDOWS,
        "plan": "NestedEvaluationPlan",
    }
    bootstrap = first["bootstrap"]
    assert bootstrap["method"] == "circular_moving_block"
    assert bootstrap["seed"] == BOOTSTRAP_SEED
    assert bootstrap["iterations"] == BOOTSTRAP_ITERATIONS
    assert bootstrap["block_windows"] == min(BOOTSTRAP_BLOCK_WINDOWS, 12)
    assert len(bootstrap["median_return_delta_ci95"]) == 2
    assert len(bootstrap["utility_win_rate_ci95"]) == 2


def test_selector_summary_empty_fails_closed() -> None:
    with pytest.raises(ValueError, match="at least one"):
        selector_summary([])


def test_selector_summary_non_finite_outcome_fails_closed() -> None:
    windows = _synthetic_windows(2)
    windows[0]["variants"]["A2_alpha_risk"]["total_return"] = float("nan")
    with pytest.raises(ValueError, match="finite"):
        selector_summary(windows)


def test_selector_identity_hash_deterministic_and_sensitive() -> None:
    payload = _synthetic_payload()
    first = selector_identity_hash(payload)
    second = selector_identity_hash(_copy(payload))
    assert first == second
    drifted = _copy(payload)
    drifted["deterministic"]["inventory_hash"] = "1" * 64
    assert selector_identity_hash(drifted) != first


# ---------------------------------------------------------------------------
# Resource record: build fail-closed and verify fail-closed.
# ---------------------------------------------------------------------------


class _FakeProcess:
    def __init__(self, rss: int, children=()):
        self._rss = rss
        self._children = list(children)

    def children(self, recursive: bool):
        assert recursive is True
        return self._children

    def memory_info(self):
        from types import SimpleNamespace

        return SimpleNamespace(rss=self._rss)


def _live_sampler():
    from jiuwenswarm.quant.reporting.resource_meter import ProcessTreeRssSampler

    mib = 1024 * 1024
    sampler = ProcessTreeRssSampler(
        _FakeProcess(100 * mib, [_FakeProcess(20 * mib)]), interval_seconds=0.01
    )
    sampler.start()
    sampler.sample_once()
    sampler.stop()
    return sampler


def test_build_resource_record_requires_started_stopped_sampler() -> None:
    from jiuwenswarm.quant.reporting.resource_meter import ProcessTreeRssSampler

    not_started = ProcessTreeRssSampler(_FakeProcess(1), interval_seconds=0.01)
    with pytest.raises(ValueError, match="never started"):
        build_resource_record(
            sampler=not_started,
            elapsed_seconds=1.0,
            per_window=[{"decision_date": "2025-01-14", "wall_time_seconds": 0.1}],
        )

    running = ProcessTreeRssSampler(_FakeProcess(1), interval_seconds=0.01)
    running.start()
    try:
        with pytest.raises(ValueError, match="stop"):
            build_resource_record(
                sampler=running,
                elapsed_seconds=1.0,
                per_window=[{"decision_date": "2025-01-14", "wall_time_seconds": 0.1}],
            )
    finally:
        running.stop()


def test_build_resource_record_valid() -> None:
    sampler = _live_sampler()
    record = build_resource_record(
        sampler=sampler,
        elapsed_seconds=3.5,
        per_window=[
            {"decision_date": "2025-01-14", "wall_time_seconds": 0.2},
            {"decision_date": "2025-02-19", "wall_time_seconds": 0.3},
        ],
    )
    assert verify_resource_record(record)
    assert record["schema"] == RESEARCH_SCHEMA
    assert record["evidence_level"] == "RESEARCH_ONLY"
    assert record["sampler"]["name"] == "ProcessTreeRssSampler"
    assert record["lifecycle"] == {"started": True, "stopped": True}
    totals = record["totals"]
    assert totals["process_tree_sample_count"] >= 1
    assert totals["process_peak_rss_mb"] > 0
    assert totals["current_rss_mb"] > 0


def test_build_resource_record_rejects_bad_wall_or_per_window() -> None:
    sampler = _live_sampler()
    with pytest.raises(ValueError, match="finite"):
        build_resource_record(
            sampler=sampler,
            elapsed_seconds=float("nan"),
            per_window=[{"decision_date": "d", "wall_time_seconds": 0.1}],
        )
    with pytest.raises(ValueError, match="non-negative"):
        build_resource_record(
            sampler=sampler,
            elapsed_seconds=-1.0,
            per_window=[{"decision_date": "d", "wall_time_seconds": 0.1}],
        )
    with pytest.raises(ValueError, match="wall_time_seconds"):
        build_resource_record(
            sampler=sampler,
            elapsed_seconds=1.0,
            per_window=[{"decision_date": "d", "wall_time_seconds": float("nan")}],
        )
    with pytest.raises(ValueError, match="at least one"):
        build_resource_record(
            sampler=sampler, elapsed_seconds=1.0, per_window=[]
        )


def test_verify_resource_record_fail_closed_cases() -> None:
    sampler = _live_sampler()
    record = build_resource_record(
        sampler=sampler,
        elapsed_seconds=1.0,
        per_window=[{"decision_date": "2025-01-14", "wall_time_seconds": 0.1}],
    )

    def mutate(mutator):
        new = dict(record)
        new["totals"] = dict(record["totals"])
        mutator(new)
        return new

    assert not verify_resource_record(None)
    assert not verify_resource_record({})
    assert not verify_resource_record(mutate(lambda r: r.__setitem__("lifecycle", {"started": True, "stopped": False})))
    assert not verify_resource_record(mutate(lambda r: r["totals"].__setitem__("process_peak_rss_mb", None)))
    assert not verify_resource_record(mutate(lambda r: r["totals"].__setitem__("current_rss_mb", float("nan"))))
    assert not verify_resource_record(mutate(lambda r: r["totals"].__setitem__("process_tree_sample_count", 0)))
    assert not verify_resource_record(mutate(lambda r: r["totals"].__setitem__("wall_time_seconds", -0.1)))
    assert not verify_resource_record(mutate(lambda r: r["totals"].__setitem__("process_peak_rss_mb", 99999.0)))
    assert not verify_resource_record(mutate(lambda r: r["totals"].__setitem__("wall_time_seconds", 99999.0)))
    assert not verify_resource_record(mutate(lambda r: r.__setitem__("per_window", [])))
    # unchanged record still verifies.
    assert verify_resource_record(record)


def test_sampler_reuse_is_stdlib_only() -> None:
    # Importing the shared sampler utility must not pull any formal/research module.
    code = (
        "import sys;"
        "import jiuwenswarm.quant.reporting.resource_meter as m;"
        "forbidden=('run_multi_agent','aggregate_formal_resources','strategy_fusion_replay','strategy_pool_replay');"
        "assert not any(f in sys.modules for f in forbidden), [f for f in forbidden if f in sys.modules]"
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = str(_REPO_ROOT / "jiuwenswarm") + os.pathsep + env.get("PYTHONPATH", "")
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(_REPO_ROOT / "jiuwenswarm"),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr


# ---------------------------------------------------------------------------
# Artifact integrity / tamper.
# ---------------------------------------------------------------------------


def _minimal_selector_payload() -> dict[str, object]:
    window = {
        "decision_date": "2025-01-14",
        "entry_date": "2025-01-16",
        "exit_date": "2025-02-20",
        "valuation_dates": ["2025-01-16"],
        "eligible_universe": ["sh.600036", "sh.601318"],
        "excluded_stocks": ["sz.000001"],
        "variants": {
            "A0_no_agent": {"total_return": 0.01, "max_drawdown": 0.05},
            "A1_alpha_only": {"total_return": 0.012, "max_drawdown": 0.05},
            "A2_alpha_risk": {"total_return": 0.013, "max_drawdown": 0.05},
        },
        "selected": SELECTED_VARIANT,
    }
    window["window_hash"] = window_hash(window)
    resource = build_resource_record(
        sampler=_live_sampler(),
        elapsed_seconds=1.0,
        per_window=[{"decision_date": "2025-01-14", "wall_time_seconds": 0.1}],
    )
    deterministic = {
        "research_schema": RESEARCH_SCHEMA,
        "selector_version": SELECTOR_VERSION,
        "decision_set": ["2025-01-14"],
        "n_windows": 1,
        "resource": resource,
        "windows": [window],
    }
    return {
        "task_id": "WP1-E4-R1",
        "deterministic": deterministic,
        "artifact_sha256": artifact_hash(deterministic),
    }


def test_verify_selector_payload_accepts_valid_and_detects_tamper() -> None:
    payload = _minimal_selector_payload()
    assert verify_selector_payload(payload)
    tampered = json.loads(canonical_json(payload))
    tampered["deterministic"]["windows"][0]["variants"]["A2_alpha_risk"][
        "total_return"
    ] = 0.5
    assert not verify_selector_payload(tampered)
    # resource tamper also fails the whole artifact.
    tampered2 = json.loads(canonical_json(payload))
    tampered2["deterministic"]["resource"]["totals"]["process_peak_rss_mb"] = None
    assert not verify_selector_payload(tampered2)


def test_excluded_eligible_identity_tamper_fails_verification() -> None:
    payload = _minimal_selector_payload()
    assert verify_selector_payload(payload)
    # Tampering the recorded eligible identities fails payload verification.
    tampered_eligible = json.loads(canonical_json(payload))
    tampered_eligible["deterministic"]["windows"][0]["eligible_universe"].append(
        "sh.999999"
    )
    assert not verify_selector_payload(tampered_eligible)
    # Tampering the recorded excluded identities fails payload verification.
    tampered_excluded = json.loads(canonical_json(payload))
    tampered_excluded["deterministic"]["windows"][0]["excluded_stocks"] = [
        "sz.000001",
        "sh.601398",
    ]
    assert not verify_selector_payload(tampered_excluded)


def test_artifact_hash_deterministic() -> None:
    first = _minimal_selector_payload()
    second = _minimal_selector_payload()
    assert first["artifact_sha256"] == second["artifact_sha256"]


# ---------------------------------------------------------------------------
# Production / direct / formal isolation.
# ---------------------------------------------------------------------------


def test_production_import_isolation() -> None:
    for relative in (
        "jiuwenswarm/evaluation/run_multi_agent.py",
        "jiuwenswarm/scripts/run_quant_pipeline.py",
        "jiuwenswarm/jiuwenswarm/extensions/quant-finance/extension.py",
        "jiuwenswarm/evaluation/aggregate_formal_resources.py",
    ):
        source = (_REPO_ROOT / relative).read_text(encoding="utf-8", errors="replace")
        assert "dynamic_selector_replay" not in source, relative


def test_module_never_imports_formal_entry_or_network() -> None:
    source = (
        _REPO_ROOT / "jiuwenswarm/evaluation/dynamic_selector_replay.py"
    ).read_text(encoding="utf-8", errors="replace")
    # The E4 module never imports the formal aggregator or the formal entry.
    assert "aggregate_formal_resources" not in source
    assert "run_multi_agent" not in source
    assert "extension.py" not in source
    for forbidden in ("api_key", "requests.", "openai", "httpx", "http://"):
        assert forbidden not in source


def test_extension_overlay_stays_disabled() -> None:
    extension_path = (
        _REPO_ROOT / "jiuwenswarm/jiuwenswarm/extensions/quant-finance/extension.py"
    )
    source = extension_path.read_text(encoding="utf-8", errors="replace")
    assert "AGENT_OVERLAY_ENABLED = False" in source


def test_fresh_import_is_lazy_and_isolated() -> None:
    code = (
        "import evaluation.dynamic_selector_replay;"
        "import sys;"
        "forbidden=('run_multi_agent','aggregate_formal_resources','strategy_fusion_replay','strategy_pool_replay');"
        "assert not any(f in sys.modules for f in forbidden), [f for f in forbidden if f in sys.modules]"
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = str(_REPO_ROOT / "jiuwenswarm") + os.pathsep + env.get("PYTHONPATH", "")
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(_REPO_ROOT / "jiuwenswarm"),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr


def test_run_selector_replay_rejects_injected_drift() -> None:
    # With an injected payload whose decision set drifts, the replay fails closed
    # before any composition (no real loader/oracle needed because the drift
    # check is the first gate after payload verification).
    payload = _synthetic_payload()
    payload["deterministic"]["decision_set"] = ["2026-01-08"]
    _rehash(payload)

    def noop(_role: str, _summary: object) -> str:
        return "[]"

    with pytest.raises(RuntimeError, match="drift"):
        run_selector_replay(noop, payload=payload)


def test_e2c_oracle_is_literal_regenerate_true_only() -> None:
    # Frozen unique-oracle contract: E4 must call load_e2c_evidence(regenerate=True)
    # literally.  The artifact-read branch (regenerate=False / --no-regenerate) was
    # a review finding; this AST static regression proves every executable
    # load_e2c_evidence call passes the literal True and the CLI defines no
    # negative (artifact-read) switch.
    path = _REPO_ROOT / "jiuwenswarm/evaluation/dynamic_selector_replay.py"
    source = path.read_text(encoding="utf-8", errors="replace")
    tree = ast.parse(source)

    def call_name(node: ast.AST) -> str | None:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return node.attr
        return None

    oracle_calls: list[dict[str, ast.AST]] = []
    cli_flags: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = call_name(node.func)
        if name == "load_e2c_evidence":
            oracle_calls.append({kw.arg: kw.value for kw in node.keywords})
        elif name == "add_argument":
            if node.args and isinstance(node.args[0], ast.Constant) \
                    and isinstance(node.args[0].value, str):
                cli_flags.append(node.args[0].value)
    assert oracle_calls, "no load_e2c_evidence call found in the module"
    for kwargs in oracle_calls:
        regenerate = kwargs.get("regenerate")
        assert regenerate is not None, "load_e2c_evidence must pass regenerate"
        assert isinstance(regenerate, ast.Constant) and regenerate.value is True, (
            "load_e2c_evidence must be called with the literal regenerate=True"
        )
    assert not any(flag.startswith("--no-") for flag in cli_flags), cli_flags
    assert "regenerate=regenerate" not in source  # no variable pass-through
