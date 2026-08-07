"""Regression tests for fail-closed formal quant RPC validation."""

from __future__ import annotations

import asyncio
import importlib.util
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


SCRIPT = Path(__file__).resolve().parents[3] / "evaluation" / "run_multi_agent.py"
SPEC = importlib.util.spec_from_file_location("run_multi_agent_validator", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
MARKET_HASH = "9" * 64


def _bound(payload: dict) -> dict:
    return {
        **payload,
        "market_content_sha256": MARKET_HASH,
        "cached": False,
        "executed": True,
    }


def _valid_fetch() -> dict:
    return _bound({
        "success": True,
        "coverage_complete": True,
        "n_stocks": MODULE.EXPECTED_STOCKS,
        "expected_stocks": MODULE.EXPECTED_STOCKS,
    })


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
    return _bound({
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
    })


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
    assert issues == ["quant.fetch_data returned an invalid stage payload"]


def test_report_phase_requires_immutable_candidate_binding() -> None:
    assert MODULE._phase_payload_valid("report", _valid_report()) is True

    mutable = _valid_report()
    mutable["candidate_package"]["path"] = "/tmp/output/submission_candidate"
    assert MODULE._phase_payload_valid("report", mutable) is False

    unbound = _valid_report()
    unbound["candidate_package"].pop("artifact_binding")
    assert MODULE._phase_payload_valid("report", unbound) is False


def test_role_usage_requires_every_formal_role_and_field() -> None:
    chunks = [
        {
            "type": "llm_usage",
            "source_member": "quant-leader",
            "payload": {"usage_metadata": {
                "input_tokens": 100,
                "output_tokens": 10,
                "cache_tokens": 4,
            }},
        },
        {
            "type": "llm_usage",
            "source_member": "alpha-analyst",
            "payload": {"usage_metadata": {
                "input_tokens": 20,
                "output_tokens": 5,
                "cache_tokens": 0,
            }},
        },
        {
            "type": "llm_usage",
            "source_member": "risk_evidence_analyst",
            "payload": {"usage_metadata": {
                "input_tokens": 30,
                "output_tokens": 6,
            }},
        },
        {
            "type": "llm_usage",
            "source_member": "unknown-role",
            "payload": {"usage_metadata": {"input_tokens": 999_999}},
        },
    ]

    usage = MODULE._aggregate_role_usage(chunks)

    assert tuple(usage) == MODULE.FORMAL_ROLES
    assert MODULE._complete_role_total(usage, "input_tokens") == 150
    assert MODULE._complete_role_total(usage, "output_tokens") == 21
    assert MODULE._complete_role_total(usage, "cache_tokens") is None


def test_one_missing_usage_field_invalidates_known_fragments() -> None:
    chunks = []
    for role in MODULE.FORMAL_ROLES:
        chunks.append({
            "type": "llm_usage",
            "source_member": role,
            "payload": {"usage_metadata": {
                "input_tokens": 100,
                "output_tokens": 10,
                "cache_tokens": 0,
            }},
        })
    chunks.append({
        "type": "llm_usage",
        "source_member": "quant-leader",
        "payload": {"usage_metadata": {"output_tokens": 1, "cache_tokens": 0}},
    })

    usage = MODULE._aggregate_role_usage(chunks)

    assert usage["quant-leader"]["input_tokens"] is None
    assert usage["quant-leader"]["output_tokens"] == 11
    assert MODULE._complete_role_total(usage, "input_tokens") is None
    assert MODULE._complete_role_total(usage, "output_tokens") == 31


def test_formal_tool_schema_rejects_missing_runtime_card() -> None:
    class Card:
        def __init__(self, name: str):
            self.name = name
            self.description = name
            self.input_params = {"type": "object"}

    class Tool:
        def __init__(self, name: str):
            self.card = Card(name)

    class CompleteToolkit:
        def get_tools(self):
            return [
                Tool(name)
                for name in sorted(set().union(*MODULE.FORMAL_ROLE_TOOL_NAMES.values()))
            ]

    result = MODULE._formal_tool_schema(CompleteToolkit)
    assert result["tool_count"] == 8

    class IncompleteToolkit:
        def get_tools(self):
            return CompleteToolkit().get_tools()[:-1]

    with pytest.raises(RuntimeError, match="missing"):
        MODULE._formal_tool_schema(IncompleteToolkit)


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


@pytest.mark.asyncio
async def test_formal_teardown_closes_session_stream_and_global_runner_in_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    class TeamManager:
        async def stop_session_runtime(self, session_id: str, reason: str) -> bool:
            assert session_id == "formal-session"
            assert reason == "formal validation teardown"
            calls.append("session")
            return True

    class Stream:
        async def aclose(self) -> None:
            calls.append("stream")

    async def stop_runner() -> bool:
        calls.append("runner")
        return True

    monkeypatch.setattr(MODULE.Runner, "stop", stop_runner)

    report = await MODULE._teardown_formal_runtime(
        TeamManager(), Stream(), session_id="formal-session"
    )

    assert calls == ["session", "stream", "runner"]
    assert report["normal_shutdown"] is True
    assert report["issues"] == []
    assert all(step["completed"] for step in report["steps"].values())


@pytest.mark.asyncio
async def test_untracked_team_session_is_not_a_false_shutdown_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class TeamManager:
        async def stop_session_runtime(self, *_args, **_kwargs) -> bool:
            return False

    async def stop_runner() -> bool:
        return True

    monkeypatch.setattr(MODULE.Runner, "stop", stop_runner)

    report = await MODULE._teardown_formal_runtime(
        TeamManager(), None, session_id="formal-session"
    )

    assert report["normal_shutdown"] is True
    assert report["steps"]["team_session_stop"]["completed"] is True
    assert report["steps"]["team_session_stop"]["return_value"] is False


@pytest.mark.asyncio
async def test_formal_teardown_retains_all_errors_and_continues_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    class TeamManager:
        async def stop_session_runtime(self, *_args, **_kwargs) -> bool:
            calls.append("session")
            raise ValueError("session exploded")

    class Stream:
        async def aclose(self) -> None:
            calls.append("stream")
            raise OSError("stream exploded")

    async def stop_runner() -> bool:
        calls.append("runner")
        raise KeyError("runner exploded")

    monkeypatch.setattr(MODULE.Runner, "stop", stop_runner)

    report = await MODULE._teardown_formal_runtime(
        TeamManager(), Stream(), session_id="formal-session"
    )

    assert calls == ["session", "stream", "runner"]
    assert report["normal_shutdown"] is False
    assert len(report["issues"]) == 3
    assert "ValueError: session exploded" in report["issues"][0]
    assert "OSError: stream exploded" in report["issues"][1]
    assert "KeyError" in report["issues"][2]


@pytest.mark.asyncio
async def test_formal_teardown_records_timeouts_and_false_runner_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class TeamManager:
        async def stop_session_runtime(self, *_args, **_kwargs) -> bool:
            await asyncio.Event().wait()
            return True

    async def stop_runner() -> bool:
        return False

    monkeypatch.setattr(MODULE.Runner, "stop", stop_runner)

    report = await MODULE._teardown_formal_runtime(
        TeamManager(),
        None,
        session_id="formal-session",
        session_timeout_seconds=0.01,
    )

    assert report["normal_shutdown"] is False
    assert report["steps"]["team_session_stop"]["completed"] is False
    assert "timeout after 0.01s" in report["issues"][0]
    assert report["steps"]["stream_close"]["skipped"] is True
    assert report["steps"]["runner_stop"]["return_value"] is False
    assert "runner_stop returned false" in report["issues"]


@pytest.mark.asyncio
async def test_timeout_proceeds_when_cleanup_suppresses_cancellation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    allow_exit = asyncio.Event()

    class TeamManager:
        async def stop_session_runtime(self, *_args, **_kwargs) -> bool:
            calls.append("session")
            while not allow_exit.is_set():
                try:
                    await asyncio.sleep(0)
                except asyncio.CancelledError:
                    continue
            return True

    async def stop_runner() -> bool:
        calls.append("runner")
        return True

    monkeypatch.setattr(MODULE.Runner, "stop", stop_runner)

    report = await MODULE._teardown_formal_runtime(
        TeamManager(),
        None,
        session_id="formal-session",
        session_timeout_seconds=0.01,
    )

    assert calls == ["session", "runner"]
    assert report["normal_shutdown"] is False
    assert report["pending_cancellation_count"] == 1
    assert report["steps"]["team_session_stop"]["cancellation_pending"] is True
    allow_exit.set()
    for _ in range(10):
        await asyncio.sleep(0)
        if not MODULE._PENDING_TEARDOWN_TASKS:
            break
    assert not MODULE._PENDING_TEARDOWN_TASKS


@pytest.mark.asyncio
async def test_main_returns_exit_code_without_forced_process_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def passing_run(_prompt: str, timeout_seconds: int):
        assert timeout_seconds == 600
        return {
            "validation_passed": True,
            "quant_phases": {phase: True for phase in MODULE.QUANT_PHASE_METHODS},
            "multi_agent_working": True,
            "stats": {"tool_calls": 8, "text_segments": 1, "errors": 0},
            "elapsed_seconds": 1.0,
            "issues": None,
        }, []

    monkeypatch.setattr(MODULE, "run_multi_agent_team", passing_run)

    assert await MODULE.main([]) == 0
    source = SCRIPT.read_text(encoding="utf-8")
    # main() completes teardown and returns the exit code; forced process exit
    # is only applied by the win32-only helper after asyncio.run returns.
    assert "os_env._exit" in source
    assert 'sys.platform == "win32"' in source
    assert "raise SystemExit(_run_cli())" in source


def test_supervisor_returns_healthy_worker_exit_code() -> None:
    captured: dict[str, object] = {}

    class Process:
        def wait(self, timeout: float) -> int:
            captured["timeout"] = timeout
            return 0

    def popen(command, *, env):
        captured["command"] = command
        captured["env"] = env
        return Process()

    result = MODULE._supervise_formal_worker(
        ["--end-date", "2026-08-05"],
        timeout_seconds=12.5,
        popen_factory=popen,
    )

    assert result == 0
    assert captured["timeout"] == 12.5
    command = captured["command"]
    assert command[:2] == [
        sys.executable,
        str(SCRIPT.resolve()),
    ]
    assert command[2:] == ["--end-date", "2026-08-05"]
    assert captured["env"][MODULE.FORMAL_WORKER_PARENT_ENV] == str(
        MODULE.os_env.getpid()
    )


def test_supervisor_terminates_only_timed_out_formal_worker() -> None:
    calls: list[tuple[str, float | None]] = []

    class Process:
        def wait(self, timeout: float) -> int:
            calls.append(("wait", timeout))
            if len(calls) == 1:
                raise subprocess.TimeoutExpired("formal-worker", timeout)
            return -15

        def terminate(self) -> None:
            calls.append(("terminate", None))

        def kill(self) -> None:
            raise AssertionError("cooperative worker termination should be enough")

    result = MODULE._supervise_formal_worker(
        [],
        timeout_seconds=0.01,
        popen_factory=lambda _command, **_kwargs: Process(),
    )

    assert result == 1
    assert calls == [("wait", 0.01), ("terminate", None), ("wait", 10.0)]


def test_parent_pid_bound_worker_marker_prevents_recursive_supervision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_main(argv: list[str]) -> int:
        assert argv == ["--end-date", "2026-08-05"]
        return 7

    monkeypatch.setattr(MODULE, "main", fake_main)
    monkeypatch.setattr(
        MODULE,
        "_supervise_formal_worker",
        lambda _argv: (_ for _ in ()).throw(AssertionError("must not recurse")),
    )
    forced: list[int] = []
    monkeypatch.setattr(
        MODULE,
        "_force_worker_exit",
        lambda rc: forced.append(rc),
    )
    monkeypatch.setenv(
        MODULE.FORMAL_WORKER_PARENT_ENV,
        str(MODULE.os_env.getppid()),
    )

    assert MODULE._run_cli([
        "--end-date",
        "2026-08-05",
    ]) == 7
    assert forced == [7]

    monkeypatch.setenv(MODULE.FORMAL_WORKER_PARENT_ENV, "1")
    assert MODULE._run_cli([]) == 2
    assert forced == [7]


def test_worker_accepts_supervisor_in_ancestor_chain_on_windows_venv(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Windows venv redirector stub inserts a process between supervisor and
    worker; the supervisor pid must still be accepted from the ancestor chain."""

    class PsutilProcess:
        def __init__(self, pid: int) -> None:
            self.pid = pid

        def parent(self) -> PsutilProcess | None:
            # worker(36744) -> venv stub(20392) -> supervisor(44168) -> None
            parents = {36744: 20392, 20392: 44168}
            next_pid = parents.get(self.pid)
            if next_pid is None:
                return None
            return PsutilProcess(next_pid)

    fake_psutil = SimpleNamespace(
        Process=PsutilProcess,
        Error=RuntimeError,
    )
    monkeypatch.setitem(sys.modules, "psutil", fake_psutil)
    # worker reports the venv stub as its direct parent on Windows
    monkeypatch.setattr(MODULE.os_env, "getppid", lambda: 20392)

    assert MODULE._worker_has_parent(44168) is True
    assert MODULE._worker_has_parent(20392) is True


def test_worker_rejects_unrelated_pid_and_psutil_failure(monkeypatch) -> None:
    """A pid not in the ancestor chain and any psutil error both fail closed."""

    class PsutilProcess:
        def __init__(self, pid: int) -> None:
            self.pid = pid

        def parent(self) -> None:
            return None

    fake_psutil = SimpleNamespace(
        Process=PsutilProcess,
        Error=RuntimeError,
    )
    monkeypatch.setitem(sys.modules, "psutil", fake_psutil)
    monkeypatch.setattr(MODULE.os_env, "getppid", lambda: 20392)

    assert MODULE._worker_has_parent(999999) is False

    class ErrorProcess:
        def __init__(self, pid: int) -> None:
            self.pid = pid

        def parent(self) -> None:
            raise RuntimeError("access denied")

    fake_error = SimpleNamespace(
        Process=ErrorProcess,
        Error=RuntimeError,
    )
    monkeypatch.setitem(sys.modules, "psutil", fake_error)
    assert MODULE._worker_has_parent(44168) is False

    monkeypatch.setitem(sys.modules, "psutil", None)
    assert MODULE._worker_has_parent(44168) is False


def test_timeout_terminates_recursive_worker_descendants(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    child_calls: list[str] = []
    parent_calls: list[str] = []

    class Child:
        def terminate(self) -> None:
            child_calls.append("terminate")

        def kill(self) -> None:
            child_calls.append("kill")

    child = Child()

    class PsutilProcess:
        def __init__(self, pid: int) -> None:
            assert pid == 4312

        def children(self, *, recursive: bool):
            assert recursive is True
            return [child]

    wait_calls = 0

    def wait_procs(processes, *, timeout: float):
        nonlocal wait_calls
        assert processes == [child]
        assert timeout == 0.25
        wait_calls += 1
        return ([], [child]) if wait_calls == 1 else ([child], [])

    fake_psutil = SimpleNamespace(
        Process=PsutilProcess,
        Error=RuntimeError,
        wait_procs=wait_procs,
    )
    monkeypatch.setitem(sys.modules, "psutil", fake_psutil)

    class Process:
        pid = 4312

        def terminate(self) -> None:
            parent_calls.append("terminate")

        def wait(self, *, timeout: float) -> int:
            assert timeout == 0.25
            parent_calls.append("wait")
            return -15

    MODULE._terminate_formal_worker_tree(Process(), grace_seconds=0.25)

    assert child_calls == ["terminate", "kill"]
    assert parent_calls == ["terminate", "wait"]
    assert wait_calls == 2


def test_worker_tree_kill_timeout_is_bounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "psutil", None)
    calls: list[str] = []

    class Process:
        pid = 4312

        def terminate(self) -> None:
            calls.append("terminate")

        def kill(self) -> None:
            calls.append("kill")

        def wait(self, *, timeout: float) -> int:
            assert timeout == 0.01
            calls.append("wait")
            raise subprocess.TimeoutExpired("formal-worker", timeout)

    MODULE._terminate_formal_worker_tree(Process(), grace_seconds=0.01)

    assert calls == ["terminate", "wait", "kill", "wait"]


def test_psutil_lookup_failure_still_terminates_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    class PsutilError(Exception):
        pass

    class PsutilProcess:
        def __init__(self, pid: int) -> None:
            assert pid == 4312

        def children(self, *, recursive: bool):
            assert recursive is True
            raise PsutilError("access denied")

    fake_psutil = SimpleNamespace(
        Process=PsutilProcess,
        Error=PsutilError,
        wait_procs=lambda *_args, **_kwargs: ([], []),
    )
    monkeypatch.setitem(sys.modules, "psutil", fake_psutil)

    class Process:
        pid = 4312

        def wait(self, *, timeout: float) -> int:
            calls.append("wait")
            if len(calls) == 1:
                raise subprocess.TimeoutExpired("formal-worker", timeout)
            return -15

        def terminate(self) -> None:
            calls.append("terminate")

        def kill(self) -> None:
            raise AssertionError("terminate should be sufficient")

    result = MODULE._supervise_formal_worker(
        [],
        timeout_seconds=0.01,
        popen_factory=lambda _command, **_kwargs: Process(),
    )

    assert result == 1
    assert calls == ["wait", "terminate", "wait"]


def test_separate_tool_results_trip_same_failure_guard_on_third_result() -> None:
    pending: dict[str, str] = {}
    guard = MODULE.ToolProgressGuard(max_identical_calls=10)
    reason = None

    for index in range(3):
        call_id = f"call-{index}"
        call_chunk = {
            "type": "tool_call",
            "payload": {
                "tool_call": {
                    "tool_call_id": call_id,
                    "name": " send_message " if index == 1 else "send_message",
                    "arguments": {"revision": index},
                }
            },
        }
        tool_call = MODULE._extract_tool_call(call_chunk)
        assert tool_call is not None
        pending[tool_call["call_id"]] = tool_call["name"]
        assert guard.record_tool_call(tool_call) is None

        result_chunk = {
            "type": "tool_result",
            "payload": {
                "tool_result": {
                    "tool_call_id": call_id,
                    "status": "error",
                    "success": False,
                    "is_error": True,
                    "result": f"failure-{index}",
                }
            },
        }
        outcome = MODULE._extract_tool_result(result_chunk, pending)
        assert outcome is not None
        reason = guard.record_tool_call(outcome)

    assert reason == (
        "CONSECUTIVE_TOOL_FAILURE_LIMIT: tool=send_message "
        "count=3 last_error=failure-2"
    )
    assert pending == {}
    assert guard.as_dict()["failure_reason_code"] == (
        "CONSECUTIVE_TOOL_FAILURE_LIMIT"
    )


def test_successful_separate_tool_result_resets_failure_sequence() -> None:
    pending = {"call-1": "send_message"}
    guard = MODULE.ToolProgressGuard(max_identical_calls=10)
    assert guard.record_tool_call({
        "event_type": "tool_result",
        "name": "send_message",
        "result": {"success": False, "error": "first"},
    }) is None

    outcome = MODULE._extract_tool_result({
        "type": "tool_result",
        "payload": {
            "tool_result": {
                "tool_call_id": "call-1",
                "status": "done",
                "success": True,
                "result": "delivered",
            }
        },
    }, pending)

    assert outcome is not None
    assert guard.record_tool_call(outcome) is None
    assert guard.as_dict()["consecutive_failure_count"] == 0


def test_tool_result_requires_one_known_matching_pending_call() -> None:
    pending = {"call-1": "send_message"}
    mismatch = MODULE._extract_tool_result({
        "type": "tool_result",
        "payload": {"tool_result": {
            "tool_call_id": "call-1",
            "tool_name": "quant.fetch",
            "success": False,
        }},
    }, pending)
    assert mismatch is not None
    assert mismatch["binding_error"] == (
        "TOOL_RESULT_NAME_MISMATCH: call_id=call-1 "
        "expected=send_message actual=quant.fetch"
    )
    assert pending == {}

    duplicate = MODULE._extract_tool_result({
        "type": "tool_result",
        "payload": {"tool_result": {
            "tool_call_id": "call-1",
            "tool_name": "send_message",
            "success": False,
        }},
    }, pending)
    assert duplicate is not None
    assert duplicate["binding_error"] == "TOOL_RESULT_UNKNOWN_CALL_ID: call-1"

    missing = MODULE._extract_tool_result({
        "type": "tool_result",
        "payload": {"tool_result": {
            "tool_name": "send_message",
            "success": False,
        }},
    }, pending)
    assert missing is not None
    assert missing["binding_error"] == "TOOL_RESULT_MISSING_CALL_ID"
