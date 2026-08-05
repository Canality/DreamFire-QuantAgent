"""Parse Alpha/Risk & Evidence RPC output into structured AgentView objects.

Fail-closed: malformed JSON, unknown tickers, or missing required fields
all produce validation errors rather than silently passing bad data.
"""

from __future__ import annotations

import json
import re
from typing import List, Tuple

from jiuwenswarm.quant.reporting.models import AgentView
from jiuwenswarm.quant.reporting.submission_contract import SubmissionContract


def parse_agent_view(
    raw_output: str | dict,
    role: str,
    contract: SubmissionContract | None = None,
) -> Tuple[AgentView | None, List[str]]:
    """Parse a current analyst RPC output into a validated AgentView.

    Args:
        raw_output: Raw JSON string or dict from the RPC.
        role: Exactly "alpha" or "risk_evidence".
        contract: Optional contract for ticker validation.

    Returns:
        (AgentView or None, list of errors). If errors, AgentView is None.
    """
    errors: List[str] = []

    if role not in {"alpha", "risk_evidence"}:
        return None, [f"Unsupported AgentView role: {role}"]

    # Parse JSON
    if isinstance(raw_output, str):
        try:
            data = json.loads(raw_output)
        except json.JSONDecodeError as e:
            errors.append(f"Malformed JSON from {role}: {e}")
            return None, errors
    elif isinstance(raw_output, dict):
        data = raw_output
    else:
        errors.append(f"Unexpected type from {role}: {type(raw_output).__name__}")
        return None, errors

    # Extract fields
    verdict = str(data.get("verdict", "")).strip()
    confidence = str(data.get("confidence", "")).strip().lower()
    candidate_tickers_raw = data.get("candidate_tickers", [])
    warnings_raw = data.get("warnings", [])
    evidence_ids_raw = data.get("evidence_ids", [])
    summary = str(data.get("summary", data.get("rationale", ""))).strip()

    # Validate required fields
    if not verdict:
        errors.append(f"{role}: missing required field 'verdict'")
    if verdict not in ("overweight", "neutral", "underweight", ""):
        errors.append(f"{role}: invalid verdict '{verdict}'")

    if confidence not in ("high", "medium", "low", ""):
        errors.append(f"{role}: invalid confidence '{confidence}'")
    if not confidence:
        errors.append(f"{role}: missing required field 'confidence'")

    # Parse tickers
    candidate_tickers: List[str] = []
    if isinstance(candidate_tickers_raw, list):
        for t in candidate_tickers_raw:
            ticker = str(t).strip()
            if ticker and re.match(r"^\d{6}\.(SH|SZ)$", ticker):
                candidate_tickers.append(ticker)
            elif ticker:
                errors.append(f"{role}: malformed ticker '{ticker}'")
    elif isinstance(candidate_tickers_raw, str):
        for part in candidate_tickers_raw.replace(",", " ").split():
            ticker = part.strip()
            if ticker and re.match(r"^\d{6}\.(SH|SZ)$", ticker):
                candidate_tickers.append(ticker)

    # Validate tickers against contract if provided
    if contract and candidate_tickers:
        for ticker in candidate_tickers:
            if ticker not in set(contract.company_codes):
                errors.append(f"{role}: unknown ticker '{ticker}' not in contract")

    # Parse warnings
    warnings: List[str] = []
    if isinstance(warnings_raw, list):
        for w in warnings_raw:
            if w and str(w).strip():
                warnings.append(str(w).strip())
    elif isinstance(warnings_raw, str) and warnings_raw.strip():
        warnings.append(warnings_raw.strip())

    # Parse evidence IDs
    evidence_ids: List[str] = []
    if isinstance(evidence_ids_raw, list):
        for eid in evidence_ids_raw:
            if eid and str(eid).strip():
                evidence_ids.append(str(eid).strip())

    # Track unknown/missing fields
    unknown_fields: List[str] = []
    if not candidate_tickers:
        unknown_fields.append("candidate_tickers")
    if not evidence_ids:
        unknown_fields.append("evidence_ids")
    if not summary:
        unknown_fields.append("summary")

    if errors:
        return None, errors

    return AgentView(
        role=role,
        verdict=verdict or "neutral",
        confidence=confidence or "medium",
        candidate_tickers=tuple(candidate_tickers),
        warnings=tuple(warnings),
        evidence_ids=tuple(evidence_ids),
        unknown_fields=tuple(unknown_fields),
        summary=summary,
    ), []
