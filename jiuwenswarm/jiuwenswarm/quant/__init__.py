"""Quantitative finance package for JiuwenSwarm."""

from jiuwenswarm.quant.stock_pool import STOCK_POOL, ALL_STOCKS, SECTOR_MAP, TICKER_NAME_MAP
from jiuwenswarm.quant.market_regime import MarketRegime
from jiuwenswarm.quant.market_index import MarketIndex
from jiuwenswarm.quant.regime_fusion import RegimeFusion
from jiuwenswarm.quant.fundamental import FundamentalData
from jiuwenswarm.quant.factors import (
    FactorConfig,
    PositionConfig,
    StrategyResult,
    FactorCalculator,
    PositionSizer,
)
from jiuwenswarm.quant.backtest_engine import BacktestEngine, BacktestResult
from jiuwenswarm.quant.team_config import (
    COORDINATOR_PERSONA,
    ALPHA_ANALYST_PERSONA,
    RISK_EVIDENCE_ANALYST_PERSONA,
    QUANT_TEAM_PREDEFINED_MEMBERS,
    load_persona,
)
from jiuwenswarm.quant.agent_decision import (
    AgentProposal,
    DecisionTrace,
    DecisionAssembler,
)

__all__ = [
    "STOCK_POOL",
    "ALL_STOCKS",
    "SECTOR_MAP",
    "TICKER_NAME_MAP",
    "MarketRegime",
    "MarketIndex",
    "RegimeFusion",
    "FundamentalData",
    "FactorConfig",
    "PositionConfig",
    "StrategyResult",
    "FactorCalculator",
    "PositionSizer",
    "BacktestEngine",
    "BacktestResult",
    "AgentProposal",
    "DecisionTrace",
    "DecisionAssembler",
    "COORDINATOR_PERSONA",
    "ALPHA_ANALYST_PERSONA",
    "RISK_EVIDENCE_ANALYST_PERSONA",
    "QUANT_TEAM_PREDEFINED_MEMBERS",
    "load_persona",
]
