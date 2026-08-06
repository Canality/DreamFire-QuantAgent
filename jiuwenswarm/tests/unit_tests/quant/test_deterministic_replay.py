"""Deterministic formal phase-state and 20-run offline replay tests."""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

from evaluation.replay_quant_trace import main as replay_main
from evaluation.replay_quant_trace import replay_quant_trace
from jiuwenswarm.quant.market_data_service import (
    MarketDataBundle,
    ProviderEvidence,
    diagnose_market_data,
    require_diagnostics_passed,
)
from jiuwenswarm.quant.phase_state import (
    QUANT_PHASE_SEQUENCE,
    build_trace_receipt,
    validate_quant_rpc_calls,
)
from jiuwenswarm.quant.reporting.snapshot_writer import write_market_data_snapshot
from jiuwenswarm.quant.stock_pool import ALL_STOCKS


def _bound(payload: dict, market_hash: str) -> dict:
    return {
        **payload,
        "market_content_sha256": market_hash,
        "cached": False,
        "executed": True,
    }


def _valid_calls(market_hash: str) -> list[dict]:
    tickers = list(ALL_STOCKS)
    candidate_id = "formal-replay-fixture"
    binding = {
        "schema": "candidate_artifact_binding/v1",
        "candidate_id": candidate_id,
        "snapshot_id": "snapshot-fixture",
        "report_count": 49,
        "announcement_facts": 1,
        "disclosure_reports": 1,
        "snapshot_manifest_sha256": "1" * 64,
        "report_manifest_sha256": "2" * 64,
        "evidence_manifest_sha256": "3" * 64,
        "company_reports_tree_sha256": "4" * 64,
        "binding_sha256": "5" * 64,
        "candidate_binding_file_sha256": "6" * 64,
    }
    payloads = (
        _bound({
            "success": True,
            "coverage_complete": True,
            "n_stocks": 49,
            "expected_stocks": 49,
        }, market_hash),
        _bound({
            "success": True,
            "n_stocks_analyzed": 49,
            "all_composite": {ticker: float(index) for index, ticker in enumerate(tickers)},
        }, market_hash),
        _bound({
            "success": True,
            "verdict": "overweight",
            "candidate_tickers": tickers[:12],
            "evidence_ids": ["factor-snapshot"],
        }, market_hash),
        _bound({
            "success": True,
            "verdict": "underweight",
            "candidate_tickers": tickers[-12:],
            "evidence_ids": ["factor-snapshot"],
        }, market_hash),
        _bound({
            "success": True,
            "n_selected": 15,
            "n_sectors_covered": 6,
        }, market_hash),
        _bound({
            "success": True,
            "n_holdings": 15,
            "cash_reserve": 0.10,
            "portfolio": [
                {"ticker": ticker, "sector": f"sector-{index}", "weight": 0.06}
                for index, ticker in enumerate(tickers[:15])
            ],
        }, market_hash),
        _bound({"success": True, "n_forward_returns": 20}, market_hash),
        _bound({
            "success": True,
            "report": "fixture report",
            "summary": {"n_holdings": 15},
            "candidate_package": {
                "path": f"/fixture/submission_candidates/{candidate_id}",
                "candidate_id": candidate_id,
                "immutable": True,
                "quality_passed": True,
                "n_reports": 49,
                "snapshot_id": "snapshot-fixture",
                "announcement_facts": 1,
                "disclosure_reports": 1,
                "artifact_binding": binding,
            },
        }, market_hash),
    )
    return [
        {
            "method": method,
            "params_keys": [],
            "payload": payload,
            "timestamp": f"2026-08-06T00:00:0{index}+00:00",
        }
        for index, ((_phase, method), payload) in enumerate(
            zip(QUANT_PHASE_SEQUENCE, payloads, strict=True)
        )
    ]


def _snapshot_bundle() -> MarketDataBundle:
    dates = pd.bdate_range("2025-01-02", periods=80)
    closes = pd.DataFrame(
        {
            ticker: np.linspace(10.0 + index, 12.0 + index, len(dates))
            + np.sin(np.arange(len(dates)) / 9 + index) * 0.05
            for index, ticker in enumerate(ALL_STOCKS)
        },
        index=dates,
    )
    volumes = pd.DataFrame(
        {
            ticker: 1_000_000 + index * 1_000 + np.arange(len(dates))
            for index, ticker in enumerate(ALL_STOCKS)
        },
        index=dates,
    )
    as_of = datetime.combine(
        dates[-1].date(), time(16, 0), tzinfo=ZoneInfo("Asia/Shanghai")
    )
    evidence = ProviderEvidence(
        name="fixture",
        source_endpoint="https://example.invalid/fixture",
        price_adjustment="raw_unadjusted",
        raw_volume_unit="shares",
        volume_multiplier_to_shares=1.0,
    )
    return MarketDataBundle(
        opens=closes * 0.999,
        highs=closes * 1.002,
        lows=closes * 0.998,
        closes=closes,
        volumes=volumes,
        secondary_closes=closes.copy(),
        benchmark_closes=pd.Series(
            np.linspace(3000.0, 3100.0, len(dates)),
            index=dates,
            name="CSI300:fixture",
        ),
        provider_ledger={ticker: "fixture" for ticker in ALL_STOCKS},
        provider_stats={"fixture": {"covered": 49}},
        provider_evidence={"fixture": evidence},
        calendar_id="SSE_SZSE_observed_sessions",
        adjustment_policy="raw_unadjusted",
        secondary_label="independent_fixture",
        as_of_time=as_of,
        retrieved_at=as_of + timedelta(minutes=1),
    )


