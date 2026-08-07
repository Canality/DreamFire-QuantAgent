"""Offline aggregation tests for three hash-bound formal resource runs."""

from __future__ import annotations

import hashlib
import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest

from evaluation.aggregate_formal_resources import (
    aggregate_formal_resources,
    main as aggregate_main,
)
from jiuwenswarm.quant.phase_state import (
    QUANT_PHASE_SEQUENCE,
    build_trace_receipt,
    canonical_json_bytes,
)
from jiuwenswarm.quant.stock_pool import ALL_STOCKS


MARKET_HASH = "a" * 64
SNAPSHOT_ID = "snapshot-benchmark"
MANIFEST_HASH = "b" * 64
ROLE_TOOLS = {
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


def _bound(payload: dict) -> dict:
    return {
        **payload,
        "market_content_sha256": MARKET_HASH,
        "cached": False,
        "executed": True,
    }


def _valid_calls() -> list[dict]:
    tickers = list(ALL_STOCKS)
    candidate_id = "formal-resource-fixture"
    binding = {
        "schema": "candidate_artifact_binding/v1",
        "candidate_id": candidate_id,
        "snapshot_id": SNAPSHOT_ID,
        "report_count": 49,
        "announcement_facts": 1,
        "disclosure_reports": 1,
        "snapshot_manifest_sha256": MANIFEST_HASH,
        "report_manifest_sha256": "1" * 64,
        "evidence_manifest_sha256": "2" * 64,
        "company_reports_tree_sha256": "3" * 64,
        "binding_sha256": "4" * 64,
        "candidate_binding_file_sha256": "5" * 64,
    }
    payloads = (
        _bound({
            "success": True,
            "coverage_complete": True,
            "n_stocks": 49,
            "expected_stocks": 49,
            "date_range": "2025-01-02 00:00:00 ~ 2025-05-21 00:00:00",
            "n_days": 90,
        }),
        _bound({
            "success": True,
            "n_stocks_analyzed": 49,
            "all_composite": {
                ticker: float(index) for index, ticker in enumerate(tickers)
            },
        }),
        _bound({
            "success": True,
            "verdict": "overweight",
            "candidate_tickers": tickers[:12],
            "evidence_ids": ["factor-snapshot"],
        }),
        _bound({
            "success": True,
            "verdict": "underweight",
            "candidate_tickers": tickers[-12:],
            "evidence_ids": ["factor-snapshot"],
        }),
        _bound({"success": True, "n_selected": 15, "n_sectors_covered": 6}),
        _bound({
            "success": True,
            "n_holdings": 15,
            "cash_reserve": 0.10,
            "portfolio": [
                {"ticker": ticker, "sector": f"sector-{index}", "weight": 0.06}
                for index, ticker in enumerate(tickers[:15])
            ],
        }),
        _bound({"success": True, "n_forward_returns": 20}),
        _bound({
            "success": True,
            "report": "fixture report",
            "summary": {"n_holdings": 15},
            "candidate_package": {
                "path": f"/fixture/submission_candidates/{candidate_id}",
                "candidate_id": candidate_id,
                "immutable": True,
                "quality_passed": True,
                "n_reports": 49,
                "snapshot_id": SNAPSHOT_ID,
                "snapshot_manifest_sha256": MANIFEST_HASH,
                "announcement_facts": 1,
                "disclosure_reports": 1,
                "artifact_binding": binding,
            },
        }),
    )
    return [
        {"method": method, "params_keys": [], "payload": payload}
        for (_phase, method), payload in zip(
            QUANT_PHASE_SEQUENCE, payloads, strict=True
        )
    ]


def _summary(
    session_id: str,
    *,
    duration: float = 90.0,
    peak_rss: float | None = 500.0,
    concurrency: int | None = 1,
    input_tokens: int | None = 500_000,
) -> dict:
    calls = _valid_calls()
    candidate = deepcopy(calls[-1]["payload"]["candidate_package"])
    phases = {phase: True for phase, _method in reversed(QUANT_PHASE_SEQUENCE)}
    stages = {
        phase: {
            "stage": phase,
            "duration_seconds": float(index + 1),
            "tool_calls": 1,
        }
        for index, (phase, _method) in enumerate(reversed(QUANT_PHASE_SEQUENCE))
    }
    roles = {
        role: {
            "stage": role,
            "input_tokens": (
                None
                if input_tokens is None
                else input_tokens if role == "quant-leader" else 0
            ),
            "output_tokens": 2,
            "cache_tokens": 1,
        }
        for role in reversed(
            ("quant-leader", "alpha_analyst", "risk_evidence_analyst")
        )
    }
    tools = [
        {
            "role": role,
            "name": name,
            "description": f"formal {name}",
            "input_params": {"type": "object"},
        }
        for role in sorted(ROLE_TOOLS)
        for name in sorted(ROLE_TOOLS[role])
    ]
    tool_bytes = canonical_json_bytes(tools)
    return {
        "session_id": session_id,
        "validation_passed": True,
        "quant_phases": phases,
        "quant_rpc_calls": calls,
        "deterministic_trace": build_trace_receipt(calls, mode="LIVE_TRACE"),
        "candidate_package": candidate,
        "resource_usage": {
            "run_id": session_id,
            "total_duration_seconds": duration,
            "peak_memory_mb": peak_rss,
            "max_concurrency": concurrency,
            "total_input_tokens": input_tokens,
            "total_output_tokens": 6,
            "total_cache_tokens": 3,
            "total_tool_calls": 8,
            "stages": stages,
            "role_breakdown": roles,
            "tool_schema": {
                "schema": "formal_tool_schema_accounting/v1",
                "scope": "formal_quant_rpc_toolcards",
                "projection": "toolcard_name_description_input_params",
                "tools": tools,
                "tool_count": 8,
                "sha256": hashlib.sha256(tool_bytes).hexdigest(),
                "utf8_bytes": len(tool_bytes),
                "tokens": 2_000,
            },
        },
    }


def _write_runs(tmp_path: Path, summaries: list[dict]) -> list[tuple[Path, str]]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    runs = []
    for index, summary in enumerate(summaries):
        path = tmp_path / f"summary-{index}.json"
        path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        runs.append((path, hashlib.sha256(path.read_bytes()).hexdigest()))
    return runs


def test_three_same_snapshot_runs_pass_resource_gates_without_business_claim(
    tmp_path: Path,
) -> None:
    runs = _write_runs(tmp_path, [
        _summary("formal-1", duration=80.0, peak_rss=490.0),
        _summary("formal-2", duration=95.0, peak_rss=510.0),
        _summary("formal-3", duration=100.0, peak_rss=520.0),
    ])

    first = aggregate_formal_resources(runs)
    second = aggregate_formal_resources(runs)

    assert first == second
    assert first["gates"]["p95_duration_seconds"]["value"] == 100.0
    assert first["gates"]["peak_process_tree_rss_mb"]["value"] == 520.0
    assert first["gates"]["input_token_reduction"]["passed"] is True
    assert first["all_resource_gates_passed"] is True
    assert first["business_passed"] is False
    assert first["evidence_level"] == "OFFLINE_AGGREGATE_REQUIRES_WINDOWS_REVIEW"


@pytest.mark.parametrize("count", [2, 4])
def test_requires_exactly_three_distinct_inputs(tmp_path: Path, count: int) -> None:
    runs = _write_runs(
        tmp_path, [_summary(f"formal-{index}") for index in range(count)]
    )
    with pytest.raises(ValueError, match="exactly 3"):
        aggregate_formal_resources(runs)


def test_hash_tamper_and_cross_snapshot_inputs_are_rejected(tmp_path: Path) -> None:
    summaries = [_summary(f"formal-{index}") for index in range(3)]
    runs = _write_runs(tmp_path, summaries)
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        aggregate_formal_resources([(runs[0][0], "0" * 64), *runs[1:]])

    summaries[2]["quant_rpc_calls"][0]["payload"]["date_range"] = (
        "2025-02-01 00:00:00 ~ 2025-06-21 00:00:00"
    )
    summaries[2]["deterministic_trace"] = build_trace_receipt(
        summaries[2]["quant_rpc_calls"], mode="LIVE_TRACE"
    )
    runs = _write_runs(tmp_path, summaries)
    with pytest.raises(ValueError, match="one window_key"):
        aggregate_formal_resources(runs)


def test_trace_candidate_and_schema_tampering_fail_closed(tmp_path: Path) -> None:
    base = [_summary(f"formal-{index}") for index in range(3)]
    tampered = deepcopy(base)
    tampered[1]["deterministic_trace"]["trace_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="trace mismatch"):
        aggregate_formal_resources(_write_runs(tmp_path / "trace", tampered))

    mutable = deepcopy(base)
    mutable[0]["candidate_package"]["immutable"] = False
    with pytest.raises(ValueError, match="mutable"):
        aggregate_formal_resources(_write_runs(tmp_path / "candidate", mutable))

    schema = deepcopy(base)
    changed_schema = schema[2]["resource_usage"]["tool_schema"]
    changed_schema["tools"][0]["description"] = "different formal schema"
    changed_bytes = canonical_json_bytes(changed_schema["tools"])
    changed_schema["sha256"] = hashlib.sha256(changed_bytes).hexdigest()
    changed_schema["utf8_bytes"] = len(changed_bytes)
    with pytest.raises(ValueError, match="tool_schema_sha256"):
        aggregate_formal_resources(_write_runs(tmp_path / "schema", schema))

    omitted = deepcopy(base)
    omitted_schema = omitted[0]["resource_usage"]["tool_schema"]
    omitted_schema["tools"] = omitted_schema["tools"][:-1]
    omitted_schema["tool_count"] = 7
    omitted_bytes = canonical_json_bytes(omitted_schema["tools"])
    omitted_schema["sha256"] = hashlib.sha256(omitted_bytes).hexdigest()
    omitted_schema["utf8_bytes"] = len(omitted_bytes)
    with pytest.raises(ValueError, match="exact eight"):
        aggregate_formal_resources(_write_runs(tmp_path / "omitted", omitted))


def test_missing_measurements_are_not_invented(tmp_path: Path) -> None:
    runs = _write_runs(tmp_path, [
        _summary("formal-1"),
        _summary("formal-2", peak_rss=None),
        _summary("formal-3", input_tokens=None),
    ])

    result = aggregate_formal_resources(runs)

    assert result["gates"]["peak_process_tree_rss_mb"] == {
        "measured": False,
        "passed": False,
        "value": None,
        "limit": 600.0,
    }
    assert result["gates"]["input_token_reduction"]["measured"] is False
    assert result["gates"]["input_token_reduction"]["value"] is None
    assert result["all_resource_gates_passed"] is False


def test_cli_is_create_once_and_preserves_benchmark_hash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runs = _write_runs(
        tmp_path, [_summary(f"formal-{index}") for index in range(3)]
    )
    output = tmp_path / "benchmark.json"
    argv = ["aggregate_formal_resources.py"]
    for path, sha in runs:
        argv.extend(["--run", str(path), sha])
    argv.extend(["--output", str(output)])
    monkeypatch.setattr(sys, "argv", argv)

    assert aggregate_main() == 0
    written = json.loads(output.read_text(encoding="utf-8"))
    assert written["benchmark_sha256"] == aggregate_formal_resources(runs)[
        "benchmark_sha256"
    ]
    with pytest.raises(FileExistsError):
        aggregate_main()


def test_aggregator_has_no_network_or_model_dependency() -> None:
    source = (
        Path(__file__).resolve().parents[3]
        / "evaluation"
        / "aggregate_formal_resources.py"
    ).read_text(encoding="utf-8")
    assert "requests" not in source
    assert "openjiuwen" not in source
    assert "_call_rpc" not in source
