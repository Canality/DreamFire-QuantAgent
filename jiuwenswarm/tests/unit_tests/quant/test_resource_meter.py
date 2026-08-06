"""Unit tests for resource_meter — Phase R5."""

import json
import os
import tempfile
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from jiuwenswarm.quant.reporting.resource_meter import (
    ObservedConcurrency,
    ProcessTreeRssSampler,
    ResourceMeter,
    ResourceReport,
    StageMetrics,
    canonical_tool_schema_accounting,
    new_resource_report,
)


def test_stage_metrics_defaults():
    sm = StageMetrics(stage="fetch_data")
    assert sm.stage == "fetch_data"
    assert sm.input_tokens is None  # not measured, not 0
    assert sm.output_tokens is None
    assert sm.tool_calls == 0


def test_stage_metrics_elapsed():
    sm = StageMetrics(stage="test", duration_seconds=2.5)
    assert sm.elapsed() == 2.5


def test_resource_meter_context_manager():
    report = new_resource_report("test-run-1")
    with ResourceMeter("test_stage", report) as meter:
        meter.record_tool_call()
        meter.record_retry()
        meter.record_tokens(input_tokens=100, output_tokens=50)

    assert "test_stage" in report.stages
    sm = report.stages["test_stage"]
    assert sm.tool_calls == 1
    assert sm.retries == 1
    assert sm.input_tokens == 100
    assert sm.output_tokens == 50
    assert sm.cache_tokens is None
    assert sm.started_at is not None
    assert sm.finished_at is not None


def test_resource_report_finalize():
    report = new_resource_report("test-run-2")
    with ResourceMeter("s1", report) as m:
        m.record_tokens(input_tokens=100, output_tokens=50)
    with ResourceMeter("s2", report) as m:
        m.record_tokens(input_tokens=200, output_tokens=100)

    report.finalize()
    assert report.total_input_tokens == 300
    assert report.total_output_tokens == 150
    assert report.total_tool_calls == 0
    assert report.finished_at is not None


def test_resource_report_missing_tokens_marked():
    """When some stages don't provide tokens, mark as missing."""
    report = new_resource_report("test-run-3")
    with ResourceMeter("s1", report) as m:
        m.record_tokens(input_tokens=100)  # no output_tokens
    with ResourceMeter("s2", report) as m:
        m.record_tokens(output_tokens=50)  # no input_tokens

    report.finalize()
    # Only s1 has input, s2 doesn't → partial
    assert report.total_input_tokens is None
    assert report.total_output_tokens is None
    assert len(report.missing_measurements) > 0


