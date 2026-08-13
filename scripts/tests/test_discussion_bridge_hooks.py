from __future__ import annotations

import importlib.util
import io
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[2]
HOOK_PATHS = [
    ROOT / ".codex" / "hooks" / "discussion_bridge_stop.py",
    ROOT / ".claude" / "hooks" / "codex_bridge_stop.py",
]


def _load_hook(path: Path):
    name = f"bridge_hook_{path.parent.parent.name}"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(params=HOOK_PATHS)
def hook(request):
    return _load_hook(request.param)


def _write_handoff(path: Path, route: str, task: str, reply: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"## [{route}] {task}\n\n### 需要回复\n{reply}\n\n---\n",
        encoding="utf-8",
    )


def test_top_handoff_and_reply_detection(hook, tmp_path: Path) -> None:
    discussion = tmp_path / "discussion.md"
    _write_handoff(discussion, "Codex → Claude", "BRIDGE-OPS-2", "请实现。")
    route, task_id, block = hook._top_handoff(discussion)
    assert route == "Codex → Claude"
    assert task_id == "BRIDGE-OPS-2"
    assert hook._requires_reply(block)


def test_no_reply_detection(hook, tmp_path: Path) -> None:
    discussion = tmp_path / "discussion.md"
    _write_handoff(discussion, "Claude → Codex", "BRIDGE-OPS-2", "无需回复。")
    assert not hook._requires_reply(hook._top_handoff(discussion)[2])


def test_outbox_older_than_discussion_is_stale(hook, tmp_path: Path) -> None:
    outbox = tmp_path / "claude_reply.md"
    discussion = tmp_path / "discussion.md"
    outbox.write_text("old", encoding="utf-8")
    discussion.write_text("new instruction", encoding="utf-8")
    os.utime(outbox, ns=(1_000_000_000, 1_000_000_000))
    os.utime(discussion, ns=(2_000_000_000, 2_000_000_000))
    assert not hook._outbox_is_fresh(outbox, discussion)


def test_newer_unchanged_outbox_is_not_fresh(hook, tmp_path: Path) -> None:
    outbox = tmp_path / "claude_reply.md"
    discussion = tmp_path / "discussion.md"
    outbox.write_text("same", encoding="utf-8")
    stale_signature = hook._file_signature(outbox)
    discussion.write_text("instruction", encoding="utf-8")
    os.utime(discussion, ns=(2_000_000_000, 2_000_000_000))
    os.utime(outbox, ns=(3_000_000_000, 3_000_000_000))
    assert not hook._outbox_is_fresh(outbox, discussion, stale_signature)


def test_newer_changed_outbox_is_fresh(hook, tmp_path: Path) -> None:
    outbox = tmp_path / "claude_reply.md"
    discussion = tmp_path / "discussion.md"
    outbox.write_text("old", encoding="utf-8")
    stale_signature = hook._file_signature(outbox)
    discussion.write_text("instruction", encoding="utf-8")
    outbox.write_text("new", encoding="utf-8")
    os.utime(discussion, ns=(2_000_000_000, 2_000_000_000))
    os.utime(outbox, ns=(3_000_000_000, 3_000_000_000))
    assert hook._outbox_is_fresh(outbox, discussion, stale_signature)


def test_delivery_is_claimed_once_across_hook_processes(hook, tmp_path: Path) -> None:
    if not hasattr(hook, "_delivery_token"):
        pytest.skip("delivery receipts belong to the Codex consumer hook")
    discussion = tmp_path / "discussion.md"
    handoff = tmp_path / "claude_reply.md"
    discussion.write_text("instruction", encoding="utf-8")
    handoff.write_text("implemented", encoding="utf-8")
    token = hook._delivery_token("BRIDGE-OPS-4", discussion, handoff)
    assert hook._claim_delivery(tmp_path, token)
    assert not hook._claim_delivery(tmp_path, token)

    handoff.write_text("implemented revision 2", encoding="utf-8")
    new_token = hook._delivery_token("BRIDGE-OPS-4", discussion, handoff)
    assert new_token != token
    assert hook._claim_delivery(tmp_path, new_token)


