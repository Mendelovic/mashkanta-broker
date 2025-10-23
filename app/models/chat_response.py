"""Pydantic models for chat endpoint responses."""

from __future__ import annotations

from typing import Any, List, Optional

from pydantic import BaseModel


class CandidateShares(BaseModel):
    fixed_unindexed_pct: float
    fixed_cpi_pct: float
    variable_prime_pct: float
    variable_cpi_pct: float


class CandidateSensitivity(BaseModel):
    scenario: str
    payment_nis: float


class CandidateMetrics(BaseModel):
    monthly_payment_nis: float
    expected_weighted_payment_nis: float
    highest_expected_payment_nis: float
    stress_payment_nis: float
    pti_ratio: float
    pti_ratio_peak: float
    five_year_total_payment_nis: float
    total_weighted_cost_nis: float
    variable_share_pct: float
    cpi_share_pct: float
    ltv_ratio: float
    prepayment_fee_exposure: str
    peak_payment_month: Optional[int] = None
    peak_payment_driver: Optional[str] = None
    sensitivities: List[CandidateSensitivity]
    highest_expected_payment_note: Optional[str] = None


class CandidateTrackDetail(BaseModel):
    track: str
    amount_nis: float
    rate_display: str
    indexation: str
    reset_note: str
    anchor_rate_pct: Optional[float] = None


class CandidateFeasibility(BaseModel):
    is_feasible: Optional[bool] = None
    ltv_ratio: Optional[float] = None
    ltv_limit: Optional[float] = None
    pti_ratio: Optional[float] = None
    pti_ratio_peak: Optional[float] = None
    pti_limit: Optional[float] = None
    issues: Optional[List[str]] = None


class CandidateSummary(BaseModel):
    label: str
    index: int
    is_recommended: bool
    is_engine_recommended: bool
    shares: CandidateShares
    metrics: CandidateMetrics
    track_details: List[CandidateTrackDetail]
    feasibility: Optional[CandidateFeasibility] = None
    notes: Optional[List[str]] = None


class ComparisonRow(BaseModel):
    label: str
    index: int
    monthly_payment_nis: float
    highest_expected_payment_nis: float
    delta_peak_payment_nis: float
    pti_ratio: float
    pti_ratio_peak: float
    variable_share_pct: float
    cpi_share_pct: float
    five_year_total_payment_nis: float
    prepayment_fee_exposure: str
    peak_payment_month: Optional[int] = None
    peak_payment_driver: Optional[str] = None


class OptimizationSummary(BaseModel):
    label: str
    index: int
    monthly_payment_nis: float
    stress_payment_nis: float
    highest_expected_payment_nis: float
    expected_weighted_payment_nis: float
    pti_ratio: float
    pti_ratio_peak: float
    highest_expected_payment_note: Optional[str] = None
    peak_payment_month: Optional[int] = None
    peak_payment_driver: Optional[str] = None
    engine_label: Optional[str] = None
    engine_index: Optional[int] = None


class OptimizationTermSweepEntry(BaseModel):
    term_years: int
    monthly_payment_nis: float
    monthly_payment_display: str
    stress_payment_nis: float
    stress_payment_display: str
    expected_weighted_payment_nis: float
    expected_weighted_payment_display: str
    pti_ratio: float
    pti_ratio_display: str
    pti_ratio_peak: float
    pti_ratio_peak_display: str


class ChatResponse(BaseModel):
    """Response from chat endpoint."""

    response: str
    thread_id: str
    files_processed: Optional[int] = None
    timeline: Optional[dict[str, Any]] = None
    intake: Optional[dict[str, Any]] = None
    planning: Optional[dict[str, Any]] = None
    optimization: Optional[dict[str, Any]] = None
    optimization_summary: Optional[OptimizationSummary] = None
    optimization_candidates: Optional[List[CandidateSummary]] = None
    optimization_matrix: Optional[List[ComparisonRow]] = None
    engine_recommended_index: Optional[int] = None
    advisor_recommended_index: Optional[int] = None
    term_sweep: Optional[List[OptimizationTermSweepEntry]] = None


__all__ = [
    "CandidateShares",
    "CandidateSensitivity",
    "CandidateMetrics",
    "CandidateTrackDetail",
    "CandidateFeasibility",
    "CandidateSummary",
    "ComparisonRow",
    "OptimizationSummary",
    "OptimizationTermSweepEntry",
    "ChatResponse",
]
