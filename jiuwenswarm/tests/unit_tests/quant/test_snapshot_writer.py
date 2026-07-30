from __future__ import annotations

import json

import pandas as pd
import pytest

from jiuwenswarm.quant.reporting.snapshot_writer import (
    install_snapshot_in_candidate,
    load_snapshot_artifacts,
    verify_snapshot_artifacts,
    write_data_snapshot,
)


def _frames():
    index = pd.bdate_range("2026-01-01", periods=3)
    columns = ["000001.SZ", "600000.SH"]
    prices = pd.DataFrame([[10.0, 20.0], [10.2, 19.8], [10.3, 20.1]], index=index, columns=columns)
    volumes = pd.DataFrame([[100, 200], [110, 210], [120, 220]], index=index, columns=columns)
    return prices, volumes


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
