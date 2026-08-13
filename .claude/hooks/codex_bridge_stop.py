from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
from typing import BinaryIO


WAIT_SECONDS = 18000
POLL_SECONDS = 1
LOCK_WAIT_SECONDS = 15
OWNER_PID_ENV = "TRACK2_BRIDGE_OWNER_PID"
HEADER_PATTERN = re.compile(
    r"^## \[(Codex → Claude|Claude → Codex(?: / bridge relay)?)\](.*)$",
    re.MULTILINE,
)
TASK_ID_PATTERN = re.compile(r"\b[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+\b")
REPLY_SECTION_PATTERN = re.compile(
    r"^### 需要(?:回复|回答)\s*$\n(?P<body>.*?)(?=^### |^---\s*$|\Z)",
    re.MULTILINE | re.DOTALL,
)
NO_REPLY_PATTERN = re.compile(
    r"^(?:无|none|no reply|不需要回复|无需回复)(?:[。\s]|$)", re.IGNORECASE
)
NO_REPLY_HEADING_PATTERN = re.compile(
    r"^### (?:无需回复|不需要回复|no reply|none)\s*$", re.MULTILINE | re.IGNORECASE
)


class ProcessLock:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.handle: BinaryIO | None = None

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+b")
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, IOError):
            handle.close()
            return False
        self.handle = handle
        return True

    def release(self) -> None:
        if self.handle is None:
            return
        try:
            self.handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        finally:
            self.handle.close()
            self.handle = None


def _repo_root(cwd: str) -> Path | None:
    candidate = Path(cwd).resolve()
    if candidate.is_file():
        candidate = candidate.parent
    for directory in (candidate, *candidate.parents):
        if (directory / ".git").exists():
            return directory
    return None


def _top_handoff(path: Path) -> tuple[str, str, str] | None:
    try:
        discussion = path.read_text(encoding="utf-8").lstrip("\ufeff")
    except OSError:
        return None
    match = HEADER_PATTERN.search(discussion)
    if match is None:
        return None
    next_match = HEADER_PATTERN.search(discussion, match.end())
    end = next_match.start() if next_match is not None else len(discussion)
    block = discussion[match.start() : end]
    task_match = TASK_ID_PATTERN.search(match.group(2))
    return match.group(1), task_match.group(0) if task_match else "", block


def _requires_reply(block: str) -> bool:
    match = REPLY_SECTION_PATTERN.search(block)
    if match is None:
        return NO_REPLY_HEADING_PATTERN.search(block) is None
    lines = [
        re.sub(r"^[\s>*-]+", "", line).strip()
        for line in match.group("body").splitlines()
        if line.strip()
    ]
    if not lines:
        return True
    return any(NO_REPLY_PATTERN.match(line) is None for line in lines)


