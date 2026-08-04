"""Tests for AgentProposal, DecisionTrace, and DecisionAssembler (WP0-B)."""

from __future__ import annotations

import pytest

from jiuwenswarm.quant.agent_decision import (
    AgentProposal,
    DecisionAssembler,
)


class TestAgentProposal:
    """AgentProposal validation and immutability."""

    def test_valid_alpha_proposal(self):
        p = AgentProposal(
            role="alpha",
            ticker="000333.SZ",
            action="include",
            adjustment=2,
            confidence="high",
            evidence=("momentum_20=+0.15", "volume_corr=+0.35"),
            rationale="Strong trend with volume confirmation.",
        )
        assert p.is_alpha
        assert not p.is_veto
        assert p.adjustment == 2

    def test_valid_risk_veto_proposal(self):
        p = AgentProposal(
            role="risk_evidence",
            ticker="600519.SH",
            action="exclude",
            adjustment=-3,
            confidence="high",
            evidence=("max_drawdown=-0.35", "reversal_5=-0.08"),
            rationale="Extreme drawdown + short-term weakness — exclude.",
        )
        assert not p.is_alpha
        assert p.is_veto
        assert p.adjustment == -3

    def test_valid_risk_reduce_proposal(self):
        p = AgentProposal(
            role="risk_evidence",
            ticker="600036.SH",
            action="reduce",
            adjustment=-1,
            confidence="medium",
            evidence=("max_drawdown=-0.30", "volume_corr=-0.15"),
            rationale="Elevated drawdown with divergence — reduce.",
        )
        assert p.action == "reduce"
        assert not p.is_veto

    def test_alpha_cannot_exclude(self):
        with pytest.raises(ValueError, match="may only 'include'"):
            AgentProposal(
                role="alpha",
                ticker="000333.SZ",
                action="exclude",
                adjustment=0,
                confidence="high",
                evidence=(),
                rationale="",
            )

    def test_risk_cannot_include(self):
        with pytest.raises(ValueError, match="may only 'exclude'/'reduce'"):
            AgentProposal(
                role="risk_evidence",
                ticker="000333.SZ",
                action="include",
                adjustment=0,
                confidence="medium",
                evidence=(),
                rationale="",
            )

    def test_alpha_adjustment_out_of_bounds(self):
        with pytest.raises(ValueError, match="out of bounds"):
            AgentProposal(
                role="alpha",
                ticker="000333.SZ",
                action="include",
                adjustment=5,  # max is 3
                confidence="high",
                evidence=("mom=0.10",),
                rationale="",
            )

    def test_risk_adjustment_out_of_bounds(self):
        with pytest.raises(ValueError, match="out of bounds"):
            AgentProposal(
                role="risk_evidence",
                ticker="000333.SZ",
                action="reduce",
                adjustment=-5,  # min is -3
                confidence="high",
                evidence=("max_dd=-0.30", "rev=-0.05"),
                rationale="",
            )

    def test_nonzero_adjustment_requires_evidence(self):
        with pytest.raises(ValueError, match="requires at least one evidence"):
            AgentProposal(
                role="alpha",
                ticker="000333.SZ",
                action="include",
                adjustment=1,
                confidence="medium",
                evidence=(),
                rationale="No evidence provided.",
            )

    def test_zero_adjustment_without_evidence_ok(self):
        """Zero adjustment without evidence is allowed (no-op proposal)."""
        p = AgentProposal(
            role="alpha",
            ticker="000333.SZ",
            action="include",
            adjustment=0,
            confidence="low",
            evidence=(),
            rationale="No strong signal.",
        )
        assert p.adjustment == 0

    def test_invalid_role_rejected(self):
        with pytest.raises(ValueError, match="Invalid role"):
            AgentProposal(
                role="bull",  # old role name — must fail
                ticker="000333.SZ",
                action="include",
                adjustment=1,
                confidence="high",
                evidence=("mom=0.10",),
                rationale="",
            )

    def test_immutable(self):
        p = AgentProposal(
            role="alpha",
            ticker="000333.SZ",
            action="include",
            adjustment=1,
            confidence="high",
            evidence=("mom=0.10",),
            rationale="Good.",
        )
        with pytest.raises(Exception):
            p.adjustment = 3  # type: ignore[misc]


