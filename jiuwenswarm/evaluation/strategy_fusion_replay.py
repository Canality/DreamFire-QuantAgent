"""WP1-E3-R1 research-only bounded strategy-slot fusion over accepted E2C replay evidence.

Research-only, deterministic, fail-closed strategy-slot fusion.  The module
consumes the accepted E2C replay evidence (either the untracked
``output/replay/strategy_pool_replay.json`` artifact or a deterministic
regeneration through the public loader oracle) and, per decision date, creates
exactly one proposal bundle with at most one bounded research-only model call per
Alpha/Risk role.  The model returns ONLY typed strategy-level signals over
globally eligible slot IDs plus PIT EvidenceRef IDs and rationale; every numeric
delta, L1/veto/normalisation and final constraint is produced and re-asserted by
server-owned deterministic code.

Global eligibility is a module-level constant: exactly ``production_six_factor``
and ``t2_comparator``.  The three trend slots and ``similar_market_blend`` are
globally excluded and can never be revived by any per-window status or Agent.

This module is RESEARCH_ONLY.  It is never imported by production, direct/formal
or RPC/E2E code, and it configures no model credentials in this phase.  The model
call is an injected callable so the machinery is fully testable offline.

Model inputs are strictly point-in-time: the per-decision candidate digest and
the PIT EvidenceRef inventory only contain windows whose exit session is strictly
before that decision, so realised return/drawdown from any later or in-flight
window can never reach the model or the assembler for an earlier decision.  The
decision-scoped slot ``status`` is a fixed outcome-free eligibility label
(``PIT_ELIGIBILITY_STATUS``); it never carries the whole-replay E2C verdict
(OK/QUALIFIED/DOES_NOT_QUALIFY/...), which would be a future-derived conclusion
for an earlier decision.

Frozen identity constants mirror the accepted location.json revision 3:
``artifact_sha256`` = b45fbaeb..., ``inventory_hash`` = 2516d8a7..., decision set =
the 12 non-overlapping matured windows.  ``load_e2c_evidence`` re-verifies the
whole-artifact hash, the inventory hash and every per-window hash and fails closed
on any tamper.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import math
import re
import sys
from collections.abc import Iterable, Mapping
from concurrent.futures import ThreadPoolExecutor, TimeoutError as _FutureTimeout
from dataclasses import dataclass
from datetime import date, datetime, time
from numbers import Real
from pathlib import Path
from types import MappingProxyType
from zoneinfo import ZoneInfo

_REPO_ROOT = Path(__file__).resolve().parents[2]
_INNER_PKG_PARENT = _REPO_ROOT / "jiuwenswarm"
if str(_INNER_PKG_PARENT) not in sys.path:
    sys.path.insert(0, str(_INNER_PKG_PARENT))

_SH = ZoneInfo("Asia/Shanghai")

# ---------------------------------------------------------------------------
# Global eligibility (frozen verdicts; trends and similar blend can never be
# revived by any per-window status or by an Agent).
# ---------------------------------------------------------------------------

FALLBACK_SLOT = "production_six_factor"
ELIGIBLE_SLOTS = ("production_six_factor", "t2_comparator")
GLOBALLY_EXCLUDED_SLOTS = (
    "trend_short_5_10_20",
    "trend_medium_20_60",
    "trend_long_120_250",
    "similar_market_blend",
)

# Outcome-free, pre-replay eligibility label used in decision-scoped (PIT)
# summaries.  A decision-scoped summary must never carry a whole-replay E2C
# verdict (OK/QUALIFIED/DOES_NOT_QUALIFY/...): that is a future-derived
# conclusion formed by the completed replay and is prohibited inside an earlier
# decision's model input.  Eligibility is a global constant frozen before
# replay, so this label is safe to expose and independent of window data.
PIT_ELIGIBILITY_STATUS = "ELIGIBLE"

VALID_ROLES = ("alpha", "risk_evidence")
ALPHA_SIGNALS = ("strengthen", "weaken", "hold")
RISK_SIGNALS = ("reduce", "veto", "hold")
VALID_CONFIDENCE = ("high", "medium", "low")

MAX_ALPHA_SLOT_DELTA = 0.10
MAX_ALPHA_TOTAL_L1 = 0.20
MIN_VETO_EVIDENCE_COUNT = 2
MAX_NON_FALLBACK_VETOES = 1

PER_ROLE_TIMEOUT_SECONDS = 45.0
MAX_INPUT_TOKENS = 4000
MAX_OUTPUT_TOKENS = 800

# Frozen server-owned signal -> delta map (location.json revision 3).
ALPHA_DELTA_MAP: dict[tuple[str, str], float] = {
    ("strengthen", "high"): 0.10,
    ("strengthen", "medium"): 0.05,
    ("strengthen", "low"): 0.02,
    ("weaken", "high"): -0.10,
    ("weaken", "medium"): -0.05,
    ("weaken", "low"): -0.02,
    ("hold", "high"): 0.0,
    ("hold", "medium"): 0.0,
    ("hold", "low"): 0.0,
}
RISK_DELTA_MAP: dict[tuple[str, str], float] = {
    ("reduce", "high"): -0.10,
    ("reduce", "medium"): -0.05,
    ("reduce", "low"): -0.02,
    ("veto", "high"): 0.0,  # veto is an exclusion, not a delta
    ("veto", "medium"): 0.0,
    ("veto", "low"): 0.0,
    ("hold", "high"): 0.0,
    ("hold", "medium"): 0.0,
    ("hold", "low"): 0.0,
}

# Version strings bound into the joint identity hash before any outer evaluation.
MODEL_VERSION = "wp1e3-r1-model-2026-08-12"
PROMPT_VERSION = "wp1e3-r1-prompt-2026-08-12"
PROPOSAL_SCHEMA_VERSION = "wp1e3-r1-proposal-schema-2026-08-12"
SIGNAL_TO_DELTA_MAP_VERSION = "wp1e3-r1-signal-delta-map-2026-08-12"
ASSEMBLER_VERSION = "wp1e3-r1-assembler-2026-08-12"
GENERATOR_CONFIG_VERSION = "wp1e3-r1-generator-config-2026-08-12"

# Frozen E2C oracle identity (accepted WP1-E2C-R1 artifact).
EXPECTED_E2C_ARTIFACT_SHA256 = (
    "b45fbaebb606f23af41734e133130920b2afb57834f2262297411db96f40e9f5"
)
EXPECTED_E2C_INVENTORY_HASH = (
    "2516d8a7d0e76729ba1a9ee7705b9e00b985f6ec89b2cb88167b96f3b6eea922"
)
DEFAULT_E2C_ARTIFACT_PATH = _REPO_ROOT / "output" / "replay" / "strategy_pool_replay.json"

# ---------------------------------------------------------------------------
# Deterministic serialization / audit hashes (mirrors strategy_pool_replay).
# ---------------------------------------------------------------------------


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


def _estimate_tokens(text: str) -> int:
    """Deterministic token-count proxy (chars / 4); used only for the budgets."""
    return max(1, len(text) // 4)


def _is_aware(value: object) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )


def _decision_time(decision_date: str) -> datetime:
    return datetime.combine(date.fromisoformat(decision_date), time(15, 0), tzinfo=_SH)


def _default_base_state() -> dict[str, float]:
    """A0 baseline: full allocation to the production hard fallback."""
    return {FALLBACK_SLOT: 1.0, "t2_comparator": 0.0}


# ---------------------------------------------------------------------------
# PIT evidence refs and typed strategy proposals.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PITEvidenceRef:
    """Server-owned point-in-time availability of one deterministic signal."""

    evidence_id: str
    signal_id: str
    available_at: datetime
    valid_until: datetime

    def __post_init__(self) -> None:
        issues: list[str] = []
        if not isinstance(self.evidence_id, str) or not self.evidence_id.strip():
            issues.append("evidence_id must be non-empty")
        if not isinstance(self.signal_id, str) or not self.signal_id.strip():
            issues.append("signal_id must be non-empty")
        if not _is_aware(self.available_at) or not _is_aware(self.valid_until):
            issues.append("evidence times must be timezone-aware")
        elif self.available_at > self.valid_until:
            issues.append("evidence available_at is after valid_until")
        if issues:
            raise ValueError(f"PITEvidenceRef validation failed: {'; '.join(issues)}")


@dataclass(frozen=True)
class StrategyProposal:
    """Immutable strategy-slot proposal from an authorised analyst role.

    ``evidence`` is a tuple of PIT EvidenceRef IDs (server-side availability is
    resolved by the assembler).  Shape validation rejects any non-schema field
    and any slot outside the globally eligible set.
    """

    role: str
    slot: str
    signal: str
    confidence: str
    evidence: tuple[str, ...]
    rationale: str
    valid_from: datetime
    valid_until: datetime

    def __post_init__(self) -> None:
        issues: list[str] = []
        if not isinstance(self.role, str) or self.role not in VALID_ROLES:
            issues.append(f"invalid role: {self.role}")
        if not isinstance(self.slot, str) or self.slot not in ELIGIBLE_SLOTS:
            issues.append(f"slot not globally eligible: {self.slot}")
        allowed_signals = ALPHA_SIGNALS if self.role == "alpha" else RISK_SIGNALS
        if not isinstance(self.signal, str) or self.signal not in allowed_signals:
            issues.append(f"invalid signal for {self.role}: {self.signal}")
        if not isinstance(self.confidence, str) or self.confidence not in VALID_CONFIDENCE:
            issues.append(f"invalid confidence: {self.confidence}")
        if not isinstance(self.evidence, tuple) or not all(
            isinstance(item, str) and item.strip() for item in self.evidence
        ):
            issues.append("evidence must be a tuple of non-empty IDs")
        elif len(self.evidence) != len(set(self.evidence)):
            issues.append("duplicate evidence_id")
        if not isinstance(self.rationale, str) or not self.rationale.strip():
            issues.append("rationale must be a non-empty string")
        if not _is_aware(self.valid_from) or not _is_aware(self.valid_until):
            issues.append("validity times must be timezone-aware")
        elif self.valid_from > self.valid_until:
            issues.append("valid_from is after valid_until")
        if self.signal != "hold" and not self.evidence:
            issues.append("non-hold signal requires at least one evidence ID")
        if issues:
            raise ValueError(f"StrategyProposal validation failed: {'; '.join(issues)}")


class RoleOutputError(Exception):
    """Raised when a role's model output violates the frozen output schema."""


