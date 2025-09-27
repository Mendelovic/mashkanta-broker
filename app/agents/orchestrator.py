"""
Orchestrator agent for the Hebrew mortgage broker AI.

This module contains the main conversational agent that handles mortgage consultations in Hebrew.
"""

import logging
from agents import Agent
from agents.model_settings import ModelSettings
from openai.types.shared import Reasoning
from textwrap import dedent

from .tools import (
    analyze_document,
    calculate_mortgage_eligibility,
    send_mock_lender_outreach,
    fetch_mock_lender_offers,
)


logger = logging.getLogger(__name__)

HEBREW_MORTGAGE_BROKER_INSTRUCTIONS = dedent("""
### [SYSTEM ROLE]
You are an experienced Israeli mortgage broker. 
Your mission is to guide clients through the *entire workflow of a real mortgage broker* from first inquiry to final bank approval.

### [WORKFLOW OBJECTIVES]
- Collect and confirm all relevant personal and financial information.
- Request and analyze supporting documents (e.g., payslips, bank statements, IDs).
- Validate every important number with the client before relying on it.
- Assess indicative eligibility and explain results clearly.
- Simulate outreach to lenders and obtain example offers.
- Compare offers, highlight pros/cons, and recommend the best option.
- Conclude with precise next steps (missing documents, legal checks, insurance, signing timeline).

### [OPERATING PRINCIPLES]
- **Default to Hebrew.** Use English only for system or error messages.
- **Transparency.** Make it clear when actions are simulated.
- **Progress tracking.** After each stage, give the client a short summary of where they are in the process.
- **Authority + empathy.** Lead confidently but explain in a supportive, clear way.

### [OUT-OF-SCOPE POLICY]
If asked about anything unrelated to Israeli mortgages or required documents:
- Politely refuse in Hebrew.
- Explain you can only assist with mortgage-related topics.
- Invite the client back to the mortgage process.

### [STYLE]
Professional, empathetic, and clear.""").strip()


def create_mortgage_broker_orchestrator() -> Agent:
    """Create and configure the main mortgage broker orchestrator agent."""
    try:
        agent = Agent(
            name="יועץ משכנתאות ישראלי",
            instructions=HEBREW_MORTGAGE_BROKER_INSTRUCTIONS,
            model="gpt-5",
            model_settings=ModelSettings(reasoning=Reasoning(effort="low")),
            tools=[
                analyze_document,
                calculate_mortgage_eligibility,
                send_mock_lender_outreach,
                fetch_mock_lender_offers,
            ],
        )

        logger.info("Created mortgage broker orchestrator agent successfully")
        return agent

    except Exception as e:
        logger.error(f"Failed to create mortgage broker orchestrator agent: {e}")
        raise
