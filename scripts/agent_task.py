#!/usr/bin/env python3
"""Deterministic task contracts and handoffs for the Codex/Claude workflow."""

from __future__ import annotations

import argparse
import difflib
import fnmatch
import hashlib
import json
import re
import shutil
import subprocess
import sys
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TASK_ID_RE = re.compile(r"^[A-Z0-9][A-Z0-9._-]{2,63}$")
STATES = {
    "DRAFT",
    "LOCATED",
    "READY",
    "IMPLEMENTED",
    "REVIEWED",
    "VERIFIED",
    "CLOSED",
    "BLOCKED",
}
RISKS = {"UNKNOWN", "LOW", "MEDIUM", "HIGH"}
SENSITIVE_PARTS = {".git", ".claude-profiles", "secrets"}


def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def validate_task_id(task_id: str) -> str:
    value = task_id.upper()
    if not TASK_ID_RE.fullmatch(value):
        raise ValueError("task id must match [A-Z0-9][A-Z0-9._-]{2,63}")
    return value


def repo_path(root: Path, relative: str, *, must_exist: bool = False) -> Path:
    normalized = relative.replace("\\", "/").strip()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    if not normalized:
        raise ValueError("repository path must not be empty")
    candidate = (root / normalized).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"path escapes repository: {relative}") from exc
    if any(part.lower() in SENSITIVE_PARTS for part in candidate.parts):
        raise ValueError(f"sensitive path is not allowed: {relative}")
    if candidate.name.lower().startswith(".env"):
        raise ValueError(f"environment secret path is not allowed: {relative}")
    if must_exist and not candidate.is_file():
        raise ValueError(f"file does not exist: {relative}")
    return candidate


