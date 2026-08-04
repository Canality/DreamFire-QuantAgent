#!/usr/bin/env python3
r"""
Multi-Agent Quant Team — Programmatic Validation Script.

Runs the full Coordinator + Alpha Analyst + Risk & Evidence Analyst
multi-agent workflow via Runner.run_agent_team_streaming(), capturing
all agent interactions,
tool calls, and final output.

Usage:
  cd D:\比赛\HUAWEI\Track_2\jiuwenswarm
  python evaluation/run_multi_agent.py
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import sys
import time
from datetime import date, datetime, timedelta, timezone
from datetime import time as datetime_time
from pathlib import Path
from zoneinfo import ZoneInfo

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ── Early init ─────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

os_env = __import__("os")
# Ensure working directory is the jiuwenswarm project root so relative
# paths in config (e.g. jiuwenswarm/extensions) resolve correctly.
os_env.chdir(str(PROJECT_ROOT))

# These imports intentionally occur after the project-root bootstrap.  Using
# importlib keeps the script runnable from either the repository root or the
# jiuwenswarm subdirectory without relying on linter-specific E402 ignores.
load_dotenv = importlib.import_module("dotenv").load_dotenv
_common_utils = importlib.import_module("jiuwenswarm.common.utils")
cleanup_team_files = _common_utils.cleanup_team_files
get_env_file = _common_utils.get_env_file
get_user_workspace_dir = _common_utils.get_user_workspace_dir
prepare_workspace = _common_utils.prepare_workspace
reset_free_search_runtime_flags = _common_utils.reset_free_search_runtime_flags

_workspace_dir = get_user_workspace_dir()
_config_file = _workspace_dir / "config" / "config.yaml"

# Ensure workspace config exists
cleanup_team_files(_workspace_dir)
if not _config_file.exists():
    prepare_workspace(overwrite=False)

# Atomically refresh the current Alpha/Risk quant_team while preserving
# unrelated user teams.
yaml = importlib.import_module("yaml")

_PROJECT_CONFIG_PATH = PROJECT_ROOT / "jiuwenswarm" / "resources" / "config.yaml"
if _config_file.exists() and _PROJECT_CONFIG_PATH.exists():
    with open(_config_file, "r", encoding="utf-8") as f:
        ws_cfg = yaml.safe_load(f) or {}
    with open(_PROJECT_CONFIG_PATH, "r", encoding="utf-8") as f:
        prj_cfg = yaml.safe_load(f) or {}
    prj_team = prj_cfg.get("modes", {}).get("team", {}).get("quant_team")
    if isinstance(prj_team, dict):
        teams = ws_cfg.setdefault("modes", {}).setdefault("team", {})
        # Replace only quant_team; preserve unrelated user teams
        teams["quant_team"] = prj_team
        with open(_config_file, "w", encoding="utf-8") as f:
            yaml.safe_dump(ws_cfg, f, allow_unicode=True, default_flow_style=False)

load_dotenv(dotenv_path=get_env_file(), override=True)
reset_free_search_runtime_flags()

# Each formal run is a fresh process — phase idempotency cache
# (_phase_results in extension.py) starts empty automatically.

# ── Now safe to import framework internals ─────────────────
# Trigger swarm provider registrations and load framework internals only after
# workspace/config initialization has completed.
importlib.import_module("jiuwenswarm.agents.swarm.assembly")
_team_manager_module = importlib.import_module(
    "jiuwenswarm.agents.harness.team.team_manager"
)
build_session_scoped_team_name = _team_manager_module.build_session_scoped_team_name
get_team_manager = _team_manager_module.get_team_manager
ToolProgressGuard = importlib.import_module(
    "jiuwenswarm.quant.orchestration_guard"
).ToolProgressGuard
_resource_meter = importlib.import_module(
    "jiuwenswarm.quant.reporting.resource_meter"
)
ResourceReport = _resource_meter.ResourceReport
StageMetrics = _resource_meter.StageMetrics
get_contract = importlib.import_module(
    "jiuwenswarm.quant.reporting.submission_contract"
).get_contract
Runner = importlib.import_module("openjiuwen.core.runner").Runner

# ── Constants ───────────────────────────────────────────────
OUTPUT_DIR = PROJECT_ROOT.parent / "output"
SESSION_ID = (
    "multi-agent-validation-"
    + datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y%m%d-%H%M%S")
)
SUBMISSION_CONTRACT = get_contract()
EXPECTED_STOCKS = SUBMISSION_CONTRACT.n_companies
EXPECTED_SECTORS = SUBMISSION_CONTRACT.n_sectors
FORMAL_TEAM_NAME = "quant_team"
FORMAL_LEADER_NAME = "quant-leader"
FORMAL_MEMBER_NAMES = {"alpha_analyst", "risk_evidence_analyst"}

QUANT_PHASE_METHODS = {
    "fetch": "quant.fetch_data",
    "factors": "quant.compute_factors",
    "alpha_view": "quant.alpha_view",
    "risk_evidence_view": "quant.risk_evidence_view",
    "select": "quant.select_stocks",
    "allocate": "quant.allocate_positions",
    "backtest": "quant.run_backtest",
    "report": "quant.generate_report",
}


def _phase_payload_valid(phase: str, payload: dict) -> bool:
    """Validate successful output, not merely that a tool name appeared."""
    if not isinstance(payload, dict) or payload.get("success") is not True:
        return False
    if phase == "fetch":
        return (
            payload.get("coverage_complete") is True
            and payload.get("n_stocks") == EXPECTED_STOCKS
            and payload.get("expected_stocks") == EXPECTED_STOCKS
        )
    if phase == "factors":
        return (
            payload.get("n_stocks_analyzed") == EXPECTED_STOCKS
            and len(payload.get("all_composite", {})) == EXPECTED_STOCKS
        )
    if phase == "select":
        return (
            payload.get("n_selected") == 15
            and payload.get("n_sectors_covered") == EXPECTED_SECTORS
        )
    if phase == "allocate":
        portfolio = payload.get("portfolio", [])
        sector_totals = {}
        for holding in portfolio:
            weight = float(holding.get("weight", 0.0))
            if weight > 0.10 + 1e-9:
                return False
            sector = holding.get("sector")
            sector_totals[sector] = sector_totals.get(sector, 0.0) + weight
        return (
            payload.get("n_holdings") == 15
            and float(payload.get("cash_reserve", 0.0)) >= 0.05 - 1e-9
            and all(weight <= 0.25 + 1e-9 for weight in sector_totals.values())
        )
    if phase == "backtest":
        return payload.get("n_forward_returns") == 20
    if phase == "report":
        # Basic: report text present and correct holding count
        base_ok = bool(payload.get("report")) and payload.get("summary", {}).get("n_holdings") == 15
        if not base_ok:
            return False
        # Candidate package: report count must match the frozen contract.
        cp = payload.get("candidate_package")
        if cp is None:
            return False
        if cp.get("error"):
            return False
        if cp.get("quality_passed") is not True:
            return False
        return cp.get("n_reports") == EXPECTED_STOCKS
    return True


def _validate_quant_rpc_calls(calls: list[dict]) -> tuple[dict[str, bool], list[str]]:
    phases = {}
    issues = []
    for phase, method in QUANT_PHASE_METHODS.items():
        matching = [call for call in calls if call.get("method") == method]
        invalid = [
            call
            for call in matching
            if not _phase_payload_valid(phase, call.get("payload", {}))
        ]
        phases[phase] = bool(matching) and not invalid
        if invalid:
            issues.append(
                f"{method} returned {len(invalid)} unsuccessful or invalid result(s)"
            )
    return phases, issues


def _serialize_chunk(chunk) -> dict:
    """Convert a streaming chunk to a serializable dict."""
    if hasattr(chunk, "model_dump"):
        return chunk.model_dump()
    if hasattr(chunk, "__dict__"):
        return _make_serializable(chunk.__dict__)
    return {"raw": str(chunk)[:2000]}


def _make_serializable(obj):
    """Recursively convert objects to JSON-serializable types."""
    if isinstance(obj, dict):
        return {k: _make_serializable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_make_serializable(v) for v in obj]
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "__dict__"):
        return _make_serializable(obj.__dict__)
    if isinstance(obj, (str, int, float, bool, type(None))):
        return obj
    return str(obj)[:500]


async def _load_formal_team_spec(team_manager, *, session_id: str):
    """Load the exact frozen quant team or stop before Runner execution."""
    spec = await team_manager.get_swarm_enriched_team_spec(
        session_id=session_id,
        mode="team",
        requested_team_name=FORMAL_TEAM_NAME,
    )
    team_name = str(getattr(spec, "team_name", ""))
    leader_name = str(getattr(getattr(spec, "leader", None), "member_name", ""))
    member_names = [
        str(getattr(member, "member_name", ""))
        for member in (getattr(spec, "predefined_members", None) or [])
    ]
    expected_team_name = build_session_scoped_team_name(FORMAL_TEAM_NAME, session_id)
    if (
        team_name != expected_team_name
        or leader_name != FORMAL_LEADER_NAME
        or len(member_names) != len(FORMAL_MEMBER_NAMES)
        or set(member_names) != FORMAL_MEMBER_NAMES
    ):
        raise RuntimeError(
            "formal team identity mismatch: "
            f"expected team={expected_team_name!r}, leader={FORMAL_LEADER_NAME!r}, "
            f"members={sorted(FORMAL_MEMBER_NAMES)!r}; got team={team_name!r}, "
            f"leader={leader_name!r}, members={sorted(member_names)!r}"
        )
    return spec


async def _init_extensions():
    """Initialize ExtensionRegistry and load quant-finance extension.

    Without this, QuantToolkit._call_rpc() will find no registered handlers
    and the LLM will retry quant_fetch_data indefinitely (34+ times).
    """
    import logging

    from jiuwenswarm.extensions.manager import ExtensionManager
    from jiuwenswarm.extensions.registry import ExtensionRegistry

    _log = logging.getLogger(__name__)

    # Check if already initialized (e.g. running inside full server)
    try:
        ExtensionRegistry.get_instance()
        _log.info("[MultiAgent] ExtensionRegistry already initialized, reusing")
        return
    except RuntimeError:
        pass

    # Create registry and load extensions
    try:
        callback_framework = Runner.callback_framework
    except Exception:  # noqa: BLE001 - optional callback failure is logged
        _log.warning("[MultiAgent] Cannot access Runner.callback_framework — "
                      "extensions may not load. Run inside jiuwenswarm server for full support.")
        return

    registry = ExtensionRegistry.create_instance(
        callback_framework=callback_framework,
        config={},
        logger=_log,
    )
    manager = ExtensionManager(registry=registry)
    await manager.load_all_extensions()

    rpc_methods = registry.list_rpc_methods()
    quant_methods = [m for m in rpc_methods if m.startswith("quant.")]
    print(f"  [MultiAgent] Extensions loaded: {len(manager.list_extensions())} extensions, "
          f"{len(quant_methods)} quant RPC methods")
    if not quant_methods:
        print("  [MultiAgent] WARNING: No quant RPC methods found! "
              "Agent tool calls will fail.")


async def run_multi_agent_team(prompt: str, timeout_seconds: int = 600):
    """
    Run the multi-agent quant team with the given prompt.

    Returns (result_summary, chunks_log).
    """
    print("=" * 70)
    print("  Multi-Agent Quant Team — Validation Run")
    print(f"  Session: {SESSION_ID}")
    print(f"  Timeout: {timeout_seconds}s")
    print("=" * 70)

    # 0. Initialize extension system (Critical: without this, quant tools fail)
    print("\n[0/5] Initializing extensions...")
    await _init_extensions()

    # 1. Select and validate the exact formal team before instrumenting tools
    # or invoking Runner.
    print("\n[1/5] Building team spec for quant_team...")
    tm = get_team_manager()
    t0 = time.time()

    spec = await _load_formal_team_spec(tm, session_id=SESSION_ID)
    print(f"  Team spec built in {time.time() - t0:.1f}s")
    print(f"  Leader: {spec.leader.member_name if hasattr(spec.leader, 'member_name') else 'quant-leader'}")
    member_count = len(spec.predefined_members) if hasattr(spec, 'predefined_members') else 0
    print(f"  Members: {member_count}")

    # Record actual RPC returns. Stream chunks are presentation events and are
    # not reliable evidence that a tool completed successfully.
    from jiuwenswarm.agents.harness.common.tools.quant_toolkits import QuantToolkit

    quant_rpc_calls = []
    failure_counts = {}
    failure_guard = {"triggered": False, "detail": None}
    progress_guard = ToolProgressGuard()
    pipeline_completed_at = {"monotonic": None}
    quant_progress = {"monotonic": None, "completed": 0}
    original_call_rpc = QuantToolkit._call_rpc

    async def audited_call_rpc(toolkit, method, params):
        payload = await original_call_rpc(toolkit, method, params)
        quant_rpc_calls.append({
            "method": method,
            "params_keys": sorted(params) if params else [],
            "payload": payload,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        phases, _ = _validate_quant_rpc_calls(quant_rpc_calls)
        completed = sum(phases.values())
        if completed > quant_progress["completed"]:
            quant_progress["completed"] = completed
            quant_progress["monotonic"] = time.monotonic()
            progress_guard.record_quant_progress(completed)
        if all(phases.values()) and pipeline_completed_at["monotonic"] is None:
            pipeline_completed_at["monotonic"] = time.monotonic()
        if isinstance(payload, dict) and payload.get("success") is True:
            failure_counts[method] = 0
        else:
            failure_counts[method] = failure_counts.get(method, 0) + 1
            failure_guard["triggered"] = True
            failure_guard["detail"] = (
                f"{method} returned an unsuccessful or invalid payload; "
                "formal quant RPCs are fail-closed"
            )
        return payload

    QuantToolkit._call_rpc = audited_call_rpc

    # 2. Run the team
    print(f"\n[2/5] Running team with prompt:\n  \"{prompt}\"")
    print("  Waiting for agent responses (this may take several minutes)...\n")

    chunks_log = []
    text_output = []
    tool_calls = []
    errors = []

    t_start = time.time()
    quant_progress["monotonic"] = time.monotonic()
    started_at = datetime.now(timezone.utc)
    process = None
    cpu_start = None
    try:
        import psutil

        process = psutil.Process()
        cpu_times = process.cpu_times()
        cpu_start = float(cpu_times.user + cpu_times.system)
    except (ImportError, OSError):
        pass
    stream = None

    try:
        stream = Runner.run_agent_team_streaming(
            agent_team=spec,
            inputs=prompt,
            session=SESSION_ID,
        ).__aiter__()
        while True:
            remaining = timeout_seconds - (time.time() - t_start)
            if pipeline_completed_at["monotonic"] is not None:
                remaining = min(
                    remaining,
                    90.0 - (time.monotonic() - pipeline_completed_at["monotonic"]),
                )
            elif quant_progress["monotonic"] is not None:
                remaining = min(
                    remaining,
                    150.0 - (time.monotonic() - quant_progress["monotonic"]),
                )
            if remaining <= 0:
                raise asyncio.TimeoutError
            try:
                chunk = await asyncio.wait_for(stream.__anext__(), timeout=remaining)
            except StopAsyncIteration:
                break
            chunk_time = time.time() - t_start
            serialized = _serialize_chunk(chunk)
            serialized["_elapsed_s"] = round(chunk_time, 1)
            chunks_log.append(serialized)

            # Categorize and display
            chunk_type = type(chunk).__name__ if hasattr(chunk, "__class__") else "unknown"

            # Extract text content
            text = _extract_text(chunk)
            if text:
                text_output.append(text)
                print(f"  [{chunk_type}] {text[:200]}", flush=True)

            # Detect tool calls
            tc = _extract_tool_call(chunk)
            if tc:
                tool_calls.append(tc)
                guard_detail = progress_guard.record_tool_call(tc)
                if guard_detail:
                    failure_guard["triggered"] = True
                    failure_guard["detail"] = guard_detail
                print(f"  [TOOL] {tc.get('name', '?')} → {str(tc.get('result', ''))[:150]}", flush=True)

            # Detect errors
            err = _extract_error(chunk)
            if err:
                errors.append(err)
                print(f"  [ERROR] {err}", flush=True)

            if failure_guard["triggered"]:
                errors.append(failure_guard["detail"])
                print(f"\n  Repeated-failure guard: {failure_guard['detail']}")
                break

            current_phases, _ = _validate_quant_rpc_calls(quant_rpc_calls)
            current_role_calls = _role_rpc_calls(chunks_log)
            if (
                all(current_phases.values())
                and current_role_calls["alpha_analyst"] > 0
                and current_role_calls["risk_evidence_analyst"] > 0
            ):
                print("\n  Business completion gate reached; closing the agent stream.")
                break

            # Timeout check
            if chunk_time > timeout_seconds:
                print(f"\n  ⚠ Timeout reached ({timeout_seconds}s), stopping...")
                break

    except asyncio.TimeoutError:
        if pipeline_completed_at["monotonic"] is None:
            if (
                quant_progress["monotonic"] is not None
                and time.monotonic() - quant_progress["monotonic"] >= 150.0
            ):
                errors.append(
                    "no validated quant-stage progress for 150s "
                    f"(completed {quant_progress['completed']}/8)"
                )
            else:
                errors.append(f"overall timeout after {timeout_seconds}s")
        else:
            errors.append("agent stream did not close within 90s after 8/8 business completion")
        print(f"\n  ⚠ Async timeout after {time.time() - t_start:.0f}s")
    except Exception as e:  # noqa: BLE001 - stream failure becomes evidence
        errors.append(str(e))
        print(f"\n  ✗ Exception: {e}")
        import traceback
        traceback.print_exc()
    finally:
        QuantToolkit._call_rpc = original_call_rpc
        # The upstream team stream can remain open after the leader has emitted
        # its final answer. Stop the Runner-owned runtime before closing the
        # iterator; otherwise async-generator teardown may wait indefinitely.
        try:
            await asyncio.wait_for(
                tm.stop_session_runtime(
                    SESSION_ID,
                    reason="formal validation teardown",
                ),
                timeout=20.0,
            )
        except (asyncio.TimeoutError, RuntimeError) as exc:
            errors.append(f"team runtime teardown failed: {exc or 'timeout'}")
        if stream is not None:
            try:
                await asyncio.wait_for(stream.aclose(), timeout=10.0)
            except (asyncio.TimeoutError, RuntimeError) as exc:
                errors.append(f"agent stream close failed: {exc or 'timeout'}")

    elapsed = time.time() - t_start

    # 3. Summarize
    print(f"\n[3/5] Run complete in {elapsed:.0f}s")
    print(f"  Text segments: {len(text_output)}")
    print(f"  Tool calls:    {len(tool_calls)}")
    print(f"  Errors:        {len(errors)}")
    print(f"  Total chunks:  {len(chunks_log)}")

    # 4. Validate: did we complete the full quant loop?
    print("\n[4/5] Validating quant loop completion...")
    phases_completed, validation_issues = _validate_quant_rpc_calls(quant_rpc_calls)
    errors.extend(issue for issue in validation_issues if issue not in errors)
    completed_count = sum(1 for v in phases_completed.values() if v)
    phase_request_counts = {
        phase: sum(
            call.get("method") == method
            for call in quant_rpc_calls
        )
        for phase, method in QUANT_PHASE_METHODS.items()
    }
    phase_execution_counts = {
        phase: sum(
            call.get("method") == method
            and call.get("payload", {}).get("success") is True
            and call.get("payload", {}).get("executed") is True
            for call in quant_rpc_calls
        )
        for phase, method in QUANT_PHASE_METHODS.items()
    }
    phase_cache_hit_counts = {
        phase: sum(
            call.get("method") == method
            and call.get("payload", {}).get("success") is True
            and call.get("payload", {}).get("cached") is True
            for call in quant_rpc_calls
        )
        for phase, method in QUANT_PHASE_METHODS.items()
    }
    execution_counts_valid = all(
        not phases_completed[phase] or phase_execution_counts[phase] == 1
        for phase in QUANT_PHASE_METHODS
    )
    if not execution_counts_valid:
        errors.append(
            "successful phase business execution count must be exactly one: "
            + ", ".join(
                f"{phase}={count}"
                for phase, count in phase_execution_counts.items()
                if phases_completed[phase] and count != 1
            )
        )
    loop_complete = (
        completed_count == len(QUANT_PHASE_METHODS)
        and execution_counts_valid
        and not failure_guard["triggered"]
    )
    participation = _agent_participation(chunks_log)
    role_rpc_calls = _role_rpc_calls(chunks_log)
    role_rpc_violations = _role_rpc_violations(chunks_log)
    # Exact role set: exactly 3 members, no stale Bull/Bear ghosts
    EXPECTED_ROLES = {"quant-leader", "alpha_analyst", "risk_evidence_analyst"}
    actual_roles = set(participation.keys())
    extra_roles = actual_roles - EXPECTED_ROLES
    missing_roles = EXPECTED_ROLES - actual_roles
    role_set_valid = not extra_roles and not missing_roles
    multi_agent_working = (
        participation.get("quant-leader", 0) > 0
        and role_rpc_calls["alpha_analyst"] > 0
        and role_rpc_calls["risk_evidence_analyst"] > 0
        and not role_rpc_violations
        and role_set_valid
    )
    if extra_roles:
        errors.append(f"UNEXPECTED ROLES DETECTED: {sorted(extra_roles)} — config may contain stale Bull/Bear members")
    if missing_roles:
        errors.append(f"MISSING REQUIRED ROLES: {sorted(missing_roles)}")
    validation_passed = loop_complete and multi_agent_working
    if not multi_agent_working:
        missing = [
            member
            for member in ("alpha_analyst", "risk_evidence_analyst")
            if role_rpc_calls[member] == 0
        ]
        parts = []
        if missing:
            parts.append("missing role-owned RPCs: " + ", ".join(missing))
        if role_rpc_violations:
            parts.append("role boundary violations: " + ", ".join(role_rpc_violations))
        issue = "multi-agent validation failed: " + "; ".join(parts)
        if issue not in errors:
            errors.append(issue)
    print(f"  Phases: {', '.join(f'{k}={v}' for k, v in phases_completed.items())}")
    print(f"  Completed: {completed_count}/8, Loop complete: {loop_complete}")
    print(f"  Phase requests: {phase_request_counts}")
    print(f"  Business executions: {phase_execution_counts}")
    print(f"  Cache hits: {phase_cache_hit_counts}")
    print(f"  Agent participation: {participation}, Multi-agent working: {multi_agent_working}")
    print(f"  Role-owned RPC calls: {role_rpc_calls}")
    print(f"  Role RPC violations: {role_rpc_violations}")

    # 5. Save results
    print("\n[5/5] Saving results...")

    summary = {
        "session_id": SESSION_ID,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "prompt": prompt,
        "elapsed_seconds": round(elapsed, 1),
        "stats": {
            "text_segments": len(text_output),
            "tool_calls": len(tool_calls),
            "errors": len(errors),
            "total_chunks": len(chunks_log),
            "quant_rpc_calls": len(quant_rpc_calls),
        },
        "quant_phases": phases_completed,
        "phase_request_counts": phase_request_counts,
        "phase_execution_counts": phase_execution_counts,
        "phase_cache_hit_counts": phase_cache_hit_counts,
        "loop_complete": loop_complete,
        "agent_participation": participation,
        "role_rpc_calls": role_rpc_calls,
        "role_rpc_violations": role_rpc_violations,
        "multi_agent_working": multi_agent_working,
        "validation_passed": validation_passed,
        "success_criterion": "8/8 validated RPC outputs plus Alpha/Risk & Evidence-owned view RPCs",
        "repeated_failure_guard": {
            **failure_guard,
            "progress_budget": progress_guard.as_dict(),
        },
        "quant_rpc_calls": quant_rpc_calls,
        "issues": errors if errors else None,
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Full chunk log
    artifact_id = SESSION_ID.removeprefix("multi-agent-validation-")
    chunks_path = OUTPUT_DIR / f"multi_agent_chunks_{artifact_id}.json"
    chunks_path.write_text(
        json.dumps(chunks_log, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )

    # Summary
    summary_path = OUTPUT_DIR / f"multi_agent_summary_{artifact_id}.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    # Combined text output
    text_path = OUTPUT_DIR / f"multi_agent_output_{artifact_id}.md"
    text_path.write_text(
        "# Multi-Agent Quant Team Output\n\n"
        f"**Session**: {SESSION_ID}\n"
        f"**Time**: {datetime.now(timezone.utc).isoformat()}\n"
        f"**Elapsed**: {elapsed:.0f}s\n\n"
        "---\n\n"
        + "".join(
            f"## Segment {index + 1}\n\n{text}\n\n"
            for index, text in enumerate(text_output)
        ),
        encoding="utf-8",
    )

    # Real resource report for the formal Agent path. Token usage comes from
    # openJiuwen llm_usage chunks; absent measurements remain None.
    usage_by_role: dict[str, dict[str, int]] = {}
    for chunk in chunks_log:
        if chunk.get("type") != "llm_usage":
            continue
        role = _canonical_member_name(chunk.get("source_member")) or "unknown"
        usage = chunk.get("payload", {}).get("usage_metadata", {})
        bucket = usage_by_role.setdefault(
            role,
            {"input_tokens": 0, "output_tokens": 0, "cache_tokens": 0},
        )
        for field in bucket:
            value = usage.get(field)
            if isinstance(value, int):
                bucket[field] += value

    input_tokens = (
        sum(row["input_tokens"] for row in usage_by_role.values())
        if usage_by_role
        else None
    )
    output_tokens = (
        sum(row["output_tokens"] for row in usage_by_role.values())
        if usage_by_role
        else None
    )
    cache_tokens = (
        sum(row["cache_tokens"] for row in usage_by_role.values())
        if usage_by_role
        else None
    )
    cpu_seconds = None
    peak_memory_mb = None
    if process is not None:
        try:
            cpu_times = process.cpu_times()
            cpu_end = float(cpu_times.user + cpu_times.system)
            cpu_seconds = cpu_end - cpu_start if cpu_start is not None else None
            peak_bytes = getattr(process.memory_info(), "peak_wset", None)
            if peak_bytes is not None:
                peak_memory_mb = float(peak_bytes) / (1024 * 1024)
        except (OSError, AttributeError):
            pass

    resource_report = ResourceReport(
        run_id=SESSION_ID,
        started_at=started_at,
        stages={
            "formal_multi_agent": StageMetrics(
                stage="formal_multi_agent",
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
                duration_seconds=round(elapsed, 3),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cache_tokens=cache_tokens,
                tool_calls=len(tool_calls),
                retries=0,
                peak_memory_mb=peak_memory_mb,
                cpu_time_seconds=cpu_seconds,
            )
        },
        role_breakdown={
            role: StageMetrics(
                stage=role,
                input_tokens=usage["input_tokens"],
                output_tokens=usage["output_tokens"],
                cache_tokens=usage["cache_tokens"],
                tool_calls=sum(
                    1
                    for chunk in chunks_log
                    if chunk.get("type") == "tool_call"
                    and _canonical_member_name(chunk.get("source_member")) == role
                ),
            )
            for role, usage in usage_by_role.items()
        },
    )
    resource_report.finalize()
    candidate_path = OUTPUT_DIR / "submission_candidate"
    if candidate_path.is_dir():
        resource_report.save_json(str(candidate_path / "resource_usage.json"))
        resource_report.save_markdown(str(candidate_path / "resource_usage.md"))
        summary["resource_usage"] = resource_report.to_dict()
        summary_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    print(f"  Chunks log:  {chunks_path}")
    print(f"  Summary:     {summary_path}")
    print(f"  Text output: {text_path}")

    return summary, chunks_log


def _canonical_member_name(member: object) -> str:
    """Normalize runtime member aliases without weakening role ownership checks."""
    normalized = str(member or "").strip().lower().replace("-", "_")
    aliases = {
        "quant_leader": "quant-leader",
        "alpha_analyst": "alpha_analyst",
        "risk_evidence_analyst": "risk_evidence_analyst",
    }
    return aliases.get(normalized, normalized)


def _agent_participation(chunks_log: list[dict]) -> dict[str, int]:
    """Count emitted chunks by member; creation alone is not participation."""
    counts = {"quant-leader": 0, "alpha_analyst": 0, "risk_evidence_analyst": 0}
    for chunk in chunks_log:
        member = _canonical_member_name(chunk.get("source_member"))
        if member in counts:
            counts[member] += 1
    return counts


def _role_rpc_calls(chunks_log: list[dict]) -> dict[str, int]:
    """Require Alpha/Risk & Evidence to call their own view RPC; leader labels are insufficient."""
    expected = {
        "alpha_analyst": "quant_alpha_view",
        "risk_evidence_analyst": "quant_risk_evidence_view",
    }
    counts = {member: 0 for member in expected}
    for chunk in chunks_log:
        member = _canonical_member_name(chunk.get("source_member"))
        if member not in expected or chunk.get("type") != "tool_call":
            continue
        tool_name = (
            chunk.get("payload", {})
            .get("tool_call", {})
            .get("name")
        )
        if tool_name == expected[member]:
            counts[member] += 1
    return counts


def _role_rpc_violations(chunks_log: list[dict]) -> list[str]:
    """Reject analyst calls outside their one role-owned Quant RPC."""
    allowed = {
        "alpha_analyst": {"quant_alpha_view"},
        "risk_evidence_analyst": {"quant_risk_evidence_view"},
    }
    violations = []
    for chunk in chunks_log:
        member = _canonical_member_name(chunk.get("source_member"))
        if member not in allowed or chunk.get("type") != "tool_call":
            continue
        tool_name = chunk.get("payload", {}).get("tool_call", {}).get("name")
        if str(tool_name or "").startswith("quant_") and tool_name not in allowed[member]:
            violations.append(f"{member}:{tool_name}")
    return violations


def _extract_text(chunk) -> str | None:
    """Extract human-readable text from a streaming chunk."""
    # Try common attributes
    for attr in ("content", "text", "message", "delta", "output"):
        if hasattr(chunk, attr):
            val = getattr(chunk, attr)
            if isinstance(val, str) and val.strip():
                return val.strip()
            if isinstance(val, dict):
                text = val.get("content") or val.get("text") or val.get("message")
                if isinstance(text, str) and text.strip():
                    return text.strip()

    # Try dict-like access
    if isinstance(chunk, dict):
        candidates = [chunk]
        if isinstance(chunk.get("payload"), dict):
            candidates.append(chunk["payload"])
        for candidate in candidates:
            for key in ("content", "text", "message", "delta", "output", "data"):
                val = candidate.get(key)
                if isinstance(val, str) and val.strip():
                    return val.strip()

    # Try model_dump
    if hasattr(chunk, "model_dump"):
        try:
            d = chunk.model_dump()
            candidates = [d]
            if isinstance(d.get("payload"), dict):
                candidates.append(d["payload"])
            for candidate in candidates:
                for key in ("content", "text", "message", "delta", "output"):
                    value = candidate.get(key)
                    if isinstance(value, str) and value.strip():
                        return value.strip()
        except Exception:  # noqa: BLE001 - unknown chunk model has no text
            return None

    return None


def _extract_tool_call(chunk) -> dict | None:
    """Extract tool call information from a chunk."""
    if hasattr(chunk, "model_dump"):
        try:
            d = chunk.model_dump()
        except Exception:  # noqa: BLE001 - unknown chunk model has no tool call
            return None
    elif isinstance(chunk, dict):
        d = chunk
    else:
        return None

    event_type = d.get("type")
    if event_type and event_type != "tool_call":
        return None

    # Stream chunks place the actual event under payload.
    if isinstance(d.get("payload"), dict):
        d = d["payload"]

    # Look for tool-related fields
    tc = {}
    if "tool_name" in d:
        tc["name"] = d["tool_name"]
    if "tool_call" in d:
        tc.update(d["tool_call"] if isinstance(d["tool_call"], dict) else {"name": str(d["tool_call"])})
    if "function_call" in d:
        fc = d["function_call"]
        tc["name"] = fc.get("name", "") if isinstance(fc, dict) else str(fc)
    if "tool_result" in d:
        tc["result"] = str(d["tool_result"])[:500]
    if "tool_call_id" in d:
        tc["call_id"] = d["tool_call_id"]

    return tc if tc else None


def _extract_error(chunk) -> str | None:
    """Extract error info from a chunk."""
    if hasattr(chunk, "error"):
        return str(chunk.error)
    if isinstance(chunk, dict) and "error" in chunk:
        return str(chunk["error"])
    return None


def _default_validation_end_date(*, now: datetime | None = None) -> date:
    """Avoid asking the formal Agent to fetch an incomplete current session."""

    shanghai = ZoneInfo("Asia/Shanghai")
    local_now = (now or datetime.now(shanghai)).astimezone(shanghai)
    end_date = local_now.date()
    if local_now.time() < datetime_time(15, 30):
        end_date -= timedelta(days=1)
    return end_date


async def main(argv: list[str] | None = None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-date", help="Inclusive market-data start date")
    parser.add_argument("--end-date", help="Inclusive market-data end date")
    args = parser.parse_args(argv)
    end_date = (
        date.fromisoformat(args.end_date)
        if args.end_date
        else _default_validation_end_date()
    )
    start_date = (
        date.fromisoformat(args.start_date)
        if args.start_date
        else end_date - timedelta(days=400)
    )
    if start_date >= end_date:
        raise ValueError("start-date must be earlier than end-date")
    prompt = (
        f"请作为量化投资团队，分析当前{EXPECTED_STOCKS}只A股股票池，完成以下任务：\n"
        f"1. 获取 {start_date.isoformat()} 至 {end_date.isoformat()} 的股票数据；"
        "调用 quant_fetch_data 时必须原样使用这两个日期，不得自行猜测年份\n"
        "   八个 quant_* 工具必须严格串行：必须收到前一阶段 success=true 后再调用下一阶段，禁止并发或预调用\n"
        "2. 计算多因子得分（动量、波动率、回撤、成交量等）\n"
        "3. Alpha分析师从趋势和板块领导力视角提交纳入提案，Risk & Evidence分析师从尾部风险和证据冲突视角行使否决\n"
        "   必须用 send_message 分别把任务委派给 alpha_analyst 和 risk_evidence_analyst；"
        "Coordinator 禁止代为调用 quant_alpha_view 或 quant_risk_evidence_view，"
        "必须等待两个成员各自调用其专属工具并返回结果\n"
        "4. 综合双方意见，选择15只股票并分配仓位\n"
        "5. 运行回测并生成简版投资报告\n"
        "请用中文回复。"
    )

    summary, _chunks = await run_multi_agent_team(prompt, timeout_seconds=600)

    print("\n" + "=" * 70)
    print("  VALIDATION RESULT")
    print("=" * 70)
    if summary["validation_passed"]:
        print("  [OK] Full quant loop completed with Alpha/Risk & Evidence participation")
    else:
        print("  [FAIL] Formal multi-agent validation did not pass")
        phases = summary.get("quant_phases", {})
        missing = [k for k, v in phases.items() if not v]
        if missing:
            print(f"  Missing phases: {', '.join(missing)}")
        if not summary.get("multi_agent_working"):
            print(f"  Agent participation: {summary.get('agent_participation')}")
    print(f"  Tool calls: {summary['stats']['tool_calls']}")
    print(f"  Text segments: {summary['stats']['text_segments']}")
    print(f"  Errors: {summary['stats']['errors']}")
    if summary.get("issues"):
        for issue in summary["issues"]:
            print(f"    - {issue}")
    print(f"  Elapsed: {summary['elapsed_seconds']:.0f}s")
    print("\nFull output path is recorded in the timestamped validation artifacts above.")
    exit_code = 0 if summary["validation_passed"] else 1
    sys.stdout.flush()
    sys.stderr.flush()
    # asyncio.run() waits indefinitely for openJiuwen scheduler tasks after a
    # deliberately early business-completion close on Windows.  This is a
    # standalone validator and all artifacts are already durably written.
    os_env._exit(exit_code)


if __name__ == "__main__":
    asyncio.run(main())
