"""Build the submission candidate package from structured facts."""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Mapping, Tuple

from jiuwenswarm.quant.reporting.company_report import generate_company_report
from jiuwenswarm.quant.reporting.models import (
    CompanyFactBundle,
    EvidenceRef,
    PortfolioSnapshot,
    ReportQualityResult,
)
from jiuwenswarm.quant.reporting.quality_gate import validate_submission
from jiuwenswarm.quant.reporting.providers.archive import EvidenceArchive
from jiuwenswarm.quant.reporting.submission_contract import SubmissionContract


_MANAGED_PACKAGE_FILES = (
    "Portfolio.json",
    "portfolio_report.md",
    "evidence_manifest.json",
    "portfolio_meta.json",
    "report_manifest.json",
    # Optional files written by the direct path after the shared package.
    # Removing them here prevents a later formal run from inheriting stale
    # direct-run evidence.
    "rails_result.json",
    "resource_usage.json",
    "resource_usage.md",
    "reproducibility.md",
    "framework_changes.md",
)
_MANAGED_PACKAGE_DIRS = ("company_reports", "data_snapshot", "evidence_archive")


def _clear_previous_candidate(package_path: str) -> None:
    """Remove only files owned by the candidate-package workflow."""
    for filename in _MANAGED_PACKAGE_FILES:
        path = os.path.join(package_path, filename)
        if os.path.isfile(path):
            os.remove(path)
    for dirname in _MANAGED_PACKAGE_DIRS:
        managed_dir = os.path.join(package_path, dirname)
        if os.path.isdir(managed_dir):
            shutil.rmtree(managed_dir)


def _collect_evidence_refs(
    bundles: Mapping[str, CompanyFactBundle],
) -> Dict[str, EvidenceRef]:
    """Collect all EvidenceRef objects from all bundles, keyed by evidence_id."""
    refs: Dict[str, EvidenceRef] = {}
    for bundle in bundles.values():
        for fact in (bundle.technical_facts + bundle.fundamental_facts +
                     bundle.event_facts + bundle.risk_facts):
            for eid in fact.evidence_ids:
                if eid and eid not in refs:
                    # Facts only carry IDs; EvidenceRef instances are provided
                    # externally. For the builder, we create placeholder refs
                    # for IDs seen in facts. Real refs should come from providers.
                    pass
    return refs


def _build_portfolio_report_md(
    portfolio: PortfolioSnapshot,
    bundles: Mapping[str, CompanyFactBundle],
    contract: SubmissionContract,
    quality: ReportQualityResult,
) -> str:
    """Generate the portfolio-level summary report covering ALL 49 companies."""
    lines = [
        "# 投资组合报告",
        "",
        f"**策略**: {portfolio.strategy_id}",
        f"**分析时点**: {portfolio.as_of_time.strftime('%Y-%m-%d')}",
        f"**合同公司总数**: {contract.n_companies}",
        f"**入选股票数**: {portfolio.n_selected}",
        f"**覆盖板块数**: {portfolio.n_sectors_represented}",
        f"**总仓位**: {portfolio.total_equity * 100:.2f}%",
        f"**现金**: {portfolio.cash * 100:.2f}%",
        "",
        "---",
        "",
        "## 持仓明细",
        "",
        "| 代码 | 名称 | 板块 | 权重 |",
        "|------|------|------|------|",
    ]

    sorted_holdings = sorted(portfolio.holdings.items(), key=lambda x: -x[1])
    for ticker, weight in sorted_holdings:
        if weight <= 0:
            continue
        bundle = bundles.get(ticker)
        name = bundle.name if bundle else ticker
        sector = bundle.sector if bundle else "未知"
        report_code = ticker.split(".")[0]
        lines.append(f"| {report_code} | {name} | {sector} | {weight * 100:.2f}% |")

    lines.extend([
        "",
        "---",
        "",
        "## 零持仓公司",
        "",
        "| 代码 | 名称 | 板块 | 原因 |",
        "|------|------|------|------|",
    ])

    # Show ALL 49 companies, not just those in holdings
    for ticker in contract.company_codes:
        weight = portfolio.holdings.get(ticker, 0.0)
        if weight > 0:
            continue  # already shown above
        bundle = bundles.get(ticker)
        name = bundle.name if bundle else contract.company_names.get(ticker, ticker)
        sector = bundle.sector if bundle else contract.sectors.get(ticker, "未知")
        reason = bundle.weight_zero_reason if bundle else "未在 bundles 中"
        report_code = ticker.split(".")[0]
        lines.append(f"| {report_code} | {name} | {sector} | {reason} |")

    lines.extend([
        "",
        "---",
        "",
        "## 质量检查结果",
        "",
        f"- **通过**: {'是' if quality.passed else '否'}",
    ])
    if quality.blockers:
        lines.append("- **阻断项**:")
        for b in quality.blockers:
            lines.append(f"  - {b}")
    if quality.warnings:
        lines.append("- **警告**:")
        for w in quality.warnings:
            lines.append(f"  - {w}")

    return "\n".join(lines) + "\n"


