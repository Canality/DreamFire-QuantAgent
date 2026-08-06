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


def _failed_call(name: str, index: int) -> dict:
    return {
        "name": name,
        "arguments": {"revision": index},
        "result": {"success": False, "error": f"failure-{index}"},
    }


def test_same_tool_failure_trips_on_third_with_varying_payloads() -> None:
    guard = ToolProgressGuard()

    assert guard.record_tool_call(_failed_call("quant.fetch", 1)) is None
    assert guard.record_tool_call(_failed_call("quant.fetch", 2)) is None
    reason = guard.record_tool_call(_failed_call("quant.fetch", 3))

    assert reason == (
        "CONSECUTIVE_TOOL_FAILURE_LIMIT: tool=quant.fetch "
        "count=3 last_error=failure-3"
    )
    assert guard.as_dict()["failure_reason_code"] == (
        "CONSECUTIVE_TOOL_FAILURE_LIMIT"
    )
    assert guard.as_dict()["consecutive_failure_count"] == 3


def test_success_or_different_tool_resets_consecutive_failure_sequence() -> None:
    guard = ToolProgressGuard(max_identical_calls=10)
    assert guard.record_tool_call(_failed_call("quant.fetch", 1)) is None
    assert guard.record_tool_call(_failed_call("quant.fetch", 2)) is None
    assert guard.record_tool_call(_call("quant.fetch", 3)) is None
    assert guard.as_dict()["consecutive_failure_count"] == 0

    assert guard.record_tool_call(_failed_call("quant.fetch", 4)) is None
    assert guard.record_tool_call(_failed_call("quant.other", 5)) is None
    assert guard.as_dict()["last_failed_tool"] == "quant.other"
    assert guard.as_dict()["consecutive_failure_count"] == 1


def test_json_failure_status_is_recognized_but_free_text_is_not_guessed() -> None:
    guard = ToolProgressGuard(max_identical_calls=10)
    for index in range(2):
        assert guard.record_tool_call({
            "name": "send_message",
            "arguments": {"revision": index},
            "result": '{"status":"FAILED","message":"unavailable"}',
        }) is None
    assert guard.as_dict()["consecutive_failure_count"] == 2

    assert guard.record_tool_call({
        "name": "send_message",
        "arguments": {"revision": 3},
        "result": "not failed: this is unstructured presentation text",
    }) is None
    assert guard.as_dict()["consecutive_failure_count"] == 0


def test_triggered_failure_diagnostic_is_immutable() -> None:
    guard = ToolProgressGuard()
    for index in range(3):
        reason = guard.record_tool_call(_failed_call("quant.fetch", index))
    frozen = guard.as_dict().copy()

    assert guard.record_tool_call(_call("quant.other", 9)) == reason
    guard.record_quant_progress(8)
    assert guard.as_dict() == frozen


def test_tool_name_whitespace_cannot_split_failure_identity() -> None:
    guard = ToolProgressGuard()

    assert guard.record_tool_call(_failed_call(" quant.fetch", 1)) is None
    assert guard.record_tool_call(_failed_call("quant.fetch ", 2)) is None
    reason = guard.record_tool_call(_failed_call(" quant.fetch ", 3))

    assert reason is not None
    assert "tool=quant.fetch count=3" in reason
