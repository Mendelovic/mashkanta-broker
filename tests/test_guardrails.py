import inspect
import json
from typing import Any, Callable, Iterator, cast

import pytest
from agents import Agent
from agents.tool_context import ToolContext
from agents.tool_guardrails import ToolInputGuardrailData, ToolOutputGuardrailData

from app.agents.guardrails import (
    optimization_required_guardrail,
    eligibility_compliance_guardrail,
    intake_required_guardrail,
    planning_required_guardrail,
)
from app.agents.tools.mortgage_eligibility_tool import evaluate_mortgage_eligibility
from app.models.context import ChatRunContext
from app.services import session_manager
from app.db.session import SessionLocal
from app.services.session_repository import SessionRepository
from app.domain.schemas import DealType, PropertyType
from app.services.mortgage_eligibility import MortgageEligibilityEvaluator, RiskProfile
from app.services.planning_mapper import build_planning_context

from .async_utils import run_async
from .factories import build_submission

NO_INTAKE_SNIPPET = "Cannot run eligibility checks before the intake interview"
NO_PLANNING_SNIPPET = "Cannot run eligibility checks before the planning context"


def create_tool_context(session_id: str, arguments: str) -> ToolContext[ChatRunContext]:
    return ToolContext(
        context=ChatRunContext(session_id=session_id),
        tool_name=evaluate_mortgage_eligibility.name,
        tool_call_id="eligibility-tool-call",
        tool_arguments=arguments,
    )


@pytest.fixture
def cleanup_sessions() -> Iterator[Callable[[str], None]]:
    created: list[str] = []

    def _register(session_id: str) -> None:
        created.append(session_id)
        session_manager._session_cache.pop(session_id, None)
        with SessionLocal() as db:
            repo = SessionRepository(db)
            repo.delete_session(session_id)
            db.commit()

    yield _register

    for session_id in created:
        session_manager._session_cache.pop(session_id, None)
        with SessionLocal() as db:
            repo = SessionRepository(db)
            repo.delete_session(session_id)
            db.commit()


def test_input_guardrail_blocks_when_no_intake(
    cleanup_sessions: Callable[[str], None],
) -> None:
    session_id = "guardrail-no-intake"
    cleanup_sessions(session_id)
    session_manager._session_cache.pop(session_id, None)
    session_manager.get_or_create_session(session_id, user_id=TEST_USER_ID)

    arguments = json.dumps(
        {
            "monthly_net_income": 18_000,
            "property_price": 1_800_000,
            "down_payment_available": 500_000,
        }
    )
    tool_ctx = create_tool_context(session_id, arguments)

    guard_output = resolve_guardrail(
        intake_required_guardrail.guardrail_function(
            ToolInputGuardrailData(context=tool_ctx, agent=cast(Agent, None))
        )
    )

    assert guard_output.behavior["type"] == "reject_content"
    behavior_dict = cast(dict[str, Any], guard_output.behavior)
    assert NO_INTAKE_SNIPPET in behavior_dict["message"]


def test_input_guardrail_allows_with_confirmed_intake(
    cleanup_sessions: Callable[[str], None],
) -> None:
    session_id = "guardrail-valid-intake"
    cleanup_sessions(session_id)
    session_manager._session_cache.pop(session_id, None)
    _, session = session_manager.get_or_create_session(session_id, user_id=TEST_USER_ID)
    session.save_intake_submission(build_submission())

    arguments = json.dumps(
        {
            "monthly_net_income": 20_000,
            "property_price": 1_100_000,
            "down_payment_available": 400_000,
            "loan_years": 25,
            "existing_monthly_loans": 0,
            "property_type": "first_home",
            "risk_profile": RiskProfile.STANDARD,
        }
    )
    tool_ctx = create_tool_context(session_id, arguments)

    guard_output = resolve_guardrail(
        intake_required_guardrail.guardrail_function(
            ToolInputGuardrailData(context=tool_ctx, agent=cast(Agent, None))
        )
    )

    assert guard_output.behavior["type"] == "allow"


def test_planning_guardrail_blocks_without_context(
    cleanup_sessions: Callable[[str], None],
) -> None:
    session_id = "guardrail-no-planning"
    cleanup_sessions(session_id)
    session_manager._session_cache.pop(session_id, None)
    _, session = session_manager.get_or_create_session(session_id, user_id=TEST_USER_ID)
    session.save_intake_submission(build_submission())

    tool_ctx = create_tool_context(session_id, "{}")

    guard_output = resolve_guardrail(
        planning_required_guardrail.guardrail_function(
            ToolInputGuardrailData(context=tool_ctx, agent=cast(Agent, None))
        )
    )

    assert guard_output.behavior["type"] == "reject_content"
    behavior_dict = cast(dict[str, Any], guard_output.behavior)
    assert NO_PLANNING_SNIPPET in behavior_dict["message"]


def test_planning_guardrail_allows_with_context(
    cleanup_sessions: Callable[[str], None],
) -> None:
    session_id = "guardrail-with-planning"
    cleanup_sessions(session_id)
    session_manager._session_cache.pop(session_id, None)
    _, session = session_manager.get_or_create_session(session_id, user_id=TEST_USER_ID)
    submission = build_submission()
    session.save_intake_submission(submission)
    session.set_planning_context(build_planning_context(submission))

    tool_ctx = create_tool_context(session_id, "{}")

    guard_output = resolve_guardrail(
        planning_required_guardrail.guardrail_function(
            ToolInputGuardrailData(context=tool_ctx, agent=cast(Agent, None))
        )
    )

    assert guard_output.behavior["type"] == "allow"


