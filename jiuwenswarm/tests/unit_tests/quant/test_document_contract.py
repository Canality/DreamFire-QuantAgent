"""Document contract tests: verify SKILL.md and README freshness.

Ensures documents don't contain hardcoded numbers that drift with experiments.
Reference: DEVELOPMENT_PLAN.md WP0-A acceptance criteria.
"""

from __future__ import annotations

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
