"""Quick feasibility checks for early intake triage."""

from __future__ import annotations

import logging

from app.domain.schemas import FeasibilityIssue, FeasibilityResult
from app.services.mortgage_eligibility import (
    MortgageEligibilityEvaluator,
    PropertyType,
    RiskProfile,
)


logger = logging.getLogger(__name__)

_PROPERTY_TYPE_MAP = {
    "single": PropertyType.FIRST_HOME,
    "first_home": PropertyType.FIRST_HOME,
    "replacement": PropertyType.UPGRADE,
    "upgrade": PropertyType.UPGRADE,
    "investment": PropertyType.INVESTMENT,
}

_DEAL_TYPE_MAP = {
    "first_home": PropertyType.FIRST_HOME,
    "replacement": PropertyType.UPGRADE,
    "investment": PropertyType.INVESTMENT,
}


def _resolve_property_type(
    property_type: str | None, deal_type: str | None, occupancy: str | None
) -> PropertyType:
    if deal_type:
        mapped = _DEAL_TYPE_MAP.get(deal_type.lower())
        if mapped:
            return mapped

    if occupancy:
        occ = occupancy.lower()
        if occ == "own":
            return PropertyType.FIRST_HOME
        if occ == "rent":
            return PropertyType.INVESTMENT

    if property_type:
        return _PROPERTY_TYPE_MAP.get(property_type.lower(), PropertyType.FIRST_HOME)

    return PropertyType.FIRST_HOME


def run_feasibility_checks(
    *,
    property_price: float,
    down_payment_available: float,
    monthly_net_income: float,
    existing_monthly_loans: float,
    loan_years: int,
    property_type: str | None,
    deal_type: str | None = None,
    occupancy: str | None = None,
    assessed_payment: float | None = None,
    peak_payment: float | None = None,
    borrower_age_years: int | None = None,
) -> FeasibilityResult:
    """Run quick LTV/PTI checks to detect obviously infeasible requests."""

    issues: list[FeasibilityIssue] = []

    if property_price <= 0:
        issue = FeasibilityIssue(
            code="invalid_property_price",
            message="יש לספק מחיר נכס גדול מאפס",
        )
        issues.append(issue)
        return FeasibilityResult(
            is_feasible=False,
            ltv_ratio=1.0,
            ltv_limit=1.0,
            pti_ratio=1.0,
            pti_limit=1.0,
            issues=issues,
        )
    loan_years = max(min(loan_years or 25, 40), 1)
    prop_type = _resolve_property_type(property_type, deal_type, occupancy)

    if property_type:
        declared = _PROPERTY_TYPE_MAP.get(property_type.lower())
        if declared and declared != prop_type:
            logger.info(
                "adjusted property classification",
                extra={
                    "declared": property_type,
                    "derived": prop_type.value,
                    "deal_type": deal_type,
                    "occupancy": occupancy,
                },
            )

    outstanding = max(property_price - max(down_payment_available, 0.0), 0.0)
    ltv_ratio = outstanding / property_price if property_price else 1.0
    ltv_limit = MortgageEligibilityEvaluator.LTV_LIMITS[prop_type]

    income = max(monthly_net_income, 0.0)
    existing_obligations = max(existing_monthly_loans, 0.0)

    calc = MortgageEligibilityEvaluator.evaluate(
        monthly_net_income=income,
        property_price=property_price,
        down_payment_available=max(down_payment_available, 0.0),
        property_type=prop_type,
        risk_profile=RiskProfile.STANDARD,
        existing_loans_payment=existing_obligations,
        years=loan_years,
        monthly_payment_override=assessed_payment,
    )

    pti_ratio = calc.debt_to_income_ratio
    pti_limit = MortgageEligibilityEvaluator.PTI_LIMITS[RiskProfile.STANDARD]
    income_for_ratio = max(income, 1.0)
    if peak_payment is not None:
        pti_ratio_peak = (
            max(peak_payment, 0.0) + existing_obligations
        ) / income_for_ratio
    else:
        pti_ratio_peak = pti_ratio

    if ltv_ratio > ltv_limit + 1e-6:
        required_down_payment = property_price * (1 - ltv_limit)
        extra_needed = max(required_down_payment - down_payment_available, 0.0)
        issues.append(
            FeasibilityIssue(
                code="ltv_exceeds_limit",
                message=(
                    "יחס המימון גבוה מהמותר. יש להגדיל הון עצמי או להקטין את מחיר הנכס"
                ),
                details={
                    "ltv_ratio": round(ltv_ratio, 4),
                    "ltv_limit": ltv_limit,
                    "additional_equity_required": extra_needed,
                },
            )
        )

    if pti_ratio > pti_limit + 1e-6:
        issues.append(
            FeasibilityIssue(
                code="pti_exceeds_limit",
                message=(
                    "תשלום חודשי צפוי חורג מ-50% מהכנסה נטו. יש להקטין את ההלוואה או להעלות הכנסה"
                ),
                details={
                    "pti_ratio": round(pti_ratio, 4),
                    "pti_limit": pti_limit,
                    "monthly_payment_capacity": calc.monthly_payment_capacity,
                },
            )
        )

    if borrower_age_years is not None:
        age_at_maturity = borrower_age_years + loan_years
        if age_at_maturity > 85:
            issues.append(
                FeasibilityIssue(
                    code="age_term_beyond_retirement",
                    message=(
                        "התקופה המבוקשת תחצה את גיל 85; ייתכן שהבנק ידרוש תקופה קצרה יותר או לווים נוספים."
                    ),
                    details={
                        "age_years": borrower_age_years,
                        "loan_term_years": loan_years,
                        "age_at_maturity": age_at_maturity,
                    },
                )
            )

    is_feasible = not issues

    return FeasibilityResult(
        is_feasible=is_feasible,
        ltv_ratio=ltv_ratio,
        ltv_limit=ltv_limit,
        pti_ratio=pti_ratio,
        pti_limit=pti_limit,
        pti_ratio_peak=pti_ratio_peak,
        issues=issues,
    )
