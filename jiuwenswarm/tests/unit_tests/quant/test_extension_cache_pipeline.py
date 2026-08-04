from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from jiuwenswarm.quant.market_data_provider import MarketDataFetchError
from jiuwenswarm.quant.market_data_service import (
    MarketDataBundle,
    ProviderEvidence,
)
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


def _market_bundle(prices: dict, volumes: dict) -> MarketDataBundle:
    closes = pd.DataFrame(prices).sort_index().reindex(columns=ALL_STOCKS)
    volume_frame = pd.DataFrame(volumes).sort_index().reindex(columns=ALL_STOCKS)
    as_of = datetime.combine(
        closes.index[-1].date(),
        time(16, 0),
        tzinfo=ZoneInfo("Asia/Shanghai"),
    )
    evidence = ProviderEvidence(
        name="test_provider",
        source_endpoint="https://example.invalid/primary",
        price_adjustment="raw_unadjusted",
        raw_volume_unit="shares",
        volume_multiplier_to_shares=1.0,
    )
    return MarketDataBundle(
        opens=closes * 0.999,
        highs=closes * 1.002,
        lows=closes * 0.998,
        closes=closes,
        volumes=volume_frame,
        secondary_closes=closes.copy(),
        benchmark_closes=pd.Series(
            np.linspace(3000.0, 3100.0, len(closes)),
            index=closes.index,
            name="CSI300:test",
        ),
        provider_ledger={ticker: "test_provider" for ticker in ALL_STOCKS},
        provider_stats={"test_provider": {"primary_covered": 49}},
        provider_evidence={"test_provider": evidence},
        calendar_id="SSE_SZSE_observed_sessions",
        adjustment_policy="raw_unadjusted",
        secondary_label="independent_test",
        as_of_time=as_of,
        retrieved_at=as_of + timedelta(minutes=1),
    )


def _install_fake_market_service(monkeypatch, module, prices, volumes) -> None:
    bundle = _market_bundle(prices, volumes)
    monkeypatch.setattr(module, "_fetch_market_bundle", lambda *_: bundle)


def test_fetch_returns_summary_and_downstream_ignores_llm_prices(monkeypatch):
    module = _load_extension_module()
    module._data_cache.clear()
    prices, volumes = _market_data()
    _install_fake_market_service(monkeypatch, module, prices, volumes)
    extension = module.QuantFinanceExtension()

    fetched = asyncio.run(extension.fetch_data({"start_date": "2025-01-01", "end_date": "2025-06-01"}))
    assert fetched["success"] is True
    assert fetched["coverage_complete"] is True
    assert fetched["n_stocks"] == fetched["expected_stocks"] == 49
    assert fetched["diagnostics_passed"] is True
    assert fetched["cached"] is False
    assert fetched["executed"] is True
    assert not any(key.startswith("_") for key in fetched)
    fetched_again = asyncio.run(
        extension.fetch_data(
            {"start_date": "2025-01-01", "end_date": "2025-06-01"}
        )
    )
    assert fetched_again["cached"] is True
    assert fetched_again["executed"] is False

    malicious_prices = {"2099-01-01": {ticker: 0.0 for ticker in ALL_STOCKS}}
    factors = asyncio.run(extension.compute_factors({"prices": malicious_prices}))
    assert factors["success"] is True
    assert factors["n_stocks_analyzed"] == 49
    assert factors["decision_date"] == "2025-04-23"


