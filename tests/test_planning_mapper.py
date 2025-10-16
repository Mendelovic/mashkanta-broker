import pytest

from app.domain.schemas import PlanningContext
from app.services.planning_mapper import build_planning_context
from tests.factories import build_submission


def test_build_planning_context_creates_expected_weights():
    submission = build_submission()
    context = build_planning_context(submission)

    assert isinstance(context, PlanningContext)
    total_weight = (
        context.weights.payment_volatility
        + context.weights.cpi_exposure
        + context.weights.prepay_fee_exposure
    )
    assert pytest.approx(total_weight, rel=1e-6) == 1.0
    assert pytest.approx(context.weights.payment_volatility, rel=1e-6) == pytest.approx(
        0.2666666667, rel=1e-6
    )
    assert pytest.approx(context.weights.cpi_exposure, rel=1e-6) == pytest.approx(
        0.4, rel=1e-6
    )
    assert pytest.approx(
        context.weights.prepay_fee_exposure, rel=1e-6
    ) == pytest.approx(0.3333333333, rel=1e-6)
    assert pytest.approx(context.soft_caps.variable_share_max, rel=1e-6) == 0.6
    assert pytest.approx(context.soft_caps.cpi_share_max, rel=1e-6) == 0.6
    assert context.soft_caps.payment_ceiling_nis == 7_500
    assert len(context.income_timeline) == 60
    assert len(context.pti_targets) == 60
    assert context.metadata["horizon_months"] == 60
    assert (
        pytest.approx(
            context.metadata["assumptions"]["soft_caps"]["variable_share_max"], rel=1e-6
        )
        == 0.6
    )
    assert (
        pytest.approx(
            context.metadata["assumptions"]["soft_caps"]["cpi_share_max"], rel=1e-6
        )
        == 0.6
    )
    assert context.metadata["assumptions"]["soft_caps"]["payment_ceiling_nis"] == 7_500


def test_build_planning_context_respects_prepayment_settings():
    submission = build_submission()
    submission.record.preferences.expected_prepay_pct = 0.2
    submission.record.preferences.expected_prepay_month = 24
    submission.record.preferences.prepayment_confirmed = True

    context = build_planning_context(submission)

    assert context.prepayment_schedule
    event = context.prepayment_schedule[0]
    assert event.month == 24
    assert pytest.approx(event.pct_of_balance, rel=1e-5) == 0.2


def test_build_planning_context_adjusts_for_future_plans():
    submission = build_submission()
    context = build_planning_context(submission)

    start_month = submission.record.future_plans[0].timeframe_months or 0
    before = (
        context.income_timeline[start_month - 1]
        if start_month > 0
        else context.income_timeline[0]
    )
    after = context.income_timeline[start_month]

    assert after < before


def test_cpi_soft_cap_omitted_when_no_preference():
    submission = build_submission()
    submission.record.preferences.cpi_tolerance = None
    context = build_planning_context(submission)

    assert context.soft_caps.cpi_share_max is None
    assert context.metadata["assumptions"]["soft_caps"]["cpi_share_max"] is None


def test_cpi_soft_cap_removed_for_high_tolerance():
    submission = build_submission()
    submission.record.preferences.cpi_tolerance = 0
    context = build_planning_context(submission)

    assert context.soft_caps.cpi_share_max is None
    assert context.metadata["assumptions"]["soft_caps"]["cpi_share_max"] is None
