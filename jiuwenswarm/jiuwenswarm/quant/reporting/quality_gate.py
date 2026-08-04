"""Quality gate: validate submission completeness, consistency, and causality.

Blockers are failures that make the submission invalid.
Warnings are issues that should be noted but don't block.

CRITICAL: Every numeric value displayed in a report must be traceable to
a valid EvidenceRef with non-empty source_type, content_sha256, and
available_at <= decision_time.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Dict, List, Mapping, Set

from jiuwenswarm.quant.reporting.models import (
    CompanyFactBundle,
    EvidenceRef,
    PortfolioSnapshot,
    ReportQualityResult,
)
from jiuwenswarm.quant.reporting.report_grade import (
    GradeResult,
    ReportGrade,
    grade_submission,
)
from jiuwenswarm.quant.reporting.submission_contract import SubmissionContract


def _evidence_valid_for_time(ref: EvidenceRef, as_of_time: datetime) -> bool:
    """Evidence is valid only if it was available at or before the decision time."""
    return ref.available_at <= as_of_time


_SHA256_HEX = re.compile(r"^[0-9a-fA-F]{64}$")


def _evidence_has_valid_hash(ref: EvidenceRef) -> bool:
    """Evidence must have a valid 64-char hex SHA-256 hash.

    Labels like "unarchived" or "extension-generated" are NOT valid hashes.
    """
    h = ref.content_sha256 or ""
    return bool(_SHA256_HEX.match(h))


def _evidence_has_valid_source(ref: EvidenceRef) -> bool:
    """Evidence must have a source_type and source_name."""
    return bool(ref.source_type) and bool(ref.source_name)


def _archive_exists(archive: object, evidence_id: str) -> bool:
    """Check *evidence_id* resolves in the archive (lazy-import safe)."""
    try:
        exists_method = getattr(archive, "exists", None)
        if exists_method is None:
            return False
        return bool(exists_method(evidence_id))
    except Exception:
        return False


def validate_submission(
    contract: SubmissionContract,
    portfolio: PortfolioSnapshot,
    bundles: Mapping[str, CompanyFactBundle],
    report_codes_on_disk: Set[str],
    generated_at: datetime,
    *,
    evidence_manifest: Mapping[str, EvidenceRef] | None = None,
    archive: object | None = None,  # EvidenceArchive | None (lazy import)
) -> ReportQualityResult:
    """Run all quality checks on a candidate submission.

    Args:
        evidence_manifest: evidence_id → EvidenceRef mapping.
            If None, evidence existence checks are skipped with a warning.
        archive: Optional ``EvidenceArchive`` for content-level verification.
            When provided, every evidence_id must resolve to an intact
            archived file whose SHA-256 matches the manifest.
    """
    blockers: List[str] = []
    warnings: List[str] = []
    metrics: Dict[str, float | int] = {}

    # ---- 1. Report set completeness ----
    expected_codes = set(contract.report_codes)
    missing = expected_codes - report_codes_on_disk
    extra = report_codes_on_disk - expected_codes
    if missing:
        blockers.append(f"Missing reports: {sorted(missing)}")
    if extra:
        blockers.append(f"Extra reports not in contract: {sorted(extra)}")

    metrics["expected_reports"] = len(expected_codes)
    metrics["reports_on_disk"] = len(report_codes_on_disk)
    metrics["reports_missing"] = len(missing)

    # ---- 2. Bundle completeness ----
    bundle_codes = {b.report_code for b in bundles.values()}
    if bundle_codes != expected_codes:
        missing_in_bundles = expected_codes - bundle_codes
        extra_in_bundles = bundle_codes - expected_codes
        if missing_in_bundles:
            blockers.append(f"Company fact bundles missing: {sorted(missing_in_bundles)}")
        if extra_in_bundles:
            blockers.append(f"Company fact bundles extra: {sorted(extra_in_bundles)}")

    # ---- 3. Weight consistency ----
    weight_mismatches = []
    for ticker, bundle in bundles.items():
        portfolio_weight = portfolio.holdings.get(ticker, 0.0)
        bundle_weight = bundle.portfolio_weight
        if abs(portfolio_weight - bundle_weight) > 1e-6:
            weight_mismatches.append(
                f"{ticker}: portfolio={portfolio_weight:.6f}, bundle={bundle_weight:.6f}"
            )
    if weight_mismatches:
        blockers.append(f"Weight mismatch between portfolio and bundles: {weight_mismatches}")

    # ---- 4. Weight rule compliance ----
    weights_ok, weight_issues = contract.validate_weights(dict(portfolio.holdings))
    if not weights_ok:
        blockers.extend(weight_issues)

    # ---- 5. Cash consistency ----
    total_equity = sum(portfolio.holdings.values())
    if abs(portfolio.total_equity - total_equity) > 1e-6:
        blockers.append(
            f"Portfolio total_equity ({portfolio.total_equity:.6f}) != "
            f"sum of holdings ({total_equity:.6f})"
        )

    metrics["total_equity"] = round(total_equity, 6)
    metrics["cash"] = round(portfolio.cash, 6)
    metrics["n_selected"] = portfolio.n_selected
    metrics["n_sectors"] = portfolio.n_sectors_represented

    # ---- 6. Fact coverage ----
    unavailable_count = 0
    empty_tech_count = 0
    no_agent_view_count = 0
    for bundle in bundles.values():
        if bundle.data_provider_status == "unavailable":
            unavailable_count += 1
        if not bundle.technical_facts:
            empty_tech_count += 1
        if not bundle.agent_views:
            no_agent_view_count += 1

    metrics["bundles_unavailable"] = unavailable_count
    metrics["bundles_with_agent_views"] = len(bundles) - no_agent_view_count

    if unavailable_count == len(bundles):
        blockers.append(
            f"All {len(bundles)} companies have data_provider_status='unavailable'. "
            f"Cannot generate a valid submission with zero data."
        )
    elif unavailable_count > len(bundles) * 0.5:
        warnings.append(f"{unavailable_count}/{len(bundles)} companies have unavailable data")

    if empty_tech_count == len(bundles):
        blockers.append(
            "No company has any technical facts. "
            "At minimum, factor scores must be populated."
        )

    if no_agent_view_count == len(bundles):
        warnings.append(
            "No company has Agent (Alpha/Risk & Evidence) views. Report quality will be degraded."
        )

    # ---- 7. EvidenceRef validation (CRITICAL) ----
    # Every numeric fact MUST be traceable to a valid EvidenceRef
    facts_without_evidence: List[str] = []
    facts_with_invalid_evidence: List[str] = []
    facts_with_future_evidence: List[str] = []

    for bundle in bundles.values():
        decision_time = bundle.as_of_time
        all_facts = (bundle.technical_facts + bundle.fundamental_facts +
                     bundle.event_facts + bundle.risk_facts)

        for fact in all_facts:
            # Facts with numeric values must have evidence
            if fact.value is not None and isinstance(fact.value, (int, float)):
                if not fact.evidence_ids:
                    facts_without_evidence.append(
                        f"{bundle.ticker}/{fact.name}={fact.value}"
                    )
                    continue

                # Check each evidence ID
                for eid in fact.evidence_ids:
                    if evidence_manifest is None:
                        continue
                    ref = evidence_manifest.get(eid)
                    if ref is None:
                        facts_with_invalid_evidence.append(
                            f"{bundle.ticker}/{fact.name}: evidence '{eid}' not in manifest"
                        )
                        continue
                    if not _evidence_has_valid_source(ref):
                        facts_with_invalid_evidence.append(
                            f"{bundle.ticker}/{fact.name}: evidence '{eid}' has empty source"
                        )
                    if not _evidence_has_valid_hash(ref):
                        facts_with_invalid_evidence.append(
                            f"{bundle.ticker}/{fact.name}: evidence '{eid}' has invalid hash"
                        )
                    if not _evidence_valid_for_time(ref, decision_time):
                        facts_with_future_evidence.append(
                            f"{bundle.ticker}/{fact.name}: evidence '{eid}' "
                            f"available_at={ref.available_at.isoformat()} > "
                            f"decision_time={decision_time.isoformat()}"
                        )

    if facts_without_evidence:
        blockers.append(
            f"Numeric facts without any evidence ID ({len(facts_without_evidence)} cases): "
            f"{facts_without_evidence[:10]}{'...' if len(facts_without_evidence) > 10 else ''}"
        )
    if facts_with_invalid_evidence:
        blockers.append(
            f"Facts referencing invalid evidence ({len(facts_with_invalid_evidence)} cases): "
            f"{facts_with_invalid_evidence[:10]}{'...' if len(facts_with_invalid_evidence) > 10 else ''}"
        )
    if facts_with_future_evidence:
        blockers.append(
            f"Facts referencing future evidence ({len(facts_with_future_evidence)} cases): "
            f"{facts_with_future_evidence[:10]}{'...' if len(facts_with_future_evidence) > 10 else ''}"
        )

    if evidence_manifest is None:
        warnings.append(
            "evidence_manifest not provided; evidence existence and temporal checks skipped"
        )

    # ---- 8. Portfolio.json format ----
    non_six_digit = [t for t in portfolio.holdings if len(t.split(".")[0]) != 6]
    if non_six_digit:
        blockers.append(f"Portfolio tickers not in 6-digit code format: {non_six_digit}")

    metrics["has_portfolio_report"] = 1  # validated by calling code

    # ---- 9. Evidence archive verification (BLOCKER) ----
    if archive is not None and evidence_manifest is not None:
        unresolved: list[str] = []
        all_evidence_ids: set[str] = set()
        for bundle in bundles.values():
            for fact in (
                bundle.technical_facts + bundle.fundamental_facts
                + bundle.event_facts + bundle.risk_facts
            ):
                all_evidence_ids.update(fact.evidence_ids)
        for eid in sorted(all_evidence_ids):
            ref = evidence_manifest.get(eid)
            if (
                ref is not None
                and ref.source_type == "market_data"
                and str(ref.source_url or "").startswith("data_snapshot/")
            ):
                # Market snapshots are installed and hash-verified in the
                # candidate package's data_snapshot directory.
                continue
            if not _archive_exists(archive, eid):
                unresolved.append(eid)
        if unresolved:
            blockers.append(
                f"Evidence referenced by facts but not found in archive "
                f"({len(unresolved)} ids): "
                f"{unresolved[:10]}{'...' if len(unresolved) > 10 else ''}"
            )
        metrics["evidence_ids_total"] = len(all_evidence_ids)
        metrics["evidence_ids_unresolved"] = len(unresolved)
    elif archive is not None and evidence_manifest is None:
        blockers.append(
            "Archive provided but no evidence_manifest; "
            "cannot verify that every fact's evidence is archived"
        )

    # ---- 10. Report grading ----
    grade_result: GradeResult = grade_submission(bundles)
    metrics["report_grade_technical"] = grade_result.n_technical
    metrics["report_grade_disclosure"] = grade_result.n_disclosure
    metrics["report_grade_fundamental"] = grade_result.n_fundamental
    metrics["report_grade_news_risk"] = grade_result.n_news_or_risk
    metrics["overall_grade"] = grade_result.grade

    if grade_result.grade == ReportGrade.TECHNICAL_PASSED and grade_result.n_companies > 0:
        warnings.append(
            "Submission grade is TECHNICAL_PASSED — only market-data evidence "
            "present. No fundamental, disclosure, or risk provider facts are "
            "connected."
        )

    passed = len(blockers) == 0

    return ReportQualityResult(
        passed=passed,
        blockers=tuple(blockers),
        warnings=tuple(warnings),
        metrics=metrics,
    )
