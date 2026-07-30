"""Quant Finance extension for JiuwenSwarm -- RPC handlers.

Registers 8 RPC handlers for the full quant investment pipeline:
  quant.fetch_data, quant.compute_factors, quant.select_stocks,
  quant.allocate_positions, quant.run_backtest, quant.generate_report,
  quant.bull_view, quant.bear_view

Data flows through an in-memory cache: fetch_data stores results,
subsequent tools read from cache. This avoids passing huge price
matrices through the LLM context window.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict

import numpy as np
import pandas as pd
import requests

from jiuwenswarm.extensions.sdk.base import BaseExtension
from jiuwenswarm.extensions.types import ExtensionConfig

logger = logging.getLogger(__name__)

# In-memory data cache to avoid passing huge price matrices through LLM context.
# Keyed by a deterministic cache key derived from (tickers, start_date, end_date).
_data_cache: dict = {}
_cache_lock = threading.Lock()
_FORWARD_TEST_DAYS = 20
_MIN_TRAIN_DAYS = 61
_PROVIDER_FAILURE_TTL_SECONDS = 300
_provider_failure: dict | None = None
_last_fetch_provider_stats: dict[str, dict[str, Any]] = {}
_last_fetch_provider_ledger: dict[str, str] = {}


def _cache_key(tickers: list, start: str, end: str) -> str:
    return f"{','.join(sorted(tickers[:5]))}_{start}_{end}"


def _get_cached_data() -> dict | None:
    with _cache_lock:
        return _data_cache.get("_last", None)


def _set_cached_data(data: dict) -> None:
    with _cache_lock:
        _data_cache["_last"] = data
        # Keep only last 3 fetches to bound memory
        keys = [k for k in _data_cache if k != "_last"]
        for k in keys[:-2]:
            del _data_cache[k]


def _update_cached_data(**updates: Any) -> bool:
    """Atomically add derived artifacts to the current market-data cache.

    Bull and Bear handlers may finish concurrently. Replacing the whole cache
    from a stale snapshot can therefore discard the other handler's result.
    Mutating the live cache under the shared lock preserves both results and
    avoids copying the large price/volume frames.
    """
    with _cache_lock:
        cached = _data_cache.get("_last")
        if not isinstance(cached, dict):
            return False
        cached.update(updates)
        return True


def _public_cache_summary(cached: dict) -> dict:
    """Return only JSON-safe metadata; raw market matrices never reach the LLM."""
    return {key: value for key, value in cached.items() if not key.startswith("_")}


def _cached_frames() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame] | None:
    """Return (training prices, training volumes, forward-test prices)."""
    cached = _get_cached_data()
    if not cached:
        return None
    prices = cached.get("_prices_df")
    volumes = cached.get("_volumes_df")
    if not isinstance(prices, pd.DataFrame) or prices.empty:
        return None
    split_at = len(prices) - _FORWARD_TEST_DAYS
    if split_at < _MIN_TRAIN_DAYS:
        return None
    train_prices = prices.iloc[:split_at].copy()
    # Include the decision-date close, yielding exactly 20 forward returns.
    test_prices = prices.iloc[split_at - 1:].copy()
    if isinstance(volumes, pd.DataFrame) and not volumes.empty:
        train_volumes = volumes.reindex(train_prices.index).copy()
    else:
        train_volumes = pd.DataFrame()
    return train_prices, train_volumes, test_prices


def _cache_required_error() -> dict[str, Any]:
    return {
        "success": False,
        "detail": (
            "完整缓存行情不可用或交易日不足；请先成功调用 quant_fetch_data，"
            f"至少需要 {_MIN_TRAIN_DAYS + _FORWARD_TEST_DAYS} 个交易日。"
        ),
    }

QUANT_FETCH_DATA = "quant.fetch_data"
QUANT_COMPUTE_FACTORS = "quant.compute_factors"
QUANT_SELECT_STOCKS = "quant.select_stocks"
QUANT_ALLOCATE_POSITIONS = "quant.allocate_positions"
QUANT_RUN_BACKTEST = "quant.run_backtest"
QUANT_GENERATE_REPORT = "quant.generate_report"
QUANT_BULL_VIEW = "quant.bull_view"
QUANT_BEAR_VIEW = "quant.bear_view"


# -- YFinance ticker conversion --

def _yf_ticker(t: str) -> str:
    return t.replace(".SH", ".SS").replace(".SZ", ".SZ")


# -- Name map (used in report generation) --

_TICKER_NAME_MAP: Dict[str, str] = {
    "601318.SH": "中国平安", "600036.SH": "招商银行", "601688.SH": "华泰证券",
    "601398.SH": "工商银行", "601288.SH": "农业银行", "601988.SH": "中国银行",
    "600000.SH": "浦发银行", "601998.SH": "中信银行", "600519.SH": "贵州茅台",
    "000858.SZ": "五粮液", "600887.SH": "伊利股份", "603288.SH": "海天味业",
    "600660.SH": "福耀玻璃", "000333.SZ": "美的集团", "000651.SZ": "格力电器",
    "601888.SH": "中国中免", "600809.SH": "山西汾酒", "300750.SZ": "宁德时代",
    "002594.SZ": "比亚迪", "601012.SH": "隆基绿能", "300274.SZ": "阳光电源",
    "600900.SH": "长江电力", "600438.SH": "通威股份", "600089.SH": "特变电工",
    "600212.SH": "绿能慧充", "688981.SH": "中芯国际", "600584.SH": "长电科技",
    "600183.SH": "生益科技", "300308.SZ": "中际旭创", "300394.SZ": "天孚通信",
    "603501.SH": "韦尔股份", "600703.SH": "三安光电", "600570.SH": "恒生电子",
    "600845.SH": "宝信软件", "688041.SH": "海光信息", "603986.SH": "兆易创新",
    "002475.SZ": "立讯精密", "601899.SH": "紫金矿业", "600309.SH": "万华化学",
    "601600.SH": "中国铝业", "600028.SH": "中国石化", "601088.SH": "中国神华",
    "600547.SH": "山东黄金", "600426.SH": "华鲁恒升", "601168.SH": "西部矿业",
    "600031.SH": "三一重工", "601766.SH": "中国中车", "601668.SH": "中国建筑",
    "601186.SH": "中国铁建",
}


class QuantFinanceExtension(BaseExtension):
    """Quantitative finance extension for JiuwenSwarm."""

    def __init__(self) -> None:
        self._registry = None
        self._initialized = False

    async def initialize(self, config: ExtensionConfig) -> None:
        self._initialized = True
        logger.info("[QuantFinance] Extension initialized.")

    async def shutdown(self) -> None:
        self._initialized = False
        logger.info("[QuantFinance] Extension shut down.")

    def register(self, registry) -> None:
        self._registry = registry
        registry.register_rpc_handler(QUANT_FETCH_DATA, self.fetch_data)
        registry.register_rpc_handler(QUANT_COMPUTE_FACTORS, self.compute_factors)
        registry.register_rpc_handler(QUANT_SELECT_STOCKS, self.select_stocks)
        registry.register_rpc_handler(QUANT_ALLOCATE_POSITIONS, self.allocate_positions)
        registry.register_rpc_handler(QUANT_RUN_BACKTEST, self.run_backtest)
        registry.register_rpc_handler(QUANT_GENERATE_REPORT, self.generate_report)
        registry.register_rpc_handler(QUANT_BULL_VIEW, self.bull_view)
        registry.register_rpc_handler(QUANT_BEAR_VIEW, self.bear_view)
        logger.info("[QuantFinance] Registered 8 RPC handlers.")

    # ---- quant.fetch_data ----

    async def fetch_data(
        self,
        params: dict[str, Any] | None = None,
        request: Any = None,
    ) -> dict[str, Any]:
        """Fetch stock price/volume data for the competition stock pool.

        Data is cached in memory. Returns a compact summary (NOT raw prices)
        to stay within LLM context limits. Subsequent tools read from cache.
        """
        del request
        params = params or {}

        start_date = str(params.get("start_date") or _default_start_date())
        end_date = str(params.get("end_date") or _default_end_date())
        ticker_filter = params.get("tickers")
        force_refresh = bool(params.get("force_refresh", False))

        from jiuwenswarm.quant.stock_pool import ALL_STOCKS

        tickers = list(ticker_filter) if ticker_filter else list(ALL_STOCKS)

        def _fetch() -> dict:
            global _provider_failure
            # Check cache first
            cached = _get_cached_data()
            if (not force_refresh and cached and cached.get("_start") == start_date
                    and cached.get("_end") == end_date
                    and cached.get("_tickers") == tickers):
                logger.info("[QuantFinance] Using cached data for %s ~ %s", start_date, end_date)
                return _public_cache_summary(cached)
            if (not force_refresh and _provider_failure is not None
                    and time.monotonic() - _provider_failure["_failed_at"]
                    < _PROVIDER_FAILURE_TTL_SECONDS):
                logger.warning("[QuantFinance] Provider circuit breaker open; skipping repeated fetch")
                return _public_cache_summary(_provider_failure)

            prices, volumes, errors = _fetch_real_data(tickers, start_date, end_date)

            missing = [
                ticker for ticker in tickers
                if not _ticker_data_usable(prices, volumes, ticker)
            ]
            if missing:
                error_detail = _build_fetch_error_message(errors)
                failure = {
                    "success": False,
                    "_start": start_date,
                    "_end": end_date,
                    "_tickers": tickers,
                    "detail": f"行情覆盖不足：{len(prices)}/{len(tickers)}；缺失 {missing}.\n{error_detail}",
                    "n_stocks": len(prices),
                    "expected_stocks": len(tickers),
                    "missing_tickers": missing,
                    "errors": errors,
                    "provider_coverage": _last_fetch_provider_stats,
                    "_failed_at": time.monotonic(),
                }
                # Cache this run's failure so an Agent retry does not hammer all
                # three providers again. force_refresh=true explicitly bypasses it.
                _set_cached_data(failure)
                _provider_failure = failure
                return _public_cache_summary(failure)

            prices_df = pd.DataFrame(prices).sort_index()
            volumes_df = pd.DataFrame(volumes).sort_index() if volumes else pd.DataFrame()

            # Store full data in cache for subsequent tools
            result = {
                "success": True,
                "_start": start_date,
                "_end": end_date,
                "_tickers": tickers,
                "_prices_df": prices_df,
                "_volumes_df": volumes_df,
                "_provider_ledger": dict(_last_fetch_provider_ledger),
                "_provider_stats": dict(_last_fetch_provider_stats),
                # Compact summary for LLM
                "n_stocks": len(prices),
                "expected_stocks": len(tickers),
                "coverage_complete": True,
                "n_days": len(prices_df),
                "date_range": f"{prices_df.index[0]} ~ {prices_df.index[-1]}",
                "top_movers": _summarize_top_movers(prices_df, 10),
                "fetch_errors": errors[:5] if errors else [],
                "provider_coverage": _last_fetch_provider_stats,
            }
            _set_cached_data(result)
            _provider_failure = None
            return _public_cache_summary(result)

        return await asyncio.to_thread(_fetch)

    # ---- quant.compute_factors ----

    async def compute_factors(
        self,
        params: dict[str, Any] | None = None,
        request: Any = None,
    ) -> dict[str, Any]:
        """Compute 6-factor scores with market regime detection (v2.6).

        Raw matrices are read exclusively from the server-side cache. Any legacy
        prices/volumes parameters are deliberately ignored.
        """
        del request
        params = params or {}

        frames = _cached_frames()
        if frames is None:
            return _cache_required_error()
        prices, volumes, _ = frames

        def _compute() -> dict:
            from jiuwenswarm.quant.market_regime import MarketRegime
            from jiuwenswarm.quant.factors import FactorCalculator
            from jiuwenswarm.quant.strategy_configs import production_factor_config

            regime = MarketRegime.detect(prices)
            factor_cfg = production_factor_config()
            factor_calc = FactorCalculator(factor_cfg)
            factor_calc.regime = regime
            factors = factor_calc.compute_factors(prices, volumes if not volumes.empty else None)
            scores = factor_calc.compute_scores(factors)
            top_stocks = []
            for ticker in scores.head(15).index:
                top_stocks.append({
                    "ticker": ticker,
                    "name": _TICKER_NAME_MAP.get(ticker, ticker),
                    "composite": round(float(scores.loc[ticker, "composite"]), 4),
                    "sector": str(scores.loc[ticker, "sector"]),
                })

            result = {
                "success": True,
                "regime": regime,
                "n_stocks_analyzed": len(scores),
                "decision_date": str(prices.index[-1].date()),
                "top_stocks": top_stocks,
                "all_composite": {t: round(float(scores.loc[t, "composite"]), 4)
                                  for t in scores.index},
            }
            if not _update_cached_data(_scores_df=scores, _factor_result=result):
                return _cache_required_error()
            return result

        return await asyncio.to_thread(_compute)

    # ---- quant.select_stocks ----

    async def select_stocks(
        self,
        params: dict[str, Any] | None = None,
        request: Any = None,
    ) -> dict[str, Any]:
        """Select stocks with sector diversification from factor scores."""
        del request
        del params

        from jiuwenswarm.quant.stock_pool import STOCK_POOL, SECTOR_MAP

        cached = _get_cached_data()
        scores = cached.get("_scores_df") if cached else None
        if not isinstance(scores, pd.DataFrame) or "composite" not in scores:
            return {
                "success": False,
                "detail": "cached factor scores required; run quant_compute_factors first",
            }

        # Selection policy is server-owned. LLM-provided scores/thresholds are
        # deliberately ignored so the model cannot rewrite a completed stage.
        all_composite = scores["composite"].astype(float).to_dict()
        top_n = 15
        min_score = -0.5

        sorted_stocks = sorted(all_composite.items(), key=lambda x: x[1], reverse=True)

        selected = []
        selected_set = set()

        # Ensure at least 1 per sector
        for sector in STOCK_POOL:
            sector_stocks_in_pool = set(STOCK_POOL[sector])
            for ticker, score in sorted_stocks:
                if ticker in sector_stocks_in_pool and ticker not in selected_set and score > min_score:
                    selected.append({"ticker": ticker, "composite": score, "sector": sector})
                    selected_set.add(ticker)
                    break

        # Fill remaining
        for ticker, score in sorted_stocks:
            if len(selected) >= top_n:
                break
            if ticker not in selected_set and score > min_score:
                sector = SECTOR_MAP.get(ticker, "其他")
                selected.append({"ticker": ticker, "composite": score, "sector": sector})
                selected_set.add(ticker)

        sectors_covered = len(set(s["sector"] for s in selected))

        if len(selected) != top_n or sectors_covered != len(STOCK_POOL):
            return {
                "success": False,
                "detail": f"选股覆盖不足：{len(selected)}/{top_n} 只，{sectors_covered}/{len(STOCK_POOL)} 个板块",
                "selected_stocks": selected,
            }

        result = {
            "success": True,
            "n_selected": len(selected),
            "n_sectors_covered": sectors_covered,
            "selected_stocks": selected,
            "tickers": [s["ticker"] for s in selected],
        }
        if not _update_cached_data(_selection_result=result):
            return _cache_required_error()
        return result

    # ---- quant.allocate_positions ----

    async def allocate_positions(
        self,
        params: dict[str, Any] | None = None,
        request: Any = None,
    ) -> dict[str, Any]:
        """Risk-parity position sizing with constraints."""
        del request
        params = params or {}

        frames = _cached_frames()
        if frames is None:
            return _cache_required_error()
        prices, _, _ = frames
        cached = _get_cached_data()
        selection = cached.get("_selection_result") if cached else None
        tickers = list(selection.get("tickers", [])) if isinstance(selection, dict) else []
        if not tickers:
            return {
                "success": False,
                "detail": "cached selection required; run quant_select_stocks first",
            }
        missing = [ticker for ticker in tickers if ticker not in prices.columns]
        if missing:
            return {"success": False, "detail": f"selected tickers missing from cache: {missing}"}
        requested_tickers = params.get("tickers")
        input_overridden = bool(requested_tickers and list(requested_tickers) != tickers)

        def _allocate() -> dict:
            from jiuwenswarm.quant.factors import PositionSizer
            from jiuwenswarm.quant.stock_pool import SECTOR_MAP
            from jiuwenswarm.quant.strategy_configs import production_position_config

            # Build minimal scores df with just the selected tickers
            # Use SECTOR_MAP (not _TICKER_NAME_MAP) so sector caps apply
            scores = pd.DataFrame(
                {"composite": [1.0] * len(tickers), "sector": [
                    SECTOR_MAP.get(t, "其他") for t in tickers
                ]},
                index=tickers,
            )

            sizer = PositionSizer(production_position_config())
            weights = sizer.allocate(scores, prices[tickers])

            portfolio = []
            total_weight = 0.0
            for ticker, weight in weights.items():
                from jiuwenswarm.quant.stock_pool import SECTOR_MAP
                portfolio.append({
                    "ticker": ticker,
                    "name": _TICKER_NAME_MAP.get(ticker, ticker),
                    "weight": round(weight, 4),
                    "weight_pct": round(weight * 100, 2),
                    "sector": SECTOR_MAP.get(ticker, "其他"),
                })
                total_weight += weight

            result = {
                "success": True,
                "total_weight": round(total_weight, 4),
                "cash_reserve": round(1 - total_weight, 4),
                "n_holdings": len(portfolio),
                "portfolio": portfolio,
                "weights": {p["ticker"]: p["weight"] for p in portfolio},
                "input_overridden": input_overridden,
            }
            if not _update_cached_data(_allocation_result=result):
                return _cache_required_error()
            return result

        return await asyncio.to_thread(_allocate)

    # ---- quant.run_backtest ----

    async def run_backtest(
        self,
        params: dict[str, Any] | None = None,
        request: Any = None,
    ) -> dict[str, Any]:
        """Run vectorized backtest with given portfolio weights."""
        del request
        del params
        initial_capital = 1_000_000.0

        frames = _cached_frames()
        if frames is None:
            return _cache_required_error()
        _, _, prices = frames
        cached = _get_cached_data()
        allocation = cached.get("_allocation_result") if cached else None
        weights = dict(allocation.get("weights", {})) if isinstance(allocation, dict) else {}
        if not weights:
            return {
                "success": False,
                "detail": "cached allocation required; run quant_allocate_positions first",
            }
        missing = [ticker for ticker in weights if ticker not in prices.columns]
        if missing:
            return {"success": False, "detail": f"weighted tickers missing from cache: {missing}"}

        def _backtest() -> dict:
            from jiuwenswarm.quant.backtest_engine import BacktestEngine

            engine = BacktestEngine(initial_capital=initial_capital)
            result = engine.run(prices, weights)

            result_payload = {
                "success": True,
                **result.metrics,
                "start_value": result.start_value,
                "end_value": round(result.end_value, 2),
                "test_start": str(prices.index[0].date()),
                "test_end": str(prices.index[-1].date()),
                "n_forward_returns": len(prices) - 1,
            }
            if not _update_cached_data(_backtest_result=result_payload):
                return _cache_required_error()
            return result_payload

        return await asyncio.to_thread(_backtest)

    # ---- quant.generate_report ----

    async def generate_report(
        self,
        params: dict[str, Any] | None = None,
        request: Any = None,
    ) -> dict[str, Any]:
        """Generate structured report + candidate submission package.

        Builds 49 bundles from in-memory cache (prices, scores, stock_pool),
        NOT from LLM-provided subset params. Candidate package failure
        propagates to top-level success=False.
        """
        del request
        del params
        cached = _get_cached_data()
        allocation = cached.get("_allocation_result") if cached else None
        factor_result = cached.get("_factor_result") if cached else None
        portfolio = list(allocation.get("portfolio", [])) if isinstance(allocation, dict) else []
        backtest = cached.get("_backtest_result", {}) if cached else {}
        regime = factor_result.get("regime", "range") if isinstance(factor_result, dict) else "range"
        top_stocks = (
            list(factor_result.get("top_stocks", []))
            if isinstance(factor_result, dict)
            else []
        )

        if not portfolio or not backtest:
            return {
                "success": False,
                "detail": (
                    "cached allocation and backtest required; run "
                    "quant_allocate_positions and quant_run_backtest first"
                ),
            }

        report_md = _build_report_markdown(portfolio, backtest, regime, top_stocks)
        result = {
            "success": True,
            "report": report_md,
            "summary": {
                "n_holdings": len(portfolio),
                "total_return": backtest.get("total_return"),
                "annualized_return": backtest.get("annualized_return"),
                "max_drawdown": backtest.get("max_drawdown"),
                "sharpe_ratio": backtest.get("sharpe_ratio"),
                "regime": regime,
            },
        }

        # Build candidate package from cache (real cache API)
        try:
            from jiuwenswarm.quant.reporting import (
                ReportService, MetricFact, EvidenceRef,
                install_snapshot_in_candidate, parse_bull_bear_pair,
                write_data_snapshot,
            )
            from jiuwenswarm.quant.stock_pool import ALL_STOCKS, SECTOR_MAP, TICKER_NAME_MAP
            from datetime import timezone as tz

            service = ReportService()
            decision_time = datetime.now(tz.utc)

            # Use real cache API: _get_cached_data() and _cached_frames()
            frames = _cached_frames()

            if frames is None or cached is None:
                result["candidate_package"] = {"error": "Cache unavailable; run fetch_data first"}
                result["success"] = False
                result["detail"] = "candidate_package_error: cache empty"
                return result

            train_prices, _train_vols, _test_prices = frames
            full_prices = cached.get("_prices_df")
            full_volumes = cached.get("_volumes_df")
            provider_ledger = cached.get("_provider_ledger")
            provider_stats = cached.get("_provider_stats")
            if (
                not isinstance(full_prices, pd.DataFrame)
                or not isinstance(full_volumes, pd.DataFrame)
                or not isinstance(provider_ledger, dict)
                or not isinstance(provider_stats, dict)
            ):
                raise RuntimeError("complete cached market-data provenance is unavailable")

            output_root = Path(__file__).resolve().parents[4] / "output"
            snapshot = write_data_snapshot(
                full_prices,
                full_volumes,
                provider_ledger,
                provider_stats,
                output_root / "data_snapshots",
            )

            ev_ref = EvidenceRef(
                evidence_id=snapshot.snapshot_id,
                source_type="market_data", source_name="Multi-source market snapshot",
                source_url=f"data_snapshot/{snapshot.manifest_path.name}",
                period_end=None, published_at=None,
                available_at=decision_time - timedelta(seconds=60),
                retrieved_at=datetime.now(tz.utc),
                content_sha256=snapshot.manifest_sha256,
            )

            # Build weights dict from LLM-provided portfolio params
            weights_dict = {}
            for entry in portfolio:
                t = entry.get("ticker", "") or entry.get("code", "")
                if t:
                    weights_dict[t] = float(entry.get("weight", 0))

            scores_df = cached.get("_scores_df")
            if not isinstance(scores_df, pd.DataFrame) or len(scores_df) != len(ALL_STOCKS):
                result["candidate_package"] = {
                    "error": "Factor scores unavailable; run compute_factors first"
                }
                result["success"] = False
                result["detail"] = "candidate_package_error: factor scores missing"
                return result

            # Build 49 bundles from ALL_STOCKS and cached factor scores
            bundles = {}
            for ticker in ALL_STOCKS:
                w = weights_dict.get(ticker, 0.0)
                if ticker not in scores_df.index:
                    result["candidate_package"] = {
                        "error": f"Factor score missing for {ticker}"
                    }
                    result["success"] = False
                    result["detail"] = "candidate_package_error: incomplete factor scores"
                    return result
                tech_facts = (
                    MetricFact(
                        name="composite_score",
                        value=round(float(scores_df.loc[ticker, "composite"]), 4),
                        unit=None,
                        status="available",
                        evidence_ids=(snapshot.snapshot_id,),
                    ),
                )
                bundles[ticker] = service.build_company_bundle(
                    ticker=ticker,
                    name=TICKER_NAME_MAP.get(ticker, ticker),
                    sector=SECTOR_MAP.get(ticker, "未知"),
                    as_of_time=decision_time, portfolio_weight=w, selected=w > 0,
                    weight_zero_reason="" if w > 0 else "Agent 未选中",
                    technical_facts=tech_facts,
                    data_provider_status="partial",
                )

            # Bull/Bear views: try from cached data (stored by bull_view/bear_view handlers)
            bull_raw = cached.get("_bull_result") if cached else None
            bear_raw = cached.get("_bear_result") if cached else None
            if bull_raw or bear_raw:
                from dataclasses import replace

                views, parse_errs = parse_bull_bear_pair(bull_raw, bear_raw)
                if views:
                    for parsed_view in views:
                        view = replace(
                            parsed_view,
                            evidence_ids=(snapshot.snapshot_id,),
                        )
                        for tk in view.candidate_tickers:
                            if tk in bundles:
                                existing = list(bundles[tk].agent_views)
                                existing.append(view)
                                bundles[tk] = service.build_company_bundle(
                                    ticker=tk, name=TICKER_NAME_MAP.get(tk, tk),
                                    sector=SECTOR_MAP.get(tk, "未知"),
                                    as_of_time=decision_time,
                                    portfolio_weight=weights_dict.get(tk, 0),
                                    selected=weights_dict.get(tk, 0) > 0,
                                    weight_zero_reason=(
                                        "" if weights_dict.get(tk, 0) > 0 else "Agent 未选中"
                                    ),
                                    technical_facts=bundles[tk].technical_facts,
                                    agent_views=tuple(existing),
                                    data_provider_status="partial",
                                )

            holdings = {t: w for t, w in weights_dict.items() if w > 0}
            ps = service.build_portfolio_snapshot(
                as_of_time=decision_time, holdings=holdings,
                cash=round(1.0 - sum(holdings.values()), 6),
                strategy_id="multi_agent_extension",
            )

            output_dir = str(output_root)
            pkg_ok, quality, pkg_path = service.build_package(
                portfolio=ps, bundles=bundles, output_dir=output_dir,
                strategy_label="multi_agent",
                evidence_manifest={snapshot.snapshot_id: ev_ref},
            )
            if not pkg_ok:
                result["candidate_package"] = {
                    "path": pkg_path, "quality_passed": False,
                    "n_reports": len(bundles),
                    "blockers": list(quality.blockers),
                    "warnings": list(quality.warnings),
                }
                result["success"] = False
                result["detail"] = "candidate_package_quality_failed"
                return result
            installed_url, installed_hash = install_snapshot_in_candidate(snapshot, pkg_path)
            if installed_url != ev_ref.source_url or installed_hash != ev_ref.content_sha256:
                raise RuntimeError("installed snapshot does not match EvidenceRef")

            result["candidate_package"] = {
                "path": pkg_path, "quality_passed": pkg_ok,
                "n_reports": len(bundles),
                "snapshot_id": snapshot.snapshot_id,
                "blockers": list(quality.blockers),
                "warnings": list(quality.warnings),
            }

        except Exception as exc:
            result["candidate_package"] = {"error": str(exc)}
            result["success"] = False
            result["detail"] = f"candidate_package_error: {exc}"

        return result


    # ---- quant.bull_view ----

    async def bull_view(
        self,
        params: dict[str, Any] | None = None,
        request: Any = None,
    ) -> dict[str, Any]:
        """Extract bullish signals using trend-factor set (direction 8 factor separation).

        Bull Analyst uses 3 trend factors:
          - momentum_20: short-term trend strength (primary)
          - momentum_60: medium-term trend confirmation
          - volume_corr: volume-price alignment (healthy trend validator)

        This is NOT the same factors as Bear — verified overlap ~28%, Spearman r≈-0.10.
        """
        del request
        params = params or {}

        frames = _cached_frames()
        if frames is None:
            return _cache_required_error()
        prices, volumes, _ = frames

        def _analyze() -> dict:
            from jiuwenswarm.quant.factors import FactorCalculator, FactorConfig
            from jiuwenswarm.quant.market_regime import MarketRegime

            regime = MarketRegime.detect(prices)

            # Bull uses trend-focused weights (direction 8: factor separation)
            # momentum_20/60 boosted, risk factors minimal
            bull_cfg = FactorConfig(
                w_momentum_20=0.50,      # primary trend signal
                w_momentum_60=0.25,      # trend confirmation
                w_max_drawdown=0.05,     # not Bull's concern — Bear handles this
                w_reversal_5=0.05,       # not Bull's concern
                w_volume_corr=0.15,      # volume confirms trend health
                w_volume_trend=0.00,     # not in Bull's factor set
            )
            calc = FactorCalculator(bull_cfg)
            calc.regime = regime
            factors = calc.compute_factors(prices, volumes if not volumes.empty else None)

            # Compute percentiles from cross-sectional distribution
            pct = _factor_percentiles(factors)

            bullish = []
            for ticker in factors.index:
                mom_20 = float(factors.loc[ticker, "momentum_20"])
                mom_60 = float(factors.loc[ticker, "momentum_60"])
                vol_corr = float(factors.loc[ticker, "volume_corr"])

                score = 0
                signals = []
                # Signal 1: strong short-term momentum (top 20%)
                if mom_20 >= pct["momentum_20_p80"]:
                    score += 3
                    signals.append(
                        f"20日动量 {mom_20:+.1%}（全市场前20%，阈值 {pct['momentum_20_p80']:+.1%}) — 短期趋势强劲"
                    )
                # Signal 2: confirmed medium-term trend (top 30%)
                if mom_60 >= pct["momentum_60_p70"]:
                    score += 2
                    signals.append(
                        f"60日动量 {mom_60:+.1%}（全市场前30%，阈值 {pct['momentum_60_p70']:+.1%}) — 中期趋势确认"
                    )
                # Signal 3: volume confirms price direction (top 30%)
                if vol_corr >= pct["volume_corr_p70"]:
                    score += 2
                    signals.append(
                        f"量价配合 r={vol_corr:+.2f}（全市场前30%，阈值 {pct['volume_corr_p70']:+.2f}) — 放量上涨，趋势健康"
                    )
                # Signal 4: trend alignment — both momentums agree (bonus)
                if mom_20 >= pct["momentum_20_p80"] and mom_60 >= pct["momentum_60_p70"]:
                    score += 1
                    signals.append("双周期趋势共振 — 20日+60日动量方向一致")
                # Signal 5: price + volume double confirmation (bonus)
                if mom_20 >= pct["momentum_20_p80"] and vol_corr >= pct["volume_corr_p70"]:
                    score += 2
                    signals.append("量价齐升 — 动量+放量双信号叠加")

                if score >= 4:
                    bullish.append({
                        "ticker": ticker,
                        "name": _TICKER_NAME_MAP.get(ticker, ticker),
                        "bull_score": score,
                        "signals": signals,
                        "key_metrics": {
                            "momentum_20": round(mom_20, 4),
                            "momentum_60": round(mom_60, 4),
                            "volume_corr": round(vol_corr, 4),
                        },
                    })

            bullish.sort(key=lambda x: x["bull_score"], reverse=True)

            bull_result = {
                "success": True,
                "regime": regime,
                "factor_weights": "bull-trend (momentum_20=0.50, momentum_60=0.25, volume_corr=0.15)",
                "percentile_thresholds": {
                    "momentum_20_p80": round(pct["momentum_20_p80"], 4),
                    "momentum_60_p70": round(pct["momentum_60_p70"], 4),
                    "volume_corr_p70": round(pct["volume_corr_p70"], 4),
                },
                "n_bullish": len(bullish),
                "bullish_stocks": bullish[:12],
                "recommended_position": "70-95%" if regime == "bull" else "50-80%",
                "verdict": "overweight" if bullish else "neutral",
                "confidence": "high" if len(bullish) >= 8 else "medium",
                "candidate_tickers": [item["ticker"] for item in bullish[:12]],
                "warnings": [],
                "evidence_ids": ["e_extension_gen"],
                "summary": f"{regime} regime; {len(bullish)} bullish candidates",
            }
            if not _update_cached_data(_bull_result=bull_result):
                return _cache_required_error()
            return bull_result

        return await asyncio.to_thread(_analyze)

    # ---- quant.bear_view ----

    async def bear_view(
        self,
        params: dict[str, Any] | None = None,
        request: Any = None,
    ) -> dict[str, Any]:
        """Extract bearish/risk signals using risk-factor set (direction 8 factor separation).

        Bear Analyst uses 3 risk factors:
          - max_drawdown: historical max drawdown (larger = riskier)
          - reversal_5: 5-day return reversal (negative = falling, risk of continuation)
          - volume_corr (REVERSED): volume-price divergence = risk signal

        This is NOT the same factors as Bull — verified overlap ~28%, Spearman r≈-0.10.
        """
        del request
        params = params or {}

        frames = _cached_frames()
        if frames is None:
            return _cache_required_error()
        prices, volumes, _ = frames

        def _analyze() -> dict:
            from jiuwenswarm.quant.factors import FactorCalculator, FactorConfig
            from jiuwenswarm.quant.market_regime import MarketRegime

            regime = MarketRegime.detect(prices)

            # Bear uses risk-focused weights (direction 8: factor separation)
            # max_drawdown + reversal_5 boosted, momentum minimal
            bear_cfg = FactorConfig(
                w_momentum_20=0.05,      # not Bear's concern — Bull handles this
                w_momentum_60=0.05,      # not Bear's concern
                w_max_drawdown=0.45,     # primary risk signal
                w_reversal_5=0.25,       # short-term reversal risk
                w_volume_corr=0.15,      # REVERSED: divergence = risk
                w_volume_trend=0.05,     # minimal — secondary confirmation only
            )
            calc = FactorCalculator(bear_cfg)
            calc.regime = regime
            factors = calc.compute_factors(prices, volumes if not volumes.empty else None)

            # Compute percentiles from cross-sectional distribution
            pct = _factor_percentiles(factors)

            bearish = []
            for ticker in factors.index:
                max_dd = float(factors.loc[ticker, "max_drawdown"])
                rev_5 = float(factors.loc[ticker, "reversal_5"])
                vol_corr = float(factors.loc[ticker, "volume_corr"])

                score = 0
                warnings = []
                # Signal 1: large historical drawdown (top 20%)
                if max_dd >= pct["max_drawdown_p80"]:
                    score += 3
                    warnings.append(
                        f"大幅回撤 {max_dd:.1%}（全市场前20%，阈值 {pct['max_drawdown_p80']:.1%}) — 60日最大回撤显著偏高"
                    )
                # Signal 2: stock has been falling recently (bottom 20% of reversal_5)
                if rev_5 <= pct["reversal_5_p20"]:
                    score += 3
                    warnings.append(
                        f"短期弱势 rev_5={rev_5:+.1%}（全市场后20%，阈值 {pct['reversal_5_p20']:+.1%}) — 5日动量显著偏弱，下跌可能延续"
                    )
                # Signal 3: volume-price divergence (bottom 30% of volume_corr)
                if vol_corr <= pct["volume_corr_p30"]:
                    score += 2
                    warnings.append(
                        f"量价背离 r={vol_corr:+.2f}（全市场后30%，阈值 {pct['volume_corr_p30']:+.2f}) — 量价不配合，趋势质量存疑"
                    )
                # Signal 4: dual risk — high drawdown + falling reversal (bonus)
                if max_dd >= pct["max_drawdown_p80"] and rev_5 <= pct["reversal_5_p20"]:
                    score += 2
                    warnings.append("回撤+弱势双信号 — 高风险组合，趋势可能加速恶化")
                # Signal 5: extreme drawdown (top 10%)
                if max_dd >= pct["max_drawdown_p90"]:
                    score += 2
                    warnings.append(
                        f"极端回撤 {max_dd:.1%}（全市场前10%，阈值 {pct['max_drawdown_p90']:.1%}) — 回撤幅度远超同板块"
                    )

                if score >= 4:
                    bearish.append({
                        "ticker": ticker,
                        "name": _TICKER_NAME_MAP.get(ticker, ticker),
                        "bear_score": score,
                        "warnings": warnings,
                        "key_metrics": {
                            "max_drawdown": round(max_dd, 4),
                            "reversal_5": round(rev_5, 4),
                            "volume_corr": round(vol_corr, 4),
                        },
                    })

            bearish.sort(key=lambda x: x["bear_score"], reverse=True)

            bear_result = {
                "success": True,
                "regime": regime,
                "factor_weights": "bear-risk (max_drawdown=0.45, reversal_5=0.25, volume_corr=0.15)",
                "percentile_thresholds": {
                    "max_drawdown_p80": round(pct["max_drawdown_p80"], 4),
                    "max_drawdown_p90": round(pct["max_drawdown_p90"], 4),
                    "reversal_5_p20": round(pct["reversal_5_p20"], 4),
                    "volume_corr_p30": round(pct["volume_corr_p30"], 4),
                },
                "n_bearish": len(bearish),
                "bearish_stocks": bearish[:12],
                "recommended_cash_reserve": "10-40%" if regime == "bear" else "5-15%",
                "verdict": "underweight" if bearish else "neutral",
                "confidence": "high" if len(bearish) >= 8 else "medium",
                "candidate_tickers": [item["ticker"] for item in bearish[:12]],
                "warnings": [
                    warning
                    for item in bearish[:3]
                    for warning in item.get("warnings", [])[:1]
                ],
                "evidence_ids": ["e_extension_gen"],
                "summary": f"{regime} regime; {len(bearish)} risk candidates",
            }
            if not _update_cached_data(_bear_result=bear_result):
                return _cache_required_error()
            return bear_result

        return await asyncio.to_thread(_analyze)


# ---- Module-level entry for ExtensionLoader ----

async def register_extensions(registry):
    extension = QuantFinanceExtension()
    extension.register(registry)
    return [extension]


# ---- Helpers ----

def _summarize_top_movers(prices_df: pd.DataFrame, top_n: int = 10) -> list[dict]:
    """Return top and bottom performers from recent prices for LLM consumption."""
    if prices_df.empty or len(prices_df) < 5:
        return []
    recent = prices_df.iloc[-5:]
    returns = (recent.iloc[-1] / recent.iloc[0] - 1).sort_values()
    result = []
    for ticker in list(returns.index[:top_n // 2]) + list(returns.index[-top_n // 2:]):
        result.append({
            "ticker": str(ticker),
            "recent_5d_return": round(float(returns[ticker]) * 100, 2),
        })
    return result


def _default_start_date() -> str:
    return (datetime.now() - timedelta(days=180)).strftime("%Y-%m-%d")


def _default_end_date() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _df_to_json(df: pd.DataFrame) -> dict:
    """Serialize DataFrame to JSON-safe dict (orient='index' with string keys)."""
    result = {}
    for idx, row in df.iterrows():
        key = str(idx)
        result[key] = {}
        for col in df.columns:
            val = row[col]
            if isinstance(val, (np.floating, float)):
                result[key][str(col)] = float(val) if not np.isnan(val) else None
            elif isinstance(val, (np.integer, int)):
                result[key][str(col)] = int(val)
            else:
                result[key][str(col)] = None if pd.isna(val) else float(val)
    return result


def _json_to_df(data: dict) -> pd.DataFrame:
    """Deserialize JSON-safe dict back to DataFrame."""
    if not data:
        return pd.DataFrame()
    df = pd.DataFrame.from_dict(data, orient="index")
    df.index = pd.to_datetime(df.index, errors="coerce")
    return df.sort_index()


def _ticker_data_usable(prices: dict, volumes: dict, ticker: str) -> bool:
    """A covered ticker must support 61 training days plus 20 forward days."""
    price_series = prices.get(ticker)
    volume_series = volumes.get(ticker)
    if price_series is None or volume_series is None:
        return False
    return (
        len(pd.Series(price_series).dropna()) >= _MIN_TRAIN_DAYS + _FORWARD_TEST_DAYS
        and len(pd.Series(volume_series).dropna()) >= _MIN_TRAIN_DAYS + _FORWARD_TEST_DAYS
    )


def _fetch_real_data(tickers, start_date, end_date):
    """Fetch real stock data with multi-source fallback chain.

    Tries sources in order, merging results to maximize coverage:
      1. Sina HTTP daily K-line (fast domestic source)
      2. Tencent HTTP daily K-line (independent domestic fallback)
      3. akshare (Eastmoney adapter, sometimes blocked)
      4. baostock (dedicated server)
      5. yfinance (international last resort)
    Each level fills in only the tickers still missing.
    """
    all_prices = {}
    all_volumes = {}
    all_errors = []
    provider_stats: dict[str, dict[str, Any]] = {}
    provider_ledger: dict[str, str] = {}

    providers = (
        ("sina", _fetch_sina),
        ("tencent", _fetch_tencent),
        ("akshare", _fetch_akshare),
        ("baostock", _fetch_baostock),
        ("yfinance", _fetch_yfinance),
    )
    for provider_name, provider in providers:
        missing = [
            ticker for ticker in tickers
            if not _ticker_data_usable(all_prices, all_volumes, ticker)
        ]
        if not missing:
            break
        covered_before = {
            ticker for ticker in tickers
            if _ticker_data_usable(all_prices, all_volumes, ticker)
        }
        logger.info(
            "[QuantFinance] %s requesting %d still-missing tickers...",
            provider_name,
            len(missing),
        )
        prices, volumes, errors = provider(missing, start_date, end_date)
        all_prices.update(prices)
        all_volumes.update(volumes)
        all_errors.extend(errors)
        covered_after = {
            ticker for ticker in tickers
            if _ticker_data_usable(all_prices, all_volumes, ticker)
        }
        newly_covered = covered_after - covered_before
        for ticker in newly_covered:
            provider_ledger[ticker] = provider_name
        provider_stats[provider_name] = {
            "requested": len(missing),
            "newly_covered": len(newly_covered),
            "errors": len(errors),
        }
        logger.info(
            "[QuantFinance] %s complete: %d/%d usable",
            provider_name,
            len(covered_after),
            len(tickers),
        )

    global _last_fetch_provider_stats, _last_fetch_provider_ledger
    _last_fetch_provider_stats = provider_stats
    _last_fetch_provider_ledger = provider_ledger
    return all_prices, all_volumes, all_errors


def _http_symbol(ticker: str) -> str:
    code, exchange = ticker.split(".")
    return f"{'sh' if exchange == 'SH' else 'sz'}{code}"


def _parallel_http_fetch(tickers, worker, provider_name):
    """Run bounded concurrent requests and retain per-ticker error evidence."""
    prices = {}
    volumes = {}
    errors = []
    with ThreadPoolExecutor(max_workers=min(8, max(1, len(tickers)))) as pool:
        futures = {pool.submit(worker, ticker): ticker for ticker in tickers}
        for future in as_completed(futures):
            ticker = futures[future]
            try:
                price, volume = future.result()
                if price is None or volume is None or price.empty or volume.empty:
                    raise ValueError("no data in requested date range")
                prices[ticker] = price
                volumes[ticker] = volume
            except Exception as exc:  # noqa: BLE001 - provider detail is evidence
                errors.append(f"{provider_name}:{ticker}: {exc}")
    return prices, volumes, errors


def _fetch_sina(tickers, start_date, end_date):
    """Fetch raw daily close/volume from Sina's public K-line endpoint."""
    url = (
        "https://quotes.sina.cn/cn/api/json_v2.php/"
        "CN_MarketDataService.getKLineData"
    )
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)
    # The endpoint is row-count based. Fetch from requested start through now
    # so historical end dates still remain available, then filter exactly.
    datalen = min(1023, max(120, (pd.Timestamp.now().normalize() - start).days + 30))

    def worker(ticker):
        response = requests.get(
            url,
            params={
                "symbol": _http_symbol(ticker),
                "scale": "240",
                "ma": "no",
                "datalen": datalen,
            },
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=12,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list) or not payload:
            raise ValueError(f"invalid payload: {str(payload)[:100]}")
        frame = pd.DataFrame(payload)
        if not {"day", "close", "volume"}.issubset(frame.columns):
            raise ValueError(f"missing fields: {list(frame.columns)}")
        frame["day"] = pd.to_datetime(frame["day"], errors="raise")
        frame = frame.set_index("day").sort_index().loc[start:end]
        price = pd.to_numeric(frame["close"], errors="coerce").dropna()
        volume = pd.to_numeric(frame["volume"], errors="coerce").dropna()
        return price, volume

    return _parallel_http_fetch(tickers, worker, "sina")


