from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest
from jiuwenswarm.quant import factor_evidence_provider
from jiuwenswarm.quant.candidate_factors import (
    AVAILABLE,
    INSUFFICIENT_HISTORY,
    INVALID_PRICE_WINDOW,
    ZERO_OR_INVALID_VOLATILITY,
    CalendarEvidence,
    CorporateActionEvidence,
    FactorInputError,
    PointInTimeFactorInput,
    compute_trend_snapshot,
)
from jiuwenswarm.quant.factor_registry import FACTOR_REGISTRY

SHANGHAI = ZoneInfo("Asia/Shanghai")
EVIDENCE_HASH = "a" * 64
TEST_TRUSTED_EVIDENCE_KEYS: set[tuple[str, str, str, str, str]] = set()


@pytest.fixture(autouse=True)
def _test_only_trusted_evidence_manifest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Install an explicit test-only trust root; runtime default stays empty."""

    TEST_TRUSTED_EVIDENCE_KEYS.clear()
    monkeypatch.setattr(
        factor_evidence_provider,
        "trusted_evidence_contains",
        lambda **item: (
            item["kind"],
            item["authority"],
            item["source_version"],
            item["source_sha256"],
            item["evidence_hash"],
        )
        in TEST_TRUSTED_EVIDENCE_KEYS,
    )


def _trust_for_test(evidence: CalendarEvidence | CorporateActionEvidence) -> None:
    if isinstance(evidence, CalendarEvidence):
        kind = "calendar"
        evidence_hash = evidence.evidence_hash
    else:
        kind = "corporate_action_operate"
        evidence_hash = evidence.archive_evidence_sha256
    TEST_TRUSTED_EVIDENCE_KEYS.add(
        (
            kind,
            evidence.authority,
            evidence.source_version,
            evidence.source_sha256,
            evidence_hash,
        )
    )


def _sessions(rows: int) -> pd.DatetimeIndex:
    return pd.bdate_range("2025-01-02", periods=rows)


def _input(
    closes: pd.DataFrame,
    *,
    sessions: pd.DatetimeIndex | None = None,
    decision_time: datetime | None = None,
    adjustment_policy: str = "point_in_time_adjusted",
    calendar_evidence: CalendarEvidence | None = None,
    corporate_action_evidence: CorporateActionEvidence | None = None,
    forecast_horizon: int = 20,
) -> PointInTimeFactorInput:
    canonical = closes.index if sessions is None else sessions
    final_date = pd.Timestamp(canonical[-1]).date()
    decision = decision_time or datetime(
        final_date.year,
        final_date.month,
        final_date.day,
        15,
        30,
        tzinfo=SHANGHAI,
    )
    calendar = calendar_evidence or CalendarEvidence(
        authority="SSE_SZSE_OFFICIAL_CALENDAR_ARCHIVE",
        source_version="test-fixture/v1",
        source_sha256=EVIDENCE_HASH,
        calendar_id="SSE_SZSE_A_SHARE_CONFIRMED_THROUGH_20260804",
        sessions=tuple(pd.Timestamp(item).date().isoformat() for item in canonical),
    )
    expected_result = {
        "point_in_time_adjusted": "POINT_IN_TIME_ADJUSTED",
        "verified_no_action_window": "NO_CORPORATE_ACTION_IN_WINDOW",
        "scale_invariant_qfq_retrospective": "SCALE_INVARIANT_QFQ_RETROSPECTIVE",
    }.get(adjustment_policy, "UNVERIFIED")
    corporate = corporate_action_evidence or CorporateActionEvidence(
        authority="BAOSTOCK_QUERY_DIVIDEND_DATA_OPERATE",
        source_version="test-fixture/v1",
        source_sha256="b" * 64,
        archive_evidence_sha256="c" * 64,
        policy=adjustment_policy,
        window_start=pd.Timestamp(canonical[0]).date().isoformat(),
        window_end=pd.Timestamp(canonical[-1]).date().isoformat(),
        ticker_results=tuple(
            (str(ticker), expected_result) for ticker in sorted(closes.columns)
        ),
        in_window_actions=factor_evidence_provider.operate_window_projection(
            window_start=pd.Timestamp(canonical[0]).date().isoformat(),
            window_end=pd.Timestamp(canonical[-1]).date().isoformat(),
            tickers=tuple(sorted(str(t) for t in closes.columns)),
        ),
    )
    _trust_for_test(calendar)
    _trust_for_test(corporate)
    return PointInTimeFactorInput(
        closes=closes,
        canonical_sessions=canonical,
        decision_time=decision,
        adjustment_policy=adjustment_policy,
        calendar_evidence=calendar,
        corporate_action_evidence=corporate,
        forecast_horizon=forecast_horizon,
    )


def _pattern_prices(rows: int) -> pd.Series:
    returns = np.array([0.012, -0.004, 0.008, 0.003, -0.002], dtype=float)
    repeated = np.resize(returns, rows - 1)
    values = np.r_[100.0, 100.0 * np.cumprod(1.0 + repeated)]
    return pd.Series(values, index=_sessions(rows), name="AAA")


def test_all_twelve_formulas_match_preregistered_math() -> None:
    series = _pattern_prices(251)
    snapshot = compute_trend_snapshot(_input(series.to_frame()))
    values = snapshot.values.loc["AAA"]

    for lookback in (5, 10, 20, 60, 120, 250):
        expected = series.iloc[-1] / series.iloc[-lookback - 1] - 1.0
        assert values[f"momentum_{lookback}"] == pytest.approx(expected)

    for lookback in (20, 60):
        momentum = series.iloc[-1] / series.iloc[-lookback - 1] - 1.0
        annualized_vol = series.pct_change().iloc[-lookback:].std(ddof=1) * np.sqrt(252)
        assert values[f"risk_adjusted_momentum_{lookback}"] == pytest.approx(
            momentum / annualized_vol
        )

    signs = [
        np.sign(series.iloc[-1] / series.iloc[-lookback - 1] - 1.0)
        for lookback in (5, 10, 20)
    ]
    assert values["trend_consistency_5_10_20"] == pytest.approx(np.mean(signs))
    assert values["price_vs_ma20"] == pytest.approx(
        series.iloc[-1] / series.iloc[-20:].mean() - 1.0
    )
    assert values["price_vs_ma60"] == pytest.approx(
        series.iloc[-1] / series.iloc[-60:].mean() - 1.0
    )
    r20 = series.iloc[-1] / series.iloc[-21] - 1.0
    r60 = series.iloc[-1] / series.iloc[-61] - 1.0
    assert values["momentum_acceleration"] == pytest.approx(r20 - r60 / 3.0)
    assert set(snapshot.status.loc["AAA"]) == {AVAILABLE}


def test_minimum_lookback_is_per_factor_and_never_shortened() -> None:
    sessions = _sessions(20)
    closes = pd.DataFrame({"AAA": np.linspace(100.0, 120.0, 20)}, index=sessions)
    snapshot = compute_trend_snapshot(_input(closes))
    assert snapshot.status.loc["AAA", "price_vs_ma20"] == AVAILABLE
    assert snapshot.status.loc["AAA", "momentum_20"] == INSUFFICIENT_HISTORY
    assert np.isnan(snapshot.values.loc["AAA", "momentum_20"])

    sessions_250 = _sessions(250)
    closes_250 = pd.DataFrame(
        {"AAA": np.linspace(100.0, 150.0, 250)}, index=sessions_250
    )
    short = compute_trend_snapshot(_input(closes_250))
    assert short.status.loc["AAA", "momentum_250"] == INSUFFICIENT_HISTORY
    assert np.isnan(short.values.loc["AAA", "momentum_250"])

    series_251 = _pattern_prices(251)
    complete = compute_trend_snapshot(_input(series_251.to_frame()))
    assert complete.status.loc["AAA", "momentum_250"] == AVAILABLE


def test_zero_volatility_is_unavailable_not_a_fabricated_zero() -> None:
    sessions = _sessions(61)
    closes = pd.DataFrame({"AAA": 100.0}, index=sessions)
    snapshot = compute_trend_snapshot(_input(closes))

    assert snapshot.values.loc["AAA", "momentum_20"] == pytest.approx(0.0)
    assert snapshot.status.loc["AAA", "momentum_20"] == AVAILABLE
    for factor_id in ("risk_adjusted_momentum_20", "risk_adjusted_momentum_60"):
        assert np.isnan(snapshot.values.loc["AAA", factor_id])
        assert snapshot.status.loc["AAA", factor_id] == ZERO_OR_INVALID_VOLATILITY


def test_invalid_price_is_ticker_local_and_unavailable() -> None:
    sessions = _sessions(61)
    closes = pd.DataFrame(
        {
            "AAA": np.linspace(100.0, 130.0, 61),
            "BBB": np.linspace(80.0, 100.0, 61),
        },
        index=sessions,
    )
    closes.loc[sessions[-2], "BBB"] = np.nan
    snapshot = compute_trend_snapshot(_input(closes))
    assert snapshot.status.loc["AAA", "momentum_5"] == AVAILABLE
    assert snapshot.status.loc["BBB", "momentum_5"] == INVALID_PRICE_WINDOW
    assert np.isnan(snapshot.values.loc["BBB", "momentum_5"])


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("decision_time", datetime(2025, 1, 30, 15, 30), "timezone-aware"),  # noqa: DTZ001
        ("adjustment_policy", "raw_unadjusted", "corporate-action policy"),
        ("forecast_horizon", 5, "official forecast horizon"),
    ],
)
def test_input_contract_rejects_unverified_or_wrong_metadata(
    field: str,
    value: object,
    message: str,
) -> None:
    series = _pattern_prices(61)
    kwargs = {field: value}
    with pytest.raises(FactorInputError, match=message):
        compute_trend_snapshot(_input(series.to_frame(), **kwargs))


def test_decision_close_and_future_rows_fail_closed() -> None:
    series = _pattern_prices(61)
    final = series.index[-1]
    before_close = datetime(
        final.year,
        final.month,
        final.day,
        14,
        59,
        tzinfo=SHANGHAI,
    )
    with pytest.raises(FactorInputError, match="decision close"):
        compute_trend_snapshot(
            _input(series.to_frame(), decision_time=before_close)
        )

    prior = series.index[-2]
    prior_close = datetime(
        prior.year,
        prior.month,
        prior.day,
        15,
        30,
        tzinfo=SHANGHAI,
    )
    with pytest.raises(FactorInputError, match="after decision_time"):
        compute_trend_snapshot(_input(series.to_frame(), decision_time=prior_close))


def test_canonical_sessions_must_match_exactly() -> None:
    series = _pattern_prices(61)
    missing = series.drop(series.index[-10])
    with pytest.raises(FactorInputError, match="canonical sessions"):
        compute_trend_snapshot(
            _input(missing.to_frame(), sessions=series.index)
        )

    duplicated = series.to_frame()
    duplicated.index = pd.DatetimeIndex(list(series.index[:-1]) + [series.index[-2]])
    with pytest.raises(FactorInputError, match="unique and increasing"):
        compute_trend_snapshot(_input(duplicated, sessions=duplicated.index))


def test_calendar_evidence_binds_full_sessions_and_authority() -> None:
    series = _pattern_prices(61)
    valid = _input(series.to_frame())
    missing_session = replace(
        valid.calendar_evidence,
        sessions=valid.calendar_evidence.sessions[:-2]
        + valid.calendar_evidence.sessions[-1:],
    )
    with pytest.raises(FactorInputError, match="archived calendar evidence"):
        compute_trend_snapshot(
            replace(valid, calendar_evidence=missing_session)
        )

    zero_source = replace(
        valid.calendar_evidence,
        source_sha256="0" * 64,
    )
    with pytest.raises(FactorInputError, match="source_sha256"):
        compute_trend_snapshot(replace(valid, calendar_evidence=zero_source))

    wrong_authority = replace(valid.calendar_evidence, authority="self-certified")
    with pytest.raises(FactorInputError, match="authority"):
        compute_trend_snapshot(
            replace(valid, calendar_evidence=wrong_authority)
        )


def test_unregistered_source_provenance_fails_closed() -> None:
    series = _pattern_prices(61)
    valid = _input(series.to_frame())

    invented_calendar = replace(
        valid.calendar_evidence,
        source_version="invented/v999",
        source_sha256="c" * 64,
    )
    with pytest.raises(FactorInputError, match="trusted source manifest"):
        compute_trend_snapshot(
            replace(valid, calendar_evidence=invented_calendar)
        )

    invented_corporate_action = replace(
        valid.corporate_action_evidence,
        source_version="invented/v999",
        source_sha256="d" * 64,
    )
    with pytest.raises(FactorInputError, match="trusted source manifest"):
        compute_trend_snapshot(
            replace(
                valid,
                corporate_action_evidence=invented_corporate_action,
            )
        )

    TEST_TRUSTED_EVIDENCE_KEYS.clear()
    with pytest.raises(FactorInputError, match="trusted source manifest"):
        compute_trend_snapshot(valid)


def test_corporate_action_evidence_binds_policy_window_and_tickers() -> None:
    series = _pattern_prices(61)
    valid = _input(series.to_frame())

    wrong_window = replace(
        valid.corporate_action_evidence,
        window_start=series.index[1].date().isoformat(),
    )
    with pytest.raises(FactorInputError, match="cover the input window"):
        compute_trend_snapshot(
            replace(valid, corporate_action_evidence=wrong_window)
        )

    wrong_ticker = replace(
        valid.corporate_action_evidence,
        ticker_results=(("BBB", "POINT_IN_TIME_ADJUSTED"),),
    )
    with pytest.raises(FactorInputError, match="exactly cover tickers"):
        compute_trend_snapshot(
            replace(valid, corporate_action_evidence=wrong_ticker)
        )

    wrong_result = replace(
        valid.corporate_action_evidence,
        ticker_results=(("AAA", "NO_CORPORATE_ACTION_IN_WINDOW"),),
    )
    with pytest.raises(FactorInputError, match="does not satisfy policy"):
        compute_trend_snapshot(
            replace(valid, corporate_action_evidence=wrong_result)
        )


def test_snapshot_hash_is_deterministic_and_binds_inputs() -> None:
    series = _pattern_prices(61)
    first = compute_trend_snapshot(_input(series.to_frame()))
    second = compute_trend_snapshot(_input(series.to_frame()))
    assert first.input_hash == second.input_hash
    assert first.snapshot_hash == second.snapshot_hash
    assert first.to_dict() == second.to_dict()
    assert first.registry_hash
    assert first.values.shape == (1, len(FACTOR_REGISTRY))
    assert first.status.shape == first.values.shape

    changed = series.copy()
    changed.iloc[-1] *= 1.001
    third = compute_trend_snapshot(_input(changed.to_frame()))
    assert third.input_hash != first.input_hash
    assert third.snapshot_hash != first.snapshot_hash


def test_ticker_column_order_is_canonical_for_hashes_and_values() -> None:
    series = _pattern_prices(61)
    closes = pd.DataFrame(
        {"BBB": series.to_numpy() * 0.8, "AAA": series.to_numpy()},
        index=series.index,
    )
    first = compute_trend_snapshot(_input(closes))
    second = compute_trend_snapshot(_input(closes[["AAA", "BBB"]]))
    assert list(first.values.index) == ["AAA", "BBB"]
    assert first.input_hash == second.input_hash
    assert first.snapshot_hash == second.snapshot_hash
    pd.testing.assert_frame_equal(first.values, second.values)


def test_non_numeric_prices_are_rejected_and_missing_values_remain_local() -> None:
    series = _pattern_prices(61)
    bad = series.astype(object).to_frame()
    bad.iloc[-1, 0] = "not-a-price"
    with pytest.raises(FactorInputError, match="must be real numeric or missing"):
        compute_trend_snapshot(_input(bad))

    complex_prices = series.astype(complex).to_frame()
    complex_prices.iloc[-1, 0] += 7j
    with pytest.raises(FactorInputError, match="must be real numeric or missing"):
        compute_trend_snapshot(_input(complex_prices))

    bool_prices = pd.DataFrame({"AAA": [True] * 61}, index=series.index)
    with pytest.raises(FactorInputError, match="must be real numeric or missing"):
        compute_trend_snapshot(_input(bool_prices))

    object_numeric = series.astype(object).to_frame()
    object_snapshot = compute_trend_snapshot(_input(object_numeric))
    assert object_snapshot.status.loc["AAA", "momentum_5"] == AVAILABLE

    closes = pd.DataFrame(
        {"AAA": series.to_numpy(), "BBB": series.to_numpy()},
        index=series.index,
    )
    closes.loc[series.index[-1], "BBB"] = pd.NA
    snapshot = compute_trend_snapshot(_input(closes))
    assert snapshot.status.loc["AAA", "momentum_5"] == AVAILABLE
    assert snapshot.status.loc["BBB", "momentum_5"] == INVALID_PRICE_WINDOW


@pytest.mark.parametrize(
    "registry",
    [
        FACTOR_REGISTRY[:1],
        tuple(reversed(FACTOR_REGISTRY)),
        FACTOR_REGISTRY + (FACTOR_REGISTRY[0],),
    ],
)
def test_public_snapshot_api_rejects_registry_injection(registry: object) -> None:
    series = _pattern_prices(61)
    with pytest.raises(TypeError, match="registry"):
        compute_trend_snapshot(  # type: ignore[call-arg]
            _input(series.to_frame()),
            registry=registry,
        )


def test_snapshot_serialization_detects_dataframe_mutation() -> None:
    series = _pattern_prices(61)
    snapshot = compute_trend_snapshot(_input(series.to_frame()))
    snapshot.values.loc["AAA", "momentum_20"] = 999.0
    with pytest.raises(ValueError, match="snapshot hash mismatch"):
        snapshot.to_dict()


def test_snapshot_serialization_uses_null_for_unavailable() -> None:
    sessions = _sessions(20)
    closes = pd.DataFrame({"AAA": np.linspace(100.0, 120.0, 20)}, index=sessions)
    payload = compute_trend_snapshot(_input(closes)).to_dict()
    assert payload["values"]["AAA"]["momentum_20"] is None
    assert payload["status"]["AAA"]["momentum_20"] == INSUFFICIENT_HISTORY


def test_input_object_is_frozen() -> None:
    series = _pattern_prices(61)
    contract = _input(series.to_frame())
    with pytest.raises(FrozenInstanceError):
        contract.forecast_horizon = 5  # type: ignore[misc]
