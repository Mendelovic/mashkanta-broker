"""Tool for quick deal feasibility triage."""

from __future__ import annotations

import json
import logging

from agents import function_tool

from ...services.deal_feasibility import run_feasibility_checks
from ...services.mortgage_eligibility import PropertyType

logger = logging.getLogger(__name__)


@function_tool
def check_deal_feasibility(
    property_price: float,
    down_payment_available: float,
    monthly_net_income: float,
    existing_monthly_loans: float = 0.0,
    loan_years: int = 25,
    property_type: str = PropertyType.FIRST_HOME.value,
    deal_type: str | None = None,
    occupancy: str | None = None,
    borrower_age_years: int | None = None,
) -> str:
    """Run a quick LTV/PTI feasibility check before continuing the full intake."""

    result = run_feasibility_checks(
        property_price=property_price,
        down_payment_available=down_payment_available,
        monthly_net_income=monthly_net_income,
        existing_monthly_loans=existing_monthly_loans,
        loan_years=loan_years,
        property_type=property_type,
        deal_type=deal_type,
        occupancy=occupancy,
        borrower_age_years=borrower_age_years,
    )

    logger.info(
        "feasibility check completed",
        extra={
            "is_feasible": result.is_feasible,
            "ltv_ratio": result.ltv_ratio,
            "pti_ratio": result.pti_ratio,
        },
    )

    return json.dumps(result.model_dump(), ensure_ascii=False)


__all__ = ["check_deal_feasibility"]