_ALLOWED_OUTPUT_FIELDS = frozenset({"slot", "signal", "confidence", "evidence_ids", "rationale"})


def _parse_item(role: str, item: object, index: int, decision_time: datetime) -> StrategyProposal:
    if not isinstance(item, dict):
        raise RoleOutputError(f"item {index} is not an object")
    extra = set(item) - _ALLOWED_OUTPUT_FIELDS
    if extra:
        raise RoleOutputError(f"item {index} has non-schema fields: {sorted(extra)}")
    missing = _ALLOWED_OUTPUT_FIELDS - set(item)
    if missing:
        raise RoleOutputError(f"item {index} is missing fields: {sorted(missing)}")
    slot = item["slot"]
    if slot not in ELIGIBLE_SLOTS:
        raise RoleOutputError(f"item {index} targets non-eligible slot: {slot!r}")
    signal = item["signal"]
    allowed_signals = ALPHA_SIGNALS if role == "alpha" else RISK_SIGNALS
    if signal not in allowed_signals:
        raise RoleOutputError(f"item {index} invalid signal for {role}: {signal!r}")
    confidence = item["confidence"]
    if confidence not in VALID_CONFIDENCE:
        raise RoleOutputError(f"item {index} invalid confidence: {confidence!r}")
    evidence_ids = item["evidence_ids"]
    if not isinstance(evidence_ids, list) or not all(
        isinstance(item_id, str) and item_id.strip() for item_id in evidence_ids
    ):
        raise RoleOutputError(
            f"item {index} evidence_ids must be a list of non-empty strings"
        )
    rationale = item["rationale"]
    if not isinstance(rationale, str) or not rationale.strip():
        raise RoleOutputError(f"item {index} rationale must be a non-empty string")
    try:
        return StrategyProposal(
            role=role,
            slot=slot,
            signal=signal,
            confidence=confidence,
            evidence=tuple(evidence_ids),
            rationale=rationale,
            valid_from=decision_time,
            valid_until=decision_time,
        )
    except ValueError as exc:
        raise RoleOutputError(f"item {index} invalid: {exc}") from exc


