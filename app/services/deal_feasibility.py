"""Quick feasibility checks that mirror core BOI guardrails."""

from __future__ import annotations

import logging

from app.configuration import boi_limits
from app.domain.schemas import (
    DealType,
    FeasibilityIssue,
    FeasibilityResult,
    OccupancyIntent,
    PropertyType,
)
from app.services.mortgage_eligibility import MortgageEligibilityEvaluator, RiskProfile

logger = logging.getLogger(__name__)

_PROPERTY_TYPE_MAP = {
    "single": PropertyType.SINGLE,
    "first_home": PropertyType.SINGLE,
    "replacement": PropertyType.REPLACEMENT,
    "upgrade": PropertyType.REPLACEMENT,
    "investment": PropertyType.INVESTMENT,
}

_DEAL_TYPE_MAP = {
    "first_home": DealType.FIRST_HOME,
    "replacement": DealType.REPLACEMENT,
    "investment": DealType.INVESTMENT,
}

_OCCUPANCY_MAP = {
    "own": OccupancyIntent.OWN,
    "rent": OccupancyIntent.RENT,
}


def _resolve_context(
    property_type: str | None, deal_type: str | None, occupancy: str | None
) -> tuple[PropertyType, DealType, OccupancyIntent]:
    resolved_deal = DealType.FIRST_HOME
    if deal_type and deal_type.lower() in _DEAL_TYPE_MAP:
        resolved_deal = _DEAL_TYPE_MAP[deal_type.lower()]

    resolved_property = _PROPERTY_TYPE_MAP.get(
        (property_type or "").lower(),
        PropertyType.SINGLE,
    )
    if resolved_deal == DealType.REPLACEMENT:
        resolved_property = PropertyType.REPLACEMENT
    elif resolved_deal == DealType.INVESTMENT:
        resolved_property = PropertyType.INVESTMENT

    resolved_occupancy = _OCCUPANCY_MAP.get(
        (occupancy or "").lower(), OccupancyIntent.OWN
    )

    if property_type and resolved_property != _PROPERTY_TYPE_MAP.get(
        property_type.lower()
    ):
        logger.info(
            "adjusted property classification",
            extra={
                "declared": property_type,
                "derived": resolved_property.value,
                "deal_type": resolved_deal.value,
                "occupancy": resolved_occupancy.value,
            },
        )

    return resolved_property, resolved_deal, resolved_occupancy


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
    variable_share: float | None = None,
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
) -> FeasibilityResult:
    """Run quick calculations to flag obviously infeasible requests."""

    issues: list[FeasibilityIssue] = []

    if property_price <= 0:
        issues.append(
            FeasibilityIssue(
                code="invalid_property_price",
                message="שווי הנכס חייב להיות גדול מאפס.",
            )
        )
        return FeasibilityResult(
            is_feasible=False,
            ltv_ratio=1.0,
            ltv_limit=1.0,
            pti_ratio=1.0,
            pti_limit=1.0,
            issues=issues,
        )

    requested_term_years = loan_years or 25
    property_enum, deal_enum, occupancy_enum = _resolve_context(
        property_type, deal_type, occupancy
    )

    income = max(monthly_net_income, 0.0)
    existing_obligations = max(existing_monthly_loans, 0.0)
    extra_housing = max(other_housing_payments, 0.0)
    rent_expense = max(borrower_rent_expense, 0.0)

    calc = MortgageEligibilityEvaluator.evaluate(
        monthly_net_income=income,
        property_price=property_price,
        down_payment_available=max(down_payment_available, 0.0),
        property_type=property_enum,
        deal_type=deal_enum,
        risk_profile=RiskProfile.STANDARD,
        occupancy=occupancy_enum,
        existing_loans_payment=existing_obligations,
        other_housing_payments=extra_housing,
        loan_term_years=max(requested_term_years, 1),
        monthly_payment_override=assessed_payment,
        peak_payment_override=peak_payment,
        variable_share_ratio=variable_share,
        is_bridge_loan=is_bridge_loan,
        bridge_term_months=bridge_term_months,
        any_purpose_amount_nis=any_purpose_amount_nis,
        is_refinance=is_refinance,
        previous_pti_ratio=previous_pti_ratio,
        previous_ltv_ratio=previous_ltv_ratio,
        previous_variable_share_ratio=previous_variable_share_ratio,
        is_reduced_price_dwelling=is_reduced_price_dwelling,
        appraised_value_nis=appraised_value_nis,
        borrower_rent_expense=rent_expense,
    )

    ltv_limit = MortgageEligibilityEvaluator._resolve_ltv_limit(
        property_enum, deal_enum
    )
    pti_limit = calc.pti_limit_applied
    variable_share_limit_pct = boi_limits.VARIABLE_SHARE_LIMIT * 100
    variable_share_pct = variable_share * 100 if variable_share is not None else None

    if calc.required_down_payment > down_payment_available + 1e-6:
        issues.append(
            FeasibilityIssue(
                code="equity_shortfall",
                message="יתרת ההון העצמי הנוכחית אינה מספיקה כדי לעמוד במגבלת המימון, ולכן יש להשלים הון עצמי נוסף או להוזיל את העסקה.",
                details={
                    "required_equity_nis": round(calc.required_down_payment, 2),
                    "available_equity_nis": round(down_payment_available, 2),
                    "ltv_limit": ltv_limit,
                },
            )
        )

    if calc.debt_to_income_ratio > pti_limit + 1e-6:
        issues.append(
            FeasibilityIssue(
                code="pti_exceeds_limit",
                message="סך ההחזרים החודשיים חורג מ-50% מההכנסה נטו, ולכן לא ניתן לאשר את המסלול במתכונת הזו.",
                details={
                    "pti_ratio": round(calc.debt_to_income_ratio, 4),
                    "pti_peak": round(calc.peak_debt_to_income_ratio, 4),
                    "pti_limit": pti_limit,
                    "monthly_payment_capacity": calc.monthly_payment_capacity,
                },
            )
        )

    if calc.loan_to_value_ratio > ltv_limit + 1e-6:
        issues.append(
            FeasibilityIssue(
                code="ltv_exceeds_limit",
                message="שיעור המימון המבוקש גבוה מהמותר עבור סוג העסקה, ולכן יש להגדיל הון עצמי או להפחית את סכום ההלוואה.",
                details={
                    "ltv_ratio": round(calc.loan_to_value_ratio, 4),
                    "ltv_limit": ltv_limit,
                    "ltv_value_basis": calc.ltv_value_basis,
                },
            )
        )

    if (
        variable_share_pct is not None
        and variable_share_pct > variable_share_limit_pct + 1e-6
    ):
        issues.append(
            FeasibilityIssue(
                code="variable_share_exceeds_limit",
                message="החלק במסלולים בריבית משתנה גבוה משני שלישים מההלוואה ולכן יש להתאים את התמהיל.",
                details={
                    "variable_share_pct": round(variable_share_pct, 2),
                    "variable_share_limit_pct": variable_share_limit_pct,
                },
            )
        )

    if requested_term_years > boi_limits.MAX_TERM_YEARS:
        issues.append(
            FeasibilityIssue(
                code="loan_term_exceeds_limit",
                message="תקופת ההלוואה המבוקשת ארוכה מ-30 שנים, ולכן יש לקצר את התקופה או לבחור פריסה אחרת.",
                details={
                    "requested_term_years": requested_term_years,
                    "term_limit_years": boi_limits.MAX_TERM_YEARS,
                },
            )
        )

    # Surface any additional regulatory violations (e.g., רולאובר).
    recognized_messages = {issue.message for issue in issues}
    for violation in calc.violations:
        if violation in recognized_messages:
            continue
        issues.append(
            FeasibilityIssue(
                code="regulatory_violation",
                message=violation,
            )
        )

    if borrower_age_years is not None:
        maturity_age = borrower_age_years + max(requested_term_years, 1)
        if maturity_age > 85:
            issues.append(
                FeasibilityIssue(
                    code="age_term_beyond_retirement",
                    message="הגיל בסיום ההלוואה עולה על 85, ולכן צריך לקצר את התקופה או לצרף לווה נוסף.",
                    details={
                        "age_years": borrower_age_years,
                        "loan_term_years": requested_term_years,
                        "age_at_maturity": maturity_age,
                    },
                )
            )

    is_feasible = not issues

    return FeasibilityResult(
        is_feasible=is_feasible,
        ltv_ratio=calc.loan_to_value_ratio,
        ltv_limit=ltv_limit,
        pti_ratio=calc.debt_to_income_ratio,
        pti_limit=pti_limit,
        pti_ratio_peak=calc.peak_debt_to_income_ratio,
        variable_share_pct=variable_share_pct,
        variable_share_limit_pct=variable_share_limit_pct,
        loan_term_years=requested_term_years,
        loan_term_limit_years=boi_limits.MAX_TERM_YEARS,
        issues=issues,
    )
