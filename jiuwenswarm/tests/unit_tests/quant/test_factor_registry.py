from __future__ import annotations

import ast
import os
import subprocess
import sys
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

import jiuwenswarm.quant.candidate_factors as candidate_factors
from jiuwenswarm.quant.candidate_factors import verify_implementation_hashes
from jiuwenswarm.quant.factor_registry import (
    FACTOR_REGISTRY,
    FACTOR_REGISTRY_HASH,
    FactorStatus,
    get_factor_definition,
    registry_hash,
    validate_registry,
)
from jiuwenswarm.quant.strategy_configs import PRODUCTION_STRATEGY, STRATEGY_SPECS


EXPECTED_FACTOR_IDS = (
    "momentum_5",
    "momentum_10",
    "momentum_20",
    "momentum_60",
    "momentum_120",
    "momentum_250",
    "risk_adjusted_momentum_20",
    "risk_adjusted_momentum_60",
    "trend_consistency_5_10_20",
    "price_vs_ma20",
    "price_vs_ma60",
    "momentum_acceleration",
)

EXPECTED_LOOKBACKS = {
    "momentum_5": 6,
    "momentum_10": 11,
    "momentum_20": 21,
    "momentum_60": 61,
    "momentum_120": 121,
    "momentum_250": 251,
    "risk_adjusted_momentum_20": 21,
    "risk_adjusted_momentum_60": 61,
    "trend_consistency_5_10_20": 21,
    "price_vs_ma20": 20,
    "price_vs_ma60": 60,
    "momentum_acceleration": 61,
}


def test_registry_contains_exact_preregistered_definitions() -> None:
    assert tuple(item.factor_id for item in FACTOR_REGISTRY) == EXPECTED_FACTOR_IDS
    assert len(FACTOR_REGISTRY) == 12
    assert {item.minimum_lookback for item in FACTOR_REGISTRY} == {
        6,
        11,
        20,
        21,
        60,
        61,
        121,
        251,
    }
    assert {
        item.factor_id: item.minimum_lookback for item in FACTOR_REGISTRY
    } == EXPECTED_LOOKBACKS


def test_registry_metadata_is_complete_and_horizon_is_unified() -> None:
    for definition in FACTOR_REGISTRY:
        payload = definition.to_dict()
        assert set(payload) == {
            "factor_id",
            "version",
            "family",
            "formula",
            "economic_hypothesis",
            "expected_direction",
            "required_fields",
            "minimum_lookback",
            "supported_horizons",
            "normalization",
            "sector_neutralization",
            "missing_value_policy",
            "availability_time_policy",
            "corporate_action_requirement",
            "enabled_status",
            "disabled_reason",
            "implementation_hash",
        }
        assert definition.version == "1.0.0"
        assert definition.family == "trend_momentum"
        assert definition.supported_horizons == (20,)
        assert definition.required_fields == ("close",)
        assert definition.expected_direction == "POSITIVE"
        assert definition.normalization == "RAW_ONLY_WP1_E0"
        assert definition.sector_neutralization == "NONE_WP1_E0"
        assert definition.missing_value_policy == "UNAVAILABLE_NO_IMPUTATION"
        assert len(definition.implementation_hash) == 64
        int(definition.implementation_hash, 16)

    conditional = get_factor_definition("momentum_250")
    assert conditional.enabled_status is FactorStatus.CONDITIONAL
    assert conditional.disabled_reason is None
    assert all(
        item.enabled_status is FactorStatus.ENABLED
        for item in FACTOR_REGISTRY
        if item.factor_id != "momentum_250"
    )


def test_registry_is_frozen_deterministic_and_lookup_fails_closed() -> None:
    assert FACTOR_REGISTRY_HASH == registry_hash(FACTOR_REGISTRY)
    assert FACTOR_REGISTRY_HASH == registry_hash(tuple(FACTOR_REGISTRY))
    with pytest.raises(FrozenInstanceError):
        FACTOR_REGISTRY[0].family = "tampered"  # type: ignore[misc]
    with pytest.raises(KeyError, match="unknown factor_id"):
        get_factor_definition("not_registered")


