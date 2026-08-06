#!/usr/bin/env python3
"""Replay one accepted formal quant trace exactly 20 times without LLM/network."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from jiuwenswarm.quant.phase_state import (  # noqa: E402
    build_trace_receipt,
    canonical_json_bytes,
    canonical_sha256,
)
from jiuwenswarm.quant.reporting.snapshot_writer import (  # noqa: E402
    load_market_data_snapshot,
    verify_market_data_snapshot,
)

REQUIRED_REPLAY_RUNS = 20


def _read_hash_bound_json(path: Path, expected_sha256: str) -> dict[str, Any]:
    raw = path.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if actual != expected_sha256:
        raise ValueError(f"input SHA-256 mismatch for {path.name}")
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid JSON input: {path.name}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"JSON input must be an object: {path.name}")
    return value


def replay_quant_trace(
    *,
    summary_path: Path,
    summary_sha256: str,
    snapshot_manifest_path: Path,
    snapshot_manifest_sha256: str,
    runs: int = REQUIRED_REPLAY_RUNS,
) -> dict[str, Any]:
    """Verify immutable inputs and replay one complete trace exactly 20 times."""
    if runs != REQUIRED_REPLAY_RUNS:
        raise ValueError(f"offline replay requires exactly {REQUIRED_REPLAY_RUNS} runs")
    summary = _read_hash_bound_json(summary_path, summary_sha256)
    artifacts = load_market_data_snapshot(
        snapshot_manifest_path,
        expected_manifest_sha256=snapshot_manifest_sha256,
    )
    snapshot_manifest = verify_market_data_snapshot(artifacts)
    calls = summary.get("quant_rpc_calls")
    if not isinstance(calls, list):
        raise ValueError("formal summary has no quant_rpc_calls trace")
    accepted_trace = summary.get("deterministic_trace")
    rebuilt_live = build_trace_receipt(calls, mode="LIVE_TRACE")
    if accepted_trace != rebuilt_live:
        raise ValueError("formal summary deterministic trace binding mismatch")
    market_hash = rebuilt_live["market_content_sha256"]
    if snapshot_manifest.get("content_sha256") != market_hash:
        raise ValueError("trace belongs to a different market snapshot")

    replay_receipts = [
        build_trace_receipt(calls, mode="OFFLINE_REPLAY")
        for _index in range(runs)
    ]
    run_hashes = [receipt["trace_sha256"] for receipt in replay_receipts]
    if len(set(run_hashes)) != 1:
        raise RuntimeError("deterministic replay output drifted across runs")
    aggregate_payload = {
        "schema": "quant_phase_replay/v1",
        "mode": "OFFLINE_REPLAY",
        "runs": runs,
        "summary_sha256": summary_sha256,
        "snapshot_manifest_sha256": snapshot_manifest_sha256,
        "market_content_sha256": market_hash,
        "per_run_trace_sha256": run_hashes,
    }
    return {
        **aggregate_payload,
        "aggregate_sha256": canonical_sha256(aggregate_payload),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--summary-sha256", required=True)
    parser.add_argument("--snapshot-manifest", type=Path, required=True)
    parser.add_argument("--snapshot-manifest-sha256", required=True)
    parser.add_argument("--runs", type=int, default=REQUIRED_REPLAY_RUNS)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = replay_quant_trace(
        summary_path=args.summary,
        summary_sha256=args.summary_sha256,
        snapshot_manifest_path=args.snapshot_manifest,
        snapshot_manifest_sha256=args.snapshot_manifest_sha256,
        runs=args.runs,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("xb") as handle:
        handle.write(canonical_json_bytes(result) + b"\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
