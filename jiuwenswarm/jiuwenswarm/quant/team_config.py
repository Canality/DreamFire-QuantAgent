"""Quant Team configuration for JiuwenSwarm multi-agent mode.

Defines the Coordinator/Alpha/Risk & Evidence multi-agent team structure.
The actual team config is in config.yaml under modes.team.quant_team.
This module provides the persona texts and config utilities for programmatic access.
"""

from pathlib import Path

_ROLES_DIR = Path(__file__).resolve().parent / "roles"


def load_persona(role: str) -> str:
    """Load a role persona from roles/<role>.md."""
    path = _ROLES_DIR / f"{role}.md"
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    return ""


COORDINATOR_PERSONA = load_persona("coordinator")
ALPHA_ANALYST_PERSONA = load_persona("alpha_analyst")
RISK_EVIDENCE_ANALYST_PERSONA = load_persona("risk_evidence_analyst")

# Short personas for config.yaml (first paragraph of each)
COORDINATOR_PERSONA_SHORT = (
    "你是量化投资组合经理（Quant PM），负责协调Alpha和Risk & Evidence两位分析师。"
    "你按固定八阶段获取49只股票、计算因子、收集两个有界AgentProposal，再由服务端缓存中的"
    "确定性select、allocate、backtest、report阶段完成决策。分析师不能覆盖股票、权重或回测输入。"
    "核心原则：完整覆盖、证据驱动、职责隔离、失败关闭。"
)

ALPHA_ANALYST_PERSONA_SHORT = (
    "你是 Alpha 分析师。你的任务是基于期限对齐趋势和板块领导力，提供有证据的纳入提案。"
    "唯一工具：`quant_alpha_view`。输出：结构化 AgentProposal（ticker、action='include'、"
    "adjustment 0~+3、confidence、evidence、rationale）。"
    "你不能选股、配仓或回测——这些是 Coordinator 的确定性阶段。"
    "风格：乐观但有约束，每个提案必须有具体因子数值支撑。"
)

RISK_EVIDENCE_ANALYST_PERSONA_SHORT = (
    "你是风险与证据分析师。你的任务是识别极端下行风险、集中度隐患和证据冲突，行使有界否决权。"
    "唯一工具：`quant_risk_evidence_view`。输出：结构化 AgentProposal（ticker、action='exclude'|'reduce'、"
    "adjustment -3~0、confidence、至少两项独立 evidence、rationale）。"
    "你不能生成防守组合或指定现金比例——这些是 Coordinator 的确定性阶段。"
    "风格：谨慎但精准，只在至少两项独立因子证据支持时提案。"
)


QUANT_TEAM_PREDEFINED_MEMBERS = [
    {
        "member_name": "alpha_analyst",
        "display_name": "Alpha Analyst 趋势与机会分析师",
        "persona": ALPHA_ANALYST_PERSONA_SHORT,
        "role_type": "teammate",
    },
    {
        "member_name": "risk_evidence_analyst",
        "display_name": "Risk & Evidence Analyst 风险与证据分析师",
        "persona": RISK_EVIDENCE_ANALYST_PERSONA_SHORT,
        "role_type": "teammate",
    },
]
