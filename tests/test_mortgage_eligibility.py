import pytest

from app.domain.schemas import (
    DealType,
    OccupancyIntent,
    PropertyType,
)
from app.services.mortgage_eligibility import MortgageEligibilityEvaluator, RiskProfile


def test_pti_rent_expense_reduces_capacity():
    result = MortgageEligibilityEvaluator.evaluate(
        monthly_net_income=10_000,
        property_price=1_000_000,
        down_payment_available=500_000,
        property_type=PropertyType.INVESTMENT,
        deal_type=DealType.INVESTMENT,
        occupancy=OccupancyIntent.RENT,
        risk_profile=RiskProfile.STANDARD,
        monthly_payment_override=3_000,
        loan_term_years=25,
        borrower_rent_expense=2_000,
    )

    assert result.violations
    assert any("ההחזר החודשי" in violation for violation in result.violations)

    baseline = MortgageEligibilityEvaluator.evaluate(
        monthly_net_income=10_000,
        property_price=1_000_000,
        down_payment_available=500_000,
        property_type=PropertyType.INVESTMENT,
        deal_type=DealType.INVESTMENT,
        occupancy=OccupancyIntent.RENT,
        risk_profile=RiskProfile.STANDARD,
        monthly_payment_override=3_000,
        loan_term_years=25,
        borrower_rent_expense=0.0,
    )

    assert not baseline.violations


def test_other_housing_payments_included_in_pti():
    result = MortgageEligibilityEvaluator.evaluate(
        monthly_net_income=15_000,
        property_price=1_000_000,
        down_payment_available=300_000,
        property_type=PropertyType.SINGLE,
        deal_type=DealType.FIRST_HOME,
        occupancy=OccupancyIntent.OWN,
        risk_profile=RiskProfile.STANDARD,
        monthly_payment_override=4_500,
        loan_term_years=25,
        other_housing_payments=1_500,
    )

    assert result.violations
    assert any("ההחזר החודשי" in violation for violation in result.violations)

    baseline = MortgageEligibilityEvaluator.evaluate(
        monthly_net_income=15_000,
        property_price=1_000_000,
        down_payment_available=300_000,
        property_type=PropertyType.SINGLE,
        deal_type=DealType.FIRST_HOME,
        occupancy=OccupancyIntent.OWN,
        risk_profile=RiskProfile.STANDARD,
        monthly_payment_override=4_500,
        loan_term_years=25,
        other_housing_payments=0.0,
    )

    assert not baseline.violations


def test_bridge_loan_exception_allows_variable_share():
    result = MortgageEligibilityEvaluator.evaluate(
        monthly_net_income=20_000,
        property_price=1_200_000,
        down_payment_available=400_000,
        property_type=PropertyType.SINGLE,
        deal_type=DealType.FIRST_HOME,
        occupancy=OccupancyIntent.OWN,
        risk_profile=RiskProfile.STANDARD,
        monthly_payment_override=4_000,
        loan_term_years=20,
        variable_share_ratio=0.8,
        is_bridge_loan=True,
        bridge_term_months=24,
    )

    assert not result.violations
    assert not any(
        "החשיפה לריבית משתנה" in violation for violation in result.violations
    )
    assert "bridge_loan_exception_under_36_months" in result.applied_exceptions

    baseline = MortgageEligibilityEvaluator.evaluate(
        monthly_net_income=20_000,
        property_price=1_200_000,
        down_payment_available=400_000,
        property_type=PropertyType.SINGLE,
        deal_type=DealType.FIRST_HOME,
        occupancy=OccupancyIntent.OWN,
        risk_profile=RiskProfile.STANDARD,
        monthly_payment_override=4_000,
        loan_term_years=20,
        variable_share_ratio=0.8,
        is_bridge_loan=False,
    )

    assert any("החשיפה לריבית משתנה" in violation for violation in baseline.violations)


def test_any_purpose_exception_allows_variable_share():
    result = MortgageEligibilityEvaluator.evaluate(
        monthly_net_income=18_000,
        property_price=1_100_000,
        down_payment_available=350_000,
        property_type=PropertyType.SINGLE,
        deal_type=DealType.FIRST_HOME,
        occupancy=OccupancyIntent.OWN,
        risk_profile=RiskProfile.STANDARD,
        monthly_payment_override=3_800,
        loan_term_years=25,
        variable_share_ratio=0.8,
        any_purpose_amount_nis=100_000,
    )

    assert not result.violations
    assert not any(
        "החשיפה לריבית משתנה" in violation for violation in result.violations
    )
    assert "any_purpose_loan_exception_under_120k_nis" in result.applied_exceptions


def test_buyer_price_cap_applied_to_ltv_basis():
    result = MortgageEligibilityEvaluator.evaluate(
        monthly_net_income=22_000,
        property_price=1_500_000,
        down_payment_available=300_000,
        property_type=PropertyType.SINGLE,
        deal_type=DealType.FIRST_HOME,
        occupancy=OccupancyIntent.OWN,
        risk_profile=RiskProfile.STANDARD,
        monthly_payment_override=4_000,
        loan_term_years=25,
        is_reduced_price_dwelling=True,
        appraised_value_nis=2_200_000,
    )

    assert result.ltv_value_basis == pytest.approx(1_800_000)


def test_refinance_cannot_worsen_pti():
    result = MortgageEligibilityEvaluator.evaluate(
        monthly_net_income=12_000,
        property_price=900_000,
        down_payment_available=200_000,
        property_type=PropertyType.SINGLE,
        deal_type=DealType.FIRST_HOME,
        occupancy=OccupancyIntent.OWN,
        risk_profile=RiskProfile.STANDARD,
        monthly_payment_override=4_200,
        loan_term_years=25,
        is_refinance=True,
        previous_pti_ratio=0.32,
    )

    assert any("מיחזור" in violation for violation in result.violations)
