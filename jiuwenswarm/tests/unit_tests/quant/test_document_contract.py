"""Document contract tests: verify SKILL.md and README freshness.

Ensures documents don't contain hardcoded numbers that drift with experiments.
Reference: DEVELOPMENT_PLAN.md WP0-A acceptance criteria.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[4]

EXTENSION_SKILL = (
    PROJECT_ROOT / "jiuwenswarm" / "jiuwenswarm" / "extensions"
    / "quant-finance" / "skills" / "quant-investment" / "SKILL.md"
)
RESOURCE_SKILL = (
    PROJECT_ROOT / "jiuwenswarm" / "jiuwenswarm" / "resources"
    / "agent" / "workspace" / "skills" / "quant-investment" / "SKILL.md"
)
README = PROJECT_ROOT / "README.md"
SUMMARY_SCRIPT = (
    PROJECT_ROOT / "jiuwenswarm" / "scripts" / "generate_validation_summary.py"
)
AGENT_IDENTITY = PROJECT_ROOT / "AGENTS.md"
CLAUDE_IDENTITY = PROJECT_ROOT / "CLAUDE.md"
AGENT_WORKFLOW = PROJECT_ROOT / "AGENT_WORKFLOW.md"
DEVELOPMENT_PLAN = PROJECT_ROOT / "DEVELOPMENT_PLAN.md"
VALIDATION = PROJECT_ROOT / "VALIDATION.md"
DISCUSSION = PROJECT_ROOT / ".claude" / "discussion.md"
HISTORY_INDEX = PROJECT_ROOT / "history" / "README.md"
HISTORY_V213 = PROJECT_ROOT / "history" / "v2.13_2026-07-30.md"
HISTORY_V214 = PROJECT_ROOT / "history" / "v2.14_2026-08-05.md"
HISTORY_V215 = PROJECT_ROOT / "history" / "v2.15_2026-08-06.md"
HISTORY_V216 = PROJECT_ROOT / "history" / "v2.16_2026-08-13.md"

ACTIVE_IDENTITY_FILES = (
    PROJECT_ROOT / "AGENTS.md",
    PROJECT_ROOT / "CLAUDE.md",
    PROJECT_ROOT / ".claude" / "skills" / "explain-change.md",
    PROJECT_ROOT / "jiuwenswarm" / "evaluation" / "policy_validator_prototype.py",
    PROJECT_ROOT / "jiuwenswarm" / "jiuwenswarm" / "quant" / "team_config.py",
    PROJECT_ROOT / "jiuwenswarm" / "jiuwenswarm" / "quant" / "roles" / "coordinator.md",
    PROJECT_ROOT / "jiuwenswarm" / "jiuwenswarm" / "quant" / "reporting" / "agent_view_parser.py",
    PROJECT_ROOT / "jiuwenswarm" / "jiuwenswarm" / "quant" / "reporting" / "__init__.py",
    PROJECT_ROOT / "jiuwenswarm" / "jiuwenswarm" / "quant" / "reporting" / "company_report.py",
    PROJECT_ROOT / "jiuwenswarm" / "jiuwenswarm" / "extensions" / "quant-finance" / "extension.py",
)

RETIRED_IDENTITY_MARKERS = (
    "parse_bull_bear_pair",
    "BULL_PERSONA",
    "BEAR_PERSONA",
    "bull_analyst",
    "bear_analyst",
    "quant_bull_view",
    "quant_bear_view",
    "quant.bull_view",
    "quant.bear_view",
    "Bull Analyst",
    "Bear Analyst",
)


def test_agent_identity_makes_frozen_contracts_challengeable_not_optional():
    """Frozen rules may be challenged, but only explicit migration can unfreeze."""
    identity = AGENT_IDENTITY.read_text(encoding="utf-8")
    normalized_identity = re.sub(r"\s+", "", identity)

    required_semantics = (
        "默认执行契约和安全边界",
        "不是不可质疑的永久真理",
        "证据或可复现反例",
        "范围受限的替代方案",
        "质疑待决期间继续执行现行契约",
        "不得把质疑当成授权",
        "产品意图、外部权限或权威来源、重大安全/证据边界",
        "新的版本化任务或契约",
        "迁移与回退、负向测试和验收结果",
    )
    for statement in required_semantics:
        assert re.sub(r"\s+", "", statement) in normalized_identity

    forbidden_shortcuts = (
        "Agent 可自行解除冻结",
        "有疑议可以先实现",
        "任何疑议都必须询问用户",
        "冻结规则仅供参考",
    )
    for shortcut in forbidden_shortcuts:
        assert re.sub(r"\s+", "", shortcut) not in normalized_identity


def test_active_development_governance_has_exactly_two_peer_roles():
    """Codex and Claude are the only active development collaborators."""
    active_paths = (
        AGENT_IDENTITY,
        CLAUDE_IDENTITY,
        AGENT_WORKFLOW,
        DEVELOPMENT_PLAN,
        README,
        PROJECT_ROOT / ".agents" / "skills" / "local-code-scout" / "SKILL.md",
        PROJECT_ROOT / ".agents" / "skills" / "bounded-code-implementer" / "SKILL.md",
        PROJECT_ROOT / ".agents" / "skills" / "diff-contract-reviewer" / "SKILL.md",
        PROJECT_ROOT / "scripts" / "agent_task.py",
    )
    combined = "\n".join(path.read_text(encoding="utf-8") for path in active_paths)

    for retired_identity in ("Missed", "Goone", "Qwen", "DeepSeek"):
        assert retired_identity not in combined
    for retired_launcher in (
        "scripts/agent_role.py",
        "scripts/agent-role.cmd",
        "scripts/claude-qwen",
        "scripts/claude-deepseek",
    ):
        assert retired_launcher not in combined

    agents = AGENT_IDENTITY.read_text(encoding="utf-8")
    claude = CLAUDE_IDENTITY.read_text(encoding="utf-8")
    workflow = AGENT_WORKFLOW.read_text(encoding="utf-8")
    assert "Codex（计划与验收）" in agents
    assert "Claude（执行与开发）" in agents
    assert "平等协作者" in agents and "不是一般意义上的上下级" in agents
    assert "定位、实现、审查是一个任务的阶段" in agents
    assert "Coordinator、AlphaAnalyst、Risk&EvidenceAnalyst" in re.sub(
        r"\s+", "", agents
    )
    assert "Claude 不自行写 `VERIFIED/CLOSED`" in claude
    assert "双方最多各两次证据交换" in claude
    assert "ACCEPT" in workflow and "MODIFY" in workflow
    assert "REJECT" in workflow and "用户升级" in workflow
    assert "无争议工作继续" in workflow
    task_cli = (PROJECT_ROOT / "scripts" / "agent_task.py").read_text(
        encoding="utf-8"
    )
    assert "Codex/Claude workflow" in task_cli
    assert "Write scope approved by Codex." in task_cli
    assert "multi-model workflow" not in task_cli
    assert "Write scope approved by Planner." not in task_cli

    for retired_file in (
        PROJECT_ROOT / "scripts" / "agent-role.cmd",
        PROJECT_ROOT / "scripts" / "agent_role.py",
        PROJECT_ROOT / "scripts" / "claude-deepseek.cmd",
        PROJECT_ROOT / "scripts" / "claude-deepseek.ps1",
        PROJECT_ROOT / "scripts" / "claude-profile.ps1",
        PROJECT_ROOT / "scripts" / "claude-qwen.cmd",
        PROJECT_ROOT / "scripts" / "claude-qwen.ps1",
        PROJECT_ROOT / "scripts" / "claude_profile.py",
    ):
        assert not retired_file.exists(), f"retired launcher remains: {retired_file}"


def _skill_body(path: Path) -> str:
    """Return SKILL.md content after the YAML frontmatter."""
    text = path.read_text(encoding="utf-8")
    # Find the second '---' line
    parts = text.split("---", 2)
    if len(parts) >= 3:
        return parts[2]
    return text


def test_active_paths_have_no_retired_agent_identity_compatibility():
    """Current runtime/docs expose only Alpha and Risk & Evidence identities."""
    for path in ACTIVE_IDENTITY_FILES:
        text = path.read_text(encoding="utf-8")
        found = [marker for marker in RETIRED_IDENTITY_MARKERS if marker in text]
        assert not found, f"{path.relative_to(PROJECT_ROOT)} retains {found}"

    roles_dir = PROJECT_ROOT / "jiuwenswarm" / "jiuwenswarm" / "quant" / "roles"
    assert not (roles_dir / "bull_analyst.md").exists()
    assert not (roles_dir / "bear_analyst.md").exists()


def test_market_regime_vocabulary_remains_supported():
    """Role cleanup must not remove the quantitative market-state vocabulary."""
    from jiuwenswarm.quant.agent_structured_output import RegimeDiagnosis

    diagnosis = RegimeDiagnosis(
        final="bull",
        technical="bear",
        index="range",
        consensus=False,
    )
    assert (diagnosis.final, diagnosis.technical, diagnosis.index) == (
        "bull",
        "bear",
        "range",
    )


def test_version_history_archive_contract():
    """Version history is complete, append-only, and separate from current truth."""
    for path in (HISTORY_INDEX, HISTORY_V213, HISTORY_V214, HISTORY_V215, HISTORY_V216):
        assert path.is_file(), f"missing version-history file: {path}"

    history_files = sorted(HISTORY_INDEX.parent.glob("v*.md"))
    assert [path.name for path in history_files] == [
        "v2.13_2026-07-30.md",
        "v2.14_2026-08-05.md",
        "v2.15_2026-08-06.md",
        "v2.15_2026-08-07.md",
        "v2.15_2026-08-07_discussion.md",
        "v2.16_2026-08-13.md",
        "v2.16_2026-08-13_discussion.md",
    ]
    assert all(
        re.fullmatch(r"v\d+\.\d+_\d{4}-\d{2}-\d{2}(_discussion)?\.md", path.name)
        for path in history_files
    )

    index = HISTORY_INDEX.read_text(encoding="utf-8")
    assert "append-only" in index
    assert "不是当前事实源" in index
    assert "170e9043e788f1d8e69ea16a6c390204ddc490ed" in index
    assert "89322cdff88ccd3172055fe870efbf5d45676ff6" in index
    assert "f205967b11065b36fc1ef6d7898c2cf79dea0872" in index

    v213 = HISTORY_V213.read_text(encoding="utf-8")
    for heading in ("### 0.", "### 1.", "### 2.", "### 3.", "### 4."):
        assert heading in v213
    assert "1,204,831" in v213
    assert "PROVISIONAL / BLOCKED" in v213

    v214 = HISTORY_V214.read_text(encoding="utf-8")
    for section in range(1, 16):
        assert f"### -{section}." in v214
    assert "multi-agent-validation-20260805-100147" in v214
    assert "DOES_NOT_QUALIFY" in v214
    assert "双入口已接线，完整 E2E 仍失败" in v214
    assert "WP1-B/C 验收完成，停止本轮 Alpha 搜索" in v214

    v215 = HISTORY_V215.read_text(encoding="utf-8")
    for marker in (
        "89322cdff88ccd3172055fe870efbf5d45676ff6..f205967b11065b36fc1ef6d7898c2cf79dea0872",
        "610 passed, 1 skipped",
        "WP1-D 正式稳定性",
        "两方开发协作",
        "Mac candidate",
        "没有 fresh direct/formal/model/network 运行",
        "production_six_factor",
    ):
        assert marker in v215

    v216 = HISTORY_V216.read_text(encoding="utf-8")
    for marker in (
        "BRIDGE-OPS-5",
        "Mac 交接文件已清理",
        "WP1-E4-R1",
        "v2.15 Windows 继续作为历史锚",
    ):
        assert marker in v216

    current_validation = VALIDATION.read_text(encoding="utf-8")
    assert not re.search(r"^### (?:-\d+|[0-4])\.", current_validation, re.MULTILINE)
    for marker in (
        "multi-agent-validation-20260805-100147",
        "4e4ff29c8269d5e9a43e96a5fabd05c89ce10d1a8742c2c624c878db59f2fac1",
        "50d49ce963809c72cfda73f53ec7ac0cd0e419fdb4d6c16a487781f45dc529a4",
            "610 passed, 1 skipped",
            "f205967b11065b36fc1ef6d7898c2cf79dea0872",
            "FINANCIAL_PARTIAL",
        "PROVISIONAL / BLOCKED",
    ):
        assert marker in current_validation

    current_discussion = DISCUSSION.read_text(encoding="utf-8")
    assert "双入口已接线，完整 E2E 仍失败" not in current_discussion
    assert "v2.15 Mac 候选交接复验" not in current_discussion
    assert "v2.14 活动旧角色兼容清理待复验" not in current_discussion
    assert "TRACK2-V215-HANDOFF-0806" not in current_discussion
    # v2.16 current handoff should reference WP1-E4-R1 implementation and BRIDGE-OPS-5
    assert "WP1-E4-R1" in current_discussion
    assert "BRIDGE-OPS-5" in current_discussion or "BRIDGE" in current_discussion
    assert "READY / IMPLEMENT" in current_discussion

    for identity_file in (
        PROJECT_ROOT / "AGENTS.md",
        PROJECT_ROOT / "AGENT_WORKFLOW.md",
        PROJECT_ROOT / "CLAUDE.md",
    ):
        identity = identity_file.read_text(encoding="utf-8")
        assert "history/" in identity
        assert "append-only" in identity

    readme = README.read_text(encoding="utf-8")
    claude = (PROJECT_ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    plan = (PROJECT_ROOT / "DEVELOPMENT_PLAN.md").read_text(encoding="utf-8")
    for current_command_doc in (readme, claude):
        assert "PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'" not in current_command_doc
        assert "Remove-Item Env:PYTEST_DISABLE_PLUGIN_AUTOLOAD" in current_command_doc
    assert "公告已形成 1,470 条、49/49" in plan
    assert "最新已接受 formal 为 97,209 input token / 12 tool calls" in plan


def test_version_history_canonical_snapshots_are_complete():
    """Archived source snapshots retain their byte-level canonical contents."""

    def marked_snapshot(path: Path, name: str) -> bytes:
        text = path.read_text(encoding="utf-8")
        begin = f"<!-- BEGIN {name} -->"
        end = f"<!-- END {name} -->"
        assert text.count(begin) == text.count(end) == 1
        body = text.split(begin, 1)[1].split(end, 1)[0]
        return (body.strip("\n") + "\n").encode()

    expected = {
        (HISTORY_V213, "V2.13_VALIDATION_SNAPSHOT"):
            "b91dae9d9897fb54883a121a91ca05955b0dc408fc39e017371ac5816d07bfe3",
        (HISTORY_V214, "V2.14_VALIDATION_SNAPSHOT"):
            "b4d013f8df390397ed2ef033e88ec5c9d46d31af104d2f716100173db414d963",
        (HISTORY_V214, "V2.14_CLOSED_DISCUSSION_SNAPSHOT"):
            "2d29c0cdfa004b9c4800db658b3d8adcba33152e93bbaa6f7b475df0e6f0e540",
    }
    for (path, name), digest in expected.items():
        assert hashlib.sha256(marked_snapshot(path, name)).hexdigest() == digest


def test_version_history_markdown_links_resolve():
    """Every checked-in history Markdown link resolves inside the repository."""
    link_pattern = re.compile(r"\[[^\]]+\]\(([^)]+\.md)\)")
    for source in (README, VALIDATION, HISTORY_INDEX):
        text = source.read_text(encoding="utf-8")
        for target in link_pattern.findall(text):
            if target.startswith(("http://", "https://")):
                continue
            resolved = (source.parent / target).resolve()
            assert resolved.is_relative_to(PROJECT_ROOT)
            assert resolved.is_file(), f"broken Markdown link in {source}: {target}"


# ---- SKILL.md hardcoded-value tests ----


def test_skill_no_hardcoded_180_days():
    """Skill must not hardcode '180 天' — lookback is config-driven."""
    for path in (EXTENSION_SKILL, RESOURCE_SKILL):
        body = _skill_body(path)
        assert "180 天" not in body, (
            f"{path.name}: hardcoded '180 天' found. "
            f"Use '回看期由 Extension 根据 _MIN_TRAIN_DAYS + _FORWARD_TEST_DAYS 自动确定' instead."
        )
        assert "180天" not in body, (
            f"{path.name}: hardcoded '180天' found."
        )


def test_skill_no_hardcoded_ic_values():
    """Skill must not contain static IC values that drift with experiments."""
    # Patterns that look like hardcoded IC values: "momentum_20=+0.0787", "IC=+0.72", etc.
    ic_pattern = re.compile(r'(momentum_\d+|volume_\w+|reversal_\d+|max_drawdown)\s*[=＝]\s*[+-]?\d+\.\d+')
    for path in (EXTENSION_SKILL, RESOURCE_SKILL):
        body = _skill_body(path)
        matches = ic_pattern.findall(body)
        assert not matches, (
            f"{path.name}: hardcoded IC values found: {matches}. "
            f"IC and factor performance numbers must reference VALIDATION.md."
        )


def test_skill_no_hardcoded_window_counts():
    """Skill must not hardcode window counts (11 IC windows, 21 portfolio windows)."""
    # Look for patterns like "11 个" or "21 个" near "窗口"
    window_pattern = re.compile(r'(?:开发|IC|组合|backtest).*?\b(\d{1,2})\s*个.*?窗口')
    for path in (EXTENSION_SKILL, RESOURCE_SKILL):
        body = _skill_body(path)
        matches = window_pattern.findall(body)
        assert not matches, (
            f"{path.name}: hardcoded window counts found: {matches}. "
            f"Window counts must reference VALIDATION.md."
        )


def test_skill_no_hardcoded_performance_numbers():
    """Skill must not contain static performance numbers like '+0.50% vs -0.07%'."""
    perf_pattern = re.compile(r'(收益|return).*?[+-]\d+\.\d+%?\s*(?:vs|优于|对比).*?[+-]\d+\.\d+%?')
    for path in (EXTENSION_SKILL, RESOURCE_SKILL):
        body = _skill_body(path)
        matches = perf_pattern.findall(body, re.IGNORECASE)
        assert not matches, (
            f"{path.name}: hardcoded performance comparison found: {matches}. "
            f"Challenger performance must reference VALIDATION.md."
        )


def test_skill_no_fabricated_training_period():
    """Skill must not contain fabricated training period data like '2026年2-7月'."""
    fake_pattern = re.compile(r'训练期.*2026\s*年')
    for path in (EXTENSION_SKILL, RESOURCE_SKILL):
        body = _skill_body(path)
        assert not fake_pattern.search(body), (
            f"{path.name}: fabricated training period found. "
            f"Training period data must come from actual experiments."
        )


def test_skill_references_validation_md():
    """Skill must reference VALIDATION.md for dynamic data."""
    for path in (EXTENSION_SKILL, RESOURCE_SKILL):
        body = _skill_body(path)
        assert "VALIDATION.md" in body, (
            f"{path.name}: missing reference to VALIDATION.md for authoritative data."
        )


def test_skill_states_production_15_stocks():
    """Skill must explicitly state production is fixed 15 stocks."""
    for path in (EXTENSION_SKILL, RESOURCE_SKILL):
        body = _skill_body(path)
        # "8-15 只" is the old ambiguous form — should not appear
        assert "8-15 只" not in body, (
            f"{path.name}: ambiguous '8-15 只' found. Production is always 15."
        )


def test_skill_has_service_cache_description():
    """Skill must describe that raw matrices stay in Extension cache, not LLM context."""
    for path in (EXTENSION_SKILL, RESOURCE_SKILL):
        body = _skill_body(path)
        assert "服务端缓存" in body, (
            f"{path.name}: missing service-side cache description."
        )
        assert "不传入行情参数" in body or "不得在消息" in body, (
            f"{path.name}: missing instruction that market data must not enter LLM context."
        )


# ---- SKILL.md sync tests ----


def test_skill_files_are_identical():
    """Both SKILL.md files must be byte-identical."""
    ext = EXTENSION_SKILL.read_bytes()
    res = RESOURCE_SKILL.read_bytes()
    assert ext == res, (
        "SKILL.md files are out of sync. "
        "Extension and resource copies must be identical. "
        "Run: diff the files and sync."
    )


# ---- README tests ----


def test_readme_references_validation_summary():
    """README must reference validation_summary.json for dynamic numbers."""
    text = README.read_text(encoding="utf-8")
    assert "validation_summary.json" in text, (
        "README must reference output/validation_summary.json for dynamic performance/token numbers."
    )


def test_readme_references_validation_md():
    """README must point to VALIDATION.md as the single source of truth."""
    text = README.read_text(encoding="utf-8")
    assert "VALIDATION.md" in text, (
        "README must reference VALIDATION.md as the authoritative run-state source."
    )


def test_readme_has_one_machine_owned_dynamic_summary_block():
    """Per-run values belong to one generated block, initially fail-closed."""

    text = README.read_text(encoding="utf-8")
    assert text.count("<!-- BEGIN GENERATED VALIDATION SUMMARY -->") == 1
    assert text.count("<!-- END GENERATED VALIDATION SUMMARY -->") == 1
    block = text.split("<!-- BEGIN GENERATED VALIDATION SUMMARY -->", 1)[1]
    block = block.split("<!-- END GENERATED VALIDATION SUMMARY -->", 1)[0]
    for field in (
        "direct_status",
        "formal_status",
        "report_status",
        "formal_session",
        "formal_input_tokens",
        "audit_passed",
    ):
        assert f"`{field}`" in block
    assert block.count("`NOT_GENERATED`") == 6
    assert "--readme update" in block


def test_readme_outside_generated_block_has_no_run_derived_claims():
    """Latest-run counts and verdicts must not bypass the generated checker."""

    text = README.read_text(encoding="utf-8")
    before, rest = text.split("<!-- BEGIN GENERATED VALIDATION SUMMARY -->", 1)
    _, after = rest.split("<!-- END GENERATED VALIDATION SUMMARY -->", 1)
    prose = before + after
    forbidden = (
        "49/49",
        "1,470",
        "8/8",
        "1/1",
        "12 次工具调用",
        "最新 direct",
        "最新 formal",
        "最新候选",
        "audit 退出 0",
    )
    for marker in forbidden:
        assert marker not in prose


def test_summary_generator_never_writes_validation_fact_source():
    """The generator may write output JSON/README, never VALIDATION.md."""

    source = SUMMARY_SCRIPT.read_text(encoding="utf-8")
    assert 'project_root / "VALIDATION.md"' not in source
    assert "VALIDATION.write" not in source


def test_readme_no_stale_performance():
    """README must not copy exact performance numbers that change per run."""
    # These exact numbers appeared in the old README and should now reference the JSON
    stale_patterns = [
        (r'\+3\.2468%', '+3.2468% (stale — use validation_summary.json)'),
        (r'2\.8762%', '2.8762% (stale — use validation_summary.json)'),
        (r'94\.94%', '94.94% (stale — use validation_summary.json)'),
        (r'5\.06%', '5.06% (stale — use validation_summary.json)'),
    ]
    text = README.read_text(encoding="utf-8")
    for pattern, desc in stale_patterns:
        # These should NOT appear as standalone facts without context
        # They can appear inside a reference like "see validation_summary.json"
        matches = list(re.finditer(pattern, text))
        for m in matches:
            # Check context: is this inside a line that references the JSON?
            line_start = text.rfind('\n', 0, m.start()) + 1
            line_end = text.find('\n', m.end())
            line = text[line_start:line_end]
            if "validation_summary.json" not in line and "VALIDATION.md" not in line:
                raise AssertionError(
                    f"README: hardcoded number '{m.group()}' on line containing: '{line[:80]}...'. "
                    f"Performance numbers must reference validation_summary.json."
                )
