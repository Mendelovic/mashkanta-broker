from app.services.mix_optimizer import optimize_mixes
from app.services.optimization_formatter import format_candidates
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
    assert recommended_item["track_details"]
    assert "fixed_unindexed_pct" in recommended_item["shares"]
