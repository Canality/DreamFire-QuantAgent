"""Focused regressions for the task-contract scope checker."""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[4]
SCRIPT = PROJECT_ROOT / "scripts" / "agent_task.py"
SPEC = importlib.util.spec_from_file_location("agent_task_cli_test", SCRIPT)
assert SPEC and SPEC.loader
AGENT_TASK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AGENT_TASK)

TASK_ID = "TEST-SCOPE"
LOCAL_FILE = "local-only.txt"


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )


def _frozen_repo(tmp_path: Path) -> tuple[Path, dict[str, str | None]]:
    _git(tmp_path, "init", "--quiet")
    task = tmp_path / "coordination" / "active" / f"{TASK_ID}.md"
    task.parent.mkdir(parents=True)
    task.write_text("task contract\n", encoding="utf-8")
    (tmp_path / ".gitignore").write_text("output/\n", encoding="utf-8")
    (tmp_path / LOCAL_FILE).write_text("original\n", encoding="utf-8")
    _git(tmp_path, "add", ".gitignore", f"coordination/active/{TASK_ID}.md")

    before = AGENT_TASK.current_hashes(tmp_path)
    assert LOCAL_FILE in before
    baseline = tmp_path / "output" / "agent_handoffs" / TASK_ID / "baseline.json"
    baseline.parent.mkdir(parents=True)
    baseline.write_text(
        json.dumps(
            {
                "task_id": TASK_ID,
                "allowed_files": [".gitignore"],
                "hashes": before,
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / ".gitignore").write_text("output/\nlocal-only.txt\n", encoding="utf-8")
    return tmp_path, before


@pytest.mark.parametrize(
    ("mutation", "local_changed"),
    [("unchanged", False), ("modified", True), ("deleted", True)],
)
def test_scope_check_rehashes_baseline_file_after_it_becomes_ignored(
    tmp_path: Path,
    mutation: str,
    local_changed: bool,
) -> None:
    root, _ = _frozen_repo(tmp_path)
    local_file = root / LOCAL_FILE
    if mutation == "modified":
        local_file.write_text("modified\n", encoding="utf-8")
    elif mutation == "deleted":
        local_file.unlink()

    changed, violations = AGENT_TASK.changed_since_baseline(root, TASK_ID)

    assert (LOCAL_FILE in changed) is local_changed
    assert (LOCAL_FILE in violations) is local_changed
    assert ".gitignore" in changed
    assert ".gitignore" not in violations


def test_current_hashes_rejects_baseline_path_outside_repository(tmp_path: Path) -> None:
    _git(tmp_path, "init", "--quiet")

    with pytest.raises(ValueError, match="path escapes repository"):
        AGENT_TASK.current_hashes(tmp_path, baseline_paths=["../outside.txt"])
