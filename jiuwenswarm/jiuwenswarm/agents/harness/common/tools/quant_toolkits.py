"""Agent-facing Quant Finance tools.

Exposes the QuantFinanceExtension RPC methods as model-callable tools.
Follows the SymphonyToolkit pattern exactly.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from typing import Any

from openjiuwen.core.foundation.tool import LocalFunction, Tool, ToolCard

from jiuwenswarm.extensions.registry import ExtensionRegistry

logger = logging.getLogger(__name__)


class QuantToolkit:
    """Expose QuantFinance extension RPC methods as model-callable tools."""

    async def _call_rpc(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        logger.info(
            "[QuantToolkit] calling RPC: method=%s params_keys=%s",
            method,
            sorted(params) if params else [],
        )
        try:
            registry = ExtensionRegistry.get_instance()
        except RuntimeError as exc:
            return {
                "success": False,
                "detail": f"QuantFinance extension RPC unavailable: {method}: {exc}",
            }

        handler = registry.get_rpc_handler(method)
        if handler is None:
            return {
                "success": False,
                "detail": f"QuantFinance extension RPC unavailable: {method}: handler not registered",
            }

        timeout_s = 300.0  # 5 minute timeout for data-heavy operations
        try:
            result = handler(params, request=None)
            payload = await asyncio.wait_for(
                result if inspect.isawaitable(result) else _return_value(result),
                timeout=timeout_s,
            )
        except asyncio.TimeoutError:
            return {"success": False, "detail": f"{method}: timeout after {timeout_s}s"}
        except Exception as exc:  # noqa: BLE001
            logger.exception("QuantFinance RPC failed: %s", method)
            return {"success": False, "detail": f"{method}: {exc}"}

        return payload if isinstance(payload, dict) else {"success": True, "result": payload}

    # -- Tool methods --

    async def fetch_data(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
        tickers: list[str] | None = None,
    ) -> dict[str, Any]:
        """Fetch A-share stock price/volume data for the competition pool."""
        params: dict[str, Any] = {}
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        if tickers:
            params["tickers"] = tickers
        return await self._call_rpc("quant.fetch_data", params)

    async def compute_factors(self) -> dict[str, Any]:
        """Compute 6-factor scores with market regime detection and sector-neutral Z-score."""
        return await self._call_rpc("quant.compute_factors", {})

    async def select_stocks(
        self,
        all_composite: dict[str, float] | None = None,
        top_n: int = 15,
        min_score: float = -0.5,
    ) -> dict[str, Any]:
        """Select top stocks with sector diversification (at least 1 per sector)."""
        params: dict[str, Any] = {
            "all_composite": all_composite or {},
            "top_n": 15 if top_n is None else top_n,
            "min_score": -0.5 if min_score is None else min_score,
        }
        return await self._call_rpc("quant.select_stocks", params)

    async def allocate_positions(
        self,
        tickers: list[str] | None = None,
    ) -> dict[str, Any]:
        """Allocate risk-parity portfolio weights with single-stock and sector caps."""
        params: dict[str, Any] = {}
        if tickers:
            params["tickers"] = tickers
        return await self._call_rpc("quant.allocate_positions", params)

    async def run_backtest(
        self,
        weights: dict[str, float] | None = None,
        initial_capital: float = 1_000_000.0,
    ) -> dict[str, Any]:
        """Run vectorized backtest; returns cumulative return, Sharpe, max drawdown, win rate."""
        params: dict[str, Any] = {
            "initial_capital": 1_000_000.0 if initial_capital is None else initial_capital,
        }
        if weights:
            params["weights"] = weights
        return await self._call_rpc("quant.run_backtest", params)

    async def generate_report(
        self,
        portfolio: list[dict[str, Any]] | None = None,
        backtest: dict[str, Any] | None = None,
        regime: str = "range",
        top_stocks: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Generate a structured Markdown quantitative investment report."""
        params: dict[str, Any] = {
            "portfolio": portfolio or [],
            "backtest": backtest or {},
            "regime": regime,
        }
        if top_stocks:
            params["top_stocks"] = top_stocks
        return await self._call_rpc("quant.generate_report", params)

    async def bull_view(self) -> dict[str, Any]:
        """Extract bullish signals from momentum and price-volume alignment."""
        return await self._call_rpc("quant.bull_view", {})

    async def bear_view(self) -> dict[str, Any]:
        """Extract bearish signals from drawdown, reversal, and price-volume divergence."""
        return await self._call_rpc("quant.bear_view", {})

    # -- get_tools --

    def get_tools(self, config: dict[str, Any] | None = None) -> list[Tool]:
        """Return the list of quant tools for agent registration."""
        del config

        def make_tool(
            name: str,
            description: str,
            input_params: dict[str, Any],
            func: Any,
        ) -> Tool:
            card = ToolCard(
                id=name,
                name=name,
                description=description,
                input_params=input_params,
            )
            return LocalFunction(card=card, func=func)

        return [
            make_tool(
                "quant_fetch_data",
                "Fetch A-share stock price and volume data for the competition stock pool "
                "(49 stocks across 6 sectors). Caches raw matrices server-side and returns only a compact summary.",
                {
                    "type": "object",
                    "properties": {
                        "start_date": {
                            "type": "string",
                            "description": "Start date in YYYY-MM-DD format. Defaults to 180 days ago.",
                        },
                        "end_date": {
                            "type": "string",
                            "description": "End date in YYYY-MM-DD format. Defaults to today.",
                        },
                        "tickers": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional list of ticker symbols to fetch. Defaults to all 49 stocks.",
                        },
                    },
                },
                self.fetch_data,
            ),
            make_tool(
                "quant_compute_factors",
                "Compute 6-factor scores (momentum_20/60, reversal_5, max_drawdown, "
                "volume_corr, volume_trend) with market regime detection "
                "(Bull/Bear/Range) and sector-neutral Z-score normalization. "
                "Returns top stocks and composite scores.",
                {"type": "object", "properties": {}},
                self.compute_factors,
            ),
            make_tool(
                "quant_select_stocks",
                "Select stocks from factor scores with sector diversification constraints "
                "(at least 1 per sector, capped at top_n). Returns selected tickers with scores.",
                {
                    "type": "object",
                    "properties": {
                        "all_composite": {
                            "type": "object",
                            "description": "Dict of ticker -> composite_score from quant_compute_factors.",
                        },
                        "top_n": {
                            "type": "integer",
                            "description": "Maximum number of stocks to select. Default: 15.",
                        },
                        "min_score": {
                            "type": "number",
                            "description": "Minimum composite score threshold. Default: -0.5.",
                        },
                    },
                    "required": ["all_composite"],
                },
                self.select_stocks,
            ),
            make_tool(
                "quant_allocate_positions",
                "Allocate portfolio weights using risk-parity (inverse volatility) with "
                "single-stock ≤10% and single-sector ≤25% caps. Returns portfolio with weights.",
                {
                    "type": "object",
                    "properties": {
                        "tickers": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of selected ticker symbols from quant_select_stocks.",
                        },
                    },
                    "required": ["tickers"],
                },
                self.allocate_positions,
            ),
            make_tool(
                "quant_run_backtest",
                "Run vectorized backtest on the portfolio. Returns cumulative return, "
                "annualized return, max drawdown, Sharpe ratio, annualized volatility, "
                "win rate, and final portfolio value.",
                {
                    "type": "object",
                    "properties": {
                        "weights": {
                            "type": "object",
                            "description": "Dict of ticker -> weight from quant_allocate_positions.",
                        },
                        "initial_capital": {
                            "type": "number",
                            "description": "Initial capital in CNY. Default: 1,000,000.",
                        },
                    },
                    "required": ["weights"],
                },
                self.run_backtest,
            ),
            make_tool(
                "quant_generate_report",
                "Generate a structured Markdown quantitative investment report from "
                "pipeline results. Includes backtest metrics, portfolio breakdown, "
                "and factor score rankings.",
                {
                    "type": "object",
                    "properties": {
                        "portfolio": {
                            "type": "array",
                            "items": {"type": "object"},
                            "description": "Portfolio list from quant_allocate_positions.",
                        },
                        "backtest": {
                            "type": "object",
                            "description": "Backtest metrics dict from quant_run_backtest.",
                        },
                        "regime": {
                            "type": "string",
                            "description": "Market regime from quant_compute_factors.",
                        },
                        "top_stocks": {
                            "type": "array",
                            "items": {"type": "object"},
                            "description": "Top stocks list from quant_compute_factors.",
                        },
                    },
                    "required": ["portfolio", "backtest"],
                },
                self.generate_report,
            ),
            make_tool(
                "quant_bull_view",
                "Extract bullish signals from factor data. Analyzes 20/60-day momentum "
                "and price-volume alignment to identify stocks with "
                "strong bullish characteristics. Returns scored list with specific signals "
                "and recommended position range. Use for Bull Analyst perspective.",
                {"type": "object", "properties": {}},
                self.bull_view,
            ),
            make_tool(
                "quant_bear_view",
                "Extract bearish/warning signals from factor data. Analyzes large drawdowns, "
                "short-term reversal, and price-volume divergence to identify risky "
                "stocks. Returns scored list with specific warnings and recommended cash "
                "reserve range. Use for Bear Analyst perspective.",
                {"type": "object", "properties": {}},
                self.bear_view,
            ),
        ]


async def _return_value(value: Any) -> Any:
    return value
