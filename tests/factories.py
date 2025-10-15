from __future__ import annotations

from app.domain.schemas import (
    BorrowerProfile,
    DealType,
    FuturePlan,
    IntakeSubmission,
    InterviewRecord,
    LoanAsk,
    Preferences,
    PreferenceSignal,
    PropertyDetails,
    Quotes,
    QuoteTrack,
    RateAnchor,
    RateView,
    ResidencyStatus,
    OccupancyIntent,
    PropertyType,
)


def build_submission() -> IntakeSubmission:
    borrower = BorrowerProfile(
        primary_applicant_name="דן",
        residency=ResidencyStatus.RESIDENT,
        occupancy=OccupancyIntent.OWN,
        net_income_nis=18_000,
        fixed_expenses_nis=2_000,
        additional_income_nis=1_500,
        employment_status="מועסק קבוע",
        employment_tenure_months=60,
        has_recent_credit_issues=False,
        age_years=34,
        dependents=0,
        income_volatility_factor=0.2,
        notes="שכר יציב בעבודה הייטק",
    )

    property_details = PropertyDetails(
        type=PropertyType.SINGLE,
        value_nis=1_800_000,
        address_city="תל אביב",
        address_region="מרכז",
        is_new_build=False,
        target_close_months=6,
    )

    loan = LoanAsk(
        amount_nis=1_200_000,
        term_years=25,
        currency="NIS",
    )

    preferences = Preferences(
        stability_vs_cost=4,
        cpi_tolerance=6,
        prime_exposure_preference=5,
        max_payment_nis=6_500,
        red_line_payment_nis=7_500,
        expected_prepay_pct=0.15,
        expected_prepay_month=18,
        rate_view=RateView.FLAT,
        additional_signals=[
            PreferenceSignal(
                name="flexibility",
                score=8,
                rationale="מבקש אופציה למחזר במקרה של ירידת ריבית",
            )
        ],
    )

    plans = [
        FuturePlan(
            category="family",
            timeframe_months=24,
            expected_income_delta_nis=-2_000,
            confidence=0.7,
            notes="מתכננים הרחבת משפחה בשנתיים הקרובות",
        )
    ]

    quotes = Quotes(
        tracks=[
            QuoteTrack(
                track="variable_prime",
                rate_anchor=RateAnchor.PRIME,
                margin_pct=-0.4,
                bank_name="Bank Leumi",
            )
        ]
    )

    record = InterviewRecord(
        borrower=borrower,
        property=property_details,
        deal_type=DealType.FIRST_HOME,
        loan=loan,
        preferences=preferences,
        future_plans=plans,
        quotes=quotes,
        interview_summary="הלקוח אישר את הנתונים והבין את השלבים הבאים.",
    )

    return IntakeSubmission(
        record=record,
        confirmation_notes=["הלקוח אישר את הסיכום."],
    )
