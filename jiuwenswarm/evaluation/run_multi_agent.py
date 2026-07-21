#!/usr/bin/env python3
"""
Multi-Agent Quant Team — Programmatic Validation Script.

Runs the full Coordinator + Bull + Bear multi-agent workflow via
Runner.run_agent_team_streaming(), capturing all agent interactions,
tool calls, and final output.

Usage:
  cd D:\比赛\HUAWEI\Track_2\jiuwenswarm
  python evaluation/run_multi_agent.py
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from datetime import datetime
from pathlib import Path

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

from dotenv import load_dotenv
from jiuwenswarm.common.utils import (
    get_env_file,
    get_user_workspace_dir,
    prepare_workspace,
    cleanup_team_files,
    reset_free_search_runtime_flags,
)

_workspace_dir = get_user_workspace_dir()
_config_file = _workspace_dir / "config" / "config.yaml"

# Ensure workspace is ready
cleanup_team_files(_workspace_dir)
if not _config_file.exists():
    prepare_workspace(overwrite=False)

load_dotenv(dotenv_path=get_env_file(), override=True)
reset_free_search_runtime_flags()

# ── Now safe to import framework internals ─────────────────
from jiuwenswarm.agents.harness.team.team_manager import get_team_manager

# Trigger swarm provider registrations
import jiuwenswarm.agents.swarm.assembly  # noqa: F401

from openjiuwen.core.runner import Runner

# ── Constants ───────────────────────────────────────────────
OUTPUT_DIR = PROJECT_ROOT.parent / "output"
SESSION_ID = f"multi-agent-validation-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

QUANT_PHASE_METHODS = {
    "fetch": "quant.fetch_data",
    "factors": "quant.compute_factors",
    "bull_view": "quant.bull_view",
    "bear_view": "quant.bear_view",
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
            and payload.get("n_stocks") == 49
            and payload.get("expected_stocks") == 49
        )
    if phase == "factors":
        return payload.get("n_stocks_analyzed") == 49 and len(payload.get("all_composite", {})) == 49
    if phase == "select":
        return payload.get("n_selected") == 15 and payload.get("n_sectors_covered") == 6
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
        return bool(payload.get("report")) and payload.get("summary", {}).get("n_holdings") == 15
    return True


def _validate_quant_rpc_calls(calls: list[dict]) -> tuple[dict[str, bool], list[str]]:
    phases = {}
    issues = []
    for phase, method in QUANT_PHASE_METHODS.items():
        matching = [call for call in calls if call.get("method") == method]
        phases[phase] = any(_phase_payload_valid(phase, call.get("payload", {})) for call in matching)
        if matching and not phases[phase]:
            issues.append(f"{method} was called but no result passed output validation")
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


async def _init_extensions():
    """Initialize ExtensionRegistry and load quant-finance extension.

    Without this, QuantToolkit._call_rpc() will find no registered handlers
    and the LLM will retry quant_fetch_data indefinitely (34+ times).
    """
    import logging
    from jiuwenswarm.extensions.registry import ExtensionRegistry
    from jiuwenswarm.extensions.manager import ExtensionManager

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
    except Exception:
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

    # Record actual RPC returns. Stream chunks are presentation events and are
    # not reliable evidence that a tool completed successfully.
    from jiuwenswarm.agents.harness.common.tools.quant_toolkits import QuantToolkit

    quant_rpc_calls = []
    failure_counts = {}
    failure_guard = {"triggered": False, "detail": None}
    pipeline_completed_at = {"monotonic": None}
    original_call_rpc = QuantToolkit._call_rpc

    async def audited_call_rpc(toolkit, method, params):
        payload = await original_call_rpc(toolkit, method, params)
        quant_rpc_calls.append({
            "method": method,
            "params_keys": sorted(params) if params else [],
            "payload": payload,
            "timestamp": datetime.now().isoformat(),
        })
        phases, _ = _validate_quant_rpc_calls(quant_rpc_calls)
        if all(phases.values()) and pipeline_completed_at["monotonic"] is None:
            pipeline_completed_at["monotonic"] = time.monotonic()
        if isinstance(payload, dict) and payload.get("success") is True:
            failure_counts[method] = 0
        else:
            failure_counts[method] = failure_counts.get(method, 0) + 1
            if failure_counts[method] >= 3:
                failure_guard["triggered"] = True
                failure_guard["detail"] = f"{method} failed {failure_counts[method]} times"
        return payload

    QuantToolkit._call_rpc = audited_call_rpc

    # 1. Get team manager and build spec
    print("\n[1/5] Building team spec for quant_team...")
    tm = get_team_manager()
    t0 = time.time()

    spec = await tm.get_swarm_enriched_team_spec(
        session_id=SESSION_ID,
        mode="team",
    )
    print(f"  Team spec built in {time.time() - t0:.1f}s")
    print(f"  Leader: {spec.leader.member_name if hasattr(spec.leader, 'member_name') else 'quant-leader'}")
    member_count = len(spec.predefined_members) if hasattr(spec, 'predefined_members') else 0
    print(f"  Members: {member_count}")

    # 2. Run the team
    print(f"\n[2/5] Running team with prompt:\n  \"{prompt}\"")
    print("  Waiting for agent responses (this may take several minutes)...\n")

    chunks_log = []
    text_output = []
    tool_calls = []
    errors = []
    final_result = None

    t_start = time.time()
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

            # Timeout check
            if chunk_time > timeout_seconds:
                print(f"\n  ⚠ Timeout reached ({timeout_seconds}s), stopping...")
                break

    except asyncio.TimeoutError:
        if pipeline_completed_at["monotonic"] is None:
            errors.append(f"overall timeout after {timeout_seconds}s")
        print(f"\n  ⚠ Async timeout after {time.time() - t_start:.0f}s")
    except Exception as e:
        errors.append(str(e))
        print(f"\n  ✗ Exception: {e}")
        import traceback
        traceback.print_exc()
    finally:
        QuantToolkit._call_rpc = original_call_rpc
        if stream is not None:
            try:
                await asyncio.wait_for(stream.aclose(), timeout=15.0)
            except (asyncio.TimeoutError, RuntimeError):
                pass

    elapsed = time.time() - t_start

    # 3. Summarize
    print(f"\n[3/5] Run complete in {elapsed:.0f}s")
    print(f"  Text segments: {len(text_output)}")
    print(f"  Tool calls:    {len(tool_calls)}")
    print(f"  Errors:        {len(errors)}")
    print(f"  Total chunks:  {len(chunks_log)}")

    # 4. Validate: did we complete the full quant loop?
    print(f"\n[4/5] Validating quant loop completion...")
    phases_completed, validation_issues = _validate_quant_rpc_calls(quant_rpc_calls)
    errors.extend(issue for issue in validation_issues if issue not in errors)
    completed_count = sum(1 for v in phases_completed.values() if v)
    loop_complete = completed_count == len(QUANT_PHASE_METHODS) and not failure_guard["triggered"]
    print(f"  Phases: {', '.join(f'{k}={v}' for k, v in phases_completed.items())}")
    print(f"  Completed: {completed_count}/8, Loop complete: {loop_complete}")

    # 5. Save results
    print(f"\n[5/5] Saving results...")

    summary = {
        "session_id": SESSION_ID,
        "timestamp": datetime.now().isoformat(),
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
        "loop_complete": loop_complete,
        "multi_agent_working": loop_complete,  # v2: real quant loop, not just "has text"
        "success_criterion": "8/8 validated RPC outputs",
        "repeated_failure_guard": failure_guard,
        "quant_rpc_calls": quant_rpc_calls,
        "issues": errors if errors else None,
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Full chunk log
    artifact_id = SESSION_ID.removeprefix("multi-agent-validation-")
    chunks_path = OUTPUT_DIR / f"multi_agent_chunks_{artifact_id}.json"
    with open(chunks_path, "w", encoding="utf-8") as f:
        json.dump(chunks_log, f, ensure_ascii=False, indent=2, default=str)

    # Summary
    summary_path = OUTPUT_DIR / f"multi_agent_summary_{artifact_id}.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    # Combined text output
    text_path = OUTPUT_DIR / f"multi_agent_output_{artifact_id}.md"
    with open(text_path, "w", encoding="utf-8") as f:
        f.write(f"# Multi-Agent Quant Team Output\n\n")
        f.write(f"**Session**: {SESSION_ID}\n")
        f.write(f"**Time**: {datetime.now().isoformat()}\n")
        f.write(f"**Elapsed**: {elapsed:.0f}s\n\n")
        f.write("---\n\n")
        for i, t in enumerate(text_output):
            f.write(f"## Segment {i+1}\n\n{t}\n\n")

    print(f"  Chunks log:  {chunks_path}")
    print(f"  Summary:     {summary_path}")
    print(f"  Text output: {text_path}")

    return summary, chunks_log


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
        for key in ("content", "text", "message", "delta", "output", "data"):
            val = chunk.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()

    # Try model_dump
    if hasattr(chunk, "model_dump"):
        try:
            d = chunk.model_dump()
            for key in ("content", "text", "message", "delta"):
                if key in d and isinstance(d[key], str) and d[key].strip():
                    return d[key].strip()
        except Exception:
            pass

    return None


def _extract_tool_call(chunk) -> dict | None:
    """Extract tool call information from a chunk."""
    if hasattr(chunk, "model_dump"):
        try:
            d = chunk.model_dump()
        except Exception:
            return None
    elif isinstance(chunk, dict):
        d = chunk
    else:
        return None

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


async def main():
    prompt = (
        "请作为量化投资团队，分析当前49只A股股票池，完成以下任务：\n"
        "1. 获取最近一年的股票数据\n"
        "2. 计算多因子得分（动量、波动率、回撤、成交量等）\n"
        "3. Bull分析师从看多视角推荐股票，Bear分析师从风控视角审查风险\n"
        "4. 综合双方意见，选择15只股票并分配仓位\n"
        "5. 运行回测并生成简版投资报告\n"
        "请用中文回复。"
    )

    summary, chunks = await run_multi_agent_team(prompt, timeout_seconds=600)

    print("\n" + "=" * 70)
    print("  VALIDATION RESULT")
    print("=" * 70)
    if summary["loop_complete"]:
        print("  [OK] Full quant loop completed (fetch->factors->select->allocate->backtest)")
    else:
        print("  [FAIL] Quant loop incomplete — check phases below")
        phases = summary.get("quant_phases", {})
        missing = [k for k, v in phases.items() if not v]
        if missing:
            print(f"  Missing phases: {', '.join(missing)}")
    print(f"  Tool calls: {summary['stats']['tool_calls']}")
    print(f"  Text segments: {summary['stats']['text_segments']}")
    print(f"  Errors: {summary['stats']['errors']}")
    if summary.get("issues"):
        for issue in summary["issues"]:
            print(f"    - {issue}")
    print(f"  Elapsed: {summary['elapsed_seconds']:.0f}s")
    print("\nFull output path is recorded in the timestamped validation artifacts above.")


if __name__ == "__main__":
    asyncio.run(main())
