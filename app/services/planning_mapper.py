"""Mapping utilities for converting intake data into planning contexts."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List

from app.domain.schemas import (
    FuturePlan,
    IntakeSubmission,
    PlanningContext,
    PreferenceWeights,
    PrepaymentEvent,
    ScenarioWeights,
    SoftCaps,
)

HORIZON_MONTHS = 60


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


def _compute_weights(submission: IntakeSubmission) -> PreferenceWeights:
    prefs = submission.record.preferences

    stability_weight = _clamp(prefs.stability_vs_cost / 10.0)
    cpi_slider = prefs.cpi_tolerance if prefs.cpi_tolerance is not None else 5
    prime_slider = (
        prefs.prime_exposure_preference
        if prefs.prime_exposure_preference is not None
        else 5
    )
    cpi_weight = _clamp(cpi_slider / 10.0)
    prepay_weight = _clamp((10 - prime_slider) / 10.0)

    total = stability_weight + cpi_weight + prepay_weight
    if total <= 1e-6:
        stability_weight = cpi_weight = prepay_weight = 1.0 / 3.0
    else:
        stability_weight /= total
        cpi_weight /= total
        prepay_weight /= total

    return PreferenceWeights(
        payment_volatility=stability_weight,
        cpi_exposure=cpi_weight,
        prepay_fee_exposure=prepay_weight,
    )


def _compute_soft_caps(submission: IntakeSubmission) -> SoftCaps:
    prefs = submission.record.preferences

    variable_cap = _clamp(1.0 - prefs.stability_vs_cost / 10.0, 0.3, 0.66)
    if prefs.cpi_tolerance is None:
        cpi_cap = None
    elif prefs.cpi_tolerance <= 2:
        cpi_cap = None
    elif prefs.cpi_tolerance >= 7:
        cpi_cap = None
    else:
        normalized = _clamp(prefs.cpi_tolerance / 10.0, 0.2, 1.0)
        cpi_cap = normalized

    payment_ceiling = prefs.red_line_payment_nis if prefs.red_line_payment_nis else None

    return SoftCaps(
        variable_share_max=variable_cap,
        cpi_share_max=cpi_cap,
        payment_ceiling_nis=payment_ceiling,
    )


def _compute_scenario_weights(rate_view) -> ScenarioWeights:
    base = ScenarioWeights(fall=0.2, flat=0.6, rise=0.2)
    if rate_view == "fall":
        return ScenarioWeights(fall=0.5, flat=0.3, rise=0.2)
    if rate_view == "rise":
        return ScenarioWeights(fall=0.2, flat=0.3, rise=0.5)
    return base


def _baseline_income(submission: IntakeSubmission) -> float:
    borrower = submission.record.borrower
    return borrower.net_income_nis + borrower.additional_income_nis


def _baseline_expense(submission: IntakeSubmission) -> float:
    borrower = submission.record.borrower
    return borrower.fixed_expenses_nis


def _apply_future_plans(
    submission: IntakeSubmission,
    income_timeline: List[float],
    expense_timeline: List[float],
) -> None:
    plans: List[FuturePlan] = submission.record.future_plans or []
    for plan in plans:
        if plan.timeframe_months is None:
            continue
        start = min(max(plan.timeframe_months, 0), HORIZON_MONTHS - 1)
        confidence = plan.confidence if plan.confidence is not None else 1.0
        delta = (plan.expected_income_delta_nis or 0.0) * confidence
        for month in range(start, HORIZON_MONTHS):
            income_timeline[month] += delta
        # heuristic: family/education events increase expenses slightly
        if plan.category in {"family", "education"} and delta < 0:
            extra_expense = abs(delta) * 0.25
            for month in range(start, HORIZON_MONTHS):
                expense_timeline[month] += extra_expense


def _build_prepayment_schedule(submission: IntakeSubmission) -> List[PrepaymentEvent]:
    prefs = submission.record.preferences
    schedule: List[PrepaymentEvent] = []
    if (
        prefs.prepayment_confirmed
        and prefs.expected_prepay_pct > 0
        and prefs.expected_prepay_month
    ):
        schedule.append(
            PrepaymentEvent(
                month=prefs.expected_prepay_month,
                pct_of_balance=_clamp(prefs.expected_prepay_pct, 0.0, 1.0),
                notes="Expected borrower prepayment",
            )
        )
    return schedule


def build_planning_context(submission: IntakeSubmission) -> PlanningContext:
    """Convert a confirmed intake submission into a planning context."""

    weights = _compute_weights(submission)
    soft_caps = _compute_soft_caps(submission)
    scenario_weights = _compute_scenario_weights(
        submission.record.preferences.rate_view.value
    )

    baseline_income = max(_baseline_income(submission), 0.0)
    baseline_expense = _baseline_expense(submission)

    income_timeline = [baseline_income for _ in range(HORIZON_MONTHS)]
    expense_timeline = [baseline_expense for _ in range(HORIZON_MONTHS)]
    _apply_future_plans(submission, income_timeline, expense_timeline)

    payment_ceiling = soft_caps.payment_ceiling_nis
    pti_targets: List[float] = []
    for month in range(HORIZON_MONTHS):
        income = max(income_timeline[month], 1.0)
        if payment_ceiling:
            pti_targets.append(_clamp(payment_ceiling / income, 0.0, 1.0))
        else:
            pti_targets.append(0.5)

    metadata = {
        "horizon_months": HORIZON_MONTHS,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "assumptions": {
            "baseline_income": baseline_income,
            "baseline_expense": baseline_expense,
            "soft_caps": {
                "variable_share_max": soft_caps.variable_share_max,
                "cpi_share_max": soft_caps.cpi_share_max,
                "payment_ceiling_nis": soft_caps.payment_ceiling_nis,
            },
        },
    }

    return PlanningContext(
        weights=weights,
        soft_caps=soft_caps,
        scenario_weights=scenario_weights,
        prepayment_schedule=_build_prepayment_schedule(submission),
        income_timeline=income_timeline,
        expense_timeline=expense_timeline,
        pti_targets=pti_targets,
        metadata=metadata,
    )
