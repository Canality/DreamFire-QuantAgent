"""WP1-E2C-R1 research-only deterministic strategy-pool historical replay.

Research-only, point-in-time replay over the accepted typed evidence bridges
(604 v2 forward labels, E0 qfq closes, official calendar/sector/operate).
Only public APIs and existing production components are used:

  - factor_evidence_provider.inspect_research_evidence_readiness
  - research_evidence_loader: load_forward_labels / load_canonical_calendar_evidence /
    load_sector_metadata_evidence / load_wide_closes / compute_49x12_snapshot
  - factor_research.compute_factor_research_snapshot / MaturedFactorObservation
  - strategy_configs.get_strategy_spec
  - factors.FactorCalculator / PositionSizer
  - backtest_engine.BacktestEngine.run_open_to_close
  - evaluation_protocol.CompetitionWindowPolicy

No private kernel, no monkeypatch of trust, no replay-local rank-IC copy,
no network.  All candidates share the identical non-overlapping matured decision
windows; similar_market_blend is per-window BENCHMARK_UNAVAILABLE.

Output contract (accepted in location.json): the artifact separates runtime
metadata (meta) from recomputable deterministic content.  Every window carries a
per-window audit ``window_hash``; the whole deterministic payload carries a
recomputable ``artifact_sha256``.  ``verify_artifact`` recomputes both and
detects any tamper.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import sys
import time
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parents[2]
_INNER_PKG_PARENT = _REPO_ROOT / "jiuwenswarm"
if str(_INNER_PKG_PARENT) not in sys.path:
    sys.path.insert(0, str(_INNER_PKG_PARENT))

from jiuwenswarm.quant import research_evidence_loader as loader  # noqa: E402
from jiuwenswarm.quant import strategy_pool  # noqa: E402
from jiuwenswarm.quant.backtest_engine import BacktestEngine  # noqa: E402
from jiuwenswarm.quant.candidate_factors import AVAILABLE  # noqa: E402
from jiuwenswarm.quant.evaluation_protocol import CompetitionWindowPolicy  # noqa: E402
from jiuwenswarm.quant.factor_evidence_provider import (  # noqa: E402
    inspect_research_evidence_readiness,
)
from jiuwenswarm.quant.factor_registry import FACTOR_REGISTRY  # noqa: E402
from jiuwenswarm.quant.factor_research import (  # noqa: E402
    FactorDirection,
    MaturedFactorObservation,
    compute_factor_research_snapshot,
)
from jiuwenswarm.quant.factors import FactorCalculator, PositionSizer  # noqa: E402
from jiuwenswarm.quant.market_regime import MarketRegime  # noqa: E402
from jiuwenswarm.quant.strategy_configs import get_strategy_spec  # noqa: E402

_SH = ZoneInfo("Asia/Shanghai")

# Preregistered acceptance thresholds, canonical source:
# jiuwenswarm/evaluation/unified_baseline_evaluation.py PREREGISTRATION.
PREREGISTERED_THRESHOLDS: dict[str, float] = {
    "median_return_delta_min": 0.003,
    "paired_utility_win_rate_min": 0.60,
    "recent_four_utility_wins_min": 3,
    "median_drawdown_worsening_max": 0.003,
    "worst_return_worsening_max": 0.005,
}
UTILITY_RETURN_WEIGHT = 0.70
UTILITY_DRAWDOWN_WEIGHT = 0.30
REASON_BENCHMARK_UNAVAILABLE = "BENCHMARK_UNAVAILABLE"
REASON_DOES_NOT_QUALIFY = "DOES_NOT_QUALIFY"
REASON_QUALIFIED = "QUALIFIED"

MIN_MATURED_WINDOWS = 8
MIN_HISTORY_SESSIONS = 251
OPERATE_COVERAGE_END = "2025-12-31"
UNIVERSE_SIZE = 49

_DEFAULT_OUT_DIR = _REPO_ROOT / "output" / "replay"

_SLOT_ORDER = (
    "production_six_factor",
    "t2_comparator",
    "trend_short_5_10_20",
    "trend_medium_20_60",
    "trend_long_120_250",
    "similar_market_blend",
)


# --------------------------------------------------------------------------
# Deterministic serialization / audit hashes.
# --------------------------------------------------------------------------

def canonical_json(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def window_hash(window: dict[str, object]) -> str:
    """Per-window audit hash over every field except the hash itself."""
    content = {key: value for key, value in window.items() if key != "window_hash"}
    return sha256_hex(canonical_json(content))


def artifact_hash(deterministic: dict[str, object]) -> str:
    """Whole-artifact audit hash over the recomputable deterministic content."""
    return sha256_hex(canonical_json(deterministic))


def build_deterministic_payload(
    *,
    inventory_hash: str,
    decision_set: tuple[str, ...] | list[str],
    windows: list[dict[str, object]],
    candidates: dict[str, object],
) -> dict[str, object]:
    """Deterministic, recomputable artifact content (windows get window_hash)."""
    audited_windows = []
    for window in windows:
        audited = dict(window)
        audited["window_hash"] = window_hash(window)
        audited_windows.append(audited)
    return {
        "inventory_hash": inventory_hash,
        "thresholds": PREREGISTERED_THRESHOLDS,
        "utility": (
            f"{UTILITY_RETURN_WEIGHT} * total_return - "
            f"{UTILITY_DRAWDOWN_WEIGHT} * max_drawdown"
        ),
        "decision_set": list(decision_set),
        "n_windows": len(decision_set),
        "min_history_sessions": MIN_HISTORY_SESSIONS,
        "operate_coverage_end": OPERATE_COVERAGE_END,
        "windows": audited_windows,
        "candidates": candidates,
    }


def verify_artifact(payload: dict[str, object]) -> bool:
    """Recompute per-window and whole-artifact hashes; False on any tamper."""
    deterministic = payload.get("deterministic")
    if not isinstance(deterministic, dict):
        return False
    for window in deterministic.get("windows", []):
        if not isinstance(window, dict):
            return False
        if window_hash(window) != window.get("window_hash"):
            return False
    return sha256_hex(canonical_json(deterministic)) == payload.get("artifact_sha256")


# --------------------------------------------------------------------------
# Ticker-format bridge: loader uses "sh.601318", production STOCK_POOL uses
# "601318.SH".  Both refer to the same 49 official stocks.
# --------------------------------------------------------------------------

def _to_production(ticker: str) -> str:
    exchange, code = ticker.split(".")
    return f"{code}.{exchange.upper()}"


def _to_loader(ticker: str) -> str:
    code, exchange = ticker.split(".")
    return f"{exchange.lower()}.{code}"


# --------------------------------------------------------------------------
# Decision window set: strictly-prior, non-overlapping, matured.
# --------------------------------------------------------------------------

def compute_decision_set(
    sessions: pd.DatetimeIndex,
    label_decisions: list[str],
    policy: CompetitionWindowPolicy,
    *,
    min_history: int = MIN_HISTORY_SESSIONS,
    operate_end: str = OPERATE_COVERAGE_END,
) -> tuple[str, ...]:
    """Select non-overlapping matured decisions; fail closed below the minimum.

    A decision is eligible when it is an accepted label decision with at least
    ``min_history`` prior sessions and its 251-session factor window is inside
    the operate archive coverage ``[start, operate_end]``.  Windows are then
    spaced so they never overlap (next decision at least ``holding_days``
    sessions after the previous one).
    """
    label_set = set(label_decisions)
    valid_positions = [
        index
        for index in range(len(sessions))
        if index >= min_history - 1
        and sessions[index].date().isoformat() <= operate_end
        and sessions[index].date().isoformat() in label_set
    ]
    selected: list[int] = []
    last_position = -1
    for position in valid_positions:
        if last_position < 0 or position >= last_position + policy.holding_days:
            selected.append(position)
            last_position = position
    if len(selected) < MIN_MATURED_WINDOWS:
        raise ValueError(
            f"insufficient matured non-overlapping windows: "
            f"{len(selected)} < {MIN_MATURED_WINDOWS}"
        )
    return tuple(sessions[index].date().isoformat() for index in selected)


def _exit_position(position: int, policy: CompetitionWindowPolicy) -> int:
    # Label window is [decision, embargo+1, entry+2 .. exit+21].
    return position + policy.embargo_trading_days + policy.holding_days


def prior_matured_decisions(
    decision: str,
    selected: tuple[str, ...],
    positions: dict[str, int],
    policy: CompetitionWindowPolicy,
) -> tuple[str, ...]:
    """Prior selected decisions whose label window fully matured before decision."""
    decision_pos = positions[decision]
    return tuple(
        prior
        for prior in selected
        if positions[prior] < decision_pos
        and _exit_position(positions[prior], policy) < decision_pos
    )


# --------------------------------------------------------------------------
# Candidate scoring.
# --------------------------------------------------------------------------

def _factor_scores(spec, closes_prod: pd.DataFrame) -> pd.DataFrame:
    """Production/T2 six-factor scores in production ticker format.

    ``closes_prod`` must already use production tickers (``601318.SH``) so the
    sector neutralization inside FactorCalculator (STOCK_POOL / SECTOR_MAP)
    resolves correctly and PositionSizer receives prices in the same format.
    """
    calculator = FactorCalculator(spec.factor_config())
    factors = calculator.compute_factors(closes_prod, volume_data=None)
    scores = calculator.compute_scores(factors)
    return calculator.filter_high_volatility(scores)


def _production_factor_contributions(
    spec,
    scores: pd.DataFrame,
    selected_tickers: list[str],
) -> dict[str, float]:
    """Regime-weighted factor contribution to the composite of the held names."""
    factor_config = spec.factor_config()
    weights = factor_config.get_regime_weights(MarketRegime.RANGE)
    contributions: dict[str, float] = {}
    for factor, weight in weights.items():
        if weight == 0.0 or factor not in scores.columns:
            continue
        z = scores.loc[selected_tickers, factor].fillna(0.0)
        contributions[factor] = round(float(weight * float(z.mean())), 8)
    return contributions


def _directions_at(
    observations: tuple[MaturedFactorObservation, ...],
    decision_15h: _dt.datetime,
    calendar_evidence,
    sector_evidence,
) -> dict[str, FactorDirection]:
    """Factor directions from a public, strictly-prior matured research snapshot."""
    if not observations:
        return {item.factor_id: FactorDirection.NEUTRAL for item in FACTOR_REGISTRY}
    research = compute_factor_research_snapshot(
        decision_time=decision_15h,
        observations=observations,
        calendar_evidence=calendar_evidence,
        sector_evidence=sector_evidence,
    )
    return {metric.factor_id: metric.direction for metric in research.metrics}


def _trend_scores(
    slot: strategy_pool.PoolSlot,
    snapshot,
    directions: dict[str, FactorDirection],
    sector_map: dict[str, str],
) -> tuple[pd.DataFrame, dict[str, pd.Series]] | None:
    """A0 equal-weight direction-flipped cross-sectional percentile scores.

    Returns ``(scores, components)`` where ``components`` maps each valid
    factor id to its (possibly flipped) cross-sectional percentile series.
    """
    components: dict[str, pd.Series] = {}
    for factor_id in slot.factor_ids:
        direction = directions.get(factor_id, FactorDirection.NEUTRAL)
        if direction is FactorDirection.NEUTRAL:
            continue
        if factor_id not in snapshot.values.columns:
            continue
        status = snapshot.status[factor_id]
        available = snapshot.values.index[status == AVAILABLE]
        if len(available) < 1:
            continue
        series = snapshot.values[factor_id].loc[available].astype(float)
        ranks = series.rank(pct=True)
        if direction is FactorDirection.FLIPPED:
            ranks = 1.0 - ranks
        components[factor_id] = ranks
    if not components:
        return None
    composite = pd.concat(components, axis=1).mean(axis=1)
    scores = pd.DataFrame({"composite": composite})
    scores["sector"] = [sector_map.get(ticker, "其他") for ticker in scores.index]
    return scores.sort_values("composite", ascending=False), components


def _trend_factor_contributions(
    components: dict[str, pd.Series],
    selected_tickers: list[str],
) -> dict[str, float]:
    """Equal-weight share of each factor in the trend composite."""
    n_valid = len(components)
    contributions: dict[str, float] = {}
    for factor_id, series in components.items():
        mean_share = series.reindex(selected_tickers).fillna(0.0).mean() / n_valid
        contributions[factor_id] = round(float(mean_share), 8)
    return contributions


def _allocate(scores: pd.DataFrame, closes: pd.DataFrame, position_config) -> dict[str, float]:
    sizer = PositionSizer(position_config)
    return sizer.allocate(scores, closes)


def _weights_to_loader(weights: dict[str, float]) -> dict[str, float]:
    return {_to_loader(ticker): value for ticker, value in weights.items()}


# --------------------------------------------------------------------------
# Per-window return measurement (official 1+20 open-to-close).
# --------------------------------------------------------------------------

def _window_backtest(
    label,
    weights_loader: dict[str, float],
) -> object:
    entry_open = pd.Series(
        {ticker: value for ticker, value in label.entry_open if value is not None},
        dtype=float,
    )
    closes = loader.load_wide_closes(list(label.valuation_dates))
    return BacktestEngine().run_open_to_close(entry_open, closes, weights_loader)


def _window_row(
    result,
    weights: dict[str, float],
    factor_contributions: dict[str, float],
) -> dict[str, object]:
    n_stocks = len(weights)
    return {
        "total_return": round(float(result.total_return), 8),
        "max_drawdown": round(float(result.max_drawdown), 8),
        "annualized_return": round(float(result.annualized_return), 8),
        "annualized_volatility": round(float(result.volatility), 8),
        "sharpe_ratio": round(float(result.sharpe_ratio), 6),
        "n_stocks_held": n_stocks,
        "coverage": round(n_stocks / UNIVERSE_SIZE, 6),
        "factor_contributions": factor_contributions,
        "weights": {ticker: round(value, 6) for ticker, value in sorted(weights.items())},
    }


# --------------------------------------------------------------------------
# Candidate-level preregistered threshold evaluation vs production.
# --------------------------------------------------------------------------

def evaluate_candidate(
    candidate: dict[str, dict[str, float]],
    production: dict[str, dict[str, float]],
    thresholds: dict[str, float] | None = None,
) -> dict[str, object]:
    """Return verdict + metrics for one candidate compared with production.

    ``candidate``/``production`` map decision -> {"total_return", "max_drawdown"}.
    Comparison uses the candidate's available (common) windows only; production
    is the baseline.  Mirrors unified_baseline_evaluation.compare_to_production.
    Fewer than ``MIN_MATURED_WINDOWS`` comparable windows fails closed.
    """
    thresholds = thresholds or PREREGISTERED_THRESHOLDS
    common = [d for d in candidate if d in production]
    if len(common) < MIN_MATURED_WINDOWS:
        return {
            "verdict": REASON_DOES_NOT_QUALIFY,
            "reason": "insufficient comparable windows",
            "n_windows": len(common),
        }
    return_delta = np.array(
        [candidate[d]["total_return"] - production[d]["total_return"] for d in common],
        dtype=float,
    )
    dd_delta = np.array(
        [candidate[d]["max_drawdown"] - production[d]["max_drawdown"] for d in common],
        dtype=float,
    )
    utilities = np.array(
        [
            UTILITY_RETURN_WEIGHT * candidate[d]["total_return"]
            - UTILITY_DRAWDOWN_WEIGHT * candidate[d]["max_drawdown"]
            - (
                UTILITY_RETURN_WEIGHT * production[d]["total_return"]
                - UTILITY_DRAWDOWN_WEIGHT * production[d]["max_drawdown"]
            )
            for d in common
        ],
        dtype=float,
    )
    recent_wins = int((utilities[-4:] > 0).sum()) if len(utilities) >= 4 else int(
        (utilities > 0).sum()
    )
    candidate_worst = min(candidate[d]["total_return"] for d in common)
    production_worst = min(production[d]["total_return"] for d in common)
    checks = {
        "median_return_delta_gte_0.003": float(np.median(return_delta))
        >= thresholds["median_return_delta_min"],
        "utility_win_rate_gte_0.60": float((utilities > 0).mean())
        >= thresholds["paired_utility_win_rate_min"],
        "recent_four_wins_gte_3": recent_wins >= thresholds["recent_four_utility_wins_min"],
        "median_drawdown_worsening_lte_0.003": float(np.median(dd_delta))
        <= thresholds["median_drawdown_worsening_max"],
        "worst_return_worsening_lte_0.005": candidate_worst
        >= production_worst - thresholds["worst_return_worsening_max"],
    }
    verdict = REASON_QUALIFIED if all(checks.values()) else REASON_DOES_NOT_QUALIFY
    return {
        "verdict": verdict,
        "reason": verdict,
        "n_windows": len(common),
        "median_return_delta": round(float(np.median(return_delta)), 6),
        "mean_return_delta": round(float(np.mean(return_delta)), 6),
        "median_drawdown_delta": round(float(np.median(dd_delta)), 6),
        "utility_wins": int((utilities > 0).sum()),
        "utility_win_rate": round(float((utilities > 0).mean()), 4),
        "recent_four_utility_wins": recent_wins,
        "worst_return": round(candidate_worst, 6),
        "checks": checks,
    }


# --------------------------------------------------------------------------
# Aggregate metrics.
# --------------------------------------------------------------------------

def _aggregate(rows: dict[str, dict[str, object]]) -> dict[str, object]:
    """Aggregate return/drawdown/volatility/Sharpe/Calmar/coverage/factor contribution."""
    if not rows:
        return {"n_windows": 0}
    returns = np.array([row["total_return"] for row in rows.values()], dtype=float)
    drawdowns = np.array([row["max_drawdown"] for row in rows.values()], dtype=float)
    annualized = np.array([row["annualized_return"] for row in rows.values()], dtype=float)
    volatility = np.array(
        [row["annualized_volatility"] for row in rows.values()], dtype=float
    )
    sharpes = np.array([row["sharpe_ratio"] for row in rows.values()], dtype=float)
    coverages = np.array([row["coverage"] for row in rows.values()], dtype=float)
    calmars = annualized / np.maximum(drawdowns, 1e-10)
    factor_keys = sorted(
        {factor for row in rows.values() for factor in row["factor_contributions"]}
    )
    return {
        "n_windows": len(rows),
        "median_return": round(float(np.median(returns)), 6),
        "mean_return": round(float(np.mean(returns)), 6),
        "worst_return": round(float(np.min(returns)), 6),
        "positive_windows": int((returns > 0).sum()),
        "median_drawdown": round(float(np.median(drawdowns)), 6),
        "worst_drawdown": round(float(np.max(drawdowns)), 6),
        "median_annualized_return": round(float(np.median(annualized)), 6),
        "median_annualized_volatility": round(float(np.median(volatility)), 6),
        "median_sharpe": round(float(np.median(sharpes)), 4),
        "median_calmar": round(float(np.median(calmars)), 4),
        "median_coverage": round(float(np.median(coverages)), 6),
        "mean_factor_contributions": {
            factor: round(
                float(np.mean([row["factor_contributions"].get(factor, 0.0) for row in rows.values()])),
                6,
            )
            for factor in factor_keys
        },
    }


# --------------------------------------------------------------------------
# Full replay.
# --------------------------------------------------------------------------

def run_replay(out_dir: Path | None = None) -> dict[str, object]:
    started = time.monotonic()
    readiness = inspect_research_evidence_readiness()
    capabilities = {c.capability: c for c in readiness.capabilities}
    if not capabilities["OFFICIAL_FORWARD_LABEL"].available:
        raise RuntimeError(
            f"OFFICIAL_FORWARD_LABEL not available: "
            f"{capabilities['OFFICIAL_FORWARD_LABEL'].reason}"
        )
    if not readiness.ready_for_e0 or not readiness.ready_for_e1:
        raise RuntimeError("research evidence readiness is not complete")

    labels = loader.load_forward_labels()
    calendar = loader.load_canonical_calendar_evidence()
    sector_evidence = loader.load_sector_metadata_evidence()
    policy = CompetitionWindowPolicy()

    sessions = pd.DatetimeIndex(pd.to_datetime(list(calendar.sessions)))
    positions = {
        session.date().isoformat(): index for index, session in enumerate(sessions)
    }
    label_decisions = [label.decision_date for label in labels]
    selected = compute_decision_set(sessions, label_decisions, policy)
    labels_by_decision = {label.decision_date: label for label in labels}
    sector_map = dict(sector_evidence.sectors)

    # Precompute one strictly-prior 49x12 snapshot per selected decision.
    snapshots = {
        decision: loader.compute_49x12_snapshot(decision_date=decision)
        for decision in selected
    }
    observation_by_decision = {
        decision: MaturedFactorObservation(snapshots[decision], labels_by_decision[decision])
        for decision in selected
    }

    windows: list[dict[str, object]] = []
    production_rows: dict[str, dict[str, object]] = {}
    candidate_rows: dict[str, dict[str, dict[str, object]]] = {
        name: {} for name in _SLOT_ORDER
    }
    unavailable: dict[str, list[str]] = {name: [] for name in _SLOT_ORDER}

    for decision in selected:
        decision_pos = positions[decision]
        window_sessions = sessions[
            decision_pos - MIN_HISTORY_SESSIONS + 1 : decision_pos + 1
        ]
        closes_loader = loader.load_wide_closes(
            [session.date().isoformat() for session in window_sessions]
        )
        label = labels_by_decision[decision]
        decision_15h = _dt.datetime.combine(
            sessions[decision_pos].date(), _dt.time(15, 0), tzinfo=_SH
        )
        directions = _directions_at(
            tuple(
                observation_by_decision[prior]
                for prior in prior_matured_decisions(
                    decision, selected, positions, policy
                )
            ),
            decision_15h,
            calendar,
            sector_evidence,
        )

        per_candidate: dict[str, object] = {}
        for name in _SLOT_ORDER:
            if name == "similar_market_blend":
                per_candidate[name] = {
                    "status": REASON_BENCHMARK_UNAVAILABLE,
                    "reason": "no trusted aligned benchmark evidence",
                }
                unavailable[name].append(decision)
                continue
            slot = strategy_pool.get_pool_slot(name)
            if name in ("production_six_factor", "t2_comparator"):
                closes_prod = closes_loader.rename(columns=_to_production)
                spec = get_strategy_spec(
                    "production_six_factor"
                    if name == "production_six_factor"
                    else "phase_b_t2_score_alloc"
                )
                scores = _factor_scores(spec, closes_prod)
                production_weights = _allocate(scores, closes_prod, spec.position_config())
                weights = _weights_to_loader(production_weights)
                contributions = _production_factor_contributions(
                    spec, scores, list(production_weights.keys())
                )
            else:
                trend = _trend_scores(slot, snapshots[decision], directions, sector_map)
                if trend is None:
                    per_candidate[name] = {
                        "status": "UNAVAILABLE",
                        "reason": "no valid direction for registered factors",
                    }
                    unavailable[name].append(decision)
                    continue
                scores, components = trend
                spec = get_strategy_spec("production_six_factor")
                weights = _allocate(scores, closes_loader, spec.position_config())
                contributions = _trend_factor_contributions(
                    components, list(weights.keys())
                )
            result = _window_backtest(labels_by_decision[decision], weights)
            per_candidate[name] = {
                "status": "OK",
                "reason": "OK",
                **_window_row(result, weights, contributions),
            }
            row = {
                "total_return": float(result.total_return),
                "max_drawdown": float(result.max_drawdown),
                "annualized_return": float(result.annualized_return),
                "annualized_volatility": float(result.volatility),
                "sharpe_ratio": float(result.sharpe_ratio),
                "n_stocks_held": len(weights),
                "coverage": len(weights) / UNIVERSE_SIZE,
                "factor_contributions": contributions,
            }
            if name == "production_six_factor":
                production_rows[decision] = row
            else:
                candidate_rows[name][decision] = row

        windows.append(
            {
                "decision_date": decision,
                "entry_date": label.entry_date,
                "exit_date": label.exit_date,
                "valuation_dates": list(label.valuation_dates),
                "candidates": per_candidate,
            }
        )

    results: dict[str, object] = {}
    for name in _SLOT_ORDER:
        if name == "similar_market_blend":
            results[name] = {
                "status": REASON_BENCHMARK_UNAVAILABLE,
                "windows": unavailable[name],
            }
        elif name == "production_six_factor":
            results[name] = {
                "status": "OK",
                **_aggregate(production_rows),
            }
        else:
            results[name] = {
                "n_available_windows": len(candidate_rows[name]),
                "unavailable_windows": unavailable[name],
                **_aggregate(candidate_rows[name]),
                **evaluate_candidate(candidate_rows[name], production_rows),
            }

    deterministic = build_deterministic_payload(
        inventory_hash=readiness.inventory_hash,
        decision_set=selected,
        windows=windows,
        candidates=results,
    )
    artifact = artifact_hash(deterministic)
    elapsed = round(time.monotonic() - started, 3)

    out_path = (out_dir or _DEFAULT_OUT_DIR) / "strategy_pool_replay.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {
        "task_id": "WP1-E2C-R1",
        "meta": {
            "command": " ".join(sys.argv),
            "created": _dt.datetime.now(_SH).isoformat(),
            "python": sys.version.split()[0],
            "elapsed_seconds": elapsed,
            "exit_code": 0,
            "artifact_path": str(out_path),
        },
        "deterministic": deterministic,
        "artifact_sha256": artifact,
    }
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    payload["meta"]["artifact_path"] = str(out_path)
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="WP1-E2C-R1 strategy-pool replay")
    parser.add_argument("--out-dir", type=Path, default=_DEFAULT_OUT_DIR)
    args = parser.parse_args(argv)
    payload = run_replay(out_dir=args.out_dir)
    assert verify_artifact(payload)
    summary = {
        name: (
            value.get("verdict") or value.get("status")
            if isinstance(value, dict)
            else value
        )
        for name, value in payload["deterministic"]["candidates"].items()
    }
    print(
        json.dumps(
            {
                "artifact": payload["meta"]["artifact_path"],
                "artifact_sha256": payload["artifact_sha256"],
                "summary": summary,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
