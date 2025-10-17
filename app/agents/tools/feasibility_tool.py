"""Tool for quick deal feasibility triage."""

from __future__ import annotations

import json
import logging

from agents import function_tool

from ...domain.schemas import PropertyType
from ...services.deal_feasibility import run_feasibility_checks

logger = logging.getLogger(__name__)


@function_tool
def check_deal_feasibility(
    property_price: float,
    down_payment_available: float,
    monthly_net_income: float,
    existing_monthly_loans: float = 0.0,
    loan_years: int = 25,
    property_type: str = PropertyType.SINGLE.value,
    deal_type: str | None = None,
    occupancy: str | None = None,
    borrower_age_years: int | None = None,
    other_housing_payments: float = 0.0,
    borrower_rent_expense: float = 0.0,
    is_bridge_loan: bool = False,
    bridge_term_months: int | None = None,
    any_purpose_amount_nis: float | None = None,
    is_refinance: bool = False,
    previous_pti_ratio: float | None = None,
    previous_ltv_ratio: float | None = None,
    previous_variable_share_ratio: float | None = None,
    is_reduced_price_dwelling: bool = False,
    appraised_value_nis: float | None = None,
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
        other_housing_payments=other_housing_payments,
        borrower_rent_expense=borrower_rent_expense,
        is_bridge_loan=is_bridge_loan,
        bridge_term_months=bridge_term_months,
        any_purpose_amount_nis=any_purpose_amount_nis,
        is_reduced_price_dwelling=is_reduced_price_dwelling,
        appraised_value_nis=appraised_value_nis,
        is_refinance=is_refinance,
        previous_pti_ratio=previous_pti_ratio,
        previous_ltv_ratio=previous_ltv_ratio,
        previous_variable_share_ratio=previous_variable_share_ratio,
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
