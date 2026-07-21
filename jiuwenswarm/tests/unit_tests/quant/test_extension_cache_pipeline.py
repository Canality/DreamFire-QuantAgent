from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

from jiuwenswarm.quant.stock_pool import ALL_STOCKS


def _load_extension_module():
    path = (
        Path(__file__).resolve().parents[3]
        / "jiuwenswarm" / "extensions" / "quant-finance" / "extension.py"
    )
    spec = importlib.util.spec_from_file_location("quant_finance_extension_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _market_data() -> tuple[dict, dict]:
    dates = pd.bdate_range("2025-01-02", periods=100)
    prices = {}
    volumes = {}
    for index, ticker in enumerate(ALL_STOCKS):
        trend = np.linspace(10 + index, 13 + index, len(dates))
        wave = np.sin(np.arange(len(dates)) / 7 + index) * 0.2
        prices[ticker] = pd.Series(trend + wave, index=dates)
        volumes[ticker] = pd.Series(1_000_000 + index * 1000 + np.arange(len(dates)), index=dates)
    return prices, volumes


def test_fetch_returns_summary_and_downstream_ignores_llm_prices(monkeypatch):
    module = _load_extension_module()
    module._data_cache.clear()
    prices, volumes = _market_data()
    monkeypatch.setattr(module, "_fetch_real_data", lambda *_: (prices, volumes, []))
    extension = module.QuantFinanceExtension()

    fetched = asyncio.run(extension.fetch_data({"start_date": "2025-01-01", "end_date": "2025-06-01"}))
    assert fetched["success"] is True
    assert fetched["coverage_complete"] is True
    assert fetched["n_stocks"] == fetched["expected_stocks"] == 49
    assert not any(key.startswith("_") for key in fetched)

    malicious_prices = {"2099-01-01": {ticker: 0.0 for ticker in ALL_STOCKS}}
    factors = asyncio.run(extension.compute_factors({"prices": malicious_prices}))
    assert factors["success"] is True
    assert factors["n_stocks_analyzed"] == 49
    assert factors["decision_date"] == "2025-04-23"


def test_cached_pipeline_uses_exact_selection_and_forward_test(monkeypatch):
    module = _load_extension_module()
    module._data_cache.clear()
    prices, volumes = _market_data()
    monkeypatch.setattr(module, "_fetch_real_data", lambda *_: (prices, volumes, []))
    extension = module.QuantFinanceExtension()

    asyncio.run(extension.fetch_data({"start_date": "2025-01-01", "end_date": "2025-06-01"}))
    composites = {ticker: 1.0 - index / 100 for index, ticker in enumerate(ALL_STOCKS)}
    selected = asyncio.run(extension.select_stocks({
        "all_composite": composites,
        "top_n": None,
        "min_score": None,
    }))
    assert selected["success"] is True
    assert selected["n_selected"] == 15
    assert selected["n_sectors_covered"] == 6

    allocation = asyncio.run(extension.allocate_positions({
        "tickers": selected["tickers"],
        "prices": {"must": "be ignored"},
    }))
    assert allocation["success"] is True
    assert allocation["n_holdings"] == 15
    assert allocation["cash_reserve"] >= 0.05

    backtest = asyncio.run(extension.run_backtest({
        "weights": allocation["weights"],
        "prices": {"must": "be ignored"},
        "initial_capital": None,
    }))
    assert backtest["success"] is True
    assert backtest["n_forward_returns"] == 20
    assert backtest["test_start"] == "2025-04-23"
    assert backtest["test_end"] == "2025-05-21"


def test_fetch_fails_closed_on_partial_coverage(monkeypatch):
    module = _load_extension_module()
    module._data_cache.clear()
    prices, volumes = _market_data()
    missing = ALL_STOCKS[-1]
    prices.pop(missing)
    volumes.pop(missing)
    monkeypatch.setattr(module, "_fetch_real_data", lambda *_: (prices, volumes, ["source failed"]))

    result = asyncio.run(module.QuantFinanceExtension().fetch_data({}))
    assert result["success"] is False
    assert result["n_stocks"] == 48
    assert result["missing_tickers"] == [missing]
    cached_failure = module._get_cached_data()
    assert cached_failure["success"] is False
    assert "_prices_df" not in cached_failure

    monkeypatch.setattr(module, "_fetch_real_data", lambda *_: (_ for _ in ()).throw(
        AssertionError("cached retry must not hit providers")
    ))
    retried = asyncio.run(module.QuantFinanceExtension().fetch_data({
        "start_date": "2024-01-01",
        "end_date": "2024-12-31",
    }))
    assert retried["success"] is False
    assert not any(key.startswith("_") for key in retried)


def test_real_data_chain_requests_only_still_missing_tickers(monkeypatch):
    module = _load_extension_module()
    prices, volumes = _market_data()
    calls = []

    def source(name, covered):
        def fetch(tickers, *_):
            calls.append((name, list(tickers)))
            chosen = [ticker for ticker in tickers if ticker in covered]
            return (
                {ticker: prices[ticker] for ticker in chosen},
                {ticker: volumes[ticker] for ticker in chosen},
                [],
            )
        return fetch

    sina_covered = set(ALL_STOCKS[:10])
    tencent_covered = set(ALL_STOCKS[10:20])
    ak_covered = set(ALL_STOCKS[20:30])
    bao_covered = set(ALL_STOCKS[30:40])
    yf_covered = set(ALL_STOCKS[40:])
    monkeypatch.setattr(module, "_fetch_sina", source("sina", sina_covered))
    monkeypatch.setattr(module, "_fetch_tencent", source("tencent", tencent_covered))
    monkeypatch.setattr(module, "_fetch_akshare", source("akshare", ak_covered))
    monkeypatch.setattr(module, "_fetch_baostock", source("baostock", bao_covered))
    monkeypatch.setattr(module, "_fetch_yfinance", source("yfinance", yf_covered))

    fetched_prices, fetched_volumes, errors = module._fetch_real_data(
        ALL_STOCKS, "2025-01-01", "2025-06-01"
    )
    assert errors == []
    assert set(fetched_prices) == set(fetched_volumes) == set(ALL_STOCKS)
    assert calls[0] == ("sina", list(ALL_STOCKS))
    assert calls[1] == ("tencent", list(ALL_STOCKS[10:]))
    assert calls[2] == ("akshare", list(ALL_STOCKS[20:]))
    assert calls[3] == ("baostock", list(ALL_STOCKS[30:]))
    assert calls[4] == ("yfinance", list(ALL_STOCKS[40:]))
    assert module._last_fetch_provider_stats == {
        "sina": {"requested": 49, "newly_covered": 10, "errors": 0},
        "tencent": {"requested": 39, "newly_covered": 10, "errors": 0},
        "akshare": {"requested": 29, "newly_covered": 10, "errors": 0},
        "baostock": {"requested": 19, "newly_covered": 10, "errors": 0},
        "yfinance": {"requested": 9, "newly_covered": 9, "errors": 0},
    }


def test_sina_and_tencent_parsers_use_raw_close_and_volume(monkeypatch):
    module = _load_extension_module()
    ticker = "600000.SH"

    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    def fake_get(url, params, **_):
        if "sina" in url:
            return FakeResponse([
                {"day": "2025-01-02", "close": "10.10", "volume": "1000"},
                {"day": "2025-01-03", "close": "10.20", "volume": "1100"},
            ])
        symbol = params["param"].split(",", 1)[0]
        return FakeResponse({
            "code": 0,
            "msg": "",
            "data": {symbol: {"day": [
                ["2025-01-02", "10.00", "10.10", "10.30", "9.90", "100"],
                ["2025-01-03", "10.10", "10.20", "10.40", "10.00", "110"],
            ]}},
        })

    monkeypatch.setattr(module.requests, "get", fake_get)
    sina_prices, sina_volumes, sina_errors = module._fetch_sina(
        [ticker], "2025-01-01", "2025-01-31"
    )
    tx_prices, tx_volumes, tx_errors = module._fetch_tencent(
        [ticker], "2025-01-01", "2025-01-31"
    )

    assert sina_errors == tx_errors == []
    assert sina_prices[ticker].tolist() == tx_prices[ticker].tolist() == [10.1, 10.2]
    assert sina_volumes[ticker].tolist() == [1000, 1100]
    assert tx_volumes[ticker].tolist() == [100, 110]