def build_candidate_package(
    contract: SubmissionContract,
    portfolio: PortfolioSnapshot,
    bundles: Mapping[str, CompanyFactBundle],
    output_dir: str,
    strategy_label: str = "production",
    *,
    evidence_manifest: Mapping[str, EvidenceRef] | None = None,
    evidence_archive: EvidenceArchive | None = None,
) -> Tuple[bool, ReportQualityResult, str]:
    """Generate a complete candidate submission package.

    Writes to output_dir/submission_candidate/ — never overwrites output/submission/.

    evidence_manifest: evidence_id → EvidenceRef mapping. If None, evidence
    consistency checks are limited (with warnings).

    Returns (package_ok, quality_result, package_path).
    """
    package_path = os.path.join(output_dir, "submission_candidate")
    os.makedirs(package_path, exist_ok=True)
    _clear_previous_candidate(package_path)

    company_reports_dir = os.path.join(package_path, "company_reports")
    os.makedirs(company_reports_dir, exist_ok=True)

    generated_at = datetime.now(timezone.utc)
    report_codes_on_disk: set[str] = set()

    # ---- Evidence manifest (full EvidenceRef serialization) ----
    ev_refs = dict(evidence_manifest) if evidence_manifest else {}
    ev_manifest_json = {
        "generated_at": generated_at.isoformat(),
        "contract_hash": contract.config_hash(),
        "evidence_count": len(ev_refs),
        "evidence_ids": sorted(ev_refs.keys()),
        "sources": sorted(set(ref.source_name for ref in ev_refs.values() if ref.source_name)),
        "evidence_refs": {
            eid: {
                "evidence_id": ref.evidence_id,
                "source_type": ref.source_type,
                "source_name": ref.source_name,
                "source_url": ref.source_url,
                "period_end": ref.period_end.isoformat() if ref.period_end else None,
                "published_at": ref.published_at.isoformat() if ref.published_at else None,
                "available_at": ref.available_at.isoformat() if ref.available_at else None,
                "retrieved_at": ref.retrieved_at.isoformat() if ref.retrieved_at else None,
                "content_sha256": ref.content_sha256,
            }
            for eid, ref in ev_refs.items()
        },
    }
    with open(os.path.join(package_path, "evidence_manifest.json"), "w", encoding="utf-8") as f:
        json.dump(ev_manifest_json, f, indent=2, ensure_ascii=False)

    # ---- Per-company reports ----
    for ticker, bundle in bundles.items():
        report_md = generate_company_report(bundle)
        report_path = os.path.join(company_reports_dir, f"{bundle.report_code}.md")
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report_md)
        report_codes_on_disk.add(bundle.report_code)

    # ---- Quality gate ----
    quality = validate_submission(
        contract=contract,
        portfolio=portfolio,
        bundles=bundles,
        report_codes_on_disk=report_codes_on_disk,
        generated_at=generated_at,
        evidence_manifest=ev_refs if ev_refs else None,
        archive=evidence_archive,
    )

    # Install every non-market evidence item in the candidate itself. External
    # source_url remains the human-verifiable publication URL; this local copy
    # is the immutable machine-verifiable payload.
    if evidence_archive is not None:
        candidate_archive = EvidenceArchive(Path(package_path) / "evidence_archive")
        for evidence_id, ref in ev_refs.items():
            if ref.source_type == "market_data":
                continue
            content = evidence_archive.read(evidence_id)
            if content is not None:
                candidate_archive.write(evidence_id, content, ref)

    # ---- Portfolio.json (official format: 6-digit code → weight) ----
    portfolio_official = {
        c.split(".")[0]: w
        for c, w in portfolio.holdings.items()
    }
    with open(os.path.join(package_path, "Portfolio.json"), "w", encoding="utf-8") as f:
        json.dump(portfolio_official, f, indent=2, ensure_ascii=False)

    # Metadata copy for traceability
    portfolio_meta = {
        "strategy": portfolio.strategy_id,
        "as_of_time": portfolio.as_of_time.isoformat(),
        "contract_hash": portfolio.contract_hash,
        "holdings": dict(portfolio.holdings),
        "cash": portfolio.cash,
        "n_selected": portfolio.n_selected,
        "n_sectors_represented": portfolio.n_sectors_represented,
        "generated_at": generated_at.isoformat(),
        "quality_passed": quality.passed,
    }
    with open(os.path.join(package_path, "portfolio_meta.json"), "w", encoding="utf-8") as f:
        json.dump(portfolio_meta, f, indent=2, ensure_ascii=False)

    # ---- Portfolio report (all 49 companies) ----
    portfolio_report_md = _build_portfolio_report_md(portfolio, bundles, contract, quality)
    with open(os.path.join(package_path, "portfolio_report.md"), "w", encoding="utf-8") as f:
        f.write(portfolio_report_md)

    # ---- Report manifest ----
    manifest = {
        "package_path": package_path,
        "generated_at": generated_at.isoformat(),
        "contract_hash": contract.config_hash(),
        "contract_source_verified": contract.source_verified,
        "quality_passed": quality.passed,
        "quality_blockers": list(quality.blockers),
        "quality_warnings": list(quality.warnings),
        "quality_metrics": dict(quality.metrics),
        "n_reports": len(report_codes_on_disk),
        "evidence_count": len(ev_refs),
        "portfolio_n_holdings": len(portfolio_official),
    }
    with open(os.path.join(package_path, "report_manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    return (quality.passed, quality, package_path)