def rel_posix(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def task_path(root: Path, task_id: str) -> Path:
    return root / "coordination" / "active" / f"{task_id}.md"


def handoff_dir(root: Path, task_id: str) -> Path:
    return root / "output" / "agent_handoffs" / task_id


def parse_frontmatter(path: Path) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if len(lines) < 3 or lines[0] != "---":
        raise ValueError(f"missing YAML frontmatter: {path}")
    try:
        end = lines.index("---", 1)
    except ValueError as exc:
        raise ValueError(f"unterminated YAML frontmatter: {path}") from exc

    data: dict[str, Any] = {}
    current_list: str | None = None
    for line in lines[1:end]:
        item = re.match(r"^\s{2}-\s+(.*)$", line)
        if item and current_list:
            data[current_list].append(item.group(1).strip().strip('"'))
            continue
        field = re.match(r"^([a-z_]+):(?:\s*(.*))?$", line)
        if not field:
            continue
        key, raw = field.group(1), (field.group(2) or "").strip()
        if raw:
            data[key] = raw.strip('"')
            current_list = None
        else:
            data[key] = []
            current_list = key
    body = "\n".join(lines[end + 1 :]).lstrip("\n")
    return data, body


def replace_scalar(text: str, key: str, value: str) -> str:
    updated, count = re.subn(
        rf"(?m)^{re.escape(key)}:.*$", f"{key}: {value}", text, count=1
    )
    if count != 1:
        raise ValueError(f"missing frontmatter field: {key}")
    return updated


def set_task_status(root: Path, task_id: str, state: str, note: str = "") -> None:
    state = state.upper()
    if state not in STATES:
        raise ValueError(f"invalid state: {state}")
    path = task_path(root, task_id)
    text = path.read_text(encoding="utf-8")
    text = replace_scalar(text, "status", state)
    text = replace_scalar(text, "updated_at", now())
    if note:
        text = text.rstrip() + f"\n- {now()} `{state}`: {note}\n"
    path.write_text(text, encoding="utf-8", newline="\n")


def normalize_scope(root: Path, values: list[str]) -> list[str]:
    normalized: list[str] = []
    for raw in values:
        value = raw.replace("\\", "/").strip()
        while value.startswith("./"):
            value = value[2:]
        if not value:
            continue
        if any(mark in value for mark in ("*", "?", "[")):
            wildcard_at = min(
                (value.index(mark) for mark in ("*", "?", "[") if mark in value),
                default=len(value),
            )
            prefix = value[:wildcard_at].rstrip("/")
            if prefix:
                repo_path(root, prefix)
        else:
            repo_path(root, value)
        normalized.append(value)
    return sorted(dict.fromkeys(normalized))


def replace_list_field(text: str, key: str, values: list[str]) -> str:
    replacement = f"{key}:\n" + "".join(f"  - {value}\n" for value in values)
    pattern = rf"(?m)^{re.escape(key)}:\s*\n(?:  - .*\n)*"
    updated, count = re.subn(pattern, replacement, text, count=1)
    if count != 1:
        raise ValueError(f"missing list field: {key}")
    return updated


def git_visible_files(root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-co", "--exclude-standard", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    return sorted(
        item.replace("\\", "/")
        for item in result.stdout.decode("utf-8", errors="surrogateescape").split("\0")
        if item
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def baseline_repo_relative(root: Path, relative: str) -> str:
    normalized = relative.replace("\\", "/").strip()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    lexical = Path(normalized)
    if not normalized or lexical.is_absolute():
        raise ValueError(f"baseline path must be repository-relative: {relative}")
    if any(part.lower() in SENSITIVE_PARTS for part in lexical.parts):
        raise ValueError(f"sensitive baseline path is not allowed: {relative}")
    candidate = (root / lexical).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"path escapes repository: {relative}") from exc
    return lexical.as_posix()


def current_hashes(
    root: Path, *, baseline_paths: Iterable[str] = ()
) -> dict[str, str | None]:
    hashes: dict[str, str | None] = {}
    relative_paths = set(git_visible_files(root))
    relative_paths.update(
        baseline_repo_relative(root, relative) for relative in baseline_paths
    )
    for relative in sorted(relative_paths):
        path = root / relative
        hashes[relative] = sha256(path) if path.is_file() else None
    return hashes


def expanded_scope(patterns: list[str], visible: set[str]) -> set[str]:
    expanded: set[str] = set()
    for pattern in patterns:
        if any(mark in pattern for mark in ("*", "?", "[")):
            expanded.update(name for name in visible if fnmatch.fnmatch(name, pattern))
        elif pattern.endswith("/"):
            expanded.update(name for name in visible if name.startswith(pattern))
        else:
            expanded.add(pattern)
    return expanded


def active_scope_conflicts(
    root: Path, task_id: str, allowed: list[str], visible: set[str]
) -> dict[str, list[str]]:
    conflicts: dict[str, list[str]] = {}
    active_dir = root / "coordination" / "active"
    for other_path in sorted(active_dir.glob("*.md")):
        if other_path.stem == task_id:
            continue
        other, _ = parse_frontmatter(other_path)
        if other.get("status") not in {"READY", "IMPLEMENTED", "REVIEWED", "VERIFIED"}:
            continue
        other_allowed = normalize_scope(root, list(other.get("allowed_files") or []))
        overlap = sorted(
            expanded_scope(allowed, visible) & expanded_scope(other_allowed, visible)
        )
        if overlap:
            conflicts[other_path.stem] = overlap[:10]
    return conflicts


def json_write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def cmd_new(args: argparse.Namespace) -> int:
    root = args.repo
    task_id = validate_task_id(args.task_id)
    path = task_path(root, task_id)
    if path.exists():
        raise ValueError(f"task already exists: {path}")
    risk = args.risk.upper()
    if risk not in RISKS:
        raise ValueError(f"invalid risk: {risk}")
    allowed = normalize_scope(root, args.allow or [])
    acceptance = args.acceptance or ["Define a targeted executable acceptance check"]
    stamp = now()
    allowed_yaml = "".join(f"  - {item}\n" for item in allowed)
    acceptance_yaml = "".join(f"  - {item}\n" for item in acceptance)
    content = (
        "---\n"
        f"id: {task_id}\n"
        f"title: {args.title}\n"
        "status: DRAFT\n"
        f"risk: {risk}\n"
        f"owner: {args.owner}\n"
        f"created_at: {stamp}\n"
        f"updated_at: {stamp}\n"
        "allowed_files:\n"
        f"{allowed_yaml}"
        "acceptance:\n"
        f"{acceptance_yaml}"
        "---\n\n"
        "## Goal\n\n"
        f"{args.goal or args.title}\n\n"
        "## Non-goals\n\n- No unrelated refactor.\n\n"
        "## Invariants\n\n- Preserve AGENTS.md and project safety contracts.\n\n"
        "## Locate brief\n\n- Pending.\n\n"
        "## Implementation evidence\n\n- Pending.\n\n"
        "## Review evidence\n\n- Pending.\n\n"
        "## Progress\n\n"
        f"- {stamp} `DRAFT`: Task created.\n"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")
    handoff_dir(root, task_id).mkdir(parents=True, exist_ok=True)
    print(path.relative_to(root))
    return 0


def cmd_set_scope(args: argparse.Namespace) -> int:
    root = args.repo
    task_id = validate_task_id(args.task_id)
    path = task_path(root, task_id)
    values = normalize_scope(root, args.allow)
    if not values:
        raise ValueError("at least one allowed file or pattern is required")
    text = replace_list_field(path.read_text(encoding="utf-8"), "allowed_files", values)
    path.write_text(text, encoding="utf-8", newline="\n")
    set_task_status(root, task_id, "LOCATED", "Write scope approved by Codex.")
    return 0


def validate_location(root: Path, task_id: str) -> dict[str, Any]:
    path = handoff_dir(root, task_id) / "location.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    required = {"task_id", "hypothesis", "confidence", "files", "tests", "symbols", "unknowns", "recommended_risk"}
    missing = sorted(required - set(data))
    if missing:
        raise ValueError(f"location.json missing fields: {', '.join(missing)}")
    if data["task_id"] != task_id:
        raise ValueError("location task_id mismatch")
    confidence = float(data["confidence"])
    if not 0 <= confidence <= 1:
        raise ValueError("confidence must be between 0 and 1")
    if data["recommended_risk"] not in {"LOW", "MEDIUM", "HIGH"}:
        raise ValueError("recommended_risk must be LOW, MEDIUM or HIGH")
    if not isinstance(data["files"], list) or not data["files"]:
        raise ValueError("files must be a non-empty list")
    for entry in data["files"]:
        if not isinstance(entry, dict) or not entry.get("path"):
            raise ValueError("each files entry needs path")
        repo_path(root, entry["path"], must_exist=True)
        for line_range in entry.get("ranges", []):
            start, end = int(line_range["start"]), int(line_range["end"])
            if start < 1 or end < start or end - start > 400:
                raise ValueError(f"invalid or oversized range for {entry['path']}")
    for test in data["tests"]:
        repo_path(root, test, must_exist=True)
    return data


def cmd_validate_location(args: argparse.Namespace) -> int:
    task_id = validate_task_id(args.task_id)
    data = validate_location(args.repo, task_id)
    print(json.dumps({"valid": True, "confidence": data["confidence"]}))
    return 0


def cmd_build_context(args: argparse.Namespace) -> int:
    root = args.repo
    task_id = validate_task_id(args.task_id)
    task = task_path(root, task_id).read_text(encoding="utf-8")
    location = validate_location(root, task_id)
    pieces = [f"# Task Contract\n\n{task.rstrip()}\n", "# Located Code\n"]
    remaining = args.max_chars - sum(len(piece) for piece in pieces)
    entries = list(location["files"]) + [
        {"path": item, "reason": "related test", "ranges": []}
        for item in location["tests"]
    ]
    seen: set[str] = set()
    for entry in entries:
        relative = entry["path"].replace("\\", "/")
        if relative in seen or remaining <= 0:
            continue
        seen.add(relative)
        path = repo_path(root, relative, must_exist=True)
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        ranges = entry.get("ranges") or [{"start": 1, "end": min(len(lines), 220)}]
        section = [f"\n## {relative}\n\nReason: {entry.get('reason', 'located')}\n"]
        for line_range in ranges:
            start = max(1, int(line_range["start"]) - 5)
            end = min(len(lines), int(line_range["end"]) + 5)
            body = "\n".join(
                f"{number:>6}: {lines[number - 1]}" for number in range(start, end + 1)
            )
            section.append(f"\n```text\n{body}\n```\n")
        rendered = "".join(section)
        if len(rendered) > remaining:
            rendered = rendered[:remaining] + "\n[context truncated]\n"
        pieces.append(rendered)
        remaining -= len(rendered)
    output = handoff_dir(root, task_id) / "context.md"
    output.write_text("\n".join(pieces), encoding="utf-8", newline="\n")
    print(json.dumps({"path": str(output), "chars": output.stat().st_size}, ensure_ascii=False))
    return 0


def cmd_freeze(args: argparse.Namespace) -> int:
    root = args.repo
    task_id = validate_task_id(args.task_id)
    task, _ = parse_frontmatter(task_path(root, task_id))
    allowed = normalize_scope(root, list(task.get("allowed_files") or []))
    if not allowed:
        raise ValueError("allowed_files must be set before freeze")
    hashes = current_hashes(root)
    conflicts = active_scope_conflicts(root, task_id, allowed, set(hashes))
    if conflicts:
        details = "; ".join(
            f"{other}: {', '.join(files)}" for other, files in conflicts.items()
        )
        raise ValueError(f"write scope overlaps an active task: {details}")
    target = handoff_dir(root, task_id)
    baseline_files = target / "baseline_files"
    for pattern in allowed:
        if any(mark in pattern for mark in ("*", "?", "[")):
            matches = [name for name in hashes if fnmatch.fnmatch(name, pattern)]
        else:
            matches = [pattern]
        for relative in matches:
            source = repo_path(root, relative)
            if source.is_file():
                destination = baseline_files / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, destination)
    json_write(
        target / "baseline.json",
        {"task_id": task_id, "created_at": now(), "allowed_files": allowed, "hashes": hashes},
    )
    set_task_status(root, task_id, "READY", "Baseline frozen; implementation may start.")
    print(json.dumps({"files_hashed": len(hashes), "allowed_files": allowed}, ensure_ascii=False))
    return 0


def scope_allowed(relative: str, patterns: list[str]) -> bool:
    return any(
        relative == pattern.rstrip("/")
        or (pattern.endswith("/") and relative.startswith(pattern))
        or fnmatch.fnmatch(relative, pattern)
        for pattern in patterns
    )


def changed_since_baseline(root: Path, task_id: str) -> tuple[list[str], list[str]]:
    baseline_path = handoff_dir(root, task_id) / "baseline.json"
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    before = baseline["hashes"]
    after = current_hashes(root, baseline_paths=before)
    changed = sorted(
        relative for relative in set(before) | set(after) if before.get(relative) != after.get(relative)
    )
    task_relative = rel_posix(root, task_path(root, task_id))
    allowed = list(baseline["allowed_files"]) + [task_relative]
    violations = [relative for relative in changed if not scope_allowed(relative, allowed)]
    return changed, violations


def cmd_scope_check(args: argparse.Namespace) -> int:
    root = args.repo
    task_id = validate_task_id(args.task_id)
    changed, violations = changed_since_baseline(root, task_id)
    payload = {"task_id": task_id, "changed_files": changed, "violations": violations, "passed": not violations}
    json_write(handoff_dir(root, task_id) / "scope_check.json", payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if not violations else 2


def cmd_diff(args: argparse.Namespace) -> int:
    root = args.repo
    task_id = validate_task_id(args.task_id)
    baseline = json.loads((handoff_dir(root, task_id) / "baseline.json").read_text(encoding="utf-8"))
    changed, _ = changed_since_baseline(root, task_id)
    patches: list[str] = []
    baseline_files = handoff_dir(root, task_id) / "baseline_files"
    for relative in changed:
        if not scope_allowed(relative, baseline["allowed_files"]):
            continue
        old_path = baseline_files / relative
        new_path = root / relative
        old = old_path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True) if old_path.is_file() else []
        new = new_path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True) if new_path.is_file() else []
        patches.extend(
            difflib.unified_diff(old, new, fromfile=f"a/{relative}", tofile=f"b/{relative}")
        )
    output = handoff_dir(root, task_id) / "diff.patch"
    output.write_text("".join(patches), encoding="utf-8", newline="\n")
    print(output)
    return 0


