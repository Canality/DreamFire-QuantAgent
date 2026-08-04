from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest
from jiuwenswarm.quant.market_data_provider import (
    BenchmarkPayload,
    MarketDataFetchError,
    ProviderPayload,
    ProviderSpec,
    default_provider_specs,
    fetch_baostock,
    fetch_market_data_bundle,
    fetch_sina,
    fetch_tencent,
    fetch_yfinance,
)
from jiuwenswarm.quant.market_data_service import ProviderEvidence, diagnose_market_data
from jiuwenswarm.quant.stock_pool import ALL_STOCKS


def _raw_frame(
    ticker: str,
    *,
    volume: float = 10.0,
    close_scale: float = 1.0,
) -> pd.DataFrame:
    dates = pd.bdate_range("2025-01-02", periods=100)
    base = 10.0 + ALL_STOCKS.index(ticker)
    closes = (base + np.arange(len(dates)) * 0.01) * close_scale
    return pd.DataFrame(
        {
            "open": closes * 0.999,
            "high": closes * 1.002,
            "low": closes * 0.998,
            "close": closes,
            "volume": np.full(len(dates), volume),
        },
        index=dates,
    )


def _specs(*, audit_enabled: bool = True) -> tuple[ProviderSpec, ...]:
    buckets = {
        "sina": set(ALL_STOCKS[:10]),
        "tencent": set(ALL_STOCKS[10:20]),
        "akshare": set(ALL_STOCKS[20:30]),
        "baostock": set(ALL_STOCKS[30:40]),
        "yfinance": set(ALL_STOCKS[40:]),
    }
    multipliers = {
        "sina": 1.0,
        "tencent": 100.0,
        "akshare": 100.0,
        "baostock": 1.0,
        "yfinance": 1.0,
    }
    specs: list[ProviderSpec] = []

    def make_fetch(
        covered: set[str],
    ):
        calls = 0

        def fetch(
            tickers: Sequence[str],
            _start: str,
            _end: str,
        ) -> ProviderPayload:
            nonlocal calls
            calls += 1
            selected = (
                [ticker for ticker in tickers if ticker in covered]
                if calls == 1
                else list(tickers) if audit_enabled else []
            )
            return ProviderPayload(
                frames={ticker: _raw_frame(ticker) for ticker in selected},
                errors=(),
            )

        return fetch

    for name, primary_tickers in buckets.items():
        specs.append(
            ProviderSpec(
                name=name,
                fetcher=make_fetch(primary_tickers),
                evidence=ProviderEvidence(
                    name=name,
                    source_endpoint=f"https://example.invalid/{name}",
                    price_adjustment="raw_unadjusted",
                    raw_volume_unit=(
                        "lots_100_shares" if multipliers[name] == 100 else "shares"
                    ),
                    volume_multiplier_to_shares=multipliers[name],
                ),
            )
        )
    return tuple(specs)


def _benchmark(_start: str, _end: str) -> BenchmarkPayload:
    dates = pd.bdate_range("2025-01-02", periods=100)
    return BenchmarkPayload(
        closes=pd.Series(3000.0 + np.arange(len(dates)), index=dates, name="CSI300"),
        provider="benchmark_test",
        source_endpoint="https://example.invalid/csi300",
        errors=(),
    )


def _as_of() -> datetime:
    return datetime.combine(
        pd.Timestamp("2025-05-21").date(),
        time(16, 0),
        tzinfo=ZoneInfo("Asia/Shanghai"),
    )


def test_progressive_fallback_builds_49_ticker_canonical_bundle() -> None:
    bundle = fetch_market_data_bundle(
        ALL_STOCKS,
        "2025-01-02",
        "2025-05-21",
        as_of_time=_as_of(),
        providers=_specs(),
        benchmark_fetcher=_benchmark,
    )

    assert list(bundle.closes.columns) == list(ALL_STOCKS)
    assert bundle.opens.shape == bundle.highs.shape == bundle.lows.shape
    assert bundle.closes.shape == bundle.volumes.shape == (100, 49)
    assert list(bundle.provider_ledger.values()).count("sina") == 10
    assert list(bundle.provider_ledger.values()).count("yfinance") == 9
    assert bundle.provider_stats["sina"]["primary_requested"] == 49
    assert bundle.provider_stats["tencent"]["primary_requested"] == 39
    assert bundle.provider_stats["yfinance"]["primary_requested"] == 9
    assert diagnose_market_data(bundle, ALL_STOCKS).passed


