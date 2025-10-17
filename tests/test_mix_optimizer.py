import pytest

from app.services.mix_optimizer import optimize_mixes
from app.services.planning_mapper import build_planning_context
from tests.factories import build_submission


def test_optimize_mixes_creates_candidates():
    submission = build_submission()
    planning = build_planning_context(submission)
    term_years = submission.record.loan.term_years

    result = optimize_mixes(submission.record, planning)

    assert result.candidates
    assert result.recommended_index < len(result.candidates)
    assert result.engine_recommended_index is not None
    assert result.advisor_recommended_index is not None
    assert result.recommended_index == result.advisor_recommended_index
    assert len(result.candidates) >= 1

    recommended = result.candidates[result.recommended_index]
    assert recommended.label.lower().startswith("tailored")
    metrics = recommended.metrics
    assert metrics.pti_ratio_peak >= metrics.pti_ratio
    assert metrics.future_pti_ratio is not None
    assert metrics.future_pti_ratio >= metrics.pti_ratio
    assert metrics.future_pti_month is not None
    assert metrics.future_pti_breach is True
    assert metrics.variable_share_pct >= 0
    assert metrics.track_details
    assert metrics.five_year_total_payment_nis > 0
    assert metrics.peak_payment_driver is not None
    assert recommended.feasibility is not None
    assert recommended.feasibility.pti_ratio == pytest.approx(metrics.pti_ratio)
    assert metrics.pti_ratio_peak >= recommended.feasibility.pti_ratio_peak
    assert recommended.feasibility.variable_share_limit_pct is not None
    assert recommended.feasibility.loan_term_limit_years == 30
    assert result.term_sweep
    sweep_terms = {entry.term_years for entry in result.term_sweep}
    assert term_years in sweep_terms
    assert any(term in sweep_terms for term in (15, 20, 25))
    assert "anchor_rates_pct" in result.assumptions
    assert "rate_table_snapshot_pct" in result.assumptions


def test_prime_and_cpi_shocks_reflect_exposure():
    submission = build_submission()
    planning = build_planning_context(submission)
    result = optimize_mixes(submission.record, planning)

    mixed_candidate = result.candidates[result.recommended_index]
    base_payment = mixed_candidate.metrics.monthly_payment_nis
    sensitivity_map = {
        item.scenario: item.payment_nis
        for item in mixed_candidate.metrics.payment_sensitivity
    }

    assert sensitivity_map["prime_+1pct"] > base_payment
    assert sensitivity_map["cpi_path_+2pct"] > base_payment
