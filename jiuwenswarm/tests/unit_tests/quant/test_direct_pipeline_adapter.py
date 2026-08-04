from __future__ import annotations

import importlib.util
from dataclasses import replace
from datetime import datetime, time, timedelta
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest
from jiuwenswarm.quant.market_data_service import (
    MarketDataBundle,
    MarketDataContractError,
    ProviderEvidence,
    diagnose_market_data,
)
from jiuwenswarm.quant.stock_pool import ALL_STOCKS


def _load_direct_module():
    path = Path(__file__).resolve().parents[3] / "scripts" / "run_quant_pipeline.py"
    spec = importlib.util.spec_from_file_location("direct_pipeline_adapter_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _bundle(periods: int = 90) -> MarketDataBundle:
    dates = pd.bdate_range("2025-01-02", periods=periods)
    step = np.arange(periods, dtype=float)
    closes = pd.DataFrame(
        {
            ticker: (10.0 + index) * (1.0 + step * (0.0005 + index * 0.000001))
            for index, ticker in enumerate(ALL_STOCKS)
        },
        index=dates,
    )
    as_of = datetime.combine(
        dates[-1].date(),
        time(16, 0),
        tzinfo=ZoneInfo("Asia/Shanghai"),
    )
    evidence = ProviderEvidence(
        name="test_primary",
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
        volumes=pd.DataFrame(1_000_000.0, index=dates, columns=ALL_STOCKS),
        secondary_closes=closes.copy(),
        benchmark_closes=pd.Series(
            3000.0 + step,
            index=dates,
            name="CSI300:test",
        ),
        provider_ledger={ticker: "test_primary" for ticker in ALL_STOCKS},
        provider_stats={"test_primary": {"primary_covered": 49}},
        provider_evidence={"test_primary": evidence},
        calendar_id="SSE_SZSE_observed_sessions",
        adjustment_policy="raw_unadjusted",
        secondary_label="independent_test",
        as_of_time=as_of,
        retrieved_at=as_of + timedelta(minutes=1),
    )


def test_direct_fetch_uses_shared_bundle_and_passed_diagnostics(monkeypatch):
    module = _load_direct_module()
    bundle = _bundle()
    calls = []

    def fake_fetch(tickers, start_date, end_date, *, as_of_time):
        calls.append((tickers, start_date, end_date, as_of_time))
        return bundle

    monkeypatch.setattr(module, "fetch_market_data_bundle", fake_fetch)
    fetched, diagnostics = module.fetch_data(
        list(ALL_STOCKS),
        "2025-01-02",
        "2025-05-07",
        as_of_time=bundle.as_of_time,
    )

    assert fetched is bundle
    assert diagnostics.passed is True
    assert diagnostics.to_dict()["provenance"]["n_stocks"] == 49
    assert calls == [
        (
            list(ALL_STOCKS),
            "2025-01-02",
            "2025-05-07",
            bundle.as_of_time,
        )
    ]


def test_direct_fetch_rejects_nonofficial_pool_before_provider(monkeypatch):
    module = _load_direct_module()
    monkeypatch.setattr(
        module,
        "fetch_market_data_bundle",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("invalid scope must not reach providers")
        ),
    )

    with pytest.raises(RuntimeError, match="official 49-stock pool"):
        module.fetch_data(
            list(ALL_STOCKS[:-1]),
            "2025-01-02",
            "2025-05-07",
        )


def test_direct_fetch_fails_closed_on_malformed_shared_bundle(monkeypatch):
    module = _load_direct_module()
    bundle = _bundle()
    malformed = replace(
        bundle,
        closes=bundle.closes.drop(columns=[ALL_STOCKS[-1]]),
    )
    monkeypatch.setattr(
        module,
        "fetch_market_data_bundle",
        lambda *_args, **_kwargs: malformed,
    )

    with pytest.raises(MarketDataContractError, match="diagnostics failed"):
        module.fetch_data(
            list(ALL_STOCKS),
            "2025-01-02",
            "2025-05-07",
            as_of_time=bundle.as_of_time,
        )


def test_decision_evidence_bundle_excludes_all_forward_test_rows():
    module = _load_direct_module()
    bundle = _bundle()
    decision_index = bundle.closes.index[-21]

    evidence = module._decision_evidence_bundle(bundle, decision_index)
    diagnostics = diagnose_market_data(
        evidence,
        ALL_STOCKS,
        minimum_rows=61,
    )

    assert diagnostics.passed is True
    assert evidence.closes.index[-1] == decision_index
    assert len(evidence.closes) == 70
    assert all(
        frame.index[-1] == decision_index
        for frame in (
            evidence.opens,
            evidence.highs,
            evidence.lows,
            evidence.closes,
            evidence.volumes,
            evidence.secondary_closes,
        )
    )
    assert evidence.benchmark_closes.index[-1] == decision_index
    assert evidence.as_of_time.isoformat().endswith("T16:00:00+08:00")


def test_default_end_date_skips_an_incomplete_current_session():
    module = _load_direct_module()
    before_close = datetime(
        2026,
        8,
        3,
        12,
        0,
        tzinfo=ZoneInfo("Asia/Shanghai"),
    )
    after_close = before_close.replace(hour=16)

    assert module._default_end_date(now=before_close) == "2026-08-02"
    assert module._default_end_date(now=after_close) == "2026-08-03"


