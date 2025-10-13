import json
from typing import Callable

import pytest
from agents.tool_context import ToolContext
from agents.tool_guardrails import ToolInputGuardrailData, ToolOutputGuardrailData

from app.agents.guardrails import (
    eligibility_compliance_guardrail,
    intake_required_guardrail,
    planning_required_guardrail,
)
from app.agents.tools.mortgage_eligibility_tool import evaluate_mortgage_eligibility
from app.domain.schemas import IntakeSubmission
from app.models.context import ChatRunContext
from app.services import session_manager
from app.services.mortgage_eligibility import (
    MortgageEligibilityEvaluator,
    PropertyType,
    RiskProfile,
)
from app.services.planning_mapper import build_planning_context

from .factories import build_submission

NO_INTAKE_SNIPPET = "לא ניתן להריץ בדיקת זכאות"
NO_PLANNING_SNIPPET = "compute_planning_context"
VIOLATION_SNIPPET = "בדיקת הזכאות הופסקה"


def create_tool_context(session_id: str, arguments: str) -> ToolContext[ChatRunContext]:
    return ToolContext(
        context=ChatRunContext(session_id=session_id),
        tool_name=evaluate_mortgage_eligibility.name,
        tool_call_id="eligibility-tool-call",
        tool_arguments=arguments,
    )


@pytest.fixture
def cleanup_sessions() -> Callable[[str], None]:
    created: list[str] = []

    def _register(session_id: str) -> None:
        created.append(session_id)

    yield _register

    for session_id in created:
        session_manager._session_cache.pop(session_id, None)  # type: ignore[attr-defined]


def test_input_guardrail_blocks_when_no_intake(cleanup_sessions: Callable[[str], None]) -> None:
    session_id = "guardrail-no-intake"
    cleanup_sessions(session_id)
    session_manager._session_cache.pop(session_id, None)  # type: ignore[attr-defined]
    session_manager.get_or_create_session(session_id)

    arguments = json.dumps(
        {
            "monthly_net_income": 18_000,
            "property_price": 1_800_000,
            "down_payment_available": 500_000,
        }
    )
    tool_ctx = create_tool_context(session_id, arguments)

    guard_output = intake_required_guardrail.guardrail_function(
        ToolInputGuardrailData(context=tool_ctx, agent=None)
    )

    assert guard_output.behavior["type"] == "reject_content"
    assert NO_INTAKE_SNIPPET in guard_output.behavior["message"]


def test_input_guardrail_allows_with_confirmed_intake(cleanup_sessions: Callable[[str], None]) -> None:
    session_id = "guardrail-valid-intake"
    cleanup_sessions(session_id)
    session_manager._session_cache.pop(session_id, None)  # type: ignore[attr-defined]
    _, session = session_manager.get_or_create_session(session_id)
    session.save_intake_submission(build_submission())

    arguments = json.dumps(
        {
            "monthly_net_income": 20_000,
            "property_price": 1_100_000,
            "down_payment_available": 400_000,
            "loan_years": 25,
            "existing_monthly_loans": 0,
            "property_type": PropertyType.FIRST_HOME.value,
            "risk_profile": RiskProfile.STANDARD.value,
        }
    )
    tool_ctx = create_tool_context(session_id, arguments)

    guard_output = intake_required_guardrail.guardrail_function(
        ToolInputGuardrailData(context=tool_ctx, agent=None)
    )

    assert guard_output.behavior["type"] == "allow"


def test_planning_guardrail_blocks_without_context(cleanup_sessions: Callable[[str], None]) -> None:
    session_id = "guardrail-no-planning"
    cleanup_sessions(session_id)
    session_manager._session_cache.pop(session_id, None)  # type: ignore[attr-defined]
    _, session = session_manager.get_or_create_session(session_id)
    session.save_intake_submission(build_submission())

    tool_ctx = create_tool_context(session_id, "{}")

    guard_output = planning_required_guardrail.guardrail_function(
        ToolInputGuardrailData(context=tool_ctx, agent=None)
    )

    assert guard_output.behavior["type"] == "reject_content"
    assert NO_PLANNING_SNIPPET in guard_output.behavior["message"]


