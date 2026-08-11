"""Offline tests for the operate-year dividend archive generator (WP1-E2O).

Every test injects a fake query function; none touches the network.  The
generator script lives under ``jiuwenswarm/scripts`` so it is loaded via
``sys.path`` and its core ``build_operate_archive`` is exercised directly.
"""

from __future__ import annotations

import csv as csv_module
import io
import json
import sys
from pathlib import Path

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parents[3] / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import fetch_corporate_action_operate as loader  # noqa: E402


DIVID_FIELDS = list(loader.CANONICAL_COLUMNS[1:])
YEARS = list(range(2020, 2026))
_BAOSTOCK_VERSION = "0.9.3"
_MODULE_HASHES = {
    "evaluation/season_index.py": "a" * 64,
    "data/resultset.py": "b" * 64,
    "login/loginout.py": "c" * 64,
    "common/contants.py": "d" * 64,
}


def make_row(**kwargs: str) -> list[str]:
    defaults = {field: "" for field in DIVID_FIELDS}
    defaults.update(kwargs)
    return [defaults[field] for field in DIVID_FIELDS]


class FakeResult:
    """Mimics the baostock ResultData pull model used by the generator."""

    def __init__(
        self,
        rows: list[list[str]],
        *,
        fields: list[str] | None = None,
        error_code: str = "0",
        error_msg: str = "",
        fail_page: int | None = None,
        code: str = "",
    ) -> None:
        self.fields = list(fields or DIVID_FIELDS)
        self.error_code = error_code
        self.error_msg = error_msg
        self.code = code
        self._rows = [list(row) for row in rows]
        self._idx = 0
        self._next_calls = 0
        self._fail_page = fail_page

    def next(self) -> bool:
        self._next_calls += 1
        if self._fail_page is not None and self._next_calls >= self._fail_page:
            self.error_code = "10002007"
            self.error_msg = "网络接收错误。"
        return self._idx < len(self._rows)

    def get_row_data(self) -> list[str]:
        row = self._rows[self._idx]
        self._idx += 1
        return row


def build(
    tmp_path: Path,
    *,
    rows_by_query: dict[tuple[str, str], list[list[str]]],
    tickers: list[str] | None = None,
    years: list[int] | None = None,
    fail_code: str | None = None,
    fail_page: int | None = None,
    wrong_returned_code: bool = False,
    official_tickers: list[str] | None = None,
) -> dict:
    tickers = tickers or ["sh.600000"]
    years = years or YEARS

    def query_fn(code: str, year: str, year_type: str):
        assert year_type == "operate"
        key = (code, year)
        rows = rows_by_query.get(key, [])
        return FakeResult(
            rows,
            error_code="0" if fail_code is None else fail_code,
            fail_page=fail_page,
            code="sh.999999" if wrong_returned_code else code,
        )

    return loader.build_operate_archive(
        tickers=tickers,
        years=years,
        out_dir=tmp_path,
        query_fn=query_fn,
        baostock_version=_BAOSTOCK_VERSION,
        baostock_module_sha256=_MODULE_HASHES,
        fetched_at="2026-08-10T00:00:00+00:00",
        tickers_expected=None,
        official_tickers=official_tickers or tickers,
    )


def test_csv_is_deterministic_across_runs(tmp_path: Path) -> None:
    rows = [make_row(dividOperateDate="2025-06-30", dividCashPsBeforeTax="1.0")]
    out1 = tmp_path / "a"
    out2 = tmp_path / "b"
    build(out1, rows_by_query={("sh.600000", "2025"): rows})
    build(out2, rows_by_query={("sh.600000", "2025"): rows})
    assert (out1 / "corporate_actions.csv").read_bytes() == (
        out2 / "corporate_actions.csv"
    ).read_bytes()
    manifest1 = json.loads((out1 / "source_records.json").read_text(encoding="utf-8"))
    manifest2 = json.loads((out2 / "source_records.json").read_text(encoding="utf-8"))
    assert manifest1["total_rows"] == manifest2["total_rows"] == 1
    assert manifest1["per_request"][0]["response_payload_sha256"] == manifest2[
        "per_request"
    ][0]["response_payload_sha256"]


