"""Fail-closed tests for the point-in-time Agent decision boundary."""

from __future__ import annotations

import hashlib
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from jiuwenswarm.quant.agent_decision import (
    OFFICIAL_SELECTION_POLICY,
    AgentProposal,
    DecisionAssembler,
    ProposalEvidence,
    SelectionPolicy,
    select_portfolio,
)
from jiuwenswarm.quant.stock_pool import STOCK_POOL

NOW = datetime(2026, 8, 6, 16, 0, tzinfo=ZoneInfo("Asia/Shanghai"))


def evidence(
    signal_id: str = "momentum_20",
    *,
    evidence_id: str | None = None,
    available_at: datetime = NOW,
    valid_until: datetime | None = None,
) -> ProposalEvidence:
    detail = f"{signal_id}=test"
    return ProposalEvidence(
        evidence_id=evidence_id or f"ev:{signal_id}",
        signal_id=signal_id,
        payload_sha256=hashlib.sha256(detail.encode()).hexdigest(),
        available_at=available_at,
        valid_until=valid_until or NOW + timedelta(days=1),
        detail=detail,
    )


def proposal(
    *,
    role: str = "alpha",
    ticker: str = "000333.SZ",
    action: str = "include",
    adjustment: int = 1,
    items: tuple[ProposalEvidence, ...] | None = None,
    valid_from: datetime | None = None,
    valid_until: datetime | None = None,
) -> AgentProposal:
    return AgentProposal(
        role=role,
        ticker=ticker,
        action=action,
        adjustment=adjustment,
        confidence="high",
        evidence=items if items is not None else (evidence(),),
        rationale="Bounded deterministic signal.",
        valid_from=valid_from or NOW - timedelta(minutes=1),
        valid_until=valid_until or NOW + timedelta(minutes=1),
    )


class TestProposalSchema:
    def test_evidence_requires_aware_ordered_times_and_payload_hash(self):
        with pytest.raises(ValueError, match="timezone-aware"):
            evidence(available_at=NOW.replace(tzinfo=None))
        with pytest.raises(ValueError, match="64 lowercase"):
            ProposalEvidence("ev", "signal", "BAD", NOW, NOW)
        with pytest.raises(ValueError, match="does not match detail"):
            ProposalEvidence("ev", "signal", "0" * 64, NOW, NOW, "actual")
        with pytest.raises(ValueError, match="after valid_until"):
            evidence(available_at=NOW, valid_until=NOW - timedelta(seconds=1))

    def test_proposal_requires_aware_ordered_validity(self):
        with pytest.raises(ValueError, match="timezone-aware"):
            proposal(valid_from=NOW.replace(tzinfo=None))
        with pytest.raises(ValueError, match="valid_from is after"):
            proposal(
                valid_from=NOW + timedelta(minutes=1),
                valid_until=NOW - timedelta(minutes=1),
            )

    @pytest.mark.parametrize(
        ("kwargs", "message"),
        [
            ({"role": "bull"}, "Invalid role"),
            ({"role": "alpha", "action": "exclude", "adjustment": 0}, "may only"),
            ({"role": "risk_evidence", "action": "include", "adjustment": 0}, "may only"),
            ({"adjustment": 4}, "out of bounds"),
            (
                {"role": "risk_evidence", "action": "reduce", "adjustment": -4},
                "out of bounds",
            ),
        ],
    )
    def test_role_action_and_bounds_fail_closed(self, kwargs, message):
        with pytest.raises(ValueError, match=message):
            proposal(**kwargs)

    def test_nonzero_adjustment_needs_immutable_evidence(self):
        with pytest.raises(ValueError, match="requires at least one"):
            proposal(items=())
        with pytest.raises(ValueError, match="immutable tuple"):
            AgentProposal(
                role="alpha",
                ticker="000333.SZ",
                action="include",
                adjustment=0,
                confidence="low",
                evidence=[],  # type: ignore[arg-type]
                rationale="",
                valid_from=NOW,
                valid_until=NOW,
            )
        with pytest.raises(ValueError, match="every evidence item"):
            AgentProposal(
                role="alpha",
                ticker="000333.SZ",
                action="include",
                adjustment=0,
                confidence="low",
                evidence=(object(),),  # type: ignore[arg-type]
                rationale="",
                valid_from=NOW,
                valid_until=NOW,
            )
        with pytest.raises(ValueError, match="rationale must"):
            AgentProposal(
                role="alpha",
                ticker="000333.SZ",
                action="include",
                adjustment=0,
                confidence="low",
                evidence=(),
                rationale=[],  # type: ignore[arg-type]
                valid_from=NOW,
                valid_until=NOW,
            )

    def test_proposal_and_evidence_are_immutable(self):
        item = evidence()
        candidate = proposal(items=(item,))
        with pytest.raises(FrozenInstanceError):
            candidate.adjustment = 3  # type: ignore[misc]
        with pytest.raises(FrozenInstanceError):
            item.signal_id = "changed"  # type: ignore[misc]


