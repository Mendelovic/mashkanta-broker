import logging
import os
import shutil
import tempfile
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Form, File, UploadFile, Security
from fastapi.security import APIKeyHeader
from pydantic import BaseModel
from agents import Runner

from ..config import settings
from ..services.session_manager import get_or_create_session


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
class ChatResponse(BaseModel):
    """Response from chat endpoint."""

    response: str
    thread_id: str
    files_processed: Optional[int] = None


# Main endpoint
@router.post("/chat", response_model=ChatResponse)
async def unified_chat_endpoint(
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
        # Create or retrieve a session; assign a fresh ID when missing
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
                    "\n[DOCUMENT_UPLOADS]\n"
                    + "\n".join(upload_lines)
                    + "\nCall `analyze_document` for each temp_path above, summarize the findings in Hebrew, and confirm key values with the client.\n\n"
                )
                message = file_context + message

            finally:
                for uploaded in files or []:
                    try:
                        uploaded.file.close()
                    except Exception:  # pragma: no cover
                        pass

        # Get the global orchestrator agent
        from main import global_orchestrator

        agent = global_orchestrator

        # Run the agent with the user message
        result = await Runner.run(agent, message, session=session)

        # Clean up temporary files once the agent has seen the paths
        for temp_path in temp_paths:
            try:
                os.unlink(temp_path)
                logger.debug("Removed temp document: %s", temp_path)
            except OSError:
                logger.warning("Failed to remove temp document: %s", temp_path)

        return ChatResponse(
            response=result.final_output,
            thread_id=thread_id,
            files_processed=files_processed or None,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Chat endpoint failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to process request: {e}")