def parse_role_output(
    role: str, raw_text: str, decision_time: datetime
) -> tuple[StrategyProposal, ...]:
    """Strictly parse one role's model output into typed strategy proposals.

    Any schema violation (malformed JSON, non-schema field, prohibited numeric
    value, unknown or globally-excluded slot, wrong-role signal, bad types)
    raises :class:`RoleOutputError` so the caller drops the whole role and
    preserves A0.
    """
    if role not in VALID_ROLES:
        raise ValueError(f"invalid role: {role}")
    if not _is_aware(decision_time):
        raise ValueError("decision_time must be timezone-aware")
    try:
        data = json.loads(raw_text)
    except (json.JSONDecodeError, TypeError) as exc:
        raise RoleOutputError(f"malformed JSON model output: {exc}") from exc
    if not isinstance(data, list):
        raise RoleOutputError("model output must be a JSON array")
    return tuple(
        _parse_item(role, item, index, decision_time)
        for index, item in enumerate(data)
    )


def server_signal_to_delta(role: str, signal: str, confidence: str) -> float:
    table = ALPHA_DELTA_MAP if role == "alpha" else RISK_DELTA_MAP
    try:
        return table[(signal, confidence)]
    except KeyError as exc:
        raise ValueError(
            f"no server delta for {role}/{signal}/{confidence}"
        ) from exc


def _bounded_delta(delta: object) -> float:
    if isinstance(delta, bool) or not isinstance(delta, Real):
        raise ValueError("delta must be a real number")
    value = float(delta)
    if not math.isfinite(value):
        raise ValueError("delta must be finite")
    if abs(value) > MAX_ALPHA_SLOT_DELTA:
        raise ValueError(
            f"delta |{value}| exceeds {MAX_ALPHA_SLOT_DELTA}"
        )
    return value


# ---------------------------------------------------------------------------
# E2C evidence verification, summaries and model input construction.
# ---------------------------------------------------------------------------


def verify_e2c_payload(payload: object) -> bool:
    """Recompute per-window and whole-artifact hashes; False on any tamper."""
    if not isinstance(payload, dict):
        return False
    deterministic = payload.get("deterministic")
    if not isinstance(deterministic, dict):
        return False
    for window in deterministic.get("windows", []):
        if not isinstance(window, dict):
            return False
        content = {key: value for key, value in window.items() if key != "window_hash"}
        if sha256_hex(canonical_json(content)) != window.get("window_hash"):
            return False
    inventory_hash = deterministic.get("inventory_hash")
    if not isinstance(inventory_hash, str) or not re.fullmatch(
        r"[0-9a-f]{64}", inventory_hash
    ):
        return False
    return sha256_hex(canonical_json(deterministic)) == payload.get("artifact_sha256")


def _find_window(deterministic: Mapping[str, object], decision_date: str) -> dict:
    for window in deterministic.get("windows", []):
        if isinstance(window, dict) and window.get("decision_date") == decision_date:
            return window
    raise KeyError(f"no E2C window for decision {decision_date}")


def _window_matures_before(window: Mapping[str, object], decision_date: str) -> bool:
    """True when ``window``'s exit session is strictly before ``decision_date``.

    A window's realised return/drawdown only becomes known after its exit, so it
    is point-in-time evidence for a decision only once ``exit_date < decision_date``.
    """
    exit_date = window.get("exit_date")
    return isinstance(exit_date, str) and bool(exit_date) and exit_date < decision_date


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    count = len(ordered)
    if count == 0:
        return 0.0
    mid = count // 2
    if count % 2 == 1:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


# Realised return/drawdown of a matured window is an immutable historical fact,
# so a ref never expires within the research horizon.  The sentinel is a frozen
# server-owned constant and must not depend on mutable window data, otherwise an
# appended future window would change the registry of earlier decisions.
_EVIDENCE_VALID_UNTIL = datetime(9999, 12, 31, 15, 0, tzinfo=_SH)


