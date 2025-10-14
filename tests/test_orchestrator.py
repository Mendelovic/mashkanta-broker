from app.agents.orchestrator import create_mortgage_broker_orchestrator


def test_orchestrator_instantiates_and_registers_tools():
    agent = create_mortgage_broker_orchestrator()

    assert agent is not None
    tool_names = {tool.name for tool in agent.tools}
    expected = {
        "check_deal_feasibility",
        "submit_intake_record",
        "compute_planning_context",
        "run_mix_optimization",
        "analyze_document",
        "evaluate_mortgage_eligibility",
        "record_timeline_event",
    }
    assert expected.issubset(tool_names)
