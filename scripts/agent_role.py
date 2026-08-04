#!/usr/bin/env python3
"""Launch one bounded Claude Code role for a versioned project task."""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
from pathlib import Path

from agent_task import RISKS, parse_frontmatter, task_path, validate_task_id
from claude_profile import claude_executable, profile_environment


ROLE_CONFIG = {
    "scout": {
        "skill": ".agents/skills/local-code-scout/SKILL.md",
        "default_profile": "qwen",
        "purpose": "只读定位定义、调用点、测试与未知项，只写 location.json",
    },
    "builder": {
        "skill": ".agents/skills/bounded-code-implementer/SKILL.md",
        "default_profile": "qwen",
        "purpose": "只在任务白名单内完成最小实现并运行验收",
    },
    "critic": {
        "skill": ".agents/skills/diff-contract-reviewer/SKILL.md",
        "default_profile": "qwen",
        "purpose": "在新会话中只读审查任务差异、反例与测试证据",
    },
}


def choose_profile(role: str, risk: str, override: str | None) -> str:
    if override:
        return override
    if role == "builder" and risk == "MEDIUM":
        return "deepseek"
    return ROLE_CONFIG[role]["default_profile"]


def build_prompt(task_id: str, role: str, skill: str) -> tuple[str, str]:
    system = (
        f"你是 Track 2 任务 {task_id} 的 {role.upper()}。"
        f"你的唯一职责是：{ROLE_CONFIG[role]['purpose']}。"
        f"必须先完整读取 {skill}、AGENT_WORKFLOW.md 和 "
        f"coordination/active/{task_id}.md，并严格执行其中的停止规则。"
        "不要通读历史 discussion、output 或整个仓库；不要扩大任务白名单。"
        "交接状态只能写入任务契约规定的工件；不要自行声称 BUSINESS_PASSED。"
    )
    prompt = (
        f"开始执行任务 {task_id} 的 {role} 阶段。先检查任务状态和前序工件；"
        "如果前置条件不满足，记录明确的 BLOCKED 原因并停止。"
    )
    return system, prompt


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task_id")
    parser.add_argument("role", choices=sorted(ROLE_CONFIG))
    parser.add_argument("--profile", choices=("qwen", "deepseek"))
    parser.add_argument(
        "--print",
        action="store_true",
        dest="print_mode",
        help="run non-interactively and return after this role finishes",
    )
    parser.add_argument(
        "--repo", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=180,
        help="hard timeout for --print mode; ignored for interactive sessions",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    root = args.repo.resolve()
    task_id = validate_task_id(args.task_id)
    path = task_path(root, task_id)
    if not path.is_file():
        print(f"ERROR: task does not exist: {path}", file=sys.stderr)
        return 2

    task, _ = parse_frontmatter(path)
    risk = str(task.get("risk", "UNKNOWN")).upper()
    if risk not in RISKS:
        print(f"ERROR: invalid task risk: {risk}", file=sys.stderr)
        return 2
    if args.role == "builder" and risk in {"UNKNOWN", "HIGH"}:
        print(
            f"ERROR: {risk} builder tasks require Planner/Codex routing before launch",
            file=sys.stderr,
        )
        return 2

    config = ROLE_CONFIG[args.role]
    skill = config["skill"]
    if not (root / skill).is_file():
        print(f"ERROR: role skill does not exist: {skill}", file=sys.stderr)
        return 2

    profile = choose_profile(args.role, risk, args.profile)
    system, prompt = build_prompt(task_id, args.role, skill)
    try:
        environment, model = profile_environment(profile)
        executable = claude_executable()
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    command = [
        executable,
        "--bare",
        "--name",
        f"{task_id}:{args.role}",
        "--append-system-prompt",
        system,
        "--permission-mode",
        "acceptEdits",
    ]
    if args.print_mode:
        command.extend(["--print", "--output-format", "text"])
    command.append(prompt)

    print(
        f"Task {task_id}: role={args.role}, risk={risk}, profile={profile}, "
        f"model={model}, mode={'print' if args.print_mode else 'interactive'}",
        flush=True,
    )
    timeout = args.timeout_seconds if args.print_mode and args.timeout_seconds > 0 else None
    if timeout is None:
        return subprocess.run(command, cwd=root, env=environment, check=False).returncode

    process_options: dict[str, object] = {}
    if os.name == "nt":
        process_options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        process_options["start_new_session"] = True
    process = subprocess.Popen(command, cwd=root, env=environment, **process_options)
    try:
        return process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                check=False,
                capture_output=True,
            )
        else:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        process.wait()
        print(
            f"ERROR: {args.role} exceeded the {timeout}s print-mode budget",
            file=sys.stderr,
        )
        return 124


if __name__ == "__main__":
    raise SystemExit(main())
