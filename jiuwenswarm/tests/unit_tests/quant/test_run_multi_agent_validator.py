"""Regression tests for fail-closed formal quant RPC validation."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


SCRIPT = Path(__file__).resolve().parents[3] / "evaluation" / "run_multi_agent.py"
SPEC = importlib.util.spec_from_file_location("run_multi_agent_validator", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _valid_fetch() -> dict:
    return {
        "success": True,
        "coverage_complete": True,
        "n_stocks": MODULE.EXPECTED_STOCKS,
        "expected_stocks": MODULE.EXPECTED_STOCKS,
    }


def _valid_report() -> dict:
    candidate_id = "formal-multi-agent-validation-test"
    binding = {
        "schema": "candidate_artifact_binding/v1",
        "candidate_id": candidate_id,
        "snapshot_id": "snapshot-1",
        "report_count": MODULE.EXPECTED_STOCKS,
        "announcement_facts": 1470,
        "disclosure_reports": MODULE.EXPECTED_STOCKS,
        "snapshot_manifest_sha256": "a" * 64,
        "report_manifest_sha256": "b" * 64,
        "evidence_manifest_sha256": "c" * 64,
        "company_reports_tree_sha256": "d" * 64,
        "binding_sha256": "e" * 64,
        "candidate_binding_file_sha256": "f" * 64,
    }
    return {
        "success": True,
        "report": "report",
        "summary": {"n_holdings": 15},
        "candidate_package": {
            "path": f"/tmp/output/submission_candidates/{candidate_id}",
            "candidate_id": candidate_id,
            "immutable": True,
            "quality_passed": True,
            "n_reports": MODULE.EXPECTED_STOCKS,
            "snapshot_id": "snapshot-1",
            "announcement_facts": 1470,
            "disclosure_reports": MODULE.EXPECTED_STOCKS,
            "artifact_binding": binding,
        },
    }


def test_valid_single_rpc_marks_phase_complete() -> None:
    phases, issues = MODULE._validate_quant_rpc_calls(
        [{"method": "quant.fetch_data", "payload": _valid_fetch()}]
    )

    assert phases["fetch"] is True
    assert issues == []


def test_later_success_cannot_hide_an_earlier_failed_rpc() -> None:
    phases, issues = MODULE._validate_quant_rpc_calls(
        [
            {"method": "quant.fetch_data", "payload": {"success": False}},
            {"method": "quant.fetch_data", "payload": _valid_fetch()},
        ]
    )

    assert phases["fetch"] is False
    assert issues == [
        "quant.fetch_data returned 1 unsuccessful or invalid result(s)"
    ]


def test_report_phase_requires_immutable_candidate_binding() -> None:
    assert MODULE._phase_payload_valid("report", _valid_report()) is True

    mutable = _valid_report()
    mutable["candidate_package"]["path"] = "/tmp/output/submission_candidate"
    assert MODULE._phase_payload_valid("report", mutable) is False

    unbound = _valid_report()
    unbound["candidate_package"].pop("artifact_binding")
    assert MODULE._phase_payload_valid("report", unbound) is False


@pytest.mark.asyncio
async def test_formal_loader_requests_and_accepts_exact_quant_team() -> None:
    captured: dict[str, object] = {}
    spec = SimpleNamespace(
        team_name="quant_team_formal-session",
        leader=SimpleNamespace(member_name="quant-leader"),
        predefined_members=[
            SimpleNamespace(member_name="alpha_analyst"),
            SimpleNamespace(member_name="risk_evidence_analyst"),
        ],
    )

    class FakeTeamManager:
        async def get_swarm_enriched_team_spec(self, **kwargs):
            captured.update(kwargs)
            return spec

    result = await MODULE._load_formal_team_spec(
        FakeTeamManager(), session_id="formal-session"
    )

    assert result is spec
    assert captured["requested_team_name"] == "quant_team"


@pytest.mark.asyncio
async def test_formal_loader_rejects_wrong_team_before_runner_execution() -> None:
    spec = SimpleNamespace(
        team_name="jiuwen_team_formal-session",
        leader=SimpleNamespace(member_name="team-leader"),
        predefined_members=[],
    )

    class FakeTeamManager:
        async def get_swarm_enriched_team_spec(self, **_kwargs):
            return spec

    with pytest.raises(RuntimeError, match="formal team identity mismatch"):
        await MODULE._load_formal_team_spec(
            FakeTeamManager(), session_id="formal-session"
        )


@pytest.mark.asyncio
async def test_formal_loader_rejects_duplicate_predefined_role() -> None:
    spec = SimpleNamespace(
        team_name="quant_team_formal-session",
        leader=SimpleNamespace(member_name="quant-leader"),
        predefined_members=[
            SimpleNamespace(member_name="alpha_analyst"),
            SimpleNamespace(member_name="alpha_analyst"),
            SimpleNamespace(member_name="risk_evidence_analyst"),
        ],
    )

    class FakeTeamManager:
        async def get_swarm_enriched_team_spec(self, **_kwargs):
            return spec

    with pytest.raises(RuntimeError, match="formal team identity mismatch"):
        await MODULE._load_formal_team_spec(
            FakeTeamManager(), session_id="formal-session"
        )


@pytest.mark.asyncio
async def test_formal_loader_uses_runtime_session_name_normalization() -> None:
    spec = SimpleNamespace(
        team_name="quant_team_formal_session",
        leader=SimpleNamespace(member_name="quant-leader"),
        predefined_members=[
            SimpleNamespace(member_name="alpha_analyst"),
            SimpleNamespace(member_name="risk_evidence_analyst"),
        ],
    )

    class FakeTeamManager:
        async def get_swarm_enriched_team_spec(self, **_kwargs):
            return spec

    result = await MODULE._load_formal_team_spec(
        FakeTeamManager(), session_id="formal/session"
    )

    assert result is spec


@pytest.mark.asyncio
async def test_bad_formal_team_is_rejected_before_runner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner_called = False
    spec = SimpleNamespace(
        team_name=f"jiuwen_team_{MODULE.SESSION_ID}",
        leader=SimpleNamespace(member_name="team-leader"),
        predefined_members=[],
    )

    class FakeTeamManager:
        async def get_swarm_enriched_team_spec(self, **_kwargs):
            return spec

    async def fake_init_extensions() -> None:
        return None

    def fail_if_runner_called(*_args, **_kwargs):
        nonlocal runner_called
        runner_called = True
        raise AssertionError("Runner must not be called for a mismatched formal team")

    monkeypatch.setattr(MODULE, "_init_extensions", fake_init_extensions)
    monkeypatch.setattr(MODULE, "get_team_manager", FakeTeamManager)
    monkeypatch.setattr(MODULE.Runner, "run_agent_team_streaming", fail_if_runner_called)

    with pytest.raises(RuntimeError, match="formal team identity mismatch"):
        await MODULE.run_multi_agent_team("test prompt")

    assert runner_called is False
