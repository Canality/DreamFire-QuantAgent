"""Immutable research-only registry for preregistered WP1-E0 factors.

This module contains metadata only.  It is intentionally not imported by the
production factor calculator, strategy registry, direct pipeline, or formal
Extension.  Formula implementations live in :mod:`candidate_factors`, which
verifies their exact source hashes against these definitions before computing.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Sequence


class FactorStatus(str, Enum):
    """Research availability of a registered definition."""

    ENABLED = "ENABLED"
    CONDITIONAL = "CONDITIONAL"
    DISABLED = "DISABLED"


@dataclass(frozen=True)
class FactorDefinition:
    """Versioned and audit-ready factor metadata."""

    factor_id: str
    version: str
    family: str
    formula: str
    economic_hypothesis: str
    expected_direction: str
    required_fields: tuple[str, ...]
    minimum_lookback: int
    supported_horizons: tuple[int, ...]
    normalization: str
    sector_neutralization: str
    missing_value_policy: str
    availability_time_policy: str
    corporate_action_requirement: str
    enabled_status: FactorStatus
    disabled_reason: str | None
    implementation_hash: str

    def to_dict(self) -> dict[str, Any]:
        """Return the canonical JSON-safe representation."""

        return {
            "factor_id": self.factor_id,
            "version": self.version,
            "family": self.family,
            "formula": self.formula,
            "economic_hypothesis": self.economic_hypothesis,
            "expected_direction": self.expected_direction,
            "required_fields": list(self.required_fields),
            "minimum_lookback": self.minimum_lookback,
            "supported_horizons": list(self.supported_horizons),
            "normalization": self.normalization,
            "sector_neutralization": self.sector_neutralization,
            "missing_value_policy": self.missing_value_policy,
            "availability_time_policy": self.availability_time_policy,
            "corporate_action_requirement": self.corporate_action_requirement,
            "enabled_status": self.enabled_status.value,
            "disabled_reason": self.disabled_reason,
            "implementation_hash": self.implementation_hash,
        }


_COMMON = {
    "version": "1.0.0",
    "family": "trend_momentum",
    "expected_direction": "POSITIVE",
    "required_fields": ("close",),
    "supported_horizons": (20,),
    "normalization": "RAW_ONLY_WP1_E0",
    "sector_neutralization": "NONE_WP1_E0",
    "missing_value_policy": "UNAVAILABLE_NO_IMPUTATION",
    "availability_time_policy": (
        "DECISION_CLOSE_AVAILABLE_AT_OR_AFTER_15_00_ASIA_SHANGHAI"
    ),
    "corporate_action_requirement": (
        "POINT_IN_TIME_ADJUSTED_OR_VERIFIED_NO_ACTION_WINDOW_WITH_EVIDENCE_HASH"
    ),
    "disabled_reason": None,
}


def _definition(
    factor_id: str,
    formula: str,
    hypothesis: str,
    minimum_lookback: int,
    implementation_hash: str,
    *,
    status: FactorStatus = FactorStatus.ENABLED,
) -> FactorDefinition:
    return FactorDefinition(
        factor_id=factor_id,
        formula=formula,
        economic_hypothesis=hypothesis,
        minimum_lookback=minimum_lookback,
        implementation_hash=implementation_hash,
        enabled_status=status,
        **_COMMON,
    )


# These hashes bind canonical metadata and the exact kernel source in
# candidate_factors.py.  verify_implementation_hashes() recomputes them before
# every snapshot; placeholders are replaced only when the kernel source changes.
_IMPLEMENTATION_HASHES = {
    "momentum_5": "c040ee9fd0b53550d03668db62a420a6fd81da90ace8ed8bad7335aa581c4b90",
    "momentum_10": "bfe05d18686db5e3eeb5621fb692beec96432b6d3dc057d05eaa5ab6fbf867ce",
    "momentum_20": "c91f586f123817bc00d1e06cbbe0aa704545872197fe4ca4bfbc3719360dd5ee",
    "momentum_60": "989e2ace4e0231b98c1deff842521bf3bcf1bf6e5da746b2bd016be310878b80",
    "momentum_120": "d8cb914c92ebf12c7ef18eb04a20c03c4534f691544162b42a1ea5e0e69f0876",
    "momentum_250": "ee99e5f14031d45d803c7fbae3fcfe29e15997850de8941de3250c246d5142e3",
    "risk_adjusted_momentum_20": "530333688473b5c8a1b22eaa37d84ae1148b6f38c2bd186bd9cdf60d062114a8",
    "risk_adjusted_momentum_60": "8c061a0df927c010d0766cc3c523f2820c6623bd5df91aa48ca5b42c7997b0d8",
    "trend_consistency_5_10_20": "532fd547407203b4ebb51d4ec054adcb1d71752b46d8f573f854c6c229010406",
    "price_vs_ma20": "824c660c4881f8ceaf195bf81f66c147101ee66afcc79e61fe9de3780c39bb6c",
    "price_vs_ma60": "acc964a1d616f14b2feb7401711fc4132aff89fca8ec17584ba77ba6bb47693e",
    "momentum_acceleration": "ff21619bb1b8368bf62afb76c630301a482f41bdfeb2736cd7e4f1ca09f89050",
}


FACTOR_REGISTRY: tuple[FactorDefinition, ...] = (
    *(
        _definition(
            f"momentum_{lookback}",
            f"close_t / close_(t-{lookback}) - 1",
            (
                f"Positive {lookback}-session price persistence may continue "
                "over the fixed official 20-session target."
            ),
            lookback + 1,
            _IMPLEMENTATION_HASHES[f"momentum_{lookback}"],
            status=(
                FactorStatus.CONDITIONAL
                if lookback == 250
                else FactorStatus.ENABLED
            ),
        )
        for lookback in (5, 10, 20, 60, 120, 250)
    ),
    *(
        _definition(
            f"risk_adjusted_momentum_{lookback}",
            (
                f"momentum_{lookback} / "
                f"(std(daily_return,{lookback},ddof=1)*sqrt(252))"
            ),
            (
                f"A {lookback}-session trend supported by lower realized "
                "volatility may be more persistent."
            ),
            lookback + 1,
            _IMPLEMENTATION_HASHES[f"risk_adjusted_momentum_{lookback}"],
        )
        for lookback in (20, 60)
    ),
    _definition(
        "trend_consistency_5_10_20",
        "mean(sign(momentum_5),sign(momentum_10),sign(momentum_20))",
        "Agreement across short input lookbacks may identify persistent trends.",
        21,
        _IMPLEMENTATION_HASHES["trend_consistency_5_10_20"],
    ),
    _definition(
        "price_vs_ma20",
        "close_t / mean(close_(t-19)..close_t) - 1",
        "Price above its 20-session mean may indicate an established trend.",
        20,
        _IMPLEMENTATION_HASHES["price_vs_ma20"],
    ),
    _definition(
        "price_vs_ma60",
        "close_t / mean(close_(t-59)..close_t) - 1",
        "Price above its 60-session mean may indicate a durable trend.",
        60,
        _IMPLEMENTATION_HASHES["price_vs_ma60"],
    ),
    _definition(
        "momentum_acceleration",
        "momentum_20 - momentum_60 / 3",
        "Recent 20-session trend strength above the 60-session pace may persist.",
        61,
        _IMPLEMENTATION_HASHES["momentum_acceleration"],
    ),
)


def canonical_hash(payload: Any) -> str:
    """Return a deterministic SHA-256 over canonical JSON."""

    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_registry(registry: Sequence[FactorDefinition]) -> None:
    """Fail closed on ambiguous or incomplete research definitions."""

    if not registry:
        raise ValueError("factor registry must not be empty")
    seen: set[str] = set()
    for definition in registry:
        if definition.factor_id in seen:
            raise ValueError(f"duplicate factor_id: {definition.factor_id}")
        seen.add(definition.factor_id)
        if not re.fullmatch(r"[a-z][a-z0-9_]+", definition.factor_id):
            raise ValueError(f"invalid factor_id: {definition.factor_id}")
        if not re.fullmatch(r"\d+\.\d+\.\d+", definition.version):
            raise ValueError(f"invalid version for {definition.factor_id}")
        if definition.supported_horizons != (20,):
            raise ValueError(
                f"{definition.factor_id} must support only official horizon 20"
            )
        if definition.minimum_lookback < 1:
            raise ValueError(
                f"invalid minimum_lookback for {definition.factor_id}"
            )
        if definition.required_fields != ("close",):
            raise ValueError(f"unsupported fields for {definition.factor_id}")
        if not definition.formula or not definition.economic_hypothesis:
            raise ValueError(f"incomplete definition for {definition.factor_id}")
        if not re.fullmatch(r"[0-9a-f]{64}", definition.implementation_hash):
            raise ValueError(
                f"invalid implementation_hash for {definition.factor_id}"
            )
        if (
            definition.enabled_status is FactorStatus.DISABLED
            and not definition.disabled_reason
        ):
            raise ValueError(
                f"disabled factor {definition.factor_id} needs disabled_reason"
            )
        if (
            definition.enabled_status is not FactorStatus.DISABLED
            and definition.disabled_reason is not None
        ):
            raise ValueError(
                f"active factor {definition.factor_id} cannot have disabled_reason"
            )


def registry_hash(registry: Sequence[FactorDefinition]) -> str:
    """Hash an ordered registry after validating it."""

    validate_registry(registry)
    return canonical_hash([definition.to_dict() for definition in registry])


def get_factor_definition(factor_id: str) -> FactorDefinition:
    """Return one exact registered definition or fail closed."""

    for definition in FACTOR_REGISTRY:
        if definition.factor_id == factor_id:
            return definition
    raise KeyError(f"unknown factor_id: {factor_id}")


validate_registry(FACTOR_REGISTRY)
FACTOR_REGISTRY_HASH = registry_hash(FACTOR_REGISTRY)
