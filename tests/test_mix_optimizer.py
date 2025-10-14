import pytest

from app.services.mix_optimizer import optimize_mixes
from app.services.planning_mapper import build_planning_context
from tests.factories import build_submission


def test_optimize_mixes_creates_candidates():
    submission = build_submission()
    planning = build_planning_context(submission)

    result = optimize_mixes(submission.record, planning)

    assert result.candidates
    assert result.recommended_index < len(result.candidates)

    recommended = result.candidates[result.recommended_index]
    metrics = recommended.metrics
    assert metrics.pti_ratio_peak >= metrics.pti_ratio
    assert metrics.variable_share_pct >= 0
    assert metrics.track_details


@pytest.mark.parametrize("basket_index", [0, 1, 2])
def test_uniform_baskets_present(basket_index: int):
    submission = build_submission()
    planning = build_planning_context(submission)
    result = optimize_mixes(submission.record, planning)

    candidate = result.candidates[basket_index]
    assert candidate.label.startswith("Uniform Basket")
    assert candidate.metrics.average_rate_pct > 0
    assert candidate.metrics.pti_ratio_peak >= candidate.metrics.pti_ratio
    assert candidate.metrics.track_details
