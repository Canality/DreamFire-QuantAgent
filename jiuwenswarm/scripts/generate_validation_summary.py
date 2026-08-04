#!/usr/bin/env python3
"""Generate validation_summary.json from actual run artifacts.

Reads the latest pipeline_results_*.json and multi_agent_summary_*.json from
output/, extracts a machine-readable summary, and writes it to
output/validation_summary.json.

This is the single source for README and Skill dynamic numbers — no human
should copy/paste session IDs, token counts, or performance numbers by hand.
"""

from __future__ import annotations

import json
import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path


def _find_latest(glob_pattern: str, output_dir: Path) -> Path | None:
    """Return the most recently modified file matching *glob*."""
    candidates = sorted(output_dir.glob(glob_pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def _load_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validate_audit_binding(
    pipeline_path: Path,
    multi_path: Path,
    audit_data: dict,
) -> tuple[bool, str | None]:
    """Verify that an audit belongs to these exact direct/formal artifacts."""
    pipeline = _load_json(pipeline_path)
    multi = _load_json(multi_path)
    session_id = multi.get("session_id")
    if audit_data.get("session_id") != session_id:
        return False, "formal session mismatch"
    if audit_data.get("direct_snapshot_id") != pipeline.get("snapshot_id"):
        return False, "direct snapshot mismatch"

    artifact_paths = audit_data.get("artifact_paths", {})
    artifact_hashes = audit_data.get("artifact_sha256", {})
    required = {
        "results",
        "direct_log",
        "multi_chunks",
        "multi_log",
        "multi_summary",
    }
    if not required.issubset(artifact_paths) or not required.issubset(artifact_hashes):
        return False, "audit artifact paths/hashes are incomplete"

    if Path(artifact_paths["results"]).resolve() != pipeline_path.resolve():
        return False, "audit results path does not match selected direct result"
    if Path(artifact_paths["multi_summary"]).resolve() != multi_path.resolve():
        return False, "audit summary path does not match selected formal result"

    artifact_id = str(session_id).removeprefix("multi-agent-validation-")
    expected_chunks = multi_path.parent / f"multi_agent_chunks_{artifact_id}.json"
    if Path(artifact_paths["multi_chunks"]).resolve() != expected_chunks.resolve():
        return False, "audit chunks path does not match selected formal session"

    for label in required:
        path = Path(artifact_paths[label])
        if not path.is_file():
            return False, f"audit artifact is missing: {label}"
        if _sha256_file(path) != artifact_hashes[label]:
            return False, f"audit artifact hash mismatch: {label}"
    direct_binding = (
        (pipeline.get("candidate_package") or {}).get("artifact_binding")
    )
    formal_binding = (
        (multi.get("candidate_package") or {}).get("artifact_binding")
    )
    audited_bindings = audit_data.get("candidate_bindings") or {}
    if not isinstance(direct_binding, dict) or not isinstance(formal_binding, dict):
        return False, "run candidate bindings are incomplete"
    if audited_bindings.get("direct") != direct_binding:
        return False, "direct candidate binding mismatch"
    if audited_bindings.get("formal") != formal_binding:
        return False, "formal candidate binding mismatch"
    return True, None


def _build_summary(
    pipeline: dict | None,
    multi: dict | None,
    audit_passed: bool | None = None,
    audit_note: str | None = None,
) -> dict:
    summary: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generator_version": "1.0.0",
        "direct": _direct_section(pipeline),
        "formal": _formal_section(multi),
        "contract": _contract_section(),
        "status": _status_section(pipeline, multi, audit_passed),
        "audit_status": {
            "passed": audit_passed,
            "note": audit_note or (
                "None=not run; BUSINESS_PASSED requires audit_passed=True"
            ),
        },
    }
    return summary


def _direct_section(pipeline: dict | None) -> dict | None:
    if pipeline is None:
        return None
    bt = pipeline.get("backtest", {})
    return {
        "snapshot_id": pipeline.get("snapshot_id"),
        "regime": pipeline.get("regime"),
        "train_period": pipeline.get("train_period"),
        "test_period": pipeline.get("test_period"),
        "n_train_trading_days": pipeline.get("n_train_trading_days"),
        "n_forward_returns": pipeline.get("n_forward_returns"),
        "n_stocks_fetched": pipeline.get("n_stocks_fetched"),
        "n_stocks_selected": pipeline.get("n_stocks_selected"),
        "n_sectors_covered": pipeline.get("n_sectors_covered"),
        "equity_weight": round(sum(h["weight"] for h in pipeline.get("portfolio", [])), 4),
        "cash_weight": round(1.0 - sum(h["weight"] for h in pipeline.get("portfolio", [])), 4),
        "sector_weights": pipeline.get("sector_weights"),
        "announcement_evidence": pipeline.get("announcement_evidence"),
        "candidate_package": pipeline.get("candidate_package"),
        "total_return": bt.get("total_return"),
        "max_drawdown": bt.get("max_drawdown"),
        "backtest": {
            "total_return": bt.get("total_return"),
            "max_drawdown": bt.get("max_drawdown"),
            "sharpe_ratio": bt.get("sharpe_ratio"),
            "win_rate": bt.get("win_rate"),
            "n_trading_days": bt.get("n_trading_days"),
        },
    }


def _formal_section(multi: dict | None) -> dict | None:
    if multi is None:
        return None
    res = multi.get("resource_usage", {})
    phases = multi.get("quant_phases", {})
    report_payloads = [
        call.get("payload", {})
        for call in multi.get("quant_rpc_calls", [])
        if call.get("method") == "quant.generate_report"
        and call.get("payload", {}).get("success") is True
    ]
    candidate_package = multi.get("candidate_package") or (
        report_payloads[-1].get("candidate_package", {}) if report_payloads else {}
    )
    return {
        "session_id": multi.get("session_id"),
        "elapsed_seconds": multi.get("elapsed_seconds"),
        "rpc_status": "8/8" if all(phases.values()) else f"{sum(1 for v in phases.values() if v)}/8",
        "phases": phases,
        "agent_participation": multi.get("agent_participation"),
        "role_rpc_calls": multi.get("role_rpc_calls"),
        "role_rpc_violations": multi.get("role_rpc_violations"),
        "phase_request_counts": multi.get("phase_request_counts"),
        "phase_execution_counts": multi.get("phase_execution_counts"),
        "phase_cache_hit_counts": multi.get("phase_cache_hit_counts"),
        "report_candidate": {
            "quality_passed": candidate_package.get("quality_passed"),
            "n_reports": candidate_package.get("n_reports"),
            "snapshot_id": candidate_package.get("snapshot_id"),
            "announcement_facts": candidate_package.get("announcement_facts"),
            "announcement_tickers": candidate_package.get(
                "announcement_tickers"
            ),
            "evidence_count": candidate_package.get("evidence_count"),
            "path": candidate_package.get("path"),
            "immutable": candidate_package.get("immutable"),
            "disclosure_reports": candidate_package.get("disclosure_reports"),
            "artifact_binding": candidate_package.get("artifact_binding"),
        },
        "multi_agent_working": multi.get("multi_agent_working"),
        "resource_usage": {
            "input_tokens": res.get("total_input_tokens"),
            "output_tokens": res.get("total_output_tokens"),
            "cache_tokens": res.get("total_cache_tokens"),
            "tool_calls": res.get("total_tool_calls"),
            "peak_memory_mb": res.get("peak_memory_mb"),
            "cpu_time_seconds": res.get("total_cpu_time_seconds"),
            "max_concurrency": res.get("max_concurrency"),
        },
        "role_breakdown": {
            role: {
                "input_tokens": v.get("input_tokens"),
                "output_tokens": v.get("output_tokens"),
                "tool_calls": v.get("tool_calls"),
            }
            for role, v in res.get("role_breakdown", {}).items()
        },
    }


def _contract_section() -> dict:
    try:
        from jiuwenswarm.quant.reporting.submission_contract import get_contract

        c = get_contract()
        ok, reason = c.can_proceed_formal()
        return {
            "n_companies": c.n_companies,
            "n_sectors": c.n_sectors,
            "status": c.contract_status,
            "source_verified": c.source_verified,
            "can_proceed_formal": ok,
            "formal_blocker": reason if not ok else None,
        }
    except Exception as exc:
        return {"error": str(exc)}


def _status_section(pipeline: dict | None, multi: dict | None, audit_passed: bool | None) -> dict:
    def _multi_status() -> str:
        if multi is None:
            return "EVIDENCE_MISSING"
        if not multi.get("validation_passed"):
            return "FAILED"
        # BUSINESS_PASSED requires independent audit confirmation
        if audit_passed is True:
            return "BUSINESS_PASSED"
        if audit_passed is False:
            return "FAILED"
        return "NOT_TESTED"

    def _direct_status() -> str:
        if pipeline is None:
            return "EVIDENCE_MISSING"
        bt = pipeline.get("backtest", {})
        portfolio = pipeline.get("portfolio", [])
        equity_weight = sum(float(row.get("weight", 0.0)) for row in portfolio)
        single_stock_ok = all(
            float(row.get("weight", 0.0)) <= 0.10 + 1e-9
            for row in portfolio
        )
        sector_weights: dict[str, float] = {}
        for row in portfolio:
            sector = str(row.get("sector", ""))
            sector_weights[sector] = (
                sector_weights.get(sector, 0.0)
                + float(row.get("weight", 0.0))
            )
        if (pipeline.get("n_stocks_fetched") == 49
                and pipeline.get("n_sectors_covered") == 6
                and pipeline.get("n_stocks_selected") == 15
                and len(portfolio) == 15
                and single_stock_ok
                and all(weight <= 0.25 + 1e-9 for weight in sector_weights.values())
                and equity_weight <= 0.95 + 1e-9
                and 1.0 - equity_weight >= 0.05 - 1e-9
                and bt.get("total_return") is not None):
            if audit_passed is True:
                return "BUSINESS_PASSED"
            if audit_passed is False:
                return "FAILED"
            return "NOT_TESTED"
        return "FAILED"

    statuses = {
        "quant_core_and_market_data": _direct_status(),
        "multi_agent_path": _multi_status(),
        "report_candidate": _multi_status(),
        "full_financial_analysis": "PARTIAL",
        "submission_contract": "PROVISIONAL",
        "strategy_alpha": "RESEARCH_ONLY",
    }

    return statuses


def main() -> int:
    project_root = Path(__file__).resolve().parents[2]  # scripts/ → jiuwenswarm/ → Track_2/
    output_dir = project_root / "output"

    if not output_dir.is_dir():
        print(f"ERROR: output directory not found: {output_dir}", file=sys.stderr)
        return 1

    pipeline_path = _find_latest("pipeline_results_*.json", output_dir)
    multi_path = _find_latest("multi_agent_summary_*.json", output_dir)

    pipeline = _load_json(pipeline_path) if pipeline_path else None
    multi = _load_json(multi_path) if multi_path else None

    # Precision-match audit: must match multi session_id, not just "latest file"
    audit_passed: bool | None = None
    audit_note: str | None = None
    if multi and pipeline_path is not None and multi_path is not None:
        session_id = multi.get("session_id", "")
        if session_id:
            audit_candidate = output_dir / f"audit_result_{session_id}.json"
            if audit_candidate.exists():
                try:
                    audit_data = _load_json(audit_candidate)
                    binding_ok, binding_error = _validate_audit_binding(
                        pipeline_path,
                        multi_path,
                        audit_data,
                    )
                    if binding_ok:
                        audit_passed = audit_data.get("passed")
                        audit_note = "audit artifacts and hashes matched"
                    else:
                        audit_passed = False
                        audit_note = binding_error
                except Exception as exc:
                    audit_passed = False
                    audit_note = f"audit binding validation failed: {exc}"
            else:
                audit_note = "matching audit JSON is missing"
    elif multi:
        audit_note = "direct or formal source artifact is missing"

    summary = _build_summary(pipeline, multi, audit_passed, audit_note)

    # Add source file info
    summary["_sources"] = {
        "pipeline_results": str(pipeline_path) if pipeline_path else None,
        "multi_agent_summary": str(multi_path) if multi_path else None,
    }

    out_path = output_dir / "validation_summary.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print(f"validation_summary.json written to {out_path}")
    print(f"  Direct:  {'present' if pipeline else 'MISSING'}")
    print(f"  Formal:  {'present' if multi else 'MISSING'}")
    if pipeline:
        print(f"  Snapshot: {pipeline.get('snapshot_id', '?')}")
    if multi:
        print(f"  Session:  {multi.get('session_id', '?')}")
        print(f"  Tokens:   {multi.get('resource_usage', {}).get('total_input_tokens', '?')}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