def test_process_lock_excludes_and_releases(hook, tmp_path: Path) -> None:
    path = tmp_path / "bridge.lock"
    first = hook.ProcessLock(path)
    second = hook.ProcessLock(path)
    assert first.acquire()
    assert not second.acquire()
    first.release()
    assert second.acquire()
    second.release()


def test_owner_liveness_uses_launcher_pid(hook, monkeypatch) -> None:
    monkeypatch.setenv(hook.OWNER_PID_ENV, "4321")
    calls = []
    monkeypatch.setattr(hook, "_pid_alive", lambda pid: calls.append(pid) or True)
    assert hook._owner_alive()
    assert calls == [4321]
    monkeypatch.setattr(hook, "_pid_alive", lambda _pid: False)
    assert not hook._owner_alive()


def test_lock_takeover_retries_until_available(hook, tmp_path: Path, monkeypatch) -> None:
    attempts = iter([False, False, True])
    lock = SimpleNamespace(acquire=lambda: next(attempts))
    clock = iter([0.0, 0.0, 1.0, 2.0])
    monkeypatch.setattr(hook, "LOCK_WAIT_SECONDS", 10)
    monkeypatch.setattr(hook, "POLL_SECONDS", 0)
    monkeypatch.setattr(hook, "_owner_alive", lambda: True)
    monkeypatch.setattr(hook.time, "time", lambda: next(clock))
    monkeypatch.setattr(hook.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(hook, "_log", lambda *_args, **_kwargs: None)
    assert hook._acquire_with_takeover(lock, tmp_path)


def test_dead_owner_does_not_wait_for_lock(hook, tmp_path: Path, monkeypatch) -> None:
    lock = SimpleNamespace(acquire=lambda: (_ for _ in ()).throw(AssertionError()))
    events = []
    monkeypatch.setattr(hook, "_owner_alive", lambda: False)
    monkeypatch.setattr(hook, "_log", lambda _root, event, **_details: events.append(event))
    assert not hook._acquire_with_takeover(lock, tmp_path)
    assert events == ["owner_exited_before_lock"]


def test_standby_budget_leaves_outer_timeout_margin(hook) -> None:
    assert hook.WAIT_SECONDS <= 18_000
    assert hook.LOCK_WAIT_SECONDS <= 15


def test_hook_commands_are_repo_rooted() -> None:
    claude_settings = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    claude_command = claude_settings["hooks"]["Stop"][0]["hooks"][0]["command"]
    codex_settings = json.loads((ROOT / ".codex" / "hooks.json").read_text(encoding="utf-8"))
    codex_command = codex_settings["hooks"]["Stop"][0]["hooks"][0]["commandWindows"]
    assert 'cd "$CLAUDE_PROJECT_DIR"' in claude_command
    assert "git rev-parse --show-toplevel" in codex_command


def test_launchers_bind_hook_owner_to_visible_powershell() -> None:
    for name in ("start-claude-cli.ps1", "start-codex-cli.ps1"):
        text = (ROOT / "output" / "bridge_runtime" / name).read_text(encoding="utf-8")
        assert '$env:TRACK2_BRIDGE_OWNER_PID = "$PID"' in text


def test_launchers_remove_stale_bridge_sessions_before_start() -> None:
    claude = (ROOT / "output" / "bridge_runtime" / "start-claude-cli.ps1").read_text(
        encoding="utf-8"
    )
    codex = (ROOT / "output" / "bridge_runtime" / "start-codex-cli.ps1").read_text(
        encoding="utf-8"
    )
    assert 'session.name -eq "track2-claude-bridge"' in claude
    assert "Stop-Process -Id $existing.Id -Force" in claude
    assert "unique persistent Codex planning and acceptance collaborator" in codex
    assert "Stop-Process -Id $_.ProcessId -Force" in codex


def test_no_reply_still_reenters_standby(hook, tmp_path: Path, monkeypatch, capsys) -> None:
    (tmp_path / ".git").mkdir()
    discussion = tmp_path / ".claude" / "discussion.md"
    _write_handoff(discussion, "Claude → Codex", "BRIDGE-OPS-2", "无需回复。")
    monkeypatch.setattr(hook, "WAIT_SECONDS", 0)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"hook_event_name": "Stop", "cwd": str(tmp_path)})))
    assert hook.main() == 0
    response = json.loads(capsys.readouterr().out)
    assert response["decision"] == "block"
    assert "standby" in response["reason"]