def test_rows_are_stable_sorted(tmp_path: Path) -> None:
    rows = [
        make_row(dividOperateDate="2025-08-01"),
        make_row(dividOperateDate="2025-01-15"),
        make_row(dividOperateDate="2025-03-10"),
    ]
    build(tmp_path, rows_by_query={("sh.600000", "2025"): rows})
    lines = (tmp_path / "corporate_actions.csv").read_text(encoding="utf-8").splitlines()
    assert lines[0] == ",".join(loader.CANONICAL_COLUMNS)
    dates = [
        dict(zip(loader.CANONICAL_COLUMNS, line.split(",")))["dividOperateDate"]
        for line in lines[1:]
    ]
    assert dates == sorted(dates)


def test_exact_duplicates_dedup_with_count(tmp_path: Path) -> None:
    row = make_row(dividOperateDate="2025-06-30", dividCashPsBeforeTax="1.0")
    build(tmp_path, rows_by_query={("sh.600000", "2025"): [row, list(row)]})
    csv_lines = (tmp_path / "corporate_actions.csv").read_text(encoding="utf-8").splitlines()
    assert len(csv_lines) == 2  # header + 1 row
    manifest = json.loads((tmp_path / "source_records.json").read_text(encoding="utf-8"))
    assert manifest["total_rows"] == 1
    assert manifest["duplicate_count"] == 1
    receipt = next(
        item for item in manifest["per_request"] if item["year"] == "2025"
    )
    assert receipt["duplicate_count"] == 1
    assert receipt["row_count"] == 2


def test_distinct_identities_same_ticker_date_all_kept(tmp_path: Path) -> None:
    rows = [
        make_row(dividOperateDate="2025-06-30", dividCashPsBeforeTax="1.0"),
        make_row(dividOperateDate="2025-06-30", dividCashPsBeforeTax="0.5"),
    ]
    build(tmp_path, rows_by_query={("sh.600000", "2025"): rows})
    csv_lines = (tmp_path / "corporate_actions.csv").read_text(encoding="utf-8").splitlines()
    assert len(csv_lines) == 3  # header + 2 distinct identities
    body = "\n".join(csv_lines[1:])
    assert "1.0" in body and "0.5" in body


def test_zero_row_success_is_valid_empty_result(tmp_path: Path) -> None:
    build(tmp_path, rows_by_query={})
    manifest = json.loads((tmp_path / "source_records.json").read_text(encoding="utf-8"))
    assert len(manifest["per_request"]) == len(YEARS)
    for receipt in manifest["per_request"]:
        assert receipt["error_code"] == "0"
        assert receipt["row_count"] == 0
        assert receipt["failed"] is False
        assert receipt["response_payload_sha256"] is not None
    assert (tmp_path / "corporate_actions.csv").read_text(
        encoding="utf-8"
    ).splitlines() == [",".join(loader.CANONICAL_COLUMNS)]


def test_mid_pagination_failure_fails_closed(tmp_path: Path) -> None:
    rows = [make_row(dividOperateDate="2025-06-30")]
    with pytest.raises(loader.GeneratorError, match="request failed"):
        build(
            tmp_path,
            rows_by_query={("sh.600000", "2025"): rows},
            fail_page=2,
        )
    assert not (tmp_path / "corporate_actions.csv").exists()


def test_request_error_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(loader.GeneratorError, match="error_code=10004006"):
        build(tmp_path, rows_by_query={}, fail_code="10004006")
    assert not (tmp_path / "source_records.json").exists()


def test_failed_build_does_not_clobber_existing_archive(tmp_path: Path) -> None:
    out = tmp_path
    (out / "corporate_actions.csv").write_text("sentinel-csv\n", encoding="utf-8")
    (out / "source_records.json").write_text("sentinel-json\n", encoding="utf-8")
    with pytest.raises(loader.GeneratorError):
        build(out, rows_by_query={}, fail_code="10002007")
    assert (out / "corporate_actions.csv").read_text(encoding="utf-8") == "sentinel-csv\n"
    assert (out / "source_records.json").read_text(encoding="utf-8") == "sentinel-json\n"


def test_output_is_utf8_no_bom_and_lf(tmp_path: Path) -> None:
    rows = [make_row(dividOperateDate="2025-06-30")]
    build(tmp_path, rows_by_query={("sh.600000", "2025"): rows})
    for name in ("corporate_actions.csv", "source_records.json"):
        content = (tmp_path / name).read_bytes()
        assert not content.startswith(b"\xef\xbb\xbf")
        assert b"\r\n" not in content


