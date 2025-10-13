import json

import pytest

from app.domain.schemas import PlanningContext
from app.services.planning_mapper import build_planning_context
from tests.factories import build_submission


def test_build_planning_context_creates_expected_weights():
    submission = build_submission()
    context = build_planning_context(submission)

    assert isinstance(context, PlanningContext)
    assert 0.0 <= context.weights.payment_volatility <= 1.0
    assert context.soft_caps.variable_share_max <= 0.66
    assert len(context.income_timeline) == 60
    assert len(context.pti_targets) == 60
    assert context.metadata["horizon_months"] == 60


def test_build_planning_context_respects_prepayment_settings():
    submission = build_submission()
    submission.record.preferences.expected_prepay_pct = 0.2
    submission.record.preferences.expected_prepay_month = 24

    context = build_planning_context(submission)

    assert context.prepayment_schedule
    event = context.prepayment_schedule[0]
    assert event.month == 24
    assert pytest.approx(event.pct_of_balance, rel=1e-5) == 0.2


def test_build_planning_context_adjusts_for_future_plans():
    submission = build_submission()
    context = build_planning_context(submission)

    start_month = submission.record.future_plans[0].timeframe_months or 0
    before = context.income_timeline[start_month - 1] if start_month > 0 else context.income_timeline[0]
    after = context.income_timeline[start_month]

    assert after < before