def _hook_agent(hook) -> str:
    return "codex" if "codex" in getattr(hook, "__name__", "") else "claude"


def test_handoff_without_reply_section_is_actionable(hook, tmp_path: Path) -> None:
    discussion = tmp_path / "discussion.md"
    discussion.write_text(
        "## [Codex → Claude] BRIDGE-OPS-5\n\n没有回复小节的指令。\n\n---\n",
        encoding="utf-8",
    )
    assert hook._requires_reply(hook._top_handoff(discussion)[2])


def test_explicit_no_reply_heading_is_passive(hook, tmp_path: Path) -> None:
    discussion = tmp_path / "discussion.md"
    discussion.write_text(
        "## [Codex → Claude] BRIDGE-OPS-5\n\n### 无需回复\n仅通知。\n\n---\n",
        encoding="utf-8",
    )
    assert not hook._requires_reply(hook._top_handoff(discussion)[2])


def test_explicit_no_reply_heading_suppresses_without_reply_section(hook, tmp_path: Path) -> None:
    discussion = tmp_path / "discussion.md"
    discussion.write_text(
        "## [Codex → Claude] BRIDGE-OPS-5\n\n### 无需回复\n无。\n\n---\n",
        encoding="utf-8",
    )
    assert not hook._requires_reply(hook._top_handoff(discussion)[2])


def test_pending_helpers_roundtrip(hook, tmp_path: Path) -> None:
    path = hook._pending_path(tmp_path, "claude")
    record = {
        "input_token": "a" * 64,
        "required_output": str(tmp_path / "out.md"),
        "pre_hash": "b" * 64,
        "created_at": "2026-08-13T00:00:00+08:00",
    }
    hook._write_pending(path, record)
    assert path.exists()
    assert hook._read_pending(path) == record
    hook._clear_pending(path)
    assert not path.exists()
    assert hook._read_pending(path) is None


def test_pending_blocked_true_when_output_unchanged(hook, tmp_path: Path) -> None:
    outbox = tmp_path / "claude_reply.md"
    outbox.write_text("unwritten", encoding="utf-8")
    path = hook._pending_path(tmp_path, "claude")
    hook._write_pending(
        path,
        {
            "input_token": "a" * 64,
            "required_output": str(outbox),
            "pre_hash": hook._file_signature(outbox),
            "created_at": "2026-08-13T00:00:00+08:00",
        },
    )
    assert hook._pending_blocked(tmp_path, "claude", outbox)
    assert path.exists()


def test_pending_cleanup_clears_when_output_changed(hook, tmp_path: Path) -> None:
    outbox = tmp_path / "claude_reply.md"
    outbox.write_text("old", encoding="utf-8")
    path = hook._pending_path(tmp_path, "claude")
    hook._write_pending(
        path,
        {
            "input_token": "a" * 64,
            "required_output": str(outbox),
            "pre_hash": hook._file_signature(outbox),
            "created_at": "2026-08-13T00:00:00+08:00",
        },
    )
    outbox.write_text("implemented", encoding="utf-8")
    hook._pending_cleanup(tmp_path, "claude")
    assert not path.exists()
    assert not hook._pending_blocked(tmp_path, "claude", outbox)


def test_pending_cleanup_keeps_record_when_output_unchanged(hook, tmp_path: Path) -> None:
    outbox = tmp_path / "claude_reply.md"
    outbox.write_text("unwritten", encoding="utf-8")
    path = hook._pending_path(tmp_path, "claude")
    hook._write_pending(
        path,
        {
            "input_token": "a" * 64,
            "required_output": str(outbox),
            "pre_hash": hook._file_signature(outbox),
            "created_at": "2026-08-13T00:00:00+08:00",
        },
    )
    hook._pending_cleanup(tmp_path, "claude")
    assert path.exists()
    assert hook._pending_blocked(tmp_path, "claude", outbox)