def slot_summaries(
    payload: Mapping[str, object],
    decision_date: str | None = None,
) -> dict[str, dict[str, object]]:
    """Server-owned deterministic per-slot summary for the globally eligible set.

    With ``decision_date`` this is a point-in-time PREFIX summary: only windows
    already matured strictly before that decision contribute realised return /
    drawdown, so no future or in-flight window can leak into the model input.
    Its ``status`` is the fixed outcome-free eligibility label
    :data:`PIT_ELIGIBILITY_STATUS`; the whole-replay E2C verdict is never read
    here, so an early decision cannot see a future-derived OK/QUALIFIED/...
    conclusion.  ``decision_date=None`` returns the whole-replay digest for
    audit, which surfaces the aggregate verdict but is never a model input.
    Fields are exactly the frozen input-summary fields; no price/volume matrix,
    per-ticker score, weight, portfolio, backtest or future label is included.
    """
    deterministic = payload["deterministic"]
    windows = deterministic.get("windows", [])
    selected = [
        window
        for window in windows
        if isinstance(window, dict)
        and (decision_date is None or _window_matures_before(window, decision_date))
    ]
    summaries: dict[str, dict[str, object]] = {}
    for slot in ELIGIBLE_SLOTS:
        if decision_date is None:
            # Whole-replay audit digest: surface the aggregate E2C verdict.
            slot_candidates = (
                deterministic.get("candidates", {}).get(slot, {})
                if isinstance(deterministic.get("candidates"), dict)
                else {}
            )
            status = (
                slot_candidates.get("status")
                or slot_candidates.get("verdict")
                or "UNAVAILABLE"
            )
        else:
            # Decision-scoped PIT summary: only the fixed pre-replay eligibility
            # label, never the whole-replay verdict.
            status = PIT_ELIGIBILITY_STATUS
        returns: list[float] = []
        drawdowns: list[float] = []
        total_return = 0.0
        n_windows = 0
        for window in selected:
            per_slot = window.get("candidates", {}).get(slot)
            if not isinstance(per_slot, dict):
                continue
            n_windows += 1
            total = per_slot.get("total_return")
            drawdown = per_slot.get("max_drawdown")
            if isinstance(total, (int, float)):
                total_return += float(total)
                returns.append(float(total))
            if isinstance(drawdown, (int, float)):
                drawdowns.append(float(drawdown))
        median_return = _median(returns)
        max_drawdown = max(drawdowns) if drawdowns else 0.0
        summaries[slot] = {
            "slot_id": slot,
            "status": status,
            "n_windows": n_windows,
            "median_return": round(median_return, 8),
            "total_return": round(total_return, 8),
            "max_drawdown": round(max_drawdown, 8),
            "utility": round(0.7 * median_return - 0.3 * max_drawdown, 8),
        }
    return summaries


_EVIDENCE_SIGNALS = (
    ("total_return", "e2c_slot_return"),
    ("max_drawdown", "e2c_slot_drawdown"),
)


def build_evidence_registry(
    payload: Mapping[str, object],
    decision_date: str | None = None,
) -> Mapping[str, PITEvidenceRef]:
    """Derive the server-owned PIT evidence refs the model may cite.

    Every ref is bound to ONE window's realised metric for one eligible slot, so
    its ``available_at`` is that window's actual exit session — never the first
    decision date.  With ``decision_date`` only windows already matured strictly
    before that decision are exposed; the first decision exposes no realised
    evidence at all.  Two refs per slot from distinct matured windows give a veto
    the two independent PIT EvidenceRef IDs it requires.
    """
    deterministic = payload["deterministic"]
    windows = deterministic.get("windows", [])
    selected = [
        window
        for window in windows
        if isinstance(window, dict)
        and (decision_date is None or _window_matures_before(window, decision_date))
    ]
    registry: dict[str, PITEvidenceRef] = {}
    for window in selected:
        window_date = window.get("decision_date")
        exit_date = window.get("exit_date")
        if not isinstance(window_date, str) or not window_date:
            continue
        available_at = (
            _decision_time(exit_date)
            if isinstance(exit_date, str) and exit_date
            else _decision_time(window_date)
        )
        per_slot = window.get("candidates")
        if not isinstance(per_slot, dict):
            continue
        for slot in ELIGIBLE_SLOTS:
            slot_data = per_slot.get(slot)
            if not isinstance(slot_data, dict):
                continue
            for value_field, signal_id in _EVIDENCE_SIGNALS:
                value = slot_data.get(value_field)
                if not isinstance(value, (int, float)):
                    continue
                evidence_id = (
                    f"e2c:{window_date}:{slot}:{value_field}:"
                    f"{sha256_hex(canonical_json({slot: float(value)}))[:16]}"
                )
                registry[evidence_id] = PITEvidenceRef(
                    evidence_id=evidence_id,
                    signal_id=signal_id,
                    available_at=available_at,
                    valid_until=_EVIDENCE_VALID_UNTIL,
                )
    return MappingProxyType(registry)


def build_input_summary(
    payload: Mapping[str, object],
    decision_date: str,
    *,
    embargo_dates: Mapping[str, str] | None = None,
) -> dict[str, object]:
    """Build the per-decision model input summary (server-owned candidate digest).

    Only the frozen fields reach the model: per globally eligible slot the
    prefix status/metrics computed strictly from windows already matured before
    ``decision_date``, the window dates, and the PIT EvidenceRef inventory as
    ``(evidence_id, signal_id)`` pairs restricted to those same matured windows.
    No raw payload, matrix, weight, portfolio or future label is included.
    """
    deterministic = payload["deterministic"]
    window = _find_window(deterministic, decision_date)
    registry = build_evidence_registry(payload, decision_date)
    inventory = [
        [ref.evidence_id, ref.signal_id]
        for ref in sorted(
            registry.values(), key=lambda item: (item.signal_id, item.evidence_id)
        )
    ]
    embargo = (embargo_dates or {}).get(decision_date) or window.get("embargo_date")
    return {
        "decision_date": decision_date,
        "embargo_date": embargo,
        "entry_date": window.get("entry_date"),
        "exit_date": window.get("exit_date"),
        "slots": slot_summaries(payload, decision_date),
        "evidence_inventory": inventory,
    }


def resolve_embargo_dates(payload: Mapping[str, object]) -> dict[str, str | None]:
    """Map each decision to its embargo session (decision+1) via the public calendar."""
    from jiuwenswarm.quant import research_evidence_loader as loader

    import pandas as pd

    calendar = loader.load_canonical_calendar_evidence()
    sessions = pd.DatetimeIndex(pd.to_datetime(list(calendar.sessions)))
    iso = [session.date().isoformat() for session in sessions]
    positions = {session_date: index for index, session_date in enumerate(iso)}
    result: dict[str, str | None] = {}
    for decision in payload["deterministic"].get("decision_set", []):
        position = positions.get(decision)
        result[decision] = (
            iso[position + 1] if position is not None and position + 1 < len(iso) else None
        )
    return result


