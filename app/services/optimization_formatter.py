"""Helpers for presenting optimization candidates."""

from __future__ import annotations

from typing import Any, Dict, List

from app.domain.schemas import OptimizationCandidate, OptimizationResult


def _share_percentages(candidate: OptimizationCandidate) -> Dict[str, float]:
    shares = candidate.shares
    return {
        "fixed_unindexed_pct": shares.fixed_unindexed * 100,
        "fixed_cpi_pct": shares.fixed_cpi * 100,
        "variable_prime_pct": shares.variable_prime * 100,
        "variable_cpi_pct": shares.variable_cpi * 100,
    }


def _metrics_snapshot(candidate: OptimizationCandidate) -> Dict[str, float]:
    metrics = candidate.metrics
    return {
        "monthly_payment_nis": metrics.monthly_payment_nis,
        "expected_weighted_payment_nis": metrics.expected_weighted_payment_nis,
        "highest_expected_payment_nis": metrics.highest_expected_payment_nis,
        "stress_payment_nis": metrics.max_payment_under_stress,
        "pti_ratio": metrics.pti_ratio,
        "pti_ratio_peak": metrics.pti_ratio_peak,
        "five_year_cost_nis": metrics.five_year_cost_nis,
        "total_weighted_cost_nis": metrics.total_weighted_cost_nis,
        "variable_share_pct": metrics.variable_share_pct,
        "cpi_share_pct": metrics.cpi_share_pct,
        "ltv_ratio": metrics.ltv_ratio,
        "prepayment_fee_exposure": metrics.prepayment_fee_exposure,
    }


def _track_details_snapshot(candidate: OptimizationCandidate) -> List[Dict[str, Any]]:
    return [
        {
            "track": detail.track,
            "amount_nis": detail.amount_nis,
            "rate_display": detail.rate_display,
            "indexation": detail.indexation,
            "reset_note": detail.reset_note,
        }
        for detail in candidate.metrics.track_details
    ]


def _feasibility_snapshot(candidate: OptimizationCandidate) -> Dict[str, Any] | None:
    feasibility = candidate.feasibility
    if feasibility is None:
        return None
    return {
        "is_feasible": feasibility.is_feasible,
        "ltv_ratio": feasibility.ltv_ratio,
        "ltv_limit": feasibility.ltv_limit,
        "pti_ratio": feasibility.pti_ratio,
        "pti_limit": feasibility.pti_limit,
        "issues": [issue.code for issue in feasibility.issues],
    }


def format_candidates(result: OptimizationResult) -> List[Dict[str, Any]]:
    """Return a presentation-friendly summary for each optimization candidate."""

    formatted: List[Dict[str, Any]] = []
    for index, candidate in enumerate(result.candidates):
        formatted.append(
            {
                "label": candidate.label,
                "index": index,
                "is_recommended": index == result.recommended_index,
                "shares": _share_percentages(candidate),
                "metrics": _metrics_snapshot(candidate),
                "track_details": _track_details_snapshot(candidate),
                "feasibility": _feasibility_snapshot(candidate),
                "notes": list(candidate.notes),
            }
        )
    return formatted


__all__ = ["format_candidates"]
