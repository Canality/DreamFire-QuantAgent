#!/usr/bin/env python3
"""Fail-closed audit for quant pipeline and multi-agent run artifacts."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import importlib
import json
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PROJECT_ROOT / "jiuwenswarm"))

get_contract = importlib.import_module(
    "jiuwenswarm.quant.reporting.submission_contract"
).get_contract

SUBMISSION_CONTRACT = get_contract()
EXPECTED_STOCKS = SUBMISSION_CONTRACT.n_companies
EXPECTED_SECTORS = SUBMISSION_CONTRACT.n_sectors

REQUIRED_MULTI_TOOLS = (
    "quant_fetch_data",
    "quant_compute_factors",
    "quant_alpha_view",
    "quant_risk_evidence_view",
    "quant_select_stocks",
    "quant_allocate_positions",
    "quant_run_backtest",
    "quant_generate_report",
)
MARKET_ARTIFACT_NAMES = {
    "opens",
    "highs",
    "lows",
    "closes",
    "volumes",
    "secondary_closes",
    "benchmark_closes",
    "diagnostics",
}


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
        "alpha_analyst": "alpha_analyst",
        "risk_evidence_analyst": "risk_evidence_analyst",
    }
    return aliases.get(normalized, normalized)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def audit_market_snapshot(
    snapshot_dir: Path,
    failures: list[str],
) -> tuple[dict, Path] | None:
    """Verify either the current nine-file bundle or one legacy snapshot."""

    manifests = list(snapshot_dir.glob("*_manifest.json")) if snapshot_dir.is_dir() else []
    if len(manifests) != 1:
        failures.append(
            f"candidate: expected exactly one snapshot manifest, got {len(manifests)}"
        )
        return None
    manifest_path = manifests[0]
    manifest = json.loads(load_text(manifest_path))
    if manifest.get("schema") == "market_data_bundle/v1":
        recorded = manifest.get("artifacts", {})
        if set(recorded) != MARKET_ARTIFACT_NAMES:
            failures.append("candidate: market-data artifact set does not match schema")
            return None
        if len(list(snapshot_dir.iterdir())) != len(MARKET_ARTIFACT_NAMES) + 1:
            failures.append("candidate: market-data snapshot must contain exactly nine files")
        raw_artifacts: dict[str, bytes] = {}
        for name in sorted(MARKET_ARTIFACT_NAMES):
            entry = recorded[name]
            artifact_path = snapshot_dir / str(entry.get("file", ""))
            try:
                archived = artifact_path.read_bytes()
                if sha256_bytes(archived) != entry.get("file_sha256"):
                    failures.append(f"candidate: snapshot {name} file SHA-256 mismatch")
                raw = archived if name == "diagnostics" else gzip.decompress(archived)
                if sha256_bytes(raw) != entry.get("content_sha256"):
                    failures.append(f"candidate: snapshot {name} content SHA-256 mismatch")
                raw_artifacts[name] = raw
            except Exception as exc:  # noqa: BLE001 - artifact failure is reported
                failures.append(f"candidate: snapshot {name} verification failed: {exc}")
        if set(raw_artifacts) == MARKET_ARTIFACT_NAMES:
            combined = b"".join(
                name.encode("utf-8") + b"\0" + raw_artifacts[name] + b"\0"
                for name in sorted(raw_artifacts)
            )
            if sha256_bytes(combined) != manifest.get("content_sha256"):
                failures.append("candidate: combined market-data content SHA-256 mismatch")
        if manifest.get("diagnostics_passed") is not True:
            failures.append("candidate: market-data diagnostics are not passed")
        policy = manifest.get("diagnostic_policy", {})
        if int(policy.get("minimum_rows") or 0) < 61:
            failures.append("candidate: market-data diagnostic policy is below 61 rows")
        if int(manifest.get("n_trading_days") or 0) < int(
            policy.get("minimum_rows") or 0
        ):
            failures.append("candidate: snapshot history is shorter than its policy")
    else:
        prices_files = list(snapshot_dir.glob("*_prices.csv.gz"))
        volumes_files = list(snapshot_dir.glob("*_volumes.csv.gz"))
        if (len(prices_files), len(volumes_files)) != (1, 1):
            failures.append(
                "candidate: expected one legacy prices/volumes snapshot, got "
                f"{len(prices_files)}/{len(volumes_files)}"
            )
            return None
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

    if set(manifest.get("provider_ledger", {})) != set(
        manifest.get("stock_codes", [])
    ):
        failures.append("candidate: provider ledger does not cover stock codes exactly")
    return manifest, manifest_path


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
            if set(roles) != {"quant-leader", "alpha_analyst", "risk_evidence_analyst"}:
                failures.append("candidate: resource role breakdown is incomplete")
            for role, metrics in roles.items():
                if int(metrics.get("input_tokens") or 0) <= 0:
                    failures.append(f"candidate: {role} input tokens are not measured")
        except Exception as exc:  # noqa: BLE001 - malformed resource data is reported
            failures.append(f"candidate: resource usage verification failed: {exc}")

    try:
        snapshot_result = audit_market_snapshot(candidate / "data_snapshot", failures)
        if snapshot_result is None:
            return
        manifest, manifest_path = snapshot_result

        evidence = json.loads(load_text(candidate / "evidence_manifest.json"))
        refs = evidence.get("evidence_refs", {})
        snapshot_id = manifest["snapshot_id"]
        if snapshot_id not in refs:
            failures.append("candidate: snapshot EvidenceRef is missing")
        else:
            ref = refs[snapshot_id]
            relative = Path(str(ref.get("source_url", "")))
            referenced = (candidate / relative).resolve()
            if candidate.resolve() not in referenced.parents:
                failures.append("candidate: EvidenceRef escapes candidate root")
            elif referenced != manifest_path.resolve():
                failures.append("candidate: EvidenceRef URL does not point to snapshot manifest")
            elif ref.get("content_sha256") != sha256_bytes(manifest_path.read_bytes()):
                failures.append("candidate: EvidenceRef hash does not match snapshot manifest")

        portfolio_meta = json.loads(load_text(candidate / "portfolio_meta.json"))
        decision_time = datetime.fromisoformat(portfolio_meta["as_of_time"])
        archive_root = candidate / "evidence_archive"
        for evidence_id, ref in refs.items():
            if evidence_id == snapshot_id:
                continue
            if ref.get("evidence_id") != evidence_id:
                failures.append(
                    f"candidate: EvidenceRef key/id mismatch for {evidence_id}"
                )
                continue
            source_url = str(ref.get("source_url") or "")
            if not source_url.startswith(("https://", "http://")):
                failures.append(
                    f"candidate: external evidence has invalid source URL: {evidence_id}"
                )
            digest = str(ref.get("content_sha256") or "")
            if not re.fullmatch(r"[0-9a-f]{64}", digest):
                failures.append(
                    f"candidate: external evidence has invalid SHA-256: {evidence_id}"
                )
                continue
            available_raw = ref.get("available_at")
            if not available_raw:
                failures.append(
                    f"candidate: external evidence has no available_at: {evidence_id}"
                )
            elif datetime.fromisoformat(available_raw) > decision_time:
                failures.append(
                    f"candidate: future evidence referenced: {evidence_id}"
                )
            if not re.fullmatch(r"[a-zA-Z0-9_.-]+", evidence_id) or ".." in evidence_id:
                failures.append(
                    f"candidate: unsafe evidence ID: {evidence_id}"
                )
                continue
            archive_path = archive_root / evidence_id[:2] / f"{evidence_id}.json"
            if not archive_path.is_file():
                failures.append(
                    f"candidate: archived evidence is missing: {evidence_id}"
                )
            elif sha256_bytes(archive_path.read_bytes()) != digest:
                failures.append(
                    f"candidate: archived evidence hash mismatch: {evidence_id}"
                )

        report_manifest = json.loads(load_text(candidate / "report_manifest.json"))
        quality_metrics = report_manifest.get("quality_metrics", {})
        if int(report_manifest.get("evidence_count") or 0) <= 1:
            failures.append("candidate: announcement evidence was not integrated")
        if int(quality_metrics.get("report_grade_disclosure") or 0) <= 0:
            failures.append("candidate: disclosure facts were not integrated")
    except Exception as exc:  # noqa: BLE001 - malformed candidate is reported
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
    summary_path = _multi_summary_path(args.multi_chunks)
    multi_summary = (
        json.loads(load_text(summary_path))
        if summary_path is not None and summary_path.is_file()
        else {}
    )

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

    member_counts = {"quant-leader": 0, "alpha_analyst": 0, "risk_evidence_analyst": 0}
    role_rpc_counts = {"alpha_analyst": 0, "risk_evidence_analyst": 0}
    expected_role_rpc = {
        "alpha_analyst": "quant_alpha_view",
        "risk_evidence_analyst": "quant_risk_evidence_view",
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

    execution_counts = multi_summary.get("phase_execution_counts", {})
    if set(execution_counts) != {
        "fetch", "factors", "alpha_view", "risk_evidence_view",
        "select", "allocate", "backtest", "report",
    }:
        failures.append("multi: business execution counts are missing or incomplete")
    else:
        invalid_counts = {
            phase: count
            for phase, count in execution_counts.items()
            if count != 1
        }
        if invalid_counts:
            failures.append(
                f"multi: business execution count must be exactly one: {invalid_counts}"
            )

    passed = len(failures) == 0

    # Write machine-readable audit result for summary generator
    _write_audit_json(
        passed=passed,
        failures=failures,
        portfolio_n=len(portfolio),
        sector_n=len(sector_weights),
        total_weight=total_weight,
        member_counts=member_counts,
        role_rpc_counts=role_rpc_counts,
        multi_chunks_path=args.multi_chunks,
        results_path=args.results,
        direct_log_path=args.direct_log,
        multi_log_path=args.multi_log,
        multi_summary_path=summary_path,
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


def _write_audit_json(
    passed: bool,
    failures: list[str],
    portfolio_n: int,
    sector_n: int,
    total_weight: float,
    member_counts: dict,
    role_rpc_counts: dict,
    multi_chunks_path: str,
    results_path: str,
    direct_log_path: str,
    multi_log_path: str | None,
    multi_summary_path: Path | None,
) -> None:
    """Write audit_result_<session>.json for consumption by summary generator."""
    session_id = "unknown"
    # Try to extract session_id from the multi summary JSON (full name)
    chunks_dir = Path(multi_chunks_path).parent
    chunks_stem = Path(multi_chunks_path).stem
    if chunks_stem.startswith("multi_agent_chunks_"):
        candidate_session = chunks_stem[len("multi_agent_chunks_"):]
        summary_path = chunks_dir / f"multi_agent_summary_{candidate_session}.json"
        if summary_path.exists():
            try:
                with open(summary_path, encoding="utf-8") as f:
                    summary_data = json.load(f)
                session_id = summary_data.get("session_id", session_id)
            except Exception:  # noqa: BLE001 - session remains explicit unknown
                session_id = "unknown"

    results_data = json.loads(load_text(Path(results_path)))
    audit_data = {
        "passed": passed,
        "session_id": session_id,
        "direct_snapshot_id": results_data.get("snapshot_id"),
        "failures": failures,
        "portfolio": {"n_stocks": portfolio_n, "n_sectors": sector_n, "total_weight": round(total_weight, 6)},
        "members": dict(member_counts),
        "role_rpc_counts": dict(role_rpc_counts),
        "tools_verified": list(REQUIRED_MULTI_TOOLS),
    }
    artifact_paths = {
        "results": Path(results_path),
        "direct_log": Path(direct_log_path),
        "multi_chunks": Path(multi_chunks_path),
    }
    if multi_log_path is not None:
        artifact_paths["multi_log"] = Path(multi_log_path)
    if multi_summary_path is not None:
        artifact_paths["multi_summary"] = Path(multi_summary_path)
    audit_data["artifact_paths"] = {
        label: str(path.resolve())
        for label, path in artifact_paths.items()
    }
    audit_data["artifact_sha256"] = {}
    for label, path in artifact_paths.items():
        try:
            digest = sha256_bytes(path.read_bytes())
            audit_data["artifact_sha256"][label] = digest
            audit_data[f"{label}_sha256"] = digest
        except Exception:  # noqa: BLE001 - missing hash is recorded as null
            audit_data["artifact_sha256"][label] = None
            audit_data[f"{label}_sha256"] = None

    out_path = Path(results_path).parent / f"audit_result_{session_id}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(audit_data, f, indent=2, ensure_ascii=False)
    print(f"Audit JSON written to {out_path}")


def _multi_summary_path(multi_chunks_path: Path) -> Path | None:
    chunks_stem = multi_chunks_path.stem
    if not chunks_stem.startswith("multi_agent_chunks_"):
        return None
    artifact_id = chunks_stem[len("multi_agent_chunks_"):]
    return multi_chunks_path.parent / f"multi_agent_summary_{artifact_id}.json"


if __name__ == "__main__":
    sys.exit(main())