class TestDecisionAssembler:
    def test_decision_clock_and_base_scores_fail_closed(self):
        with pytest.raises(ValueError, match="timezone-aware"):
            DecisionAssembler.assemble({}, [], decision_time=NOW.replace(tzinfo=None))
        for unsafe in (float("nan"), float("inf"), float("-inf"), True, "1"):
            with pytest.raises(ValueError, match="score"):
                DecisionAssembler.assemble(
                    {"000333.SZ": unsafe},  # type: ignore[dict-item]
                    [],
                    decision_time=NOW,
                )

    @pytest.mark.parametrize(
        ("candidate", "reason"),
        [
            (proposal(ticker="UNKNOWN"), "absent from base"),
            (
                proposal(items=(evidence(available_at=NOW + timedelta(seconds=1)),)),
                "future evidence",
            ),
            (
                proposal(
                    items=(
                        evidence(
                            available_at=NOW - timedelta(seconds=2),
                            valid_until=NOW - timedelta(seconds=1),
                        ),
                    )
                ),
                "expired evidence",
            ),
            (
                proposal(
                    valid_from=NOW - timedelta(days=2),
                    valid_until=NOW - timedelta(days=1),
                ),
                "outside validity",
            ),
        ],
    )
    def test_invalid_proposals_are_traced_without_effect(self, candidate, reason):
        base = {"000333.SZ": 1.0}
        trace = DecisionAssembler.assemble(base, [candidate], decision_time=NOW)
        assert dict(trace.adjusted_scores) == base
        assert len(trace.rejected) == 1
        assert reason in next(iter(trace.reject_reasons.values()))

    def test_duplicate_identity_and_under_evidenced_veto_are_rejected(self):
        duplicate = evidence("drawdown", evidence_id="same")
        duplicate_two = evidence("reversal", evidence_id="same")
        candidates = [
            proposal(items=(duplicate, duplicate_two)),
            proposal(
                role="risk_evidence",
                action="exclude",
                adjustment=-3,
                items=(evidence("drawdown"),),
            ),
        ]
        trace = DecisionAssembler.assemble(
            {"000333.SZ": 1.0}, candidates, decision_time=NOW
        )
        assert len(trace.rejected) == 2
        assert len(trace.reject_reasons) == 2
        assert any("duplicate evidence_id" in value for value in trace.reject_reasons.values())
        assert any("two independent" in value for value in trace.reject_reasons.values())

    def test_evidence_identity_cannot_be_reused_across_proposals(self):
        shared = evidence("momentum", evidence_id="shared")
        first = proposal(ticker="000333.SZ", items=(shared,))
        second = proposal(ticker="000651.SZ", items=(shared,))
        trace = DecisionAssembler.assemble(
            {"000333.SZ": 1.0, "000651.SZ": 1.0},
            [second, first],
            decision_time=NOW,
        )
        assert len(trace.accepted) == 1
        assert trace.accepted[0].ticker == "000333.SZ"
        assert "reused across proposals" in next(iter(trace.reject_reasons.values()))

        detail = "same payload with relabelled ids"
        payload_hash = hashlib.sha256(detail.encode()).hexdigest()
        relabelled = tuple(
            ProposalEvidence(
                evidence_id=f"relabeled-{index}",
                signal_id=f"signal-{index}",
                payload_sha256=payload_hash,
                available_at=NOW,
                valid_until=NOW,
                detail=detail,
            )
            for index in range(2)
        )
        trace = DecisionAssembler.assemble(
            {"000333.SZ": 1.0, "000651.SZ": 1.0},
            [
                proposal(ticker="000333.SZ", items=(relabelled[0],)),
                proposal(ticker="000651.SZ", items=(relabelled[1],)),
            ],
            decision_time=NOW,
        )
        assert len(trace.accepted) == 1
        assert "payload reused" in next(iter(trace.reject_reasons.values()))

    def test_relabelled_identical_payloads_do_not_satisfy_veto_independence(self):
        detail = "same underlying provider fact"
        payload_hash = hashlib.sha256(detail.encode()).hexdigest()
        relabelled = tuple(
            ProposalEvidence(
                evidence_id=f"evidence-{index}",
                signal_id=f"claimed-signal-{index}",
                payload_sha256=payload_hash,
                available_at=NOW,
                valid_until=NOW,
                detail=detail,
            )
            for index in range(2)
        )
        veto = proposal(
            role="risk_evidence",
            action="exclude",
            adjustment=-3,
            items=relabelled,
        )
        trace = DecisionAssembler.assemble(
            {"000333.SZ": 1.0}, [veto], decision_time=NOW
        )
        assert trace.accepted == ()
        assert trace.adjusted_scores["000333.SZ"] == 1.0
        assert "independently hashed" in next(iter(trace.reject_reasons.values()))

    def test_independent_veto_excludes_and_does_not_mutate_input(self):
        veto = proposal(
            role="risk_evidence",
            action="exclude",
            adjustment=-3,
            items=(evidence("drawdown"), evidence("reversal")),
        )
        original = veto
        trace = DecisionAssembler.assemble(
            {"000333.SZ": 1.0, "000651.SZ": 0.5}, [veto], decision_time=NOW
        )
        assert trace.adjusted_scores["000333.SZ"] == float("-inf")
        assert trace.accepted == (veto,)
        assert veto is original and veto.adjustment == -3

    def test_adjustments_are_clipped_only_after_immutable_aggregation(self):
        candidates = [
            proposal(items=(evidence("momentum_20", evidence_id="one"),), adjustment=3),
            proposal(items=(evidence("momentum_60", evidence_id="two"),), adjustment=3),
        ]
        trace = DecisionAssembler.assemble(
            {"000333.SZ": 1.0}, candidates, decision_time=NOW
        )
        assert trace.adjusted_scores["000333.SZ"] == 4.0
        assert [item.adjustment for item in candidates] == [3, 3]
        assert len(trace.role_adjustments) == 2

    def test_trace_is_deeply_immutable_and_deterministic(self):
        first = proposal(ticker="000651.SZ", items=(evidence("m1"),))
        second = proposal(ticker="000333.SZ", items=(evidence("m2"),))
        base = {"000651.SZ": 1.0, "000333.SZ": 1.0}
        left = DecisionAssembler.assemble(base, [first, second], decision_time=NOW)
        right = DecisionAssembler.assemble(base, [second, first], decision_time=NOW)
        assert left == right
        assert left.base_ranking == ("000333.SZ", "000651.SZ")
        assert left.selected_before == left.selected_after
        with pytest.raises(TypeError):
            left.base_scores["000333.SZ"] = 99.0  # type: ignore[index]

    def test_trace_records_selection_impact(self):
        policy = SelectionPolicy(top_n=1, min_score=-10.0)
        candidate = proposal(ticker="000651.SZ", adjustment=2)
        trace = DecisionAssembler.assemble(
            {"000333.SZ": 2.0, "000651.SZ": 1.0},
            [candidate],
            decision_time=NOW,
            selection_policy=policy,
        )
        assert trace.selected_before == ("000333.SZ",)
        assert trace.selected_after == ("000651.SZ",)
        assert trace.net_effect("000651.SZ") == 2.0


class TestSharedSelectionPolicy:
    def test_official_policy_is_sector_first_then_score_and_ticker(self):
        scores = {
            ticker: 1.0
            for tickers in STOCK_POOL.values()
            for ticker in tickers
        }
        selected = select_portfolio(scores)
        assert len(selected) == OFFICIAL_SELECTION_POLICY.top_n
        assert len({item.sector for item in selected}) == len(STOCK_POOL)
        assert [item.ticker for item in selected[:6]] == [
            min(tickers) for tickers in STOCK_POOL.values()
        ]

    def test_official_policy_rejects_unknown_and_unsafe_scores(self):
        with pytest.raises(ValueError, match="outside the selection universe"):
            select_portfolio({"UNKNOWN": 1.0})
        with pytest.raises(ValueError, match="score"):
            select_portfolio({"000333.SZ": float("nan")})
        with pytest.raises(ValueError, match="finite"):
            select_portfolio({"000333.SZ": float("-inf")})
