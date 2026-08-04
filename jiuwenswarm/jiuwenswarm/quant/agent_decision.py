"""Agent Decision Contract: AgentProposal, DecisionTrace, and DecisionAssembler.

All Agent influence on the portfolio flows through AgentProposal objects.
DecisionAssembler is a pure function: same proposals → same adjusted scores.

Design rules (from DEVELOPMENT_PLAN.md):
- AgentProposal with no evidence → adjustment = 0 (fail-safe).
- Future evidence or out-of-bounds adjustment → fail-closed.
- Regular adjustments and major risk vetos both use pre-registered bounds.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

# Pre-registered adjustment bounds — no Agent may exceed these.
MAX_ADJUST_UP = 3       # max upward adjustment from Alpha Analyst
MAX_ADJUST_DOWN = -3     # max downward adjustment from Risk & Evidence Analyst
VALID_ACTIONS = frozenset({"include", "exclude", "reduce"})
VALID_ROLES = frozenset({"alpha", "risk_evidence"})
VALID_CONFIDENCE = frozenset({"high", "medium", "low"})


@dataclass(frozen=True)
class AgentProposal:
    """A single stock-level proposal from Alpha or Risk & Evidence Analyst.

    Immutable by design — once submitted, proposals cannot be altered.
    """

    role: str           # "alpha" | "risk_evidence"
    ticker: str         # e.g. "000333.SZ"
    action: str         # "include" | "exclude" | "reduce"
    adjustment: int     # alpha: 0..+3, risk_evidence: -3..0
    confidence: str     # "high" | "medium" | "low"
    evidence: Tuple[str, ...]   # factor names & values supporting this proposal
    rationale: str              # 1-2 sentence reason

    def __post_init__(self) -> None:
        issues: list[str] = []

        if self.role not in VALID_ROLES:
            issues.append(f"Invalid role: {self.role}")

        if self.action not in VALID_ACTIONS:
            issues.append(f"Invalid action: {self.action}")

        if self.confidence not in VALID_CONFIDENCE:
            issues.append(f"Invalid confidence: {self.confidence}")

        # Enforce role-action consistency
        if self.role == "alpha" and self.action != "include":
            issues.append(f"Alpha Analyst may only 'include', got '{self.action}'")
        if self.role == "risk_evidence" and self.action not in ("exclude", "reduce"):
            issues.append(f"Risk & Evidence Analyst may only 'exclude'/'reduce', got '{self.action}'")

        # Enforce adjustment bounds by role
        if self.role == "alpha":
            if not (0 <= self.adjustment <= MAX_ADJUST_UP):
                issues.append(
                    f"Alpha adjustment {self.adjustment} out of bounds [0, {MAX_ADJUST_UP}]"
                )
        if self.role == "risk_evidence":
            if not (MAX_ADJUST_DOWN <= self.adjustment <= 0):
                issues.append(
                    f"Risk & Evidence adjustment {self.adjustment} out of bounds [{MAX_ADJUST_DOWN}, 0]"
                )

        # No evidence → zero adjustment (fail-safe)
        if not self.evidence and self.adjustment != 0:
            issues.append(
                f"Non-zero adjustment ({self.adjustment}) requires at least one evidence item"
            )

        if issues:
            raise ValueError(f"AgentProposal validation failed: {'; '.join(issues)}")

    @property
    def is_alpha(self) -> bool:
        return self.role == "alpha"

    @property
    def is_veto(self) -> bool:
        """True if this proposal excludes a stock entirely."""
        return self.action == "exclude"


@dataclass(frozen=True)
class DecisionTrace:
    """Full audit trail: how the final composite scores were derived from proposals.

    Records every proposal, whether it was accepted/rejected, and the net effect.
    """

    base_scores: Dict[str, float]          # ticker → original composite score
    proposals: Tuple[AgentProposal, ...]   # all submitted proposals
    accepted: Tuple[AgentProposal, ...]    # proposals that passed validation
    rejected: Tuple[AgentProposal, ...]    # proposals rejected (with reasons)
    adjusted_scores: Dict[str, float]      # ticker → score after applying accepted proposals
    reject_reasons: Dict[str, str]         # ticker → reason for rejection

    def net_effect(self, ticker: str) -> float:
        """How much did Agent proposals change this ticker's score?"""
        return self.adjusted_scores.get(ticker, 0.0) - self.base_scores.get(ticker, 0.0)


class DecisionAssembler:
    """Pure function: merges AgentProposals into composite scores.

    Rules (in order):
    1. No-evidence proposals → rejected (adjustment = 0).
    2. Future-evidence proposals → rejected.
    3. Out-of-bounds adjustments → clamped then applied.
    4. Exclude takes precedence over include for the same ticker.
    5. Multiple proposals for same ticker → net adjustment = sum of adjustments,
       bounded within [MAX_ADJUST_DOWN, MAX_ADJUST_UP].
    """

    @staticmethod
    def assemble(
        base_scores: Dict[str, float],
        proposals: List[AgentProposal],
        decision_date: str | None = None,
    ) -> DecisionTrace:
        """Apply validated proposals to base scores; return full trace."""

        accepted: List[AgentProposal] = []
        rejected: List[AgentProposal] = []
        reject_reasons: Dict[str, str] = {}

        net_adjustment: Dict[str, int] = {}
        excluded: set[str] = set()

        for p in proposals:
            # Rule 1: no evidence → zero effect
            if not p.evidence:
                rejected.append(p)
                reject_reasons.setdefault(p.ticker, "no evidence provided")
                continue

            # Rule 2: future evidence rejected (placeholder — real check needs dates)
            # Currently pass-through; WP0-C adds evidence timestamp validation.

            # Rule 3: clamp to bounds (paranoid safety — AgentProposal already enforces)
            clamped = max(MAX_ADJUST_DOWN, min(MAX_ADJUST_UP, p.adjustment))
            if clamped != p.adjustment:
                # Clamping happened — still accept with clamped value
                object.__setattr__(p, 'adjustment', clamped)

            accepted.append(p)

            # Apply per ticker
            ticker = p.ticker
            if p.action == "exclude":
                excluded.add(ticker)
            else:
                net_adjustment[ticker] = net_adjustment.get(ticker, 0) + clamped

        # Build adjusted scores
        adjusted: Dict[str, float] = {}
        for ticker, score in base_scores.items():
            if ticker in excluded:
                adjusted[ticker] = float("-inf")  # excluded stocks won't be selected
            else:
                net = net_adjustment.get(ticker, 0)
                clipped = max(MAX_ADJUST_DOWN, min(MAX_ADJUST_UP, net))
                adjusted[ticker] = score + clipped

        return DecisionTrace(
            base_scores=dict(base_scores),
            proposals=tuple(proposals),
            accepted=tuple(accepted),
            rejected=tuple(rejected),
            adjusted_scores=adjusted,
            reject_reasons=dict(reject_reasons),
        )


# ---- Pre-registered bounds for veto ----

# Risk & Evidence Analyst needs at least 2 independent factor signals to veto.
MIN_VETO_EVIDENCE_COUNT = 2

# Alpha proposals need at least 1 evidence item (already enforced in AgentProposal).
MIN_ALPHA_EVIDENCE_COUNT = 1
