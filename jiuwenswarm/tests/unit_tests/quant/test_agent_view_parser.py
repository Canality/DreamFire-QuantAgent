"""Tests for agent_view_parser — Phase R2."""

import json

from jiuwenswarm.quant.reporting.agent_view_parser import (
    parse_agent_view,
    parse_bull_bear_pair,
)
from jiuwenswarm.quant.reporting.submission_contract import SubmissionContract


def _make_contract() -> SubmissionContract:
    codes = ("000001.SH", "000002.SZ", "000333.SZ")
    return SubmissionContract(
        company_codes=codes,
        company_names={c: f"C{c}" for c in codes},
        sectors={c: "T" for c in codes},
        sector_names=("T",),
        source_file="t.xlsx", source_sha256="abc", report_file_extension=".md",
        equity_weight_rule="equities_plus_cash_equals_one", allow_cash=None,
        report_quality_rule="unresolved", unresolved_questions=(),
        contract_status="PROVISIONAL",
    )


def test_parse_valid_bull_view():
    data = {
        "verdict": "overweight",
        "confidence": "high",
        "candidate_tickers": ["000001.SH", "000002.SZ"],
        "warnings": [],
        "evidence_ids": ["e1"],
        "summary": "Strong momentum",
    }
    view, errors = parse_agent_view(data, "alpha", _make_contract())
    assert view is not None
    assert errors == []
    assert view.role == "alpha"
    assert view.verdict == "overweight"
    assert view.confidence == "high"
    assert "000001.SH" in view.candidate_tickers


def test_parse_malformed_json():
    view, errors = parse_agent_view("not json", "bull")
    assert view is None
    assert len(errors) > 0
    assert any("Malformed" in e for e in errors)


def test_parse_missing_required_fields():
    view, errors = parse_agent_view({}, "bear")
    assert view is None
    assert len(errors) > 0


def test_parse_invalid_ticker():
    data = {"verdict": "neutral", "confidence": "medium", "candidate_tickers": ["bad_ticker"]}
    view, errors = parse_agent_view(data, "bull", _make_contract())
    assert len(errors) > 0
    assert any("malformed" in e.lower() for e in errors)


def test_parse_unknown_ticker():
    data = {"verdict": "neutral", "confidence": "medium", "candidate_tickers": ["999999.SZ"]}
    view, errors = parse_agent_view(data, "bull", _make_contract())
    assert len(errors) > 0
    assert any("unknown" in e.lower() for e in errors)


def test_parse_valid_from_json_string():
    raw = json.dumps({"verdict": "underweight", "confidence": "low"})
    view, errors = parse_agent_view(raw, "bear")
    assert view is not None
    assert view.verdict == "underweight"


def test_parse_bull_bear_pair():
    bull = {"verdict": "overweight", "confidence": "high"}
    bear = {"verdict": "underweight", "confidence": "medium"}
    views, errors = parse_bull_bear_pair(bull, bear)
    assert len(views) == 2
    assert views[0].role == "alpha"
    assert views[1].role == "risk_evidence"


def test_parse_bull_bear_pair_one_fails():
    views, errors = parse_bull_bear_pair({"verdict": "ok"}, "bad string")
    assert len(views) == 0  # bull missing confidence, bear malformed
    assert len(errors) > 1
