import pytest

from app.models.chat_response import CandidateSummary
from app.services.chat_payload import build_candidate_summary
from app.services.mix_optimizer import optimize_mixes
from app.services.optimization_formatter import (
    format_candidates,
    format_comparison_matrix,
    format_term_sweep,
)
from app.services.planning_mapper import build_planning_context
from tests.factories import build_submission


def test_format_candidates_returns_all_candidates() -> None:
    submission = build_submission()
    planning = build_planning_context(submission)
    result = optimize_mixes(submission.record, planning)

    summaries = format_candidates(result)

    assert len(summaries) == len(result.candidates)
    labels = [item["label"] for item in summaries]
    assert result.candidates[0].label in labels
    recommended = [item for item in summaries if item["is_recommended"]]
    assert len(recommended) == 1
    recommended_item = recommended[0]
    assert recommended_item["metrics"]["monthly_payment_nis"] > 0
    assert (
        recommended_item["metrics"]["pti_ratio_peak"]
        >= recommended_item["metrics"]["pti_ratio"]
    )
    assert recommended_item["metrics"]["prepayment_fee_exposure"]
    assert recommended_item["metrics"]["five_year_total_payment_nis"] > 0
    assert recommended_item["metrics"]["peak_payment_driver"] is not None
    assert recommended_item["track_details"]
    assert "fixed_unindexed_pct" in recommended_item["shares"]
    assert "monthly_payment_display" in recommended_item["metrics"]
    assert "," in recommended_item["metrics"]["monthly_payment_display"]
    assert "pti_ratio_peak_display" in recommended_item["metrics"]
    assert "is_engine_recommended" in recommended_item
    prime_tracks = [
        track
        for track in recommended_item["track_details"]
        if track["track"] == "variable_prime"
    ]
    if prime_tracks:
        assert prime_tracks[0]["anchor_rate_pct"] is not None
        assert pytest.approx(prime_tracks[0]["anchor_rate_pct"], rel=1e-6) == 6.0


def test_formatter_payload_validates_against_chat_models() -> None:
    submission = build_submission()
    planning = build_planning_context(submission)
    result = optimize_mixes(submission.record, planning)

    candidate_payloads = format_candidates(result)
    summaries = [build_candidate_summary(item) for item in candidate_payloads]

    assert len(summaries) == len(candidate_payloads)
    assert all(isinstance(summary, CandidateSummary) for summary in summaries)
    assert all(summary.metrics.sensitivities for summary in summaries)
    assert any(summary.is_engine_recommended for summary in summaries)
    feasibilities = [
        summary.feasibility for summary in summaries if summary.feasibility
    ]
    assert all(feasibility.pti_ratio_peak is not None for feasibility in feasibilities)


def test_format_comparison_matrix_returns_expected_rows() -> None:
    submission = build_submission()
    planning = build_planning_context(submission)
    result = optimize_mixes(submission.record, planning)

    rows = format_comparison_matrix(result)

    assert rows, "comparison matrix should include at least one row"
    first = rows[0]
    assert "monthly_payment_nis" in first
    assert "delta_peak_payment_nis" in first
    assert "prepayment_fee_exposure" in first
    assert "monthly_payment_display" in first
    assert "pti_ratio_peak_display" in first
    assert "five_year_total_payment_nis" in first
    assert "peak_payment_driver" in first


def test_format_term_sweep() -> None:
    submission = build_submission()
    planning = build_planning_context(submission)
    result = optimize_mixes(submission.record, planning)

    sweep = format_term_sweep(result.term_sweep)
    assert sweep
    entry = sweep[0]
    assert "term_years" in entry
    assert "monthly_payment_display" in entry
    assert "pti_ratio_display" in entry