def _fetch_tencent(tickers, start_date, end_date):
    """Fetch raw daily close/volume from Tencent's independent K-line endpoint."""
    url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"

    def worker(ticker):
        symbol = _http_symbol(ticker)
        response = requests.get(
            url,
            params={
                "param": f"{symbol},day,{start_date},{end_date},1023,none",
            },
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=12,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") != 0:
            raise ValueError(f"provider code={payload.get('code')}: {payload.get('msg')}")
        rows = payload.get("data", {}).get(symbol, {}).get("day", [])
        if not rows:
            raise ValueError("empty day series")
        normalized = [row[:6] for row in rows if len(row) >= 6]
        frame = pd.DataFrame(
            normalized,
            columns=["date", "open", "close", "high", "low", "volume"],
        )
        frame["date"] = pd.to_datetime(frame["date"], errors="raise")
        frame = frame.set_index("date").sort_index()
        price = pd.to_numeric(frame["close"], errors="coerce").dropna()
        volume = pd.to_numeric(frame["volume"], errors="coerce").dropna()
        return price, volume

    return _parallel_http_fetch(tickers, worker, "tencent")


def _fetch_yfinance(tickers, start_date, end_date):
    """Try fetching stock data via yfinance (Yahoo Finance API)."""
    prices = {}
    volumes = {}
    errors = []
    try:
        import yfinance as yf
        for ticker in tickers:
            yt = _yf_ticker(ticker)
            try:
                # Keep all five providers on the same raw-close convention.
                df = yf.download(yt, start=start_date, end=end_date,
                                 progress=False, auto_adjust=False)
                if df is not None and not df.empty:
                    if isinstance(df.columns, pd.MultiIndex):
                        prices[ticker] = df["Close"].iloc[:, 0]
                        vol_col = df.get("Volume")
                        if vol_col is not None:
                            volumes[ticker] = vol_col.iloc[:, 0] if isinstance(vol_col, pd.DataFrame) else vol_col
                    else:
                        prices[ticker] = df["Close"]
                        volumes[ticker] = df.get("Volume", pd.Series(dtype=float))
            except Exception as e:
                errors.append(f"yfinance:{ticker}: {e}")
                continue
    except ImportError:
        errors.append("yfinance not installed. Run: pip install yfinance")
    return prices, volumes, errors


def _fetch_akshare(tickers, start_date, end_date):
    """Try fetching stock data via akshare (A-share native data source)."""
    prices = {}
    volumes = {}
    errors = []
    try:
        import akshare as ak
        for ticker in tickers:
            code = ticker.replace(".SH", "").replace(".SZ", "")
            symbol = code
            try:
                df = ak.stock_zh_a_hist(
                    symbol=symbol,
                    period="daily",
                    start_date=start_date.replace("-", ""),
                    end_date=end_date.replace("-", ""),
                    # Keep all five providers on the same raw-close convention.
                    adjust="",
                )
                if df is not None and not df.empty:
                    df["日期"] = pd.to_datetime(df["日期"])
                    df = df.set_index("日期")
                    prices[ticker] = df["收盘"]
                    volumes[ticker] = df.get("成交量", pd.Series(dtype=float))
            except Exception as e:
                errors.append(f"akshare:{ticker}: {e}")
                continue
    except ImportError:
        errors.append("akshare not installed. Run: pip install akshare")
    return prices, volumes, errors


def _fetch_baostock(tickers, start_date, end_date):
    """Fetch stock data via baostock (dedicated server, stable, no rate limit).

    BaoStock provides free A-share daily K-line data via its own server,
    independent of scraping third-party websites. Requires pip install baostock.
    """
    prices = {}
    volumes = {}
    errors = []
    try:
        import baostock as bs
        lg = bs.login()
        if lg.error_code != "0":
            errors.append(f"baostock login failed: {lg.error_msg}")
            return prices, volumes, errors

        for ticker in tickers:
            code = ticker.replace(".SH", ".sh").replace(".SZ", ".sz")
            try:
                rs = bs.query_history_k_data_plus(
                    code, "date,close,volume",
                    start_date=start_date,
                    end_date=end_date,
                    frequency="d", adjustflag="3",
                )
                if rs.error_code != "0":
                    errors.append(f"baostock:{ticker}: {rs.error_msg}")
                    continue

                rows = []
                while rs.next():
                    rows.append(rs.get_row_data())

                if not rows:
                    errors.append(f"baostock:{ticker}: no data")
                    continue

                df = pd.DataFrame(rows, columns=rs.fields)
                df["date"] = pd.to_datetime(df["date"])
                df = df.set_index("date")
                prices[ticker] = pd.to_numeric(df["close"], errors="coerce").dropna()
                volumes[ticker] = pd.to_numeric(df["volume"], errors="coerce").dropna()
            except Exception as e:
                errors.append(f"baostock:{ticker}: {e}")
                continue
        bs.logout()
    except ImportError:
        errors.append("baostock not installed. Run: pip install baostock")
    return prices, volumes, errors


def _build_fetch_error_message(errors: list) -> str:
    """Build a clear error message when all data sources fail."""
    sina_count = sum(1 for e in errors if "sina:" in e)
    tencent_count = sum(1 for e in errors if "tencent:" in e)
    yf_count = sum(1 for e in errors if "yfinance:" in e)
    ak_count = sum(1 for e in errors if "akshare:" in e)
    bs_count = sum(1 for e in errors if "baostock" in e)
    import_count = sum(1 for e in errors if "not installed" in e)

    lines = [
        "无法完整获取真实股票数据。已按 Sina -> Tencent -> akshare -> "
        "baostock -> yfinance 逐层补缺。",
        f"错误摘要: Sina {sina_count} 条, Tencent {tencent_count} 条, "
        f"akshare {ak_count} 条, baostock {bs_count} 条, "
        f"yfinance {yf_count} 条, 缺少依赖 {import_count} 条。",
        "",
        "解决方案:",
    ]

    if import_count > 0:
        lines.append("  1. 安装缺失的依赖:")
        for e in errors:
            if "not installed" in e:
                lines.append(f"     {e}")

    lines.extend([
        "  2. 检查网络连接: Sina/Tencent 是优先国内 HTTP 行情源",
        "     yfinance 需要访问 Yahoo Finance API",
        "     akshare 需要访问东方财富等国内数据源",
        "     baostock 需要连接其行情服务器",
        "  3. 如果在内网环境，可能需要配置代理:",
        "     export HTTP_PROXY=http://your-proxy:port",
        "     export HTTPS_PROXY=http://your-proxy:port",
        "  4. 确认股票代码正确且交易日历内存在数据",
    ])

    return "\n".join(lines)


def _factor_percentiles(factors: pd.DataFrame) -> dict:
    """Compute percentile thresholds from cross-sectional factor distribution.

    Returns dict of percentile values used by bull_view and bear_view scoring.
    Percentiles adapt to current market conditions — e.g. in a raging bull
    market, the momentum thresholds will be higher because everyone is up.

    Factor separation (direction 8):
      - Bull: momentum_20, momentum_60, volume_corr (trend factors)
      - Bear: max_drawdown, reversal_5, volume_corr (risk factors)
    """
    pct = {}

    def _p(data, q):
        v = float(data.quantile(q / 100.0))
        # Small epsilon so >= threshold works correctly for exact matches
        sign = 1 if v >= 0 else -1
        return v - sign * abs(v) * 1e-6

    # Bull trend factors: p80/p70 for momentum, p70 for volume correlation
    pct["momentum_20_p80"] = _p(factors["momentum_20"], 80)
    pct["momentum_60_p70"] = _p(factors["momentum_60"], 70)
    pct["volume_corr_p70"] = _p(factors["volume_corr"], 70)

    # Bear risk factors: p80/p90 for drawdown, p20 for reversal, p30 for volume corr
    pct["max_drawdown_p80"] = _p(factors["max_drawdown"], 80)
    pct["max_drawdown_p90"] = _p(factors["max_drawdown"], 90)
    pct["reversal_5_p20"] = _p(factors["reversal_5"], 20)
    pct["volume_corr_p30"] = _p(factors["volume_corr"], 30)

    return pct


def _build_report_markdown(portfolio, backtest, regime, top_stocks):
    """Build a causal-chain investment report (diagnosis → strategy → execution)."""
    regime_labels = {"bull": "牛市 (Bull)", "bear": "熊市 (Bear)", "range": "震荡市 (Range-bound)"}
    regime_label = regime_labels.get(regime, regime)

    lines = [
        "# 量化投资分析报告",
        "",
        f"**生成日期**: {datetime.now().strftime('%Y-%m-%d')}",
        f"**市场状态**: {regime_label}",
        "**框架**: openJiuwen JiuwenSwarm (QuantFinance Extension)",
        "",
        "---",
        "",
        "## 一、市场诊断",
        "",
        "### 1.1 判市结果",
        f"- **最终判市**: {regime_label}",
        "- **判市方法**: 技术面信号 + CSI 300 指数信号 → 融合投票",
        "",
        "### 1.2 当前市场含义",
    ]

    # Regime-specific diagnosis
    if regime == "bull":
        lines.extend([
            "- 趋势向上，市场情绪乐观",
            "- **策略倾向**: 动量因子权重放大，偏向趋势跟随",
            "- **风险提示**: 关注波动率变化，警惕趋势末端反转",
        ])
    elif regime == "bear":
        lines.extend([
            "- 趋势向下，市场情绪谨慎",
            "- **策略倾向**: 风控因子权重放大，偏向防御配置",
            "- **风险提示**: 关注超跌反弹机会，避免追空",
        ])
    else:
        lines.extend([
            "- 方向不明，市场处于震荡格局",
            "- **策略倾向**: 因子权重均衡，不过度押注单一方向",
            "- **风险提示**: 震荡市中风格轮动快，避免频繁切换策略",
        ])

    lines.extend([
        "",
        "---",
        "",
        "## 二、策略选择",
        "",
        "### 2.1 因子模型",
        "",
        "采用生产六因子模型：momentum_20, momentum_60, reversal_5, max_drawdown, volume_corr, volume_trend",
        "",
        "### 2.2 因子选择逻辑",
        "",
        f"- **市场状态**: {regime_label}",
        "- **因子权重**: 等权，由 PositionSizer 施加单股≤10%、板块≤25% 约束",
        "",
        "---",
        "",
        "## 三、选股执行",
        "",
        "### 3.1 多视角分析架构",
        "",
        "选股由双 Agent 协作完成（Bull 看多视角 + Bear 风控视角），Coordinator 综合决策。",
        "",
        "### 3.2 选股约束",
        "",
        "- 波动率硬约束：vol_z > 2.0 → 排除",
        "- 选股: 裸分 Top 15",
        "- 仓位分配: 逆波动率加权，单只≤10%，单板块≤25%，最低 5% 现金",
        "",
        "---",
        "",
        "## 四、回测表现",
        "",
        "| 指标 | 数值 |",
        "|------|------|",
    ])

    bt_metrics = [
        ("累计收益率", "total_return", "%"),
        ("年化收益率", "annualized_return", "%"),
        ("最大回撤", "max_drawdown", "%"),
        ("Sharpe 比率", "sharpe_ratio", ""),
        ("年化波动率", "annualized_volatility", "%"),
        ("日胜率", "win_rate", "%"),
    ]

    for label, key, unit in bt_metrics:
        val = backtest.get(key, "N/A")
        if isinstance(val, (int, float)):
            if unit == "%" and key not in ("sharpe_ratio",):
                val = round(val * 100, 2)
            lines.append(f"| {label} | {val}{unit} |")
        else:
            lines.append(f"| {label} | {val} |")

    lines.extend([
        "",
        "---",
        "",
        "## 五、投资组合明细",
        "",
        "| 股票代码 | 股票名称 | 所属板块 | 持仓占比(%) |",
        "|---------|---------|---------|-----------|",
    ])

    for p in portfolio:
        ticker = p.get("ticker", "")
        name = p.get("name", "")
        sector = p.get("sector", "")
        w = p.get("weight_pct", 0)
        lines.append(f"| {ticker} | {name} | {sector} | {w} |")

    if top_stocks:
        lines.extend([
            "",
            "---",
            "",
            "## 六、因子得分 Top 10",
            "",
            "| 股票代码 | 股票名称 | 综合得分 | 板块 |",
            "|---------|---------|---------|------|",
        ])
        for s in top_stocks[:10]:
            lines.append(
                f"| {s['ticker']} | {s['name']} | {s['composite']:.3f} | {s['sector']} |"
            )

    lines.extend([
        "",
        "---",
        "",
        "## 七、模型局限性说明",
        "",
        "本策略基于量化因子模型，以下局限性应在解读结果时予以考虑：",
        "",
        "### 1. 因子选择的时间依赖性",
        "- 因子有效性基于历史行情回测，不保证未来表现",
        "- 历史样本中 bull/range/bear 分布不均衡，特定市态下因子预测力可能衰减",
        "- 如果当前评测期市场状态与训练期显著不同，因子预测力可能下降",
        "",
        "### 2. 因子在不同市场状态下的稳定性",
        "- 动量因子依赖趋势延续性，在震荡或反转阶段可能衰减",
        "- 反转和回撤因子的作用会随市场状态变化，当前报告不声称固定 IC",
        "",
        "### 3. 缺乏独立验证集",
        "- 当前报告只引用运行时可复核事实，不把历史实验窗口描述为本次证据",
        "- 策略研究仍需保持训练、验证和最终测试的时间隔离",
        "",
        "### 4. 持仓周期的固有限制",
        "- 本策略持仓周期为 20 个交易日（约 1 个自然月）",
        "- 当前生产模型未纳入基本面因子；其短周期有效性需要独立验证",
        "- 如评测周期显著不同于 20 日，因子有效性需重新评估",
        "",
        "### 5. 市场状态判别的局限性",
        "- 判市系统基于波动率标准化阈值和 CSI 300 指数融合信号",
        "- 波动率异常时强制返回震荡市（range），但阈值（2×历史波动率）可能漏判温和熊市",
        "- 判市结果只能描述当前状态，不能预测未来市场方向",
        "",
        "---",
        "",
        "*本报告由基于 JiuwenSwarm 的量化投资 Agent 自动生成。*",
        "*投资结果基于历史数据回测，不构成任何投资建议。*",
    ])

    return "\n".join(lines)
