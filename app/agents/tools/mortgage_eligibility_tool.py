from __future__ import annotations

import logging
from typing import Literal, NotRequired, TypedDict

from agents import function_tool

from ..guardrails import (
    eligibility_compliance_guardrail,
    intake_required_guardrail,
    planning_required_guardrail,
)
from app.services.mortgage_eligibility import (
    MortgageEligibilityEvaluator,
    PropertyType,
    RiskProfile,
)


logger = logging.getLogger(__name__)


class MortgageEligibilityInputs(TypedDict):
    monthly_net_income: float
    property_price: float
    down_payment_available: float
    existing_monthly_loans: float
    loan_years: int
    property_type: str
    risk_profile: str


class MortgageEligibilityLimits(TypedDict):
    dti_limit: float
    ltv_limit: float


class MortgageEligibilityDetails(TypedDict):
    is_eligible: bool
    eligibility_notes: str
    max_loan_amount: float
    monthly_payment_capacity: float
    required_down_payment: float
    debt_to_income_ratio: float
    loan_to_value_ratio: float
    limits: MortgageEligibilityLimits


class MortgageImprovementOption(TypedDict):
    type: Literal["reduce_price", "required_down_payment", "required_income"]
    target_value: float
    delta_value: NotRequired[float]
    additional_amount: NotRequired[float]


class MortgageEligibilityError(TypedDict):
    error: str


class MortgageEligibilityResult(TypedDict):
    inputs: MortgageEligibilityInputs
    eligibility: MortgageEligibilityDetails
    improvement_options: list[MortgageImprovementOption]


_PROPERTY_TYPE_MAP = {
    PropertyType.FIRST_HOME.value: PropertyType.FIRST_HOME,
    PropertyType.UPGRADE.value: PropertyType.UPGRADE,
    PropertyType.INVESTMENT.value: PropertyType.INVESTMENT,
}

_RISK_PROFILE_MAP = {
    RiskProfile.CONSERVATIVE.value: RiskProfile.CONSERVATIVE,
    RiskProfile.STANDARD.value: RiskProfile.STANDARD,
    RiskProfile.AGGRESSIVE.value: RiskProfile.AGGRESSIVE,
}


@function_tool
def evaluate_mortgage_eligibility(
    monthly_net_income: float,
    property_price: float,
    down_payment_available: float,
    existing_monthly_loans: float = 0.0,
    loan_years: int = 25,
    property_type: str = PropertyType.FIRST_HOME.value,
    risk_profile: str = RiskProfile.STANDARD.value,
) -> MortgageEligibilityResult | MortgageEligibilityError:
    """Evaluate Israeli mortgage eligibility using simplified banking rules."""
    try:
        prop_type = _PROPERTY_TYPE_MAP.get(property_type, PropertyType.FIRST_HOME)
        risk = _RISK_PROFILE_MAP.get(risk_profile, RiskProfile.STANDARD)

        calc = MortgageEligibilityEvaluator.evaluate(
            monthly_net_income=monthly_net_income,
            property_price=property_price,
            down_payment_available=down_payment_available,
            property_type=prop_type,
            risk_profile=risk,
            existing_loans_payment=existing_monthly_loans,
            years=loan_years,
        )

        inputs: MortgageEligibilityInputs = {
            "monthly_net_income": monthly_net_income,
            "property_price": property_price,
            "down_payment_available": down_payment_available,
            "existing_monthly_loans": existing_monthly_loans,
            "loan_years": loan_years,
            "property_type": prop_type.value,
            "risk_profile": risk.value,
        }

        limits: MortgageEligibilityLimits = {
            "dti_limit": MortgageEligibilityEvaluator.DTI_LIMITS[risk],
            "ltv_limit": MortgageEligibilityEvaluator.LTV_LIMITS[prop_type],
        }

        eligibility: MortgageEligibilityDetails = {
            "is_eligible": calc.is_eligible,
            "eligibility_notes": calc.eligibility_notes,
            "max_loan_amount": calc.max_loan_amount,
            "monthly_payment_capacity": calc.monthly_payment_capacity,
            "required_down_payment": calc.required_down_payment,
            "debt_to_income_ratio": calc.debt_to_income_ratio,
            "loan_to_value_ratio": calc.loan_to_value_ratio,
            "limits": limits,
        }

        improvement_options: list[MortgageImprovementOption] = []
        if not calc.is_eligible:
            adjustments = MortgageEligibilityEvaluator.adjustments_to_qualify(
                monthly_net_income,
                property_price,
                down_payment_available,
                prop_type,
                existing_monthly_loans,
            )

            if "reduce_price" in adjustments:
                target_price = adjustments["reduce_price"]
                improvement_options.append(
                    {
                        "type": "reduce_price",
                        "target_value": target_price,
                        "delta_value": max(property_price - target_price, 0.0),
                    }
                )

            if "required_down_payment" in adjustments:
                required = adjustments["required_down_payment"]
                additional = max(required - down_payment_available, 0.0)
                improvement_options.append(
                    {
                        "type": "required_down_payment",
                        "target_value": required,
                        "additional_amount": additional,
                    }
                )

            if "required_income" in adjustments:
                required_income = adjustments["required_income"]
                additional_income = max(required_income - monthly_net_income, 0.0)
                improvement_options.append(
                    {
                        "type": "required_income",
                        "target_value": required_income,
                        "additional_amount": additional_income,
                    }
                )

        return {
            "inputs": inputs,
            "eligibility": eligibility,
            "improvement_options": improvement_options,
        }

    except Exception as exc:
        logger.error("Eligibility calculation failed: %s", exc)
        return {"error": f"eligibility calculation failed - {exc}"}


evaluate_mortgage_eligibility.tool_input_guardrails = [
    intake_required_guardrail,
    planning_required_guardrail,
]
evaluate_mortgage_eligibility.tool_output_guardrails = [
    eligibility_compliance_guardrail
]