def test_planning_guardrail_allows_with_context(cleanup_sessions: Callable[[str], None]) -> None:
    session_id = "guardrail-with-planning"
    cleanup_sessions(session_id)
    session_manager._session_cache.pop(session_id, None)  # type: ignore[attr-defined]
    _, session = session_manager.get_or_create_session(session_id)
    submission = build_submission()
    session.save_intake_submission(submission)
    session.set_planning_context(build_planning_context(submission))

    tool_ctx = create_tool_context(session_id, "{}")

    guard_output = planning_required_guardrail.guardrail_function(
        ToolInputGuardrailData(context=tool_ctx, agent=None)
    )

    assert guard_output.behavior["type"] == "allow"


def test_output_guardrail_rejects_on_violation(cleanup_sessions: Callable[[str], None]) -> None:
    session_id = "guardrail-violation"
    cleanup_sessions(session_id)
    session_manager._session_cache.pop(session_id, None)  # type: ignore[attr-defined]
    _, session = session_manager.get_or_create_session(session_id)
    submission = build_submission()
    session.save_intake_submission(submission)
    session.set_planning_context(build_planning_context(submission))

    arguments = json.dumps(
        {
            "monthly_net_income": 8_000,
            "property_price": 2_200_000,
            "down_payment_available": 200_000,
            "loan_years": 32,
            "existing_monthly_loans": 0,
            "property_type": PropertyType.FIRST_HOME.value,
            "risk_profile": RiskProfile.STANDARD.value,
        }
    )
    tool_ctx = create_tool_context(session_id, arguments)

    allow_output = intake_required_guardrail.guardrail_function(
        ToolInputGuardrailData(context=tool_ctx, agent=None)
    )
    assert allow_output.behavior["type"] == "allow"

    planning_output = planning_required_guardrail.guardrail_function(
        ToolInputGuardrailData(context=tool_ctx, agent=None)
    )
    assert planning_output.behavior["type"] == "allow"

    calc = MortgageEligibilityEvaluator.evaluate(
        monthly_net_income=8_000,
        property_price=2_200_000,
        down_payment_available=200_000,
        property_type=PropertyType.FIRST_HOME,
        risk_profile=RiskProfile.STANDARD,
        existing_loans_payment=0,
        years=32,
    )

    tool_output = {
        "inputs": {
            "monthly_net_income": 8_000,
            "property_price": 2_200_000,
            "down_payment_available": 200_000,
            "existing_monthly_loans": 0,
            "loan_years": 32,
            "property_type": PropertyType.FIRST_HOME.value,
            "risk_profile": RiskProfile.STANDARD.value,
        },
        "eligibility": {
            "is_eligible": calc.is_eligible,
            "eligibility_notes": calc.eligibility_notes,
            "max_loan_amount": calc.max_loan_amount,
            "monthly_payment_capacity": calc.monthly_payment_capacity,
            "required_down_payment": calc.required_down_payment,
            "debt_to_income_ratio": calc.debt_to_income_ratio,
            "loan_to_value_ratio": calc.loan_to_value_ratio,
            "limits": {
                "dti_limit": MortgageEligibilityEvaluator.DTI_LIMITS[RiskProfile.STANDARD],
                "ltv_limit": MortgageEligibilityEvaluator.LTV_LIMITS[PropertyType.FIRST_HOME],
            },
        },
        "improvement_options": [],
    }

    guard_output = eligibility_compliance_guardrail.guardrail_function(
        ToolOutputGuardrailData(context=tool_ctx, agent=None, output=tool_output)
    )

    assert guard_output.behavior["type"] == "reject_content"
    assert VIOLATION_SNIPPET in guard_output.behavior["message"]