def test_actionable_wake_persists_pending_record(hook, tmp_path: Path, monkeypatch, capsys) -> None:
    agent = _hook_agent(hook)
    (tmp_path / ".git").mkdir()
    discussion = tmp_path / ".claude" / "discussion.md"
    discussion.parent.mkdir(parents=True, exist_ok=True)
    if agent == "claude":
        route, task = "Codex → Claude", "BRIDGE-OPS-5"
        required = tmp_path / "output" / "agent_handoffs" / task / "claude_reply.md"
        required.parent.mkdir(parents=True, exist_ok=True)
        required.write_text("old", encoding="utf-8")
        os.utime(required, ns=(1_000_000_000, 1_000_000_000))
        discussion.write_text(f"## [{route}] {task}\n\n无回复小节指令。\n\n---\n", encoding="utf-8")
        os.utime(discussion, ns=(2_000_000_000, 2_000_000_000))
    else:
        route, task = "Claude → Codex", "BRIDGE-OPS-5"
        required = discussion
        discussion.write_text(f"## [{route}] {task}\n\n无回复小节指令。\n\n---\n", encoding="utf-8")
    monkeypatch.setattr(hook, "WAIT_SECONDS", 0)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"hook_event_name": "Stop", "cwd": str(tmp_path)})))
    assert hook.main() == 0
    response = json.loads(capsys.readouterr().out)
    assert response["decision"] == "block"
    assert response["reason"]
    record = hook._read_pending(hook._pending_path(tmp_path, agent))
    assert record is not None
    assert record["required_output"] == str(required)
    assert record["pre_hash"] == hook._file_signature(required)


def test_pending_record_blocks_unchanged_output(hook, tmp_path: Path, monkeypatch, capsys) -> None:
    agent = _hook_agent(hook)
    (tmp_path / ".git").mkdir()
    discussion = tmp_path / ".claude" / "discussion.md"
    discussion.parent.mkdir(parents=True, exist_ok=True)
    if agent == "claude":
        route, task = "Codex → Claude", "BRIDGE-OPS-5"
        required = tmp_path / "output" / "agent_handoffs" / task / "claude_reply.md"
        required.parent.mkdir(parents=True, exist_ok=True)
        required.write_text("unwritten", encoding="utf-8")
        os.utime(required, ns=(1_000_000_000, 1_000_000_000))
        discussion.write_text(f"## [{route}] {task}\n\n指令。\n\n---\n", encoding="utf-8")
        os.utime(discussion, ns=(2_000_000_000, 2_000_000_000))
    else:
        route, task = "Claude → Codex", "BRIDGE-OPS-5"
        required = discussion
        discussion.write_text(f"## [{route}] {task}\n\n指令。\n\n---\n", encoding="utf-8")
    path = hook._pending_path(tmp_path, agent)
    hook._write_pending(
        path,
        {
            "input_token": hook._file_signature(discussion),
            "required_output": str(required),
            "pre_hash": hook._file_signature(required),
            "created_at": "2026-08-13T00:00:00+08:00",
        },
    )
    monkeypatch.setattr(hook, "WAIT_SECONDS", 0)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"hook_event_name": "Stop", "cwd": str(tmp_path)})))
    assert hook.main() == 0
    response = json.loads(capsys.readouterr().out)
    assert response["decision"] == "block"
    assert "pending" in response["reason"]
    assert path.exists()


