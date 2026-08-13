"""WP1-E4-R1 research-only full dynamic selector replay over accepted E2C/E3 evidence.

Research-only, deterministic, fail-closed historical replay of the dynamic
strategy-slot selector.  For each accepted E2C decision the module rebuilds
point-in-time inputs (251-session close window + corporate-action evidence) from
the public loader, runs the accepted E3 bounded fusion exactly once per decision
(caller-injected, no-credential model function; create-once bundle), evaluates
the A0/A1/A2 variants independently, and deterministically composes each
variant's final slot weights into a stock portfolio with ONE ``PositionSizer``
call using the production position config.

Frozen oracle: ``load_e2c_evidence(regenerate=True)`` is the ONLY E2C evidence
mode (strategy_fusion_replay re-verifies artifact_sha256 / inventory_hash /
per-window hashes and fails closed on drift).  The artifact-read branch
(``regenerate=False``) is removed from the contract and unreachable: the CLI has
no ``--no-regenerate`` switch and ``run_selector_replay`` calls the loader with
the literal ``regenerate=True``.  A static regression in the focused test asserts
no artifact-read / variable-regenerate switch exists.

Composition (frozen, location.json composition_boundary): per eligible slot the
E2C-comparable composite is computed over the official 49-stock universe from
the same strictly-prior 251-session close window E2C uses (``compute_factors ->
compute_scores -> filter_high_volatility``).  The blend is
``sum_s final_weight(s) * composite_s(stock)`` over the common composite
universe; every slot must expose the identical post-filter eligible ticker set
and no in-scope stock may lack a composite (fail closed).  A0
(production:1.0 / t2:0.0) therefore equals the production_six_factor E2C
portfolio exactly.  Selection and allocation are ONE
``PositionSizer(production position_config).allocate`` call, so the selection
set equals the allocation keys by construction; the final constraints
(per-stock <=0.10, per-sector <=0.25, cash >=0.05, selection==keys, 49-stock /
six-sector source coverage) are re-asserted after normalization.

Post-filter eligible-set gate (contract clarification v2, 2026-08-13): the
composite recipe includes ``filter_high_volatility`` and the accepted E2C
production path applies the same filter, so on the real archive each slot
composite drops the same 1-2 high-volatility names per window (verified on
2025-01-14: both slot composites cover 47 of the 49 stocks, dropping 601688.SH
and 603986.SH).  Contract v2 accepts a SHARED post-filter exclusion: it is not
source-coverage loss.  The gate is: both eligible slots must expose the
identical post-filter eligible ticker set (any asymmetric exclusion fails
closed), no in-scope stock may have a NaN/missing composite, the source close
frame must still be the official 49-stock universe across six sectors, and the
blended universe must retain the top-15 selection and all six sectors.  This
preserves the frozen A0==production identity.  Excluded official tickers and the
resulting eligible identities are recorded per decision in the window payload
(``excluded_stocks`` / ``eligible_universe``, loader-ticker format) and bound
into the per-window hash, so tampering either list fails payload verification.

Block Bootstrap: ``moving_block_bootstrap`` is bound to the frozen
NestedEvaluationPlan values (seed 20260804 / iterations 2000 / block_windows 3)
and applied to the selected-variant (A2) vs A0 deltas.

Resource evidence: ``ProcessTreeRssSampler`` (root + recursive children, 0.05s,
immediate/final samples, running peak) plus ``time.monotonic()`` elapsed;
wall-clock timestamps are observational only.  ``research_selector_resource/v1``
fields are validated fail-closed (present, finite, non-negative; sampler started
and stopped; sample_count > 0; peak/current RSS present; preregistered ceilings
1800s / 2048MB).

This module is RESEARCH_ONLY and is never imported by production, direct/formal
or RPC/E2E code.  It configures no credentials and makes no real model calls in
this phase; the model is an injected callable.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import math
import sys
import time
from collections.abc import Mapping, Sequence
from numbers import Real
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parents[2]
_INNER_PKG_PARENT = _REPO_ROOT / "jiuwenswarm"
if str(_INNER_PKG_PARENT) not in sys.path:
    sys.path.insert(0, str(_INNER_PKG_PARENT))

_SH = ZoneInfo("Asia/Shanghai")

# ---------------------------------------------------------------------------
# Frozen constants (location.json supplement + fresh baseline handoff).
# ---------------------------------------------------------------------------

RESEARCH_SCHEMA = "research_selector_resource/v1"
FALLBACK_SLOT = "production_six_factor"
ELIGIBLE_SLOTS = ("production_six_factor", "t2_comparator")
GLOBALLY_EXCLUDED_SLOTS = (
    "trend_short_5_10_20",
    "trend_medium_20_60",
    "trend_long_120_250",
    "similar_market_blend",
)
BASE_SLOT_STATE = {"production_six_factor": 1.0, "t2_comparator": 0.0}
VARIANTS = ("A0_no_agent", "A1_alpha_only", "A2_alpha_risk")
SELECTED_VARIANT = "A2_alpha_risk"
COMPARISON_BASELINE = "A0_no_agent"
UNIVERSE_SIZE = 49
MIN_MATURED_WINDOWS = 8
MIN_HISTORY_SESSIONS = 251
TOP_N_STOCKS = 15

BOOTSTRAP_SEED = 20260804
BOOTSTRAP_ITERATIONS = 2000
BOOTSTRAP_BLOCK_WINDOWS = 3

SAMPLER_INTERVAL_SECONDS = 0.05
RESOURCE_CEILING_TOTAL_WALL_TIME_SECONDS_MAX = 1800.0
RESOURCE_CEILING_PROCESS_PEAK_RSS_MB_MAX = 2048.0

# Version strings bound into the selector identity hash.
SELECTOR_VERSION = "wp1e4-r1-selector-2026-08-12"
COMPOSITION_VERSION = "wp1e4-r1-composition-2026-08-12"
RESOURCE_SCHEMA_VERSION = "wp1e4-r1-resource-schema-2026-08-12"

# Frozen E2C decision inventory (accepted WP1-E2C-R1 12-window set).  Any drift
# fails the replay closed; it is never silently accepted as a new experiment.
EXPECTED_DECISION_SET: tuple[str, ...] = (
    "2025-01-14",
    "2025-02-19",
    "2025-03-19",
    "2025-04-17",
    "2025-05-20",
    "2025-06-18",
    "2025-07-16",
    "2025-08-13",
    "2025-09-10",
    "2025-10-16",
    "2025-11-13",
    "2025-12-11",
)

_SLOT_SPEC: dict[str, str] = {
    "production_six_factor": "production_six_factor",
    "t2_comparator": "phase_b_t2_score_alloc",
}

_DEFAULT_OUT_DIR = _REPO_ROOT / "output" / "selector"

# ---------------------------------------------------------------------------
# Ticker-format bridge (mirrors strategy_pool_replay).
# ---------------------------------------------------------------------------


def _to_production(ticker: str) -> str:
    exchange, code = ticker.split(".")
    return f"{code}.{exchange.upper()}"


def _to_loader(ticker: str) -> str:
    code, exchange = ticker.split(".")
    return f"{exchange.lower()}.{code}"


# ---------------------------------------------------------------------------
# Deterministic serialization / audit hashes.
# ---------------------------------------------------------------------------


def canonical_json(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def window_hash(window: Mapping[str, object]) -> str:
    """Per-window audit hash over every field except the hash itself."""
    content = {key: value for key, value in window.items() if key != "window_hash"}
    return sha256_hex(canonical_json(content))


def artifact_hash(deterministic: Mapping[str, object]) -> str:
    """Whole-artifact audit hash over the recomputable deterministic content."""
    return sha256_hex(canonical_json(deterministic))


# ---------------------------------------------------------------------------
# Final slot weights validation (mirrors StrategyAssembler normalisation).
# ---------------------------------------------------------------------------


def _validate_final_weights(final_weights: Mapping[str, object]) -> dict[str, float]:
    if not isinstance(final_weights, Mapping):
        raise ValueError("final_weights must be a mapping")
    if set(final_weights) != set(ELIGIBLE_SLOTS):
        raise ValueError(f"final_weights must cover exactly {list(ELIGIBLE_SLOTS)}")
    normalised: dict[str, float] = {}
    for slot in ELIGIBLE_SLOTS:
        value = final_weights[slot]
        if isinstance(value, bool) or not isinstance(value, Real):
            raise ValueError(f"final weight for {slot} must be a real number")
        weight = float(value)
        if not math.isfinite(weight) or weight < 0.0:
            raise ValueError(f"final weight for {slot} must be finite and non-negative")
        normalised[slot] = weight
    total = sum(normalised.values())
    if abs(total - 1.0) > 1e-6:
        raise ValueError(f"final_weights must sum to 1.0, got {total}")
    return normalised


# ---------------------------------------------------------------------------
# Deterministic stock composition (frozen composition_boundary).
# ---------------------------------------------------------------------------


def slot_composite_scores(closes_prod: pd.DataFrame, spec_name: str) -> pd.DataFrame:
    """E2C-comparable composite scores for one slot over ``closes_prod``.

    Mirrors strategy_pool_replay._factor_scores exactly: compute_factors ->
    compute_scores -> filter_high_volatility, all on the production-ticker close
    frame so sector neutralisation (STOCK_POOL / SECTOR_MAP) resolves.
    """
    from jiuwenswarm.quant.factors import FactorCalculator
    from jiuwenswarm.quant.strategy_configs import get_strategy_spec

    calculator = FactorCalculator(get_strategy_spec(spec_name).factor_config())
    factors = calculator.compute_factors(closes_prod, volume_data=None)
    scores = calculator.compute_scores(factors)
    return calculator.filter_high_volatility(scores)


def _blend_frames(
    final_weights: Mapping[str, object],
    frames: Mapping[str, pd.DataFrame],
    closes_prod: pd.DataFrame,
) -> pd.DataFrame:
    """Pure blend over the common composite universe (testable core).

    ``frames`` maps each eligible slot to its E2C-comparable scores DataFrame
    (must carry ``composite`` and ``sector`` columns).  Fail-closed rules: the
    two slots expose the identical post-filter eligible ticker set (asymmetric
    exclusion fails), no in-scope stock has a NaN/missing composite, the source
    close frame is the official 49-stock universe across six sectors, and the
    blended universe retains the top-15 selection and all six sectors.  Ties in
    the blended composite resolve to the fixed loader-built close frame row
    order.

    Contract v2 note: a SHARED post-filter exclusion (both slots dropping the
    same official names) is accepted and is not source-coverage loss; the gate
    here is that the two slots' post-filter eligible ticker sets must be
    identical while the source frame still covers the official 49 stocks across
    six sectors.  The excluded / eligible identities are recorded per decision
    by ``decision_composition`` and bound into the per-window hash.
    """
    fw = _validate_final_weights(final_weights)
    if set(frames) != set(ELIGIBLE_SLOTS):
        raise ValueError(f"composite frames must cover exactly {list(ELIGIBLE_SLOTS)}")
    indexes = [set(frames[slot].index) for slot in ELIGIBLE_SLOTS]
    if len({frozenset(index) for index in indexes}) != 1:
        raise ValueError(
            "slot composites must expose the identical post-filter eligible ticker set"
        )
    if len(closes_prod.columns) != UNIVERSE_SIZE:
        raise ValueError(f"source close frame must be the official {UNIVERSE_SIZE} stocks")

    frame = pd.DataFrame(
        {slot: frames[slot]["composite"] for slot in ELIGIBLE_SLOTS}
    )
    if frame.isna().any().any():
        raise ValueError("slot composite missing a value for a universe stock")
    sectors = frames[FALLBACK_SLOT]["sector"].reindex(frame.index)
    if sectors.isna().any():
        raise ValueError("blend universe has a stock without a sector")
    if len(sectors.unique()) != 6:
        raise ValueError("blend universe must cover all six sectors")
    if len(frame) < TOP_N_STOCKS:
        raise ValueError("blend universe too small for the frozen top-15 selection")

    blend = pd.Series(0.0, index=frame.index, dtype=float)
    for slot in ELIGIBLE_SLOTS:
        blend = blend + fw[slot] * frame[slot]

    result = pd.DataFrame({"composite": blend, "sector": sectors})
    order = {ticker: index for index, ticker in enumerate(closes_prod.columns)}
    missing_order = [ticker for ticker in result.index if ticker not in order]
    if missing_order:
        raise ValueError("blend universe contains a ticker outside the loader close frame")
    result["_order"] = result.index.map(order)
    result = result.sort_values(["composite", "_order"], ascending=[False, True])
    return result.drop(columns="_order")


def blended_scores(
    final_weights: Mapping[str, object],
    closes_prod: pd.DataFrame,
) -> pd.DataFrame:
    """Deterministic blended per-stock composite + sector over the 49 universe."""
    frames = {
        slot: slot_composite_scores(closes_prod, _SLOT_SPEC[slot])
        for slot in ELIGIBLE_SLOTS
    }
    return _blend_frames(final_weights, frames, closes_prod)


def _assert_portfolio_constraints(
    weights: Mapping[str, float],
    blended: pd.DataFrame,
    closes_prod: pd.DataFrame,
) -> None:
    """Re-assert the frozen final constraints after normalisation (fail closed)."""
    from jiuwenswarm.quant.strategy_configs import get_strategy_spec

    cfg = get_strategy_spec("production_six_factor").position_config()
    top_n = blended.head(cfg.top_n_stocks)
    if set(weights) != set(top_n.index):
        raise AssertionError("selection set != allocation keys")
    total = sum(float(value) for value in weights.values())
    if total > 1.0 - cfg.min_cash + 1e-9:
        raise AssertionError("cash reserve violated after normalization")
    if total < 0.0 or any(float(value) < 0.0 for value in weights.values()):
        raise AssertionError("negative weight after normalization")
    sector_totals: dict[str, float] = {}
    for ticker, weight in weights.items():
        if float(weight) > cfg.max_single_stock + 1e-9:
            raise AssertionError("single-stock cap violated after normalization")
        sector = blended["sector"].get(ticker, "其他")
        sector_totals[sector] = sector_totals.get(sector, 0.0) + float(weight)
    for sector, weight in sector_totals.items():
        if weight > cfg.max_single_sector + 1e-9:
            raise AssertionError("sector cap violated after normalization")
    if len(closes_prod.columns) != UNIVERSE_SIZE:
        raise AssertionError("source universe must be the official 49 stocks")
    if len(blended["sector"].unique()) != 6:
        raise AssertionError("blend universe must cover six sectors")


def compose_portfolio(
    final_weights: Mapping[str, object],
    closes_loader: pd.DataFrame,
) -> tuple[dict[str, float], pd.DataFrame]:
    """Deterministic stock composition in ONE PositionSizer call.

    ``closes_loader`` is the strictly-prior 251-session loader-ticker close
    frame.  Returns ``(weights_prod, blended)`` where ``weights_prod`` maps
    production tickers to final weights and the selection set equals the
    allocation keys by construction.
    """
    from jiuwenswarm.quant.factors import PositionSizer
    from jiuwenswarm.quant.strategy_configs import get_strategy_spec

    closes_prod = closes_loader.rename(columns=_to_production)
    blended = blended_scores(final_weights, closes_prod)
    sizer = PositionSizer(get_strategy_spec("production_six_factor").position_config())
    weights = sizer.allocate(blended, closes_prod)
    _assert_portfolio_constraints(weights, blended, closes_prod)
    return weights, blended


def _check_a0_matches_e2c_production(
    payload: Mapping[str, object],
    decision_date: str,
    composition: Mapping[str, Mapping[str, object]],
) -> None:
    """Fail closed unless A0 equals the production_six_factor E2C portfolio."""
    from evaluation.strategy_fusion_replay import _find_window

    window = _find_window(payload["deterministic"], decision_date)
    prod = window.get("candidates", {}).get("production_six_factor")
    if not isinstance(prod, dict):
        raise AssertionError("E2C window missing production_six_factor candidate")
    e2c_weights = prod.get("weights")
    if not isinstance(e2c_weights, dict):
        raise AssertionError("E2C production_six_factor weights missing")
    a0_weights = {
        ticker: round(float(value), 6)
        for ticker, value in composition["A0_no_agent"]["weights_loader"].items()
    }
    expected = {
        ticker: round(float(value), 6) for ticker, value in e2c_weights.items()
    }
    if a0_weights != expected:
        raise AssertionError(
            "A0 composition does not equal the production_six_factor E2C portfolio"
        )


# ---------------------------------------------------------------------------
# Per-decision fusion + composition (one-shot, PIT).
# ---------------------------------------------------------------------------


def decision_composition(
    payload: Mapping[str, object],
    decision_date: str,
    call_fn: object,
    *,
    closes_loader: pd.DataFrame,
    base_slot_state: Mapping[str, object] | None = None,
    evidence_registry: Mapping[str, object] | None = None,
    embargo_dates: Mapping[str, str] | None = None,
    timeout_seconds: float | None = None,
) -> dict[str, object]:
    """Run the frozen E3 boundary once and compose every variant's portfolio.

    Returns a dict with the per-variant ``{final_weights, weights_loader}``
    records plus the decision-level ``eligible_universe`` / ``excluded_stocks``
    lists (loader-ticker format, sorted).  The two eligible slots expose the
    identical post-filter eligible ticker set (any asymmetric exclusion fails
    closed in ``_blend_frames``); the excluded official tickers and the eligible
    identities are recorded here and later bound into the per-window hash.  The
    model is called at most once per role (create-once bundle); A0/A1/A2 are
    always evaluated from that single bundle with no shared mutable state.
    """
    from evaluation.strategy_fusion_replay import (
        build_evidence_registry as _build_registry,
        evaluate_variants,
        run_proposal_bundle,
        verify_e2c_payload,
    )

    if not verify_e2c_payload(payload):
        raise RuntimeError("E2C evidence failed artifact integrity verification")
    kwargs: dict[str, object] = {}
    if embargo_dates is not None:
        kwargs["embargo_dates"] = embargo_dates
    if timeout_seconds is not None:
        kwargs["timeout_seconds"] = timeout_seconds
    bundle = run_proposal_bundle(decision_date, payload, call_fn, **kwargs)
    registry = (
        evidence_registry
        if evidence_registry is not None
        else _build_registry(payload, decision_date)
    )
    base = base_slot_state if base_slot_state is not None else BASE_SLOT_STATE
    variants = evaluate_variants(bundle, base, evidence_registry=registry)

    closes_prod_columns = list(closes_loader.rename(columns=_to_production).columns)
    result: dict[str, object] = {}
    eligible_prod: list[str] | None = None
    excluded_prod: list[str] | None = None
    for name in VARIANTS:
        final_weights = dict(variants[name].final_weights)
        weights_prod, blended = compose_portfolio(final_weights, closes_loader)
        weights_loader = {
            _to_loader(ticker): round(float(value), 8)
            for ticker, value in sorted(weights_prod.items())
        }
        if eligible_prod is None:
            eligible_prod = sorted(blended.index)
            excluded_prod = sorted(set(closes_prod_columns) - set(eligible_prod))
        elif set(blended.index) != set(eligible_prod):
            raise AssertionError(
                "post-filter eligible universe drifted across variants"
            )
        result[name] = {
            "final_weights": {
                slot: round(float(final_weights[slot]), 8) for slot in sorted(final_weights)
            },
            "weights_loader": weights_loader,
        }
    result["eligible_universe"] = sorted(_to_loader(t) for t in eligible_prod)
    result["excluded_stocks"] = sorted(_to_loader(t) for t in excluded_prod)
    return result


def _window_outcome(label, weights_loader: Mapping[str, float]):
    """Official 1+20 open-to-close outcome (mirrors strategy_pool_replay)."""
    from jiuwenswarm.quant import research_evidence_loader as loader
    from jiuwenswarm.quant.backtest_engine import BacktestEngine

    entry_open = pd.Series(
        {ticker: value for ticker, value in label.entry_open if value is not None},
        dtype=float,
    )
    closes = loader.load_wide_closes(list(label.valuation_dates))
    return BacktestEngine().run_open_to_close(entry_open, closes, weights_loader)


# ---------------------------------------------------------------------------
# Selector aggregate + Block Bootstrap.
# ---------------------------------------------------------------------------


def selector_summary(windows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    """Selected-variant vs A0 return/utility deltas + deterministic Bootstrap."""
    from jiuwenswarm.quant.nested_evaluation import moving_block_bootstrap

    if not windows:
        raise ValueError("selector bootstrap requires at least one paired window")
    return_delta: list[float] = []
    utility_delta: list[float] = []
    for window in windows:
        variants = window.get("variants")
        if not isinstance(variants, dict):
            raise ValueError("window has no variants")
        selected = variants.get(SELECTED_VARIANT)
        baseline = variants.get(COMPARISON_BASELINE)
        if not isinstance(selected, dict) or not isinstance(baseline, dict):
            raise ValueError("selected/baseline variant missing")
        sel_return = selected.get("total_return")
        sel_dd = selected.get("max_drawdown")
        base_return = baseline.get("total_return")
        base_dd = baseline.get("max_drawdown")
        for value in (sel_return, sel_dd, base_return, base_dd):
            if not isinstance(value, Real) or not math.isfinite(float(value)):
                raise ValueError("variant outcome must be finite")
        sel_util = 0.7 * float(sel_return) - 0.3 * float(sel_dd)
        base_util = 0.7 * float(base_return) - 0.3 * float(base_dd)
        return_delta.append(float(sel_return) - float(base_return))
        utility_delta.append(sel_util - base_util)

    stats = moving_block_bootstrap(
        np.array(return_delta, dtype=float),
        np.array(utility_delta, dtype=float),
        iterations=BOOTSTRAP_ITERATIONS,
        block_windows=BOOTSTRAP_BLOCK_WINDOWS,
        seed=BOOTSTRAP_SEED,
    )
    return {
        "n_windows": len(windows),
        "selected_variant": SELECTED_VARIANT,
        "comparison_baseline": COMPARISON_BASELINE,
        "median_return_delta": round(float(np.median(return_delta)), 8),
        "utility_win_rate": round(
            float(np.mean(np.array(utility_delta) > 0.0)), 6
        ),
        "bootstrap": stats,
        "bootstrap_binding": {
            "method": "circular_moving_block",
            "seed": BOOTSTRAP_SEED,
            "iterations": BOOTSTRAP_ITERATIONS,
            "block_windows": BOOTSTRAP_BLOCK_WINDOWS,
            "plan": "NestedEvaluationPlan",
        },
    }


def selector_identity_hash(payload: Mapping[str, object]) -> str:
    """Joint selector identity frozen before any outer evaluation."""
    from evaluation.strategy_fusion_replay import joint_identity_hash

    base = joint_identity_hash(
        artifact_sha256=str(payload.get("artifact_sha256", "")),
        inventory_hash=str(payload.get("deterministic", {}).get("inventory_hash", "")),
        decision_set=list(payload.get("deterministic", {}).get("decision_set", [])),
    )
    return sha256_hex(
        canonical_json(
            {
                "joint_identity": base,
                "research_schema": RESEARCH_SCHEMA,
                "selector_version": SELECTOR_VERSION,
                "composition_version": COMPOSITION_VERSION,
                "resource_schema_version": RESOURCE_SCHEMA_VERSION,
                "selected_variant": SELECTED_VARIANT,
                "comparison_baseline": COMPARISON_BASELINE,
            }
        )
    )


def _validate_decision_set(decision_set: Sequence[object]) -> None:
    if tuple(str(item) for item in decision_set) != EXPECTED_DECISION_SET:
        raise RuntimeError("decision inventory drift from the accepted E2C 12-window set")


# ---------------------------------------------------------------------------
# Research resource record (research_selector_resource/v1).
# ---------------------------------------------------------------------------


def build_resource_record(
    *,
    sampler,
    elapsed_seconds: float,
    per_window: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Build the research resource record and fail closed on any gap."""
    started = getattr(sampler, "_thread", None) is not None
    stopped = bool(started and getattr(sampler, "_stop", None).is_set())
    if not started:
        raise ValueError("RSS sampler was never started")
    if not stopped:
        raise ValueError("RSS sampler stop() was not called")
    if getattr(sampler, "sample_count", 0) <= 0:
        raise ValueError("RSS sampler recorded zero samples")
    peak = getattr(sampler, "peak_rss_mb", None)
    current = getattr(sampler, "current_rss_mb", None)
    if peak is None or current is None:
        raise ValueError("RSS sampler has no peak/current measurement")
    if not isinstance(elapsed_seconds, Real) or not math.isfinite(float(elapsed_seconds)):
        raise ValueError("monotonic elapsed must be finite")
    if float(elapsed_seconds) < 0.0:
        raise ValueError("monotonic elapsed must be non-negative")

    windows: list[dict[str, object]] = []
    for item in per_window:
        decision_date = item.get("decision_date")
        wall = item.get("wall_time_seconds")
        if not isinstance(decision_date, str) or not decision_date:
            raise ValueError("per-window decision_date missing")
        if not isinstance(wall, Real) or not math.isfinite(float(wall)) or float(wall) < 0.0:
            raise ValueError("per-window wall_time_seconds must be finite and non-negative")
        windows.append(
            {"decision_date": decision_date, "wall_time_seconds": round(float(wall), 6)}
        )
    if not windows:
        raise ValueError("resource record requires at least one per-window entry")

    max_processes = getattr(sampler, "max_processes", None)
    return {
        "schema": RESEARCH_SCHEMA,
        "evidence_level": "RESEARCH_ONLY",
        "sampler": {
            "name": "ProcessTreeRssSampler",
            "interval_seconds": round(float(sampler.interval_seconds), 6),
            "scope": "root_process_plus_recursive_children",
        },
        "lifecycle": {"started": started, "stopped": stopped},
        "per_window": windows,
        "totals": {
            "wall_time_seconds": round(float(elapsed_seconds), 6),
            "process_peak_rss_mb": round(float(peak), 4),
            "current_rss_mb": round(float(current), 4),
            "process_tree_sample_count": int(sampler.sample_count),
            "max_processes": int(max_processes if max_processes is not None else 0),
        },
    }


