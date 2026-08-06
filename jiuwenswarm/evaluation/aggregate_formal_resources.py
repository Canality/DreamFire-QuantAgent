#!/usr/bin/env python3
"""Aggregate exactly three immutable same-snapshot formal resource summaries."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from jiuwenswarm.quant.phase_state import (  # noqa: E402
    QUANT_PHASE_SEQUENCE,
    build_trace_receipt,
    canonical_json_bytes,
    canonical_sha256,
)

REQUIRED_RUNS = 3
BASELINE_INPUT_TOKENS = 1_204_831
MAX_P95_SECONDS = 120.0
MAX_PEAK_RSS_MB = 600.0
EXPECTED_ROLES = ("quant-leader", "alpha_analyst", "risk_evidence_analyst")
EXPECTED_ROLE_TOOLS = {
    "quant-leader": {
        "quant_fetch_data",
        "quant_compute_factors",
        "quant_select_stocks",
        "quant_allocate_positions",
        "quant_run_backtest",
        "quant_generate_report",
    },
    "alpha_analyst": {"quant_alpha_view"},
    "risk_evidence_analyst": {"quant_risk_evidence_view"},
}
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")


def _read_bound_json(path: Path, expected_sha256: str) -> dict[str, Any]:
    if not SHA256_PATTERN.fullmatch(expected_sha256):
        raise ValueError(f"invalid expected SHA-256: {path.name}")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError(f"summary SHA-256 mismatch: {path.name}")
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid summary JSON: {path.name}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"summary must be an object: {path.name}")
    return value


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{label} must be measured")
    numeric = float(value)
    if not math.isfinite(numeric) or numeric < 0:
        raise ValueError(f"{label} must be finite and non-negative")
    return numeric


def nearest_rank_p95(values: Sequence[float]) -> float:
    if not values:
        raise ValueError("P95 requires observations")
    ordered = sorted(_number(value, "P95 observation") for value in values)
    rank = math.ceil(0.95 * len(ordered))
    return ordered[rank - 1]


def _optional_metric(
    values: Sequence[object],
    *,
    label: str,
    reducer,
) -> float | None:
    if any(value is None for value in values):
        return None
    try:
        measured = [_number(value, label) for value in values]
    except ValueError:
        return None
    return float(reducer(measured))


def _validate_summary(summary: dict[str, Any]) -> dict[str, Any]:
    if summary.get("validation_passed") is not True:
        raise ValueError("formal summary did not pass validation")
    phases = summary.get("quant_phases")
    expected_phases = [phase for phase, _method in QUANT_PHASE_SEQUENCE]
    if (
        not isinstance(phases, dict)
        or set(phases) != set(expected_phases)
        or not all(phases[phase] is True for phase in expected_phases)
    ):
        raise ValueError("formal summary is not exact 8/8")
    calls = summary.get("quant_rpc_calls")
    if not isinstance(calls, list):
        raise ValueError("formal summary has no quant RPC trace")
    rebuilt_trace = build_trace_receipt(calls, mode="LIVE_TRACE")
    if summary.get("deterministic_trace") != rebuilt_trace:
        raise ValueError("formal deterministic trace mismatch")

    candidate = summary.get("candidate_package")
    if (
        not isinstance(candidate, dict)
        or candidate.get("immutable") is not True
        or candidate.get("quality_passed") is not True
    ):
        raise ValueError("formal candidate is missing or mutable")
    snapshot_id = candidate.get("snapshot_id")
    manifest_sha = candidate.get("snapshot_manifest_sha256")
    if not isinstance(snapshot_id, str) or not snapshot_id:
        raise ValueError("formal candidate snapshot_id is missing")
    if not isinstance(manifest_sha, str) or not SHA256_PATTERN.fullmatch(manifest_sha):
        raise ValueError("formal candidate snapshot manifest hash is missing")

    resource = summary.get("resource_usage")
    if not isinstance(resource, dict):
        raise ValueError("formal resource usage is missing")
    session_id = summary.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        raise ValueError("formal session_id is missing")
    if resource.get("run_id") != session_id:
        raise ValueError("resource usage is not bound to the formal session")
    stages = resource.get("stages")
    if not isinstance(stages, dict) or set(stages) != set(expected_phases):
        raise ValueError("resource usage does not contain exact eight stages")
    for phase in expected_phases:
        stage = stages[phase]
        if not isinstance(stage, dict) or stage.get("stage") != phase:
            raise ValueError(f"invalid resource stage: {phase}")
        _number(stage.get("duration_seconds"), f"{phase} duration")
        if stage.get("tool_calls") != 1:
            raise ValueError(f"{phase} must record exactly one RPC")
    if resource.get("total_tool_calls") != len(expected_phases):
        raise ValueError("resource usage must total exactly eight quant RPCs")

    roles = resource.get("role_breakdown")
    if not isinstance(roles, dict) or set(roles) != set(EXPECTED_ROLES):
        raise ValueError("resource usage does not contain exact formal roles")
    role_fields: dict[str, list[int | float | None]] = {
        field: [] for field in ("input_tokens", "output_tokens", "cache_tokens")
    }
    for role in EXPECTED_ROLES:
        usage = roles[role]
        if not isinstance(usage, dict):
            raise ValueError(f"invalid role usage: {role}")
        for field in role_fields:
            value = usage.get(field)
            if value is not None:
                _number(value, f"{role} {field}")
            role_fields[field].append(value)
    for field, values in role_fields.items():
        total = resource.get(f"total_{field}")
        if any(value is None for value in values):
            if total is not None:
                raise ValueError(f"partial {field} cannot produce a formal total")
        else:
            expected_total = sum(float(value) for value in values if value is not None)
            if _number(total, f"total {field}") != expected_total:
                raise ValueError(f"total {field} does not match formal roles")

    tool_schema = resource.get("tool_schema")
    if (
        not isinstance(tool_schema, dict)
        or tool_schema.get("schema") != "formal_tool_schema_accounting/v1"
        or tool_schema.get("scope") != "formal_quant_rpc_toolcards"
        or tool_schema.get("projection")
        != "toolcard_name_description_input_params"
    ):
        raise ValueError("tool schema accounting is missing")
    tools = tool_schema.get("tools")
    if not isinstance(tools, list) or tool_schema.get("tool_count") != 8:
        raise ValueError("tool schema must contain the exact eight formal ToolCards")
    actual_role_tools = {role: set() for role in EXPECTED_ROLES}
    for tool in tools:
        if not isinstance(tool, dict):
            raise ValueError("invalid formal ToolCard projection")
        role = tool.get("role")
        name = tool.get("name")
        if (
            role not in actual_role_tools
            or not isinstance(name, str)
            or not isinstance(tool.get("description"), str)
            or not tool["description"]
            or not isinstance(tool.get("input_params"), dict)
            or name in actual_role_tools[role]
        ):
            raise ValueError("invalid formal ToolCard projection")
        actual_role_tools[role].add(name)
    if actual_role_tools != EXPECTED_ROLE_TOOLS:
        raise ValueError("tool schema does not match the exact formal role boundary")
    tool_bytes = canonical_json_bytes(tools)
    schema_sha = tool_schema.get("sha256")
    if (
        not isinstance(schema_sha, str)
        or not SHA256_PATTERN.fullmatch(schema_sha)
        or hashlib.sha256(tool_bytes).hexdigest() != schema_sha
    ):
        raise ValueError("tool schema hash is missing")
    if _number(tool_schema.get("utf8_bytes"), "tool schema bytes") != len(tool_bytes):
        raise ValueError("tool schema byte count mismatch")
    if tool_schema.get("tokens") is not None:
        _number(tool_schema["tokens"], "tool schema tokens")

    return {
        "session_id": session_id,
        "market_content_sha256": rebuilt_trace["market_content_sha256"],
        "snapshot_id": snapshot_id,
        "snapshot_manifest_sha256": manifest_sha,
        "tool_schema_sha256": schema_sha,
        "total_duration_seconds": resource.get("total_duration_seconds"),
        "peak_memory_mb": resource.get("peak_memory_mb"),
        "max_concurrency": resource.get("max_concurrency"),
        "total_input_tokens": resource.get("total_input_tokens"),
    }


def aggregate_formal_resources(
    runs: Sequence[tuple[Path, str]],
) -> dict[str, Any]:
    """Validate and aggregate exactly three caller-hash-bound formal runs."""
    if len(runs) != REQUIRED_RUNS:
        raise ValueError(f"resource benchmark requires exactly {REQUIRED_RUNS} runs")
    resolved = [path.resolve() for path, _sha in runs]
    if len(set(resolved)) != REQUIRED_RUNS:
        raise ValueError("resource benchmark inputs must be distinct files")
    summaries = [_read_bound_json(path, sha) for path, sha in runs]
    validated = [_validate_summary(summary) for summary in summaries]
    sessions = [row["session_id"] for row in validated]
    if len(set(sessions)) != REQUIRED_RUNS:
        raise ValueError("formal session IDs must be distinct")
    identity_fields = (
        "market_content_sha256",
        "snapshot_id",
        "snapshot_manifest_sha256",
        "tool_schema_sha256",
    )
    for field in identity_fields:
        if len({row[field] for row in validated}) != 1:
            raise ValueError(f"formal runs do not share one {field}")

    durations = [row["total_duration_seconds"] for row in validated]
    p95_duration = _optional_metric(
        durations,
        label="total duration",
        reducer=nearest_rank_p95,
    )
    peak_rss = _optional_metric(
        [row["peak_memory_mb"] for row in validated],
        label="peak RSS",
        reducer=max,
    )
    max_concurrency = _optional_metric(
        [row["max_concurrency"] for row in validated],
        label="max concurrency",
        reducer=max,
    )
    max_input_tokens = _optional_metric(
        [row["total_input_tokens"] for row in validated],
        label="input tokens",
        reducer=max,
    )
    reduction = (
        1.0 - max_input_tokens / BASELINE_INPUT_TOKENS
        if max_input_tokens is not None
        else None
    )
    gates = {
        "three_formal_runs": {"measured": True, "passed": True, "value": 3},
        "p95_duration_seconds": {
            "measured": p95_duration is not None,
            "passed": p95_duration is not None and p95_duration <= MAX_P95_SECONDS,
            "value": p95_duration,
            "limit": MAX_P95_SECONDS,
        },
        "peak_process_tree_rss_mb": {
            "measured": peak_rss is not None,
            "passed": peak_rss is not None and peak_rss <= MAX_PEAK_RSS_MB,
            "value": peak_rss,
            "limit": MAX_PEAK_RSS_MB,
        },
        "observed_quant_rpc_concurrency": {
            "measured": max_concurrency is not None,
            "passed": max_concurrency is not None and max_concurrency >= 1,
            "value": max_concurrency,
        },
        "input_token_reduction": {
            "measured": reduction is not None,
            "passed": reduction is not None and reduction >= 0.50,
            "value": reduction,
            "baseline_input_tokens": BASELINE_INPUT_TOKENS,
            "max_observed_input_tokens": max_input_tokens,
        },
    }
    payload = {
        "schema": "formal_resource_benchmark/v1",
        "evidence_level": "OFFLINE_AGGREGATE_REQUIRES_WINDOWS_REVIEW",
        "business_passed": False,
        "run_count": REQUIRED_RUNS,
        "summary_sha256": [sha for _path, sha in runs],
        "session_ids": sessions,
        **{field: validated[0][field] for field in identity_fields},
        "gates": gates,
        "all_resource_gates_passed": all(gate["passed"] for gate in gates.values()),
    }
    return {**payload, "benchmark_sha256": canonical_sha256(payload)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="append",
        nargs=2,
        metavar=("SUMMARY", "SHA256"),
        required=True,
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = aggregate_formal_resources(
        [(Path(path), sha) for path, sha in args.run]
    )
    result["generated_at"] = datetime.now(timezone.utc).isoformat()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("xb") as handle:
        handle.write(canonical_json_bytes(result) + b"\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
