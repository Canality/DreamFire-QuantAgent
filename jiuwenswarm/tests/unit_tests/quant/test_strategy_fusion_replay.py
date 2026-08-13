"""WP1-E3-R1 tests for the research-only bounded strategy-slot fusion module.

Covers location revision 3's full negative-coverage map, artifact tamper,
cache/production/direct/formal isolation and determinism.  All tests are
self-contained on synthetic E2C-shaped payloads; nothing reads the untracked
``output/`` artifact and no model or network is invoked.
"""

from __future__ import annotations

import json
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from evaluation.strategy_fusion_replay import (
    ALPHA_DELTA_MAP,
    ALPHA_SIGNALS,
    DEFAULT_E2C_ARTIFACT_PATH,
    ELIGIBLE_SLOTS,
    EXPECTED_E2C_ARTIFACT_SHA256,
    EXPECTED_E2C_INVENTORY_HASH,
    FALLBACK_SLOT,
    GLOBALLY_EXCLUDED_SLOTS,
    MAX_ALPHA_SLOT_DELTA,
    MAX_ALPHA_TOTAL_L1,
    MAX_INPUT_TOKENS,
    MIN_VETO_EVIDENCE_COUNT,
    PER_ROLE_TIMEOUT_SECONDS,
    PIT_ELIGIBILITY_STATUS,
    PITEvidenceRef,
    RISK_DELTA_MAP,
    RISK_SIGNALS,
    RoleOutputError,
    StrategyAssembler,
    StrategyProposal,
    VALID_CONFIDENCE,
    VALID_ROLES,
    artifact_hash,
    build_evidence_registry,
    build_fusion_payload,
    build_input_summary,
    call_role_model,
    canonical_json,
    evaluate_variants,
    joint_identity_hash,
    load_e2c_evidence,
    parse_role_output,
    run_proposal_bundle,
    server_signal_to_delta,
    slot_summaries,
    verify_e2c_payload,
    verify_fusion_payload,
    window_hash,
)

_REPO_ROOT = Path(__file__).resolve().parents[4]