def verify_resource_record(record: object) -> bool:
    """Fail-closed validation of the research resource record."""
    if not isinstance(record, dict):
        return False
    if record.get("schema") != RESEARCH_SCHEMA:
        return False
    if record.get("evidence_level") != "RESEARCH_ONLY":
        return False
    sampler = record.get("sampler")
    if not isinstance(sampler, dict) or sampler.get("name") != "ProcessTreeRssSampler":
        return False
    interval = sampler.get("interval_seconds")
    if (
        not isinstance(interval, Real)
        or not math.isfinite(float(interval))
        or float(interval) <= 0.0
    ):
        return False
    lifecycle = record.get("lifecycle")
    if (
        not isinstance(lifecycle, dict)
        or lifecycle.get("started") is not True
        or lifecycle.get("stopped") is not True
    ):
        return False
    totals = record.get("totals")
    if not isinstance(totals, dict):
        return False
    wall = totals.get("wall_time_seconds")
    peak = totals.get("process_peak_rss_mb")
    current = totals.get("current_rss_mb")
    for name, value in (
        ("wall_time_seconds", wall),
        ("process_peak_rss_mb", peak),
        ("current_rss_mb", current),
    ):
        if (
            value is None
            or not isinstance(value, Real)
            or not math.isfinite(float(value))
            or float(value) < 0.0
        ):
            return False
    count = totals.get("process_tree_sample_count")
    if not isinstance(count, int) or count <= 0:
        return False
    max_processes = totals.get("max_processes")
    if not isinstance(max_processes, int) or max_processes < 0:
        return False
    per_window = record.get("per_window")
    if not isinstance(per_window, list) or not per_window:
        return False
    for item in per_window:
        if not isinstance(item, dict):
            return False
        if not isinstance(item.get("decision_date"), str) or not item["decision_date"]:
            return False
        w = item.get("wall_time_seconds")
        if not isinstance(w, Real) or not math.isfinite(float(w)) or float(w) < 0.0:
            return False
    if float(wall) > RESOURCE_CEILING_TOTAL_WALL_TIME_SECONDS_MAX:
        return False
    if float(peak) > RESOURCE_CEILING_PROCESS_PEAK_RSS_MB_MAX:
        return False
    return True