def test_optimization_guardrail_blocks_without_result(
    cleanup_sessions: Callable[[str], None],
) -> None:
    session_id = "guardrail-no-optimization"
    cleanup_sessions(session_id)
    session_manager._session_cache.pop(session_id, None)
    _, session = session_manager.get_or_create_session(session_id, user_id=TEST_USER_ID)
    submission = build_submission()
    session.save_intake_submission(submission)
    session.set_planning_context(build_planning_context(submission))

    tool_ctx = create_tool_context(session_id, "{}")
    guard_output = resolve_guardrail(
        optimization_required_guardrail.guardrail_function(
            ToolInputGuardrailData(context=tool_ctx, agent=cast(Agent, None))
        )
    )

    assert guard_output.behavior["type"] == "reject_content"


def test_optimization_guardrail_allows_with_result(
    cleanup_sessions: Callable[[str], None],
) -> None:
    session_id = "guardrail-with-optimization"
    cleanup_sessions(session_id)
    session_manager._session_cache.pop(session_id, None)
    _, session = session_manager.get_or_create_session(session_id, user_id=TEST_USER_ID)
    submission = build_submission()
    session.save_intake_submission(submission)
    planning_context = build_planning_context(submission)
    session.set_planning_context(planning_context)

    from app.services.mix_optimizer import optimize_mixes

    session.set_optimization_result(optimize_mixes(submission.record, planning_context))

    tool_ctx = create_tool_context(session_id, "{}")
    guard_output = resolve_guardrail(
        optimization_required_guardrail.guardrail_function(
            ToolInputGuardrailData(context=tool_ctx, agent=cast(Agent, None))
        )
    )

    assert guard_output.behavior["type"] == "allow"


def test_output_guardrail_rejects_on_violation(
    cleanup_sessions: Callable[[str], None],
) -> None:
    session_id = "guardrail-violation"
    cleanup_sessions(session_id)
    session_manager._session_cache.pop(session_id, None)
    _, session = session_manager.get_or_create_session(session_id, user_id=TEST_USER_ID)
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
            "property_type": "first_home",
            "risk_profile": RiskProfile.STANDARD,
        }
    )
    tool_ctx = create_tool_context(session_id, arguments)

    guard_intake = resolve_guardrail(
        intake_required_guardrail.guardrail_function(
            ToolInputGuardrailData(context=tool_ctx, agent=cast(Agent, None))
        )
    )
    assert guard_intake.behavior["type"] == "allow"

    guard_planning = resolve_guardrail(
        planning_required_guardrail.guardrail_function(
            ToolInputGuardrailData(context=tool_ctx, agent=cast(Agent, None))
        )
    )
    assert guard_planning.behavior["type"] == "allow"

    calc = MortgageEligibilityEvaluator.evaluate(
        monthly_net_income=8_000,
        property_price=2_200_000,
        down_payment_available=200_000,
        property_type=PropertyType.SINGLE,
        deal_type=DealType.FIRST_HOME,
        risk_profile=RiskProfile.STANDARD,
        existing_loans_payment=0,
        loan_term_years=32,
    )

    tool_output = {
        "inputs": {
            "monthly_net_income": 8_000,
            "property_price": 2_200_000,
            "down_payment_available": 200_000,
            "existing_monthly_loans": 0,
            "loan_years": 32,
            "property_type": "first_home",
            "risk_profile": RiskProfile.STANDARD,
        },
        "eligibility": {
            "is_eligible": calc.is_eligible,
            "eligibility_notes": calc.eligibility_notes,
            "max_loan_amount": calc.max_loan_amount,
            "monthly_payment_capacity": calc.monthly_payment_capacity,
            "required_down_payment": calc.required_down_payment,
            "debt_to_income_ratio": calc.debt_to_income_ratio,
            "peak_debt_to_income_ratio": calc.peak_debt_to_income_ratio,
            "loan_to_value_ratio": calc.loan_to_value_ratio,
            "ltv_value_basis": calc.ltv_value_basis,
            "assessed_monthly_payment": calc.assessed_monthly_payment,
            "pti_limit_applied": calc.pti_limit_applied,
            "limits": {
                "pti_limit": calc.pti_limit_applied,
                "dti_limit": calc.pti_limit_applied,
                "ltv_limit": MortgageEligibilityEvaluator._resolve_ltv_limit(
                    PropertyType.SINGLE, DealType.FIRST_HOME
                ),
            },
            "violations": calc.violations,
            "warnings": calc.warnings,
            "applied_exceptions": calc.applied_exceptions,
        },
        "improvement_options": [],
    }

    guard_output = resolve_guardrail(
        eligibility_compliance_guardrail.guardrail_function(
            ToolOutputGuardrailData(
                context=tool_ctx, agent=cast(Agent, None), output=tool_output
            )
        )
    )

    assert guard_output.behavior["type"] == "reject_content"
    behavior_dict = cast(dict[str, Any], guard_output.behavior)
    if calc.violations:
        assert calc.violations[0] in behavior_dict["message"]


def resolve_guardrail(result):
    if inspect.isawaitable(result):
        return run_async(result)
    return result


TEST_USER_ID = "test-user-guardrails"