def cmd_set_status(args: argparse.Namespace) -> int:
    task_id = validate_task_id(args.task_id)
    set_task_status(args.repo, task_id, args.state, args.note or "")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    task_id = validate_task_id(args.task_id)
    task, _ = parse_frontmatter(task_path(args.repo, task_id))
    artifacts = handoff_dir(args.repo, task_id)
    payload = {
        "task": task,
        "artifacts": sorted(path.name for path in artifacts.iterdir()) if artifacts.exists() else [],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_delete(args: argparse.Namespace) -> int:
    task_id = validate_task_id(args.task_id)
    if args.confirm != task_id:
        raise ValueError(f"pass --confirm {task_id} to delete this task")
    path = task_path(args.repo, task_id)
    artifacts = handoff_dir(args.repo, task_id)
    if path.exists():
        path.unlink()
    if artifacts.exists():
        shutil.rmtree(artifacts)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    commands = parser.add_subparsers(dest="command", required=True)

    new = commands.add_parser("new")
    new.add_argument("task_id")
    new.add_argument("--title", required=True)
    new.add_argument("--owner", default="unassigned")
    new.add_argument("--risk", default="UNKNOWN")
    new.add_argument("--goal")
    new.add_argument("--allow", action="append")
    new.add_argument("--acceptance", action="append")
    new.set_defaults(func=cmd_new)

    scope = commands.add_parser("set-scope")
    scope.add_argument("task_id")
    scope.add_argument("--allow", action="append", required=True)
    scope.set_defaults(func=cmd_set_scope)

    locate = commands.add_parser("validate-location")
    locate.add_argument("task_id")
    locate.set_defaults(func=cmd_validate_location)

    context = commands.add_parser("build-context")
    context.add_argument("task_id")
    context.add_argument("--max-chars", type=int, default=40_000)
    context.set_defaults(func=cmd_build_context)

    freeze = commands.add_parser("freeze")
    freeze.add_argument("task_id")
    freeze.set_defaults(func=cmd_freeze)

    check = commands.add_parser("scope-check")
    check.add_argument("task_id")
    check.set_defaults(func=cmd_scope_check)

    diff = commands.add_parser("diff")
    diff.add_argument("task_id")
    diff.set_defaults(func=cmd_diff)

    state = commands.add_parser("set-status")
    state.add_argument("task_id")
    state.add_argument("state", choices=sorted(STATES))
    state.add_argument("--note")
    state.set_defaults(func=cmd_set_status)

    status = commands.add_parser("status")
    status.add_argument("task_id")
    status.set_defaults(func=cmd_status)

    delete = commands.add_parser("delete")
    delete.add_argument("task_id")
    delete.add_argument("--confirm", required=True)
    delete.set_defaults(func=cmd_delete)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    args.repo = args.repo.resolve()
    try:
        return int(args.func(args))
    except (OSError, ValueError, json.JSONDecodeError, subprocess.CalledProcessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
