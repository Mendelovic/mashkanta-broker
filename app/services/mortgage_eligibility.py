"""
Israeli mortgage eligibility evaluation helpers (demo).

Provides indicative eligibility checks with simplified Israeli banking rules.
For production accuracy, tie in live market data and full regulatory logic
(income types, credit history, guarantors, age caps, etc.).
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional


class PropertyType(Enum):
    """Property purchase type."""

    FIRST_HOME = "דירה ראשונה"
    UPGRADE = "שיפור דיור"
    INVESTMENT = "השקעה"


class RiskProfile(Enum):
    """Loan risk profile."""

    CONSERVATIVE = "שמרני"
    STANDARD = "סטנדרטי"
    AGGRESSIVE = "אגרסיבי"


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
    pti_limit_applied: float = 0.5


class MortgageEligibilityEvaluator:
    """
    Israeli mortgage eligibility evaluator based on banking regulations.

    Key Rules:
    - PTI (Payment to Income): Max 50% of disposable income for mortgage payments
    - LTV (Loan to Value): Max 75% for first home, 70% for upgrade, 50% for investment
    - Minimum income requirements
    """

    PTI_REGULATORY_LIMIT: float = 0.50

    PTI_LIMITS = {
        RiskProfile.CONSERVATIVE: 0.35,
        RiskProfile.STANDARD: 0.50,
        RiskProfile.AGGRESSIVE: 0.50,
    }

    LTV_LIMITS = {
        PropertyType.FIRST_HOME: 0.75,
        PropertyType.UPGRADE: 0.70,
        PropertyType.INVESTMENT: 0.50,
    }

    @classmethod
    # TODO: Replace static interest rate with data-driven calculations.
    # TODO: Bring in full Israeli underwriting rules (credit history, age limits, employment types).
    def evaluate(
        cls,
        monthly_net_income: float,
        property_price: float,
        down_payment_available: float,
        property_type: PropertyType = PropertyType.FIRST_HOME,
        risk_profile: RiskProfile = RiskProfile.STANDARD,
        existing_loans_payment: float = 0.0,
        years: int = 25,
        monthly_payment_override: Optional[float] = None,
    ) -> MortgageEligibilityResult:
        """Evaluate mortgage eligibility based on Israeli standards."""

        pti_cap = min(cls.PTI_LIMITS[risk_profile], cls.PTI_REGULATORY_LIMIT)
        max_monthly_payment = max(
            (monthly_net_income * pti_cap) - existing_loans_payment,
            0.0,
        )

        ltv_limit = cls.LTV_LIMITS[property_type]
        max_loan_by_ltv = property_price * ltv_limit
        actual_loan_amount = max(property_price - max(down_payment_available, 0.0), 0.0)

        avg_interest_rate = 0.04 / 12
        months = max(years, 1) * 12

        if (
            monthly_payment_override is not None
            and monthly_payment_override > 1e-6
            and actual_loan_amount > 0
        ):
            max_loan_by_payment = (
                actual_loan_amount * max_monthly_payment / monthly_payment_override
            )
        else:
            if avg_interest_rate > 0:
                annuity_factor = (
                    1 - (1 + avg_interest_rate) ** -months
                ) / avg_interest_rate
                max_loan_by_payment = max_monthly_payment * annuity_factor
            else:
                max_loan_by_payment = max_monthly_payment * months

        max_loan_amount = min(max_loan_by_payment, max_loan_by_ltv)

        required_down_payment = max(property_price - max_loan_amount, 0.0)
        is_eligible = down_payment_available >= required_down_payment

        if monthly_payment_override is not None:
            actual_monthly_payment = max(monthly_payment_override, 0.0)
        else:
            actual_monthly_payment = cls._calculate_monthly_payment(
                actual_loan_amount,
                avg_interest_rate,
                months,
            )

        disposable_income = max(monthly_net_income, 1.0)
        actual_pti = (
            actual_monthly_payment + max(existing_loans_payment, 0.0)
        ) / disposable_income
        actual_ltv = (
            (actual_loan_amount / property_price) if property_price > 0 else 0.0
        )

        notes: list[str] = []
        if not is_eligible:
            shortfall = required_down_payment - down_payment_available
            if shortfall > 0:
                notes.append(f"נדרש להוסיף הון עצמי נוסף של {shortfall:,.0f} ₪")
        if actual_pti > pti_cap:
            notes.append(
                f"תשלום חודשי של {actual_monthly_payment:,.0f} ₪ יוצר יחס החזר של {actual_pti:.1%}, גבוה מהמגבלה ({pti_cap:.0%})."
            )
        elif actual_pti > 0.40:
            notes.append(
                f"יחס ההחזר החודשי צפוי להיות {actual_pti:.1%}; שקלו כרית ביטחון או קיצור תקופת ההלוואה."
            )

        if actual_ltv > ltv_limit:
            notes.append(
                f"חלק המימון ({actual_ltv:.0%}) חורג מהמגבלה ({ltv_limit:.0%})."
            )

        if is_eligible and not notes:
            notes.append("הלקוח תואם את דרישות בנק ישראל לעומס החזר וליחס מימון.")

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
        )

    @staticmethod
    def _calculate_monthly_payment(
        loan_amount: float, monthly_rate: float, months: int
    ) -> float:
        """Calculate monthly payment using mortgage formula."""
        if months <= 0:
            return 0.0
        if monthly_rate > 0:
            factor = (
                monthly_rate
                * (1 + monthly_rate) ** months
                / ((1 + monthly_rate) ** months - 1)
            )
            return loan_amount * factor
        return loan_amount / months

    @classmethod
    def adjustments_to_qualify(
        cls,
        monthly_net_income: float,
        property_price: float,
        down_payment_available: float,
        property_type: PropertyType = PropertyType.FIRST_HOME,
        existing_loans_payment: float = 0.0,
    ) -> Dict[str, float]:
        """Calculate the adjustments required to turn an ineligible case into an eligible one."""

        scenarios: Dict[str, float] = {}

        for price_reduction in [0, 50_000, 100_000, 200_000, 300_000]:
            adjusted_price = property_price - price_reduction
            if adjusted_price <= 0:
                continue

            calc = cls.evaluate(
                monthly_net_income,
                adjusted_price,
                down_payment_available,
                property_type,
                RiskProfile.STANDARD,
                existing_loans_payment,
            )

            if calc.is_eligible:
                scenarios["reduce_price"] = adjusted_price
                break

        calc = cls.evaluate(
            monthly_net_income,
            property_price,
            down_payment_available,
            property_type,
            RiskProfile.STANDARD,
            existing_loans_payment,
        )
        scenarios["required_down_payment"] = calc.required_down_payment

        for income_increase in range(0, 20_000, 1_000):
            adjusted_income = monthly_net_income + income_increase
            calc = cls.evaluate(
                adjusted_income,
                property_price,
                down_payment_available,
                property_type,
                RiskProfile.STANDARD,
                existing_loans_payment,
            )

            if calc.is_eligible:
                scenarios["required_income"] = adjusted_income
                break

        return scenarios