def _file_signature(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""


def _pending_path(root: Path, agent: str) -> Path:
    return root / "output" / "agent_handoffs" / ".bridge" / f"{agent}-pending.json"


def _read_pending(path: Path) -> dict | None:
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    return record if isinstance(record, dict) else None


def _write_pending(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(record, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, path)


def _clear_pending(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        pass


def _pending_cleanup(root: Path, agent: str) -> None:
    """Clear the durable pending record once its required output changed."""
    path = _pending_path(root, agent)
    record = _read_pending(path)
    if record is None:
        return
    required = Path(record.get("required_output") or "")
    if not str(required) or _file_signature(required) != record.get("pre_hash"):
        _clear_pending(path)


def _pending_blocked(root: Path, agent: str, required_output: Path) -> bool:
    """True when a durable pending record is still open (required output unchanged)."""
    path = _pending_path(root, agent)
    record = _read_pending(path)
    if record is None:
        return False
    return (
        record.get("required_output") == str(required_output)
        and _file_signature(required_output) == record.get("pre_hash")
    )


def _pending_actionable(
    root: Path, agent: str, input_path: Path, required_output: Path
) -> None:
    _write_pending(
        _pending_path(root, agent),
        {
            "input_token": _file_signature(input_path),
            "required_output": str(required_output),
            "pre_hash": _file_signature(required_output),
            "created_at": dt.datetime.now().isoformat(),
        },
    )


def _stale_outbox_signature(outbox: Path, discussion: Path) -> str:
    try:
        if outbox.stat().st_mtime_ns <= discussion.stat().st_mtime_ns:
            return _file_signature(outbox)
    except OSError:
        pass
    return ""


def _outbox_is_fresh(outbox: Path, discussion: Path, stale_signature: str = "") -> bool:
    try:
        if outbox.stat().st_mtime_ns <= discussion.stat().st_mtime_ns:
            return False
    except OSError:
        return False
    signature = _file_signature(outbox)
    return bool(signature) and (not stale_signature or signature != stale_signature)


def _continue(reason: str) -> None:
    print(json.dumps({"decision": "block", "reason": reason}, separators=(",", ":")))


def _owner_alive() -> bool:
    raw = os.environ.get(OWNER_PID_ENV, "").strip()
    if not raw:
        return True
    try:
        owner_pid = int(raw)
        if owner_pid <= 0:
            return False
        return _pid_alive(owner_pid)
    except ValueError:
        return False


def _pid_alive(pid: int) -> bool:
    if os.name != "nt":
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    import ctypes
    from ctypes import wintypes

    process_query_limited_information = 0x1000
    still_active = 259
    kernel32 = ctypes.windll.kernel32
    kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
    kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL
    handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
    if not handle:
        return False
    try:
        exit_code = wintypes.DWORD()
        return bool(kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))) and (
            exit_code.value == still_active
        )
    finally:
        kernel32.CloseHandle(handle)


def _acquire_with_takeover(lock: ProcessLock, root: Path) -> bool:
    deadline = time.time() + LOCK_WAIT_SECONDS
    while time.time() < deadline:
        if not _owner_alive():
            _log(root, "owner_exited_before_lock")
            return False
        if lock.acquire():
            return True
        time.sleep(POLL_SECONDS)
    _log(root, "lock_busy_timeout")
    return False


def _log(root: Path, event: str, **details: object) -> None:
    path = root / "output" / "agent_handoffs" / ".bridge" / "hooks.ndjson"
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {"time": dt.datetime.now().isoformat(), "agent": "claude", "event": event, **details}
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")


def _instruction_reason(task_id: str) -> str:
    label = task_id or "the current task"
    return (
        f"Codex has a bounded instruction for {label}. Execute only that phase under "
        "project governance, write the local outbox, and stop."
    )


def _pending_block_reason(task_id: str) -> str:
    label = task_id or "the current task"
    return (
        f"An actionable wake for {label} is pending but the required durable output is "
        "unchanged. Execute that bounded phase, write the output, and stop."
    )


def main() -> int:
    fallback_root = _repo_root(str(Path.cwd()))
    try:
        raw_payload = sys.stdin.read()
        payload = json.loads(raw_payload.lstrip("\ufeff"))
    except (json.JSONDecodeError, OSError) as exc:
        if fallback_root is not None:
            _log(fallback_root, "invalid_payload", error=type(exc).__name__)
        return 0
    root = _repo_root(
        str(os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or Path.cwd())
    ) or fallback_root
    if root is None or payload.get("hook_event_name") != "Stop":
        return 0

    lock = ProcessLock(root / "output" / "agent_handoffs" / ".bridge" / "claude-stop.lock")
    if not _acquire_with_takeover(lock, root):
        return 0
    try:
        discussion = root / ".claude" / "discussion.md"
        current = _top_handoff(discussion)
        discussion_signature = _file_signature(discussion)
        _log(
            root,
            "standby_entered",
            route=current[0] if current else "",
            task_id=current[1] if current else "",
        )
        _pending_cleanup(root, "claude")

        if current and current[0] == "Codex → Claude" and _requires_reply(current[2]):
            task_id = current[1]
            outbox = root / "output" / "agent_handoffs" / task_id / "claude_reply.md"
            if _pending_blocked(root, "claude", outbox):
                _log(root, "blocked_pending_unwritten", task_id=task_id)
                _continue(_pending_block_reason(task_id))
                return 0
            stale_signature = _stale_outbox_signature(outbox, discussion)
            if not _outbox_is_fresh(outbox, discussion, stale_signature):
                _pending_actionable(root, "claude", discussion, outbox)
                _log(root, "continue_instruction", task_id=task_id)
                _continue(_instruction_reason(task_id))
                return 0

        # Standby is intentionally lock-free so a newer Stop hook can observe
        # and consume a fresh handoff without waiting behind this long poll.
        lock.release()
        deadline = time.time() + WAIT_SECONDS
        while time.time() < deadline:
            if not _owner_alive():
                _log(root, "owner_exited", task_id=current[1] if current else "")
                return 0
            new_signature = _file_signature(discussion)
            if new_signature != discussion_signature:
                discussion_signature = new_signature
                current = _top_handoff(discussion)
                if current and current[0] == "Codex → Claude" and _requires_reply(current[2]):
                    task_id = current[1]
                    outbox = root / "output" / "agent_handoffs" / task_id / "claude_reply.md"
                    if _pending_blocked(root, "claude", outbox):
                        if not _acquire_with_takeover(lock, root):
                            time.sleep(POLL_SECONDS)
                            continue
                        _log(root, "blocked_pending_unwritten", task_id=task_id)
                        _continue(_pending_block_reason(task_id))
                        return 0
                    stale_signature = _stale_outbox_signature(outbox, discussion)
                    if not _outbox_is_fresh(outbox, discussion, stale_signature):
                        if not _acquire_with_takeover(lock, root):
                            time.sleep(POLL_SECONDS)
                            continue
                        _pending_actionable(root, "claude", discussion, outbox)
                        _log(root, "continue_new_instruction", task_id=task_id)
                        _continue(_instruction_reason(task_id))
                        return 0
            time.sleep(POLL_SECONDS)

        _log(root, "standby_timeout", task_id=current[1] if current else "")
        _continue(
            "The bounded bridge standby window expired without a new Codex instruction. "
            "Stop again immediately so the Stop hook re-enters local-file standby."
        )
        return 0
    finally:
        lock.release()


if __name__ == "__main__":
    raise SystemExit(main())
