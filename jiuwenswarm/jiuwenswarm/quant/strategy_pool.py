"""Frozen, auditable research strategy pool registry.

Pure data only; this module must never activate or execute a strategy.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from jiuwenswarm.quant.factor_registry import FACTOR_REGISTRY
from jiuwenswarm.quant.strategy_configs import PRODUCTION_STRATEGY


@dataclass(frozen=True)
class PoolSlot:
    """Immutable descriptor for one research pool slot."""

    name: str
    base_strategy: str
    factor_ids: tuple[str, ...]
    target_horizon: int = 20
    research_only: bool = True
    production_qualified: bool = False
    hard_fallback: bool = False


def _research(name: str, factor_ids: tuple[str, ...]) -> PoolSlot:
    return PoolSlot(name, name, factor_ids)


_SHORT_TREND = (
    "momentum_5",
    "momentum_10",
    "momentum_20",
    "trend_consistency_5_10_20",
    "price_vs_ma20",
    "momentum_acceleration",
)

_MEDIUM_TREND = (
    "momentum_20",
    "momentum_60",
    "risk_adjusted_momentum_20",
    "risk_adjusted_momentum_60",
    "price_vs_ma20",
    "price_vs_ma60",
    "momentum_acceleration",
)

_LONG_TREND = (
    "momentum_120",
    "momentum_250",
    "risk_adjusted_momentum_60",
    "price_vs_ma60",
)

_EXPECTED_NAMES = (
    "production_six_factor",
    "t2_comparator",
    "trend_short_5_10_20",
    "trend_medium_20_60",
    "trend_long_120_250",
    "similar_market_blend",
)

STRATEGY_POOL: tuple[PoolSlot, ...] = (
    PoolSlot(
        "production_six_factor",
        PRODUCTION_STRATEGY,
        (),
        research_only=False,
        production_qualified=True,
        hard_fallback=True,
    ),
    PoolSlot("t2_comparator", "phase_b_t2_score_alloc", ()),
    _research("trend_short_5_10_20", _SHORT_TREND),
    _research("trend_medium_20_60", _MEDIUM_TREND),
    _research("trend_long_120_250", _LONG_TREND),
    PoolSlot(
        "similar_market_blend",
        "similar_market_blend",
        tuple(item.factor_id for item in FACTOR_REGISTRY),
    ),
)


def _validate_pool() -> None:
    names = tuple(slot.name for slot in STRATEGY_POOL)
    if names != _EXPECTED_NAMES:
        raise RuntimeError("STRATEGY_POOL names must match the exact required order")
    if len(set(names)) != len(names):
        raise RuntimeError("STRATEGY_POOL names must be unique")
    production = [slot for slot in STRATEGY_POOL if slot.production_qualified]
    fallback = [slot for slot in STRATEGY_POOL if slot.hard_fallback]
    if len(production) != 1 or len(fallback) != 1:
        raise RuntimeError("exactly one production and one fallback slot are required")
    if production[0] is not fallback[0]:
        raise RuntimeError("production and fallback must be the same slot")
    if production[0].base_strategy != PRODUCTION_STRATEGY:
        raise RuntimeError("production/fallback slot must use PRODUCTION_STRATEGY")
    registry_ids = {item.factor_id for item in FACTOR_REGISTRY}
    pool_ids = {factor for slot in STRATEGY_POOL for factor in slot.factor_ids}
    if registry_ids != pool_ids:
        raise RuntimeError("STRATEGY_POOL factor union must equal FACTOR_REGISTRY")
    for slot in STRATEGY_POOL:
        if slot.target_horizon != 20:
            raise RuntimeError("all pool slots must target horizon 20")
        if not set(slot.factor_ids) <= registry_ids:
            raise RuntimeError("pool slot references unknown factor IDs")
        if not slot.production_qualified and not slot.research_only:
            raise RuntimeError("non-production pool slots must be research-only")


_validate_pool()

STRATEGY_POOL_BY_NAME: Mapping[str, PoolSlot] = MappingProxyType(
    {slot.name: slot for slot in STRATEGY_POOL}
)


def get_pool_slot(name: str) -> PoolSlot:
    try:
        return STRATEGY_POOL_BY_NAME[name]
    except KeyError as exc:
        raise ValueError(f"unknown strategy pool slot: {name}") from exc


def production_pool_slot() -> PoolSlot:
    return get_pool_slot("production_six_factor")
