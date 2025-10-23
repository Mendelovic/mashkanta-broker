"""Builders for chat optimization payloads."""

from __future__ import annotations

from typing import Any, List, Optional, Tuple

from ..models.chat_response import (
    CandidateFeasibility,
    CandidateMetrics,
    CandidateSensitivity,
    CandidateShares,
    CandidateSummary,
    CandidateTrackDetail,
    ComparisonRow,
    OptimizationSummary,
    OptimizationTermSweepEntry,
)
from .optimization_formatter import (
    format_candidates,
    format_comparison_matrix,
    format_term_sweep,
)


def build_candidate_summary(item: dict[str, Any]) -> CandidateSummary:
    """Convert formatter payload into `CandidateSummary` Pydantic model."""

    shares = item.get("shares", {})
    metrics = item.get("metrics", {})
    feasibility_data = item.get("feasibility")
    track_details_raw = item.get("track_details", [])
    track_models: List[CandidateTrackDetail] = []
    for detail in track_details_raw:
        if isinstance(detail, dict):
            track_models.append(
                CandidateTrackDetail(
                    track=str(detail.get("track", "")),
                    amount_nis=float(detail.get("amount_nis", 0.0)),
                    rate_display=str(detail.get("rate_display", "")),
                    indexation=str(detail.get("indexation", "")),
                    reset_note=str(detail.get("reset_note", "")),
                    anchor_rate_pct=(
                        float(detail["anchor_rate_pct"])
                        if "anchor_rate_pct" in detail
                        and detail["anchor_rate_pct"] is not None
                        else None
                    ),
                )
            )

    sensitivities_raw = metrics.get("payment_sensitivity", [])
    sensitivity_models: List[CandidateSensitivity] = []
    for sensitivity in sensitivities_raw:
        if isinstance(sensitivity, dict):
            sensitivity_models.append(
                CandidateSensitivity(
                    scenario=str(sensitivity.get("scenario", "")),
                    payment_nis=float(sensitivity.get("payment_nis", 0.0)),
                )
            )

    return CandidateSummary(
        label=item.get("label", ""),
        index=item.get("index", 0),
        is_recommended=bool(item.get("is_recommended", False)),
        is_engine_recommended=bool(item.get("is_engine_recommended", False)),
        shares=CandidateShares(
            fixed_unindexed_pct=float(shares.get("fixed_unindexed_pct", 0.0)),
            fixed_cpi_pct=float(shares.get("fixed_cpi_pct", 0.0)),
            variable_prime_pct=float(shares.get("variable_prime_pct", 0.0)),
            variable_cpi_pct=float(shares.get("variable_cpi_pct", 0.0)),
        ),
        metrics=CandidateMetrics(
            monthly_payment_nis=float(metrics.get("monthly_payment_nis", 0.0)),
            expected_weighted_payment_nis=float(
                metrics.get("expected_weighted_payment_nis", 0.0)
            ),
            highest_expected_payment_nis=float(
                metrics.get("highest_expected_payment_nis", 0.0)
            ),
            highest_expected_payment_note=str(
                metrics.get(
                    "highest_expected_payment_note",
                    "Highest expected payment reflects Bank of Israel disclosure stress.",
                )
            ),
            stress_payment_nis=float(metrics.get("stress_payment_nis", 0.0)),
            pti_ratio=float(metrics.get("pti_ratio", 0.0)),
            pti_ratio_peak=float(metrics.get("pti_ratio_peak", 0.0)),
            five_year_total_payment_nis=float(
                metrics.get("five_year_total_payment_nis", 0.0)
            ),
            total_weighted_cost_nis=float(metrics.get("total_weighted_cost_nis", 0.0)),
            variable_share_pct=float(metrics.get("variable_share_pct", 0.0)),
            cpi_share_pct=float(metrics.get("cpi_share_pct", 0.0)),
            ltv_ratio=float(metrics.get("ltv_ratio", 0.0)),
            prepayment_fee_exposure=str(metrics.get("prepayment_fee_exposure", "")),
            peak_payment_month=(
                int(metrics["peak_payment_month"])
                if metrics.get("peak_payment_month") is not None
                else None
            ),
            peak_payment_driver=(
                str(metrics.get("peak_payment_driver"))
                if metrics.get("peak_payment_driver") is not None
                else None
            ),
            sensitivities=sensitivity_models,
        ),
        track_details=track_models,
        feasibility=CandidateFeasibility(**feasibility_data)
        if isinstance(feasibility_data, dict)
        else None,
        notes=list(item.get("notes", [])) or None,
    )


def build_optimization_payload(
    optimization_result,
) -> Tuple[
    List[CandidateSummary],
    List[ComparisonRow],
    Optional[OptimizationSummary],
    Optional[List[OptimizationTermSweepEntry]],
    Optional[int],
    Optional[int],
]:
    if optimization_result is None:
        return [], [], None, None, None, None

    candidate_payloads = format_candidates(optimization_result)
    optimization_matrix = [
        ComparisonRow(**row) for row in format_comparison_matrix(optimization_result)
    ]

    candidate_models: List[CandidateSummary] = [
        build_candidate_summary(item) for item in candidate_payloads
    ]

    optimization_summary: Optional[OptimizationSummary] = None
    engine_recommended_index: Optional[int] = None
    advisor_recommended_index: Optional[int] = None

    if candidate_models:
        engine_recommended_index = optimization_result.engine_recommended_index
        advisor_recommended_index = (
            optimization_result.advisor_recommended_index
            if optimization_result.advisor_recommended_index is not None
            else optimization_result.recommended_index
        )
        recommended_candidate = next(
            (candidate for candidate in candidate_models if candidate.is_recommended),
            candidate_models[0],
        )
        engine_candidate = next(
            (
                candidate
                for candidate in candidate_models
                if candidate.is_engine_recommended
            ),
            recommended_candidate,
        )
        optimization_summary = OptimizationSummary(
            label=recommended_candidate.label,
            index=recommended_candidate.index,
            monthly_payment_nis=recommended_candidate.metrics.monthly_payment_nis,
            stress_payment_nis=recommended_candidate.metrics.stress_payment_nis,
            highest_expected_payment_nis=recommended_candidate.metrics.highest_expected_payment_nis,
            expected_weighted_payment_nis=recommended_candidate.metrics.expected_weighted_payment_nis,
            pti_ratio=recommended_candidate.metrics.pti_ratio,
            pti_ratio_peak=recommended_candidate.metrics.pti_ratio_peak,
            highest_expected_payment_note=recommended_candidate.metrics.highest_expected_payment_note,
            peak_payment_month=recommended_candidate.metrics.peak_payment_month,
            peak_payment_driver=recommended_candidate.metrics.peak_payment_driver,
            engine_label=engine_candidate.label,
            engine_index=engine_candidate.index,
        )

    term_sweep_rows: Optional[List[OptimizationTermSweepEntry]] = None
    if optimization_result.term_sweep:
        term_sweep_rows = [
            OptimizationTermSweepEntry(**row)
            for row in format_term_sweep(optimization_result.term_sweep)
        ]

    return (
        candidate_models,
        optimization_matrix,
        optimization_summary,
        term_sweep_rows,
        engine_recommended_index,
        advisor_recommended_index,
    )


__all__ = ["build_candidate_summary", "build_optimization_payload"]
