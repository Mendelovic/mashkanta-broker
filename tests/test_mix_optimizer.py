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
    assert recommended.feasibility is not None
    assert recommended.feasibility.pti_ratio == pytest.approx(metrics.pti_ratio)
    assert recommended.feasibility.pti_ratio_peak == pytest.approx(
        metrics.pti_ratio_peak
    )


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
    assert candidate.feasibility is not None
    assert candidate.feasibility.pti_ratio == pytest.approx(candidate.metrics.pti_ratio)
    assert candidate.feasibility.pti_ratio_peak == pytest.approx(
        candidate.metrics.pti_ratio_peak
    )


def test_fixed_basket_sensitivity_stays_flat():
    submission = build_submission()
    planning = build_planning_context(submission)
    result = optimize_mixes(submission.record, planning)

    fixed_candidate = result.candidates[0]
    base_payment = fixed_candidate.metrics.monthly_payment_nis
    stress_payment = fixed_candidate.metrics.max_payment_under_stress
    sensitivity_map = {
        item.scenario: item.payment_nis
        for item in fixed_candidate.metrics.payment_sensitivity
    }

    assert stress_payment == pytest.approx(base_payment)
    assert all(
        payment == pytest.approx(base_payment) for payment in sensitivity_map.values()
    )


def test_prime_and_cpi_shocks_reflect_exposure():
    submission = build_submission()
    planning = build_planning_context(submission)
    result = optimize_mixes(submission.record, planning)

    mixed_candidate = result.candidates[1]
    base_payment = mixed_candidate.metrics.monthly_payment_nis
    sensitivity_map = {
        item.scenario: item.payment_nis
        for item in mixed_candidate.metrics.payment_sensitivity
    }

    assert sensitivity_map["prime_+1pct"] > base_payment
    assert sensitivity_map["cpi_path_+2pct"] > base_payment