def test_report_cache_preserves_scores_and_concurrent_agent_views(monkeypatch, tmp_path):
    module = _load_extension_module()
    module._data_cache.clear()
    prices, volumes = _market_data()
    _install_fake_market_service(monkeypatch, module, prices, volumes)
    extension = module.QuantFinanceExtension()

    fetched = asyncio.run(
        extension.fetch_data({"start_date": "2025-01-01", "end_date": "2025-06-01"})
    )
    assert fetched["success"] is True
    factors = asyncio.run(extension.compute_factors({}))

    async def run_views():
        return await asyncio.gather(extension.alpha_view({}), extension.risk_evidence_view({}))

    alpha, risk = asyncio.run(run_views())
    cached = module._get_cached_data()
    assert isinstance(cached["_scores_df"], pd.DataFrame)
    assert len(cached["_scores_df"]) == 49
    assert cached["_alpha_result"] == alpha
    assert cached["_risk_result"] == risk

    from jiuwenswarm.quant import reporting
    from jiuwenswarm.quant.reporting import (
        EvidenceRef,
        MetricFact,
        ReportService,
        ServiceResult,
        parse_bull_bear_pair,
    )
    from jiuwenswarm.quant.reporting.providers.announcement import (
        AnnouncementDiagnostics,
        AnnouncementTerminalCause,
    )
    from jiuwenswarm.quant.reporting.providers.status import ProviderStatus

    project_snapshot_root = Path(__file__).resolve().parents[4] / "output" / "data_snapshots"
    snapshots_before = (
        {path.name for path in project_snapshot_root.iterdir()}
        if project_snapshot_root.exists()
        else set()
    )
    real_write_market_data_snapshot = reporting.write_market_data_snapshot

    def isolated_write_market_data_snapshot(bundle, diagnostics, _, **kwargs):
        return real_write_market_data_snapshot(
            bundle,
            diagnostics,
            tmp_path / "data_snapshots",
            **kwargs,
        )

    monkeypatch.setattr(
        reporting,
        "write_market_data_snapshot",
        isolated_write_market_data_snapshot,
    )

    async def fake_announcement_run(self, tickers, as_of_time):
        del self
        evidence_id = "ann-test-formal-propagation"
        raw = b'{"title":"fixture disclosure"}'
        first = tickers[0]
        return ServiceResult(
            facts_by_ticker={
                ticker: (
                    [MetricFact(
                        name="exchange_announcement",
                        value="fixture disclosure",
                        unit=None,
                        status="available",
                        evidence_ids=(evidence_id,),
                    )]
                    if ticker == first else []
                )
                for ticker in tickers
            },
            manifest={
                evidence_id: EvidenceRef(
                    evidence_id=evidence_id,
                    source_type="disclosure",
                    source_name="fixture",
                    source_url="https://example.invalid/disclosure",
                    period_end=as_of_time,
                    published_at=as_of_time,
                    available_at=as_of_time,
                    retrieved_at=as_of_time,
                    content_sha256=hashlib.sha256(raw).hexdigest(),
                )
            },
            statuses={
                ticker: (
                    ProviderStatus.COMPLETE
                    if ticker == first else ProviderStatus.AVAILABLE_NO_EVENT
                )
                for ticker in tickers
            },
            diagnostics_by_ticker={
                ticker: AnnouncementDiagnostics(
                    terminal_cause=(
                        AnnouncementTerminalCause.EVENTS_FOUND
                        if ticker == first
                        else AnnouncementTerminalCause.TRUE_NO_DATA
                    )
                )
                for ticker in tickers
            },
        )

    monkeypatch.setattr(
        reporting.AnnouncementService,
        "run",
        fake_announcement_run,
    )

    views, errors = parse_bull_bear_pair(alpha, risk)
    assert errors == []
    assert {view.role for view in views} == {"alpha", "risk_evidence"}

    selected = asyncio.run(
        extension.select_stocks({"all_composite": factors["all_composite"]})
    )
    allocation = asyncio.run(
        extension.allocate_positions({"tickers": selected["tickers"]})
    )
    backtest = asyncio.run(
        extension.run_backtest({"weights": allocation["weights"]})
    )

    captured = {}

    class DummyQuality:
        blockers = ()
        warnings = ()

    def fake_build_package(
        self, *, portfolio, bundles, output_dir, strategy_label,
        evidence_manifest, evidence_archive
    ):
        del self, portfolio, output_dir, strategy_label, evidence_archive
        captured["bundles"] = bundles
        captured["evidence_manifest"] = evidence_manifest
        return True, DummyQuality(), str(tmp_path)

    monkeypatch.setattr(ReportService, "build_package", fake_build_package)
    report = asyncio.run(
        extension.generate_report(
            {
                "portfolio": [{"ticker": ALL_STOCKS[0], "weight": 1.0}],
                "backtest": {"total_return": 999.0},
                "regime": "bull",
                "top_stocks": [],
            }
        )
    )
    assert report["success"] is True, report
    assert report["summary"]["n_holdings"] == allocation["n_holdings"]
    assert report["summary"]["total_return"] == backtest["total_return"]
    assert report["summary"]["regime"] == factors["regime"]
    assert report["candidate_package"]["quality_passed"] is True
    assert report["candidate_package"]["n_reports"] == 49
    assert len(captured["bundles"]) == 49
    assert all(bundle.technical_facts for bundle in captured["bundles"].values())
    assert any(bundle.agent_views for bundle in captured["bundles"].values())
    assert [
        fact.value
        for fact in captured["bundles"][ALL_STOCKS[0]].event_facts
    ] == ["fixture disclosure"]
    assert len(captured["evidence_manifest"]) == 2
    assert sum(
        ref.source_type == "disclosure"
        for ref in captured["evidence_manifest"].values()
    ) == 1
    assert len(list((tmp_path / "data_snapshot").iterdir())) == 9
    evidence_id = next(iter(captured["evidence_manifest"]))
    market_evidence = captured["evidence_manifest"][evidence_id]
    assert market_evidence.available_at.isoformat() == "2025-04-23T16:00:00+08:00"
    assert market_evidence.period_end == market_evidence.available_at
    assert market_evidence.published_at == market_evidence.available_at
    manifest_path = tmp_path / market_evidence.source_url
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["n_trading_days"] == 80
    assert manifest["actual_end_date"].startswith("2025-04-23")
    assert manifest["as_of_time"] == market_evidence.available_at.isoformat()
    assert manifest["diagnostic_policy"]["minimum_rows"] == 61
    assert all(
        view.evidence_ids == (evidence_id,)
        for bundle in captured["bundles"].values()
        for view in bundle.agent_views
    )
    snapshots_after = (
        {path.name for path in project_snapshot_root.iterdir()}
        if project_snapshot_root.exists()
        else set()
    )
    assert snapshots_after == snapshots_before


