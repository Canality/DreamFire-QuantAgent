from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).parents[3] / "evaluation" / "local_scoring.py"
SPEC = importlib.util.spec_from_file_location("local_scoring", MODULE_PATH)
local_scoring = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = local_scoring
SPEC.loader.exec_module(local_scoring)


def _row(total_return: float, max_drawdown: float) -> dict:
    return {
        "decision_date": "2026-01-01",
        "official": {
            "total_return": total_return,
            "max_drawdown": max_drawdown,
        },
    }


def test_empirical_percentile_is_tie_aware_and_directional() -> None:
    reference = [1.0, 2.0, 2.0, 4.0]
    assert local_scoring.empirical_percentile(
        2.0, reference, higher_is_better=True
    ) == pytest.approx(0.5)
    assert local_scoring.empirical_percentile(
        2.0, reference, higher_is_better=False
    ) == pytest.approx(0.5)
    assert local_scoring.empirical_percentile(
        5.0, reference, higher_is_better=True
    ) == pytest.approx(1.0)


def test_portfolio_score_uses_56_24_weighting() -> None:
    reference = [_row(-0.02, 0.08), _row(0.00, 0.04), _row(0.02, 0.02)]
    candidate = [_row(0.03, 0.01)]
    report = local_scoring.score_portfolio(candidate, reference)
    assert report["expected_return_score"] == pytest.approx(56.0)
    assert report["expected_drawdown_score"] == pytest.approx(24.0)
    assert report["expected_score"] == pytest.approx(80.0)


def test_resource_penalties_apply_only_for_full_ten_percent_steps() -> None:
    assert local_scoring.score_tokens(109.9, 100).score == pytest.approx(10.0)
    assert local_scoring.score_tokens(110.0, 100).score == pytest.approx(8.0)
    assert local_scoring.score_runtime(120.0, 100).score == pytest.approx(3.0)


def test_missing_resource_baseline_is_pending_not_full_marks() -> None:
    token = local_scoring.score_tokens(5000, None)
    runtime = local_scoring.score_runtime(None, 100)
    compute = local_scoring.score_compute(None)
    assert token.score is None
    assert runtime.score is None
    assert compute.score is None
    assert token.status == "pending_baseline_or_measurement"


def test_compute_tiers_follow_declared_five_point_dimension() -> None:
    assert local_scoring.score_compute("excellent").score == pytest.approx(5.0)
    assert local_scoring.score_compute("good").score == pytest.approx(3.0)
    assert local_scoring.score_compute("medium").score == pytest.approx(1.0)
    assert local_scoring.score_compute("poor").score == pytest.approx(0.0)