_DECISION_SET = (
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
_BASE = {"production_six_factor": 1.0, "t2_comparator": 0.0}


def _decision_time(decision_date: str) -> datetime:
    from evaluation.strategy_fusion_replay import _decision_time as resolve

    return resolve(decision_date)


def _synthetic_window(decision_date: str, *, exit_date: str | None = None) -> dict[str, object]:
    """One window; trend_short_5_10_20 records a LOCAL OK to prove unrevivability.

    ``exit_date`` defaults to the decision date itself, which means the window is
    only ever point-in-time evidence for decisions strictly after that date.
    """
    content: dict[str, object] = {
        "decision_date": decision_date,
        "entry_date": decision_date,
        "exit_date": exit_date if exit_date is not None else decision_date,
        "valuation_dates": [decision_date],
        "candidates": {
            "production_six_factor": {
                "status": "OK",
                "total_return": 0.02,
                "max_drawdown": 0.05,
            },
            "t2_comparator": {
                "status": "OK",
                "total_return": 0.025,
                "max_drawdown": 0.048,
            },
            "trend_short_5_10_20": {
                "status": "OK",
                "total_return": 0.015,
                "max_drawdown": 0.05,
            },
        },
    }
    content["window_hash"] = window_hash(content)
    return content


def _window_exit_dates() -> dict[str, str]:
    """Exit each window strictly before the NEXT decision so it matures on time.

    Window ``i`` exits the day before decision ``i+1``, so at decision index ``k``
    exactly the windows 0..k-1 have ``exit_date < decision_date`` and are matured.
    """
    exits: dict[str, str] = {}
    for index, decision in enumerate(_DECISION_SET):
        if index + 1 < len(_DECISION_SET):
            exits[decision] = (
                date.fromisoformat(_DECISION_SET[index + 1]) - timedelta(days=1)
            ).isoformat()
        else:
            exits[decision] = (
                date.fromisoformat(decision) + timedelta(days=21)
            ).isoformat()
    return exits


def _synthetic_payload() -> dict[str, object]:
    exits = _window_exit_dates()
    windows = [
        _synthetic_window(decision, exit_date=exits[decision])
        for decision in _DECISION_SET
    ]
    candidates = {
        "production_six_factor": {
            "status": "OK",
            "n_windows": 12,
            "median_return": 0.025,
            "worst_drawdown": 0.05,
        },
        "t2_comparator": {
            "verdict": "QUALIFIED",
            "n_windows": 12,
            "median_return": 0.028,
            "worst_drawdown": 0.048,
        },
    }
    deterministic = {
        "inventory_hash": "2" * 64,
        "decision_set": list(_DECISION_SET),
        "windows": windows,
        "candidates": candidates,
    }
    return {
        "task_id": "SYNTHETIC",
        "deterministic": deterministic,
        "artifact_sha256": artifact_hash(deterministic),
    }


def _rehash(payload: dict[str, object]) -> dict[str, object]:
    """Recompute per-window and whole-artifact hashes after a mutation."""
    deterministic = payload["deterministic"]
    for window in deterministic["windows"]:
        window["window_hash"] = window_hash(window)
    payload["artifact_sha256"] = artifact_hash(deterministic)
    return payload


def _copy(payload: dict[str, object]) -> dict[str, object]:
    return json.loads(canonical_json(payload))


def _json_proposal(
    slot: str,
    signal: str,
    confidence: str = "high",
    evidence_ids: list[str] | None = None,
    rationale: str = "rationale",
) -> str:
    return json.dumps(
        [
            {
                "slot": slot,
                "signal": signal,
                "confidence": confidence,
                "evidence_ids": evidence_ids if evidence_ids is not None else ["e1"],
                "rationale": rationale,
            }
        ]
    )


# ---------------------------------------------------------------------------
# Global eligibility.
# ---------------------------------------------------------------------------


def test_globally_eligible_set_is_exact() -> None:
    assert ELIGIBLE_SLOTS == ("production_six_factor", "t2_comparator")
    assert GLOBALLY_EXCLUDED_SLOTS == (
        "trend_short_5_10_20",
        "trend_medium_20_60",
        "trend_long_120_250",
        "similar_market_blend",
    )
    assert FALLBACK_SLOT == "production_six_factor"


def test_global_failed_slots_cannot_be_revived_by_parser() -> None:
    # Even though the synthetic artifact records a LOCAL OK for
    # trend_short_5_10_20, the parser rejects any proposal targeting it.
    payload = _synthetic_payload()
    assert payload["deterministic"]["windows"][0]["candidates"][
        "trend_short_5_10_20"
    ]["status"] == "OK"
    decision_time = _decision_time(_DECISION_SET[0])
    for excluded in GLOBALLY_EXCLUDED_SLOTS:
        with pytest.raises(RoleOutputError, match="non-eligible"):
            parse_role_output(
                "alpha",
                _json_proposal(excluded, "strengthen"),
                decision_time,
            )
    # The trend slot never appears in the summary either.
    assert set(slot_summaries(payload)) == set(ELIGIBLE_SLOTS)


def test_global_failed_slots_cannot_be_revived_by_schema() -> None:
    decision_time = _decision_time(_DECISION_SET[0])
    for excluded in GLOBALLY_EXCLUDED_SLOTS:
        with pytest.raises(ValueError, match="not globally eligible"):
            StrategyProposal(
                role="alpha",
                slot=excluded,
                signal="strengthen",
                confidence="high",
                evidence=("e1",),
                rationale="r",
                valid_from=decision_time,
                valid_until=decision_time,
            )


# ---------------------------------------------------------------------------
# Strict parser / output schema.
# ---------------------------------------------------------------------------


def test_parse_valid_alpha_and_risk_proposals() -> None:
    decision_time = _decision_time(_DECISION_SET[0])
    alpha = parse_role_output(
        "alpha",
        _json_proposal("t2_comparator", "strengthen", "high", ["e1"]),
        decision_time,
    )
    assert len(alpha) == 1
    assert alpha[0].role == "alpha"
    assert alpha[0].slot == "t2_comparator"
    assert alpha[0].signal == "strengthen"
    risk = parse_role_output(
        "risk_evidence",
        _json_proposal("production_six_factor", "reduce", "low", ["e1"]),
        decision_time,
    )
    assert risk[0].signal == "reduce"
    assert risk[0].valid_from == decision_time
    assert risk[0].valid_until == decision_time


def test_parse_accepts_hold_with_empty_evidence() -> None:
    decision_time = _decision_time(_DECISION_SET[0])
    proposals = parse_role_output(
        "alpha",
        _json_proposal("production_six_factor", "hold", "medium", []),
        decision_time,
    )
    assert proposals[0].signal == "hold"
    assert proposals[0].evidence == ()


def test_parse_rejects_non_schema_numeric_fields() -> None:
    decision_time = _decision_time(_DECISION_SET[0])
    for bad_key in ("delta", "adjustment", "score", "weight", "ticker", "portfolio", "backtest"):
        item = {
            "slot": "t2_comparator",
            "signal": "strengthen",
            "confidence": "high",
            "evidence_ids": ["e1"],
            "rationale": "r",
            bad_key: 0.05,
        }
        with pytest.raises(RoleOutputError, match="non-schema fields"):
            parse_role_output("alpha", json.dumps([item]), decision_time)


def test_parse_rejects_wrong_role_signals() -> None:
    decision_time = _decision_time(_DECISION_SET[0])
    with pytest.raises(RoleOutputError, match="invalid signal"):
        parse_role_output("alpha", _json_proposal("t2_comparator", "reduce"), decision_time)
    with pytest.raises(RoleOutputError, match="invalid signal"):
        parse_role_output(
            "risk_evidence", _json_proposal("t2_comparator", "strengthen"), decision_time
        )
    with pytest.raises(RoleOutputError, match="invalid signal"):
        parse_role_output("alpha", _json_proposal("t2_comparator", "veto"), decision_time)


def test_parse_rejects_unknown_and_non_eligible_slots() -> None:
    decision_time = _decision_time(_DECISION_SET[0])
    with pytest.raises(RoleOutputError, match="non-eligible"):
        parse_role_output("alpha", _json_proposal("nonexistent_slot", "strengthen"), decision_time)


def test_parse_rejects_malformed_json_and_non_list() -> None:
    decision_time = _decision_time(_DECISION_SET[0])
    with pytest.raises(RoleOutputError, match="malformed JSON"):
        parse_role_output("alpha", "not json at all", decision_time)
    with pytest.raises(RoleOutputError, match="JSON array"):
        parse_role_output("alpha", '{"slot": "t2_comparator"}', decision_time)


def test_parse_rejects_bad_field_types() -> None:
    decision_time = _decision_time(_DECISION_SET[0])
    with pytest.raises(RoleOutputError, match="evidence_ids"):
        parse_role_output(
            "alpha",
            json.dumps(
                [
                    {
                        "slot": "t2_comparator",
                        "signal": "strengthen",
                        "confidence": "high",
                        "evidence_ids": [0.5],
                        "rationale": "r",
                    }
                ]
            ),
            decision_time,
        )
    with pytest.raises(RoleOutputError, match="confidence"):
        parse_role_output(
            "alpha",
            json.dumps(
                [
                    {
                        "slot": "t2_comparator",
                        "signal": "strengthen",
                        "confidence": 7,
                        "evidence_ids": ["e1"],
                        "rationale": "r",
                    }
                ]
            ),
            decision_time,
        )
    with pytest.raises(RoleOutputError, match="rationale"):
        parse_role_output(
            "alpha",
            json.dumps(
                [
                    {
                        "slot": "t2_comparator",
                        "signal": "strengthen",
                        "confidence": "high",
                        "evidence_ids": ["e1"],
                        "rationale": "",
                    }
                ]
            ),
            decision_time,
        )


def test_parse_rejects_duplicate_evidence_within_proposal() -> None:
    decision_time = _decision_time(_DECISION_SET[0])
    with pytest.raises(RoleOutputError, match="duplicate evidence_id"):
        parse_role_output(
            "alpha",
            json.dumps(
                [
                    {
                        "slot": "t2_comparator",
                        "signal": "strengthen",
                        "confidence": "high",
                        "evidence_ids": ["e1", "e1"],
                        "rationale": "r",
                    }
                ]
            ),
            decision_time,
        )


# ---------------------------------------------------------------------------
# Server signal -> delta map.
# ---------------------------------------------------------------------------


def test_server_delta_map_matches_frozen_values() -> None:
    assert server_signal_to_delta("alpha", "strengthen", "high") == 0.10
    assert server_signal_to_delta("alpha", "strengthen", "medium") == 0.05
    assert server_signal_to_delta("alpha", "strengthen", "low") == 0.02
    assert server_signal_to_delta("alpha", "weaken", "high") == -0.10
    assert server_signal_to_delta("alpha", "weaken", "medium") == -0.05
    assert server_signal_to_delta("alpha", "weaken", "low") == -0.02
    assert server_signal_to_delta("alpha", "hold", "high") == 0.0
    assert server_signal_to_delta("risk_evidence", "reduce", "high") == -0.10
    assert server_signal_to_delta("risk_evidence", "reduce", "medium") == -0.05
    assert server_signal_to_delta("risk_evidence", "reduce", "low") == -0.02
    assert server_signal_to_delta("risk_evidence", "veto", "high") == 0.0
    assert server_signal_to_delta("risk_evidence", "hold", "medium") == 0.0
    # Alpha per-slot bound is guaranteed by the map.
    for value in ALPHA_DELTA_MAP.values():
        assert abs(value) <= MAX_ALPHA_SLOT_DELTA
    for value in RISK_DELTA_MAP.values():
        assert value <= 0.0
        assert abs(value) <= MAX_ALPHA_SLOT_DELTA
    # Two eligible slots cannot exceed total L1 through the map alone.
    assert 2 * MAX_ALPHA_SLOT_DELTA == MAX_ALPHA_TOTAL_L1


def test_bounded_delta_rejects_non_finite_and_out_of_bound() -> None:
    from evaluation.strategy_fusion_replay import _bounded_delta

    for bad in (float("nan"), float("inf"), float("-inf"), 0.11, -0.11):
        with pytest.raises(ValueError):
            _bounded_delta(bad)
    assert _bounded_delta(0.10) == 0.10
    assert _bounded_delta(-0.10) == -0.10


def test_server_delta_unknown_signal_raises() -> None:
    with pytest.raises(ValueError, match="no server delta"):
        server_signal_to_delta("alpha", "strengthen", "extreme")


# ---------------------------------------------------------------------------
# Evidence registry and model input summary.
# ---------------------------------------------------------------------------


def test_evidence_registry_is_per_window_and_point_in_time() -> None:
    payload = _synthetic_payload()
    registry = build_evidence_registry(payload)
    # One ref per (window, eligible slot, PIT signal): two signals per slot.
    source_windows = {evidence_id.split(":")[1] for evidence_id in registry}
    assert source_windows == set(_DECISION_SET)
    assert len(registry) == len(_DECISION_SET) * 2 * 2
    signals = {ref.signal_id for ref in registry.values()}
    assert signals == {"e2c_slot_return", "e2c_slot_drawdown"}
    # available_at reflects the source window's actual exit session, never
    # the first decision date (the review's PIT assertion).
    exit_by_decision = {
        w["decision_date"]: w["exit_date"] for w in payload["deterministic"]["windows"]
    }
    first_decision_time = _decision_time(_DECISION_SET[0])
    for evidence_id, ref in registry.items():
        source = evidence_id.split(":")[1]
        assert source in exit_by_decision
        assert ref.available_at == _decision_time(exit_by_decision[source])
        assert ref.available_at != first_decision_time
    # The first decision has no matured window -> no realised evidence.
    assert not build_evidence_registry(payload, _DECISION_SET[0])


def test_per_decision_registry_exposes_only_matured_windows() -> None:
    payload = _synthetic_payload()
    for index, decision in enumerate(_DECISION_SET):
        registry = build_evidence_registry(payload, decision)
        # Exactly windows 0..index-1 exit strictly before decision[index].
        assert len(registry) == 4 * index, decision
        for ref in registry.values():
            assert ref.available_at < _decision_time(decision)


def test_future_windows_do_not_affect_early_decision() -> None:
    payload = _synthetic_payload()
    early = _DECISION_SET[2]
    registry_early = build_evidence_registry(payload, early)

    def _model(role: str, _summary: object) -> str:
        ordered = sorted(registry_early.values(), key=lambda ref: ref.evidence_id)
        t2_ref = next(ref for ref in ordered if "t2_comparator" in ref.evidence_id)
        production_ref = next(
            ref for ref in ordered if "production_six_factor" in ref.evidence_id
        )
        if role == "alpha":
            return _json_proposal(
                "t2_comparator", "strengthen", "medium", [t2_ref.evidence_id]
            )
        return _json_proposal(
            "production_six_factor", "reduce", "low", [production_ref.evidence_id]
        )

    summary_before = build_input_summary(payload, early)
    bundle_before = run_proposal_bundle(early, payload, _model)
    variants_before = evaluate_variants(bundle_before, _BASE, evidence_registry=registry_early)

    # Mutate a window strictly after the early decision, flip the whole-replay
    # aggregate verdicts, AND append a new future window.  None of these may
    # change an earlier decision's PIT summary, bundle or variants.
    mutated = _copy(payload)
    later = _DECISION_SET[-1]
    for window in mutated["deterministic"]["windows"]:
        if window["decision_date"] == later:
            window["candidates"]["t2_comparator"]["total_return"] = 9.99
    mutated["deterministic"]["candidates"]["t2_comparator"]["verdict"] = "DOES_NOT_QUALIFY"
    mutated["deterministic"]["candidates"]["production_six_factor"]["status"] = "FAILED"
    new_decision = "2026-01-08"
    mutated["deterministic"]["windows"].append(
        _synthetic_window(new_decision, exit_date="2026-02-05")
    )
    mutated["deterministic"]["decision_set"].append(new_decision)
    _rehash(mutated)

    registry_after = build_evidence_registry(mutated, early)
    summary_after = build_input_summary(mutated, early)
    bundle_after = run_proposal_bundle(early, mutated, _model)
    variants_after = evaluate_variants(bundle_after, _BASE, evidence_registry=registry_after)

    assert summary_after == summary_before
    assert dict(registry_after) == dict(registry_early)
    assert bundle_after.bundle_sha256 == bundle_before.bundle_sha256
    for name in ("A0_no_agent", "A1_alpha_only", "A2_alpha_risk"):
        assert variants_after[name].final_weights == variants_before[name].final_weights


def test_input_summary_contains_only_frozen_fields() -> None:
    decision = _DECISION_SET[2]
    summary = build_input_summary(
        _synthetic_payload(), decision, embargo_dates={decision: "2025-03-20"}
    )
    assert set(summary) == {
        "decision_date",
        "embargo_date",
        "entry_date",
        "exit_date",
        "slots",
        "evidence_inventory",
    }
    assert summary["decision_date"] == decision
    assert summary["embargo_date"] == "2025-03-20"
    assert set(summary["slots"]) == set(ELIGIBLE_SLOTS)
    for slot, fields in summary["slots"].items():
        assert set(fields) == {
            "slot_id",
            "status",
            "n_windows",
            "median_return",
            "total_return",
            "max_drawdown",
            "utility",
        }
    # The decision-scoped status is the fixed outcome-free eligibility label,
    # never the whole-replay E2C verdict.
    assert summary["slots"]["t2_comparator"]["status"] == PIT_ELIGIBILITY_STATUS
    assert summary["slots"]["production_six_factor"]["status"] == PIT_ELIGIBILITY_STATUS
    # The summary is a PIT prefix: only the two windows matured before this
    # decision contribute realised metrics.
    assert summary["slots"]["t2_comparator"]["n_windows"] == 2
    assert summary["slots"]["t2_comparator"]["total_return"] == pytest.approx(0.05)
    # Inventory is (evidence_id, signal_id) pairs restricted to matured windows.
    assert all(isinstance(pair, list) and len(pair) == 2 for pair in summary["evidence_inventory"])
    assert len(summary["evidence_inventory"]) == 4 * 2


def test_input_summary_excludes_raw_payload() -> None:
    payload = _synthetic_payload()
    summary = build_input_summary(payload, _DECISION_SET[0])
    text = canonical_json(summary)
    # No per-window detail, no weights/portfolios/tickers, no excluded slots.
    for forbidden in ("trend_short_5_10_20", "weights", "portfolio", "valuation_dates"):
        assert forbidden not in text


def test_input_summary_unknown_decision_raises() -> None:
    with pytest.raises(KeyError, match="no E2C window"):
        build_input_summary(_synthetic_payload(), "2024-01-01")


def test_first_decision_status_has_no_future_verdict() -> None:
    """The first decision's summary never exposes a whole-replay E2C verdict."""
    payload = _synthetic_payload()
    summary = build_input_summary(payload, _DECISION_SET[0])
    assert summary["slots"]["t2_comparator"]["n_windows"] == 0
    for slot in ELIGIBLE_SLOTS:
        status = summary["slots"][slot]["status"]
        assert status == PIT_ELIGIBILITY_STATUS
        # No whole-replay qualification/result conclusion may appear at all.
        assert status not in {
            "OK",
            "QUALIFIED",
            "QUALIFIED_RESEARCH_ONLY",
            "DOES_NOT_QUALIFY",
            "BENCHMARK_UNAVAILABLE",
            "UNAVAILABLE",
        }


def test_whole_replay_digest_keeps_aggregate_verdict() -> None:
    """decision_date=None is an audit digest (never a model input): it may
    surface the aggregate E2C verdict."""
    digest = slot_summaries(_synthetic_payload())
    assert digest["production_six_factor"]["status"] == "OK"
    assert digest["t2_comparator"]["status"] == "QUALIFIED"


# ---------------------------------------------------------------------------
# E2C artifact integrity verification.
# ---------------------------------------------------------------------------


def test_verify_e2c_payload_detects_artifact_tamper() -> None:
    payload = _synthetic_payload()
    assert verify_e2c_payload(payload)
    tampered = _copy(payload)
    tampered["deterministic"]["candidates"]["t2_comparator"]["median_return"] = 0.99
    assert not verify_e2c_payload(tampered)


def test_verify_e2c_payload_detects_inventory_tamper() -> None:
    tampered = _copy(_synthetic_payload())
    tampered["deterministic"]["inventory_hash"] = "1" * 64
    assert not verify_e2c_payload(tampered)


def test_verify_e2c_payload_detects_window_tamper() -> None:
    tampered = _copy(_synthetic_payload())
    tampered["deterministic"]["windows"][0]["candidates"]["t2_comparator"][
        "total_return"
    ] = 0.5
    assert not verify_e2c_payload(tampered)


def test_verify_e2c_payload_rejects_missing_deterministic() -> None:
    assert not verify_e2c_payload({})
    assert not verify_e2c_payload({"artifact_sha256": "0" * 64})
    assert not verify_e2c_payload(None)


def test_load_e2c_evidence_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_e2c_evidence(tmp_path / "missing.json")


def test_load_e2c_evidence_rejects_identity_drift(tmp_path: Path) -> None:
    payload = _synthetic_payload()
    path = tmp_path / "e2c.json"
    path.write_text(canonical_json(payload), encoding="utf-8")
    with pytest.raises(RuntimeError, match="artifact_sha256"):
        load_e2c_evidence(path)


def test_load_e2c_evidence_rejects_tamper(tmp_path: Path) -> None:
    payload = _synthetic_payload()
    payload["deterministic"]["candidates"]["production_six_factor"]["median_return"] = 0.9
    path = tmp_path / "e2c.json"
    path.write_text(canonical_json(payload), encoding="utf-8")
    with pytest.raises(RuntimeError, match="integrity"):
        load_e2c_evidence(path)


# ---------------------------------------------------------------------------
# Research-only model adapter: budgets and per-role failure.
# ---------------------------------------------------------------------------


def test_call_role_model_success() -> None:
    summary = {"decision_date": _DECISION_SET[0]}
    proposals, failure = call_role_model(
        "alpha",
        summary,
        lambda _role, _summary: _json_proposal(
            "t2_comparator", "strengthen", "high", ["e1"]
        ),
    )
    assert failure is None
    assert proposals is not None and proposals[0].slot == "t2_comparator"


def test_call_role_model_timeout_drops_role() -> None:
    summary = {"decision_date": _DECISION_SET[0]}

    def _slow(_role: str, _summary: object) -> str:
        time.sleep(0.25)
        return "[]"

    proposals, failure = call_role_model(
        "alpha", summary, _slow, timeout_seconds=0.05
    )
    assert proposals is None
    assert failure is not None and "timed out" in failure


def test_call_role_model_parse_failure_drops_role() -> None:
    summary = {"decision_date": _DECISION_SET[0]}
    proposals, failure = call_role_model(
        "alpha", summary, lambda _role, _summary: "not json", timeout_seconds=1.0
    )
    assert proposals is None
    assert "schema violation" in failure


def test_call_role_model_output_too_large_drops_role() -> None:
    summary = {"decision_date": _DECISION_SET[0]}
    proposals, failure = call_role_model(
        "alpha",
        summary,
        lambda _role, _summary: "x" * (MAX_INPUT_TOKENS * 4),
        timeout_seconds=1.0,
    )
    assert proposals is None
    assert "token budget" in failure


def test_call_role_model_input_too_large_drops_role() -> None:
    proposals, failure = call_role_model(
        "alpha",
        {"decision_date": _DECISION_SET[0], "pad": "x" * (MAX_INPUT_TOKENS * 8)},
        lambda _role, _summary: "[]",
        timeout_seconds=1.0,
    )
    assert proposals is None
    assert "token budget" in failure


def test_call_role_model_call_error_drops_role() -> None:
    summary = {"decision_date": _DECISION_SET[0]}

    def _boom(_role: str, _summary: object) -> str:
        raise RuntimeError("provider down")

    proposals, failure = call_role_model("alpha", summary, _boom, timeout_seconds=1.0)
    assert proposals is None
    assert "model call failed" in failure


# ---------------------------------------------------------------------------
# Create-once bundle.
# ---------------------------------------------------------------------------


def test_run_proposal_bundle_calls_model_once_per_role() -> None:
    payload = _synthetic_payload()
    calls: list[tuple[str, str]] = []

    def _counting(role: str, summary: object) -> str:
        calls.append((role, summary["decision_date"]))
        return "[]"

    bundle = run_proposal_bundle(_DECISION_SET[0], payload, _counting)
    assert calls == [("alpha", _DECISION_SET[0]), ("risk_evidence", _DECISION_SET[0])]
    assert bundle.alpha.succeeded and bundle.risk.succeeded
    assert isinstance(bundle.bundle_sha256, str) and len(bundle.bundle_sha256) == 64
    second = run_proposal_bundle(_DECISION_SET[0], payload, _counting)
    assert bundle.bundle_sha256 == second.bundle_sha256


def test_run_proposal_bundle_role_failure_preserves_a0() -> None:
    payload = _synthetic_payload()

    def _failing_first(role: str, _summary: object) -> str:
        if role == "alpha":
            return "not json"
        return _json_proposal("production_six_factor", "hold", "medium", [])

    bundle = run_proposal_bundle(_DECISION_SET[0], payload, _failing_first)
    assert not bundle.alpha.succeeded and bundle.alpha.failure_reason is not None
    assert bundle.risk.succeeded
    registry = build_evidence_registry(payload)
    variants = evaluate_variants(bundle, _BASE, evidence_registry=registry)
    assert variants["A1_alpha_only"].final_weights == _BASE  # alpha dropped -> A0
    assert variants["A2_alpha_risk"].final_weights == _BASE  # risk only hold -> A0


def test_run_proposal_bundle_rejects_tampered_payload() -> None:
    payload = _synthetic_payload()
    payload["deterministic"]["windows"][0]["candidates"]["t2_comparator"][
        "total_return"
    ] = 0.99
    with pytest.raises(RuntimeError, match="integrity"):
        run_proposal_bundle(_DECISION_SET[0], payload, lambda _role, _summary: "[]")


# ---------------------------------------------------------------------------
# Assembler negative gates.
# ---------------------------------------------------------------------------


def _registry_with_availability(
    *,
    future: bool = False,
    expired: bool = False,
) -> dict[str, PITEvidenceRef]:
    decision_time = _decision_time(_DECISION_SET[0])
    if future:
        available_at = decision_time + timedelta(days=1)
        valid_until = decision_time + timedelta(days=2)
    elif expired:
        available_at = decision_time - timedelta(days=2)
        valid_until = decision_time - timedelta(days=1)
    else:
        available_at = decision_time
        valid_until = decision_time + timedelta(days=1)
    return {
        "e1": PITEvidenceRef("e1", "s1", available_at, valid_until),
        "e2": PITEvidenceRef("e2", "s2", available_at, valid_until),
        "e3": PITEvidenceRef("e3", "s3", available_at, valid_until),
    }


def test_assembler_future_evidence_drops_only_that_proposal() -> None:
    decision_time = _decision_time(_DECISION_SET[0])
    registry = _registry_with_availability(future=True)
    proposals = parse_role_output(
        "alpha",
        json.dumps(
            [
                {
                    "slot": "t2_comparator",
                    "signal": "strengthen",
                    "confidence": "high",
                    "evidence_ids": ["e1"],
                    "rationale": "r",
                },
                {
                    "slot": "production_six_factor",
                    "signal": "hold",
                    "confidence": "low",
                    "evidence_ids": [],
                    "rationale": "keep",
                },
            ]
        ),
        decision_time,
    )
    trace = StrategyAssembler.assemble(
        _BASE, proposals, decision_time=decision_time, evidence_registry=registry
    )
    assert any("future evidence" in (outcome.reason or "") for outcome in trace.outcomes)
    # The hold proposal on the fallback survives; final stays A0.
    assert trace.final_weights == _BASE
    assert len(trace.accepted) == 1


def test_assembler_expired_evidence_drops_proposal() -> None:
    decision_time = _decision_time(_DECISION_SET[0])
    registry = _registry_with_availability(expired=True)
    proposals = parse_role_output(
        "alpha", _json_proposal("t2_comparator", "strengthen", "high", ["e1"]), decision_time
    )
    trace = StrategyAssembler.assemble(
        _BASE, proposals, decision_time=decision_time, evidence_registry=registry
    )
    assert any("expired evidence" in (outcome.reason or "") for outcome in trace.outcomes)
    assert trace.final_weights == _BASE


def test_assembler_unknown_evidence_drops_proposal() -> None:
    decision_time = _decision_time(_DECISION_SET[0])
    registry = _registry_with_availability()
    proposals = parse_role_output(
        "alpha", _json_proposal("t2_comparator", "strengthen", "high", ["ghost"]), decision_time
    )
    trace = StrategyAssembler.assemble(
        _BASE, proposals, decision_time=decision_time, evidence_registry=registry
    )
    assert any("unknown evidence" in (outcome.reason or "") for outcome in trace.outcomes)
    assert trace.final_weights == _BASE


def test_assembler_evidence_reuse_across_proposals_rejected() -> None:
    decision_time = _decision_time(_DECISION_SET[0])
    registry = _registry_with_availability()
    proposals = parse_role_output(
        "alpha",
        json.dumps(
            [
                {
                    "slot": "t2_comparator",
                    "signal": "strengthen",
                    "confidence": "high",
                    "evidence_ids": ["e1"],
                    "rationale": "r1",
                },
                {
                    "slot": "production_six_factor",
                    "signal": "weaken",
                    "confidence": "medium",
                    "evidence_ids": ["e1"],
                    "rationale": "r2",
                },
            ]
        ),
        decision_time,
    )
    trace = StrategyAssembler.assemble(
        _BASE, proposals, decision_time=decision_time, evidence_registry=registry
    )
    assert any("reused across proposals" in (outcome.reason or "") for outcome in trace.outcomes)
    # Only the first proposal survives.
    assert len(trace.accepted) == 1


def test_assembler_excess_l1_drops_alpha_and_preserves_a0() -> None:
    decision_time = _decision_time(_DECISION_SET[0])
    registry = _registry_with_availability()
    # Three strengthen-high on one slot -> per-slot 0.30 and L1 0.30 > 0.20.
    items = [
        {
            "slot": "t2_comparator",
            "signal": "strengthen",
            "confidence": "high",
            "evidence_ids": [evidence],
            "rationale": f"r{index}",
        }
        for index, evidence in enumerate(("e1", "e2", "e3"))
    ]
    proposals = parse_role_output("alpha", json.dumps(items), decision_time)
    trace = StrategyAssembler.assemble(
        _BASE, proposals, decision_time=decision_time, evidence_registry=registry
    )
    assert "alpha" in trace.role_failures
    assert trace.final_weights == _BASE
    assert all(not outcome.accepted for outcome in trace.outcomes)


def test_assembler_max_l1_boundary_ok() -> None:
    decision_time = _decision_time(_DECISION_SET[0])
    registry = _registry_with_availability()
    # Strengthen high on both slots -> exactly 0.20 total L1, allowed.
    proposals = parse_role_output(
        "alpha",
        json.dumps(
            [
                {
                    "slot": "t2_comparator",
                    "signal": "strengthen",
                    "confidence": "high",
                    "evidence_ids": ["e1"],
                    "rationale": "r1",
                },
                {
                    "slot": "production_six_factor",
                    "signal": "weaken",
                    "confidence": "high",
                    "evidence_ids": ["e2"],
                    "rationale": "r2",
                },
            ]
        ),
        decision_time,
    )
    trace = StrategyAssembler.assemble(
        _BASE, proposals, decision_time=decision_time, evidence_registry=registry
    )
    assert not trace.role_failures
    assert len(trace.accepted) == 2
    total = sum(abs(value) for value in trace.net_deltas.values())
    assert total <= MAX_ALPHA_TOTAL_L1 + 1e-9


def test_assembler_unsupported_single_evidence_veto_rejected() -> None:
    decision_time = _decision_time(_DECISION_SET[0])
    registry = _registry_with_availability()
    proposals = parse_role_output(
        "risk_evidence", _json_proposal("t2_comparator", "veto", "high", ["e1"]), decision_time
    )
    trace = StrategyAssembler.assemble(
        _BASE, proposals, decision_time=decision_time, evidence_registry=registry
    )
    assert any("two independent" in (outcome.reason or "") for outcome in trace.outcomes)
    assert trace.excluded_slots == ()
    assert trace.final_weights == _BASE


def test_assembler_second_veto_rejected() -> None:
    decision_time = _decision_time(_DECISION_SET[0])
    registry = _registry_with_availability()
    proposals = parse_role_output(
        "risk_evidence",
        json.dumps(
            [
                {
                    "slot": "t2_comparator",
                    "signal": "veto",
                    "confidence": "high",
                    "evidence_ids": ["e1", "e2"],
                    "rationale": "r1",
                },
                {
                    "slot": "t2_comparator",
                    "signal": "veto",
                    "confidence": "high",
                    "evidence_ids": ["e2", "e3"],
                    "rationale": "r2",
                },
            ]
        ),
        decision_time,
    )
    trace = StrategyAssembler.assemble(
        _BASE, proposals, decision_time=decision_time, evidence_registry=registry
    )
    assert len(trace.accepted) == 1
    assert any("more than one veto" in (outcome.reason or "") for outcome in trace.outcomes)
    assert trace.excluded_slots == ("t2_comparator",)
    assert trace.final_weights == _BASE  # vetoed slot renormalises production back to 1.0


def test_assembler_fallback_veto_rejected() -> None:
    decision_time = _decision_time(_DECISION_SET[0])
    registry = _registry_with_availability()
    proposals = parse_role_output(
        "risk_evidence",
        _json_proposal("production_six_factor", "veto", "high", ["e1", "e2"]),
        decision_time,
    )
    trace = StrategyAssembler.assemble(
        _BASE, proposals, decision_time=decision_time, evidence_registry=registry
    )
    assert any("fallback slot" in (outcome.reason or "") for outcome in trace.outcomes)
    assert trace.excluded_slots == ()
    assert trace.final_weights == _BASE


def test_assembler_normalization_and_final_constraints() -> None:
    decision_time = _decision_time(_DECISION_SET[0])
    registry = _registry_with_availability()
    alpha = parse_role_output(
        "alpha", _json_proposal("t2_comparator", "strengthen", "high", ["e1"]), decision_time
    )
    risk = parse_role_output(
        "risk_evidence",
        _json_proposal("production_six_factor", "reduce", "low", ["e2"]),
        decision_time,
    )
    trace = StrategyAssembler.assemble(
        _BASE, alpha + risk, decision_time=decision_time, evidence_registry=registry
    )
    weights = dict(trace.final_weights)
    assert all(value >= 0.0 for value in weights.values())
    assert abs(sum(weights.values()) - 1.0) < 1e-9
    assert trace.net_deltas["t2_comparator"] == 0.10
    assert trace.net_deltas["production_six_factor"] == -0.02
    # t2 gains weight, production loses weight.
    assert weights["t2_comparator"] > 0.0
    assert weights["t2_comparator"] < weights["production_six_factor"]


def test_assembler_veto_excludes_and_renormalises() -> None:
    decision_time = _decision_time(_DECISION_SET[0])
    registry = _registry_with_availability()
    proposals = parse_role_output(
        "risk_evidence",
        _json_proposal("t2_comparator", "veto", "high", ["e1", "e2"]),
        decision_time,
    )
    trace = StrategyAssembler.assemble(
        _BASE, proposals, decision_time=decision_time, evidence_registry=registry
    )
    assert trace.excluded_slots == ("t2_comparator",)
    assert trace.final_weights == {"production_six_factor": 1.0, "t2_comparator": 0.0}


def test_assembler_hold_has_zero_effect() -> None:
    decision_time = _decision_time(_DECISION_SET[0])
    registry = _registry_with_availability()
    proposals = parse_role_output(
        "alpha", _json_proposal("production_six_factor", "hold", "low", []), decision_time
    )
    trace = StrategyAssembler.assemble(
        _BASE, proposals, decision_time=decision_time, evidence_registry=registry
    )
    assert trace.final_weights == _BASE
    assert trace.net_deltas == {"production_six_factor": 0.0, "t2_comparator": 0.0}


def test_assembler_base_state_validation() -> None:
    decision_time = _decision_time(_DECISION_SET[0])
    registry = _registry_with_availability()
    with pytest.raises(ValueError, match="cover exactly"):
        StrategyAssembler.assemble(
            {"production_six_factor": 1.0}, (), decision_time=decision_time
        )
    with pytest.raises(ValueError, match="non-negative"):
        StrategyAssembler.assemble(
            {"production_six_factor": 1.1, "t2_comparator": -0.1},
            (),
            decision_time=decision_time,
        )
    with pytest.raises(ValueError, match="sum to 1.0"):
        StrategyAssembler.assemble(
            {"production_six_factor": 0.5, "t2_comparator": 0.2},
            (),
            decision_time=decision_time,
        )
    with pytest.raises(ValueError, match="timezone-aware"):
        StrategyAssembler.assemble(
            _BASE, (), decision_time=datetime(2025, 1, 14), evidence_registry=registry
        )


# ---------------------------------------------------------------------------
# Variants, determinism and cache isolation.
# ---------------------------------------------------------------------------


def test_variants_are_independent_and_deterministic() -> None:
    payload = _synthetic_payload()
    decision = _DECISION_SET[2]
    registry = build_evidence_registry(payload, decision)
    evidence_ids = sorted(registry)

    def _model(role: str, _summary: object) -> str:
        if role == "alpha":
            return _json_proposal("t2_comparator", "strengthen", "medium", [evidence_ids[0]])
        return _json_proposal("production_six_factor", "reduce", "low", [evidence_ids[1]])

    bundle = run_proposal_bundle(decision, payload, _model)
    first = evaluate_variants(bundle, _BASE, evidence_registry=registry)
    second = evaluate_variants(bundle, _BASE, evidence_registry=registry)
    assert set(first) == {"A0_no_agent", "A1_alpha_only", "A2_alpha_risk"}
    assert first["A0_no_agent"].final_weights == _BASE
    assert (
        first["A2_alpha_risk"].final_weights
        == second["A2_alpha_risk"].final_weights
    )
    a1_t2 = first["A1_alpha_only"].final_weights["t2_comparator"]
    a2_t2 = first["A2_alpha_risk"].final_weights["t2_comparator"]
    assert a1_t2 > first["A0_no_agent"].final_weights["t2_comparator"]
    # Risk's non-positive production adjustment tilts the blend further to t2.
    assert a2_t2 > a1_t2


def test_variants_do_not_recall_the_model() -> None:
    payload = _synthetic_payload()
    registry = build_evidence_registry(payload)
    calls: list[str] = []

    def _counting(_role: str, _summary: object) -> str:
        calls.append("call")
        return "[]"

    bundle = run_proposal_bundle(_DECISION_SET[0], payload, _counting)
    assert len(calls) == 2  # one per role, create-once
    evaluate_variants(bundle, _BASE, evidence_registry=registry)
    assert len(calls) == 2  # variants reuse the same bundle


# ---------------------------------------------------------------------------
# Joint identity hash.
# ---------------------------------------------------------------------------


def test_joint_identity_hash_deterministic_and_sensitive(monkeypatch: pytest.MonkeyPatch) -> None:
    import evaluation.strategy_fusion_replay as sfr

    decision_set = list(_DECISION_SET)
    first = joint_identity_hash(
        artifact_sha256=EXPECTED_E2C_ARTIFACT_SHA256,
        inventory_hash=EXPECTED_E2C_INVENTORY_HASH,
        decision_set=decision_set,
    )
    second = joint_identity_hash(
        artifact_sha256=EXPECTED_E2C_ARTIFACT_SHA256,
        inventory_hash=EXPECTED_E2C_INVENTORY_HASH,
        decision_set=list(decision_set),
    )
    assert first == second
    assert joint_identity_hash(
        artifact_sha256="a" * 64,
        inventory_hash=EXPECTED_E2C_INVENTORY_HASH,
        decision_set=decision_set,
    ) != first
    assert joint_identity_hash(
        artifact_sha256=EXPECTED_E2C_ARTIFACT_SHA256,
        inventory_hash="b" * 64,
        decision_set=decision_set,
    ) != first
    monkeypatch.setattr(sfr, "MODEL_VERSION", "different-model-version")
    assert sfr.joint_identity_hash(
        artifact_sha256=EXPECTED_E2C_ARTIFACT_SHA256,
        inventory_hash=EXPECTED_E2C_INVENTORY_HASH,
        decision_set=decision_set,
    ) != first


# ---------------------------------------------------------------------------
# Fusion serialization.
# ---------------------------------------------------------------------------


def _fusion_payload() -> dict[str, object]:
    payload = _synthetic_payload()
    decision = _DECISION_SET[2]
    registry = build_evidence_registry(payload, decision)
    bundle = run_proposal_bundle(
        decision, payload, lambda _role, _summary: "[]"
    )
    variants = evaluate_variants(bundle, _BASE, evidence_registry=registry)
    identity = joint_identity_hash(
        artifact_sha256=EXPECTED_E2C_ARTIFACT_SHA256,
        inventory_hash=EXPECTED_E2C_INVENTORY_HASH,
        decision_set=list(_DECISION_SET),
    )
    return build_fusion_payload(
        decision_date=decision,
        base_slot_state=_BASE,
        variants=variants,
        identity_hash=identity,
    )


def test_fusion_payload_deterministic_and_tamper_detected() -> None:
    first = _fusion_payload()
    assert verify_fusion_payload(first)
    second = _fusion_payload()
    assert first["artifact_sha256"] == second["artifact_sha256"]
    tampered = _copy(first)
    tampered["deterministic"]["windows"][0]["variants"]["A2_alpha_risk"]["final_weights"][
        "t2_comparator"
    ] = 0.5
    assert not verify_fusion_payload(tampered)


def test_verify_fusion_payload_rejects_missing() -> None:
    assert not verify_fusion_payload({})
    assert not verify_fusion_payload(None)


# ---------------------------------------------------------------------------
# Production / direct / formal isolation.
# ---------------------------------------------------------------------------


def test_production_import_isolation() -> None:
    for relative in (
        "jiuwenswarm/evaluation/run_multi_agent.py",
        "jiuwenswarm/scripts/run_quant_pipeline.py",
        "jiuwenswarm/jiuwenswarm/extensions/quant-finance/extension.py",
    ):
        source = (_REPO_ROOT / relative).read_text(encoding="utf-8", errors="replace")
        assert "strategy_fusion_replay" not in source, relative


def test_module_never_imports_extension_or_network() -> None:
    source = (_REPO_ROOT / "jiuwenswarm/evaluation/strategy_fusion_replay.py").read_text(
        encoding="utf-8", errors="replace"
    )
    assert "extension.py" not in source
    assert "import extension" not in source
    for forbidden in ("api_key", "requests.", "openai", "httpx", "http://"):
        assert forbidden not in source


def test_extension_overlay_stays_disabled() -> None:
    extension_path = (
        _REPO_ROOT / "jiuwenswarm/jiuwenswarm/extensions/quant-finance/extension.py"
    )
    source = extension_path.read_text(encoding="utf-8", errors="replace")
    assert "AGENT_OVERLAY_ENABLED = False" in source


def test_default_artifact_path_is_untracked_output() -> None:
    # The fusion oracle is the untracked output/ artifact or a deterministic
    # regeneration; it must never be under jiuwenswarm/evaluation (product tree).
    assert "output" in DEFAULT_E2C_ARTIFACT_PATH.parts
    assert "evaluation" not in DEFAULT_E2C_ARTIFACT_PATH.parts


# ---------------------------------------------------------------------------
# Frozen role/signal vocabularies.
# ---------------------------------------------------------------------------


def test_role_and_signal_vocabularies() -> None:
    assert VALID_ROLES == ("alpha", "risk_evidence")
    assert ALPHA_SIGNALS == ("strengthen", "weaken", "hold")
    assert RISK_SIGNALS == ("reduce", "veto", "hold")
    assert VALID_CONFIDENCE == ("high", "medium", "low")
    assert MIN_VETO_EVIDENCE_COUNT == 2
    assert PER_ROLE_TIMEOUT_SECONDS == 45.0