def test_duplicate_or_invalid_registry_fails_closed() -> None:
    with pytest.raises(ValueError, match="duplicate factor_id"):
        validate_registry(FACTOR_REGISTRY + (FACTOR_REGISTRY[0],))

    wrong_horizon = replace(FACTOR_REGISTRY[0], supported_horizons=(5,))
    with pytest.raises(ValueError, match="official horizon"):
        validate_registry((wrong_horizon,) + FACTOR_REGISTRY[1:])

    bad_hash = replace(FACTOR_REGISTRY[0], implementation_hash="not-a-hash")
    with pytest.raises(ValueError, match="implementation_hash"):
        validate_registry((bad_hash,) + FACTOR_REGISTRY[1:])


def test_registered_implementation_hashes_match_exact_kernels() -> None:
    verify_implementation_hashes()
    tampered = replace(FACTOR_REGISTRY[0], implementation_hash="0" * 64)
    with pytest.raises(ValueError, match="implementation hash mismatch"):
        verify_implementation_hashes((tampered,) + FACTOR_REGISTRY[1:])


def _tampered_momentum(prices, lookback):  # type: ignore[no-untyped-def]
    return 123.0


def _nested_dependency(prices, lookback):  # type: ignore[no-untyped-def]
    return float(prices[-1] / prices[-lookback - 1] - 1.0)


def _nested_kernel(prices):  # type: ignore[no-untyped-def]
    return sum(_nested_dependency(prices, lookback) for lookback in (5, 10, 20))


def test_dependency_closure_walks_nested_code_objects() -> None:
    """Helper discovery must not depend on Python comprehension inlining."""

    original_dependency_module = _nested_dependency.__module__
    original_kernel_module = _nested_kernel.__module__
    try:
        _nested_dependency.__module__ = candidate_factors.__name__
        _nested_kernel.__module__ = candidate_factors.__name__
        closure = candidate_factors._function_dependency_closure(_nested_kernel)
    finally:
        _nested_dependency.__module__ = original_dependency_module
        _nested_kernel.__module__ = original_kernel_module

    assert {function.__name__ for function in closure} == {
        "_nested_dependency",
        "_nested_kernel",
    }


def test_kernel_dispatch_parameters_and_transitive_helpers_are_hashed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(
        candidate_factors._KERNELS,
        "momentum_5",
        (_tampered_momentum, {"lookback": 5}),
    )
    with pytest.raises(ValueError, match="implementation hash mismatch"):
        verify_implementation_hashes()

    monkeypatch.undo()
    original = candidate_factors._momentum
    monkeypatch.setattr(candidate_factors, "_momentum", _tampered_momentum)
    with pytest.raises(ValueError, match="implementation hash mismatch"):
        verify_implementation_hashes()
    monkeypatch.setattr(candidate_factors, "_momentum", original)

    kernel, _ = candidate_factors._KERNELS["momentum_5"]
    monkeypatch.setitem(
        candidate_factors._KERNELS,
        "momentum_5",
        (kernel, {"lookback": 6}),
    )
    with pytest.raises(ValueError, match="implementation hash mismatch"):
        verify_implementation_hashes()


def test_research_modules_are_not_imported_by_production_paths() -> None:
    assert PRODUCTION_STRATEGY == "production_six_factor"
    production = STRATEGY_SPECS[PRODUCTION_STRATEGY]
    assert production.name == PRODUCTION_STRATEGY
    assert production.factor_weights == (0.34, 0.17, 0.16, 0.08, 0.19, 0.06)

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
        "jiuwenswarm.quant.factor_registry",
        "jiuwenswarm.quant.candidate_factors",
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
                node.module in {"factor_registry", "candidate_factors"}
                or any(
                    alias.name in {"factor_registry", "candidate_factors"}
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
    assert "jiuwenswarm.quant.factor_registry" not in sys.modules, module
    assert "jiuwenswarm.quant.candidate_factors" not in sys.modules, module
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
