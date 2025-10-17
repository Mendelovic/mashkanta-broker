"""
Israeli mortgage eligibility evaluation helpers based on Bank of Israel directives.

Provides indicative eligibility checks aligned with Directive 329 requirements.
For production use, integrate live market data, full underwriting rules and
source weighting.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from app.configuration import boi_limits
from app.domain.schemas import DealType, OccupancyIntent, PropertyType


class RiskProfile:
    """Risk tolerance presets that influence internal PTI comfort levels."""

    CONSERVATIVE = "conservative"
    STANDARD = "standard"
    AGGRESSIVE = "aggressive"


@dataclass
class MortgageEligibilityResult:
    """Snapshot of an eligibility evaluation."""

    max_loan_amount: float
    monthly_payment_capacity: float
    required_down_payment: float
    debt_to_income_ratio: float
    loan_to_value_ratio: float
    total_property_price: float
    is_eligible: bool
    eligibility_notes: str
    assessed_monthly_payment: float = 0.0
    pti_limit_applied: float = boi_limits.PTI_REGULATORY_LIMIT
    peak_debt_to_income_ratio: float = 0.0
    ltv_value_basis: float = 0.0
    violations: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    applied_exceptions: List[str] = field(default_factory=list)


class MortgageEligibilityEvaluator:
    """Core BOI guardrail evaluator for intake, feasibility, and optimization flows."""

    DEFAULT_INTEREST_RATE_ANNUAL: float = 0.04
    RISK_PROFILE_PTI_LIMITS: Dict[str, float] = {
        RiskProfile.CONSERVATIVE: 0.30,
        RiskProfile.STANDARD: 0.33,
        RiskProfile.AGGRESSIVE: 0.40,
    }

    @staticmethod
    def _calculate_monthly_payment(
        loan_amount: float, monthly_rate: float, months: int
    ) -> float:
        """Calculate monthly payment using mortgage formula."""
        if loan_amount <= 0 or months <= 0:
            return 0.0
        if monthly_rate <= 0:
            return loan_amount / months
        factor = (
            monthly_rate
            * (1 + monthly_rate) ** months
            / ((1 + monthly_rate) ** months - 1)
        )
        return loan_amount * factor

    @classmethod
    def _resolve_ltv_limit(
        cls, property_type: PropertyType, deal_type: Optional[DealType]
    ) -> float:
        if deal_type is not None:
            limit = boi_limits.LTV_LIMITS_BY_DEAL.get(deal_type)
            if limit is not None:
                return limit
        return boi_limits.LTV_LIMITS_BY_PROPERTY.get(property_type, 0.0)

    @classmethod
    def _buyer_price_value_basis(
        cls,
        *,
        purchase_price: float,
        is_reduced_price_dwelling: bool,
        appraised_value_nis: Optional[float],
    ) -> float:
        if not is_reduced_price_dwelling or appraised_value_nis is None:
            return purchase_price
        if appraised_value_nis <= boi_limits.BUYER_PRICE_APPRAISAL_CAP_NIS:
            return appraised_value_nis
        return max(boi_limits.BUYER_PRICE_APPRAISAL_CAP_NIS, purchase_price)

    @classmethod
    def evaluate(
        cls,
        *,
        monthly_net_income: float,
        property_price: float,
        down_payment_available: float,
        property_type: PropertyType = PropertyType.SINGLE,
        deal_type: DealType = DealType.FIRST_HOME,
        risk_profile: str = RiskProfile.STANDARD,
        occupancy: OccupancyIntent = OccupancyIntent.OWN,
        existing_loans_payment: float = 0.0,
        other_housing_payments: float = 0.0,
        loan_term_years: int = 25,
        monthly_payment_override: Optional[float] = None,
        peak_payment_override: Optional[float] = None,
        variable_share_ratio: Optional[float] = None,
        is_bridge_loan: bool = False,
        bridge_term_months: Optional[int] = None,
        any_purpose_amount_nis: Optional[float] = None,
        is_refinance: bool = False,
        previous_pti_ratio: Optional[float] = None,
        previous_ltv_ratio: Optional[float] = None,
        previous_variable_share_ratio: Optional[float] = None,
        is_reduced_price_dwelling: bool = False,
        appraised_value_nis: Optional[float] = None,
        borrower_rent_expense: float = 0.0,
    ) -> MortgageEligibilityResult:
        """Evaluate mortgage eligibility against Directive 329 red lines."""

        risk_pti_limit = cls.RISK_PROFILE_PTI_LIMITS.get(
            risk_profile, boi_limits.PTI_REGULATORY_LIMIT
        )
        pti_cap = min(risk_pti_limit, boi_limits.PTI_REGULATORY_LIMIT)

        rent_deduction = (
            borrower_rent_expense
            if boi_limits.PTI_OCCUPANCY_RENT_DEDUCTION.get(occupancy, False)
            else 0.0
        )
        disposable_income = max(monthly_net_income - rent_deduction, 0.0)
        other_housing = max(other_housing_payments, 0.0)
        existing_obligations = max(existing_loans_payment, 0.0) + other_housing

        max_monthly_payment = max(
            disposable_income * pti_cap - existing_obligations, 0.0
        )

        ltv_limit = cls._resolve_ltv_limit(property_type, deal_type)
        ltv_value_basis = cls._buyer_price_value_basis(
            purchase_price=property_price,
            is_reduced_price_dwelling=is_reduced_price_dwelling,
            appraised_value_nis=appraised_value_nis,
        )
        ltv_value_basis = max(ltv_value_basis, 0.0)

        actual_loan_amount = max(property_price - max(down_payment_available, 0.0), 0.0)
        max_loan_by_ltv = ltv_value_basis * ltv_limit

        monthly_rate = cls.DEFAULT_INTEREST_RATE_ANNUAL / 12
        months = max(loan_term_years, 1) * 12

        if (
            monthly_payment_override is not None
            and monthly_payment_override > 1e-6
            and actual_loan_amount > 0
        ):
            max_loan_by_payment = (
                actual_loan_amount * max_monthly_payment / monthly_payment_override
            )
        else:
            if monthly_rate > 0:
                annuity_factor = (1 - (1 + monthly_rate) ** -months) / monthly_rate
                max_loan_by_payment = max_monthly_payment * annuity_factor
            else:
                max_loan_by_payment = max_monthly_payment * months

        max_loan_amount = min(max_loan_by_payment, max_loan_by_ltv)
        required_down_payment = max(property_price - max_loan_amount, 0.0)

        actual_monthly_payment = (
            max(monthly_payment_override, 0.0)
            if monthly_payment_override is not None
            else cls._calculate_monthly_payment(
                actual_loan_amount, monthly_rate, months
            )
        )
        peak_payment = (
            max(peak_payment_override, actual_monthly_payment)
            if peak_payment_override is not None
            else actual_monthly_payment
        )

        income_floor = max(disposable_income, 1.0)
        actual_pti = (actual_monthly_payment + existing_obligations) / income_floor
        peak_pti = (peak_payment + existing_obligations) / income_floor
        actual_ltv = (
            (actual_loan_amount / ltv_value_basis) if ltv_value_basis > 0 else 0.0
        )

        violations: List[str] = []
        warnings: List[str] = []
        applied_exceptions: List[str] = []

        if down_payment_available + 1e-6 < required_down_payment:
            shortfall = required_down_payment - down_payment_available
            violations.append(
                f"חסר הון עצמי של כ-{shortfall:,.0f} ₪ כדי לעמוד בגובה המימון המותר."
            )

        if actual_pti > pti_cap + 1e-6:
            violations.append(
                f"ההחזר החודשי ({actual_monthly_payment:,.0f} ₪) מעלה את יחס ההחזר ל-{actual_pti:.1%}, מעבר לתקרת {pti_cap:.0%} המותרת."
            )
        elif actual_pti > boi_limits.PTI_WARNING_THRESHOLD + 1e-6:
            warnings.append(
                f"יחס ההחזר {actual_pti:.1%} גבוה מ-40%, ולכן הבנק יסווג את ההלוואה כבעלת סיכון מוגבר."
            )

        if actual_ltv > ltv_limit + 1e-6:
            violations.append(
                f"שיעור המימון {actual_ltv:.0%} גבוה מהמותר ({ltv_limit:.0%}) עבור סוג העסקה."
            )

        # Variable share cap (Directive 329 §7, §12 exceptions)
        variable_share = (
            variable_share_ratio if variable_share_ratio is not None else 0.0
        )
        variable_cap = boi_limits.VARIABLE_SHARE_LIMIT
        variable_within_limit = variable_share <= variable_cap + 1e-6

        if not variable_within_limit:
            exception_applied = False
            if is_bridge_loan and bridge_term_months is not None:
                if (
                    bridge_term_months
                    <= boi_limits.VARIABLE_SHARE_EXCEPTIONS.max_bridge_term_months
                ):
                    exception_applied = True
                    applied_exceptions.append("bridge_loan_exception_under_36_months")
            if (
                not exception_applied
                and any_purpose_amount_nis is not None
                and any_purpose_amount_nis
                <= boi_limits.VARIABLE_SHARE_EXCEPTIONS.any_purpose_amount_nis + 1e-6
            ):
                exception_applied = True
                applied_exceptions.append("any_purpose_loan_exception_under_120k_nis")

            if not exception_applied:
                violations.append(
                    f"החשיפה לריבית משתנה ({variable_share * 100:.1f}%) חורגת מן התקרה ‎{variable_cap * 100:.0f}%."
                )

        # Term ceiling
        if loan_term_years > boi_limits.MAX_TERM_YEARS:
            violations.append(
                f"תקופת ההלוואה המבוקשת ({loan_term_years} שנים) חורגת מהמקסימום ‎{boi_limits.MAX_TERM_YEARS} שנים."
            )

        # Refinance may not worsen ratios (§329 §9)
        if is_refinance:
            if (
                previous_pti_ratio is not None
                and actual_pti > previous_pti_ratio + 1e-6
            ):
                violations.append(
                    "מיחזור ההלוואה מגדיל את יחס ההחזר ביחס להלוואה הקיימת (329 §9)."
                )
            if (
                previous_ltv_ratio is not None
                and actual_ltv > previous_ltv_ratio + 1e-6
            ):
                violations.append(
                    "מיחזור ההלוואה מגדיל את שיעור המימון ביחס להלוואה הקיימת (329 §9)."
                )
            if (
                previous_variable_share_ratio is not None
                and variable_share > previous_variable_share_ratio + 1e-6
            ):
                violations.append(
                    "מיחזור ההלוואה מגדיל את רכיב הריבית המשתנה ביחס לקיים (329 §9)."
                )

        notes: List[str] = []
        notes.extend(violations)
        notes.extend(warnings)
        if not violations and not warnings:
            notes.append("הבקשה עומדת במגבלות הרגולטוריות הידועות.")

        is_eligible = not violations

        return MortgageEligibilityResult(
            max_loan_amount=max_loan_amount,
            monthly_payment_capacity=max_monthly_payment,
            required_down_payment=required_down_payment,
            debt_to_income_ratio=actual_pti,
            loan_to_value_ratio=actual_ltv,
            total_property_price=property_price,
            is_eligible=is_eligible,
            eligibility_notes=" | ".join(notes),
            assessed_monthly_payment=actual_monthly_payment,
            pti_limit_applied=pti_cap,
            peak_debt_to_income_ratio=peak_pti,
            ltv_value_basis=ltv_value_basis,
            violations=violations,
            warnings=warnings,
            applied_exceptions=applied_exceptions,
        )

    @classmethod
    def adjustments_to_qualify(
        cls,
        *,
        monthly_net_income: float,
        property_price: float,
        down_payment_available: float,
        property_type: PropertyType = PropertyType.SINGLE,
        deal_type: DealType = DealType.FIRST_HOME,
        existing_loans_payment: float = 0.0,
        other_housing_payments: float = 0.0,
    ) -> Dict[str, float]:
        """Suggest minimum adjustments to reach compliance (heuristic)."""

        scenarios: Dict[str, float] = {}

        for price_reduction in [0, 50_000, 100_000, 200_000, 300_000]:
            adjusted_price = property_price - price_reduction
            if adjusted_price <= 0:
                continue

            calc = cls.evaluate(
                monthly_net_income=monthly_net_income,
                property_price=adjusted_price,
                down_payment_available=down_payment_available,
                property_type=property_type,
                deal_type=deal_type,
                existing_loans_payment=existing_loans_payment,
                other_housing_payments=other_housing_payments,
            )

            if calc.is_eligible:
                scenarios["reduce_price"] = adjusted_price
                break

        calc = cls.evaluate(
            monthly_net_income=monthly_net_income,
            property_price=property_price,
            down_payment_available=down_payment_available,
            property_type=property_type,
            deal_type=deal_type,
            existing_loans_payment=existing_loans_payment,
            other_housing_payments=other_housing_payments,
        )
        scenarios["required_down_payment"] = calc.required_down_payment

        for income_increase in range(0, 20_000, 1_000):
            adjusted_income = monthly_net_income + income_increase
            calc = cls.evaluate(
                monthly_net_income=adjusted_income,
                property_price=property_price,
                down_payment_available=down_payment_available,
                property_type=property_type,
                deal_type=deal_type,
                existing_loans_payment=existing_loans_payment,
                other_housing_payments=other_housing_payments,
            )

            if calc.is_eligible:
                scenarios["required_income"] = adjusted_income
                break

        return scenarios
