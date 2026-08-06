"""Unit tests for SubmissionContract — Phase R0 (third review backlog fixes).

Covers: original 21 + second-round 10 + third-round 6 = 37 tests.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from jiuwenswarm.quant.reporting.submission_contract import (
    SubmissionContract,
    _OFFICIAL_EXCEL_REL_PATH,
    _OFFICIAL_EXCEL_SHA256,
    _resolve_official_excel_path,
    _resolve_project_root,
    get_contract,
)


# ---- helpers ----

def _make_provisional_contract(n_codes: int = 49) -> SubmissionContract:
    """Build a minimal provisional contract with synthetic codes."""
    codes = tuple(f"{i:06d}.SH" for i in range(1, n_codes + 1))
    names = {c: f"公司_{c}" for c in codes}
    sectors = {c: "测试板块" for c in codes}
    return SubmissionContract(
        company_codes=codes,
        company_names=names,
        sectors=sectors,
        sector_names=("测试板块",),
        source_file="test.xlsx",
        source_sha256="abc123",
        report_file_extension=".md",
        equity_weight_rule="equities_plus_cash_equals_one",
        allow_cash=None,
        report_quality_rule="unresolved",
        unresolved_questions=(),
        contract_status="PROVISIONAL",
    )


def _make_confirmed_contract(n_codes: int = 49) -> SubmissionContract:
    """Build a confirmed contract with resolved semantics (test source, not official)."""
    codes = tuple(f"{i:06d}.SH" for i in range(1, n_codes + 1))
    names = {c: f"公司_{c}" for c in codes}
    sectors = {c: "测试板块" for c in codes}
    return SubmissionContract(
        company_codes=codes,
        company_names=names,
        sectors=sectors,
        sector_names=("测试板块",),
        source_file="test.xlsx",
        source_sha256="abc123",
        report_file_extension=".md",
        equity_weight_rule="equities_plus_cash_equals_one",
        allow_cash=True,                  # resolved
        report_quality_rule="affects_shortlisting",  # resolved
        unresolved_questions=(),
        contract_status="CONFIRMED",
    )


# ============================================================
# Original 21 tests
# ============================================================

def test_company_codes_unique_and_format():
    c = get_contract()
    codes = c.company_codes
    assert len(codes) == len(set(codes))
    for code in codes:
        assert len(code) >= 8
        assert "." in code
        ticker, exchange = code.split(".")
        assert ticker.isdigit()
        assert exchange in ("SH", "SZ")


def test_mappings_consistent():
    c = get_contract()
    code_set = set(c.company_codes)
    name_set = set(c.company_names.keys())
    sector_set = set(c.sectors.keys())
    assert code_set == name_set
    assert code_set == sector_set
    for ticker, sec in c.sectors.items():
        assert sec in c.sector_names


def test_report_set_missing_one_fails():
    c = get_contract()
    all_codes = set(c.report_codes)
    missing_one = all_codes - {c.report_codes[0]}
    passed, issues = c.validate_report_set(missing_one)
    assert not passed
    assert "Missing reports" in issues[0]


def test_report_set_extra_one_fails():
    c = get_contract()
    all_codes = set(c.report_codes)
    extra_code = all_codes | {"999999"}
    passed, issues = c.validate_report_set(extra_code)
    assert not passed
    assert any("Extra reports" in i for i in issues)


def test_report_set_exact_passes():
    c = get_contract()
    passed, issues = c.validate_report_set(set(c.report_codes))
    assert passed


def test_49_stock_contract():
    c = get_contract()
    assert c.n_companies == 49
    assert c.n_sectors == 6
    assert c.n_companies == len(c.company_codes)


def test_50_stock_contract_configurable():
    c = _make_provisional_contract(n_codes=50)
    assert c.n_companies == 50
    passed, issues = c.validate_report_set(set(c.report_codes))
    assert passed
    missing_one = set(c.report_codes) - {c.report_codes[0]}
    passed, issues = c.validate_report_set(missing_one)
    assert not passed


def test_n_companies_not_hardcoded():
    c = _make_provisional_contract(n_codes=30)
    assert c.n_companies == 30
    assert c.n_companies == len(c.company_codes)


def test_weight_rule_equities_plus_cash():
    c = _make_provisional_contract(n_codes=49)
    w = {code: 0.95 / 49 for code in c.company_codes}
    passed, issues = c.validate_weights(w)
    assert passed
    w_bad = {code: 1.05 / 49 for code in c.company_codes}
    passed, issues = c.validate_weights(w_bad)
    assert not passed
    assert any("exceeds 1.0" in i for i in issues)
    w_full = {code: 1.0 / 49 for code in c.company_codes}
    passed, issues = c.validate_weights(w_full)
    assert passed


def test_weight_rule_equities_equal_one():
    n = 15
    codes = tuple(f"{i:06d}.SH" for i in range(1, n + 1))
    contract = SubmissionContract(
        company_codes=codes,
        company_names={code: f"C{i}" for i, code in enumerate(codes, 1)},
        sectors={code: "T" for code in codes},
        sector_names=("T",),
        source_file="t.xlsx",
        source_sha256="abc",
        report_file_extension=".md",
        equity_weight_rule="equities_equal_one",
        allow_cash=False,
        report_quality_rule="unresolved",
        unresolved_questions=(),
        contract_status="PROVISIONAL",
    )
    w = {code: 1.0 / n for code in codes}
    passed, issues = contract.validate_weights(w)
    assert passed
    w_under = {code: 0.95 / n for code in codes}
    passed, issues = contract.validate_weights(w_under)
    assert not passed
    assert any("!= 1.0" in i for i in issues)
    w_over = {code: 1.0 / n for code in codes}
    w_over[codes[0]] = 0.15
    remaining = 0.85
    for code in codes[1:]:
        w_over[code] = remaining / (n - 1)
    passed, issues = contract.validate_weights(w_over)
    assert not passed
    assert any("cap exceeded" in i for i in issues)


def test_single_stock_cap():
    c = _make_provisional_contract(n_codes=49)
    w = {code: 0.01 for code in c.company_codes}
    w[c.company_codes[0]] = 0.15
    passed, issues = c.validate_weights(w)
    assert not passed
    assert any("cap exceeded" in i for i in issues)


def test_negative_weight():
    c = _make_provisional_contract(n_codes=49)
    w = {code: 0.02 for code in c.company_codes}
    w[c.company_codes[0]] = -0.01
    passed, issues = c.validate_weights(w)
    assert not passed
    assert any("Negative weight" in i for i in issues)


def test_provisional_cannot_proceed_formal():
    c = _make_provisional_contract()
    can, reason = c.can_proceed_formal()
    assert not can
    assert "PROVISIONAL" in reason


def test_unresolved_questions_block_formal():
    c = SubmissionContract(
        company_codes=("000001.SH",),
        company_names={"000001.SH": "Test"},
        sectors={"000001.SH": "T"},
        sector_names=("T",),
        source_file="t.xlsx",
        source_sha256="abc",
        report_file_extension=".md",
        equity_weight_rule="equities_plus_cash_equals_one",
        allow_cash=None,
        report_quality_rule="unresolved",
        unresolved_questions=("Q1: blocking question",),
        contract_status="CONFIRMED",
    )
    can, reason = c.can_proceed_formal()
    assert not can


def test_confirmed_no_issues_proceeds():
    """CONFIRMED + resolved semantics on a test (non-official) source → cannot proceed formal.

    Note: after R0 backlog fix, only canonical official source can proceed formal.
    Test sources are always rejected in can_proceed_formal.
    """
    c = _make_confirmed_contract()
    can, reason = c.can_proceed_formal()
    # Test source "test.xlsx" is not canonical → formal must fail
    assert not can, f"Test source should not proceed formal, got: {reason}"
    assert "canonical" in reason.lower() or "official" in reason.lower()


def test_config_hash_changes_on_code_change():
    c1 = _make_provisional_contract(n_codes=49)
    c2 = _make_provisional_contract(n_codes=50)
    assert c1.config_hash() != c2.config_hash()


def test_config_hash_stable():
    c1 = _make_provisional_contract(n_codes=49)
    c2 = _make_provisional_contract(n_codes=49)
    assert c1.config_hash() == c2.config_hash()


def test_config_hash_changes_on_weight_rule():
    c1 = _make_provisional_contract(n_codes=10)
    c2 = SubmissionContract(
        company_codes=c1.company_codes,
        company_names=c1.company_names,
        sectors=c1.sectors,
        sector_names=c1.sector_names,
        source_file=c1.source_file,
        source_sha256=c1.source_sha256,
        report_file_extension=c1.report_file_extension,
        equity_weight_rule="equities_equal_one",
        allow_cash=False,
        report_quality_rule=c1.report_quality_rule,
        unresolved_questions=c1.unresolved_questions,
        contract_status=c1.contract_status,
    )
    assert c1.config_hash() != c2.config_hash()


def test_round_trip_config():
    """to_config → from_config round-trip. source_verified is derived, not round-tripped."""
    c1 = _make_provisional_contract(n_codes=10)
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    ) as f:
        c1.to_config(f.name)
        tmp_path = f.name
    try:
        c2 = SubmissionContract.from_config(tmp_path)
        assert c1.company_codes == c2.company_codes
        assert dict(c1.company_names) == dict(c2.company_names)
        assert dict(c1.sectors) == dict(c2.sectors)
        assert c1.sector_names == c2.sector_names
        assert c1.equity_weight_rule == c2.equity_weight_rule
        assert c1.allow_cash == c2.allow_cash
        assert c1.contract_status == c2.contract_status
        assert c1.unresolved_questions == c2.unresolved_questions
        assert c1.config_hash() == c2.config_hash()
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def test_get_contract_loads_config():
    c = get_contract()
    assert c is not None
    assert c.n_companies == 49
    assert c.contract_status == "PROVISIONAL"


def test_contract_is_frozen():
    c = _make_provisional_contract()
    with pytest.raises(Exception):
        c.company_codes = ("000001.SH",)  # type: ignore[misc]


# ============================================================
# Second-round tests (N1-N10)
# ============================================================

def test_official_excel_hash_matches_archived_source():
    project_root = _resolve_project_root()
    excel_path = project_root / _OFFICIAL_EXCEL_REL_PATH
    assert excel_path.exists()
    ok, reason = SubmissionContract.verify_official_excel(
        str(excel_path), _OFFICIAL_EXCEL_SHA256
    )
    assert ok, f"Official Excel hash verification failed: {reason}"


def test_nested_mappings_are_immutable():
    c = get_contract()
    with pytest.raises(TypeError):
        c.company_names[c.company_codes[0]] = "MUTATED"  # type: ignore[index]
    with pytest.raises(TypeError):
        c.sectors[c.company_codes[0]] = "MUTATED_SECTOR"  # type: ignore[index]


def test_unknown_weight_rule_rejected():
    with pytest.raises(ValueError) as exc_info:
        SubmissionContract(
            company_codes=("000001.SH",),
            company_names={"000001.SH": "T"},
            sectors={"000001.SH": "X"},
            sector_names=("X",),
            source_file="t.xlsx",
            source_sha256="abc",
            report_file_extension=".md",
            equity_weight_rule="not_a_rule",
            allow_cash=None,
            report_quality_rule="unresolved",
            unresolved_questions=(),
            contract_status="PROVISIONAL",
        )
    assert "equity_weight_rule" in str(exc_info.value).lower()


def test_unknown_portfolio_ticker_rejected():
    c = _make_provisional_contract(n_codes=10)
    bad_ticker = "999999.XX"
    w = {code: 0.1 for code in c.company_codes}
    w[bad_ticker] = 0.01
    passed, issues = c.validate_weights(w)
    assert not passed
    assert any("Unknown ticker" in i for i in issues)


def test_allow_cash_false_rejects_underinvestment():
    c = SubmissionContract(
        company_codes=tuple(f"{i:06d}.SH" for i in range(1, 11)),
        company_names={f"{i:06d}.SH": f"C{i}" for i in range(1, 11)},
        sectors={f"{i:06d}.SH": "T" for i in range(1, 11)},
        sector_names=("T",),
        source_file="t.xlsx",
        source_sha256="abc",
        report_file_extension=".md",
        equity_weight_rule="equities_plus_cash_equals_one",
        allow_cash=False,
        report_quality_rule="unresolved",
        unresolved_questions=(),
        contract_status="PROVISIONAL",
    )
    w = {code: 0.95 / 10 for code in c.company_codes}
    passed, issues = c.validate_weights(w)
    assert not passed
    assert any("allow_cash" in i for i in issues)
    w_full = {code: 1.0 / 10 for code in c.company_codes}
    passed, issues = c.validate_weights(w_full)
    assert passed


def test_invalid_rule_combination_rejected():
    with pytest.raises(ValueError) as exc_info:
        SubmissionContract(
            company_codes=("000001.SH",),
            company_names={"000001.SH": "T"},
            sectors={"000001.SH": "X"},
            sector_names=("X",),
            source_file="t.xlsx",
            source_sha256="abc",
            report_file_extension=".md",
            equity_weight_rule="equities_equal_one",
            allow_cash=True,
            report_quality_rule="unresolved",
            unresolved_questions=(),
            contract_status="PROVISIONAL",
        )
    assert "allow_cash" in str(exc_info.value).lower()


def test_source_hash_changes_config_hash():
    c1 = _make_provisional_contract(n_codes=10)
    c2 = SubmissionContract(
        company_codes=c1.company_codes,
        company_names=c1.company_names,
        sectors=c1.sectors,
        sector_names=c1.sector_names,
        source_file=c1.source_file,
        source_sha256="DIFFERENT_HASH_12345",
        report_file_extension=c1.report_file_extension,
        equity_weight_rule=c1.equity_weight_rule,
        allow_cash=c1.allow_cash,
        report_quality_rule=c1.report_quality_rule,
        unresolved_questions=c1.unresolved_questions,
        contract_status=c1.contract_status,
    )
    assert c1.config_hash() != c2.config_hash()
    c3 = _make_provisional_contract(n_codes=10)
    assert c1.config_hash() == c3.config_hash()


def test_duplicate_company_code_rejected():
    with pytest.raises(ValueError) as exc_info:
        SubmissionContract(
            company_codes=("000001.SH", "000001.SH", "000002.SZ"),
            company_names={"000001.SH": "A", "000002.SZ": "B"},
            sectors={"000001.SH": "X", "000002.SZ": "X"},
            sector_names=("X",),
            source_file="t.xlsx",
            source_sha256="abc",
            report_file_extension=".md",
            equity_weight_rule="equities_plus_cash_equals_one",
            allow_cash=None,
            report_quality_rule="unresolved",
            unresolved_questions=(),
            contract_status="PROVISIONAL",
        )
    assert "duplicate" in str(exc_info.value).lower()


def test_mapping_key_mismatch_rejected():
    with pytest.raises(ValueError):
        SubmissionContract(
            company_codes=("000001.SH",),
            company_names={"000001.SH": "A", "000002.SZ": "Extra"},
            sectors={"000001.SH": "X"},
            sector_names=("X",),
            source_file="t.xlsx",
            source_sha256="abc",
            report_file_extension=".md",
            equity_weight_rule="equities_plus_cash_equals_one",
            allow_cash=None,
            report_quality_rule="unresolved",
            unresolved_questions=(),
            contract_status="PROVISIONAL",
        )
    with pytest.raises(ValueError):
        SubmissionContract(
            company_codes=("000001.SH", "000002.SZ"),
            company_names={"000001.SH": "A"},
            sectors={"000001.SH": "X", "000002.SZ": "Y"},
            sector_names=("X", "Y"),
            source_file="t.xlsx",
            source_sha256="abc",
            report_file_extension=".md",
            equity_weight_rule="equities_plus_cash_equals_one",
            allow_cash=None,
            report_quality_rule="unresolved",
            unresolved_questions=(),
            contract_status="PROVISIONAL",
        )


def test_report_code_is_six_digits_and_roundtrips_to_ticker():
    c = get_contract()
    for code in c.report_codes:
        assert len(code) == 6
        assert code.isdigit()
        ticker = c.report_code_to_ticker[code]
        assert ticker in c.company_codes
        assert c.ticker_to_report_code[ticker] == code
    for ticker in c.company_codes:
        rc = c.ticker_to_report_code[ticker]
        assert len(rc) == 6
        assert rc.isdigit()
        assert c.report_code_to_ticker[rc] == ticker


# ============================================================
# Third-round tests (N11-N16) — Codex R0 backlog
# ============================================================

def test_official_source_requires_matching_hash_and_semantics():
    """Bad hash and fake semantics on the canonical path both fail closed.

    Uses absolute path to guarantee _is_official_path matches via os.path.realpath.
    """
    import os
    official_abs = _resolve_official_excel_path()
    if not os.path.exists(official_abs):
        pytest.skip("Official Excel not available")

    # Wrong hash on absolute canonical path → must raise
    with pytest.raises(ValueError) as exc_info:
        SubmissionContract(
            company_codes=("000001.SH",),
            company_names={"000001.SH": "Test"},
            sectors={"000001.SH": "T"},
            sector_names=("T",),
            source_file=official_abs,       # absolute path → _is_official_path = True
            source_sha256="0" * 64,          # wrong hash
            report_file_extension=".md",
            equity_weight_rule="equities_plus_cash_equals_one",
            allow_cash=None,
            report_quality_rule="unresolved",
            unresolved_questions=(),
            contract_status="PROVISIONAL",
        )
    msg = str(exc_info.value).lower()
    assert "hash mismatch" in msg or "verification failed" in msg or "tampered" in msg

    # Correct path/hash cannot self-attest an unrelated one-company contract.
    with pytest.raises(ValueError, match="semantic mismatch"):
        SubmissionContract(
            company_codes=("000001.SH",),
            company_names={"000001.SH": "Test"},
            sectors={"000001.SH": "T"},
            sector_names=("T",),
            source_file=official_abs,
            source_sha256=_OFFICIAL_EXCEL_SHA256,
            report_file_extension=".md",
            equity_weight_rule="equities_plus_cash_equals_one",
            allow_cash=None,
            report_quality_rule="unresolved",
            unresolved_questions=(),
            contract_status="PROVISIONAL",
        )

    # The repository's exact 49-name/six-group contract remains verified.
    assert get_contract().source_verified is True


def test_formal_gate_rejects_non_official_or_self_asserted_source():
    """Formal gate rejects non-canonical, unresolved, and fake official inputs."""
    # Case A: test source (not canonical) → reject
    c = SubmissionContract(
        company_codes=("000001.SH", "000002.SZ"),
        company_names={"000001.SH": "A", "000002.SZ": "B"},
        sectors={"000001.SH": "T", "000002.SZ": "T"},
        sector_names=("T",),
        source_file="fake.xlsx",
        source_sha256="attacker-controlled",
        report_file_extension=".md",
        equity_weight_rule="equities_plus_cash_equals_one",
        allow_cash=True,
        report_quality_rule="affects_shortlisting",
        unresolved_questions=(),
        contract_status="CONFIRMED",
    )
    can, reason = c.can_proceed_formal()
    assert not can, f"Non-canonical source should be rejected, got: {reason}"

    # Case B: allow_cash=None (unresolved) → reject
    c2 = SubmissionContract(
        company_codes=("000001.SH", "000002.SZ"),
        company_names={"000001.SH": "A", "000002.SZ": "B"},
        sectors={"000001.SH": "T", "000002.SZ": "T"},
        sector_names=("T",),
        source_file="test.xlsx",
        source_sha256="abc",
        report_file_extension=".md",
        equity_weight_rule="equities_plus_cash_equals_one",
        allow_cash=None,
        report_quality_rule="affects_shortlisting",
        unresolved_questions=(),
        contract_status="CONFIRMED",
    )
    can, reason = c2.can_proceed_formal()
    assert not can

    # Case C: canonical bytes cannot bless an unrelated two-company contract.
    import os
    official_abs = _resolve_official_excel_path()
    if os.path.exists(official_abs):
        with pytest.raises(ValueError, match="semantic mismatch"):
            SubmissionContract(
                company_codes=("000001.SH", "000002.SZ"),
                company_names={"000001.SH": "A", "000002.SZ": "B"},
                sectors={"000001.SH": "T", "000002.SZ": "T"},
                sector_names=("T",),
                source_file=official_abs,
                source_sha256=_OFFICIAL_EXCEL_SHA256,
                report_file_extension=".md",
                equity_weight_rule="equities_plus_cash_equals_one",
                allow_cash=True,
                report_quality_rule="affects_shortlisting",
                unresolved_questions=(),
                contract_status="CONFIRMED",
            )


def test_canonical_source_rejects_name_or_group_drift() -> None:
    canonical = get_contract()
    ticker = canonical.company_codes[0]

    changed_names = dict(canonical.company_names)
    changed_names[ticker] = "伪造公司名称"
    with pytest.raises(ValueError, match="company_names"):
        SubmissionContract(
            company_codes=canonical.company_codes,
            company_names=changed_names,
            sectors=canonical.sectors,
            sector_names=canonical.sector_names,
            source_file=canonical.source_file,
            source_sha256=canonical.source_sha256,
            report_file_extension=canonical.report_file_extension,
            equity_weight_rule=canonical.equity_weight_rule,
            allow_cash=canonical.allow_cash,
            report_quality_rule=canonical.report_quality_rule,
            unresolved_questions=canonical.unresolved_questions,
            contract_status=canonical.contract_status,
        )

    changed_sectors = dict(canonical.sectors)
    changed_sectors[ticker] = next(
        sector
        for sector in canonical.sector_names
        if sector != canonical.sectors[ticker]
    )
    with pytest.raises(ValueError, match="sectors"):
        SubmissionContract(
            company_codes=canonical.company_codes,
            company_names=canonical.company_names,
            sectors=changed_sectors,
            sector_names=canonical.sector_names,
            source_file=canonical.source_file,
            source_sha256=canonical.source_sha256,
            report_file_extension=canonical.report_file_extension,
            equity_weight_rule=canonical.equity_weight_rule,
            allow_cash=canonical.allow_cash,
            report_quality_rule=canonical.report_quality_rule,
            unresolved_questions=canonical.unresolved_questions,
            contract_status=canonical.contract_status,
        )


def test_official_source_rejects_symlink_aliases(
    tmp_path: Path,
) -> None:
    canonical = get_contract()
    official_path = Path(_resolve_official_excel_path())

    final_alias = tmp_path / "alias.xlsx"
    parent_alias = tmp_path / "aliased-parent"
    try:
        final_alias.symlink_to(official_path)
        parent_alias.symlink_to(official_path.parent, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlink creation is unavailable: {exc}")

    for alias in (final_alias, parent_alias / official_path.name):
        contract = SubmissionContract(
            company_codes=canonical.company_codes,
            company_names=canonical.company_names,
            sectors=canonical.sectors,
            sector_names=canonical.sector_names,
            source_file=str(alias),
            source_sha256=canonical.source_sha256,
            report_file_extension=canonical.report_file_extension,
            equity_weight_rule=canonical.equity_weight_rule,
            allow_cash=canonical.allow_cash,
            report_quality_rule=canonical.report_quality_rule,
            unresolved_questions=canonical.unresolved_questions,
            contract_status=canonical.contract_status,
        )
        assert contract.source_verified is False

def test_allow_cash_requires_bool_or_none_and_formal_requires_bool():
    """allow_cash type invariant: must be None or bool. Formal requires bool."""
    # String "yes" → rejected at construction
    with pytest.raises(ValueError) as exc_info:
        SubmissionContract(
            company_codes=("000001.SH",),
            company_names={"000001.SH": "A"},
            sectors={"000001.SH": "T"},
            sector_names=("T",),
            source_file="t.xlsx",
            source_sha256="abc",
            report_file_extension=".md",
            equity_weight_rule="equities_plus_cash_equals_one",
            allow_cash="yes",  # bad type
            report_quality_rule="unresolved",
            unresolved_questions=(),
            contract_status="PROVISIONAL",
        )
    assert "allow_cash" in str(exc_info.value).lower()

    # int 0 → rejected
    with pytest.raises(ValueError):
        SubmissionContract(
            company_codes=("000001.SH",),
            company_names={"000001.SH": "A"},
            sectors={"000001.SH": "T"},
            sector_names=("T",),
            source_file="t.xlsx",
            source_sha256="abc",
            report_file_extension=".md",
            equity_weight_rule="equities_plus_cash_equals_one",
            allow_cash=0,
            report_quality_rule="unresolved",
            unresolved_questions=(),
            contract_status="PROVISIONAL",
        )


def test_empty_weights_obey_total_weight_rule():
    """Empty weight dict under equities_equal_one must fail (sum=0 != 1.0)."""
    c = SubmissionContract(
        company_codes=("000001.SH", "000002.SZ"),
        company_names={"000001.SH": "A", "000002.SZ": "B"},
        sectors={"000001.SH": "T", "000002.SZ": "T"},
        sector_names=("T",),
        source_file="t.xlsx",
        source_sha256="abc",
        report_file_extension=".md",
        equity_weight_rule="equities_equal_one",
        allow_cash=False,
        report_quality_rule="unresolved",
        unresolved_questions=(),
        contract_status="PROVISIONAL",
    )
    passed, issues = c.validate_weights({})
    assert not passed, "Empty weights under equities_equal_one should fail"
    assert any("!= 1.0" in i for i in issues), f"Issues: {issues}"

    # equities_plus_cash with allow_cash=None: empty → total=0, no violation
    c2 = _make_provisional_contract(n_codes=10)
    passed, issues = c2.validate_weights({})
    assert passed, f"Empty weights under equities_plus_cash (allow_cash=None) should pass, got: {issues}"


def test_complex_weight_returns_validation_failure_not_exception():
    """Complex numbers must return validation failure, not raise TypeError."""
    c = _make_provisional_contract(n_codes=10)
    ticker = c.company_codes[0]
    # Complex weight: should not throw, should report as non-Real
    passed, issues = c.validate_weights({ticker: 0.05 + 0j})
    assert not passed, "Complex weight should be rejected"
    assert any("complex" in i.lower() or "non-real" in i.lower() for i in issues), f"Issues: {issues}"


def test_sector_names_are_unique_and_exactly_match_sector_values():
    """sector_names must be unique and match exactly the set of sector values."""
    # Duplicate sector_names → rejected
    with pytest.raises(ValueError) as exc_info:
        SubmissionContract(
            company_codes=("000001.SH",),
            company_names={"000001.SH": "A"},
            sectors={"000001.SH": "T"},
            sector_names=("T", "T"),  # duplicate
            source_file="t.xlsx",
            source_sha256="abc",
            report_file_extension=".md",
            equity_weight_rule="equities_plus_cash_equals_one",
            allow_cash=None,
            report_quality_rule="unresolved",
            unresolved_questions=(),
            contract_status="PROVISIONAL",
        )
    assert "duplicate" in str(exc_info.value).lower()

    # sector_names with extra unused entry → rejected
    with pytest.raises(ValueError) as exc_info2:
        SubmissionContract(
            company_codes=("000001.SH",),
            company_names={"000001.SH": "A"},
            sectors={"000001.SH": "T"},
            sector_names=("T", "UNUSED"),
            source_file="t.xlsx",
            source_sha256="abc",
            report_file_extension=".md",
            equity_weight_rule="equities_plus_cash_equals_one",
            allow_cash=None,
            report_quality_rule="unresolved",
            unresolved_questions=(),
            contract_status="PROVISIONAL",
        )
    msg2 = str(exc_info2.value).lower()
    assert "sector_names" in msg2 or "sector values" in msg2


def test_config_requires_allow_cash_and_source_verified_is_derived():
    """from_config must require allow_cash; source_verified is derived, not read from JSON."""
    import os
    # Write a config missing allow_cash
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    ) as f:
        json.dump({
            "company_codes": ["000001.SH"],
            "company_names": {"000001.SH": "A"},
            "sectors": {"000001.SH": "T"},
            "sector_names": ["T"],
            "source_file": "t.xlsx",
            "source_sha256": "abc",
            "report_file_extension": ".md",
            "equity_weight_rule": "equities_plus_cash_equals_one",
            # allow_cash MISSING
            "report_quality_rule": "unresolved",
            "unresolved_questions": [],
            "contract_status": "PROVISIONAL",
        }, f)
        tmp = f.name
    try:
        with pytest.raises(ValueError) as exc_info:
            SubmissionContract.from_config(tmp)
        assert "allow_cash" in str(exc_info.value).lower()
    finally:
        os.unlink(tmp)

    # source_verified in JSON → still uses derived value, not the JSON value
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    ) as f:
        json.dump({
            "company_codes": ["000001.SH"],
            "company_names": {"000001.SH": "A"},
            "sectors": {"000001.SH": "T"},
            "sector_names": ["T"],
            "source_file": "t.xlsx",
            "source_sha256": "abc",
            "report_file_extension": ".md",
            "equity_weight_rule": "equities_plus_cash_equals_one",
            "allow_cash": None,
            "report_quality_rule": "unresolved",
            "unresolved_questions": [],
            "contract_status": "PROVISIONAL",
            "source_verified": True,  # should be ignored
        }, f)
        tmp2 = f.name
    try:
        c = SubmissionContract.from_config(tmp2)
        # "t.xlsx" + "abc" is not canonical → source_verified should be False
        assert c.source_verified is False, (
            "source_verified must be derived from canonical constants, not JSON"
        )
    finally:
        os.unlink(tmp2)
