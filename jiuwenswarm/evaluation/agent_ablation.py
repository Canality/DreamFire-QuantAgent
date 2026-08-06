#!/usr/bin/env python3
"""Deterministic A0/A1/A2 Agent ablation on one frozen PIT snapshot."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.util
import json
import sys
from collections.abc import Mapping, Sequence
from datetime import datetime, time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from jiuwenswarm.quant.agent_decision import (
    OFFICIAL_SELECTION_POLICY,
    AgentProposal,
    DecisionAssembler,
    ProposalEvidence,
)
from jiuwenswarm.quant.backtest_engine import BacktestEngine
from jiuwenswarm.quant.evaluation_protocol import CompetitionWindowPolicy
from jiuwenswarm.quant.factors import PositionSizer
from jiuwenswarm.quant.stock_pool import ALL_STOCKS, SECTOR_MAP, STOCK_POOL
from jiuwenswarm.quant.strategy_configs import production_position_config

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_EXT_PATH = (
    _PROJECT_ROOT
    / "jiuwenswarm"
    / "extensions"
    / "quant-finance"
    / "extension.py"
)
_SHANGHAI = ZoneInfo("Asia/Shanghai")
_POLICY = CompetitionWindowPolicy()


def _load_extension():
    spec = importlib.util.spec_from_file_location("quant_ablation_ext", _EXT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _frame_payload(frame: pd.DataFrame) -> dict[str, Any]:
    ordered = frame.sort_index().sort_index(axis=1)
    return {
        "index": [pd.Timestamp(value).isoformat() for value in ordered.index],
        "columns": [str(value) for value in ordered.columns],
        "values": [
            [None if pd.isna(value) else round(float(value), 12) for value in row]
            for row in ordered.to_numpy()
        ],
    }


def _snapshot_sha256(
    *,
    base_scores: Mapping[str, float],
    train_prices: pd.DataFrame,
    entry_open: pd.Series,
    holding_closes: pd.DataFrame,
    decision_time: datetime,
    embargo_date: pd.Timestamp,
    session_calendar: pd.DatetimeIndex,
) -> str:
    payload = {
        "base_scores": [
            [ticker, round(float(score), 12)]
            for ticker, score in sorted(base_scores.items())
        ],
        "train_prices": _frame_payload(train_prices),
        "entry_open": [
            [ticker, round(float(entry_open[ticker]), 12)]
            for ticker in sorted(entry_open.index)
        ],
        "holding_closes": _frame_payload(holding_closes),
        "decision_time": decision_time.isoformat(),
        "embargo_date": pd.Timestamp(embargo_date).isoformat(),
        "session_calendar": [
            pd.Timestamp(value).isoformat() for value in session_calendar
        ],
        "window_policy": {
            "embargo_trading_days": _POLICY.embargo_trading_days,
            "holding_days": _POLICY.holding_days,
            "entry": _POLICY.entry,
            "exit": _POLICY.exit,
        },
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _position_overlap(left: Mapping[str, float], right: Mapping[str, float]) -> dict:
    left_set = set(left)
    right_set = set(right)
    return {
        "n_common": len(left_set & right_set),
        "n_only_left": len(left_set - right_set),
        "n_only_right": len(right_set - left_set),
        "common_tickers": sorted(left_set & right_set),
        "only_left_tickers": sorted(left_set - right_set),
        "only_right_tickers": sorted(right_set - left_set),
    }


def _proposal_payload(proposal: AgentProposal) -> dict[str, Any]:
    return {
        "role": proposal.role,
        "ticker": proposal.ticker,
        "action": proposal.action,
        "adjustment": proposal.adjustment,
        "confidence": proposal.confidence,
        "rationale": proposal.rationale,
        "valid_from": proposal.valid_from.isoformat(),
        "valid_until": proposal.valid_until.isoformat(),
        "evidence": [
            {
                "evidence_id": evidence.evidence_id,
                "signal_id": evidence.signal_id,
                "payload_sha256": evidence.payload_sha256,
                "available_at": evidence.available_at.isoformat(),
                "valid_until": evidence.valid_until.isoformat(),
                "detail": evidence.detail,
            }
            for evidence in proposal.evidence
        ],
    }


def _trace_payload(trace) -> dict[str, Any]:
    return {
        "decision_time": trace.decision_time.isoformat(),
        "base_scores": dict(sorted(trace.base_scores.items())),
        "adjusted_scores": {
            ticker: (
                "EXCLUDED"
                if score == float("-inf")
                else score
            )
            for ticker, score in sorted(trace.adjusted_scores.items())
        },
        "proposals": [_proposal_payload(proposal) for proposal in trace.proposals],
        "outcomes": [
            {
                "proposal": _proposal_payload(outcome.proposal),
                "accepted": outcome.accepted,
                "reason": outcome.reason,
                "applied_adjustment": outcome.applied_adjustment,
            }
            for outcome in trace.outcomes
        ],
        "n_proposals": len(trace.proposals),
        "n_accepted": len(trace.accepted),
        "n_rejected": len(trace.rejected),
        "reject_reasons": dict(trace.reject_reasons),
        "base_ranking": list(trace.base_ranking),
        "adjusted_ranking": list(trace.adjusted_ranking),
        "selected_before": list(trace.selected_before),
        "selected_after": list(trace.selected_after),
        "excluded_tickers": sorted(
            proposal.ticker for proposal in trace.accepted if proposal.is_veto
        ),
        "role_adjustments": [
            {
                "role": item.role,
                "ticker": item.ticker,
                "action": item.action,
                "adjustment": item.adjustment,
            }
            for item in trace.role_adjustments
        ],
    }


def _evaluate_variant(
    *,
    name: str,
    base_scores: Mapping[str, float],
    proposals: Sequence[AgentProposal],
    train_prices: pd.DataFrame,
    entry_open: pd.Series,
    holding_closes: pd.DataFrame,
    decision_time: datetime,
) -> dict[str, Any]:
    trace = DecisionAssembler.assemble(
        base_scores,
        proposals,
        decision_time=decision_time,
        selection_policy=OFFICIAL_SELECTION_POLICY,
    )
    tickers = list(trace.selected_after)
    sectors = {SECTOR_MAP[ticker] for ticker in tickers}
    if len(tickers) != OFFICIAL_SELECTION_POLICY.top_n or len(sectors) != len(STOCK_POOL):
        raise ValueError(
            f"{name} selection incomplete: {len(tickers)} stocks, {len(sectors)} sectors"
        )

    score_frame = pd.DataFrame(
        {
            "composite": [float(trace.adjusted_scores[ticker]) for ticker in tickers],
            "sector": [SECTOR_MAP[ticker] for ticker in tickers],
        },
        index=tickers,
    )
    weights = PositionSizer(production_position_config()).allocate(
        score_frame,
        train_prices[tickers],
    )
    result = BacktestEngine().run_open_to_close(
        entry_open,
        holding_closes,
        weights,
    )
    p10_daily = float(result.daily_returns.quantile(0.10))
    total_return = float(result.metrics["total_return"])
    max_drawdown = float(result.metrics["max_drawdown"])
    return {
        "variant": name,
        "tickers": tickers,
        "weights": dict(sorted(weights.items())),
        "metrics": {
            **result.metrics,
            "p10_daily_return": round(p10_daily, 6),
            "utility_return_minus_mdd": round(total_return - abs(max_drawdown), 6),
        },
        "trace": _trace_payload(trace),
    }


def evaluate_ablation(
    *,
    base_scores: Mapping[str, float],
    alpha_proposals: Sequence[AgentProposal],
    risk_proposals: Sequence[AgentProposal],
    train_prices: pd.DataFrame,
    entry_open: pd.Series,
    holding_closes: pd.DataFrame,
    decision_time: datetime,
    embargo_date: pd.Timestamp,
    session_calendar: Sequence[pd.Timestamp],
) -> dict[str, Any]:
    """Evaluate A0/A1/A2 simultaneously without shared mutable caches."""

    if decision_time.tzinfo is None or decision_time.utcoffset() is None:
        raise ValueError("decision_time must be timezone-aware")
    if set(base_scores) != set(ALL_STOCKS):
        raise ValueError("base_scores must exactly match the official stock universe")
    if list(train_prices.columns) != list(ALL_STOCKS):
        raise ValueError("train_prices must preserve the official stock order")
    if list(holding_closes.columns) != list(ALL_STOCKS):
        raise ValueError("holding_closes must preserve the official stock order")
    if list(entry_open.index) != list(ALL_STOCKS):
        raise ValueError("entry_open must preserve the official stock order")
    if len(holding_closes) != _POLICY.holding_days:
        raise ValueError(f"holding_closes must contain {_POLICY.holding_days} sessions")
    def normalise_session(value: object) -> pd.Timestamp:
        timestamp = pd.Timestamp(value)
        if timestamp.tzinfo is not None:
            timestamp = timestamp.tz_convert(_SHANGHAI).tz_localize(None)
        return timestamp.normalize()

    calendar = pd.DatetimeIndex(
        [normalise_session(value) for value in session_calendar]
    )
    if calendar.empty or calendar.has_duplicates or not calendar.is_monotonic_increasing:
        raise ValueError("session_calendar must be unique and strictly increasing")
    if any(timestamp.dayofweek >= 5 for timestamp in calendar):
        raise ValueError("session_calendar cannot contain weekend sessions")
    embargo = normalise_session(embargo_date)
    embargo_positions = [
        index for index, timestamp in enumerate(calendar) if timestamp == embargo
    ]
    if len(embargo_positions) != 1 or embargo_positions[0] == 0:
        raise ValueError("embargo_date must identify one canonical forward session")
    start_idx = embargo_positions[0]
    try:
        window = _POLICY.get_window(calendar, start_idx)
    except IndexError as exc:
        raise ValueError("session_calendar does not contain the full holding window") from exc

    decision_date = normalise_session(decision_time)
    train_sessions = pd.DatetimeIndex(
        [normalise_session(value) for value in train_prices.index]
    )
    holding_sessions = pd.DatetimeIndex(
        [normalise_session(value) for value in holding_closes.index]
    )
    if train_sessions.has_duplicates or not train_sessions.is_monotonic_increasing:
        raise ValueError("training sessions must be unique and increasing")
    if holding_sessions.has_duplicates or not holding_sessions.is_monotonic_increasing:
        raise ValueError("holding sessions must be unique and increasing")
    if list(train_sessions) != list(calendar[:start_idx]):
        raise ValueError("training sessions must end exactly before canonical embargo")
    if decision_date != normalise_session(window.decision_date):
        raise ValueError("decision_time does not match the canonical decision session")
    if embargo != normalise_session(window.embargo_date):
        raise ValueError("embargo_date does not match the canonical window")
    if list(holding_sessions) != [
        normalise_session(value) for value in window.valuation_dates
    ]:
        raise ValueError("holding closes do not match the 20 canonical valuation sessions")
    if entry_open.name is None:
        raise ValueError("entry_open must retain its source session label")
    entry_label = normalise_session(entry_open.name)
    entry_date = normalise_session(window.entry_date)
    if entry_label != entry_date or holding_sessions[0] != entry_date:
        raise ValueError("entry_open label must equal the canonical entry session")

    snapshot_sha256 = _snapshot_sha256(
        base_scores=base_scores,
        train_prices=train_prices,
        entry_open=entry_open,
        holding_closes=holding_closes,
        decision_time=decision_time,
        embargo_date=embargo,
        session_calendar=calendar,
    )
    proposal_payload = {
        "alpha": [_proposal_payload(proposal) for proposal in alpha_proposals],
        "risk": [_proposal_payload(proposal) for proposal in risk_proposals],
    }
    proposal_bundle_sha256 = hashlib.sha256(
        json.dumps(
            proposal_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    variants = {
        "A0_no_agent": _evaluate_variant(
            name="A0_no_agent",
            base_scores=base_scores,
            proposals=(),
            train_prices=train_prices,
            entry_open=entry_open,
            holding_closes=holding_closes,
            decision_time=decision_time,
        ),
        "A1_alpha_only": _evaluate_variant(
            name="A1_alpha_only",
            base_scores=base_scores,
            proposals=tuple(alpha_proposals),
            train_prices=train_prices,
            entry_open=entry_open,
            holding_closes=holding_closes,
            decision_time=decision_time,
        ),
        "A2_alpha_risk": _evaluate_variant(
            name="A2_alpha_risk",
            base_scores=base_scores,
            proposals=tuple(alpha_proposals) + tuple(risk_proposals),
            train_prices=train_prices,
            entry_open=entry_open,
            holding_closes=holding_closes,
            decision_time=decision_time,
        ),
    }
    a0 = variants["A0_no_agent"]
    for key in ("A1_alpha_only", "A2_alpha_risk"):
        variant = variants[key]
        variant["vs_A0"] = {
            "return_delta_pp": round(
                (variant["metrics"]["total_return"] - a0["metrics"]["total_return"])
                * 100,
                6,
            ),
            "max_drawdown_delta_pp": round(
                (
                    variant["metrics"]["max_drawdown"]
                    - a0["metrics"]["max_drawdown"]
                )
                * 100,
                6,
            ),
            "p10_daily_delta_pp": round(
                (
                    variant["metrics"]["p10_daily_return"]
                    - a0["metrics"]["p10_daily_return"]
                )
                * 100,
                6,
            ),
            "overlap": _position_overlap(a0["weights"], variant["weights"]),
        }

    return {
        "schema_version": "wp0b-ablation-v2",
        "snapshot_sha256": snapshot_sha256,
        "proposal_bundle_sha256": proposal_bundle_sha256,
        "decision_time": decision_time.isoformat(),
        "embargo_date": str(embargo.date()),
        "entry_date": str(entry_date.date()),
        "exit_date": str(pd.Timestamp(holding_closes.index[-1]).date()),
        "holding_sessions": len(holding_closes),
        "variants": variants,
        "promotion_eligible": False,
        "promotion_note": (
            "A single snapshot is diagnostic only; production overlay remains disabled "
            "until pre-registered outer-window evidence passes."
        ),
    }


def _bind_evidence(
    *,
    role: str,
    ticker: str,
    raw_items: Sequence[Any],
    decision_time: datetime,
) -> tuple[ProposalEvidence, ...]:
    bound: list[ProposalEvidence] = []
    for index, raw in enumerate(raw_items):
        detail = str(raw).strip()
        if not detail:
            continue
        payload_hash = hashlib.sha256(detail.encode("utf-8")).hexdigest()
        signal_id = detail.split("=", 1)[0].strip() or f"signal_{index}"
        bound.append(
            ProposalEvidence(
                evidence_id=f"derived:{role}:{ticker}:{payload_hash}:{index}",
                signal_id=signal_id,
                payload_sha256=payload_hash,
                available_at=decision_time,
                valid_until=decision_time,
                detail=detail,
            )
        )
    return tuple(bound)


def _proposals_from_views(
    alpha_view: Mapping[str, Any],
    risk_view: Mapping[str, Any],
    decision_time: datetime,
) -> tuple[tuple[AgentProposal, ...], tuple[AgentProposal, ...]]:
    alpha: list[AgentProposal] = []
    for item in alpha_view.get("alpha_stocks", [])[:12]:
        score = item.get("alpha_score", 0)
        adjustment = 2 if score >= 7 else 1 if score >= 5 else 0
        if adjustment == 0:
            continue
        alpha.append(
            AgentProposal(
                role="alpha",
                ticker=item["ticker"],
                action="include",
                adjustment=adjustment,
                confidence="high" if adjustment == 2 else "medium",
                evidence=_bind_evidence(
                    role="alpha",
                    ticker=item["ticker"],
                    raw_items=item.get("signals", [])[:2],
                    decision_time=decision_time,
                ),
                rationale=str(item.get("signals", [""])[0]),
                valid_from=decision_time,
                valid_until=decision_time,
            )
        )

    risk: list[AgentProposal] = []
    for item in risk_view.get("risky_stocks", [])[:12]:
        score = item.get("risk_score", 0)
        action = "exclude" if score >= 8 else "reduce" if score >= 5 else None
        if action is None:
            continue
        risk.append(
            AgentProposal(
                role="risk_evidence",
                ticker=item["ticker"],
                action=action,
                adjustment=-3 if action == "exclude" else -1,
                confidence="high" if action == "exclude" else "medium",
                evidence=_bind_evidence(
                    role="risk",
                    ticker=item["ticker"],
                    raw_items=item.get("warnings", [])[:2],
                    decision_time=decision_time,
                ),
                rationale=str(item.get("warnings", [""])[0]),
                valid_from=decision_time,
                valid_until=decision_time,
            )
        )
    return tuple(alpha), tuple(risk)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-date")
    parser.add_argument("--end-date")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    extension_module = _load_extension()
    extension_module._data_cache.clear()
    extension_module._phase_results.clear()
    extension = extension_module.QuantFinanceExtension()
    fetch_params = {
        key: value
        for key, value in {
            "start_date": args.start_date,
            "end_date": args.end_date,
        }.items()
        if value
    }
    fetched = asyncio.run(extension.fetch_data(fetch_params))
    if not fetched.get("success"):
        raise RuntimeError(f"fetch failed: {fetched.get('detail')}")
    cached = extension_module._get_cached_data()
    bundle = cached.get("_market_data_bundle") if cached else None
    if bundle is None or len(bundle.closes) < 61 + _POLICY.total_forward_days:
        raise RuntimeError("complete market bundle with decision/embargo/holding data required")

    start_idx = len(bundle.closes) - _POLICY.total_forward_days
    window = _POLICY.get_window(bundle.closes.index, start_idx)
    history_prices = bundle.closes.iloc[:start_idx].copy()
    history_volumes = bundle.volumes.iloc[:start_idx].copy()
    entry_open, holding_closes = _POLICY.slice_window(
        bundle.opens,
        bundle.closes,
        start_idx,
    )
    decision_time = datetime.combine(
        window.decision_date.date(),
        time(15, 0),
        tzinfo=_SHANGHAI,
    )

    # The extension's deterministic factor/analyst functions reserve 20 rows.
    # Remove the embargo row before appending the 20 holding rows so their
    # internal training slice ends exactly at the decision close.
    analysis_prices = pd.concat([history_prices, holding_closes])
    analysis_volumes = pd.concat(
        [history_volumes, bundle.volumes.reindex(holding_closes.index)]
    )
    analysis_cache = dict(cached)
    analysis_cache.update(
        _prices_df=analysis_prices,
        _volumes_df=analysis_volumes,
    )
    extension_module._data_cache["_last"] = analysis_cache
    extension_module._phase_results.clear()

    factor_result = asyncio.run(extension.compute_factors({}))
    alpha_view = asyncio.run(extension.alpha_view({}))
    risk_view = asyncio.run(extension.risk_evidence_view({}))
    if not all(result.get("success") for result in (factor_result, alpha_view, risk_view)):
        raise RuntimeError("factor or analyst view failed")
    cached = extension_module._get_cached_data()
    score_frame = cached.get("_scores_df") if cached else None
    if not isinstance(score_frame, pd.DataFrame):
        raise RuntimeError("precise cached factor scores required")
    alpha_proposals, risk_proposals = _proposals_from_views(
        alpha_view,
        risk_view,
        decision_time,
    )
    result = evaluate_ablation(
        base_scores=score_frame["composite"].to_dict(),
        alpha_proposals=alpha_proposals,
        risk_proposals=risk_proposals,
        train_prices=history_prices,
        entry_open=entry_open.reindex(ALL_STOCKS),
        holding_closes=holding_closes.reindex(columns=ALL_STOCKS),
        decision_time=decision_time,
        embargo_date=window.embargo_date,
        session_calendar=bundle.closes.index,
    )
    result["generated_at"] = datetime.now(_SHANGHAI).isoformat()
    output = args.output or (
        _PROJECT_ROOT.parent
        / "output"
        / f"ablation_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps({"output": str(output), "snapshot_sha256": result["snapshot_sha256"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
