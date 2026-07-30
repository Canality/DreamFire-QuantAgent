"""Quant reporting: structured facts → deterministic reports → submission package.

R0: submission_contract — frozen official contest rules
R1: models, company_report, quality_gate, package_builder — evidence → reports
R2: report_service — shared service for pipeline + Extension paths
R3: symphony_adapter — Symphony plan generation + policy validation
R4: providers — data source abstraction (base + registry)
R5: resource_meter — real resource measurement (no estimation)
R6: submission runner (see evaluation/)
"""

from jiuwenswarm.quant.reporting.submission_contract import SubmissionContract, get_contract
from jiuwenswarm.quant.reporting.models import (
    AgentView,
    CompanyFactBundle,
    EvidenceRef,
    MetricFact,
    PortfolioSnapshot,
    ReportQualityResult,
)
from jiuwenswarm.quant.reporting.company_report import generate_company_report
from jiuwenswarm.quant.reporting.quality_gate import validate_submission
from jiuwenswarm.quant.reporting.package_builder import build_candidate_package
from jiuwenswarm.quant.reporting.report_service import ReportService
from jiuwenswarm.quant.reporting.agent_view_parser import parse_agent_view, parse_bull_bear_pair
from jiuwenswarm.quant.reporting.resource_meter import (
    ResourceMeter,
    ResourceReport,
    StageMetrics,
    new_resource_report,
)
from jiuwenswarm.quant.reporting.snapshot_writer import (
    SnapshotArtifacts,
    install_snapshot_in_candidate,
    load_snapshot_artifacts,
    verify_snapshot_artifacts,
    write_data_snapshot,
)
from jiuwenswarm.quant.reporting.symphony_adapter import (
    PlanStep,
    PlanValidationResult,
    SymphonyPlan,
    SymphonyPlanRequest,
    SymphonyExecutionTrace,
    build_static_quant_plan,
    validate_quant_plan,
)

__all__ = [
    # R0
    "SubmissionContract",
    "get_contract",
    # R1
    "EvidenceRef",
    "MetricFact",
    "CompanyFactBundle",
    "PortfolioSnapshot",
    "AgentView",
    "ReportQualityResult",
    "generate_company_report",
    "validate_submission",
    "build_candidate_package",
    # R2
    "ReportService",
    "parse_agent_view",
    "parse_bull_bear_pair",
    # R3
    "PlanStep",
    "PlanValidationResult",
    "SymphonyPlan",
    "SymphonyPlanRequest",
    "SymphonyExecutionTrace",
    "build_static_quant_plan",
    "validate_quant_plan",
    # R5
    "ResourceMeter",
    "ResourceReport",
    "StageMetrics",
    "new_resource_report",
    "SnapshotArtifacts",
    "write_data_snapshot",
    "load_snapshot_artifacts",
    "verify_snapshot_artifacts",
    "install_snapshot_in_candidate",
]
