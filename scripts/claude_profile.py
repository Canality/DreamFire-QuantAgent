#!/usr/bin/env python3
"""Launch Claude Code with an isolated provider profile."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


PROFILES = {"qwen", "deepseek"}


def profile_environment(profile: str) -> tuple[dict[str, str], str]:
    if profile not in PROFILES:
        raise ValueError(f"unknown Claude profile: {profile}")
    profile_dir = Path.home() / ".claude-profiles" / profile
    settings_path = profile_dir / "settings.json"
    if not settings_path.is_file():
        raise ValueError(f"missing Claude profile: {settings_path}")

    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    profile_env = settings.get("env")
    if not isinstance(profile_env, dict):
        raise ValueError(f"Claude profile has no env object: {settings_path}")

    environment = os.environ.copy()
    for key in list(environment):
        if key.startswith("ANTHROPIC_"):
            environment.pop(key)
    environment.update({str(key): str(value) for key, value in profile_env.items()})
    if environment.get("ANTHROPIC_AUTH_TOKEN") and not environment.get(
        "ANTHROPIC_API_KEY"
    ):
        environment["ANTHROPIC_API_KEY"] = environment["ANTHROPIC_AUTH_TOKEN"]
    environment["CLAUDE_CONFIG_DIR"] = str(profile_dir)
    return environment, str(profile_env.get("ANTHROPIC_MODEL", "unknown"))


def claude_executable() -> str:
    executable = shutil.which("claude.exe") or shutil.which("claude")
    if not executable:
        raise ValueError("claude executable was not found")
    return executable


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in PROFILES:
        print(
            "usage: claude_profile.py {qwen|deepseek} [claude arguments...]",
            file=sys.stderr,
        )
        return 2

    profile = sys.argv[1]
    try:
        environment, model = profile_environment(profile)
        executable = claude_executable()
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(f"Claude profile: {profile} ({model})", flush=True)
    return subprocess.run([executable, *sys.argv[2:]], env=environment, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
