"""Deterministic progress guard for the formal multi-agent workflow."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


TASK_MANAGEMENT_TOOLS = frozenset({
    "build_team",
    "create_task",
    "update_task",
    "view_task",
})


@dataclass
class ToolProgressGuard:
    """Stop tool churn even when an Agent varies arguments on every call."""

    max_identical_calls: int = 3
    max_management_calls_without_progress: int = 12
    max_all_calls_without_progress: int = 24
    completed_phases: int = 0
    management_calls_without_progress: int = 0
    all_calls_without_progress: int = 0
    last_signature: str | None = None
    identical_count: int = 0
    triggered: bool = False
    detail: str | None = None

    def record_quant_progress(self, completed_phases: int) -> None:
        """Reset no-progress budgets only when a new business phase completes."""
        if completed_phases <= self.completed_phases:
            return
        self.completed_phases = completed_phases
        self.management_calls_without_progress = 0
        self.all_calls_without_progress = 0

    def record_tool_call(self, tool_call: dict[str, Any]) -> str | None:
        """Record one stream tool call and return a failure reason if tripped."""
        if self.triggered:
            return self.detail

        name = str(tool_call.get("name") or "")
        signature = json.dumps(
            {
                "name": name,
                "args": tool_call.get("arguments", tool_call.get("args")),
                "result": tool_call.get("result"),
            },
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )
        if signature == self.last_signature:
            self.identical_count += 1
        else:
            self.last_signature = signature
            self.identical_count = 1

        self.all_calls_without_progress += 1
        if name in TASK_MANAGEMENT_TOOLS:
            self.management_calls_without_progress += 1

        if self.identical_count >= self.max_identical_calls:
            return self._trip(
                f"identical tool call repeated {self.identical_count} times: {name or '?'}"
            )
        if (
            self.management_calls_without_progress
            >= self.max_management_calls_without_progress
        ):
            return self._trip(
                "task-management calls without quant progress reached "
                f"{self.management_calls_without_progress}"
            )
        if self.all_calls_without_progress >= self.max_all_calls_without_progress:
            return self._trip(
                "all tool calls without quant progress reached "
                f"{self.all_calls_without_progress}"
            )
        return None

    def as_dict(self) -> dict[str, Any]:
        return {
            "triggered": self.triggered,
            "detail": self.detail,
            "completed_phases": self.completed_phases,
            "management_calls_without_progress": (
                self.management_calls_without_progress
            ),
            "all_calls_without_progress": self.all_calls_without_progress,
        }

    def _trip(self, detail: str) -> str:
        self.triggered = True
        self.detail = detail
        return detail
