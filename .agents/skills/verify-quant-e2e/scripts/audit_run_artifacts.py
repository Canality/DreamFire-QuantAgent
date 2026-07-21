#!/usr/bin/env python3
"""Fail-closed audit for quant pipeline and multi-agent run artifacts."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path


REQUIRED_MULTI_TOOLS = (
    "quant_fetch_data",
    "quant_compute_factors",
    "quant_bull_view",
    "quant_bear_view",
    "quant_select_stocks",
    "quant_allocate_positions",
    "quant_run_backtest",
    "quant_generate_report",
)


def load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--direct-log", type=Path, required=True)
    parser.add_argument("--multi-log", type=Path, required=True)
    args = parser.parse_args()

    failures: list[str] = []
    results = json.loads(load_text(args.results))
    direct_log = load_text(args.direct_log)
    multi_log = load_text(args.multi_log)

    if "Done." not in direct_log or "Results saved to" not in direct_log:
        failures.append("direct: run did not complete and save a fresh result")

    coverage_matches = re.findall(r"\b(\d+) stocks,\s*(\d+) days\b", direct_log)
    if not coverage_matches:
        failures.append("direct: cannot prove stock/day coverage from log")
    else:
        n_stocks, n_days = map(int, coverage_matches[-1])
        if n_stocks != 49:
            failures.append(f"direct: expected 49 stocks, got {n_stocks}")
        if n_days < 60:
            failures.append(f"direct: insufficient history, got {n_days} days")

    selection = re.search(r"\b(\d+) stocks from (\d+) sectors\b", direct_log)
    portfolio = results.get("portfolio") or []
    if selection:
        selected_n, selected_sectors = map(int, selection.groups())
        if selected_n != len(portfolio):
            failures.append(
                f"direct: selection has {selected_n} stocks but portfolio has {len(portfolio)}"
            )
        if selected_sectors != 6:
            failures.append(f"direct: expected 6 selected sectors, got {selected_sectors}")
    else:
        failures.append("direct: cannot prove selection count and sector coverage")

    sector_weights: dict[str, float] = defaultdict(float)
    total_weight = 0.0
    for row in portfolio:
        ticker = row.get("ticker", "<unknown>")
        weight = float(row.get("weight", 0.0))
        total_weight += weight
        sector_weights[str(row.get("sector", "<unknown>"))] += weight
        if weight > 0.10001:
            failures.append(f"direct: {ticker} weight {weight:.2%} exceeds 10%")

    if total_weight > 0.9501:
        failures.append(f"direct: total weight {total_weight:.2%} leaves less than 5% cash")
    for sector, weight in sector_weights.items():
        if weight > 0.2501:
            failures.append(f"direct: sector {sector} weight {weight:.2%} exceeds 25%")
    if len(sector_weights) != 6:
        failures.append(f"direct: portfolio covers {len(sector_weights)} sectors, expected 6")

    tool_counts = {
        tool: len(re.findall(rf"Executing tool: {re.escape(tool)}\b", multi_log))
        for tool in REQUIRED_MULTI_TOOLS
    }
    for tool, count in tool_counts.items():
        if count == 0:
            failures.append(f"multi: missing traversal evidence for {tool}")
    if tool_counts["quant_fetch_data"] > 3:
        failures.append(f"multi: quant_fetch_data repeated {tool_counts['quant_fetch_data']} times")
    if re.search(r"Executing tool: quant_compute_factors with args: \{\"prices\"", multi_log):
        failures.append("multi: raw price matrix passed through LLM instead of Extension cache")

    if failures:
        print("E2E AUDIT: FAILED")
        for item in failures:
            print(f"- {item}")
        return 1

    print("E2E AUDIT: PASSED")
    print(f"- portfolio: {len(portfolio)} stocks, {len(sector_weights)} sectors")
    print(f"- total weight: {total_weight:.2%}")
    print("- multi-agent tools: " + ", ".join(REQUIRED_MULTI_TOOLS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
