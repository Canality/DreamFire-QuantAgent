"""Tests for cache-independent A0/A1/A2 ablation evidence."""

from __future__ import annotations

import hashlib
import importlib.util
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

from jiuwenswarm.quant.agent_decision import AgentProposal, ProposalEvidence, select_portfolio
from jiuwenswarm.quant.stock_pool import ALL_STOCKS


def _load_module():
    path = Path(__file__).resolve().parents[3] / "evaluation" / "agent_ablation.py"
    spec = importlib.util.spec_from_file_location("agent_ablation_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _evidence(signal: str, decision_time: datetime) -> ProposalEvidence:
    detail = f"{signal}=fixture"
    return ProposalEvidence(
        evidence_id=f"fixture:{signal}",
        signal_id=signal,
        payload_sha256=hashlib.sha256(detail.encode()).hexdigest(),
        available_at=decision_time,
        valid_until=decision_time,
        detail=detail,
    )


def _fixture():
    calendar = pd.bdate_range("2025-01-02", periods=82)
    train_index = calendar[:61]
    embargo_date = calendar[61]
    holding_index = calendar[62:82]
    train_step = np.arange(len(train_index), dtype=float)
    holding_step = np.arange(1, 21, dtype=float)
    train = pd.DataFrame(
        {
            ticker: (20.0 + index) * (1 + train_step * (0.0002 + index * 0.000002))
            for index, ticker in enumerate(ALL_STOCKS)
        },
        index=train_index,
    )
    entry = train.iloc[-1] * 1.001
    entry.name = holding_index[0]
    holding = pd.DataFrame(
        {
            ticker: entry[ticker]
            * (1 + holding_step * (-0.0005 + index * 0.00004))
            for index, ticker in enumerate(ALL_STOCKS)
        },
        index=holding_index,
    )
    base_scores = {
        ticker: 1.5 - index * (1.8 / (len(ALL_STOCKS) - 1))
        for index, ticker in enumerate(ALL_STOCKS)
    }
    decision_time = datetime.combine(
        train_index[-1].date(),
        datetime.min.time().replace(hour=15),
        tzinfo=ZoneInfo("Asia/Shanghai"),
    )
    a0 = [item.ticker for item in select_portfolio(base_scores)]
    alpha_ticker = next(ticker for ticker in reversed(ALL_STOCKS) if ticker not in a0)
    alpha = AgentProposal(
        role="alpha",
        ticker=alpha_ticker,
        action="include",
        adjustment=3,
        confidence="high",
        evidence=(_evidence("momentum_20", decision_time),),
        rationale="fixture alpha",
        valid_from=decision_time,
        valid_until=decision_time,
    )
    risk_ticker = a0[-1]
    risk = AgentProposal(
        role="risk_evidence",
        ticker=risk_ticker,
        action="exclude",
        adjustment=-3,
        confidence="high",
        evidence=(
            _evidence("drawdown", decision_time),
            _evidence("reversal", decision_time),
        ),
        rationale="fixture veto",
        valid_from=decision_time,
        valid_until=decision_time,
    )
    return {
        "base_scores": base_scores,
        "alpha_proposals": (alpha,),
        "risk_proposals": (risk,),
        "train_prices": train,
        "entry_open": entry.reindex(ALL_STOCKS),
        "holding_closes": holding.reindex(columns=ALL_STOCKS),
        "decision_time": decision_time,
        "embargo_date": embargo_date,
        "session_calendar": calendar,
    }


def test_ablation_uses_three_independent_allocations_and_reports_all_metrics():
    module = _load_module()
    inputs = _fixture()
    result = module.evaluate_ablation(**inputs)
    variants = result["variants"]

    assert result["holding_sessions"] == 20
    assert result["promotion_eligible"] is False
    assert len(result["snapshot_sha256"]) == 64
    assert len(result["proposal_bundle_sha256"]) == 64
    assert variants["A0_no_agent"]["tickers"] != variants["A1_alpha_only"]["tickers"]
    assert variants["A1_alpha_only"]["tickers"] != variants["A2_alpha_risk"]["tickers"]
    assert variants["A0_no_agent"]["weights"] != variants["A1_alpha_only"]["weights"]
    assert variants["A1_alpha_only"]["weights"] != variants["A2_alpha_risk"]["weights"]
    for variant in variants.values():
        assert variant["metrics"]["n_trading_days"] == 20
        assert "total_return" in variant["metrics"]
        assert "max_drawdown" in variant["metrics"]
        assert "p10_daily_return" in variant["metrics"]
        assert "utility_return_minus_mdd" in variant["metrics"]
        assert variant["trace"]["selected_after"] == variant["tickers"]
        assert len(variant["trace"]["base_scores"]) == len(ALL_STOCKS)
        assert len(variant["trace"]["adjusted_scores"]) == len(ALL_STOCKS)
        assert len(variant["trace"]["outcomes"]) == variant["trace"]["n_proposals"]


def test_ablation_is_deterministic_on_the_same_frozen_snapshot():
    module = _load_module()
    inputs = _fixture()
    first = module.evaluate_ablation(**inputs)
    second = module.evaluate_ablation(**inputs)
    assert first == second


def test_ablation_rejects_missing_embargo_or_wrong_horizon():
    module = _load_module()
    inputs = _fixture()
    inputs["embargo_date"] = inputs["holding_closes"].index[0]
    with pytest.raises(ValueError, match="canonical|full holding"):
        module.evaluate_ablation(**inputs)

    inputs = _fixture()
    inputs["holding_closes"] = inputs["holding_closes"].iloc[:-1]
    with pytest.raises(ValueError, match="20 sessions"):
        module.evaluate_ablation(**inputs)


def test_ablation_binds_entry_label_and_unique_canonical_sessions():
    module = _load_module()
    inputs = _fixture()
    inputs["entry_open"].name = inputs["train_prices"].index[-1]
    with pytest.raises(ValueError, match="entry_open label"):
        module.evaluate_ablation(**inputs)

    inputs = _fixture()
    duplicate_index = list(inputs["holding_closes"].index)
    duplicate_index[-1] = duplicate_index[-2]
    inputs["holding_closes"].index = duplicate_index
    with pytest.raises(ValueError, match="unique and increasing"):
        module.evaluate_ablation(**inputs)

    inputs = _fixture()
    weekend = pd.Timestamp("2025-03-29")
    calendar = list(inputs["session_calendar"])
    calendar[61] = weekend
    inputs["session_calendar"] = pd.DatetimeIndex(sorted(calendar))
    inputs["embargo_date"] = weekend
    with pytest.raises(ValueError, match="weekend"):
        module.evaluate_ablation(**inputs)


def test_view_adapter_builds_typed_pit_proposals():
    module = _load_module()
    inputs = _fixture()
    decision_time = inputs["decision_time"]
    alpha, risk = module._proposals_from_views(
        {
            "alpha_stocks": [
                {
                    "ticker": ALL_STOCKS[0],
                    "alpha_score": 7,
                    "signals": ["momentum=strong"],
                }
            ]
        },
        {
            "risky_stocks": [
                {
                    "ticker": ALL_STOCKS[1],
                    "risk_score": 8,
                    "warnings": ["drawdown=high", "reversal=weak"],
                }
            ]
        },
        decision_time,
    )
    assert len(alpha) == len(risk) == 1
    assert all(
        isinstance(item, ProposalEvidence)
        for proposal in alpha + risk
        for item in proposal.evidence
    )
    assert alpha[0].valid_from == risk[0].valid_from == decision_time
