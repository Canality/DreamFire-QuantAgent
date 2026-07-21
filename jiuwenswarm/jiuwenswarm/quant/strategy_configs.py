"""Named, auditable strategy configurations used by production and research.

Keeping the factor weights here prevents evaluation-only scripts from silently
using a different model than the direct and JiuwenSwarm production paths.
"""

from __future__ import annotations

from dataclasses import dataclass

from jiuwenswarm.quant.factors import FactorConfig, PositionConfig


@dataclass(frozen=True)
class StrategySpec:
    """Immutable description of one comparable strategy baseline."""

    name: str
    description: str
    factor_weights: tuple[float, float, float, float, float, float]
    top_n: int = 15
    max_single_stock: float = 0.10
    max_single_sector: float = 0.25
    max_total_weight: float = 0.95
    score_tilt: float = 0.0  # 0=inverse-vol only; >0 = tilt towards higher scores

    def factor_config(self) -> FactorConfig:
        mom20, mom60, max_dd, reversal5, volume_corr, volume_trend = self.factor_weights
        return FactorConfig(
            w_momentum_20=mom20,
            w_momentum_60=mom60,
            w_max_drawdown=max_dd,
            w_reversal_5=reversal5,
            w_volume_corr=volume_corr,
            w_volume_trend=volume_trend,
        )

    def position_config(self) -> PositionConfig:
        return PositionConfig(
            max_single_stock=self.max_single_stock,
            max_single_sector=self.max_single_sector,
            min_cash=round(1.0 - self.max_total_weight, 10),
            top_n_stocks=self.top_n,
            score_tilt=self.score_tilt,
        )


PRODUCTION_STRATEGY = "production_six_factor"

STRATEGY_SPECS: dict[str, StrategySpec] = {
    PRODUCTION_STRATEGY: StrategySpec(
        name=PRODUCTION_STRATEGY,
        description="Current v2.6 six-factor production model",
        factor_weights=(0.34, 0.17, 0.16, 0.08, 0.19, 0.06),
    ),
    "two_factor_ic_ratio": StrategySpec(
        name="two_factor_ic_ratio",
        description="momentum_20 0.71 + volume_trend 0.29 candidate",
        factor_weights=(0.71, 0.0, 0.0, 0.0, 0.0, 0.29),
    ),
    "momentum20_only": StrategySpec(
        name="momentum20_only",
        description="Single-factor momentum_20 diagnostic baseline",
        factor_weights=(1.0, 0.0, 0.0, 0.0, 0.0, 0.0),
    ),
    # --- Phase B: 2×2 mechanism experiment ---
    "phase_b_t0_control": StrategySpec(
        name="phase_b_t0_control",
        description="T0 control: mom20 0.71/vol_trend 0.29, pure inverse-vol",
        factor_weights=(0.71, 0.0, 0.0, 0.0, 0.0, 0.29),
        score_tilt=0.0,
    ),
    "phase_b_t1_shrink": StrategySpec(
        name="phase_b_t1_shrink",
        description="T1 shrinkage: mom20 0.85/vol_trend 0.15, pure inverse-vol",
        factor_weights=(0.85, 0.0, 0.0, 0.0, 0.0, 0.15),
        score_tilt=0.0,
    ),
    "phase_b_t2_score_alloc": StrategySpec(
        name="phase_b_t2_score_alloc",
        description="T2 score-allocation: 0.71/0.29, inv-vol × exp(0.20×clip(z,-2,2))",
        factor_weights=(0.71, 0.0, 0.0, 0.0, 0.0, 0.29),
        score_tilt=0.20,
    ),
    "phase_b_t3_joint": StrategySpec(
        name="phase_b_t3_joint",
        description="T3 joint: 0.85/0.15, inv-vol × exp(0.20×clip(z,-2,2))",
        factor_weights=(0.85, 0.0, 0.0, 0.0, 0.0, 0.15),
        score_tilt=0.20,
    ),
}


def get_strategy_spec(name: str = PRODUCTION_STRATEGY) -> StrategySpec:
    """Return a named strategy or fail loudly instead of falling back."""

    try:
        return STRATEGY_SPECS[name]
    except KeyError as exc:
        raise ValueError(
            f"Unknown strategy {name!r}; expected one of {sorted(STRATEGY_SPECS)}"
        ) from exc


def production_factor_config() -> FactorConfig:
    """Build the factor config used by both production execution paths."""

    return get_strategy_spec(PRODUCTION_STRATEGY).factor_config()


def production_position_config() -> PositionConfig:
    """Build the position config used by both production execution paths."""

    return get_strategy_spec(PRODUCTION_STRATEGY).position_config()
