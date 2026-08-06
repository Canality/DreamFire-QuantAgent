"""Resource metering: runtime measurement of tokens, time, CPU, memory.

Never estimates or hardcodes — only reports what was actually measured.
Missing measurements are marked "unknown", not guessed or set to 0.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Sequence


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
    current_memory_mb: float | None = None
    memory_sample_count: int | None = None
    memory_sample_interval_seconds: float | None = None
    max_processes: int | None = None

    # Per-role breakdown (for multi-agent runs)
    role_breakdown: Dict[str, StageMetrics] = field(default_factory=dict)
    tool_schema: Dict[str, Any] = field(default_factory=dict)

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

        if self.total_duration_seconds is None:
            self.total_duration_seconds = sum(durations) if durations else None

        # LLM token totals come from roles when available. Timing-only RPC stages
        # cannot safely attribute surrounding model context to one tool call.
        token_records = self.role_breakdown or self.stages
        inputs = [
            sm.input_tokens for sm in token_records.values()
            if sm.input_tokens is not None
        ]
        outputs = [
            sm.output_tokens for sm in token_records.values()
            if sm.output_tokens is not None
        ]
        caches = [
            sm.cache_tokens for sm in token_records.values()
            if sm.cache_tokens is not None
        ]

        if inputs and len(inputs) == len(token_records):
            self.total_input_tokens = sum(inputs)
        else:
            self.missing_measurements.append("input_tokens (partial or absent)")

        if outputs and len(outputs) == len(token_records):
            self.total_output_tokens = sum(outputs)
        else:
            self.missing_measurements.append("output_tokens (partial or absent)")

        if caches and len(caches) == len(token_records):
            self.total_cache_tokens = sum(caches)
        else:
            self.missing_measurements.append("cache_tokens (partial or absent)")

        # Memory
        mems = [
            sm.peak_memory_mb
            for sm in self.stages.values()
            if sm.peak_memory_mb is not None
        ]
        if self.peak_memory_mb is None and mems:
            self.peak_memory_mb = max(mems)
        if self.peak_memory_mb is None:
            self.missing_measurements.append("peak_memory_mb")
        cpu_times = [
            sm.cpu_time_seconds
            for sm in self.stages.values()
            if sm.cpu_time_seconds is not None
        ]
        if self.total_cpu_time_seconds is None and cpu_times:
            self.total_cpu_time_seconds = sum(cpu_times)
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
            "current_memory_mb": self.current_memory_mb,
            "memory_sample_count": self.memory_sample_count,
            "memory_sample_interval_seconds": self.memory_sample_interval_seconds,
            "max_processes": self.max_processes,
            "missing_measurements": self.missing_measurements,
            "tool_schema": self.tool_schema,
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
            f"- **当前进程树内存 (MB)**: {self.current_memory_mb:.0f}"
            if self.current_memory_mb is not None
            else "- **当前进程树内存 (MB)**: 未测量"
        )
        lines.append(
            f"- **内存采样数**: {self.memory_sample_count}"
            if self.memory_sample_count is not None
            else "- **内存采样数**: 未测量"
        )
        lines.append(
            f"- **进程树最大进程数**: {self.max_processes}"
            if self.max_processes is not None
            else "- **进程树最大进程数**: 未测量"
        )
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
        if self.tool_schema:
            lines.extend([
                "## 工具 Schema 计量",
                "",
                f"- **工具数**: {self.tool_schema.get('tool_count', '未测量')}",
                f"- **UTF-8 字节数**: {self.tool_schema.get('utf8_bytes', '未测量')}",
                f"- **SHA-256**: {self.tool_schema.get('sha256', '未测量')}",
                f"- **诊断 Token 数**: {self.tool_schema.get('tokens', '未测量')}",
                f"- **Tokenizer**: {self.tool_schema.get('tokenizer', '未测量')}",
                "",
            ])
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


class ObservedConcurrency:
    """Thread-safe measurement of simultaneous calls at one named boundary."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active = 0
        self._maximum: int | None = None

    def enter(self) -> None:
        with self._lock:
            self._active += 1
            self._maximum = max(self._maximum or 0, self._active)

    def exit(self) -> None:
        with self._lock:
            if self._active <= 0:
                raise RuntimeError("concurrency tracker exit without enter")
            self._active -= 1

    @property
    def maximum(self) -> int | None:
        with self._lock:
            return self._maximum


class ProcessTreeRssSampler:
    """Sample root-plus-recursive-child RSS without platform peak fields."""

    def __init__(
        self,
        process: Any,
        *,
        interval_seconds: float = 0.05,
    ) -> None:
        if interval_seconds <= 0:
            raise ValueError("RSS sample interval must be positive")
        self.process = process
        self.interval_seconds = interval_seconds
        self.peak_rss_mb: float | None = None
        self.current_rss_mb: float | None = None
        self.sample_count = 0
        self.max_processes: int | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def sample_once(self) -> float | None:
        try:
            processes = [self.process, *self.process.children(recursive=True)]
        except Exception:  # noqa: BLE001 - psutil errors vary by platform/version
            return None
        rss = 0
        measured = 0
        for process in processes:
            try:
                value = int(process.memory_info().rss)
            except Exception:  # noqa: BLE001 - disappearing child is expected
                continue
            if value < 0:
                continue
            rss += value
            measured += 1
        if measured == 0:
            return None
        rss_mb = rss / (1024 * 1024)
        self.current_rss_mb = rss_mb
        self.peak_rss_mb = max(self.peak_rss_mb or 0.0, rss_mb)
        self.max_processes = max(self.max_processes or 0, measured)
        self.sample_count += 1
        return rss_mb

    def _run(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            self.sample_once()

    def start(self) -> None:
        if self._thread is not None:
            raise RuntimeError("RSS sampler already started")
        self.sample_once()
        self._thread = threading.Thread(
            target=self._run,
            name="quant-process-tree-rss",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=max(1.0, self.interval_seconds * 4))
        self.sample_once()


def canonical_tool_schema_accounting(
    role_tools: Mapping[str, Sequence[Any]],
    *,
    tokenizer_name: str = "cl100k_base",
) -> dict[str, Any]:
    """Measure canonical bytes/hash and diagnostic tokens for actual ToolCards."""
    projection = []
    for role in sorted(role_tools):
        for tool in sorted(
            role_tools[role],
            key=lambda item: str(getattr(getattr(item, "card", None), "name", "")),
        ):
            card = getattr(tool, "card", None)
            if card is None:
                raise ValueError(f"tool for {role} has no ToolCard")
            input_params = getattr(card, "input_params", {})
            if hasattr(input_params, "model_dump"):
                input_params = input_params.model_dump()
            projection.append({
                "role": role,
                "name": str(getattr(card, "name", "")),
                "description": str(getattr(card, "description", "")),
                "input_params": input_params,
            })
    raw = json.dumps(
        projection,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    token_count = None
    tokenizer = None
    try:
        import tiktoken

        encoding = tiktoken.get_encoding(tokenizer_name)
        token_count = len(encoding.encode(raw.decode("utf-8")))
        tokenizer = f"tiktoken:{tokenizer_name}:diagnostic_not_provider_usage"
    except (ImportError, KeyError, UnicodeError, ValueError):
        pass
    return {
        "schema": "formal_tool_schema_accounting/v1",
        "scope": "formal_quant_rpc_toolcards",
        "projection": "toolcard_name_description_input_params",
        "tools": projection,
        "tool_count": len(projection),
        "utf8_bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "tokens": token_count,
        "tokenizer": tokenizer,
    }