def test_exact_trace_rejects_missing_duplicate_reorder_and_stale_hash() -> None:
    market_hash = "a" * 64
    calls = _valid_calls(market_hash)
    accepted = validate_quant_rpc_calls(calls, require_complete=True)
    assert accepted.complete is True
    assert accepted.issues == ()
    assert len(accepted.event_hashes) == 8

    with pytest.raises(ValueError, match="incomplete"):
        build_trace_receipt(calls[:-1])
    duplicate = [calls[0], *calls]
    assert validate_quant_rpc_calls(duplicate, require_complete=True).issues
    reordered = list(calls)
    reordered[2], reordered[3] = reordered[3], reordered[2]
    assert "expected quant.alpha_view" in validate_quant_rpc_calls(
        reordered, require_complete=True
    ).issues[0]
    stale = json.loads(json.dumps(calls))
    stale[5]["payload"]["market_content_sha256"] = "b" * 64
    assert "stale or different" in validate_quant_rpc_calls(
        stale, require_complete=True
    ).issues[0]


def test_trace_hash_excludes_wall_clock_timestamp_but_binds_payload() -> None:
    calls = _valid_calls("c" * 64)
    first = build_trace_receipt(calls)
    for call in calls:
        call["timestamp"] = "2099-01-01T00:00:00+00:00"
    assert build_trace_receipt(calls) == first
    calls[1]["payload"]["all_composite"][ALL_STOCKS[0]] = -999.0
    assert build_trace_receipt(calls)["trace_sha256"] != first["trace_sha256"]


def test_real_fixture_replays_exactly_twenty_times_without_runtime_imports(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = _snapshot_bundle()
    diagnostics = require_diagnostics_passed(
        diagnose_market_data(bundle, list(ALL_STOCKS), minimum_rows=61)
    )
    snapshot = write_market_data_snapshot(
        bundle,
        diagnostics,
        tmp_path / "snapshot",
        snapshot_id="market-replay-fixture",
        minimum_rows=61,
    )
    manifest = json.loads(snapshot.manifest_path.read_text(encoding="utf-8"))
    calls = _valid_calls(manifest["content_sha256"])
    summary = {
        "quant_rpc_calls": calls,
        "deterministic_trace": build_trace_receipt(calls),
    }
    summary_path = tmp_path / "formal-summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    summary_hash = hashlib.sha256(summary_path.read_bytes()).hexdigest()

    replay = replay_quant_trace(
        summary_path=summary_path,
        summary_sha256=summary_hash,
        snapshot_manifest_path=snapshot.manifest_path,
        snapshot_manifest_sha256=snapshot.manifest_sha256,
        runs=20,
    )
    assert replay["mode"] == "OFFLINE_REPLAY"
    assert replay["runs"] == 20
    assert len(replay["per_run_trace_sha256"]) == 20
    assert len(set(replay["per_run_trace_sha256"])) == 1
    assert len(replay["aggregate_sha256"]) == 64

    cli_output = tmp_path / "replay.json"
    monkeypatch.setattr(sys, "argv", [
        "replay_quant_trace.py",
        "--summary", str(summary_path),
        "--summary-sha256", summary_hash,
        "--snapshot-manifest", str(snapshot.manifest_path),
        "--snapshot-manifest-sha256", snapshot.manifest_sha256,
        "--runs", "20",
        "--output", str(cli_output),
    ])
    assert replay_main() == 0
    cli_payload = json.loads(cli_output.read_text(encoding="utf-8"))
    assert cli_payload["aggregate_sha256"] == replay["aggregate_sha256"]

    with pytest.raises(ValueError, match="exactly 20"):
        replay_quant_trace(
            summary_path=summary_path,
            summary_sha256=summary_hash,
            snapshot_manifest_path=snapshot.manifest_path,
            snapshot_manifest_sha256=snapshot.manifest_sha256,
            runs=19,
        )
    with pytest.raises(ValueError, match="input SHA-256 mismatch"):
        replay_quant_trace(
            summary_path=summary_path,
            summary_sha256="0" * 64,
            snapshot_manifest_path=snapshot.manifest_path,
            snapshot_manifest_sha256=snapshot.manifest_sha256,
        )
    source = (Path(__file__).resolve().parents[3] / "evaluation" / "replay_quant_trace.py")
    source_text = source.read_text(encoding="utf-8").lower()
    assert "openjiuwen" not in source_text
    assert "requests" not in source_text
