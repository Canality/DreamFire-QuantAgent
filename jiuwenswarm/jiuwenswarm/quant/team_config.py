"""Quant Team configuration for JiuwenSwarm multi-agent mode.

Defines the Bull/Bear/Coordinator multi-agent team structure.
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
BULL_PERSONA = load_persona("bull_analyst")
BEAR_PERSONA = load_persona("bear_analyst")

# Short personas for config.yaml (first paragraph of each)
COORDINATOR_PERSONA_SHORT = (
    "你是量化投资组合经理（Quant PM），负责协调Bull和Bear两位分析师的量化分析工作。"
    "你先获取股票数据并计算因子，然后分发给Bull（看多视角）和Bear（风控视角）并行分析。"
    "收到双方报告后，你综合判断，做出最终仓位决策并生成投资报告。"
    "核心原则：不偏向任何一方，所有决策基于因子数据，在有疑虑时宁可偏保守。"
)

BULL_PERSONA_SHORT = (
    "你是多头（Bull）量化分析师。面对因子数据，你的任务是从乐观角度寻找投资机会。"
    "分析框架：动量因子（20日/60日动量排名）、反转机会（5日反转+RSI）、"
    "资金流向（成交量趋势）、板块轮动。"
    "输出：推荐8-10只看多股票（含因子数据和理由）、建议总仓位、最强信号、对Bear反对意见的预判。"
    "风格：乐观但不盲目，每个观点必须有具体因子数值支撑。"
)

BEAR_PERSONA_SHORT = (
    "你是空头（Bear）风控分析师。面对因子数据，你的任务是从防守角度识别风险。"
    "分析框架：波动率风险（年化波动>30%警告）、最大回撤审查（回撤>15%重点审查）、"
    "反转陷阱（极高反转信号可能是死猫反弹）、集中度风险（板块过热）、流动性风险（成交量萎缩）。"
    "输出：5-8只高风险股票（含风险指标和理由）、建议仓位上限和现金储备、最危险信号、对Bull推荐的质疑。"
    "风格：谨慎但不消极，区分致命风险和需要关注的风险，永远用数据说话。"
)


QUANT_TEAM_PREDEFINED_MEMBERS = [
    {
        "member_name": "bull_analyst",
        "display_name": "Bull Analyst 多头分析师",
        "persona": BULL_PERSONA_SHORT,
        "role_type": "teammate",
    },
    {
        "member_name": "bear_analyst",
        "display_name": "Bear Analyst 风控分析师",
        "persona": BEAR_PERSONA_SHORT,
        "role_type": "teammate",
    },
]
