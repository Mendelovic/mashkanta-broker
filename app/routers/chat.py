import logging
import os
import shutil
import tempfile
from typing import Annotated, Optional, Any, List

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Form,
    File,
    UploadFile,
    Security,
    Request,
)
from fastapi.security import APIKeyHeader
from pydantic import BaseModel
from agents import Runner

from ..config import settings
from ..models.context import ChatRunContext
from ..services.session_manager import get_or_create_session
from ..services.optimization_formatter import (
    format_candidates,
    format_comparison_matrix,
    format_term_sweep,
)


logger = logging.getLogger(__name__)

_api_key_header = APIKeyHeader(name="x-mortgage-api-key", auto_error=False)


async def require_api_key(provided: str | None = Security(_api_key_header)) -> None:
    """Validate the optional API key header for the chat endpoint."""
    if settings.chat_api_key:
        if provided != settings.chat_api_key:
            raise HTTPException(status_code=401, detail="Invalid API key")
    elif provided:
        logger.warning(
            "API key provided but chat_api_key not configured; ignoring header"
        )


router = APIRouter(
    prefix="",  # No prefix since we want /chat at root level
    tags=["chat"],
    responses={404: {"description": "Not found"}},
    dependencies=[Depends(require_api_key)],
)


# Response Models
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


# Main endpoint
@router.post("/chat", response_model=ChatResponse)
async def unified_chat_endpoint(
    request: Request,
    message: Annotated[str, Form(max_length=settings.max_message_length)],
    thread_id: Annotated[Optional[str], Form()] = None,
    files: Annotated[Optional[list[UploadFile]], File()] = None,
):
    """
    chat endpoint handling all interactions.

    Accepts:
    - message: User message (required)
    - thread_id: Session identifier for continuing conversations (optional; server assigns one if missing)
    - header x-mortgage-api-key: Required when the server is configured with chat_api_key

    Returns:
    - response: Agent's response
    - thread_id: Session identifier for next request
    - files_processed: Number of files processed (if any)
    """
    try:
        provided_thread_id = thread_id
        thread_id, session = get_or_create_session(thread_id)

        if provided_thread_id is None:
            logger.info("Assigned new session_id: %s", thread_id)

        files_processed = 0
        temp_paths: list[str] = []

        candidate_files = files or []
        valid_files = [
            file for file in candidate_files if file and getattr(file, "filename", None)
        ]

        if valid_files:
            if len(valid_files) > settings.max_files_per_request:
                raise HTTPException(
                    status_code=400,
                    detail=f"You can upload up to {settings.max_files_per_request} files per request.",
                )

            try:
                upload_lines: list[str] = []
                for uploaded in valid_files:
                    filename = uploaded.filename or ""
                    lowered = filename.lower()
                    if not lowered.endswith((".pdf", ".png", ".jpg", ".jpeg")):
                        raise HTTPException(
                            status_code=400,
                            detail="Only PDF and image files (PNG/JPG) are supported.",
                        )

                    suffix = os.path.splitext(lowered)[1] or ".pdf"

                    with tempfile.NamedTemporaryFile(
                        delete=False, suffix=suffix
                    ) as tmp:
                        shutil.copyfileobj(uploaded.file, tmp)
                        temp_path = tmp.name
                        temp_paths.append(temp_path)

                    files_processed += 1
                    display_name = uploaded.filename or os.path.basename(temp_path)
                    upload_lines.append(f"- {display_name}: {temp_path}")
                    logger.info(
                        "Stored uploaded document for analysis: %s -> %s",
                        uploaded.filename,
                        temp_path,
                    )

                file_context = (
                    "\n[DOCUMENT_UPLOADS]\n" + "\n".join(upload_lines) + "\n\n"
                )
                message = file_context + message

            finally:
                for uploaded in files or []:
                    try:
                        uploaded.file.close()
                    except Exception:  # pragma: no cover
                        pass

        agent = getattr(request.app.state, "orchestrator", None)
        if agent is None:
            logger.error("Chat orchestrator is not initialized")
            raise HTTPException(status_code=503, detail="Chat agent is unavailable")

        result = await Runner.run(
            agent,
            message,
            session=session,
            context=ChatRunContext(session_id=thread_id),
            max_turns=settings.agent_max_turns,
        )

        for temp_path in temp_paths:
            try:
                os.unlink(temp_path)
                logger.debug("Removed temp document: %s", temp_path)
            except OSError:
                logger.warning("Failed to remove temp document: %s", temp_path)

        timeline_state = session.get_timeline().to_dict()
        intake_state = session.get_intake().to_dict()
        planning_context = session.get_planning_context()
        planning_state = (
            planning_context.model_dump() if planning_context is not None else None
        )
        optimization_result = session.get_optimization_result()
        optimization_state = (
            optimization_result.model_dump()
            if optimization_result is not None
            else None
        )

        optimization_summary: OptimizationSummary | None = None
        optimization_candidates: List[CandidateSummary] | None = None
        optimization_matrix: List[ComparisonRow] | None = None
        term_sweep_rows: List[OptimizationTermSweepEntry] | None = None
        engine_recommended_index: Optional[int] = None
        advisor_recommended_index: Optional[int] = None
        if optimization_result is not None:
            candidate_payloads = format_candidates(optimization_result)
            optimization_matrix = [
                ComparisonRow(**row)
                for row in format_comparison_matrix(optimization_result)
            ]
            candidate_models: List[CandidateSummary] = []
            for item in candidate_payloads:
                candidate_models.append(build_candidate_summary(item))
            if candidate_models:
                optimization_candidates = candidate_models
                engine_recommended_index = optimization_result.engine_recommended_index
                advisor_recommended_index = (
                    optimization_result.advisor_recommended_index
                    if optimization_result.advisor_recommended_index is not None
                    else optimization_result.recommended_index
                )
                recommended_candidate = next(
                    (c for c in candidate_models if c.is_recommended),
                    candidate_models[0],
                )
                engine_candidate = next(
                    (c for c in candidate_models if c.is_engine_recommended),
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

            if optimization_result.term_sweep:
                term_sweep_rows = [
                    OptimizationTermSweepEntry(**row)
                    for row in format_term_sweep(optimization_result.term_sweep)
                ]

        return ChatResponse(
            response=result.final_output,
            thread_id=thread_id,
            files_processed=files_processed or None,
            timeline=timeline_state,
            intake=intake_state,
            planning=planning_state,
            optimization=optimization_state,
            optimization_summary=optimization_summary,
            optimization_candidates=optimization_candidates,
            optimization_matrix=optimization_matrix,
            engine_recommended_index=engine_recommended_index,
            advisor_recommended_index=advisor_recommended_index,
            term_sweep=term_sweep_rows,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Chat endpoint failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to process request: {e}")
