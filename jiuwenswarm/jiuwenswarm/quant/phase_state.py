"""Pure deterministic state and hashing for the eight formal quant stages."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence


QUANT_PHASE_SEQUENCE = (
    ("fetch", "quant.fetch_data"),
    ("factors", "quant.compute_factors"),
    ("alpha_view", "quant.alpha_view"),
    ("risk_evidence_view", "quant.risk_evidence_view"),
    ("select", "quant.select_stocks"),
    ("allocate", "quant.allocate_positions"),
    ("backtest", "quant.run_backtest"),
    ("report", "quant.generate_report"),
)
QUANT_PHASE_METHODS = dict(QUANT_PHASE_SEQUENCE)
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")


def _json_safe(value: object) -> object:
    """Recursively normalize JSON-safe values for deterministic serialization.

    ``json.dumps`` only accepts plain ``dict``/``list``/scalars. Non-dict
    ``Mapping`` views such as ``types.MappingProxyType`` pass the ``Mapping``
    type check but are not serializable, so normalize them to dict without
    changing the bytes of already-serializable inputs.
    """
    if isinstance(value, Mapping) and not isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    return value


def canonical_json_bytes(value: object) -> bytes:
    """Serialize one JSON value identically across platforms and fail closed."""
    _validate_json_value(value)
    normalized = _json_safe(value)
    return json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _validate_json_value(value: object) -> None:
    if value is None or isinstance(value, str | bool | int):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite values are forbidden in phase traces")
        return
    if isinstance(value, list | tuple):
        for item in value:
            _validate_json_value(item)
        return
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise ValueError("phase trace object keys must be strings")
        for item in value.values():
            _validate_json_value(item)
        return
    raise ValueError(f"phase trace value is not JSON-safe: {type(value).__name__}")


def _is_hash(value: object) -> bool:
    return isinstance(value, str) and _HASH_RE.fullmatch(value) is not None


def validate_phase_payload(
    phase: str,
    payload: object,
    *,
    expected_stocks: int = 49,
    expected_sectors: int = 6,
) -> bool:
    """Validate the server result needed to advance one formal stage."""
    if not isinstance(payload, dict) or payload.get("success") is not True:
        return False
    if payload.get("executed") is not True or payload.get("cached") is not False:
        return False
    if not _is_hash(payload.get("market_content_sha256")):
        return False
    if phase == "fetch":
        return (
            payload.get("coverage_complete") is True
            and payload.get("n_stocks") == expected_stocks
            and payload.get("expected_stocks") == expected_stocks
        )
    if phase == "factors":
        return (
            payload.get("n_stocks_analyzed") == expected_stocks
            and isinstance(payload.get("all_composite"), dict)
            and len(payload.get("all_composite", {})) == expected_stocks
        )
    if phase == "alpha_view":
        return (
            payload.get("verdict") in {"overweight", "neutral", "underweight"}
            and isinstance(payload.get("candidate_tickers"), list)
            and isinstance(payload.get("evidence_ids"), list)
        )
    if phase == "risk_evidence_view":
        return (
            payload.get("verdict") in {"overweight", "neutral", "underweight"}
            and isinstance(payload.get("candidate_tickers"), list)
            and isinstance(payload.get("evidence_ids"), list)
        )
    if phase == "select":
        return (
            payload.get("n_selected") == 15
            and payload.get("n_sectors_covered") == expected_sectors
        )
    if phase == "allocate":
        portfolio = payload.get("portfolio", [])
        if not isinstance(portfolio, list):
            return False
        sector_totals: dict[object, float] = {}
        try:
            for holding in portfolio:
                weight = float(holding.get("weight", 0.0))
                if (
                    not math.isfinite(weight)
                    or weight <= 0.0
                    or weight > 0.10 + 1e-9
                ):
                    return False
                sector = holding.get("sector")
                if not isinstance(sector, str) or not sector:
                    return False
                sector_totals[sector] = sector_totals.get(sector, 0.0) + weight
            cash = float(payload.get("cash_reserve", 0.0))
        except (AttributeError, TypeError, ValueError):
            return False
        return (
            payload.get("n_holdings") == 15
            and len(portfolio) == 15
            and math.isfinite(cash)
            and cash >= 0.05 - 1e-9
            and cash <= 1.0 + 1e-9
            and all(weight <= 0.25 + 1e-9 for weight in sector_totals.values())
        )
    if phase == "backtest":
        return payload.get("n_forward_returns") == 20
    if phase == "report":
        summary = payload.get("summary", {})
        candidate = payload.get("candidate_package")
        if (
            not payload.get("report")
            or not isinstance(summary, dict)
            or summary.get("n_holdings") != 15
            or not isinstance(candidate, dict)
            or candidate.get("error")
            or candidate.get("quality_passed") is not True
        ):
            return False
        binding = candidate.get("artifact_binding")
        if not isinstance(binding, dict):
            return False
        candidate_id = candidate.get("candidate_id")
        if (
            not isinstance(candidate_id, str)
            or not candidate_id
            or candidate_id in {".", ".."}
            or "/" in candidate_id
            or "\\" in candidate_id
        ):
            return False
        candidate_path = str(candidate.get("path") or "").replace("\\", "/")
        candidate_parts = [part for part in candidate_path.split("/") if part]
        hash_fields = (
            "snapshot_manifest_sha256",
            "report_manifest_sha256",
            "evidence_manifest_sha256",
            "company_reports_tree_sha256",
            "binding_sha256",
            "candidate_binding_file_sha256",
        )
        return (
            candidate.get("n_reports") == expected_stocks
            and candidate.get("immutable") is True
            and len(candidate_parts) >= 2
            and candidate_parts[-2] == "submission_candidates"
            and candidate_parts[-1] == candidate_id
            and binding.get("schema") == "candidate_artifact_binding/v1"
            and binding.get("candidate_id") == candidate_id
            and binding.get("snapshot_id") == candidate.get("snapshot_id")
            and binding.get("report_count") == expected_stocks
            and binding.get("announcement_facts")
            == candidate.get("announcement_facts")
            and binding.get("disclosure_reports")
            == candidate.get("disclosure_reports")
            and all(_is_hash(binding.get(field)) for field in hash_fields)
        )
    return False


@dataclass(frozen=True)
class TraceValidation:
    phases: Mapping[str, bool]
    issues: tuple[str, ...]
    complete: bool
    market_content_sha256: str | None
    event_hashes: tuple[str, ...]


def validate_quant_rpc_calls(
    calls: Sequence[Mapping[str, Any]],
    *,
    expected_stocks: int = 49,
    expected_sectors: int = 6,
    require_complete: bool = False,
) -> TraceValidation:
    """Validate exact order, exactly-once execution, payloads and one epoch."""
    phases = {phase: False for phase, _method in QUANT_PHASE_SEQUENCE}
    issues: list[str] = []
    event_hashes: list[str] = []
    market_hash: str | None = None
    if len(calls) > len(QUANT_PHASE_SEQUENCE):
        issues.append(
            f"quant RPC count exceeds {len(QUANT_PHASE_SEQUENCE)}: {len(calls)}"
        )
    for index, call in enumerate(calls[: len(QUANT_PHASE_SEQUENCE)]):
        phase, expected_method = QUANT_PHASE_SEQUENCE[index]
        method = call.get("method")
        if method != expected_method:
            issues.append(
                f"stage {index} expected {expected_method}, got {method or '?'}"
            )
            break
        payload = call.get("payload")
        if not validate_phase_payload(
            phase,
            payload,
            expected_stocks=expected_stocks,
            expected_sectors=expected_sectors,
        ):
            issues.append(f"{expected_method} returned an invalid stage payload")
            break
        assert isinstance(payload, dict)
        payload_market_hash = str(payload["market_content_sha256"])
        if market_hash is None:
            market_hash = payload_market_hash
        elif payload_market_hash != market_hash:
            issues.append(
                f"{expected_method} belongs to a stale or different market snapshot"
            )
            break
        event = {
            "index": index,
            "phase": phase,
            "method": expected_method,
            "market_content_sha256": payload_market_hash,
            "params_keys": sorted(call.get("params_keys") or []),
            "payload_sha256": canonical_sha256(payload),
        }
        event_hashes.append(canonical_sha256(event))
        phases[phase] = True
    complete = (
        not issues
        and len(calls) == len(QUANT_PHASE_SEQUENCE)
        and all(phases.values())
    )
    if require_complete and not complete and not issues:
        issues.append(
            f"quant RPC trace is incomplete: {len(calls)}/{len(QUANT_PHASE_SEQUENCE)}"
        )
    return TraceValidation(
        phases=phases,
        issues=tuple(issues),
        complete=complete,
        market_content_sha256=market_hash,
        event_hashes=tuple(event_hashes),
    )


def build_trace_receipt(
    calls: Sequence[Mapping[str, Any]],
    *,
    expected_stocks: int = 49,
    expected_sectors: int = 6,
    mode: str = "LIVE_TRACE",
) -> dict[str, Any]:
    """Build a timestamp-free canonical receipt for one complete trace."""
    validation = validate_quant_rpc_calls(
        calls,
        expected_stocks=expected_stocks,
        expected_sectors=expected_sectors,
        require_complete=True,
    )
    if validation.issues or not validation.complete:
        raise ValueError("; ".join(validation.issues) or "quant trace is incomplete")
    payload = {
        "schema": "quant_phase_trace/v1",
        "mode": mode,
        "market_content_sha256": validation.market_content_sha256,
        "stage_sequence": [phase for phase, _method in QUANT_PHASE_SEQUENCE],
        "event_hashes": list(validation.event_hashes),
    }
    return {**payload, "trace_sha256": canonical_sha256(payload)}