def test_resource_report_save_json():
    report = new_resource_report("test-run-4")
    with ResourceMeter("s1", report) as m:
        m.record_tokens(input_tokens=100, output_tokens=50)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
        tmp = f.name
    try:
        report.finalize()
        report.save_json(tmp)
        with open(tmp, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["run_id"] == "test-run-4"
        assert "stages" in data
    finally:
        os.unlink(tmp)


def test_resource_report_save_markdown():
    report = new_resource_report("test-run-5")
    with ResourceMeter("s1", report) as m:
        m.record_tokens(input_tokens=100, output_tokens=50)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
        tmp = f.name
    try:
        report.finalize()
        report.save_markdown(tmp)
        with open(tmp, "r", encoding="utf-8") as f:
            content = f.read()
        assert "test-run-5" in content
        assert "资源消耗日志" in content
    finally:
        os.unlink(tmp)


def test_record_error():
    report = new_resource_report("test-run-6")
    with ResourceMeter("error_stage", report) as m:
        m.record_error("Connection timeout")
        m.record_error("Retry exhausted")

    sm = report.stages["error_stage"]
    assert len(sm.errors) == 2
    assert "Connection timeout" in sm.errors


def test_explicit_run_measurements_survive_finalize() -> None:
    roles = {
        role: StageMetrics(
            stage=role,
            input_tokens=10,
            output_tokens=2,
            cache_tokens=1,
        )
        for role in ("quant-leader", "alpha_analyst", "risk_evidence_analyst")
    }
    report = ResourceReport(
        run_id="formal",
        started_at=datetime.now(timezone.utc),
        stages={"fetch": StageMetrics(stage="fetch", duration_seconds=0.25)},
        role_breakdown=roles,
        total_duration_seconds=9.5,
        peak_memory_mb=321.5,
        total_cpu_time_seconds=4.25,
        max_concurrency=1,
    )

    report.finalize()

    assert report.total_duration_seconds == 9.5
    assert report.total_input_tokens == 30
    assert report.total_output_tokens == 6
    assert report.total_cache_tokens == 3
    assert report.peak_memory_mb == 321.5
    assert report.total_cpu_time_seconds == 4.25


def test_incomplete_role_usage_never_becomes_a_partial_total() -> None:
    report = ResourceReport(
        run_id="formal",
        started_at=datetime.now(timezone.utc),
        role_breakdown={
            "quant-leader": StageMetrics(stage="quant-leader", input_tokens=100),
            "alpha_analyst": StageMetrics(stage="alpha_analyst", input_tokens=20),
            "risk_evidence_analyst": StageMetrics(stage="risk_evidence_analyst"),
        },
    )

    report.finalize()

    assert report.total_input_tokens is None
    assert "input_tokens (partial or absent)" in report.missing_measurements


def test_observed_concurrency_reports_only_real_admission() -> None:
    tracker = ObservedConcurrency()
    assert tracker.maximum is None
    tracker.enter()
    tracker.enter()
    assert tracker.maximum == 2
    tracker.exit()
    tracker.exit()
    with pytest.raises(RuntimeError, match="without enter"):
        tracker.exit()


def test_process_tree_sampler_sums_root_and_live_children() -> None:
    mib = 1024 * 1024

    class FakeProcess:
        def __init__(self, rss: int, children=(), *, gone: bool = False):
            self._rss = rss
            self._children = list(children)
            self._gone = gone

        def children(self, recursive: bool):
            assert recursive is True
            return self._children

        def memory_info(self):
            if self._gone:
                raise OSError("process exited")
            return SimpleNamespace(rss=self._rss)

    root = FakeProcess(100 * mib, [FakeProcess(20 * mib), FakeProcess(5 * mib, gone=True)])
    sampler = ProcessTreeRssSampler(root, interval_seconds=0.01)

    assert sampler.sample_once() == 120.0
    assert sampler.current_rss_mb == 120.0
    assert sampler.peak_rss_mb == 120.0
    assert sampler.sample_count == 1
    assert sampler.max_processes == 2
    with pytest.raises(ValueError, match="positive"):
        ProcessTreeRssSampler(root, interval_seconds=0)


def test_tool_schema_accounting_is_canonical_and_content_bound() -> None:
    class FakeTool:
        def __init__(self, name: str, description: str):
            self.card = SimpleNamespace(
                name=name,
                description=description,
                input_params={"type": "object", "properties": {"x": {"type": "string"}}},
            )

    alpha = FakeTool("alpha", "中文说明")
    risk = FakeTool("risk", "risk")
    first = canonical_tool_schema_accounting({"risk": [risk], "alpha": [alpha]})
    second = canonical_tool_schema_accounting({"alpha": [alpha], "risk": [risk]})

    assert first == second
    assert first["scope"] == "formal_quant_rpc_toolcards"
    assert first["tool_count"] == 2
    assert len(first["tools"]) == 2
    assert first["utf8_bytes"] > 0
    assert len(first["sha256"]) == 64
    assert (first["tokens"] is None) == (first["tokenizer"] is None)
    alpha.card.description = "changed"
    assert canonical_tool_schema_accounting({"alpha": [alpha], "risk": [risk]})[
        "sha256"
    ] != first["sha256"]
