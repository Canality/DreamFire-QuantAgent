"""SubmissionContract: frozen official contest rules as code.

This module is the single source of truth for contest submission rules:
- Company universe (derived from stock_pool, verified against official Excel)
- Equity weight rules
- Report quality rules
- Unresolved / conflicting official guidance

Design rule: no business logic anywhere may hardcode 49 or 50.
Always use len(contract.company_codes) or contract.n_companies.
"""

from __future__ import annotations

import hashlib
import json
import math
import numbers
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Mapping, Tuple


# ---- constants ----

_VALID_WEIGHT_RULES = frozenset({
    "equities_plus_cash_equals_one",
    "equities_equal_one",
})

_VALID_REPORT_QUALITY_RULES = frozenset({
    "affects_shortlisting",
    "reference_only",
    "unresolved",
})

_VALID_CONTRACT_STATUSES = frozenset({
    "PROVISIONAL",
    "CONFIRMED",
})

_VALID_REPORT_EXTENSIONS = frozenset({".md", ".txt", ".pdf"})

# Ticker format: exactly 6 digits, ".SH" or ".SZ"
_TICKER_PATTERN = re.compile(r"^\d{6}\.(SH|SZ)$")

# Official Excel file: relative path from project root
_OFFICIAL_EXCEL_REL_PATH = "赛题文档/上市公司列表.xlsx"
# SHA-256 verified 2026-07-29 against the actual file on disk
_OFFICIAL_EXCEL_SHA256 = (
    "C021D69B5C3BF3EA0C4626811DF5ED9A02CD4C67E1068AD2F0CE35D759210617"
)

# Canonical source identity: the ONLY (path, hash) pair accepted for formal submission
_CANONICAL_SOURCE = (_OFFICIAL_EXCEL_REL_PATH, _OFFICIAL_EXCEL_SHA256)


def _resolve_project_root() -> Path:
    """Return the project root directory (Track_2).

    reporting/submission_contract.py → quant/reporting → quant →
    jiuwenswarm → jiuwenswarm → Track_2 (4 levels up).
    """
    return Path(__file__).resolve().parents[4]


def _resolve_official_excel_path() -> str:
    """Return the absolute path to the official Excel file."""
    return str(_resolve_project_root() / _OFFICIAL_EXCEL_REL_PATH)


def _compute_file_sha256(path: str) -> str:
    """Compute SHA-256 hex digest of a file. Returns '' if missing."""
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest().upper()
    except (FileNotFoundError, OSError):
        return ""


def _verify_file_matches_hash(path: str, expected_sha256: str) -> Tuple[bool, str]:
    """Verify a file exists and its SHA-256 matches the expected value.

    Returns (ok, reason).
    """
    if not path:
        return False, "path is empty"
    file_path = Path(path)
    if not file_path.exists():
        resolved = str(_resolve_project_root() / path)
        if Path(resolved).exists():
            file_path = Path(resolved)
        else:
            return False, f"File not found: {path}"
    actual = _compute_file_sha256(str(file_path))
    if not actual:
        return False, f"Cannot compute hash of: {path}"
    expected = expected_sha256.upper()
    if actual != expected:
        return False, (
            f"Hash mismatch for {path}: expected {expected}, got {actual}"
        )
    return True, f"Verified: {path}, SHA-256={actual}"


def _is_official_path(source_file: str) -> bool:
    """True only when source_file resolves to the exact canonical absolute path.

    Uses os.path.realpath to normalize and compare — rejects look-alike
    paths like C:/attacker/赛题文档/上市公司列表.xlsx.
    """
    canonical_abs = os.path.realpath(_resolve_official_excel_path())
    try:
        source_path = Path(source_file)
        if not source_path.is_absolute():
            source_path = _resolve_project_root() / source_path
        resolved = os.path.realpath(source_path)
    except (ValueError, OSError):
        return False
    return resolved == canonical_abs


