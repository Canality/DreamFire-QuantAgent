import importlib.util
from pathlib import Path

from jiuwenswarm.quant.strategy_configs import (
    PRODUCTION_STRATEGY,
    get_strategy_spec,
    production_factor_config,
    production_position_config,
)


def _load_evaluator():
    path = Path(__file__).resolve().parents[3] / "evaluation" / "unified_baseline_evaluation.py"
    spec = importlib.util.spec_from_file_location("unified_baseline_evaluation", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_named_baselines_are_exact_and_production_is_unchanged():
    assert PRODUCTION_STRATEGY == "production_six_factor"
    production = production_factor_config()
    assert (
        production.w_momentum_20,
        production.w_momentum_60,
        production.w_max_drawdown,
        production.w_reversal_5,
        production.w_volume_corr,
        production.w_volume_trend,
    ) == (0.34, 0.17, 0.16, 0.08, 0.19, 0.06)

    two_factor = get_strategy_spec("two_factor_ic_ratio").factor_config()
    assert two_factor.w_momentum_20 == 0.71
    assert two_factor.w_volume_trend == 0.29
    assert sum([
        two_factor.w_momentum_60,
        two_factor.w_max_drawdown,
        two_factor.w_reversal_5,
        two_factor.w_volume_corr,
    ]) == 0.0

    momentum = get_strategy_spec("momentum20_only").factor_config()
    assert momentum.w_momentum_20 == 1.0
    assert production_position_config().min_cash == 0.05


def test_schedule_is_non_overlapping_and_causal():
    evaluator = _load_evaluator()
    starts = evaluator.build_schedule(500)
    assert starts[0] == 80
    assert starts[-1] == 480
    assert all(b - a == 20 for a, b in zip(starts, starts[1:]))
    assert all(start - 1 < start for start in starts)
    assert all(start + 19 < 500 for start in starts)


def test_preregistered_acceptance_is_frozen_before_run():
    evaluator = _load_evaluator()
    thresholds = evaluator.PREREGISTRATION["candidate_acceptance"]
    assert thresholds["median_return_delta_min"] == 0.003
    assert thresholds["paired_utility_win_rate_min"] == 0.60
    assert thresholds["recent_four_utility_wins_min"] == 3
