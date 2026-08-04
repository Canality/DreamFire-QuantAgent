from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest
from jiuwenswarm.quant.market_data_service import (
    MarketDataBundle,
    MarketDataContractError,
    ProviderEvidence,
    diagnose_market_data,
    require_diagnostics_passed,
)
from jiuwenswarm.quant.stock_pool import ALL_STOCKS


def _bundle() -> MarketDataBundle:
    dates = pd.bdate_range("2025-01-02", periods=100)
    step = np.arange(len(dates), dtype=float)
    closes = pd.DataFrame(
        {
            ticker: (10.0 + index) * (1.0 + step * (0.0005 + index * 0.000001))
            for index, ticker in enumerate(ALL_STOCKS)
        },
        index=dates,
    )
    opens = closes * 0.999
    highs = closes * 1.002
    lows = opens * 0.998
    volumes = pd.DataFrame(
        {
            ticker: np.full(len(dates), 1_000_000.0 + index * 1_000)
            for index, ticker in enumerate(ALL_STOCKS)
        },
        index=dates,
    )
    provider_ledger = {
        ticker: "sina" if index < 30 else "tencent"
        for index, ticker in enumerate(ALL_STOCKS)
    }
    provider_evidence = {
        name: ProviderEvidence(
            name=name,
            source_endpoint=f"https://example.invalid/{name}",
            price_adjustment="raw_unadjusted",
            raw_volume_unit="shares",
            volume_multiplier_to_shares=1.0,
        )
        for name in ("sina", "tencent")
    }
    benchmark = pd.Series(
        3_000.0 * (1.0004**step),
        index=dates,
        name="CSI300",
    )
    as_of_time = datetime.combine(
        dates[-1].date(),
        time(15, 30),
        tzinfo=ZoneInfo("Asia/Shanghai"),
    )
    return MarketDataBundle(
        opens=opens,
        highs=highs,
        lows=lows,
        closes=closes,
        volumes=volumes,
        secondary_closes=closes.copy(),
        benchmark_closes=benchmark,
        provider_ledger=provider_ledger,
        provider_stats={
            "sina": {"requested": 49, "newly_covered": 30, "errors": 0},
            "tencent": {"requested": 19, "newly_covered": 19, "errors": 0},
        },
        provider_evidence=provider_evidence,
        calendar_id="SSE_SZSE_TRADING_DAYS",
        adjustment_policy="raw_unadjusted",
        secondary_label="tencent_audit",
        as_of_time=as_of_time,
        retrieved_at=as_of_time + timedelta(minutes=1),
    )


def test_valid_49_ticker_bundle_emits_compact_json_diagnostics() -> None:
    diagnostics = diagnose_market_data(_bundle(), ALL_STOCKS)

    assert diagnostics.passed
    payload = diagnostics.to_dict()
    assert payload["provenance"]["n_stocks"] == 49
    assert payload["provenance"]["as_of_time"].endswith("+08:00")
    assert payload["provenance"]["minimum_secondary_overlap_days"] >= 20
    assert payload["breadth"]["n_stocks"] == 49
    assert set(payload["regimes"]) == {
        "benchmark",
        "consensus",
        "final",
        "pool",
    }
    assert len(payload["sector_states"]) == 6
    assert not {
        "opens",
        "highs",
        "lows",
        "closes",
        "volumes",
        "secondary_closes",
        "benchmark_closes",
    }.intersection(payload)
    json.dumps(payload, ensure_ascii=False)


@pytest.mark.parametrize(
    ("mutate", "expected_blocker"),
    [
        (
            lambda bundle: replace(
                bundle,
                opens=bundle.opens.drop(columns=[ALL_STOCKS[-1]]),
            ),
            "opens columns",
        ),
        (
            lambda bundle: replace(
                bundle,
                highs=bundle.highs.drop(columns=[ALL_STOCKS[-1]]),
            ),
            "highs columns",
        ),
        (
            lambda bundle: replace(
                bundle,
                provider_evidence={"sina": bundle.provider_evidence["sina"]},
            ),
            "provider evidence missing",
        ),
        (
            lambda bundle: replace(
                bundle,
                benchmark_closes=pd.Series(dtype=float),
            ),
            "benchmark",
        ),
        (
            lambda bundle: replace(
                bundle,
                secondary_closes=bundle.secondary_closes.drop(
                    columns=[ALL_STOCKS[-1]]
                ),
            ),
            "secondary overlap",
        ),
    ],
)
def test_missing_required_evidence_fails_closed(mutate, expected_blocker: str) -> None:
    diagnostics = diagnose_market_data(mutate(_bundle()), ALL_STOCKS)

    assert not diagnostics.passed
    assert any(expected_blocker in blocker.lower() for blocker in diagnostics.blockers)
    with pytest.raises(MarketDataContractError):
        require_diagnostics_passed(diagnostics)


def test_missing_close_frame_fails_closed_without_attribute_error() -> None:
    diagnostics = diagnose_market_data(
        replace(_bundle(), closes=None),
        ALL_STOCKS,
    )

    assert not diagnostics.passed
    assert any("closes frame" in blocker.lower() for blocker in diagnostics.blockers)
    with pytest.raises(MarketDataContractError):
        require_diagnostics_passed(diagnostics)


def test_one_of_49_secondary_divergence_fails_closed() -> None:
    bundle = _bundle()
    secondary = bundle.secondary_closes.copy()
    secondary.iloc[-1, -1] *= 1.5

    diagnostics = diagnose_market_data(
        replace(bundle, secondary_closes=secondary),
        ALL_STOCKS,
    )

    assert not diagnostics.passed
    cross_source = diagnostics.to_dict()["integrity_reports"][-1]
    assert cross_source["metrics"]["n_divergent_points"] == 1
    assert cross_source["metrics"]["n_divergent_tickers"] == 1


def test_provider_adjustment_must_match_bundle_policy() -> None:
    bundle = _bundle()
    evidence = dict(bundle.provider_evidence)
    evidence["tencent"] = replace(
        evidence["tencent"],
        price_adjustment="forward_adjusted",
    )

    diagnostics = diagnose_market_data(
        replace(bundle, provider_evidence=evidence),
        ALL_STOCKS,
    )

    assert not diagnostics.passed
    assert any("adjustment" in blocker.lower() for blocker in diagnostics.blockers)


def test_future_market_date_relative_to_as_of_time_fails_closed() -> None:
    bundle = _bundle()
    diagnostics = diagnose_market_data(
        replace(
            bundle,
            as_of_time=bundle.as_of_time - timedelta(days=2),
        ),
        ALL_STOCKS,
    )

    assert not diagnostics.passed
    assert any("after as_of_time" in blocker for blocker in diagnostics.blockers)


def test_naive_evidence_timestamps_fail_closed() -> None:
    bundle = _bundle()
    diagnostics = diagnose_market_data(
        replace(
            bundle,
            retrieved_at=bundle.retrieved_at.replace(tzinfo=None),
        ),
        ALL_STOCKS,
    )

    assert not diagnostics.passed
    assert any("retrieved_at" in blocker for blocker in diagnostics.blockers)


def test_invalid_ohlc_relationship_fails_closed() -> None:
    bundle = _bundle()
    highs = bundle.highs.copy()
    highs.iloc[-1, -1] = bundle.lows.iloc[-1, -1] - 1.0

    diagnostics = diagnose_market_data(
        replace(bundle, highs=highs),
        ALL_STOCKS,
    )

    assert not diagnostics.passed
    assert any("ohlc relationship" in blocker.lower() for blocker in diagnostics.blockers)
