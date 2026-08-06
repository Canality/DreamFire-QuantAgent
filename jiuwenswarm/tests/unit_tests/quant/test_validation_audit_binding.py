"""Fail-closed tests for validation-summary audit binding."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from jiuwenswarm.quant.market_data_service import (
    MarketDataBundle,
    ProviderEvidence,
    diagnose_market_data,
)
from jiuwenswarm.quant.reporting.snapshot_writer import write_market_data_snapshot
from jiuwenswarm.quant.reporting.candidate_binding import write_candidate_binding
from jiuwenswarm.quant.stock_pool import ALL_STOCKS

SCRIPT = (
    Path(__file__).resolve().parents[3]
    / "scripts"
    / "generate_validation_summary.py"
)
SPEC = importlib.util.spec_from_file_location("validation_summary_script", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

AUDIT_SCRIPT = (
    Path(__file__).resolve().parents[4]
    / ".agents"
    / "skills"
    / "verify-quant-e2e"
    / "scripts"
    / "audit_run_artifacts.py"
)
AUDIT_SPEC = importlib.util.spec_from_file_location("quant_e2e_audit_script", AUDIT_SCRIPT)
assert AUDIT_SPEC is not None and AUDIT_SPEC.loader is not None
AUDIT_MODULE = importlib.util.module_from_spec(AUDIT_SPEC)
AUDIT_SPEC.loader.exec_module(AUDIT_MODULE)


def _write(path: Path, payload: dict | str) -> None:
    if isinstance(payload, str):
        path.write_text(payload, encoding="utf-8")
    else:
        path.write_text(json.dumps(payload), encoding="utf-8")


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _candidate_fixture(tmp_path: Path, candidate_id: str = "direct-test") -> dict:
    candidate = tmp_path / "submission_candidates" / candidate_id
    (candidate / "company_reports").mkdir(parents=True)
    (candidate / "data_snapshot").mkdir()
    _write(
        candidate / "report_manifest.json",
        {
            "candidate_id": candidate_id,
            "quality_metrics": {"report_grade_disclosure": 1},
        },
    )
    _write(
        candidate / "evidence_manifest.json",
        {
            "evidence_refs": {
                "snap-1": {"source_type": "market_data"},
                "ann-1": {"source_type": "disclosure"},
            }
        },
    )
    _write(candidate / "portfolio_meta.json", {"as_of_time": "2025-01-01T16:00:00+08:00"})
    _write(candidate / "Portfolio.json", {"600000": 0.1})
    _write(candidate / "portfolio_report.md", "portfolio")
    _write(candidate / "company_reports" / "600000.md", "report")
    _write(candidate / "data_snapshot" / "snap-1_manifest.json", {"snapshot_id": "snap-1"})
    binding = write_candidate_binding(candidate)
    return {
        "path": str(candidate.resolve()),
        "candidate_id": candidate_id,
        "immutable": True,
        "snapshot_id": "snap-1",
        "snapshot_manifest_sha256": binding["snapshot_manifest_sha256"],
        "announcement_facts": 1,
        "disclosure_reports": 1,
        "artifact_binding": binding,
    }


def _fixture(tmp_path: Path) -> tuple[Path, Path, dict]:
    session_id = "multi-agent-validation-20260731-150000"
    artifact_id = "20260731-150000"
    pipeline = tmp_path / "pipeline_results_20260731_145900.json"
    summary = tmp_path / f"multi_agent_summary_{artifact_id}.json"
    chunks = tmp_path / f"multi_agent_chunks_{artifact_id}.json"
    direct_log = tmp_path / "direct.log"
    multi_log = tmp_path / "multi.log"
    direct_binding = {"binding_sha256": "a" * 64}
    formal_binding = {"binding_sha256": "b" * 64}
    _write(
        pipeline,
        {
            "snapshot_id": "snap-1",
            "candidate_package": {"artifact_binding": direct_binding},
        },
    )
    _write(
        summary,
        {
            "session_id": session_id,
            "candidate_package": {"artifact_binding": formal_binding},
        },
    )
    _write(chunks, [])
    _write(direct_log, "direct")
    _write(multi_log, "formal")
    paths = {
        "results": pipeline,
        "direct_log": direct_log,
        "multi_chunks": chunks,
        "multi_log": multi_log,
        "multi_summary": summary,
    }
    audit = {
        "passed": True,
        "session_id": session_id,
        "direct_snapshot_id": "snap-1",
        "artifact_paths": {key: str(value.resolve()) for key, value in paths.items()},
        "artifact_sha256": {key: _digest(value) for key, value in paths.items()},
        "candidate_bindings": {
            "direct": direct_binding,
            "formal": formal_binding,
        },
    }
    return pipeline, summary, audit


def test_exact_artifact_binding_passes(tmp_path: Path) -> None:
    pipeline, summary, audit = _fixture(tmp_path)

    assert MODULE._validate_audit_binding(pipeline, summary, audit) == (
        True,
        None,
    )


def test_cross_snapshot_binding_fails(tmp_path: Path) -> None:
    pipeline, summary, audit = _fixture(tmp_path)
    audit["direct_snapshot_id"] = "snap-other"

    valid, reason = MODULE._validate_audit_binding(pipeline, summary, audit)

    assert valid is False
    assert reason == "direct snapshot mismatch"


def test_direct_business_pass_requires_bound_audit() -> None:
    portfolio = [
        {
            "ticker": f"{index:06d}.SH",
            "weight": 0.05,
            "sector": f"sector-{index % 6}",
        }
        for index in range(15)
    ]
    pipeline = {
        "n_stocks_fetched": 49,
        "n_sectors_covered": 6,
        "n_stocks_selected": 15,
        "portfolio": portfolio,
        "backtest": {"total_return": 0.01},
    }

    assert MODULE._status_section(pipeline, None, None)[
        "quant_core_and_market_data"
    ] == "NOT_TESTED"
    assert MODULE._status_section(pipeline, None, True)[
        "quant_core_and_market_data"
    ] == "BUSINESS_PASSED"


def test_readme_projection_detects_any_dynamic_field_drift() -> None:
    summary = MODULE._build_summary(None, None, None, "no bound run")
    readme = (
        "prefix\n"
        + MODULE.render_readme_summary_block(summary)
        + "\nsuffix\n"
    )
    assert MODULE.readme_summary_matches(readme, summary)

    drifted = json.loads(json.dumps(summary))
    drifted["status"]["multi_agent_path"] = "BUSINESS_PASSED"
    assert not MODULE.readme_summary_matches(readme, drifted)


def test_checked_in_readme_matches_absent_local_run_evidence() -> None:
    readme_path = Path(__file__).resolve().parents[4] / "README.md"
    readme = readme_path.read_text(encoding="utf-8")
    assert MODULE.readme_summary_matches(readme, None)


def test_unaudited_artifacts_cannot_render_business_passed() -> None:
    portfolio = [
        {
            "ticker": f"{index:06d}.SH",
            "weight": 0.05,
            "sector": f"sector-{index % 6}",
        }
        for index in range(15)
    ]
    pipeline = {
        "n_stocks_fetched": 49,
        "n_sectors_covered": 6,
        "n_stocks_selected": 15,
        "portfolio": portfolio,
        "backtest": {"total_return": 0.01},
    }
    multi = {
        "session_id": "multi-agent-validation-unbound",
        "validation_passed": True,
        "quant_phases": {str(index): True for index in range(8)},
        "resource_usage": {"total_input_tokens": 123},
    }
    summary = MODULE._build_summary(pipeline, multi, None, "audit missing")

    assert summary["status"]["quant_core_and_market_data"] == "NOT_TESTED"
    assert summary["status"]["multi_agent_path"] == "NOT_TESTED"
    assert summary["status"]["report_candidate"] == "NOT_TESTED"
    assert "BUSINESS_PASSED" not in MODULE.render_readme_summary_block(summary)


def test_readme_projection_rejects_missing_or_duplicate_markers() -> None:
    summary = MODULE._build_summary(None, None, None)
    assert not MODULE.readme_summary_matches("no markers", summary)
    duplicated = (
        MODULE.render_readme_summary_block(summary)
        + "\n"
        + MODULE.render_readme_summary_block(summary)
    )
    assert not MODULE.readme_summary_matches(duplicated, summary)


def test_replaced_direct_result_fails_hash_binding(tmp_path: Path) -> None:
    pipeline, summary, audit = _fixture(tmp_path)
    _write(pipeline, {"snapshot_id": "snap-1", "changed": True})

    valid, reason = MODULE._validate_audit_binding(pipeline, summary, audit)

    assert valid is False
    assert reason == "audit artifact hash mismatch: results"


def test_cross_formal_session_fails(tmp_path: Path) -> None:
    pipeline, summary, audit = _fixture(tmp_path)
    _write(summary, {"session_id": "multi-agent-validation-other"})

    valid, reason = MODULE._validate_audit_binding(pipeline, summary, audit)

    assert valid is False
    assert reason == "formal session mismatch"


def test_missing_artifact_hash_fails(tmp_path: Path) -> None:
    pipeline, summary, audit = _fixture(tmp_path)
    audit["artifact_sha256"].pop("multi_log")

    valid, reason = MODULE._validate_audit_binding(pipeline, summary, audit)

    assert valid is False
    assert reason == "audit artifact paths/hashes are incomplete"


def test_bound_candidate_rejects_mutable_or_tampered_artifact(
    tmp_path: Path,
    monkeypatch,
) -> None:
    candidate = _candidate_fixture(tmp_path)
    monkeypatch.setattr(
        AUDIT_MODULE,
        "audit_candidate_evidence",
        lambda *_args, **_kwargs: None,
    )
    failures: list[str] = []
    resolved = AUDIT_MODULE.audit_bound_candidate(
        "direct",
        candidate,
        tmp_path,
        failures,
        expected_snapshot_id="snap-1",
        expected_announcement_facts=1,
        expected_disclosure_reports=1,
        require_formal_resources=False,
    )
    assert resolved == Path(candidate["path"])
    assert failures == []

    Path(candidate["path"], "company_reports", "600000.md").write_text(
        "later formal overwrite",
        encoding="utf-8",
    )
    failures = []
    AUDIT_MODULE.audit_bound_candidate(
        "direct",
        candidate,
        tmp_path,
        failures,
        expected_snapshot_id="snap-1",
        expected_announcement_facts=1,
        expected_disclosure_reports=1,
        require_formal_resources=False,
    )
    assert any("binding mismatch" in failure for failure in failures)

    mutable = dict(candidate, path=str(tmp_path / "submission_candidate"))
    failures = []
    assert AUDIT_MODULE.audit_bound_candidate(
        "direct",
        mutable,
        tmp_path,
        failures,
        expected_snapshot_id="snap-1",
        require_formal_resources=False,
    ) is None
    assert failures == [
        "direct: candidate path is not a direct child of submission_candidates"
    ]


def test_e2e_audit_accepts_and_verifies_nine_file_market_snapshot(tmp_path: Path) -> None:
    dates = pd.bdate_range("2025-01-02", periods=61)
    step = np.arange(len(dates), dtype=float)
    closes = pd.DataFrame(
        {
            ticker: (10.0 + index) * (1.0 + step * 0.0005)
            for index, ticker in enumerate(ALL_STOCKS)
        },
        index=dates,
    )
    as_of = datetime.combine(
        dates[-1].date(),
        time(16, 0),
        tzinfo=ZoneInfo("Asia/Shanghai"),
    )
    evidence = ProviderEvidence(
        name="test",
        source_endpoint="https://example.invalid/test",
        price_adjustment="raw_unadjusted",
        raw_volume_unit="shares",
        volume_multiplier_to_shares=1.0,
    )
    bundle = MarketDataBundle(
        opens=closes * 0.999,
        highs=closes * 1.002,
        lows=closes * 0.998,
        closes=closes,
        volumes=pd.DataFrame(1_000_000.0, index=dates, columns=ALL_STOCKS),
        secondary_closes=closes.copy(),
        benchmark_closes=pd.Series(3000.0 + step, index=dates, name="CSI300"),
        provider_ledger={ticker: "test" for ticker in ALL_STOCKS},
        provider_stats={"test": {"primary_covered": 49}},
        provider_evidence={"test": evidence},
        calendar_id="SSE_SZSE_observed_sessions",
        adjustment_policy="raw_unadjusted",
        secondary_label="independent_test",
        as_of_time=as_of,
        retrieved_at=as_of + timedelta(minutes=1),
    )
    diagnostics = diagnose_market_data(bundle, ALL_STOCKS, minimum_rows=61)
    artifacts = write_market_data_snapshot(
        bundle,
        diagnostics,
        tmp_path / "data_snapshot",
        minimum_rows=61,
    )

    failures: list[str] = []
    result = AUDIT_MODULE.audit_market_snapshot(
        tmp_path / "data_snapshot",
        failures,
    )

    assert result is not None
    assert result[0]["snapshot_id"] == artifacts.snapshot_id
    assert failures == []