def test_direct_script_has_no_private_extension_fetch_dependency():
    module = _load_direct_module()
    source = Path(module.__file__).read_text(encoding="utf-8")

    assert "_fetch_real_data" not in source
    assert "extensions/quant-finance/extension.py" not in source


def test_direct_report_adapter_forwards_shared_announcement_evidence(
    monkeypatch,
    tmp_path,
):
    from jiuwenswarm.quant.reporting import EvidenceRef, MetricFact
    from jiuwenswarm.quant.reporting.providers.status import ProviderStatus

    module = _load_direct_module()
    bundle = _bundle()
    diagnostics = diagnose_market_data(bundle, list(ALL_STOCKS))
    sectors = []
    by_sector = {}
    for ticker in ALL_STOCKS:
        sector = module.SECTOR_MAP[ticker]
        if sector not in sectors:
            sectors.append(sector)
        by_sector.setdefault(sector, []).append(ticker)
    selected = []
    for offset in range(3):
        for sector in sectors:
            if len(selected) >= 15:
                break
            selected.append(by_sector[sector][offset])

    scores = pd.DataFrame(
        {
            "composite": np.linspace(2.0, 1.0, len(ALL_STOCKS)),
            "sector": [module.SECTOR_MAP[ticker] for ticker in ALL_STOCKS],
        },
        index=ALL_STOCKS,
    )
    event_ref = EvidenceRef(
        evidence_id="ann-runtime-proof",
        source_type="disclosure",
        source_name="runtime-test",
        source_url="https://example.invalid/announcement",
        period_end=bundle.as_of_time,
        published_at=bundle.as_of_time,
        available_at=bundle.as_of_time,
        retrieved_at=bundle.retrieved_at,
        content_sha256="b" * 64,
    )
    event_fact = MetricFact(
        name="exchange_announcement",
        value="runtime announcement proof",
        unit=None,
        status="available",
        evidence_ids=(event_ref.evidence_id,),
    )
    announcement_result = SimpleNamespace(
        facts_by_ticker={selected[0]: (event_fact,)},
        manifest={event_ref.evidence_id: event_ref},
        total_facts=1,
        tickers_with_events=1,
        statuses={ticker: ProviderStatus.COMPLETE for ticker in ALL_STOCKS},
    )
    captured = {"bundles": {}}

    class FakeFactorCalculator:
        def __init__(self, _config):
            self.regime = None

        def compute_factors(self, _prices, _volumes):
            return object()

        def compute_scores(self, _factors):
            return scores

    class FakePositionSizer:
        def __init__(self, _config):
            pass

        def allocate(self, _scores, _prices):
            return {ticker: 0.05 for ticker in selected}

    class FakeBacktestEngine:
        def run(self, _prices, _weights):
            return SimpleNamespace(
                total_return=0.01,
                max_drawdown=-0.01,
                sharpe_ratio=1.0,
                metrics={"total_return": 0.01},
            )

    class FakeReportService:
        def build_company_bundle(self, **kwargs):
            captured["bundles"][kwargs["ticker"]] = kwargs
            return SimpleNamespace(portfolio_weight=kwargs["portfolio_weight"])

        def build_portfolio_snapshot(self, **kwargs):
            return SimpleNamespace(**kwargs)

        def build_package(self, **kwargs):
            captured["manifest"] = kwargs["evidence_manifest"]
            captured["archive"] = kwargs["evidence_archive"]
            raise RuntimeError("runtime propagation captured")

    snapshot = SimpleNamespace(
        snapshot_id="snapshot-runtime-proof",
        manifest_sha256="a" * 64,
        manifest_path=tmp_path / "manifest.json",
    )
    fake_repo = tmp_path / "fake_repo"
    fake_repo.mkdir()
    monkeypatch.setattr(
        module,
        "__file__",
        str(fake_repo / "jiuwenswarm" / "scripts" / "run_quant_pipeline.py"),
    )
    monkeypatch.setattr(
        module,
        "fetch_data",
        lambda *_args, **_kwargs: (bundle, diagnostics),
    )
    monkeypatch.setattr(module, "select_stocks", lambda _scores: selected)
    monkeypatch.setattr(module.MarketRegime, "detect", lambda *_a, **_k: "neutral")
    monkeypatch.setattr(module, "FactorCalculator", FakeFactorCalculator)
    monkeypatch.setattr(module, "PositionSizer", FakePositionSizer)
    monkeypatch.setattr(module, "BacktestEngine", FakeBacktestEngine)

    import jiuwenswarm.quant.reporting as reporting

    monkeypatch.setattr(reporting, "write_market_data_snapshot", lambda *_a, **_k: snapshot)
    monkeypatch.setattr(reporting, "run_announcement_service", lambda *_a, **_k: announcement_result)
    monkeypatch.setattr(reporting, "ReportService", FakeReportService)

    with pytest.raises(RuntimeError, match="runtime propagation captured"):
        module.main([
            "--start-date", "2025-01-02",
            "--end-date", bundle.as_of_time.date().isoformat(),
        ])

    assert captured["bundles"][selected[0]]["event_facts"] == (event_fact,)
    assert captured["bundles"][selected[1]]["event_facts"] == ()
    assert captured["manifest"][event_ref.evidence_id] is event_ref
    assert captured["manifest"][snapshot.snapshot_id].evidence_id == snapshot.snapshot_id
    assert captured["archive"].root == fake_repo / "output" / "evidence_archive"
