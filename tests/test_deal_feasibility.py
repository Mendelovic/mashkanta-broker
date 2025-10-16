import pytest

from app.services.deal_feasibility import run_feasibility_checks
from app.domain.schemas import FeasibilityResult


def test_run_feasibility_passes_for_reasonable_case():
    result = run_feasibility_checks(
        property_price=1_200_000,
        down_payment_available=400_000,
        monthly_net_income=20_000,
        existing_monthly_loans=0,
        loan_years=25,
        property_type="single",
    )

    assert isinstance(result, FeasibilityResult)
    assert result.is_feasible
    assert not result.issues
    assert result.loan_term_limit_years == 30
    assert pytest.approx(result.variable_share_limit_pct, rel=1e-6) == 66.66666666666666


def test_run_feasibility_flags_high_ltv():
    result = run_feasibility_checks(
        property_price=1_000_000,
        down_payment_available=100_000,
        monthly_net_income=20_000,
        existing_monthly_loans=0,
        loan_years=25,
        property_type="single",
    )

    assert not result.is_feasible
    assert any(issue.code == "ltv_exceeds_limit" for issue in result.issues)


def test_run_feasibility_flags_high_pti():
    result = run_feasibility_checks(
        property_price=1_000_000,
        down_payment_available=500_000,
        monthly_net_income=6_000,
        existing_monthly_loans=1_500,
        loan_years=25,
        property_type="single",
    )

    assert not result.is_feasible
    assert any(issue.code == "pti_exceeds_limit" for issue in result.issues)


def test_run_feasibility_warns_on_age_term_conflict():
    result = run_feasibility_checks(
        property_price=1_500_000,
        down_payment_available=600_000,
        monthly_net_income=25_000,
        existing_monthly_loans=0,
        loan_years=30,
        property_type="single",
        borrower_age_years=60,
    )

    assert any(issue.code == "age_term_beyond_retirement" for issue in result.issues)


def test_ltv_limit_respects_deal_type_over_property_type():
    result = run_feasibility_checks(
        property_price=1_200_000,
        down_payment_available=300_000,
        monthly_net_income=22_000,
        existing_monthly_loans=0,
        loan_years=25,
        property_type="investment",
        deal_type="first_home",
        occupancy="own",
    )

    assert result.ltv_limit == pytest.approx(0.75)
    assert result.is_feasible


def test_pti_ratio_uses_assessed_payment_override():
    result = run_feasibility_checks(
        property_price=1_100_000,
        down_payment_available=400_000,
        monthly_net_income=15_000,
        existing_monthly_loans=0,
        loan_years=25,
        property_type="single",
        assessed_payment=5_000,
    )

    assert result.pti_ratio == pytest.approx(5_000 / 15_000)


def test_run_feasibility_flags_variable_share_limit():
    result = run_feasibility_checks(
        property_price=1_200_000,
        down_payment_available=400_000,
        monthly_net_income=20_000,
        existing_monthly_loans=0,
        loan_years=25,
        property_type="single",
        variable_share=0.7,
    )

    assert any(issue.code == "variable_share_exceeds_limit" for issue in result.issues)
    assert result.variable_share_pct == pytest.approx(70.0)


def test_run_feasibility_flags_term_limit():
    result = run_feasibility_checks(
        property_price=1_200_000,
        down_payment_available=400_000,
        monthly_net_income=20_000,
        existing_monthly_loans=0,
        loan_years=32,
        property_type="single",
    )

    assert any(issue.code == "loan_term_exceeds_limit" for issue in result.issues)
    assert result.loan_term_years == 32
