"""Tests for the frozen strategy pool registry."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, is_dataclass
from pathlib import Path

import pytest

from jiuwenswarm.quant.factor_registry import FACTOR_REGISTRY
from jiuwenswarm.quant.strategy_configs import PRODUCTION_STRATEGY
from jiuwenswarm.quant.strategy_pool import (
    STRATEGY_POOL,
    STRATEGY_POOL_BY_NAME,
    PoolSlot,
    get_pool_slot,
    production_pool_slot,
)

_REPO_ROOT = Path(__file__).resolve().parents[4]


def test_exact_order_and_count() -> None:
    assert len(STRATEGY_POOL) == 6
    assert [slot.name for slot in STRATEGY_POOL] == [
        "production_six_factor",
        "t2_comparator",
        "trend_short_5_10_20",
        "trend_medium_20_60",
        "trend_long_120_250",
        "similar_market_blend",
    ]


def test_unique_production_and_fallback() -> None:
    production = [slot for slot in STRATEGY_POOL if slot.production_qualified]
    fallback = [slot for slot in STRATEGY_POOL if slot.hard_fallback]
    assert len(production) == 1
    assert len(fallback) == 1
    assert production == fallback
    assert production[0].base_strategy == PRODUCTION_STRATEGY
    assert fallback[0].base_strategy == PRODUCTION_STRATEGY


def test_nonproduction_slots_are_research_only() -> None:
    for slot in STRATEGY_POOL:
        if not slot.production_qualified:
            assert slot.research_only is True
            assert slot.hard_fallback is False


def test_factor_union_equals_registry() -> None:
    pool_ids = {factor for slot in STRATEGY_POOL for factor in slot.factor_ids}
    assert pool_ids == {item.factor_id for item in FACTOR_REGISTRY}


def test_all_horizons_are_twenty() -> None:
    assert {slot.target_horizon for slot in STRATEGY_POOL} == {20}


def test_t2_comparator_binding() -> None:
    slot = get_pool_slot("t2_comparator")
    assert slot.base_strategy == "phase_b_t2_score_alloc"
    assert slot.factor_ids == ()
    assert slot.research_only is True
    assert slot.production_qualified is False
    assert slot.hard_fallback is False


def test_pool_slot_is_frozen_and_mapping_is_read_only() -> None:
    assert is_dataclass(PoolSlot)
    with pytest.raises(FrozenInstanceError):
        STRATEGY_POOL[0].name = "mutated"
    with pytest.raises(TypeError):
        STRATEGY_POOL_BY_NAME["mutated"] = STRATEGY_POOL[0]
    assert set(STRATEGY_POOL_BY_NAME) == {slot.name for slot in STRATEGY_POOL}


def test_production_strategy_pointer_unchanged() -> None:
    assert production_pool_slot().base_strategy is PRODUCTION_STRATEGY


def test_unknown_lookup_raises_value_error() -> None:
    with pytest.raises(ValueError):
        get_pool_slot("does_not_exist")


def test_production_pool_slot() -> None:
    assert production_pool_slot() is get_pool_slot("production_six_factor")


@pytest.mark.parametrize(
    "relative_path",
    [
        "jiuwenswarm/scripts/run_quant_pipeline.py",
        "jiuwenswarm/jiuwenswarm/extensions/quant-finance/extension.py",
        "jiuwenswarm/jiuwenswarm/quant/__init__.py",
    ],
)
def test_forbidden_files_do_not_mention_strategy_pool(relative_path: str) -> None:
    source = (_REPO_ROOT / relative_path).read_text(encoding="utf-8")
    assert "strategy_pool" not in source