def test_pending_cleared_after_output_delivered(tmp_path: Path, monkeypatch, capsys) -> None:
    hook = _load_hook(HOOK_PATHS[1])
    (tmp_path / ".git").mkdir()
    discussion = tmp_path / ".claude" / "discussion.md"
    discussion.parent.mkdir(parents=True, exist_ok=True)
    discussion.write_text("## [Codex → Claude] BRIDGE-OPS-5\n\n指令。\n\n---\n", encoding="utf-8")
    outbox = tmp_path / "output" / "agent_handoffs" / "BRIDGE-OPS-5" / "claude_reply.md"
    outbox.parent.mkdir(parents=True, exist_ok=True)
    outbox.write_text("old", encoding="utf-8")
    path = hook._pending_path(tmp_path, "claude")
    hook._write_pending(
        path,
        {
            "input_token": hook._file_signature(discussion),
            "required_output": str(outbox),
            "pre_hash": hook._file_signature(outbox),
            "created_at": "2026-08-13T00:00:00+08:00",
        },
    )
    outbox.write_text("implemented now", encoding="utf-8")
    os.utime(outbox, ns=(3_000_000_000, 3_000_000_000))
    os.utime(discussion, ns=(2_000_000_000, 2_000_000_000))
    monkeypatch.setattr(hook, "WAIT_SECONDS", 0)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"hook_event_name": "Stop", "cwd": str(tmp_path)})))
    assert hook.main() == 0
    assert not path.exists()
    response = json.loads(capsys.readouterr().out)
    assert response["decision"] == "block"
    assert "standby" in response["reason"]


def test_codex_outbox_ready_wake_persists_pending(tmp_path: Path, monkeypatch, capsys) -> None:
    hook = _load_hook(HOOK_PATHS[0])
    (tmp_path / ".git").mkdir()
    discussion = tmp_path / ".claude" / "discussion.md"
    discussion.parent.mkdir(parents=True, exist_ok=True)
    discussion.write_text("## [Codex → Claude] BRIDGE-OPS-5\n\n指令。\n\n---\n", encoding="utf-8")
    outbox = tmp_path / "output" / "agent_handoffs" / "BRIDGE-OPS-5" / "claude_reply.md"
    outbox.parent.mkdir(parents=True, exist_ok=True)
    outbox.write_text("implemented", encoding="utf-8")
    os.utime(discussion, ns=(1_000_000_000, 1_000_000_000))
    os.utime(outbox, ns=(2_000_000_000, 2_000_000_000))
    monkeypatch.setattr(hook, "WAIT_SECONDS", 0)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"hook_event_name": "Stop", "cwd": str(tmp_path)})))
    assert hook.main() == 0
    response = json.loads(capsys.readouterr().out)
    assert response["decision"] == "block"
    record = hook._read_pending(hook._pending_path(tmp_path, "codex"))
    assert record is not None
    assert record["required_output"] == str(discussion)
    assert record["pre_hash"] == hook._file_signature(discussion)


def test_codex_outbox_ready_blocks_unchanged_discussion(tmp_path: Path, monkeypatch, capsys) -> None:
    hook = _load_hook(HOOK_PATHS[0])
    (tmp_path / ".git").mkdir()
    discussion = tmp_path / ".claude" / "discussion.md"
    discussion.parent.mkdir(parents=True, exist_ok=True)
    discussion.write_text("## [Codex → Claude] BRIDGE-OPS-5\n\n指令。\n\n---\n", encoding="utf-8")
    outbox = tmp_path / "output" / "agent_handoffs" / "BRIDGE-OPS-5" / "claude_reply.md"
    outbox.parent.mkdir(parents=True, exist_ok=True)
    outbox.write_text("implemented", encoding="utf-8")
    os.utime(discussion, ns=(1_000_000_000, 1_000_000_000))
    os.utime(outbox, ns=(2_000_000_000, 2_000_000_000))
    path = hook._pending_path(tmp_path, "codex")
    hook._write_pending(
        path,
        {
            "input_token": hook._file_signature(outbox),
            "required_output": str(discussion),
            "pre_hash": hook._file_signature(discussion),
            "created_at": "2026-08-13T00:00:00+08:00",
        },
    )
    monkeypatch.setattr(hook, "WAIT_SECONDS", 0)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"hook_event_name": "Stop", "cwd": str(tmp_path)})))
    assert hook.main() == 0
    response = json.loads(capsys.readouterr().out)
    assert response["decision"] == "block"
    assert "pending" in response["reason"]
    assert path.exists()
