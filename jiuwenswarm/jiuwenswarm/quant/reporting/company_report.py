"""Generate per-company Markdown reports from CompanyFactBundle."""

from __future__ import annotations

from typing import List

from jiuwenswarm.quant.reporting.models import (
    AgentView,
    CompanyFactBundle,
    MetricFact,
)


def _fmt_pct(value: float | None, decimals: int = 2) -> str:
    if value is None:
        return "N/A"
    return f"{value * 100:.{decimals}f}%"


def _fmt_num(value: float | int | str | None, decimals: int = 2) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, str):
        return value
    if isinstance(value, int):
        return str(value)
    return f"{value:.{decimals}f}"


def _render_metric_table(facts: tuple[MetricFact, ...], title: str) -> List[str]:
    lines: List[str] = []
    if not facts:
        return lines
    lines.append(f"### {title}")
    lines.append("")
    lines.append("| 指标 | 数值 | 状态 |")
    lines.append("|------|------|------|")
    for f in facts:
        val_str = _fmt_num(f.value) if f.value is not None else "N/A"
        unit = f.unit or ""
        display = f"{val_str}{unit}" if unit else val_str
        status_icon = {"available": "✓", "unavailable": "✗", "stale": "⚠", "derived": "→"}.get(f.status, "?")
        lines.append(f"| {f.name} | {display} | {status_icon} {f.status} |")
    lines.append("")
    return lines


def _render_agent_view(view: AgentView) -> List[str]:
    lines: List[str] = []
    if view.role == "alpha":
        role_label = "Alpha 趋势与机会分析师"
    elif view.role == "risk_evidence":
        role_label = "Risk & Evidence 风险与证据分析师"
    else:
        raise ValueError(f"unsupported AgentView role: {view.role}")
    lines.append(f"#### {role_label}")
    lines.append("")
    lines.append(f"- **判断**: {view.verdict}")
    lines.append(f"- **置信度**: {view.confidence}")
    if view.candidate_tickers:
        lines.append(f"- **关注股票**: {', '.join(view.candidate_tickers)}")
    if view.warnings:
        lines.append(f"- **风险提示**: {', '.join(view.warnings)}")
    if view.unknown_fields:
        lines.append(f"- **数据缺失字段**: {', '.join(view.unknown_fields)}")
    if view.summary:
        lines.append("")
        lines.append(view.summary)
    lines.append("")
    return lines


def generate_company_report(bundle: CompanyFactBundle) -> str:
    """Generate a complete per-company Markdown report from structured facts.

    Returns deterministic output — same facts always produce the same report.
    No LLM text generation, no hardcoded IC numbers.
    """
    lines: List[str] = []

    # ---- Header ----
    weight_str = _fmt_pct(bundle.portfolio_weight, decimals=2)
    lines.append(f"# {bundle.name} ({bundle.report_code}) 投资分析报告")
    lines.append("")
    lines.append(f"**板块**: {bundle.sector}")
    lines.append(f"**分析时点**: {bundle.as_of_time.strftime('%Y-%m-%d')}")
    lines.append(f"**持仓权重**: {weight_str}")
    lines.append(f"**入选组合**: {'是' if bundle.selected else '否'}")
    if not bundle.selected and bundle.weight_zero_reason:
        lines.append(f"**零持仓原因**: {bundle.weight_zero_reason}")
    lines.append(f"**数据状态**: {bundle.data_provider_status}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # ---- Investment Conclusion ----
    lines.append("## 1. 投资结论")
    lines.append("")
    if bundle.selected:
        lines.append(f"该股票入选当前投资组合，配置权重 {weight_str}。")
    else:
        lines.append(f"该股票未入选当前投资组合。（{bundle.weight_zero_reason}）")
    lines.append("")

    # ---- Technical / Quantitative ----
    lines.append("## 2. 技术/量化分析")
    lines.append("")
    lines.extend(_render_metric_table(bundle.technical_facts, "因子指标"))
    if not bundle.technical_facts:
        lines.append("*技术分析数据不可用*")
        lines.append("")

    # ---- Fundamental ----
    lines.append("## 3. 基本面分析")
    lines.append("")
    lines.extend(_render_metric_table(bundle.fundamental_facts, "财务指标"))
    if not bundle.fundamental_facts:
        lines.append("*基本面数据不可用*")
        lines.append("")

    # ---- Events / News ----
    lines.append("## 4. 公告/事件/新闻")
    lines.append("")
    lines.extend(_render_metric_table(bundle.event_facts, "近期事件"))
    if not bundle.event_facts:
        lines.append("*近期无重大事件或数据不可用*")
        lines.append("")

    # ---- Risk ----
    lines.append("## 5. 风险评估")
    lines.append("")
    lines.extend(_render_metric_table(bundle.risk_facts, "风险指标"))
    if not bundle.risk_facts:
        lines.append("*风险数据不可用*")
        lines.append("")

    # ---- Agent Views ----
    lines.append("## 6. Agent 分析视角")
    lines.append("")
    if bundle.agent_views:
        for view in bundle.agent_views:
            lines.extend(_render_agent_view(view))
    else:
        lines.append("*Agent 分析不可用*")
        lines.append("")

    # ---- Limitations ----
    lines.append("## 7. 局限性声明")
    lines.append("")
    lines.append("- 本报告基于分析时点之前可获取的数据生成，不包含未来信息。")
    lines.append("- 技术因子基于历史价格和成交量计算，不构成未来收益保证。")
    if bundle.data_provider_status != "complete":
        lines.append(f"- 数据覆盖状态为 '{bundle.data_provider_status}'，部分分析可能不完整。")
    if bundle.event_facts:
        lines.append("- 公告事实来自分析时点前可用的归档原文；基本面和新闻数据仍未接入。")
    else:
        lines.append("- 公告、基本面和新闻事实在当前分析时点不可用或尚未接入。")
    lines.append("")

    return "\n".join(lines)
