"""Point-in-time Agent proposals and deterministic portfolio selection.

Agent text can only influence scores through immutable, time-bounded proposals.
The production overlay remains separately gated by ``AGENT_OVERLAY_ENABLED``.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from numbers import Real
from types import MappingProxyType

from jiuwenswarm.quant.stock_pool import SECTOR_MAP, STOCK_POOL

MAX_ADJUST_UP = 3
MAX_ADJUST_DOWN = -3
MIN_VETO_EVIDENCE_COUNT = 2
MIN_ALPHA_EVIDENCE_COUNT = 1
VALID_ACTIONS = frozenset({"include", "exclude", "reduce"})
VALID_ROLES = frozenset({"alpha", "risk_evidence"})
VALID_CONFIDENCE = frozenset({"high", "medium", "low"})


def _is_aware(value: object) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )


@dataclass(frozen=True)
class ProposalEvidence:
    """Identity and point-in-time availability of one deterministic signal."""

    evidence_id: str
    signal_id: str
    payload_sha256: str
    available_at: datetime
    valid_until: datetime
    detail: str = ""

    def __post_init__(self) -> None:
        issues: list[str] = []
        if not isinstance(self.evidence_id, str) or not self.evidence_id.strip():
            issues.append("evidence_id must be non-empty")
        if not isinstance(self.signal_id, str) or not self.signal_id.strip():
            issues.append("signal_id must be non-empty")
        if not isinstance(self.payload_sha256, str) or not re.fullmatch(
            r"[0-9a-f]{64}", self.payload_sha256
        ):
            issues.append("payload_sha256 must be 64 lowercase hexadecimal characters")
        if not isinstance(self.detail, str):
            issues.append("detail must be an immutable string")
        elif (
            isinstance(self.payload_sha256, str)
            and re.fullmatch(r"[0-9a-f]{64}", self.payload_sha256)
            and self.payload_sha256
            != hashlib.sha256(self.detail.encode("utf-8")).hexdigest()
        ):
            issues.append("payload_sha256 does not match detail")
        if not _is_aware(self.available_at) or not _is_aware(self.valid_until):
            issues.append("evidence times must be timezone-aware")
        elif self.available_at > self.valid_until:
            issues.append("evidence available_at is after valid_until")
        if issues:
            raise ValueError(f"ProposalEvidence validation failed: {'; '.join(issues)}")


@dataclass(frozen=True)
class AgentProposal:
    """Immutable stock-level proposal from an authorised analyst role."""

    role: str
    ticker: str
    action: str
    adjustment: int
    confidence: str
    evidence: tuple[ProposalEvidence, ...]
    rationale: str
    valid_from: datetime
    valid_until: datetime

    def __post_init__(self) -> None:
        issues: list[str] = []
        if not isinstance(self.role, str) or self.role not in VALID_ROLES:
            issues.append(f"Invalid role: {self.role}")
        if not isinstance(self.ticker, str) or not self.ticker.strip():
            issues.append("ticker must be non-empty")
        if not isinstance(self.action, str) or self.action not in VALID_ACTIONS:
            issues.append(f"Invalid action: {self.action}")
        if not isinstance(self.confidence, str) or self.confidence not in VALID_CONFIDENCE:
            issues.append(f"Invalid confidence: {self.confidence}")
        if not isinstance(self.rationale, str):
            issues.append("rationale must be an immutable string")
        if not isinstance(self.adjustment, int) or isinstance(self.adjustment, bool):
            issues.append("adjustment must be an integer")
        if not isinstance(self.evidence, tuple):
            issues.append("evidence must be an immutable tuple")
        elif not all(isinstance(item, ProposalEvidence) for item in self.evidence):
            issues.append("every evidence item must be ProposalEvidence")
        if not _is_aware(self.valid_from) or not _is_aware(self.valid_until):
            issues.append("proposal validity times must be timezone-aware")
        elif self.valid_from > self.valid_until:
            issues.append("proposal valid_from is after valid_until")

        if self.role == "alpha" and self.action != "include":
            issues.append(f"Alpha Analyst may only 'include', got '{self.action}'")
        if self.role == "risk_evidence" and self.action not in {"exclude", "reduce"}:
            issues.append(
                "Risk & Evidence Analyst may only 'exclude'/'reduce', "
                f"got '{self.action}'"
            )
        if self.role == "alpha" and not 0 <= self.adjustment <= MAX_ADJUST_UP:
            issues.append(
                f"Alpha adjustment {self.adjustment} out of bounds [0, {MAX_ADJUST_UP}]"
            )
        if self.role == "risk_evidence" and not MAX_ADJUST_DOWN <= self.adjustment <= 0:
            issues.append(
                "Risk & Evidence adjustment "
                f"{self.adjustment} out of bounds [{MAX_ADJUST_DOWN}, 0]"
            )
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
        return self.action == "exclude"


@dataclass(frozen=True)
class SelectionPolicy:
    """Server-owned deterministic stock selection policy."""

    top_n: int = 15
    min_score: float = -0.5
    sector_groups: tuple[tuple[str, tuple[str, ...]], ...] = ()
    reject_unmapped: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.top_n, int) or isinstance(self.top_n, bool) or self.top_n <= 0:
            raise ValueError("top_n must be a positive integer")
        if not math.isfinite(self.min_score):
            raise ValueError("min_score must be finite")


OFFICIAL_SELECTION_POLICY = SelectionPolicy(
    sector_groups=tuple((sector, tuple(tickers)) for sector, tickers in STOCK_POOL.items()),
    reject_unmapped=True,
)
RANK_ONLY_SELECTION_POLICY = SelectionPolicy()


@dataclass(frozen=True)
class SelectedStock:
    ticker: str
    composite: float
    sector: str


def _normalise_scores(
    scores: Mapping[str, Real],
    *,
    allow_negative_infinity: bool,
) -> dict[str, float]:
    normalised: dict[str, float] = {}
    for ticker, raw_score in scores.items():
        if not isinstance(ticker, str) or not ticker.strip():
            raise ValueError("score tickers must be non-empty strings")
        if isinstance(raw_score, bool) or not isinstance(raw_score, Real):
            raise ValueError(f"score for {ticker} must be a real number")
        score = float(raw_score)
        if not math.isfinite(score) and not (
            allow_negative_infinity and score == float("-inf")
        ):
            raise ValueError(f"score for {ticker} must be finite")
        normalised[ticker] = score
    return normalised


def _score_ranking(scores: Mapping[str, float]) -> tuple[str, ...]:
    return tuple(sorted(scores, key=lambda ticker: (-scores[ticker], ticker)))


def _select_portfolio(
    scores: Mapping[str, Real],
    policy: SelectionPolicy,
    *,
    excluded: frozenset[str],
) -> tuple[SelectedStock, ...]:
    values = _normalise_scores(
        {ticker: score for ticker, score in scores.items() if ticker not in excluded},
        allow_negative_infinity=False,
    )
    official_sectors = {
        ticker: sector
        for sector, tickers in policy.sector_groups
        for ticker in tickers
    }
    if policy.reject_unmapped:
        unknown = sorted(set(values) - set(official_sectors))
        if unknown:
            raise ValueError(f"scores contain tickers outside the selection universe: {unknown}")

    ranking = _score_ranking(values)
    selected: list[SelectedStock] = []
    selected_set: set[str] = set()

    for sector, sector_tickers in policy.sector_groups:
        allowed = set(sector_tickers)
        for ticker in ranking:
            score = values[ticker]
            if ticker in allowed and score > policy.min_score:
                selected.append(SelectedStock(ticker, score, sector))
                selected_set.add(ticker)
                break

    for ticker in ranking:
        if len(selected) >= policy.top_n:
            break
        score = values[ticker]
        if ticker in selected_set or score <= policy.min_score:
            continue
        selected.append(
            SelectedStock(
                ticker=ticker,
                composite=score,
                sector=official_sectors.get(ticker, SECTOR_MAP.get(ticker, "unmapped")),
            )
        )
        selected_set.add(ticker)
    return tuple(selected)


def select_portfolio(
    scores: Mapping[str, Real],
    policy: SelectionPolicy = OFFICIAL_SELECTION_POLICY,
) -> tuple[SelectedStock, ...]:
    """Select finite external scores for both direct and formal paths."""

    return _select_portfolio(scores, policy, excluded=frozenset())


@dataclass(frozen=True)
class ProposalOutcome:
    proposal: AgentProposal
    accepted: bool
    reason: str | None
    applied_adjustment: int


@dataclass(frozen=True)
class RoleAdjustment:
    role: str
    ticker: str
    action: str
    adjustment: int


@dataclass(frozen=True)
class DecisionTrace:
    """Deeply immutable audit trail for one decision-time assembly."""

    decision_time: datetime
    base_scores: Mapping[str, float]
    proposals: tuple[AgentProposal, ...]
    outcomes: tuple[ProposalOutcome, ...]
    adjusted_scores: Mapping[str, float]
    base_ranking: tuple[str, ...]
    adjusted_ranking: tuple[str, ...]
    selected_before: tuple[str, ...]
    selected_after: tuple[str, ...]
    role_adjustments: tuple[RoleAdjustment, ...]
    reject_reasons: Mapping[str, str]

    @property
    def accepted(self) -> tuple[AgentProposal, ...]:
        return tuple(outcome.proposal for outcome in self.outcomes if outcome.accepted)

    @property
    def rejected(self) -> tuple[AgentProposal, ...]:
        return tuple(outcome.proposal for outcome in self.outcomes if not outcome.accepted)

    def net_effect(self, ticker: str) -> float:
        if ticker not in self.base_scores:
            return 0.0
        return self.adjusted_scores[ticker] - self.base_scores[ticker]


def _proposal_sort_key(proposal: AgentProposal) -> tuple[object, ...]:
    return (
        proposal.ticker,
        proposal.role,
        proposal.action,
        proposal.adjustment,
        tuple(
            (
                evidence.evidence_id,
                evidence.signal_id,
                evidence.payload_sha256,
                evidence.available_at.isoformat(),
                evidence.valid_until.isoformat(),
            )
            for evidence in proposal.evidence
        ),
        proposal.confidence,
        proposal.rationale,
        proposal.valid_from.isoformat(),
        proposal.valid_until.isoformat(),
    )


def _proposal_rejection(proposal: AgentProposal, decision_time: datetime) -> str | None:
    if not proposal.evidence:
        return "no evidence provided"
    evidence_ids = [evidence.evidence_id for evidence in proposal.evidence]
    if len(evidence_ids) != len(set(evidence_ids)):
        return "duplicate evidence_id"
    if not proposal.valid_from <= decision_time <= proposal.valid_until:
        return "proposal outside validity period"
    for evidence in proposal.evidence:
        if evidence.available_at > decision_time:
            return f"future evidence: {evidence.evidence_id}"
        if evidence.valid_until < decision_time:
            return f"expired evidence: {evidence.evidence_id}"
    if proposal.is_veto:
        independent_signals = {evidence.signal_id for evidence in proposal.evidence}
        independent_payloads = {
            evidence.payload_sha256 for evidence in proposal.evidence
        }
        if (
            len(independent_signals) < MIN_VETO_EVIDENCE_COUNT
            or len(independent_payloads) < MIN_VETO_EVIDENCE_COUNT
        ):
            return "veto requires two independently hashed signal payloads"
    return None


class DecisionAssembler:
    """Fail-closed pure merger of bounded point-in-time proposals."""

    @staticmethod
    def assemble(
        base_scores: Mapping[str, Real],
        proposals: Iterable[AgentProposal],
        *,
        decision_time: datetime,
        selection_policy: SelectionPolicy = RANK_ONLY_SELECTION_POLICY,
    ) -> DecisionTrace:
        if not _is_aware(decision_time):
            raise ValueError("decision_time must be timezone-aware")
        base = _normalise_scores(base_scores, allow_negative_infinity=False)
        ordered_proposals = tuple(sorted(tuple(proposals), key=_proposal_sort_key))
        outcomes: list[ProposalOutcome] = []
        role_adjustments: list[RoleAdjustment] = []
        reject_reasons: dict[str, str] = {}
        net_adjustment: dict[str, int] = {}
        excluded: set[str] = set()
        claimed_evidence_ids: set[str] = set()
        claimed_payload_hashes: set[str] = set()

        for index, proposal in enumerate(ordered_proposals):
            reason = None
            if proposal.ticker not in base:
                reason = "ticker absent from base scores"
            else:
                reason = _proposal_rejection(proposal, decision_time)
            proposal_evidence_ids = {
                evidence.evidence_id for evidence in proposal.evidence
            }
            proposal_payload_hashes = {
                evidence.payload_sha256 for evidence in proposal.evidence
            }
            if reason is None and claimed_evidence_ids.intersection(proposal_evidence_ids):
                reason = "evidence_id reused across proposals"
            if reason is None and claimed_payload_hashes.intersection(
                proposal_payload_hashes
            ):
                reason = "evidence payload reused across proposals"
            if reason is not None:
                outcomes.append(ProposalOutcome(proposal, False, reason, 0))
                reject_reasons[
                    f"{index}:{proposal.role}:{proposal.ticker}"
                ] = reason
                continue

            claimed_evidence_ids.update(proposal_evidence_ids)
            claimed_payload_hashes.update(proposal_payload_hashes)
            outcomes.append(
                ProposalOutcome(proposal, True, None, proposal.adjustment)
            )
            role_adjustments.append(
                RoleAdjustment(
                    proposal.role,
                    proposal.ticker,
                    proposal.action,
                    proposal.adjustment,
                )
            )
            if proposal.is_veto:
                excluded.add(proposal.ticker)
            else:
                net_adjustment[proposal.ticker] = (
                    net_adjustment.get(proposal.ticker, 0) + proposal.adjustment
                )

        adjusted: dict[str, float] = {}
        for ticker, score in base.items():
            if ticker in excluded:
                adjusted[ticker] = float("-inf")
                continue
            clipped = max(
                MAX_ADJUST_DOWN,
                min(MAX_ADJUST_UP, net_adjustment.get(ticker, 0)),
            )
            adjusted[ticker] = score + clipped

        before = _select_portfolio(base, selection_policy, excluded=frozenset())
        after = _select_portfolio(
            adjusted,
            selection_policy,
            excluded=frozenset(excluded),
        )
        return DecisionTrace(
            decision_time=decision_time,
            base_scores=MappingProxyType(dict(sorted(base.items()))),
            proposals=ordered_proposals,
            outcomes=tuple(outcomes),
            adjusted_scores=MappingProxyType(dict(sorted(adjusted.items()))),
            base_ranking=_score_ranking(base),
            adjusted_ranking=_score_ranking(adjusted),
            selected_before=tuple(item.ticker for item in before),
            selected_after=tuple(item.ticker for item in after),
            role_adjustments=tuple(role_adjustments),
            reject_reasons=MappingProxyType(reject_reasons),
        )