def test_volume_is_converted_to_shares_from_provider_evidence() -> None:
    bundle = fetch_market_data_bundle(
        ALL_STOCKS,
        "2025-01-02",
        "2025-05-21",
        as_of_time=_as_of(),
        providers=_specs(),
        benchmark_fetcher=_benchmark,
    )

    assert bundle.volumes[ALL_STOCKS[0]].iloc[-1] == 10.0
    assert bundle.volumes[ALL_STOCKS[10]].iloc[-1] == 1000.0
    assert bundle.volumes[ALL_STOCKS[20]].iloc[-1] == 1000.0
    assert bundle.volumes[ALL_STOCKS[30]].iloc[-1] == 10.0


def test_secondary_source_is_independent_for_every_ticker() -> None:
    bundle = fetch_market_data_bundle(
        ALL_STOCKS,
        "2025-01-02",
        "2025-05-21",
        as_of_time=_as_of(),
        providers=_specs(),
        benchmark_fetcher=_benchmark,
    )

    audit_ledger = bundle.provider_stats["secondary_audit"]["provider_ledger"]
    assert set(audit_ledger) == set(ALL_STOCKS)
    assert all(
        audit_ledger[ticker] != bundle.provider_ledger[ticker]
        for ticker in ALL_STOCKS
    )
    assert bundle.secondary_closes.notna().sum().min() >= 20


def test_missing_primary_coverage_fails_closed() -> None:
    specs = _specs()
    truncated = specs[:-1]

    with pytest.raises(MarketDataFetchError, match="primary coverage"):
        fetch_market_data_bundle(
            ALL_STOCKS,
            "2025-01-02",
            "2025-05-21",
            as_of_time=_as_of(),
            providers=truncated,
            benchmark_fetcher=_benchmark,
        )


def test_missing_independent_secondary_coverage_fails_closed() -> None:
    with pytest.raises(MarketDataFetchError, match="secondary coverage"):
        fetch_market_data_bundle(
            ALL_STOCKS,
            "2025-01-02",
            "2025-05-21",
            as_of_time=_as_of(),
            providers=_specs(audit_enabled=False),
            benchmark_fetcher=_benchmark,
        )


def test_missing_benchmark_fails_closed() -> None:
    def missing_benchmark(_start: str, _end: str) -> BenchmarkPayload:
        return BenchmarkPayload(
            closes=pd.Series(dtype=float),
            provider="none",
            source_endpoint="",
            errors=("unavailable",),
        )

    with pytest.raises(MarketDataFetchError, match="benchmark"):
        fetch_market_data_bundle(
            ALL_STOCKS,
            "2025-01-02",
            "2025-05-21",
            as_of_time=_as_of(),
            providers=_specs(),
            benchmark_fetcher=missing_benchmark,
        )


def test_current_incomplete_session_is_rejected() -> None:
    before_close = _as_of().replace(hour=14)
    with pytest.raises(MarketDataFetchError, match="incomplete trading session"):
        fetch_market_data_bundle(
            ALL_STOCKS,
            "2025-01-02",
            "2025-05-21",
            as_of_time=before_close,
            providers=_specs(),
            benchmark_fetcher=_benchmark,
        )


def test_default_provider_units_and_adjustment_are_explicit() -> None:
    specs = {spec.name: spec for spec in default_provider_specs()}

    assert list(specs) == ["sina", "tencent", "akshare", "baostock", "yfinance"]
    assert specs["sina"].evidence.volume_multiplier_to_shares == 1.0
    assert specs["tencent"].evidence.volume_multiplier_to_shares == 100.0
    assert specs["akshare"].evidence.volume_multiplier_to_shares == 100.0
    assert specs["baostock"].evidence.volume_multiplier_to_shares == 1.0
    assert specs["yfinance"].evidence.volume_multiplier_to_shares == 1.0
    assert {
        spec.evidence.price_adjustment for spec in specs.values()
    } == {"raw_unadjusted"}


