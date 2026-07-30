#!/usr/bin/env python3
"""Fail-closed audit for quant pipeline and multi-agent run artifacts."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PROJECT_ROOT / "jiuwenswarm"))

from jiuwenswarm.quant.reporting.submission_contract import get_contract

SUBMISSION_CONTRACT = get_contract()
EXPECTED_STOCKS = SUBMISSION_CONTRACT.n_companies
EXPECTED_SECTORS = SUBMISSION_CONTRACT.n_sectors

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
    raw = path.read_bytes()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16", errors="replace")
    if raw[:200].count(b"\x00") > 20:
        return raw.decode("utf-16-le", errors="replace")
    return raw.decode("utf-8", errors="replace")


def canonical_member_name(member: object) -> str:
    """Normalize equivalent runtime aliases while preserving exact role checks."""
    normalized = str(member or "").strip().lower().replace("-", "_")
    aliases = {
        "quant_leader": "quant-leader",
        "bull_analyst": "bull_analyst",
        "bear_analyst": "bear_analyst",
    }
    return aliases.get(normalized, normalized)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def audit_candidate_evidence(candidate: Path, failures: list[str]) -> None:
    report_codes = {
        path.stem
        for path in (candidate / "company_reports").glob("*.md")
    }
    report_ok, report_issues = SUBMISSION_CONTRACT.validate_report_set(report_codes)
    if not report_ok:
        failures.extend(f"candidate: {issue}" for issue in report_issues)

    resource_json = candidate / "resource_usage.json"
    resource_md = candidate / "resource_usage.md"
    if not resource_json.is_file() or not resource_md.is_file():
        failures.append("candidate: formal resource usage JSON/Markdown is missing")
    else:
        try:
            resource = json.loads(load_text(resource_json))
            if float(resource.get("total_duration_seconds") or 0) <= 0:
                failures.append("candidate: resource duration is not measured")
            if int(resource.get("total_input_tokens") or 0) <= 0:
                failures.append("candidate: input token usage is not measured")
            if int(resource.get("total_output_tokens") or 0) <= 0:
                failures.append("candidate: output token usage is not measured")
            if int(resource.get("total_tool_calls") or 0) < len(REQUIRED_MULTI_TOOLS):
                failures.append("candidate: resource tool-call count is incomplete")
            roles = resource.get("role_breakdown", {})
            if set(roles) != {"quant-leader", "bull_analyst", "bear_analyst"}:
                failures.append("candidate: resource role breakdown is incomplete")
            for role, metrics in roles.items():
                if int(metrics.get("input_tokens") or 0) <= 0:
                    failures.append(f"candidate: {role} input tokens are not measured")
        except Exception as exc:
            failures.append(f"candidate: resource usage verification failed: {exc}")

    snapshot_dir = candidate / "data_snapshot"
    manifests = list(snapshot_dir.glob("*_manifest.json")) if snapshot_dir.is_dir() else []
    prices_files = list(snapshot_dir.glob("*_prices.csv.gz")) if snapshot_dir.is_dir() else []
    volumes_files = list(snapshot_dir.glob("*_volumes.csv.gz")) if snapshot_dir.is_dir() else []
    if (len(manifests), len(prices_files), len(volumes_files)) != (1, 1, 1):
        failures.append(
            "candidate: expected exactly one manifest/prices/volumes snapshot, got "
            f"{len(manifests)}/{len(prices_files)}/{len(volumes_files)}"
        )
        return
    try:
        manifest_path = manifests[0]
        manifest = json.loads(load_text(manifest_path))
        prices_path = snapshot_dir / manifest["prices_file"]
        volumes_path = snapshot_dir / manifest["volumes_file"]
        prices_gzip = prices_path.read_bytes()
        volumes_gzip = volumes_path.read_bytes()
        prices_raw = gzip.decompress(prices_gzip)
        volumes_raw = gzip.decompress(volumes_gzip)
        checks = {
            "prices_file_sha256": sha256_bytes(prices_gzip),
            "volumes_file_sha256": sha256_bytes(volumes_gzip),
            "prices_content_sha256": sha256_bytes(prices_raw),
            "volumes_content_sha256": sha256_bytes(volumes_raw),
            "content_sha256": sha256_bytes(
                prices_raw + b"\n--VOLUMES--\n" + volumes_raw
            ),
        }
        for field, actual in checks.items():
            if manifest.get(field) != actual:
                failures.append(f"candidate: snapshot {field} mismatch")
        if set(manifest.get("provider_ledger", {})) != set(manifest.get("stock_codes", [])):
            failures.append("candidate: provider ledger does not cover stock codes exactly")

        evidence = json.loads(load_text(candidate / "evidence_manifest.json"))
        refs = evidence.get("evidence_refs", {})
        if set(refs) != {manifest["snapshot_id"]}:
            failures.append("candidate: evidence IDs do not identify the sole snapshot")
        else:
            ref = refs[manifest["snapshot_id"]]
            relative = Path(str(ref.get("source_url", "")))
            referenced = (candidate / relative).resolve()
            if candidate.resolve() not in referenced.parents:
                failures.append("candidate: EvidenceRef escapes candidate root")
            elif referenced != manifest_path.resolve():
                failures.append("candidate: EvidenceRef URL does not point to snapshot manifest")
            elif ref.get("content_sha256") != sha256_bytes(manifest_path.read_bytes()):
                failures.append("candidate: EvidenceRef hash does not match snapshot manifest")
    except Exception as exc:
        failures.append(f"candidate: snapshot evidence verification failed: {exc}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--direct-log", type=Path, required=True)
    parser.add_argument(
        "--multi-log",
        type=Path,
        help="Optional raw formal-run log; tool traversal is audited from chunks.",
    )
    parser.add_argument("--multi-chunks", type=Path, required=True)
    args = parser.parse_args()

    failures: list[str] = []
    results = json.loads(load_text(args.results))
    direct_log = load_text(args.direct_log)
    multi_log = load_text(args.multi_log) if args.multi_log else ""
    multi_chunks = json.loads(load_text(args.multi_chunks))
    audit_candidate_evidence(args.results.parent / "submission_candidate", failures)

    if "Done." not in direct_log or "Results saved to" not in direct_log:
        failures.append("direct: run did not complete and save a fresh result")

    coverage_matches = re.findall(r"\b(\d+) stocks,\s*(\d+) days\b", direct_log)
    if not coverage_matches:
        failures.append("direct: cannot prove stock/day coverage from log")
    else:
        n_stocks, n_days = map(int, coverage_matches[-1])
        if n_stocks != EXPECTED_STOCKS:
            failures.append(
                f"direct: expected {EXPECTED_STOCKS} stocks, got {n_stocks}"
            )
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
        if selected_sectors != EXPECTED_SECTORS:
            failures.append(
                f"direct: expected {EXPECTED_SECTORS} selected sectors, "
                f"got {selected_sectors}"
            )
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
    if len(sector_weights) != EXPECTED_SECTORS:
        failures.append(
            f"direct: portfolio covers {len(sector_weights)} sectors, "
            f"expected {EXPECTED_SECTORS}"
        )

    chunk_tool_calls = [
        chunk.get("payload", {}).get("tool_call", {})
        for chunk in multi_chunks
        if chunk.get("type") == "tool_call"
    ]
    tool_counts = {
        tool: sum(call.get("name") == tool for call in chunk_tool_calls)
        for tool in REQUIRED_MULTI_TOOLS
    }
    for tool, count in tool_counts.items():
        if count == 0:
            failures.append(f"multi: missing traversal evidence for {tool}")
    if tool_counts["quant_fetch_data"] > 3:
        failures.append(f"multi: quant_fetch_data repeated {tool_counts['quant_fetch_data']} times")
    factor_args = [
        str(call.get("arguments", ""))
        for call in chunk_tool_calls
        if call.get("name") == "quant_compute_factors"
    ]
    raw_prices_via_chunks = any(
        re.search(r'["\']prices["\']\s*:', arguments)
        for arguments in factor_args
    )
    raw_prices_via_log = bool(
        multi_log
        and re.search(
            r"Executing tool: quant_compute_factors with args: \{\"prices\"",
            multi_log,
        )
    )
    if raw_prices_via_chunks or raw_prices_via_log:
        failures.append("multi: raw price matrix passed through LLM instead of Extension cache")

    member_counts = {"quant-leader": 0, "bull_analyst": 0, "bear_analyst": 0}
    role_rpc_counts = {"bull_analyst": 0, "bear_analyst": 0}
    expected_role_rpc = {
        "bull_analyst": "quant_bull_view",
        "bear_analyst": "quant_bear_view",
    }
    forbidden_role_calls: list[str] = []
    for chunk in multi_chunks:
        member = canonical_member_name(chunk.get("source_member"))
        if member in member_counts:
            member_counts[member] += 1
        if member in expected_role_rpc and chunk.get("type") == "tool_call":
            tool_name = (
                chunk.get("payload", {})
                .get("tool_call", {})
                .get("name")
            )
            if tool_name == expected_role_rpc[member]:
                role_rpc_counts[member] += 1
            elif str(tool_name or "").startswith("quant_"):
                forbidden_role_calls.append(f"{member}:{tool_name}")
    if member_counts["quant-leader"] == 0:
        failures.append("multi: quant-leader produced no stream events")
    for member, count in role_rpc_counts.items():
        if count == 0:
            failures.append(
                f"multi: {member} did not call {expected_role_rpc[member]}; "
                "creation or leader-owned calls are not delegation"
            )
    if forbidden_role_calls:
        failures.append(
            "multi: analyst role boundary violated: " + ", ".join(forbidden_role_calls)
        )

    if failures:
        print("E2E AUDIT: FAILED")
        for item in failures:
            print(f"- {item}")
        return 1

    print("E2E AUDIT: PASSED")
    print(f"- portfolio: {len(portfolio)} stocks, {len(sector_weights)} sectors")
    print(f"- total weight: {total_weight:.2%}")
    print("- multi-agent tools: " + ", ".join(REQUIRED_MULTI_TOOLS))
    print("- member events: " + ", ".join(f"{k}={v}" for k, v in member_counts.items()))
    print("- role-owned RPCs: " + ", ".join(f"{k}={v}" for k, v in role_rpc_counts.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
