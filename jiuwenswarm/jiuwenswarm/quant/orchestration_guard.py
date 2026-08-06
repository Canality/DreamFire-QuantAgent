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
FAILED_STATUSES = frozenset({"ERROR", "FAILED", "FAILURE"})


def _failure_outcome(tool_call: dict[str, Any]) -> tuple[bool | None, str | None]:
    """Recognize explicit failure fields without guessing from free text."""
    error = tool_call.get("error")
    if error not in (None, ""):
        return True, str(error)[:200]
    if tool_call.get("failed") is True:
        return True, str(tool_call.get("result") or "explicit failed=true")[:200]

    outcome_fields = {"result", "success", "status", "is_error", "failed", "error"}
    if not outcome_fields.intersection(tool_call):
        return None, None
    if tool_call.get("success") is False or tool_call.get("is_error") is True:
        detail = tool_call.get("error") or tool_call.get("result") or "success=false"
        return True, str(detail)[:200]
    status = str(tool_call.get("status") or "").strip().upper()
    if status in FAILED_STATUSES:
        detail = tool_call.get("error") or tool_call.get("result") or status
        return True, str(detail)[:200]

    result = tool_call.get("result")
    if isinstance(result, str):
        try:
            decoded = json.loads(result)
        except (json.JSONDecodeError, TypeError):
            return False, None
        result = decoded
    if not isinstance(result, dict):
        return False, None

    result_error = result.get("error")
    status = str(result.get("status") or "").strip().upper()
    failed = result.get("success") is False or status in FAILED_STATUSES
    if not failed and result_error in (None, ""):
        return False, None
    detail = result_error or result.get("message") or status or "success=false"
    return True, str(detail)[:200]


@dataclass
class ToolProgressGuard:
    """Stop tool churn even when an Agent varies arguments on every call."""

    max_identical_calls: int = 3
    max_consecutive_failures: int = 3
    max_management_calls_without_progress: int = 12
    max_all_calls_without_progress: int = 24
    completed_phases: int = 0
    management_calls_without_progress: int = 0
    all_calls_without_progress: int = 0
    last_signature: str | None = None
    identical_count: int = 0
    last_failed_tool: str | None = None
    consecutive_failure_count: int = 0
    failure_reason_code: str | None = None
    last_failure_detail: str | None = None
    triggered: bool = False
    detail: str | None = None

    def record_quant_progress(self, completed_phases: int) -> None:
        """Reset no-progress budgets only when a new business phase completes."""
        if self.triggered:
            return
        if completed_phases <= self.completed_phases:
            return
        self.completed_phases = completed_phases
        self.management_calls_without_progress = 0
        self.all_calls_without_progress = 0
        self.last_failed_tool = None
        self.consecutive_failure_count = 0
        self.last_failure_detail = None

    def record_tool_call(self, tool_call: dict[str, Any]) -> str | None:
        """Record one stream tool call and return a failure reason if tripped."""
        if self.triggered:
            return self.detail

        name = str(tool_call.get("name") or "").strip()
        failed, failure_detail = _failure_outcome(tool_call)
        if failed is True and name:
            if name == self.last_failed_tool:
                self.consecutive_failure_count += 1
            else:
                self.last_failed_tool = name
                self.consecutive_failure_count = 1
            self.last_failure_detail = failure_detail
        elif failed is False:
            self.last_failed_tool = None
            self.consecutive_failure_count = 0
            self.last_failure_detail = None

        # Runtime tool_result events are terminal outcomes for the failure
        # sequence, not additional calls for identical/churn budgets.
        if tool_call.get("event_type") == "tool_result":
            if self.consecutive_failure_count >= self.max_consecutive_failures:
                return self._trip_consecutive_failure(name)
            return None

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

        if self.consecutive_failure_count >= self.max_consecutive_failures:
            return self._trip_consecutive_failure(name)
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
            "last_failed_tool": self.last_failed_tool,
            "consecutive_failure_count": self.consecutive_failure_count,
            "failure_reason_code": self.failure_reason_code,
            "last_failure_detail": self.last_failure_detail,
        }

    def _trip(self, detail: str) -> str:
        self.triggered = True
        self.detail = detail
        return detail

    def _trip_consecutive_failure(self, name: str) -> str:
        self.failure_reason_code = "CONSECUTIVE_TOOL_FAILURE_LIMIT"
        detail = (
            f"{self.failure_reason_code}: tool={name} "
            f"count={self.consecutive_failure_count}"
        )
        if self.last_failure_detail:
            detail += f" last_error={self.last_failure_detail}"
        return self._trip(detail)
