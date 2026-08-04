"""Shared report service: called by both run_quant_pipeline and Extension RPC.

Single entry point for report generation — ensures both paths produce
identical outputs from identical inputs.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, Mapping, Tuple

from jiuwenswarm.quant.reporting.models import (
    AgentView,
    CompanyFactBundle,
    EvidenceRef,
    MetricFact,
    PortfolioSnapshot,
    ReportQualityResult,
)
from jiuwenswarm.quant.reporting.company_report import generate_company_report
from jiuwenswarm.quant.reporting.package_builder import build_candidate_package
from jiuwenswarm.quant.reporting.providers.archive import EvidenceArchive
from jiuwenswarm.quant.reporting.submission_contract import (
    SubmissionContract,
    get_contract,
)


class ReportService:
    """Shared report generation service.

    Both run_quant_pipeline.py and the Extension's quant.generate_report RPC
    must use this service so that outputs are identical.
    """

    def __init__(self, contract: SubmissionContract | None = None):
        self._contract = contract or get_contract()

    @property
    def contract(self) -> SubmissionContract:
        return self._contract

    def build_company_bundle(
        self,
        ticker: str,
        name: str,
        sector: str,
        as_of_time: datetime,
        portfolio_weight: float,
        selected: bool,
        weight_zero_reason: str = "",
        *,
        technical_facts: Tuple[MetricFact, ...] = (),
        fundamental_facts: Tuple[MetricFact, ...] = (),
        event_facts: Tuple[MetricFact, ...] = (),
        risk_facts: Tuple[MetricFact, ...] = (),
        agent_views: Tuple[AgentView, ...] = (),
        data_provider_status: str = "partial",
    ) -> CompanyFactBundle:
        """Build a single company's fact bundle with contract-derived metadata."""
        return CompanyFactBundle(
            ticker=ticker,
            report_code=self._contract.ticker_to_report_code.get(ticker, ticker.split(".")[0]),
            name=name,
            sector=sector,
            as_of_time=as_of_time,
            portfolio_weight=portfolio_weight,
            selected=selected,
            weight_zero_reason=weight_zero_reason,
            technical_facts=technical_facts,
            fundamental_facts=fundamental_facts,
            event_facts=event_facts,
            risk_facts=risk_facts,
            agent_views=agent_views,
            data_provider_status=data_provider_status,
        )

    def build_portfolio_snapshot(
        self,
        as_of_time: datetime,
        holdings: Dict[str, float],
        cash: float,
        strategy_id: str,
    ) -> PortfolioSnapshot:
        """Build a portfolio snapshot with contract hash embedded."""
        return PortfolioSnapshot(
            as_of_time=as_of_time,
            holdings=holdings,
            cash=cash,
            total_equity=sum(holdings.values()),
            n_selected=len([w for w in holdings.values() if w > 0]),
            n_sectors_represented=len({
                self._contract.sectors.get(t, "未知") for t, w in holdings.items() if w > 0
            }),
            strategy_id=strategy_id,
            contract_hash=self._contract.config_hash(),
        )

    def generate_all_reports(
        self,
        bundles: Dict[str, CompanyFactBundle],
    ) -> Dict[str, str]:
        """Generate MD report text for all companies. Returns {report_code: markdown}."""
        return {b.report_code: generate_company_report(b) for b in bundles.values()}

    def build_package(
        self,
        portfolio: PortfolioSnapshot,
        bundles: Dict[str, CompanyFactBundle],
        output_dir: str,
        strategy_label: str = "production",
        evidence_manifest: Mapping[str, "EvidenceRef"] | None = None,
        evidence_archive: EvidenceArchive | None = None,
    ) -> Tuple[bool, ReportQualityResult, str]:
        """Build the complete submission candidate package."""
        return build_candidate_package(
            contract=self._contract,
            portfolio=portfolio,
            bundles=bundles,
            output_dir=output_dir,
            strategy_label=strategy_label,
            evidence_manifest=evidence_manifest,
            evidence_archive=evidence_archive,
        )
