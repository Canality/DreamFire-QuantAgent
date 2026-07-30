"""Unit tests for symphony_adapter — Phase R3."""


from jiuwenswarm.quant.reporting.symphony_adapter import (
    PlanStep,
    SymphonyPlan,
    build_static_quant_plan,
    validate_quant_plan,
)


def test_static_plan_has_all_required_skills():
    plan = build_static_quant_plan()
    skill_names = {s.skill_name for s in plan.steps}
    required = {"fetch_data", "compute_factors", "bull_view", "bear_view",
                "select_stocks", "allocate_positions", "run_backtest", "generate_report"}
    assert required.issubset(skill_names), f"Missing: {required - skill_names}"


def test_static_plan_is_source_fallback():
    plan = build_static_quant_plan()
    assert plan.source == "static_fallback"


def test_validate_static_plan_passes():
    plan = build_static_quant_plan()
    result = validate_quant_plan(plan)
    assert result.valid, f"Static plan should be valid, got blockers: {result.blockers}"


def test_validate_plan_missing_skill_blocked():
    """Plan missing a required skill must fail validation."""
    plan = SymphonyPlan(
        plan_id="test-1",
        query="test",
        generated_at=None,
        steps=[
            PlanStep(step_id="1", skill_name="fetch_data", description="Fetch"),
            PlanStep(step_id="2", skill_name="generate_report", description="Report"),
        ],
        source="test",
    )
    result = validate_quant_plan(plan)
    assert not result.valid
    assert len(result.missing_required_skills) > 0


def test_validate_plan_ordering_violation_blocked():
    """Report before fetch must be caught."""
    plan = SymphonyPlan(
        plan_id="test-2",
        query="test",
        generated_at=None,
        steps=[
            PlanStep(step_id="1", skill_name="generate_report", description="Report first"),
            PlanStep(step_id="2", skill_name="fetch_data", description="Fetch second"),
        ],
        source="test",
    )
    result = validate_quant_plan(plan)
    # Ordering violation: fetch (step 2) should come before generate_report (step 1)
    assert len(result.ordering_violations) > 0


def test_plan_step_dependencies():
    step = PlanStep(
        step_id="3",
        skill_name="bull_view",
        description="Bull analysis",
        depends_on=["2"],
        expected_outputs=["bull_recommendations"],
    )
    assert step.step_id == "3"
    assert "2" in step.depends_on
