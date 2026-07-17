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

    # 1. Get team manager and build spec
    print("\n[1/4] Building team spec for quant_team...")
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
    print(f"\n[2/4] Running team with prompt:\n  \"{prompt}\"")
    print("  Waiting for agent responses (this may take several minutes)...\n")

    chunks_log = []
    text_output = []
    tool_calls = []
    errors = []
    final_result = None

    t_start = time.time()

    try:
        async for chunk in Runner.run_agent_team_streaming(
            agent_team=spec,
            inputs=prompt,
            session=SESSION_ID,
        ):
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

            # Timeout check
            if chunk_time > timeout_seconds:
                print(f"\n  ⚠ Timeout reached ({timeout_seconds}s), stopping...")
                break

    except asyncio.TimeoutError:
        print(f"\n  ⚠ Async timeout after {time.time() - t_start:.0f}s")
    except Exception as e:
        errors.append(str(e))
        print(f"\n  ✗ Exception: {e}")
        import traceback
        traceback.print_exc()

    elapsed = time.time() - t_start

    # 3. Summarize
    print(f"\n[3/4] Run complete in {elapsed:.0f}s")
    print(f"  Text segments: {len(text_output)}")
    print(f"  Tool calls:    {len(tool_calls)}")
    print(f"  Errors:        {len(errors)}")
    print(f"  Total chunks:  {len(chunks_log)}")

    # 4. Save results
    print(f"\n[4/4] Saving results...")

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
        },
        "multi_agent_working": len(tool_calls) > 0 and len(text_output) > 0,
        "issues": errors if errors else None,
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Full chunk log
    chunks_path = OUTPUT_DIR / "multi_agent_chunks.json"
    with open(chunks_path, "w", encoding="utf-8") as f:
        json.dump(chunks_log, f, ensure_ascii=False, indent=2, default=str)

    # Summary
    summary_path = OUTPUT_DIR / "multi_agent_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    # Combined text output
    text_path = OUTPUT_DIR / "multi_agent_output.md"
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
    if summary["multi_agent_working"]:
        print("  ✓ Multi-agent team ran and produced output")
    else:
        print("  ✗ Multi-agent team did NOT produce expected output")
    print(f"  Tool calls: {summary['stats']['tool_calls']}")
    print(f"  Text segments: {summary['stats']['text_segments']}")
    print(f"  Errors: {summary['stats']['errors']}")
    if summary.get("issues"):
        for issue in summary["issues"]:
            print(f"    - {issue}")
    print(f"  Elapsed: {summary['elapsed_seconds']:.0f}s")
    print(f"\nFull output: {OUTPUT_DIR / 'multi_agent_output.md'}")


if __name__ == "__main__":
    asyncio.run(main())