def load_e2c_evidence(
    artifact_path: str | Path | None = None,
    *,
    regenerate: bool = False,
    regenerate_out_dir: str | Path | None = None,
) -> dict[str, object]:
    """Load the E2C replay oracle and verify its full identity.

    ``regenerate=True`` deterministically rebuilds the oracle through the public
    loader replay; otherwise the artifact at ``artifact_path`` (or the default
    untracked ``output/replay/strategy_pool_replay.json``) is read.  Both paths
    re-verify artifact_sha256, inventory_hash and every per-window window_hash and
    fail closed on tamper or identity drift.
    """
    if regenerate:
        import evaluation.strategy_pool_replay as replay  # lazy, heavy imports

        payload = replay.run_replay(out_dir=regenerate_out_dir)
    else:
        path = (
            Path(artifact_path)
            if artifact_path is not None
            else DEFAULT_E2C_ARTIFACT_PATH
        )
        if not path.is_file():
            raise FileNotFoundError(f"E2C artifact not found: {path}")
        payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not verify_e2c_payload(payload):
        raise RuntimeError("E2C evidence failed artifact integrity verification")
    if payload.get("artifact_sha256") != EXPECTED_E2C_ARTIFACT_SHA256:
        raise RuntimeError("E2C artifact_sha256 does not match the frozen expectation")
    if payload.get("deterministic", {}).get("inventory_hash") != EXPECTED_E2C_INVENTORY_HASH:
        raise RuntimeError("E2C inventory_hash does not match the frozen expectation")
    return payload


def joint_identity_hash(
    *,
    artifact_sha256: str,
    inventory_hash: str,
    decision_set: Iterable[str],
) -> str:
    """Joint identity hash frozen before any outer evaluation."""
    payload = {
        "artifact_sha256": artifact_sha256,
        "inventory_hash": inventory_hash,
        "decision_set": list(decision_set),
        "model_version": MODEL_VERSION,
        "prompt_version": PROMPT_VERSION,
        "proposal_schema_version": PROPOSAL_SCHEMA_VERSION,
        "signal_to_delta_map_version": SIGNAL_TO_DELTA_MAP_VERSION,
        "assembler_version": ASSEMBLER_VERSION,
        "generator_config_version": GENERATOR_CONFIG_VERSION,
    }
    return sha256_hex(canonical_json(payload))


# ---------------------------------------------------------------------------
# Research-only model adapter (one bounded call per role, create-once bundle).
# ---------------------------------------------------------------------------


def call_role_model(
    role: str,
    input_summary: Mapping[str, object],
    call_fn: object,
    *,
    timeout_seconds: float = PER_ROLE_TIMEOUT_SECONDS,
    max_input_tokens: int = MAX_INPUT_TOKENS,
    max_output_tokens: int = MAX_OUTPUT_TOKENS,
) -> tuple[tuple[StrategyProposal, ...] | None, str | None]:
    """Run one bounded model call for one role.

    Returns ``(proposals, None)`` on success or ``(None, failure_reason)`` on any
    failure.  Zero tools, zero Quant RPCs, zero retries; timeout drops the role.
    The model call itself is the injected ``call_fn(role, input_summary)`` so no
    credential or external service is needed in this phase.
    """
    if not callable(call_fn):
        return None, "call_fn must be callable"
    if _estimate_tokens(canonical_json(dict(input_summary))) > max_input_tokens:
        return None, "input summary exceeds the per-role token budget"
    executor = ThreadPoolExecutor(max_workers=1)
    try:
        future = executor.submit(call_fn, role, dict(input_summary))
        try:
            raw = future.result(timeout=timeout_seconds)
        except _FutureTimeout:
            return None, f"model call timed out after {timeout_seconds}s"
        except Exception as exc:
            return None, f"model call failed: {exc!r}"
    finally:
        executor.shutdown(wait=False)
    if not isinstance(raw, str):
        raw = str(raw)
    if _estimate_tokens(raw) > max_output_tokens:
        return None, "model output exceeds the per-role token budget"
    decision_time = _decision_time(str(input_summary["decision_date"]))
    try:
        proposals = parse_role_output(role, raw, decision_time)
    except RoleOutputError as exc:
        return None, f"model output schema violation: {exc}"
    return proposals, None


@dataclass(frozen=True)
class RoleCall:
    """Outcome of one bounded role call inside a create-once bundle."""

    role: str
    input_summary: dict[str, object]
    proposals: tuple[StrategyProposal, ...] | None
    failure_reason: str | None

    @property
    def succeeded(self) -> bool:
        return self.proposals is not None


@dataclass(frozen=True)
class ProposalBundle:
    """One create-once proposal bundle per decision date.

    ``alpha`` and ``risk`` each hold at most one role call; the bundle is built
    exactly once per decision and reused for every A0/A1/A2 variant.
    """

    decision_date: str
    decision_time: datetime
    summary: dict[str, object]
    alpha: RoleCall
    risk: RoleCall

    @property
    def bundle_sha256(self) -> str:
        payload = {
            "decision_date": self.decision_date,
            "alpha": _role_call_payload(self.alpha),
            "risk": _role_call_payload(self.risk),
        }
        return sha256_hex(canonical_json(payload))


def _proposal_payload(proposal: StrategyProposal) -> dict[str, object]:
    return {
        "role": proposal.role,
        "slot": proposal.slot,
        "signal": proposal.signal,
        "confidence": proposal.confidence,
        "evidence": list(proposal.evidence),
        "rationale": proposal.rationale,
        "valid_from": proposal.valid_from.isoformat(),
        "valid_until": proposal.valid_until.isoformat(),
    }


def _role_call_payload(role_call: RoleCall) -> dict[str, object]:
    if role_call.proposals is None:
        return {"failure_reason": role_call.failure_reason}
    return {"proposals": [_proposal_payload(proposal) for proposal in role_call.proposals]}


