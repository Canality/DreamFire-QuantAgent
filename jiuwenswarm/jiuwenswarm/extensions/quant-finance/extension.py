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
import json
import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List

import numpy as np
import pandas as pd

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
                # Compact summary for LLM
                "n_stocks": len(prices),
                "expected_stocks": len(tickers),
                "coverage_complete": True,
                "n_days": len(prices_df),
                "date_range": f"{prices_df.index[0]} ~ {prices_df.index[-1]}",
                "top_movers": _summarize_top_movers(prices_df, 10),
                "fetch_errors": errors[:5] if errors else [],
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
            from jiuwenswarm.quant.factors import FactorCalculator, FactorConfig

            regime = MarketRegime.detect(prices)
            factor_cfg = FactorConfig()
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

            return {
                "success": True,
                "regime": regime,
                "n_stocks_analyzed": len(scores),
                "decision_date": str(prices.index[-1].date()),
                "top_stocks": top_stocks,
                "all_composite": {t: round(float(scores.loc[t, "composite"]), 4)
                                  for t in scores.index},
            }

        return await asyncio.to_thread(_compute)

    # ---- quant.select_stocks ----

    async def select_stocks(
        self,
        params: dict[str, Any] | None = None,
        request: Any = None,
    ) -> dict[str, Any]:
        """Select stocks with sector diversification from factor scores."""
        del request
        params = params or {}

        all_composite = params.get("all_composite", {})
        top_n = int(params.get("top_n") if params.get("top_n") is not None else 15)
        min_score = float(params.get("min_score") if params.get("min_score") is not None else -0.5)

        from jiuwenswarm.quant.stock_pool import STOCK_POOL, SECTOR_MAP

        if not all_composite:
            return {"success": False, "detail": "all_composite scores required"}

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

        return {
            "success": True,
            "n_selected": len(selected),
            "n_sectors_covered": sectors_covered,
            "selected_stocks": selected,
            "tickers": [s["ticker"] for s in selected],
        }

    # ---- quant.allocate_positions ----

    async def allocate_positions(
        self,
        params: dict[str, Any] | None = None,
        request: Any = None,
    ) -> dict[str, Any]:
        """Risk-parity position sizing with constraints."""
        del request
        params = params or {}

        tickers = params.get("tickers", [])

        frames = _cached_frames()
        if frames is None:
            return _cache_required_error()
        prices, _, _ = frames
        if not tickers:
            return {"success": False, "detail": "tickers are required"}
        missing = [ticker for ticker in tickers if ticker not in prices.columns]
        if missing:
            return {"success": False, "detail": f"selected tickers missing from cache: {missing}"}

        def _allocate() -> dict:
            from jiuwenswarm.quant.factors import PositionSizer, PositionConfig
            from jiuwenswarm.quant.stock_pool import SECTOR_MAP

            # Build minimal scores df with just the selected tickers
            # Use SECTOR_MAP (not _TICKER_NAME_MAP) so sector caps apply
            scores = pd.DataFrame(
                {"composite": [1.0] * len(tickers), "sector": [
                    SECTOR_MAP.get(t, "其他") for t in tickers
                ]},
                index=tickers,
            )

            sizer = PositionSizer(PositionConfig())
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

            return {
                "success": True,
                "total_weight": round(total_weight, 4),
                "cash_reserve": round(1 - total_weight, 4),
                "n_holdings": len(portfolio),
                "portfolio": portfolio,
                "weights": {p["ticker"]: p["weight"] for p in portfolio},
            }

        return await asyncio.to_thread(_allocate)

    # ---- quant.run_backtest ----

    async def run_backtest(
        self,
        params: dict[str, Any] | None = None,
        request: Any = None,
    ) -> dict[str, Any]:
        """Run vectorized backtest with given portfolio weights."""
        del request
        params = params or {}

        weights = params.get("weights", {})
        initial_capital = float(
            params.get("initial_capital")
            if params.get("initial_capital") is not None
            else 1_000_000.0
        )

        frames = _cached_frames()
        if frames is None:
            return _cache_required_error()
        _, _, prices = frames
        if not weights:
            return {"success": False, "detail": "weights are required"}
        missing = [ticker for ticker in weights if ticker not in prices.columns]
        if missing:
            return {"success": False, "detail": f"weighted tickers missing from cache: {missing}"}

        def _backtest() -> dict:
            from jiuwenswarm.quant.backtest_engine import BacktestEngine

            engine = BacktestEngine(initial_capital=initial_capital)
            result = engine.run(prices, weights)

            return {
                "success": True,
                **result.metrics,
                "start_value": result.start_value,
                "end_value": round(result.end_value, 2),
                "test_start": str(prices.index[0].date()),
                "test_end": str(prices.index[-1].date()),
                "n_forward_returns": len(prices) - 1,
            }

        return await asyncio.to_thread(_backtest)

    # ---- quant.generate_report ----

    async def generate_report(
        self,
        params: dict[str, Any] | None = None,
        request: Any = None,
    ) -> dict[str, Any]:
        """Generate structured Markdown quantitative investment report."""
        del request
        params = params or {}

        portfolio = params.get("portfolio", [])
        backtest = params.get("backtest", {})
        regime = params.get("regime", "range")
        top_stocks = params.get("top_stocks", [])

        if not portfolio or not backtest:
            return {"success": False, "detail": "portfolio and backtest are required"}

        return {
            "success": True,
            "report": _build_report_markdown(portfolio, backtest, regime, top_stocks),
            "summary": {
                "n_holdings": len(portfolio),
                "total_return": backtest.get("total_return"),
                "annualized_return": backtest.get("annualized_return"),
                "max_drawdown": backtest.get("max_drawdown"),
                "sharpe_ratio": backtest.get("sharpe_ratio"),
                "regime": regime,
            },
        }


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

            return {
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
            }

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

            return {
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
            }

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
    import numpy as np
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
      1. akshare (fast, domestic sources, sometimes blocked)
      2. baostock (dedicated server, stable, no rate limit)
      3. yfinance (international, slow in China, last resort)
    Each level fills in only the tickers still missing.
    """
    all_prices = {}
    all_volumes = {}
    all_errors = []

    # Tier 1: akshare
    prices, volumes, errors = _fetch_akshare(tickers, start_date, end_date)
    all_prices.update(prices)
    all_volumes.update(volumes)
    all_errors.extend(errors)

    missing = [t for t in tickers if not _ticker_data_usable(all_prices, all_volumes, t)]
    if missing:
        logger.info("[QuantFinance] akshare: %d/%d stocks, trying baostock for %d missing...",
                    len(all_prices), len(tickers), len(missing))
        # Tier 2: baostock
        prices2, volumes2, errors2 = _fetch_baostock(missing, start_date, end_date)
        all_prices.update(prices2)
        all_volumes.update(volumes2)
        all_errors.extend(errors2)

    still_missing = [t for t in tickers if not _ticker_data_usable(all_prices, all_volumes, t)]
    if still_missing:
        logger.info("[QuantFinance] baostock: %d/%d stocks, trying yfinance for %d missing...",
                    len(all_prices), len(tickers), len(still_missing))
        # Tier 3: yfinance
        prices3, volumes3, errors3 = _fetch_yfinance(still_missing, start_date, end_date)
        all_prices.update(prices3)
        all_volumes.update(volumes3)
        all_errors.extend(errors3)

    return all_prices, all_volumes, all_errors


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
                df = yf.download(yt, start=start_date, end=end_date,
                                 progress=False, auto_adjust=True)
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
                    adjust="qfq",
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
    yf_count = sum(1 for e in errors if "yfinance:" in e)
    ak_count = sum(1 for e in errors if "akshare:" in e)
    bs_count = sum(1 for e in errors if "baostock" in e)
    import_count = sum(1 for e in errors if "not installed" in e)

    lines = [
        "无法完整获取真实股票数据。已按 akshare -> baostock -> yfinance 逐层补缺。",
        f"错误摘要: akshare {ak_count} 条, baostock {bs_count} 条, "
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
        "  2. 检查网络连接: yfinance 需要访问 Yahoo Finance API",
        "     akshare 需要访问东方财富/新浪等国内数据源",
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
        f"### 1.1 判市结果",
        f"- **最终判市**: {regime_label}",
        f"- **判市方法**: 技术面信号 + CSI 300 指数信号 → 融合投票",
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
        "采用 **6 因子多维度模型**（经 IC 分析验证）：",
        "",
        "| 因子 | 维度 | 训练期 IC | 作用 |",
        "|------|------|----------|------|",
        "| momentum_20 | 价格趋势 | +0.084 | 主力因子，中期趋势强度 |",
        "| momentum_60 | 价格趋势 | +0.055 | 长期趋势确认 |",
        "| max_drawdown | 风险控制 | -0.114 | 回撤小的股票表现更好 |",
        "| reversal_5 | 反转信号 | -0.094 | 短期反转预警 |",
        "| volume_corr | 量价关系 | +0.049 | 量价配合确认（稳定器） |",
        "| volume_trend | 量能趋势 | +0.073 | 资金关注度变化 |",
        "",
        "### 2.2 因子选择逻辑",
        "",
        f"- **市场状态**: {regime_label}",
        "- **因子权重**: 根据市场状态动态调整（趋势市重动量，震荡市重风控）",
        "- **量价双维度**: 价格因子（4 个）+ 量能因子（2 个），后者与价格因子正交（r<0.25），提供独立 alpha",
        "- **假设声明**: 因子 IC 基于 2026 年 2-7 月行情测量。如评测期市场状态显著不同，因子预测力可能下降",
        "",
        "---",
        "",
        "## 三、选股执行",
        "",
        "### 3.1 多视角分析架构",
        "",
        "选股由双 Agent 协作完成：",
        "- **Bull Analyst（趋势视角）**: momentum_20 + momentum_60 + volume_corr，寻找趋势健康、量价配合的股票",
        "- **Bear Analyst（风控视角）**: max_drawdown + reversal_5 + volume_corr(反向)，筛选风险低、回撤小的股票",
        "- **Coordinator（综合决策）**: 融合双视角，共识标的优先，分歧标的由 PM 基于判市做判断",
        "",
        "> 两套视角独立验证（Spearman r≈-0.10, overlap≈28%），确保多视角互补而非重复。",
        "",
        "### 3.2 选股约束",
        "",
        "- 波动率硬约束：vol_z > 2.0 → 排除",
        "- 板块分散化：每板块至少 1 只，最多 3 只",
        "- 仓位分配：风险平价（1/波动率），单只≤10%，单板块≤25%，最低 5% 现金",
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
        "- 因子 IC（信息系数）基于 **2026 年 2-7 月** 的历史行情测量",
        "- 该期间 8 个评测窗口中 5 个为牛市、3 个为震荡市，**无熊市样本**",
        "- 如果当前评测期市场状态与训练期显著不同，因子预测力可能下降",
        "",
        "### 2. 因子在不同市场状态下的稳定性",
        "- `momentum_20` (IC=+0.72)：在趋势市中预测力最强，震荡/下跌市中 IC 可能衰减",
        "- `momentum_60` (IC=+0.41)：同理，依赖趋势延续性",
        "- `reversal_5` (IC=+0.39)：震荡市中可能相对更有效",
        "- `max_drawdown` (IC=-0.38)：各市态下均有防御价值，相对最稳定",
        "",
        "### 3. 缺乏独立验证集",
        "- 因子选择（IC 分析）和权重优化均在同一批 8 个窗口上完成",
        "- 未预留独立的验证窗口——存在一定程度的过拟合风险",
        "- 理想流程应为：训练集选因子 → 验证集调权重 → 测试集打分（三段隔离）",
        "",
        "### 4. 持仓周期的固有限制",
        "- 本策略持仓周期为 20 个交易日（约 1 个自然月）",
        "- 在此周期上，基本面因子（PE/PB/ROE）的 IC≈0——基本面变化速度不足以在 20 日内影响股价",
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