def test_cached_pipeline_uses_exact_selection_and_forward_test(monkeypatch):
    module = _load_extension_module()
    module._data_cache.clear()
    prices, volumes = _market_data()
    _install_fake_market_service(monkeypatch, module, prices, volumes)
    extension = module.QuantFinanceExtension()

    asyncio.run(extension.fetch_data({"start_date": "2025-01-01", "end_date": "2025-06-01"}))
    asyncio.run(extension.compute_factors({}))
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

    # Idempotency: repeated call with different params returns cached result
    tampered_allocation = asyncio.run(extension.allocate_positions({
        "tickers": selected["tickers"][:-1],
    }))
    assert tampered_allocation["success"] is True
    assert tampered_allocation.get("cached") is True
    assert tampered_allocation.get("executed") is False
    assert tampered_allocation["weights"] == allocation["weights"]
    # The first execution's input_overridden is preserved in cache
    assert tampered_allocation["input_overridden"] is False

    backtest = asyncio.run(extension.run_backtest({
        "weights": {selected["tickers"][0]: 1.0},
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
    monkeypatch.setattr(
        module,
        "_fetch_market_bundle",
        lambda *_: (_ for _ in ()).throw(
            MarketDataFetchError("primary coverage incomplete: source failed")
        ),
    )

    failed_request = {"start_date": "2025-01-01", "end_date": "2025-06-01"}
    result = asyncio.run(module.QuantFinanceExtension().fetch_data(failed_request))
    assert result["success"] is False
    assert "source failed" in result["detail"]
    cached_failure = module._get_cached_data()
    assert cached_failure["success"] is False
    assert "_prices_df" not in cached_failure
    assert "_market_data_bundle" not in cached_failure

    monkeypatch.setattr(module, "_fetch_market_bundle", lambda *_: (_ for _ in ()).throw(
        AssertionError("cached retry must not hit providers")
    ))
    retried = asyncio.run(
        module.QuantFinanceExtension().fetch_data(failed_request)
    )
    assert retried["success"] is False
    assert not any(key.startswith("_") for key in retried)

    monkeypatch.setattr(
        module,
        "_fetch_market_bundle",
        lambda *_: (_ for _ in ()).throw(
            MarketDataFetchError("different request reached provider")
        ),
    )
    different = asyncio.run(
        module.QuantFinanceExtension().fetch_data(
            {"start_date": "2024-01-01", "end_date": "2024-12-31"}
        )
    )
    assert "different request reached provider" in different["detail"]


def test_new_fetch_invalidates_all_derived_phase_results(monkeypatch):
    module = _load_extension_module()
    module._data_cache.clear()
    module._phase_results.clear()
    prices, volumes = _market_data()
    _install_fake_market_service(monkeypatch, module, prices, volumes)
    extension = module.QuantFinanceExtension()
    request = {"start_date": "2025-01-01", "end_date": "2025-06-01"}

    assert asyncio.run(extension.fetch_data(request))["success"] is True
    first = asyncio.run(extension.compute_factors({}))
    assert first["executed"] is True
    assert "compute_factors" in module._phase_results

    refreshed = asyncio.run(
        extension.fetch_data({**request, "force_refresh": True})
    )
    assert refreshed["success"] is True
    assert module._phase_results == {}
    recomputed = asyncio.run(extension.compute_factors({}))
    assert recomputed["executed"] is True
    assert recomputed["cached"] is False


def test_explicit_empty_ticker_filter_fails_without_calling_provider(monkeypatch):
    module = _load_extension_module()
    module._data_cache.clear()
    monkeypatch.setattr(
        module,
        "_fetch_market_bundle",
        lambda *_: (_ for _ in ()).throw(
            AssertionError("invalid ticker request must not reach providers")
        ),
    )

    result = asyncio.run(
        module.QuantFinanceExtension().fetch_data({"tickers": []})
    )
    assert result["success"] is False
    assert result["expected_stocks"] == 49
    assert result["n_stocks"] == 0


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
    assert module._last_fetch_provider_ledger == {
        **{ticker: "sina" for ticker in ALL_STOCKS[:10]},
        **{ticker: "tencent" for ticker in ALL_STOCKS[10:20]},
        **{ticker: "akshare" for ticker in ALL_STOCKS[20:30]},
        **{ticker: "baostock" for ticker in ALL_STOCKS[30:40]},
        **{ticker: "yfinance" for ticker in ALL_STOCKS[40:]},
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
