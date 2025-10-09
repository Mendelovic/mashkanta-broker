"""
Israeli mortgage eligibility evaluation helpers (demo).

Provides indicative eligibility checks with simplified Israeli banking rules.
For production accuracy, tie in live market data and full regulatory logic
(income types, credit history, guarantors, age caps, etc.).
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict


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


class MortgageEligibilityEvaluator:
    """
    Israeli mortgage eligibility evaluator based on banking regulations.

    Key Rules:
    - DTI (Debt to Income): Max 30-40% of net income for mortgage payments
    - LTV (Loan to Value): Max 75% for first home, 50-70% for investment
    - Minimum income requirements
    """

    # Israeli banking standard limits
    DTI_LIMITS = {
        RiskProfile.CONSERVATIVE: 0.30,  # 30% of net income
        RiskProfile.STANDARD: 0.35,      # 35% of net income
        RiskProfile.AGGRESSIVE: 0.40,    # 40% of net income
    }

    LTV_LIMITS = {
        PropertyType.FIRST_HOME: 0.75,   # 75% financing
        PropertyType.UPGRADE: 0.70,      # 70% financing
        PropertyType.INVESTMENT: 0.50,   # 50% financing
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
        existing_loans_payment: float = 0,
        years: int = 25,
    ) -> MortgageEligibilityResult:
        """Evaluate mortgage eligibility based on Israeli standards."""

        dti_limit = cls.DTI_LIMITS[risk_profile]
        max_monthly_payment = (monthly_net_income * dti_limit) - existing_loans_payment

        ltv_limit = cls.LTV_LIMITS[property_type]
        max_loan_by_ltv = property_price * ltv_limit

        avg_interest_rate = 0.04 / 12
        months = years * 12

        if avg_interest_rate > 0:
            max_loan_by_payment = max_monthly_payment * (
                (1 - (1 + avg_interest_rate) ** -months) / avg_interest_rate
            )
        else:
            max_loan_by_payment = max_monthly_payment * months

        max_loan_amount = min(max_loan_by_payment, max_loan_by_ltv)

        required_down_payment = property_price - max_loan_amount
        is_eligible = down_payment_available >= required_down_payment

        actual_loan_amount = property_price - down_payment_available
        actual_monthly_payment = cls._calculate_monthly_payment(
            actual_loan_amount, avg_interest_rate, months
        )
        actual_dti = (
            (actual_monthly_payment + existing_loans_payment) / monthly_net_income
            if monthly_net_income > 0
            else 0.0
        )
        actual_ltv = actual_loan_amount / property_price if property_price > 0 else 0.0

        notes: list[str] = []
        if not is_eligible:
            shortfall = required_down_payment - down_payment_available
            if shortfall > 0:
                notes.append(f"נדרש {shortfall:,.0f} ₪ הון עצמי נוסף")

        if actual_dti > dti_limit:
            notes.append(
                f"יחס ההחזר החודשי ({actual_dti:.1%}) גבוה מהמגבלה ({dti_limit:.0%})"
            )

        if actual_ltv > ltv_limit:
            notes.append(
                f"יחס המימון ({actual_ltv:.0%}) גבוה מהמגבלה ({ltv_limit:.0%})"
            )

        if is_eligible and not notes:
            notes.append("הלקוח עומד בדרישות הבנק")

        return MortgageEligibilityResult(
            max_loan_amount=max_loan_amount,
            monthly_payment_capacity=max_monthly_payment,
            required_down_payment=required_down_payment,
            debt_to_income_ratio=actual_dti,
            loan_to_value_ratio=actual_ltv,
            total_property_price=property_price,
            is_eligible=is_eligible,
            eligibility_notes=" | ".join(notes),
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
        existing_loans_payment: float = 0,
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