class TestDecisionAssembler:
    """DecisionAssembler pure-function properties."""

    def test_no_proposals_preserves_scores(self):
        base = {"A": 1.0, "B": 0.5, "C": -0.2}
        trace = DecisionAssembler.assemble(base, [])
        assert trace.adjusted_scores == base
        assert len(trace.accepted) == 0
        assert len(trace.rejected) == 0

    def test_no_evidence_proposal_rejected(self):
        base = {"A": 1.0}
        p = AgentProposal(
            role="alpha",
            ticker="A",
            action="include",
            adjustment=0,
            confidence="low",
            evidence=(),
            rationale="No evidence.",
        )
        trace = DecisionAssembler.assemble(base, [p])
        # No-evidence proposals are rejected regardless of adjustment value
        assert len(trace.rejected) == 1
        assert len(trace.accepted) == 0
        assert trace.adjusted_scores["A"] == 1.0  # unchanged

    def test_alpha_proposal_increases_score(self):
        base = {"A": 1.0, "B": 0.5}
        p = AgentProposal(
            role="alpha",
            ticker="A",
            action="include",
            adjustment=2,
            confidence="high",
            evidence=("momentum_20=+0.15",),
            rationale="Strong trend.",
        )
        trace = DecisionAssembler.assemble(base, [p])
        assert trace.adjusted_scores["A"] == 3.0  # 1.0 + 2
        assert trace.adjusted_scores["B"] == 0.5  # unchanged

    def test_risk_proposal_decreases_score(self):
        base = {"A": 1.0}
        p = AgentProposal(
            role="risk_evidence",
            ticker="A",
            action="reduce",
            adjustment=-2,
            confidence="high",
            evidence=("max_drawdown=-0.35", "reversal_5=-0.08"),
            rationale="High risk.",
        )
        trace = DecisionAssembler.assemble(base, [p])
        assert trace.adjusted_scores["A"] == -1.0  # 1.0 - 2

    def test_exclude_sets_negative_infinity(self):
        base = {"A": 1.0, "B": 0.5}
        p = AgentProposal(
            role="risk_evidence",
            ticker="A",
            action="exclude",
            adjustment=-3,
            confidence="high",
            evidence=("max_drawdown=-0.40", "reversal_5=-0.10"),
            rationale="Critical risk — exclude.",
        )
        trace = DecisionAssembler.assemble(base, [p])
        assert trace.adjusted_scores["A"] == float("-inf")
        assert trace.adjusted_scores["B"] == 0.5

    def test_multiple_proposals_net_adjustment(self):
        base = {"A": 1.0}
        p1 = AgentProposal(
            role="alpha",
            ticker="A",
            action="include",
            adjustment=2,
            confidence="high",
            evidence=("momentum_20=+0.15",),
            rationale="Strong trend.",
        )
        p2 = AgentProposal(
            role="risk_evidence",
            ticker="A",
            action="reduce",
            adjustment=-1,
            confidence="medium",
            evidence=("max_drawdown=-0.25", "volume_corr=-0.10"),
            rationale="Moderate risk.",
        )
        trace = DecisionAssembler.assemble(base, [p1, p2])
        assert trace.adjusted_scores["A"] == 2.0  # 1.0 + 2 - 1

    def test_exclude_takes_precedence(self):
        base = {"A": 1.0}
        p_include = AgentProposal(
            role="alpha",
            ticker="A",
            action="include",
            adjustment=3,
            confidence="high",
            evidence=("momentum_20=+0.20",),
            rationale="Very strong.",
        )
        p_exclude = AgentProposal(
            role="risk_evidence",
            ticker="A",
            action="exclude",
            adjustment=-3,
            confidence="high",
            evidence=("max_drawdown=-0.45", "reversal_5=-0.12"),
            rationale="Too risky.",
        )
        trace = DecisionAssembler.assemble(base, [p_include, p_exclude])
        assert trace.adjusted_scores["A"] == float("-inf")

    def test_determinism(self):
        base = {"A": 1.0, "B": 0.5, "C": -0.2}
        p = AgentProposal(
            role="alpha",
            ticker="A",
            action="include",
            adjustment=1,
            confidence="high",
            evidence=("mom=0.10",),
            rationale="",
        )
        t1 = DecisionAssembler.assemble(base, [p])
        t2 = DecisionAssembler.assemble(base, [p])
        assert t1.adjusted_scores == t2.adjusted_scores
        assert t1.accepted == t2.accepted

    def test_net_effect_tracks_delta(self):
        base = {"A": 1.0}
        p = AgentProposal(
            role="alpha",
            ticker="A",
            action="include",
            adjustment=1,
            confidence="medium",
            evidence=("mom=0.05",),
            rationale="",
        )
        trace = DecisionAssembler.assemble(base, [p])
        assert trace.net_effect("A") == 1.0
        assert trace.net_effect("B") == 0.0  # not in base


class TestVetoEvidenceRequirement:
    """Risk & Evidence veto requires >= 2 independent factor signals."""

    def test_single_evidence_veto_allowed_in_proposal(self):
        """AgentProposal allows 1 evidence — it's the assembler's job to weight it.
        The MIN_VETO_EVIDENCE_COUNT is a guideline for the Risk & Evidence Analyst
        persona, enforced by the prompt, not by code at the AgentProposal level."""
        # This is valid at the schema level — prompt enforces the 2-evidence guideline
        p = AgentProposal(
            role="risk_evidence",
            ticker="000333.SZ",
            action="reduce",
            adjustment=-1,
            confidence="medium",
            evidence=("max_drawdown=-0.30",),
            rationale="Single evidence reduce.",
        )
        assert len(p.evidence) == 1
        # But the persona says >= 2 for exclude, >= 1 for reduce is acceptable