def run_proposal_bundle(
    decision_date: str,
    payload: Mapping[str, object],
    call_fn: object,
    *,
    embargo_dates: Mapping[str, str] | None = None,
    timeout_seconds: float = PER_ROLE_TIMEOUT_SECONDS,
) -> ProposalBundle:
    """Create the single proposal bundle for one decision date (create-once).

    Re-verifies the E2C evidence identity, builds the input summary once, and
    calls the bounded model at most once per role.  A role failure drops only that
    role's bundle and preserves A0.
    """
    if not verify_e2c_payload(payload):
        raise RuntimeError("E2C evidence failed artifact integrity verification")
    summary = build_input_summary(payload, decision_date, embargo_dates=embargo_dates)
    alpha_proposals, alpha_failure = call_role_model(
        "alpha", summary, call_fn, timeout_seconds=timeout_seconds
    )
    risk_proposals, risk_failure = call_role_model(
        "risk_evidence", summary, call_fn, timeout_seconds=timeout_seconds
    )
    return ProposalBundle(
        decision_date=decision_date,
        decision_time=_decision_time(decision_date),
        summary=summary,
        alpha=RoleCall("alpha", summary, alpha_proposals, alpha_failure),
        risk=RoleCall("risk_evidence", summary, risk_proposals, risk_failure),
    )


# ---------------------------------------------------------------------------
# Deterministic StrategyAssembler.
# ---------------------------------------------------------------------------


def _normalise_slot_state(base_slot_state: Mapping[str, object]) -> dict[str, float]:
    if not isinstance(base_slot_state, Mapping):
        raise ValueError("base_slot_state must be a mapping")
    if set(base_slot_state) != set(ELIGIBLE_SLOTS):
        raise ValueError(
            f"base_slot_state must cover exactly {list(ELIGIBLE_SLOTS)}"
        )
    normalised: dict[str, float] = {}
    for slot in ELIGIBLE_SLOTS:
        value = base_slot_state[slot]
        if isinstance(value, bool) or not isinstance(value, Real):
            raise ValueError(f"base weight for {slot} must be a real number")
        weight = float(value)
        if not math.isfinite(weight) or weight < 0.0:
            raise ValueError(f"base weight for {slot} must be finite and non-negative")
        normalised[slot] = weight
    total = sum(normalised.values())
    if abs(total - 1.0) > 1e-6:
        raise ValueError(f"base_slot_state must sum to 1.0, got {total}")
    return normalised


def _proposal_sort_key(proposal: StrategyProposal) -> tuple[object, ...]:
    return (
        proposal.role,
        proposal.slot,
        proposal.signal,
        proposal.confidence,
        tuple(proposal.evidence),
        proposal.rationale,
        proposal.valid_from.isoformat(),
        proposal.valid_until.isoformat(),
    )


def _proposal_rejection(
    proposal: StrategyProposal,
    decision_time: datetime,
    registry: Mapping[str, PITEvidenceRef],
    veto_count: int,
) -> str | None:
    if proposal.signal != "hold" and not proposal.evidence:
        return "no evidence provided"
    if not proposal.valid_from <= decision_time <= proposal.valid_until:
        return "proposal outside validity period"
    for evidence_id in proposal.evidence:
        ref = registry.get(evidence_id)
        if ref is None:
            return f"unknown evidence: {evidence_id}"
        if ref.available_at > decision_time:
            return f"future evidence: {evidence_id}"
        if ref.valid_until < decision_time:
            return f"expired evidence: {evidence_id}"
    if proposal.signal == "veto":
        if proposal.slot == FALLBACK_SLOT:
            return "fallback slot cannot be vetoed"
        if len(proposal.evidence) < MIN_VETO_EVIDENCE_COUNT:
            return "veto requires at least two independent evidence refs"
        if veto_count >= MAX_NON_FALLBACK_VETOES:
            return "more than one veto per decision"
    return None


@dataclass(frozen=True)
class StrategyProposalOutcome:
    proposal: StrategyProposal
    accepted: bool
    reason: str | None
    applied_delta: float


@dataclass(frozen=True)
class StrategyDecisionTrace:
    """Deeply immutable audit trail for one strategy-level assembly."""

    decision_time: datetime
    base_slot_state: Mapping[str, float]
    proposals: tuple[StrategyProposal, ...]
    outcomes: tuple[StrategyProposalOutcome, ...]
    net_deltas: Mapping[str, float]
    excluded_slots: tuple[str, ...]
    role_failures: Mapping[str, str]
    final_weights: Mapping[str, float]
    base_ranking: tuple[str, ...]
    adjusted_ranking: tuple[str, ...]
    reject_reasons: Mapping[str, str]

    @property
    def accepted(self) -> tuple[StrategyProposal, ...]:
        return tuple(outcome.proposal for outcome in self.outcomes if outcome.accepted)

    @property
    def rejected(self) -> tuple[StrategyProposal, ...]:
        return tuple(outcome.proposal for outcome in self.outcomes if not outcome.accepted)

    def net_effect(self, slot: str) -> float:
        if slot not in self.base_slot_state:
            return 0.0
        return self.final_weights[slot] - self.base_slot_state[slot]


