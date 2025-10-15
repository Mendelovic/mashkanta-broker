import asyncio
import json
import pytest

from agents.tool_context import ToolContext

from app.agents.tools.feasibility_tool import check_deal_feasibility
from app.models.context import ChatRunContext


def run_tool(payload: dict) -> dict:
    arguments = json.dumps(payload)
    ctx = ToolContext(
        context=ChatRunContext(session_id="test-session"),
        tool_name=check_deal_feasibility.name,
        tool_call_id="feasibility-tool",
        tool_arguments=arguments,
    )
    output = asyncio.run(check_deal_feasibility.on_invoke_tool(ctx, arguments))
    return json.loads(output)


def test_check_deal_feasibility_returns_json():
    payload = {
        "property_price": 1_200_000,
        "down_payment_available": 400_000,
        "monthly_net_income": 20_000,
        "existing_monthly_loans": 0,
        "loan_years": 25,
        "property_type": "single",
    }
    data = run_tool(payload)
    assert data["is_feasible"] is True


def test_check_deal_feasibility_flags_issue():
    payload = {
        "property_price": 1_000_000,
        "down_payment_available": 50_000,
        "monthly_net_income": 10_000,
        "existing_monthly_loans": 0,
        "loan_years": 25,
        "property_type": "single",
    }
    data = run_tool(payload)
    assert data["is_feasible"] is False
    assert any(issue["code"] == "ltv_exceeds_limit" for issue in data["issues"])


def test_check_deal_feasibility_flags_age_term_warning():
    payload = {
        "property_price": 1_400_000,
        "down_payment_available": 500_000,
        "monthly_net_income": 22_000,
        "existing_monthly_loans": 0,
        "loan_years": 30,
        "property_type": "single",
        "borrower_age_years": 58,
    }
    data = run_tool(payload)
    assert any(
        issue["code"] == "age_term_beyond_retirement" for issue in data["issues"]
    )


def test_check_deal_feasibility_uses_deal_type_and_occupancy():
    payload = {
        "property_price": 1_100_000,
        "down_payment_available": 325_000,
        "monthly_net_income": 21_000,
        "existing_monthly_loans": 0,
        "loan_years": 25,
        "property_type": "investment",
        "deal_type": "first_home",
        "occupancy": "own",
    }
    data = run_tool(payload)
    assert data["ltv_limit"] == pytest.approx(0.75)
