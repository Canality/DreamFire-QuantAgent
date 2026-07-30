"""Resource metering: runtime measurement of tokens, time, CPU, memory.

Never estimates or hardcodes — only reports what was actually measured.
Missing measurements are marked "unknown", not guessed or set to 0.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List


@dataclass
class StageMetrics:
    """Resource usage for one pipeline stage."""
    stage: str
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_seconds: float | None = None
    input_tokens: int | None = None       # None = not measured
    output_tokens: int | None = None
    cache_tokens: int | None = None
    tool_calls: int = 0
    retries: int = 0
    errors: List[str] = field(default_factory=list)
    peak_memory_mb: float | None = None
    cpu_time_seconds: float | None = None

    def elapsed(self) -> float | None:
        if self.started_at and self.finished_at:
            return (self.finished_at - self.started_at).total_seconds()
        return self.duration_seconds


@dataclass
class ResourceReport:
    """Complete resource usage for one full run."""
    run_id: str
    started_at: datetime
    finished_at: datetime | None = None
    stages: Dict[str, StageMetrics] = field(default_factory=dict)

    # Aggregates (computed, not estimated)
    total_duration_seconds: float | None = None
    total_input_tokens: int | None = None
    total_output_tokens: int | None = None
    total_cache_tokens: int | None = None
    total_tool_calls: int = 0
    total_retries: int = 0
    peak_memory_mb: float | None = None
    total_cpu_time_seconds: float | None = None
    max_concurrency: int | None = None

    # Per-role breakdown (for multi-agent runs)
    role_breakdown: Dict[str, StageMetrics] = field(default_factory=dict)

    # Status
    missing_measurements: List[str] = field(default_factory=list)

    def finalize(self) -> None:
        """Compute aggregates from stages. Call once at end of run."""
        self.finished_at = datetime.now(timezone.utc)
        self.total_tool_calls = 0
        self.total_retries = 0
        self.missing_measurements = []
        durations = []
        for sm in self.stages.values():
            e = sm.elapsed()
            if e is not None:
                durations.append(e)
            self.total_tool_calls += sm.tool_calls
            self.total_retries += sm.retries

        self.total_duration_seconds = sum(durations) if durations else None

        # Token totals: only if ALL stages provide measurements
        inputs = [sm.input_tokens for sm in self.stages.values() if sm.input_tokens is not None]
        outputs = [sm.output_tokens for sm in self.stages.values() if sm.output_tokens is not None]
        caches = [sm.cache_tokens for sm in self.stages.values() if sm.cache_tokens is not None]

        if inputs and len(inputs) == len(self.stages):
            self.total_input_tokens = sum(inputs)
        else:
            self.missing_measurements.append("input_tokens (partial or absent)")

        if outputs and len(outputs) == len(self.stages):
            self.total_output_tokens = sum(outputs)
        else:
            self.missing_measurements.append("output_tokens (partial or absent)")

        if caches and len(caches) == len(self.stages):
            self.total_cache_tokens = sum(caches)
        else:
            self.missing_measurements.append("cache_tokens (partial or absent)")

        # Memory
        mems = [sm.peak_memory_mb for sm in self.stages.values() if sm.peak_memory_mb is not None]
        self.peak_memory_mb = max(mems) if mems else None
        if self.peak_memory_mb is None:
            self.missing_measurements.append("peak_memory_mb")
        cpu_times = [
            sm.cpu_time_seconds
            for sm in self.stages.values()
            if sm.cpu_time_seconds is not None
        ]
        self.total_cpu_time_seconds = sum(cpu_times) if cpu_times else None
        if self.total_cpu_time_seconds is None:
            self.missing_measurements.append("total_cpu_time_seconds")
        if self.max_concurrency is None:
            self.missing_measurements.append("max_concurrency")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "total_duration_seconds": self.total_duration_seconds,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_cache_tokens": self.total_cache_tokens,
            "total_tool_calls": self.total_tool_calls,
            "total_retries": self.total_retries,
            "peak_memory_mb": self.peak_memory_mb,
            "total_cpu_time_seconds": self.total_cpu_time_seconds,
            "max_concurrency": self.max_concurrency,
            "missing_measurements": self.missing_measurements,
            "stages": {
                name: {
                    "stage": sm.stage,
                    "duration_seconds": sm.elapsed(),
                    "input_tokens": sm.input_tokens,
                    "output_tokens": sm.output_tokens,
                    "cache_tokens": sm.cache_tokens,
                    "tool_calls": sm.tool_calls,
                    "retries": sm.retries,
                    "errors": sm.errors,
                    "peak_memory_mb": sm.peak_memory_mb,
                    "cpu_time_seconds": sm.cpu_time_seconds,
                }
                for name, sm in self.stages.items()
            },
            "role_breakdown": {
                name: {
                    "stage": sm.stage,
                    "duration_seconds": sm.elapsed(),
                    "input_tokens": sm.input_tokens,
                    "output_tokens": sm.output_tokens,
                    "cache_tokens": sm.cache_tokens,
                    "tool_calls": sm.tool_calls,
                    "retries": sm.retries,
                    "errors": sm.errors,
                }
                for name, sm in self.role_breakdown.items()
            },
        }

    def save_json(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

    def save_markdown(self, path: str) -> None:
        lines = [
            "# 资源消耗日志",
            "",
            f"- **运行 ID**: {self.run_id}",
            f"- **开始时间**: {self.started_at.isoformat() if self.started_at else 'N/A'}",
            f"- **结束时间**: {self.finished_at.isoformat() if self.finished_at else 'N/A'}",
            "",
            "## 总体统计",
            "",
        ]
        lines.append(f"- **总耗时**: {self.total_duration_seconds:.1f}s" if self.total_duration_seconds else "- **总耗时**: 未测量")
        lines.append(f"- **Input Tokens**: {self.total_input_tokens}" if self.total_input_tokens is not None else "- **Input Tokens**: 未测量")
        lines.append(f"- **Output Tokens**: {self.total_output_tokens}" if self.total_output_tokens is not None else "- **Output Tokens**: 未测量")
        lines.append(f"- **Cache Tokens**: {self.total_cache_tokens}" if self.total_cache_tokens is not None else "- **Cache Tokens**: 未测量")
        lines.append(f"- **工具调用总数**: {self.total_tool_calls}")
        lines.append(f"- **重试次数**: {self.total_retries}")
        lines.append(f"- **峰值内存 (MB)**: {self.peak_memory_mb:.0f}" if self.peak_memory_mb else "- **峰值内存 (MB)**: 未测量")
        lines.append(
            f"- **CPU 时间 (s)**: {self.total_cpu_time_seconds:.1f}"
            if self.total_cpu_time_seconds is not None
            else "- **CPU 时间 (s)**: 未测量"
        )
        lines.append(
            f"- **最大并发**: {self.max_concurrency}"
            if self.max_concurrency is not None
            else "- **最大并发**: 未测量"
        )
        lines.append("")
        if self.missing_measurements:
            lines.append("## 缺失测量项")
            lines.append("")
            for m in self.missing_measurements:
                lines.append(f"- {m}")
            lines.append("")

        lines.append("## 阶段详情")
        lines.append("")
        lines.append("| 阶段 | 耗时(s) | Input Tokens | Output Tokens | 工具调用 | 重试 | 错误 |")
        lines.append("|------|---------|-------------|---------------|----------|------|------|")
        for name, sm in self.stages.items():
            dur = f"{sm.elapsed():.1f}" if sm.elapsed() is not None else "N/A"
            itok = str(sm.input_tokens) if sm.input_tokens is not None else "?"
            otok = str(sm.output_tokens) if sm.output_tokens is not None else "?"
            errs = str(len(sm.errors)) if sm.errors else "0"
            lines.append(f"| {name} | {dur} | {itok} | {otok} | {sm.tool_calls} | {sm.retries} | {errs} |")

        if self.role_breakdown:
            lines.extend([
                "",
                "## Agent 角色用量",
                "",
                "| 角色 | Input Tokens | Output Tokens | Cache Tokens | 工具调用 |",
                "|------|-------------:|--------------:|-------------:|---------:|",
            ])
            for name, sm in self.role_breakdown.items():
                lines.append(
                    f"| {name} | {sm.input_tokens if sm.input_tokens is not None else '?'} "
                    f"| {sm.output_tokens if sm.output_tokens is not None else '?'} "
                    f"| {sm.cache_tokens if sm.cache_tokens is not None else '?'} "
                    f"| {sm.tool_calls} |"
                )

        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")


class ResourceMeter:
    """Context manager for measuring a single stage's resource usage."""

    def __init__(self, stage_name: str, report: ResourceReport):
        self._stage = StageMetrics(stage=stage_name)
        self._name = stage_name
        self._report = report
        self._start_cpu: float | None = None

    def __enter__(self) -> "ResourceMeter":
        self._stage.started_at = datetime.now(timezone.utc)
        try:
            self._start_cpu = os.times().user + os.times().system
        except (AttributeError, OSError):
            self._start_cpu = None
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self._stage.finished_at = datetime.now(timezone.utc)
        if self._start_cpu is not None:
            try:
                end_cpu = os.times().user + os.times().system
                self._stage.cpu_time_seconds = end_cpu - self._start_cpu
            except (AttributeError, OSError):
                pass
        self._report.stages[self._name] = self._stage

    def record_tokens(self, input_tokens: int | None = None, output_tokens: int | None = None, cache_tokens: int | None = None) -> None:
        if input_tokens is not None:
            self._stage.input_tokens = (self._stage.input_tokens or 0) + input_tokens
        if output_tokens is not None:
            self._stage.output_tokens = (self._stage.output_tokens or 0) + output_tokens
        if cache_tokens is not None:
            self._stage.cache_tokens = (self._stage.cache_tokens or 0) + cache_tokens

    def record_tool_call(self) -> None:
        self._stage.tool_calls += 1

    def record_retry(self) -> None:
        self._stage.retries += 1

    def record_error(self, error: str) -> None:
        self._stage.errors.append(error)


def new_resource_report(run_id: str) -> ResourceReport:
    return ResourceReport(
        run_id=run_id,
        started_at=datetime.now(timezone.utc),
    )
