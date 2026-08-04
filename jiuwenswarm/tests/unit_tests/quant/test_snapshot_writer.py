from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest
from jiuwenswarm.quant.market_data_service import (
    MarketDataBundle,
    ProviderEvidence,
    diagnose_market_data,
)
from jiuwenswarm.quant.reporting.snapshot_writer import (
    install_market_data_snapshot_in_candidate,
    install_snapshot_in_candidate,
    load_market_data_snapshot,
    load_snapshot_artifacts,
    verify_market_data_snapshot,
    verify_snapshot_artifacts,
    write_data_snapshot,
    write_market_data_snapshot,
)
from jiuwenswarm.quant.stock_pool import ALL_STOCKS


def _frames():
    index = pd.bdate_range("2026-01-01", periods=3)
    columns = ["000001.SZ", "600000.SH"]
    prices = pd.DataFrame([[10.0, 20.0], [10.2, 19.8], [10.3, 20.1]], index=index, columns=columns)
    volumes = pd.DataFrame([[100, 200], [110, 210], [120, 220]], index=index, columns=columns)
    return prices, volumes


def _market_bundle() -> MarketDataBundle:
    dates = pd.bdate_range("2025-01-02", periods=100)
    step = np.arange(len(dates), dtype=float)
    closes = pd.DataFrame(
        {
            ticker: (10.0 + index) * (1.0 + step * (0.0005 + index * 0.000001))
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
        name="sina",
        source_endpoint="https://example.invalid/sina",
        price_adjustment="raw_unadjusted",
        raw_volume_unit="shares",
        volume_multiplier_to_shares=1.0,
    )
    return MarketDataBundle(
        opens=closes * 0.999,
        highs=closes * 1.002,
        lows=closes * 0.998,
        closes=closes,
        volumes=pd.DataFrame(
            1_000_000.0,
            index=dates,
            columns=ALL_STOCKS,
        ),
        secondary_closes=closes.copy(),
        benchmark_closes=pd.Series(
            3000.0 + step,
            index=dates,
            name="CSI300:test",
        ),
        provider_ledger={ticker: "sina" for ticker in ALL_STOCKS},
        provider_stats={"sina": {"primary_covered": 49}},
        provider_evidence={"sina": evidence},
        calendar_id="SSE_SZSE_observed_sessions",
        adjustment_policy="raw_unadjusted",
        secondary_label="test_secondary",
        as_of_time=as_of,
        retrieved_at=as_of + timedelta(minutes=1),
    )


def test_snapshot_round_trip_and_candidate_install(tmp_path):
    prices, volumes = _frames()
    ledger = {"000001.SZ": "sina", "600000.SH": "tencent"}
    artifacts = write_data_snapshot(
        prices, volumes, ledger, {"sina": {"newly_covered": 1}}, tmp_path / "archive"
    )
    manifest = verify_snapshot_artifacts(artifacts)
    assert manifest["provider_ledger"] == ledger
    url, digest = install_snapshot_in_candidate(artifacts, tmp_path / "candidate")
    assert url == f"data_snapshot/{artifacts.manifest_path.name}"
    assert digest == artifacts.manifest_sha256
    copied = load_snapshot_artifacts(tmp_path / "candidate" / url)
    assert verify_snapshot_artifacts(copied)["content_sha256"] == manifest["content_sha256"]
    assert len(list((tmp_path / "candidate" / "data_snapshot").iterdir())) == 3


def test_snapshot_rejects_incomplete_ledger(tmp_path):
    prices, volumes = _frames()
    with pytest.raises(ValueError, match="ledger"):
        write_data_snapshot(prices, volumes, {"000001.SZ": "sina"}, {}, tmp_path)


def test_snapshot_detects_tampered_archive(tmp_path):
    prices, volumes = _frames()
    artifacts = write_data_snapshot(
        prices,
        volumes,
        {"000001.SZ": "sina", "600000.SH": "sina"},
        {},
        tmp_path,
    )
    artifacts.prices_path.write_bytes(artifacts.prices_path.read_bytes() + b"tampered")
    with pytest.raises(ValueError, match="prices archive"):
        verify_snapshot_artifacts(artifacts)


def test_manifest_hash_is_hash_of_manifest_file(tmp_path):
    prices, volumes = _frames()
    artifacts = write_data_snapshot(
        prices,
        volumes,
        {"000001.SZ": "sina", "600000.SH": "sina"},
        {},
        tmp_path,
    )
    assert len(artifacts.manifest_sha256) == 64
    assert json.loads(artifacts.manifest_path.read_text(encoding="utf-8"))["volumes_file"].endswith(
        "_volumes.csv.gz"
    )


def test_market_data_snapshot_round_trip_and_candidate_install(tmp_path):
    bundle = _market_bundle()
    diagnostics = diagnose_market_data(bundle, ALL_STOCKS)
    artifacts = write_market_data_snapshot(
        bundle,
        diagnostics,
        tmp_path / "archive",
    )

    manifest = verify_market_data_snapshot(artifacts)
    assert manifest["schema"] == "market_data_bundle/v1"
    assert manifest["n_stocks"] == 49
    assert manifest["calendar_id"] == bundle.calendar_id
    assert manifest["adjustment_policy"] == bundle.adjustment_policy
    assert manifest["provider_evidence"]["sina"]["raw_volume_unit"] == "shares"
    assert set(manifest["artifacts"]) == {
        "benchmark_closes",
        "closes",
        "diagnostics",
        "highs",
        "lows",
        "opens",
        "secondary_closes",
        "volumes",
    }

    url, digest = install_market_data_snapshot_in_candidate(
        artifacts,
        tmp_path / "candidate",
    )
    assert digest == artifacts.manifest_sha256
    copied = load_market_data_snapshot(
        tmp_path / "candidate" / url,
        expected_manifest_sha256=digest,
    )
    assert verify_market_data_snapshot(copied)["content_sha256"] == manifest[
        "content_sha256"
    ]
    assert len(list((tmp_path / "candidate" / "data_snapshot").iterdir())) == 9


@pytest.mark.parametrize(
    "artifact_name",
    [
        "opens",
        "highs",
        "lows",
        "closes",
        "volumes",
        "secondary_closes",
        "benchmark_closes",
        "diagnostics",
    ],
)
def test_market_data_snapshot_rejects_any_tampered_artifact(
    tmp_path,
    artifact_name: str,
):
    bundle = _market_bundle()
    artifacts = write_market_data_snapshot(
        bundle,
        diagnose_market_data(bundle, ALL_STOCKS),
        tmp_path,
    )
    target = artifacts.artifact_paths[artifact_name]
    target.write_bytes(target.read_bytes() + b"tampered")

    with pytest.raises(ValueError, match=artifact_name):
        verify_market_data_snapshot(artifacts)


def test_market_data_snapshot_rejects_tampered_manifest(tmp_path):
    bundle = _market_bundle()
    artifacts = write_market_data_snapshot(
        bundle,
        diagnose_market_data(bundle, ALL_STOCKS),
        tmp_path,
    )
    artifacts.manifest_path.write_bytes(
        artifacts.manifest_path.read_bytes() + b" "
    )

    with pytest.raises(ValueError, match="manifest SHA-256"):
        verify_market_data_snapshot(artifacts)


def test_market_data_snapshot_rejects_diagnostics_from_another_bundle(tmp_path):
    bundle = _market_bundle()
    altered = replace(
        bundle,
        retrieved_at=bundle.retrieved_at + timedelta(minutes=1),
    )
    stale_diagnostics = diagnose_market_data(altered, ALL_STOCKS)

    with pytest.raises(ValueError, match="diagnostics do not match"):
        write_market_data_snapshot(bundle, stale_diagnostics, tmp_path)


def test_market_data_snapshot_records_bounded_decision_evidence_policy(tmp_path):
    bundle = _market_bundle()
    decision_index = bundle.closes.index[60]
    decision_time = datetime.combine(
        decision_index.date(),
        time(16, 0),
        tzinfo=ZoneInfo("Asia/Shanghai"),
    )
    decision_bundle = replace(
        bundle,
        opens=bundle.opens.loc[:decision_index],
        highs=bundle.highs.loc[:decision_index],
        lows=bundle.lows.loc[:decision_index],
        closes=bundle.closes.loc[:decision_index],
        volumes=bundle.volumes.loc[:decision_index],
        secondary_closes=bundle.secondary_closes.loc[:decision_index],
        benchmark_closes=bundle.benchmark_closes.loc[:decision_index],
        as_of_time=decision_time,
    )
    diagnostics = diagnose_market_data(
        decision_bundle,
        ALL_STOCKS,
        minimum_rows=61,
    )

    artifacts = write_market_data_snapshot(
        decision_bundle,
        diagnostics,
        tmp_path,
        minimum_rows=61,
    )
    manifest = verify_market_data_snapshot(artifacts)

    assert manifest["n_trading_days"] == 61
    assert manifest["actual_end_date"].startswith(str(decision_index.date()))
    assert manifest["diagnostic_policy"] == {
        "minimum_rows": 61,
        "minimum_secondary_overlap_days": 20,
        "minimum_benchmark_rows": 60,
        "cross_source_tolerance_pct": 1.0,
    }


def test_market_data_snapshot_never_allows_sub_strategy_history(tmp_path):
    bundle = _market_bundle()

    with pytest.raises(ValueError, match="cannot be below 61"):
        write_market_data_snapshot(
            bundle,
            diagnose_market_data(bundle, ALL_STOCKS),
            tmp_path,
            minimum_rows=60,
        )


def test_market_data_snapshot_requires_exact_official_pool(tmp_path):
    bundle = _market_bundle()
    renamed = list(ALL_STOCKS)
    renamed[-1] = "999999.SH"
    wrong_pool = replace(
        bundle,
        opens=bundle.opens.set_axis(renamed, axis=1),
        highs=bundle.highs.set_axis(renamed, axis=1),
        lows=bundle.lows.set_axis(renamed, axis=1),
        closes=bundle.closes.set_axis(renamed, axis=1),
        volumes=bundle.volumes.set_axis(renamed, axis=1),
        secondary_closes=bundle.secondary_closes.set_axis(renamed, axis=1),
        provider_ledger={ticker: "sina" for ticker in renamed},
    )

    with pytest.raises(ValueError, match="official 49-ticker"):
        write_market_data_snapshot(
            wrong_pool,
            diagnose_market_data(bundle, ALL_STOCKS),
            tmp_path,
        )


def test_market_data_candidate_install_never_overwrites(tmp_path):
    bundle = _market_bundle()
    artifacts = write_market_data_snapshot(
        bundle,
        diagnose_market_data(bundle, ALL_STOCKS),
        tmp_path / "archive",
    )
    candidate = tmp_path / "candidate"
    install_market_data_snapshot_in_candidate(artifacts, candidate)

    with pytest.raises(FileExistsError, match="immutable candidate"):
        install_market_data_snapshot_in_candidate(artifacts, candidate)
