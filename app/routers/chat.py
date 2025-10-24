import logging
from typing import Annotated, Optional

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Form,
    File,
    Request,
    UploadFile,
)
from agents import Runner

from ..config import settings
from ..models.chat_response import ChatResponse
from ..models.context import ChatRunContext
from ..security import AuthenticatedUser, get_current_user
from ..services.session_manager import get_or_create_session
from ..services.chat_payload import build_optimization_payload
from ..services.session_snapshot import gather_session_state
from ..services.upload_manager import cleanup_temp_paths, process_uploads


logger = logging.getLogger(__name__)


router = APIRouter(
    prefix="",  # No prefix since we want /chat at root level
    tags=["chat"],
    responses={404: {"description": "Not found"}},
)


# Main endpoint
@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: Request,
    message: Annotated[str, Form(max_length=settings.max_message_length)],
    thread_id: Annotated[Optional[str], Form()] = None,
    files: Annotated[Optional[list[UploadFile]], File()] = None,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    try:
        provided_thread_id = thread_id
        try:
            thread_id, session = get_or_create_session(
                thread_id, user_id=current_user.user_id
            )
        except PermissionError:
            logger.warning(
                "User %s attempted to access unauthorized session_id=%s",
                current_user.user_id,
                thread_id,
            )
            raise HTTPException(status_code=404, detail="Session not found")

        if provided_thread_id is None:
            logger.info("Assigned new session_id: %s", thread_id)

        upload_result = process_uploads(files)
        if upload_result.message_prefix:
            message = upload_result.message_prefix + message
        files_processed = upload_result.files_processed
        temp_paths = upload_result.temp_paths

        agent = getattr(request.app.state, "orchestrator", None)
        if agent is None:
            logger.error("Chat orchestrator is not initialized")
            raise HTTPException(status_code=503, detail="Chat agent is unavailable")

        try:
            result = await Runner.run(
                agent,
                message,
                session=session,
                context=ChatRunContext(session_id=thread_id),
                max_turns=settings.agent_max_turns,
            )
        finally:
            cleanup_temp_paths(temp_paths)

        (
            timeline_state,
            intake_state,
            planning_state,
            optimization_result,
            optimization_state,
        ) = gather_session_state(session)

        (
            optimization_candidates,
            optimization_matrix,
            optimization_summary,
            term_sweep_rows,
            engine_recommended_index,
            advisor_recommended_index,
        ) = build_optimization_payload(optimization_result)

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
    except Exception:
        logger.exception("Chat endpoint failed")
        raise HTTPException(status_code=500, detail="Failed to process request.")