# ---------------------------------------------------------------------------
# Full replay.
# ---------------------------------------------------------------------------


def verify_selector_payload(payload: object) -> bool:
    """Recompute window/artifact hashes and the resource record; False on tamper."""
    if not isinstance(payload, dict):
        return False
    deterministic = payload.get("deterministic")
    if not isinstance(deterministic, dict):
        return False
    for window in deterministic.get("windows", []):
        if not isinstance(window, dict):
            return False
        content = {key: value for key, value in window.items() if key != "window_hash"}
        if window_hash(content) != window.get("window_hash"):
            return False
    if sha256_hex(canonical_json(deterministic)) != payload.get("artifact_sha256"):
        return False
    return verify_resource_record(deterministic.get("resource"))


def run_selector_replay(
    call_fn: object,
    *,
    payload: Mapping[str, object] | None = None,
    base_slot_state: Mapping[str, object] | None = None,
    timeout_seconds: float | None = None,
    out_dir: Path | None = None,
) -> dict[str, object]:
    """Deterministic full dynamic selector replay over the accepted E2C evidence.

    ``payload`` is injected for offline tests; when ``None`` the frozen oracle
    ``load_e2c_evidence(regenerate=True)`` is used literally — the ONLY E2C
    evidence mode.  There is no artifact-read (``regenerate=False``) path.
    """
    import psutil

    from jiuwenswarm.quant.reporting.resource_meter import ProcessTreeRssSampler

    started = time.monotonic()
    sampler = ProcessTreeRssSampler(
        psutil.Process(), interval_seconds=SAMPLER_INTERVAL_SECONDS
    )
    sampler.start()
    try:
        from evaluation.strategy_fusion_replay import (
            resolve_embargo_dates,
            verify_e2c_payload,
        )
        from jiuwenswarm.quant import research_evidence_loader as loader

        if payload is None:
            from evaluation.strategy_fusion_replay import load_e2c_evidence

            payload = load_e2c_evidence(regenerate=True)
        if not verify_e2c_payload(payload):
            raise RuntimeError("E2C evidence failed artifact integrity verification")
        _validate_decision_set(payload["deterministic"].get("decision_set", []))

        decision_set = tuple(
            str(item) for item in payload["deterministic"]["decision_set"]
        )
        labels = loader.load_forward_labels()
        labels_by_decision = {label.decision_date: label for label in labels}
        embargo_dates = resolve_embargo_dates(payload)

        windows: list[dict[str, object]] = []
        per_window: list[dict[str, object]] = []
        for decision in decision_set:
            w_started = time.monotonic()
            input_bundle = loader.build_factor_input(decision_date=decision)
            composition = decision_composition(
                payload,
                decision,
                call_fn,
                closes_loader=input_bundle.closes,
                base_slot_state=base_slot_state,
                embargo_dates=embargo_dates,
                timeout_seconds=timeout_seconds,
            )
            _check_a0_matches_e2c_production(payload, decision, composition)
            label = labels_by_decision[decision]
            variant_out: dict[str, object] = {}
            for name in VARIANTS:
                item = composition[name]
                result = _window_outcome(label, item["weights_loader"])
                variant_out[name] = {
                    "final_weights": item["final_weights"],
                    "weights": {
                        ticker: round(float(value), 6)
                        for ticker, value in sorted(item["weights_loader"].items())
                    },
                    "n_stocks_held": len(item["weights_loader"]),
                    "total_return": round(float(result.total_return), 8),
                    "max_drawdown": round(float(result.max_drawdown), 8),
                    "annualized_return": round(float(result.annualized_return), 8),
                    "annualized_volatility": round(float(result.volatility), 8),
                    "sharpe_ratio": round(float(result.sharpe_ratio), 6),
                }
            windows.append(
                {
                    "decision_date": decision,
                    "entry_date": label.entry_date,
                    "exit_date": label.exit_date,
                    "valuation_dates": list(label.valuation_dates),
                    "eligible_universe": composition["eligible_universe"],
                    "excluded_stocks": composition["excluded_stocks"],
                    "variants": variant_out,
                    "selected": SELECTED_VARIANT,
                }
            )
            per_window.append(
                {
                    "decision_date": decision,
                    "wall_time_seconds": round(time.monotonic() - w_started, 6),
                }
            )
        selector = selector_summary(windows)
        identity = selector_identity_hash(payload)
        elapsed = time.monotonic() - started
    finally:
        sampler.stop()

    resource = build_resource_record(
        sampler=sampler, elapsed_seconds=elapsed, per_window=per_window
    )
    if not verify_resource_record(resource):
        raise RuntimeError("resource record failed validation")

    audited_windows: list[dict[str, object]] = []
    for window in windows:
        audited = dict(window)
        audited["window_hash"] = window_hash(window)
        audited_windows.append(audited)

    deterministic: dict[str, object] = {
        "research_schema": RESEARCH_SCHEMA,
        "selector_version": SELECTOR_VERSION,
        "composition_version": COMPOSITION_VERSION,
        "resource_schema_version": RESOURCE_SCHEMA_VERSION,
        "decision_set": list(decision_set),
        "n_windows": len(decision_set),
        "global_eligible_set": list(ELIGIBLE_SLOTS),
        "global_excluded_set": list(GLOBALLY_EXCLUDED_SLOTS),
        "identity_hash": identity,
        "selector": {
            key: value for key, value in selector.items() if key != "bootstrap_binding"
        },
        "bootstrap_binding": selector["bootstrap_binding"],
        "resource": resource,
        "windows": audited_windows,
    }
    artifact = artifact_hash(deterministic)
    out_path = (out_dir or _DEFAULT_OUT_DIR) / "dynamic_selector_replay.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_payload: dict[str, object] = {
        "task_id": "WP1-E4-R1",
        "meta": {
            "command": " ".join(sys.argv),
            "created": _dt.datetime.now(_SH).isoformat(),
            "python": sys.version.split()[0],
            "elapsed_seconds": round(elapsed, 3),
            "exit_code": 0,
            "artifact_path": str(out_path),
        },
        "deterministic": deterministic,
        "artifact_sha256": artifact,
    }
    out_path.write_text(
        json.dumps(out_payload, ensure_ascii=False, sort_keys=True, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    out_payload["meta"]["artifact_path"] = str(out_path)
    return out_payload


# ---------------------------------------------------------------------------
# Standalone research scaffold (no real model; credentials out of scope).
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="WP1-E4-R1 dynamic selector replay scaffold (research-only)"
    )
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--timeout", type=float, default=None)
    args = parser.parse_args(argv)

    def _noop_model(_role: str, _summary: Mapping[str, object]) -> str:
        # No model credentials are configured in this phase; the scaffold runs a
        # deterministic empty-proposal baseline so the pipeline is fully exercised.
        return "[]"

    payload = run_selector_replay(
        _noop_model,
        timeout_seconds=args.timeout,
        out_dir=args.out_dir,
    )
    assert verify_selector_payload(payload)
    selector = payload["deterministic"]["selector"]
    print(
        json.dumps(
            {
                "artifact": payload["meta"]["artifact_path"],
                "artifact_sha256": payload["artifact_sha256"],
                "identity_hash": payload["deterministic"]["identity_hash"],
                "n_windows": payload["deterministic"]["n_windows"],
                "selected_variant": selector.get("selected_variant"),
                "median_return_delta": selector.get("median_return_delta"),
                "utility_win_rate": selector.get("utility_win_rate"),
                "resource": payload["deterministic"]["resource"]["totals"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
