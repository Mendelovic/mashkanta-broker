import asyncio
import json

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
