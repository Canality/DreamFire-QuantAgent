"""Unit tests for resource_meter — Phase R5."""

import json
import os
import tempfile

from jiuwenswarm.quant.reporting.resource_meter import (
    ResourceMeter,
    StageMetrics,
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