def test_manifest_records_receipts_and_dependency_identity(tmp_path: Path) -> None:
    tickers = [f"sh.{600000 + i:06d}" for i in range(49)]
    rows_by_query = {
        (code, str(year)): [
            make_row(
                dividOperateDate=f"{year}-06-30",
                dividCashPsBeforeTax="1.0",
            )
        ]
        for code in tickers
        for year in YEARS
    }
    build(
        tmp_path,
        rows_by_query=rows_by_query,
        tickers=tickers,
    )
    manifest = json.loads((tmp_path / "source_records.json").read_text(encoding="utf-8"))
    assert manifest["schema"] == "corporate_action_operate_archive/v1"
    assert manifest["archive_id"] == "corporate_action_operate_2020_2025/v1"
    assert manifest["years"] == [str(year) for year in YEARS]
    assert manifest["coverage_start"] == "2020-01-01"
    assert manifest["coverage_end"] == "2025-12-31"
    assert manifest["baostock_version"] == _BAOSTOCK_VERSION
    assert manifest["baostock_module_sha256"] == dict(sorted(_MODULE_HASHES.items()))
    assert manifest["total_receipts"] == 49 * len(YEARS)
    assert manifest["total_rows"] == 49 * len(YEARS)
    assert len(manifest["tickers"]) == 49
    for receipt in manifest["per_request"]:
        assert receipt["yearType"] == "operate"
        assert receipt["error_code"] == "0"
        assert receipt["response_payload_sha256"] is not None
        assert receipt["max_event_date"] == f"{receipt['year']}-06-30"


def test_ticker_count_validation() -> None:
    with pytest.raises(loader.GeneratorError, match="expected 49 tickers"):
        loader.build_operate_archive(
            tickers=["sh.600000"],
            years=YEARS,
            out_dir=Path("ignored"),
            query_fn=lambda code, year, yt: FakeResult([]),
            baostock_version=_BAOSTOCK_VERSION,
            baostock_module_sha256=_MODULE_HASHES,
            official_tickers=["sh.600000"],
            tickers_expected=49,
        )


def test_cli_network_gate_is_off_by_default() -> None:
    with pytest.raises(SystemExit) as excinfo:
        loader.main(["--tickers-file", "tickers.txt"])
    assert excinfo.value.code == 2


def test_rejects_invalid_ticker_format() -> None:
    with pytest.raises(loader.GeneratorError, match="invalid ticker format"):
        build(
            tmp_path=Path("ignored"),
            rows_by_query={},
            tickers=["xx.600000"],
        )


def test_rejects_duplicate_tickers() -> None:
    with pytest.raises(loader.GeneratorError, match="duplicate tickers"):
        build(
            tmp_path=Path("ignored"),
            rows_by_query={},
            tickers=["sh.600000", "sh.600000"],
        )


def test_rejects_ticker_membership_drift() -> None:
    official = ["sh.600000", "sh.600001"]
    with pytest.raises(loader.GeneratorError, match="official universe"):
        loader.build_operate_archive(
            tickers=["sh.600000", "sh.600002"],
            years=YEARS,
            out_dir=Path("ignored"),
            query_fn=lambda code, year, yt: FakeResult([], code=code),
            baostock_version=_BAOSTOCK_VERSION,
            baostock_module_sha256=_MODULE_HASHES,
            official_tickers=official,
            tickers_expected=None,
        )


def test_rejects_missing_official_tickers() -> None:
    with pytest.raises(loader.GeneratorError, match="cannot self-authorize"):
        loader.build_operate_archive(
            tickers=["sh.600000"],
            years=YEARS,
            out_dir=Path("ignored"),
            query_fn=lambda code, year, yt: FakeResult([], code=code),
            baostock_version=_BAOSTOCK_VERSION,
            baostock_module_sha256=_MODULE_HASHES,
            tickers_expected=None,
        )


def test_rejects_returned_code_mismatch(tmp_path: Path) -> None:
    with pytest.raises(loader.GeneratorError, match="request failed"):
        build(
            tmp_path,
            rows_by_query={("sh.600000", "2025"): [make_row(dividOperateDate="2025-06-30")]},
            wrong_returned_code=True,
        )


