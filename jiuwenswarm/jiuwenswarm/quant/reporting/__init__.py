"""Quant reporting: structured facts → deterministic reports → submission package.

R0: submission_contract — frozen official contest rules
R1: models, company_report, quality_gate, package_builder — evidence → reports
R2: report_service — shared service for pipeline + Extension paths
R3: symphony_adapter — Symphony plan generation + policy validation
R4: providers — data source abstraction (base + registry)
R5: resource_meter — real resource measurement (no estimation)
R6: submission runner (see evaluation/)
"""

from jiuwenswarm.quant.reporting.agent_view_parser import parse_agent_view
from jiuwenswarm.quant.reporting.announcement_service import (
    AnnouncementService,
    AnnouncementUniverseHealthError,
    ServiceResult,
    run_announcement_service,
)
from jiuwenswarm.quant.reporting.company_report import generate_company_report
from jiuwenswarm.quant.reporting.candidate_binding import (
    verify_candidate_binding,
    write_candidate_binding,
)
from jiuwenswarm.quant.reporting.models import (
    AgentView,
    CompanyFactBundle,
    EvidenceRef,
    MetricFact,
    PortfolioSnapshot,
    ReportQualityResult,
)
from jiuwenswarm.quant.reporting.package_builder import build_candidate_package
from jiuwenswarm.quant.reporting.quality_gate import validate_submission
from jiuwenswarm.quant.reporting.report_grade import (
    GradeResult,
    ReportGrade,
    grade_bundle,
    grade_submission,
)
from jiuwenswarm.quant.reporting.report_service import ReportService
from jiuwenswarm.quant.reporting.resource_meter import (
    ResourceMeter,
    ResourceReport,
    StageMetrics,
    new_resource_report,
)
from jiuwenswarm.quant.reporting.snapshot_writer import (
    MarketDataSnapshotArtifacts,
    SnapshotArtifacts,
    install_market_data_snapshot_in_candidate,
    install_snapshot_in_candidate,
    load_market_data_snapshot,
    load_snapshot_artifacts,
    verify_market_data_snapshot,
    verify_snapshot_artifacts,
    write_data_snapshot,
    write_market_data_snapshot,
)
from jiuwenswarm.quant.reporting.submission_contract import (
    SubmissionContract,
    get_contract,
)
from jiuwenswarm.quant.reporting.symphony_adapter import (
    PlanStep,
    PlanValidationResult,
    SymphonyExecutionTrace,
    SymphonyPlan,
    SymphonyPlanRequest,
    build_static_quant_plan,
    validate_quant_plan,
)

__all__ = [
    "AgentView",
    "AnnouncementService",
    "AnnouncementUniverseHealthError",
    "CompanyFactBundle",
    "EvidenceRef",
    "GradeResult",
    "MarketDataSnapshotArtifacts",
    "MetricFact",
    "PlanStep",
    "PlanValidationResult",
    "PortfolioSnapshot",
    "ReportGrade",
    "ReportQualityResult",
    "ReportService",
    "ResourceMeter",
    "ResourceReport",
    "ServiceResult",
    "SnapshotArtifacts",
    "StageMetrics",
    "SubmissionContract",
    "SymphonyExecutionTrace",
    "SymphonyPlan",
    "SymphonyPlanRequest",
    "build_candidate_package",
    "build_static_quant_plan",
    "generate_company_report",
    "get_contract",
    "grade_bundle",
    "grade_submission",
    "install_market_data_snapshot_in_candidate",
    "install_snapshot_in_candidate",
    "load_market_data_snapshot",
    "load_snapshot_artifacts",
    "new_resource_report",
    "parse_agent_view",
    "run_announcement_service",
    "validate_quant_plan",
    "validate_submission",
    "verify_candidate_binding",
    "verify_market_data_snapshot",
    "verify_snapshot_artifacts",
    "write_data_snapshot",
    "write_candidate_binding",
    "write_market_data_snapshot",
]