class StrategyAssembler:
    """Fail-closed deterministic merger of bounded strategy-slot proposals."""

    @staticmethod
    def assemble(
        base_slot_state: Mapping[str, object],
        proposals: Iterable[StrategyProposal],
        *,
        decision_time: datetime,
        evidence_registry: Mapping[str, PITEvidenceRef] | None = None,
    ) -> StrategyDecisionTrace:
        if not _is_aware(decision_time):
            raise ValueError("decision_time must be timezone-aware")
        base = _normalise_slot_state(base_slot_state)
        registry = dict(evidence_registry or {})
        ordered = tuple(sorted(tuple(proposals), key=_proposal_sort_key))

        decisions: list[tuple[StrategyProposal, bool, str | None, float]] = []
        claimed_evidence: set[str] = set()
        veto_count = 0
        role_delta_invalid: dict[str, str] = {}

        for index, proposal in enumerate(ordered):
            reason = _proposal_rejection(proposal, decision_time, registry, veto_count)
            if reason is None and claimed_evidence.intersection(proposal.evidence):
                reason = "evidence_id reused across proposals"
            if reason is not None:
                decisions.append((proposal, False, reason, 0.0))
                continue
            claimed_evidence.update(proposal.evidence)
            try:
                delta = _bounded_delta(
                    server_signal_to_delta(
                        proposal.role, proposal.signal, proposal.confidence
                    )
                )
            except ValueError as exc:
                role_delta_invalid[proposal.role] = f"invalid delta: {exc}"
                decisions.append((proposal, False, f"invalid delta: {exc}", 0.0))
                continue
            if proposal.signal == "veto":
                veto_count += 1
            decisions.append((proposal, True, None, delta))

        alpha_net: dict[str, float] = {slot: 0.0 for slot in ELIGIBLE_SLOTS}
        risk_net: dict[str, float] = {slot: 0.0 for slot in ELIGIBLE_SLOTS}
        for proposal, accepted, _reason, delta in decisions:
            if not accepted:
                continue
            bucket = alpha_net if proposal.role == "alpha" else risk_net
            bucket[proposal.slot] += delta

        role_failures: dict[str, str] = {}
        alpha_l1 = sum(abs(value) for value in alpha_net.values())
        alpha_slot_max = max((abs(value) for value in alpha_net.values()), default=0.0)
        if alpha_l1 > 0.0 and (
            alpha_slot_max > MAX_ALPHA_SLOT_DELTA + 1e-9
            or alpha_l1 > MAX_ALPHA_TOTAL_L1 + 1e-9
        ):
            role_failures["alpha"] = (
                "alpha per-slot |delta|<=0.10 and total L1<=0.20 violated "
                f"(slot_max={alpha_slot_max:.4f}, l1={alpha_l1:.4f})"
            )
        if any(value > 1e-12 for value in risk_net.values()):
            role_failures["risk_evidence"] = "risk delta must be non-positive"
        for role, reason in role_delta_invalid.items():
            role_failures[role] = reason

        if "alpha" in role_failures:
            alpha_net = {slot: 0.0 for slot in ELIGIBLE_SLOTS}
        if "risk_evidence" in role_failures:
            risk_net = {slot: 0.0 for slot in ELIGIBLE_SLOTS}

        final_outcomes: list[StrategyProposalOutcome] = []
        reject_reasons: dict[str, str] = {}
        excluded: set[str] = set()
        net_delta: dict[str, float] = {slot: 0.0 for slot in ELIGIBLE_SLOTS}
        for index, (proposal, accepted, reason, delta) in enumerate(decisions):
            key = f"{index}:{proposal.role}:{proposal.slot}"
            if not accepted:
                final_outcomes.append(StrategyProposalOutcome(proposal, False, reason, 0.0))
                reject_reasons[key] = reason or "rejected"
                continue
            if proposal.role in role_failures:
                final_outcomes.append(
                    StrategyProposalOutcome(proposal, False, role_failures[proposal.role], 0.0)
                )
                reject_reasons[key] = role_failures[proposal.role]
                continue
            final_outcomes.append(StrategyProposalOutcome(proposal, True, None, delta))
            net_delta[proposal.slot] += delta
            if proposal.role == "risk_evidence" and proposal.signal == "veto":
                excluded.add(proposal.slot)

        adjusted: dict[str, float] = {}
        for slot in ELIGIBLE_SLOTS:
            if slot in excluded:
                adjusted[slot] = 0.0
            else:
                adjusted[slot] = max(0.0, base[slot] + net_delta[slot])
        total = sum(adjusted.values())
        if total <= 1e-9:
            raise RuntimeError("all eligible slots excluded; cannot form an allocation")
        final_weights: dict[str, float] = {
            slot: value / total for slot, value in adjusted.items()
        }
        for slot in ELIGIBLE_SLOTS:
            if final_weights[slot] < -1e-9:
                raise RuntimeError(f"final weight negative for {slot}")
        if abs(sum(final_weights.values()) - 1.0) > 1e-9:
            raise RuntimeError("final weights do not sum to 1")

        base_ranking = tuple(sorted(ELIGIBLE_SLOTS, key=lambda slot: (-base[slot], slot)))
        adjusted_ranking = tuple(
            sorted(ELIGIBLE_SLOTS, key=lambda slot: (-final_weights[slot], slot))
        )
        return StrategyDecisionTrace(
            decision_time=decision_time,
            base_slot_state=MappingProxyType(dict(sorted(base.items()))),
            proposals=tuple(item[0] for item in decisions),
            outcomes=tuple(final_outcomes),
            net_deltas=MappingProxyType(dict(sorted(net_delta.items()))),
            excluded_slots=tuple(sorted(excluded)),
            role_failures=MappingProxyType(dict(role_failures)),
            final_weights=MappingProxyType(dict(sorted(final_weights.items()))),
            base_ranking=base_ranking,
            adjusted_ranking=adjusted_ranking,
            reject_reasons=MappingProxyType(dict(reject_reasons)),
        )


def evaluate_variants(
    bundle: ProposalBundle,
    base_slot_state: Mapping[str, object],
    *,
    evidence_registry: Mapping[str, PITEvidenceRef],
) -> dict[str, StrategyDecisionTrace]:
    """Evaluate A0/A1/A2 independently from one bundle with no shared mutable state."""
    alpha = bundle.alpha.proposals or ()
    risk = bundle.risk.proposals or ()
    return {
        "A0_no_agent": StrategyAssembler.assemble(
            base_slot_state,
            (),
            decision_time=bundle.decision_time,
            evidence_registry=evidence_registry,
        ),
        "A1_alpha_only": StrategyAssembler.assemble(
            base_slot_state,
            alpha,
            decision_time=bundle.decision_time,
            evidence_registry=evidence_registry,
        ),
        "A2_alpha_risk": StrategyAssembler.assemble(
            base_slot_state,
            alpha + risk,
            decision_time=bundle.decision_time,
            evidence_registry=evidence_registry,
        ),
    }


# ---------------------------------------------------------------------------
# Fusion serialization (mirrors strategy_pool_replay: meta separated).
# ---------------------------------------------------------------------------