def test_rejects_row_width_mismatch(tmp_path: Path) -> None:
    malformed = make_row(dividOperateDate="2025-06-30")[:-1]
    with pytest.raises(loader.GeneratorError, match="request failed"):
        build(
            tmp_path,
            rows_by_query={("sh.600000", "2025"): [malformed]},
        )


def test_rejects_blank_operate_date(tmp_path: Path) -> None:
    with pytest.raises(loader.GeneratorError, match="request failed"):
        build(
            tmp_path,
            rows_by_query={("sh.600000", "2025"): [make_row(dividOperateDate="")]},
        )


def test_rejects_operate_date_outside_requested_year(tmp_path: Path) -> None:
    with pytest.raises(loader.GeneratorError, match="request failed"):
        build(
            tmp_path,
            rows_by_query={
                ("sh.600000", "2025"): [make_row(dividOperateDate="2024-06-30")]
            },
        )


def test_csv_quotes_commas_quotes_and_linebreaks(tmp_path: Path) -> None:
    row = make_row(dividOperateDate="2025-06-30", dividCashStock='a,b"c\nd')
    build(tmp_path, rows_by_query={("sh.600000", "2025"): [row]})
    text = (tmp_path / "corporate_actions.csv").read_text(encoding="utf-8")
    parsed = list(csv_module.reader(io.StringIO(text)))
    assert len(parsed) == 2
    assert len(parsed[1]) == len(loader.CANONICAL_COLUMNS)
    index = loader.CANONICAL_COLUMNS.index("dividCashStock")
    assert parsed[1][index] == 'a,b"c\nd'


def test_pair_replace_rolls_back_on_second_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = [make_row(dividOperateDate="2025-06-30")]
    build(tmp_path, rows_by_query={("sh.600000", "2025"): rows})
    old_csv = (tmp_path / "corporate_actions.csv").read_bytes()
    old_records = (tmp_path / "source_records.json").read_bytes()
    real_replace = loader.os.replace
    calls = {"n": 0}

    def flaky_replace(source: object, destination: object) -> None:
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError("simulated second replace failure")
        real_replace(source, destination)

    monkeypatch.setattr(loader.os, "replace", flaky_replace)
    with pytest.raises(OSError, match="simulated second replace failure"):
        build(tmp_path, rows_by_query={("sh.600000", "2025"): rows})
    assert (tmp_path / "corporate_actions.csv").read_bytes() == old_csv
    assert (tmp_path / "source_records.json").read_bytes() == old_records


def test_cross_ticker_same_action_fields_coexist(tmp_path: Path) -> None:
    row = make_row(dividOperateDate="2025-06-30", dividCashPsBeforeTax="1.0")
    tickers = ["sh.600000", "sz.000001"]
    build(
        tmp_path,
        rows_by_query={
            ("sh.600000", "2025"): [row],
            ("sz.000001", "2025"): [list(row)],
        },
        tickers=tickers,
        official_tickers=tickers,
    )
    csv_lines = (tmp_path / "corporate_actions.csv").read_text(encoding="utf-8").splitlines()
    assert len(csv_lines) == 3  # header + both cross-ticker actions
    body = "\n".join(csv_lines[1:])
    assert "sh.600000" in body and "sz.000001" in body
    manifest = json.loads((tmp_path / "source_records.json").read_text(encoding="utf-8"))
    assert manifest["total_rows"] == 2
    assert manifest["duplicate_count"] == 0


def test_same_identity_different_pay_date_is_duplicate(tmp_path: Path) -> None:
    row1 = make_row(
        dividOperateDate="2025-06-30",
        dividCashPsBeforeTax="1.0",
        dividPayDate="2025-07-01",
    )
    row2 = make_row(
        dividOperateDate="2025-06-30",
        dividCashPsBeforeTax="1.0",
        dividPayDate="2025-07-02",
    )
    build(tmp_path, rows_by_query={("sh.600000", "2025"): [row1, row2]})
    csv_lines = (tmp_path / "corporate_actions.csv").read_text(encoding="utf-8").splitlines()
    assert len(csv_lines) == 2  # header + 1 deduplicated canonical action
    manifest = json.loads((tmp_path / "source_records.json").read_text(encoding="utf-8"))
    assert manifest["total_rows"] == 1
    assert manifest["duplicate_count"] == 1
