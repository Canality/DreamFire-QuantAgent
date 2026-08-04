"""Regression tests for formal-path tool-churn protection."""

from jiuwenswarm.quant.orchestration_guard import ToolProgressGuard


def _call(name: str, index: int) -> dict:
    return {"name": name, "arguments": {"revision": index}, "result": "ok"}


def test_varying_update_task_calls_trip_management_budget() -> None:
    guard = ToolProgressGuard(max_management_calls_without_progress=4)

    reasons = [guard.record_tool_call(_call("update_task", i)) for i in range(4)]

    assert reasons[:3] == [None, None, None]
    assert reasons[3] == "task-management calls without quant progress reached 4"
    assert guard.triggered is True


def test_quant_progress_resets_no_progress_budgets() -> None:
    guard = ToolProgressGuard(max_management_calls_without_progress=3)
    assert guard.record_tool_call(_call("update_task", 1)) is None
    assert guard.record_tool_call(_call("view_task", 2)) is None

    guard.record_quant_progress(1)

    assert guard.management_calls_without_progress == 0
    assert guard.all_calls_without_progress == 0
    assert guard.record_tool_call(_call("update_task", 3)) is None


def test_identical_tool_guard_remains_active() -> None:
    guard = ToolProgressGuard(max_identical_calls=3)
    call = _call("some_tool", 1)

    assert guard.record_tool_call(call) is None
    assert guard.record_tool_call(call) is None
    assert guard.record_tool_call(call) == (
        "identical tool call repeated 3 times: some_tool"
    )


def test_other_varying_tools_trip_global_budget() -> None:
    guard = ToolProgressGuard(max_all_calls_without_progress=3)

    assert guard.record_tool_call(_call("search", 1)) is None
    assert guard.record_tool_call(_call("search", 2)) is None
    assert guard.record_tool_call(_call("search", 3)) == (
        "all tool calls without quant progress reached 3"
    )