def _trace_payload(trace: StrategyDecisionTrace) -> dict[str, object]:
    return {
        "decision_time": trace.decision_time.isoformat(),
        "base_slot_state": {
            slot: round(weight, 8) for slot, weight in sorted(trace.base_slot_state.items())
        },
        "final_weights": {
            slot: round(weight, 8) for slot, weight in sorted(trace.final_weights.items())
        },
        "net_deltas": {
            slot: round(value, 8) for slot, value in sorted(trace.net_deltas.items())
        },
        "excluded_slots": list(trace.excluded_slots),
        "role_failures": dict(trace.role_failures),
        "base_ranking": list(trace.base_ranking),
        "adjusted_ranking": list(trace.adjusted_ranking),
        "reject_reasons": dict(trace.reject_reasons),
        "proposals": [_proposal_payload(proposal) for proposal in trace.proposals],
        "outcomes": [
            {
                "role": outcome.proposal.role,
                "slot": outcome.proposal.slot,
                "signal": outcome.proposal.signal,
                "accepted": outcome.accepted,
                "reason": outcome.reason,
                "applied_delta": round(outcome.applied_delta, 8),
            }
            for outcome in trace.outcomes
        ],
    }


def build_fusion_payload(
    *,
    decision_date: str,
    base_slot_state: Mapping[str, object],
    variants: Mapping[str, StrategyDecisionTrace],
    identity_hash: str,
) -> dict[str, object]:
    """Per-decision deterministic fusion artifact with a recomputable hash."""
    window_content: dict[str, object] = {
        "decision_date": decision_date,
        "base_slot_state": {
            slot: round(float(base_slot_state[slot]), 8)
            for slot in sorted(base_slot_state)
        },
        "joint_identity_hash": identity_hash,
        "variants": {
            name: _trace_payload(trace) for name, trace in sorted(variants.items())
        },
    }
    window_content["window_hash"] = window_hash(window_content)
    deterministic: dict[str, object] = {"windows": [window_content]}
    return {"deterministic": deterministic, "artifact_sha256": artifact_hash(deterministic)}


def verify_fusion_payload(payload: object) -> bool:
    """Recompute the fusion window/artifact hashes; False on any tamper."""
    if not isinstance(payload, dict):
        return False
    deterministic = payload.get("deterministic")
    if not isinstance(deterministic, dict):
        return False
    for window in deterministic.get("windows", []):
        if not isinstance(window, dict):
            return False
        content = {key: value for key, value in window.items() if key != "window_hash"}
        if sha256_hex(canonical_json(content)) != window.get("window_hash"):
            return False
    return sha256_hex(canonical_json(deterministic)) == payload.get("artifact_sha256")


# ---------------------------------------------------------------------------
# Standalone research scaffold (no real model; credentials are out of scope).
# ---------------------------------------------------------------------------


def _parse_base(text: str | None) -> dict[str, float]:
    if text is None:
        return _default_base_state()
    data = json.loads(text)
    if not isinstance(data, dict) or set(data) != set(ELIGIBLE_SLOTS):
        raise ValueError("base must cover exactly the eligible slots")
    return {slot: float(data[slot]) for slot in ELIGIBLE_SLOTS}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="WP1-E3-R1 strategy-slot fusion scaffold (research-only)"
    )
    parser.add_argument(
        "--decision",
        help="decision date YYYY-MM-DD (default: first decision in the set)",
    )
    parser.add_argument(
        "--base",
        help=(
            'base slot state JSON, e.g. \'{"production_six_factor":1.0,'
            '"t2_comparator":0.0}\''
        ),
    )
    parser.add_argument("--artifact", type=Path, default=None)
    parser.add_argument(
        "--regenerate", action="store_true", help="deterministically regenerate the E2C oracle"
    )
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--timeout", type=float, default=PER_ROLE_TIMEOUT_SECONDS)
    args = parser.parse_args(argv)

    payload = load_e2c_evidence(args.artifact, regenerate=args.regenerate)
    decision_set = list(payload["deterministic"]["decision_set"])
    decision = args.decision or decision_set[0]
    if decision not in decision_set:
        parser.error(f"decision {decision} not in the E2C decision set")
    base = _parse_base(args.base)
    registry = build_evidence_registry(payload, decision)
    embargo_dates = resolve_embargo_dates(payload)

    def _noop_model(_role: str, _summary: Mapping[str, object]) -> str:
        # No model credentials are configured in this phase; the scaffold runs a
        # deterministic empty-proposal baseline so the pipeline is fully exercised.
        return "[]"

    bundle = run_proposal_bundle(
        decision,
        payload,
        _noop_model,
        embargo_dates=embargo_dates,
        timeout_seconds=args.timeout,
    )
    variants = evaluate_variants(bundle, base, evidence_registry=registry)
    identity_hash = joint_identity_hash(
        artifact_sha256=str(payload["artifact_sha256"]),
        inventory_hash=str(payload["deterministic"]["inventory_hash"]),
        decision_set=decision_set,
    )
    artifact = build_fusion_payload(
        decision_date=decision,
        base_slot_state=base,
        variants=variants,
        identity_hash=identity_hash,
    )
    assert verify_fusion_payload(artifact)
    out_path = (
        args.out
        or (_REPO_ROOT / "output" / "fusion" / f"fusion_{decision}.json")
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_payload: dict[str, object] = {
        "task_id": "WP1-E3-R1",
        "meta": {
            "command": " ".join(sys.argv),
            "created": _dt.datetime.now(_SH).isoformat(),
            "python": sys.version.split()[0],
            "exit_code": 0,
        },
        **artifact,
    }
    out_path.write_text(
        json.dumps(out_payload, ensure_ascii=False, sort_keys=True, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    print(
        json.dumps(
            {
                "artifact": str(out_path),
                "artifact_sha256": artifact["artifact_sha256"],
                "identity_hash": identity_hash,
                "decision": decision,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