class _FakeResponse:
    def __init__(self, payload) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self._payload


class _FakeHttp:
    def get(self, url, params, **_):
        if "sina" in url:
            return _FakeResponse(
                [
                    {
                        "day": "2025-01-02",
                        "open": "10.00",
                        "high": "10.30",
                        "low": "9.90",
                        "close": "10.10",
                        "volume": "1000",
                    }
                ]
            )
        symbol = params["param"].split(",", 1)[0]
        return _FakeResponse(
            {
                "code": 0,
                "msg": "",
                "data": {
                    symbol: {
                        "day": [
                            ["2025-01-02", "10.00", "10.10", "10.30", "9.90", "10"]
                        ]
                    }
                },
            }
        )


def test_sina_and_tencent_parse_full_raw_ohlcv() -> None:
    ticker = "600000.SH"
    sina = fetch_sina([ticker], "2025-01-01", "2025-01-31", http=_FakeHttp())
    tencent = fetch_tencent(
        [ticker],
        "2025-01-01",
        "2025-01-31",
        http=_FakeHttp(),
    )

    assert sina.errors == tencent.errors == ()
    assert list(sina.frames[ticker].columns) == ["open", "high", "low", "close", "volume"]
    assert sina.frames[ticker].iloc[0].tolist() == [10.0, 10.3, 9.9, 10.1, 1000.0]
    assert tencent.frames[ticker].iloc[0].tolist() == [10.0, 10.3, 9.9, 10.1, 10.0]


def test_yfinance_end_date_is_converted_from_inclusive_to_exclusive() -> None:
    calls: list[dict] = []

    class FakeYFinance:
        @staticmethod
        def download(_ticker, **kwargs):
            calls.append(kwargs)
            index = pd.DatetimeIndex(["2025-01-31"])
            return pd.DataFrame(
                {
                    "Open": [10.0],
                    "High": [10.3],
                    "Low": [9.9],
                    "Close": [10.1],
                    "Volume": [1000.0],
                },
                index=index,
            )

    payload = fetch_yfinance(
        ["600000.SH"],
        "2025-01-01",
        "2025-01-31",
        yf_module=FakeYFinance(),
    )

    assert payload.errors == ()
    assert calls[0]["end"] == "2025-02-01"
    assert payload.frames["600000.SH"].index[-1] == pd.Timestamp("2025-01-31")


def test_baostock_uses_exchange_prefix_symbol_and_raw_ohlcv() -> None:
    calls: list[str] = []

    class Status:
        error_code = "0"
        error_msg = ""

    class Result:
        error_code = "0"
        error_msg = ""
        fields = ("date", "open", "high", "low", "close", "volume")

        def __init__(self) -> None:
            self._pending = True

        def next(self) -> bool:
            pending = self._pending
            self._pending = False
            return pending

        @staticmethod
        def get_row_data() -> list[str]:
            return ["2025-01-02", "10.00", "10.30", "9.90", "10.10", "1000"]

    class FakeBaoStock:
        @staticmethod
        def login() -> Status:
            return Status()

        @staticmethod
        def logout() -> Status:
            return Status()

        @staticmethod
        def query_history_k_data_plus(code, *_args, **_kwargs) -> Result:
            calls.append(code)
            return Result()

    payload = fetch_baostock(
        ["600000.SH"],
        "2025-01-01",
        "2025-01-31",
        bs_module=FakeBaoStock(),
    )

    assert payload.errors == ()
    assert calls == ["sh.600000"]
    assert payload.frames["600000.SH"].iloc[0].tolist() == [
        10.0,
        10.3,
        9.9,
        10.1,
        1000.0,
    ]


def test_retrieval_timestamp_is_not_before_as_of() -> None:
    bundle = fetch_market_data_bundle(
        ALL_STOCKS,
        "2025-01-02",
        "2025-05-21",
        as_of_time=_as_of(),
        providers=_specs(),
        benchmark_fetcher=_benchmark,
        now=lambda: _as_of() + timedelta(minutes=1),
    )

    assert bundle.retrieved_at > bundle.as_of_time
