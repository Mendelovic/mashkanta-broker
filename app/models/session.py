"""Pydantic models for session listing and detail APIs."""

from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel

from .chat_response import (
    CandidateSummary,
    ComparisonRow,
    OptimizationSummary,
    OptimizationTermSweepEntry,
)


class SessionMessageModel(BaseModel):
    id: int
    role: str
    content: dict[str, Any]
    created_at: datetime


class SessionSummary(BaseModel):
    session_id: str
    created_at: datetime
    updated_at: datetime
    message_count: int
    latest_message: Optional[SessionMessageModel] = None


class SessionDetail(BaseModel):
    session_id: str
    created_at: datetime
    updated_at: datetime
    messages: List[SessionMessageModel]
    timeline: dict[str, Any]
    intake: dict[str, Any]
    planning: Optional[dict[str, Any]] = None
    optimization: Optional[dict[str, Any]] = None
    optimization_summary: Optional[OptimizationSummary] = None
    optimization_candidates: Optional[List[CandidateSummary]] = None
    optimization_matrix: Optional[List[ComparisonRow]] = None
    engine_recommended_index: Optional[int] = None
    advisor_recommended_index: Optional[int] = None
    term_sweep: Optional[List[OptimizationTermSweepEntry]] = None


__all__ = ["SessionMessageModel", "SessionSummary", "SessionDetail"]
