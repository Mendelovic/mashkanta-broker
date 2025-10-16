"""Helpers for presenting optimization candidates."""

from __future__ import annotations

from typing import Any, Dict, List

from app.domain.schemas import OptimizationCandidate, OptimizationResult, TermSweepEntry


def _format_currency(value: float) -> str:
    return f"{value:,.0f}"


def _format_pct(value: float) -> str:
    return f"{value:.1f}%"


def _share_percentages(candidate: OptimizationCandidate) -> Dict[str, float]:
    shares = candidate.shares
    return {
        "fixed_unindexed_pct": shares.fixed_unindexed * 100,
        "fixed_cpi_pct": shares.fixed_cpi * 100,
        "variable_prime_pct": shares.variable_prime * 100,
        "variable_cpi_pct": shares.variable_cpi * 100,
    }


def _metrics_snapshot(candidate: OptimizationCandidate) -> Dict[str, Any]:
    metrics = candidate.metrics
    delta_peak_payment = (
        metrics.highest_expected_payment_nis - metrics.monthly_payment_nis
    )
    return {
        "monthly_payment_nis": metrics.monthly_payment_nis,
        "monthly_payment_display": _format_currency(metrics.monthly_payment_nis),
        "expected_weighted_payment_nis": metrics.expected_weighted_payment_nis,
        "highest_expected_payment_nis": metrics.highest_expected_payment_nis,
        "highest_expected_payment_display": _format_currency(
            metrics.highest_expected_payment_nis
        ),
        "highest_expected_payment_note": metrics.highest_expected_payment_note,
        "stress_payment_nis": metrics.max_payment_under_stress,
        "stress_payment_display": _format_currency(metrics.max_payment_under_stress),
        "delta_peak_payment_nis": delta_peak_payment,
        "delta_peak_payment_display": _format_currency(delta_peak_payment),
        "pti_ratio": metrics.pti_ratio,
        "pti_ratio_display": _format_pct(metrics.pti_ratio * 100),
        "pti_ratio_peak": metrics.pti_ratio_peak,
        "pti_ratio_peak_display": _format_pct(metrics.pti_ratio_peak * 100),
        "five_year_total_payment_nis": metrics.five_year_total_payment_nis,
        "five_year_total_payment_display": _format_currency(
            metrics.five_year_total_payment_nis
        ),
        "total_weighted_cost_nis": metrics.total_weighted_cost_nis,
        "variable_share_pct": metrics.variable_share_pct,
        "variable_share_display": _format_pct(metrics.variable_share_pct),
        "cpi_share_pct": metrics.cpi_share_pct,
        "cpi_share_display": _format_pct(metrics.cpi_share_pct),
        "ltv_ratio": metrics.ltv_ratio,
        "ltv_ratio_display": _format_pct(metrics.ltv_ratio * 100),
        "prepayment_fee_exposure": metrics.prepayment_fee_exposure,
        "peak_payment_month": metrics.peak_payment_month,
        "peak_payment_driver": metrics.peak_payment_driver,
        "payment_sensitivity": [
            {"scenario": item.scenario, "payment_nis": item.payment_nis}
            for item in metrics.payment_sensitivity
        ],
    }


def _track_details_snapshot(candidate: OptimizationCandidate) -> List[Dict[str, Any]]:
    return [
        {
            "track": detail.track,
            "amount_nis": detail.amount_nis,
            "rate_display": detail.rate_display,
            "indexation": detail.indexation,
            "reset_note": detail.reset_note,
            "anchor_rate_pct": detail.anchor_rate_pct,
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
        "pti_ratio_peak": feasibility.pti_ratio_peak,
        "pti_limit": feasibility.pti_limit,
        "variable_share_pct": feasibility.variable_share_pct,
        "variable_share_limit_pct": feasibility.variable_share_limit_pct,
        "loan_term_years": feasibility.loan_term_years,
        "loan_term_limit_years": feasibility.loan_term_limit_years,
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
                "is_engine_recommended": index
                == (
                    result.engine_recommended_index
                    if result.engine_recommended_index is not None
                    else result.recommended_index
                ),
                "shares": _share_percentages(candidate),
                "metrics": _metrics_snapshot(candidate),
                "track_details": _track_details_snapshot(candidate),
                "feasibility": _feasibility_snapshot(candidate),
                "notes": list(candidate.notes),
            }
        )
    return formatted


def format_comparison_matrix(result: OptimizationResult) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for index, candidate in enumerate(result.candidates):
        metrics = candidate.metrics
        delta_peak_payment = (
            metrics.highest_expected_payment_nis - metrics.monthly_payment_nis
        )
        rows.append(
            {
                "label": candidate.label,
                "index": index,
                "monthly_payment_nis": metrics.monthly_payment_nis,
                "monthly_payment_display": _format_currency(
                    metrics.monthly_payment_nis
                ),
                "highest_expected_payment_nis": metrics.highest_expected_payment_nis,
                "highest_expected_payment_display": _format_currency(
                    metrics.highest_expected_payment_nis
                ),
                "delta_peak_payment_nis": delta_peak_payment,
                "delta_peak_payment_display": _format_currency(delta_peak_payment),
                "pti_ratio": metrics.pti_ratio,
                "pti_ratio_display": _format_pct(metrics.pti_ratio * 100),
                "pti_ratio_peak": metrics.pti_ratio_peak,
                "pti_ratio_peak_display": _format_pct(metrics.pti_ratio_peak * 100),
                "variable_share_pct": metrics.variable_share_pct,
                "variable_share_display": _format_pct(metrics.variable_share_pct),
                "cpi_share_pct": metrics.cpi_share_pct,
                "cpi_share_display": _format_pct(metrics.cpi_share_pct),
                "five_year_total_payment_nis": metrics.five_year_total_payment_nis,
                "five_year_total_payment_display": _format_currency(
                    metrics.five_year_total_payment_nis
                ),
                "prepayment_fee_exposure": metrics.prepayment_fee_exposure,
                "peak_payment_month": metrics.peak_payment_month,
                "peak_payment_driver": metrics.peak_payment_driver,
            }
        )
    return rows


def format_term_sweep(entries: List[TermSweepEntry]) -> List[Dict[str, Any]]:
    formatted: List[Dict[str, Any]] = []
    for entry in entries:
        formatted.append(
            {
                "term_years": entry.term_years,
                "monthly_payment_nis": entry.monthly_payment_nis,
                "monthly_payment_display": _format_currency(entry.monthly_payment_nis),
                "stress_payment_nis": entry.stress_payment_nis,
                "stress_payment_display": _format_currency(entry.stress_payment_nis),
                "expected_weighted_payment_nis": entry.expected_weighted_payment_nis,
                "expected_weighted_payment_display": _format_currency(
                    entry.expected_weighted_payment_nis
                ),
                "pti_ratio": entry.pti_ratio,
                "pti_ratio_display": _format_pct(entry.pti_ratio * 100),
                "pti_ratio_peak": entry.pti_ratio_peak,
                "pti_ratio_peak_display": _format_pct(entry.pti_ratio_peak * 100),
            }
        )
    return formatted


__all__ = ["format_candidates", "format_comparison_matrix", "format_term_sweep"]