def _is_canonical_source(source_file: str, source_sha256: str) -> bool:
    """True only when source_file AND source_sha256 both match the canonical pair."""
    canonical_path, canonical_hash = _CANONICAL_SOURCE
    path_matches = _is_official_path(source_file)
    hash_matches = source_sha256.upper() == canonical_hash.upper()
    return path_matches and hash_matches


# ---- main contract class ----


@dataclass(frozen=True)
class SubmissionContract:
    """Frozen contest rules contract. Modify via config file, not in code.

    Immutability: frozen=True prevents attribute reassignment.
    Internal mappings are converted to MappingProxyType in __post_init__
    so nested mutations (c.company_names[k] = v) raise TypeError.

    source_verified is a DERIVED field (init=False) — it is computed from
    canonical constants in __post_init__, never from user input.
    """

    company_codes: Tuple[str, ...]
    company_names: Mapping[str, str]
    sectors: Mapping[str, str]
    sector_names: Tuple[str, ...]

    source_file: str
    source_sha256: str

    report_file_extension: str

    equity_weight_rule: str
    allow_cash: bool | None
    report_quality_rule: str

    unresolved_questions: Tuple[str, ...]
    contract_status: str

    # Derived — computed from canonical source, not user input
    source_verified: bool = field(init=False, compare=False, default=False)

    def __post_init__(self) -> None:
        """Validate ALL invariants; make nested mappings immutable.

        This is the single validation boundary: construction, from_config,
        and from_stock_pool all flow through here.
        """
        issues: list[str] = []

        # --- ticker format ---
        bad_tickers = [t for t in self.company_codes if not _TICKER_PATTERN.match(t)]
        if bad_tickers:
            issues.append(
                f"Malformed ticker(s): {bad_tickers}. "
                f"Must match ^\\d{{6}}\\.(SH|SZ)$"
            )

        # --- report code uniqueness ---
        report_codes_list = [c.split(".")[0] for c in self.company_codes]
        if len(report_codes_list) != len(set(report_codes_list)):
            from collections import Counter
            dupes = sorted(rc for rc, n in Counter(report_codes_list).items() if n > 1)
            issues.append(
                f"Duplicate report codes: {dupes}. "
                f"Each 6-digit code must map to exactly one ticker."
            )

        # --- report file extension ---
        if self.report_file_extension not in _VALID_REPORT_EXTENSIONS:
            issues.append(
                f"Unknown report_file_extension '{self.report_file_extension}'. "
                f"Must be one of: {sorted(_VALID_REPORT_EXTENSIONS)}"
            )

        # --- weight rule ---
        if self.equity_weight_rule not in _VALID_WEIGHT_RULES:
            issues.append(
                f"Unknown equity_weight_rule '{self.equity_weight_rule}'. "
                f"Must be one of: {sorted(_VALID_WEIGHT_RULES)}"
            )

        # --- report quality rule ---
        if self.report_quality_rule not in _VALID_REPORT_QUALITY_RULES:
            issues.append(
                f"Unknown report_quality_rule '{self.report_quality_rule}'. "
                f"Must be one of: {sorted(_VALID_REPORT_QUALITY_RULES)}"
            )

        # --- contract status ---
        if self.contract_status not in _VALID_CONTRACT_STATUSES:
            issues.append(
                f"Unknown contract_status '{self.contract_status}'. "
                f"Must be one of: {sorted(_VALID_CONTRACT_STATUSES)}"
            )

        # --- allow_cash type invariant ---
        if self.allow_cash is not None and type(self.allow_cash) is not bool:
            issues.append(
                f"allow_cash must be None or bool, got {type(self.allow_cash).__name__} "
                f"with value {self.allow_cash!r}"
            )

        # --- allow_cash / weight_rule consistency ---
        if self.equity_weight_rule == "equities_equal_one" and self.allow_cash is True:
            issues.append(
                "Invalid combination: equities_equal_one requires allow_cash=False "
                f"or None, got allow_cash={self.allow_cash}"
            )

        # --- duplicate codes ---
        if len(self.company_codes) != len(set(self.company_codes)):
            from collections import Counter
            dupes = sorted(c for c, n in Counter(self.company_codes).items() if n > 1)
            issues.append(f"Duplicate company codes: {dupes}")

        # --- mapping consistency ---
        code_set = set(self.company_codes)
        name_keys = set(self.company_names.keys())
        sector_keys = set(self.sectors.keys())

        if code_set != name_keys:
            missing = sorted(code_set - name_keys)
            extra = sorted(name_keys - code_set)
            parts = []
            if missing:
                parts.append(f"codes without names: {missing}")
            if extra:
                parts.append(f"names without codes: {extra}")
            issues.append("Company codes/names mismatch: " + "; ".join(parts))

        if code_set != sector_keys:
            missing = sorted(code_set - sector_keys)
            extra = sorted(sector_keys - code_set)
            parts = []
            if missing:
                parts.append(f"codes without sectors: {missing}")
            if extra:
                parts.append(f"sectors without codes: {extra}")
            issues.append("Company codes/sectors mismatch: " + "; ".join(parts))

        # --- sector_names: must be unique and exactly match sector values ---
        if len(self.sector_names) != len(set(self.sector_names)):
            from collections import Counter
            dupes = sorted(s for s, n in Counter(self.sector_names).items() if n > 1)
            issues.append(f"sector_names contains duplicates: {dupes}")

        sector_values = set(self.sectors.values())
        sector_names_set = set(self.sector_names)
        if sector_names_set != sector_values:
            extra_in_names = sorted(sector_names_set - sector_values)
            missing_from_names = sorted(sector_values - sector_names_set)
            parts = []
            if extra_in_names:
                parts.append(f"sector_names not in any sector: {extra_in_names}")
            if missing_from_names:
                parts.append(f"sector values not in sector_names: {missing_from_names}")
            issues.append("sector_names must exactly match sector values: " + "; ".join(parts))

        # --- source_file validation ---
        # Three cases:
        # 1. Official path + canonical hash → verify file, mark source_verified
        # 2. Official path + WRONG hash → reject (look-alike attack)
        # 3. Non-official path (test/dev) → allow, source_verified stays False
        verified = False
        if _is_canonical_source(self.source_file, self.source_sha256):
            # Path + hash both match canonical → verify file on disk
            ok, _reason = _verify_file_matches_hash(
                _resolve_official_excel_path(), self.source_sha256
            )
            verified = ok
            if not ok:
                issues.append(
                    f"Canonical source file hash mismatch: {_reason}"
                )
        elif _is_official_path(self.source_file):
            # Path resolves to official file but hash doesn't match canonical
            issues.append(
                f"Source file '{self.source_file}' resolves to the official Excel "
                f"but the hash does not match the audited canonical hash "
                f"({_OFFICIAL_EXCEL_SHA256[:16]}...). "
                f"Rejecting — this could be a tampered or outdated source."
            )
        object.__setattr__(self, 'source_verified', verified)

        if issues:
            raise ValueError(
                f"SubmissionContract construction failed: {len(issues)} issue(s):\n  "
                + "\n  ".join(issues)
            )

        # --- make nested mappings truly immutable ---
        object.__setattr__(self, 'company_names', MappingProxyType(dict(self.company_names)))
        object.__setattr__(self, 'sectors', MappingProxyType(dict(self.sectors)))

    # ---- factories ----

    @classmethod
    def from_stock_pool(
        cls,
        official_excel_path: str | None = None,
        official_excel_sha256: str | None = None,
    ) -> "SubmissionContract":
        """Build contract from the project stock_pool module + official Excel.

        The official Excel MUST exist and match the archived hash.
        Raises ValueError on mismatch (fail-closed).

        When overrides are provided, they become the verified source;
        otherwise canonical constants are used.
        """
        from jiuwenswarm.quant.stock_pool import (
            ALL_STOCKS,
            SECTOR_MAP,
            STOCK_POOL,
            TICKER_NAME_MAP,
        )

        codes = tuple(sorted(ALL_STOCKS))
        names = {t: TICKER_NAME_MAP.get(t, t) for t in codes}
        sectors_map = {t: SECTOR_MAP.get(t, "未知") for t in codes}
        sec_names = tuple(STOCK_POOL.keys())

        # Resolve path and hash: use overrides if provided, else canonical
        if official_excel_path is not None:
            verify_path = official_excel_path
            source_path = official_excel_path
        else:
            verify_path = _resolve_official_excel_path()
            source_path = _OFFICIAL_EXCEL_REL_PATH

        if official_excel_sha256 is not None:
            verify_hash = official_excel_sha256
        else:
            verify_hash = _OFFICIAL_EXCEL_SHA256

        # Verify
        source_ok, reason = _verify_file_matches_hash(verify_path, verify_hash)
        if not source_ok:
            raise ValueError(
                f"Cannot build contract from stock_pool: {reason}. "
                f"Fix the Excel file or update _OFFICIAL_EXCEL_SHA256."
            )

        unresolved = (
            "Q1: static rules say 初赛 is pure objective backtest; "
            "Q&A says report completeness/usability affects shortlisting — which prevails?",
            "Q2: Q&A says 50 companies; official Excel has 49 — which is authoritative?",
            "Q3: static rules allow 半仓/空仓; "
            "Q&A says sum of company weights = 1 — does this mean equities_only or equities+cash=1?",
        )

        return cls(
            company_codes=codes,
            company_names=names,
            sectors=sectors_map,
            sector_names=sec_names,
            source_file=source_path,
            source_sha256=verify_hash,
            report_file_extension=".md",
            equity_weight_rule="equities_plus_cash_equals_one",
            allow_cash=None,
            report_quality_rule="unresolved",
            unresolved_questions=unresolved,
            contract_status="PROVISIONAL",
        )

    @classmethod
    def from_config(cls, config_path: str) -> "SubmissionContract":
        """Load contract from a JSON config file.

        All invariants run through __post_init__; bad configs raise ValueError.
        source_verified is never read from config — it is always derived.
        allow_cash is a required key.
        """
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        required = {
            "company_codes", "company_names", "sectors", "sector_names",
            "source_file", "source_sha256", "report_file_extension",
            "equity_weight_rule", "allow_cash", "report_quality_rule",
            "unresolved_questions", "contract_status",
        }
        actual = set(data.keys())
        missing = required - actual
        if missing:
            raise ValueError(
                f"Config {config_path} missing required keys: {sorted(missing)}"
            )

        allow_cash = data["allow_cash"]
        if allow_cash is not None and not isinstance(allow_cash, bool):
            raise ValueError(
                f"Config {config_path}: allow_cash must be None or bool, "
                f"got {type(allow_cash).__name__}: {allow_cash!r}"
            )

        return cls(
            company_codes=tuple(data["company_codes"]),
            company_names=dict(data["company_names"]),
            sectors=dict(data["sectors"]),
            sector_names=tuple(data["sector_names"]),
            source_file=str(data["source_file"]),
            source_sha256=str(data["source_sha256"]),
            report_file_extension=str(data["report_file_extension"]),
            equity_weight_rule=str(data["equity_weight_rule"]),
            allow_cash=allow_cash,
            report_quality_rule=str(data["report_quality_rule"]),
            unresolved_questions=tuple(data["unresolved_questions"]),
            contract_status=str(data["contract_status"]),
        )

    def to_config(self, config_path: str) -> None:
        """Persist contract to a JSON config file.

        source_verified is written for diagnostics only; it is never read back.
        """
        data = {
            "company_codes": list(self.company_codes),
            "company_names": dict(self.company_names),
            "sectors": dict(self.sectors),
            "sector_names": list(self.sector_names),
            "source_file": self.source_file,
            "source_sha256": self.source_sha256,
            "report_file_extension": self.report_file_extension,
            "equity_weight_rule": self.equity_weight_rule,
            "allow_cash": self.allow_cash,
            "report_quality_rule": self.report_quality_rule,
            "unresolved_questions": list(self.unresolved_questions),
            "contract_status": self.contract_status,
            "source_verified": self.source_verified,
        }
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    # ---- derived properties ----

    @property
    def n_companies(self) -> int:
        return len(self.company_codes)

    @property
    def n_sectors(self) -> int:
        return len(self.sector_names)

    @property
    def report_codes(self) -> Tuple[str, ...]:
        """6-digit report codes (no exchange suffix) for file naming."""
        return tuple(c.split(".")[0] for c in self.company_codes)

    @property
    def ticker_to_report_code(self) -> Mapping[str, str]:
        """Map ticker '000333.SZ' → report code '000333'."""
        return MappingProxyType({c: c.split(".")[0] for c in self.company_codes})

    @property
    def report_code_to_ticker(self) -> Mapping[str, str]:
        """Map report code '000333' → ticker '000333.SZ'."""
        return MappingProxyType({c.split(".")[0]: c for c in self.company_codes})

    @property
    def is_stale(self) -> bool:
        """True if the canonical source file has changed since construction.

        Always False for non-canonical (test/dev) contracts.
        """
        if not _is_official_path(self.source_file):
            return False
        ok, _ = _verify_file_matches_hash(
            self.source_file, self.source_sha256
        )
        return not ok

    # ---- validation methods ----

    def validate_report_set(self, report_codes: set[str]) -> tuple[bool, tuple[str, ...]]:
        """Check that report file set exactly matches contract company set."""
        issues: list[str] = []
        expected = set(self.report_codes)
        missing = expected - report_codes
        extra = report_codes - expected
        if missing:
            issues.append(f"Missing reports for: {sorted(missing)}")
        if extra:
            issues.append(f"Extra reports not in contract: {sorted(extra)}")
        return (len(issues) == 0, tuple(issues))

    def can_proceed_formal(self) -> tuple[bool, str]:
        """Check if contract is safe for formal submission packaging.

        Formal mode requires ALL of:
        - CONFIRMED status
        - No blocking unresolved questions
        - allow_cash is True or False (not None)
        - report_quality_rule is not 'unresolved'
        - Source is the canonical official Excel, verified and not stale
        """
        if self.contract_status != "CONFIRMED":
            return (False, f"Contract status is {self.contract_status}, not CONFIRMED")

        if self.unresolved_questions:
            return (False, f"Unresolved blocking questions remain: {len(self.unresolved_questions)} items")

        if self.allow_cash is None:
            return (False, "allow_cash is unresolved (None); must be True or False")
        if type(self.allow_cash) is not bool:
            return (False, f"allow_cash has wrong type ({type(self.allow_cash).__name__}); must be bool")

        if self.report_quality_rule == "unresolved":
            return (False, "report_quality_rule is still 'unresolved'")

        # Only canonical source can proceed to formal
        if not _is_official_path(self.source_file):
            return (False, "Not the canonical official source; formal requires verified official Excel")

        if not self.source_verified:
            return (False, "Official source was not verified; file hash mismatch with archived hash")

        if self.is_stale:
            return (False, "Official source file has changed since contract was constructed")

        return (True, "Contract confirmed, no blocking issues")

    def validate_weights(
        self, weights: dict[str, float]
    ) -> tuple[bool, tuple[str, ...]]:
        """Validate portfolio weights against contract equity weight rule.

        - Rejects non-numeric values (bool, str, None)
        - Rejects non-Real numbers (complex) — returns validation failure, not exception
        - Rejects non-finite values (NaN, +inf, -inf)
        - Rejects tickers not in company_codes
        - Rejects negative weights
        - Rejects single-stock cap violations
        - Enforces equity weight rule, even for empty weight dicts

        Returns (passed, tuple_of_issues).
        """
        issues: list[str] = []
        valid_tickers = set(self.company_codes)

        nonfinite: list[str] = []
        nonnumeric: list[str] = []
        nonreal: list[str] = []

        for ticker, w in weights.items():
            if isinstance(w, bool) or not isinstance(w, numbers.Number):
                nonnumeric.append(f"{ticker}={w!r} (type={type(w).__name__})")
            elif not isinstance(w, numbers.Real):
                nonreal.append(f"{ticker}={w!r} (type={type(w).__name__}, not Real)")
            elif not math.isfinite(w):
                nonfinite.append(f"{ticker}={w!r}")

        if nonnumeric:
            issues.append(f"Non-numeric weight values: {nonnumeric}")
        if nonreal:
            issues.append(f"Non-Real weight values (complex): {nonreal}")
        if nonfinite:
            issues.append(f"Non-finite weight values (NaN/inf): {nonfinite}")

        # Only compute total over finite Real numeric values
        numeric_weights: dict[str, float] = {}
        for t, w in weights.items():
            if (
                isinstance(w, numbers.Real)
                and not isinstance(w, bool)
                and math.isfinite(w)
            ):
                numeric_weights[t] = float(w)

        # --- reject unknown tickers ---
        for ticker in weights:
            if ticker not in valid_tickers:
                issues.append(f"Unknown ticker not in contract: {ticker}")

        # --- enforce weight rule (even when numeric_weights is empty) ---
        total = sum(numeric_weights.values())

        if not math.isfinite(total):
            issues.append(f"Sum of weights is non-finite: {total}")
            return (False, tuple(issues))

        if self.equity_weight_rule == "equities_plus_cash_equals_one":
            if total > 1.0 + 1e-6:
                issues.append(f"Sum of weights ({total:.6f}) exceeds 1.0")
            if self.allow_cash is False and abs(total - 1.0) > 1e-6:
                issues.append(
                    f"allow_cash=False but equity weights sum to {total:.6f} != 1.0"
                )
        elif self.equity_weight_rule == "equities_equal_one":
            if abs(total - 1.0) > 1e-6:
                issues.append(
                    f"Sum of equity weights ({total:.6f}) != 1.0, "
                    f"required by equities_equal_one"
                )
            if self.allow_cash is True:
                issues.append(
                    "Invalid: equities_equal_one with allow_cash=True "
                    "(cash implies equity sum < 1.0)"
                )

        # --- per-ticker checks ---
        for ticker, w in numeric_weights.items():
            if ticker not in valid_tickers:
                continue
            if w < 0:
                issues.append(f"Negative weight for {ticker}: {w}")
            if w > 0.10 + 1e-6:
                issues.append(f"Single-stock cap exceeded for {ticker}: {w:.4f} > 0.10")

        return (len(issues) == 0, tuple(issues))

    # ---- hash / identity ----

    def config_hash(self) -> str:
        """Deterministic hash of the full contract for change detection.

        source_verified is excluded — it is derived, not part of contract identity.
        """
        payload = json.dumps(
            {
                "codes": list(self.company_codes),
                "names": dict(sorted(self.company_names.items())),
                "sectors": dict(sorted(self.sectors.items())),
                "sector_names": list(self.sector_names),
                "source_file": self.source_file,
                "source_sha256": self.source_sha256,
                "report_file_extension": self.report_file_extension,
                "weight_rule": self.equity_weight_rule,
                "allow_cash": self.allow_cash,
                "report_quality_rule": self.report_quality_rule,
                "contract_status": self.contract_status,
                "unresolved_questions": list(self.unresolved_questions),
            },
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    # ---- official source verification ----

    @staticmethod
    def verify_official_excel(
        excel_path: str | None = None,
        expected_sha256: str | None = None,
    ) -> tuple[bool, str]:
        """Verify the official Excel file exists and matches the archived hash.

        Returns (ok, reason).
        """
        path = excel_path or _resolve_official_excel_path()
        expected = (expected_sha256 or _OFFICIAL_EXCEL_SHA256).upper()
        return _verify_file_matches_hash(path, expected)


# ---- module-level factory ----


def get_contract() -> SubmissionContract:
    """Return the current SubmissionContract.

    Tries config file first; falls back to stock_pool construction.
    """
    config_path = (
        Path(__file__).resolve().parent / "resources" / "submission_contract.json"
    )
    if config_path.exists():
        return SubmissionContract.from_config(str(config_path))
    return SubmissionContract.from_stock_pool()
