import logging
import tempfile
import shutil
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends, File, UploadFile, Form
from pydantic import BaseModel
from agents import Runner

from ..config import settings
from ..agents.orchestrator import create_mortgage_broker_orchestrator
from ..services.session_manager import get_session_manager, SessionManager


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="",  # No prefix since we want /chat at root level
    tags=["chat"],
    responses={404: {"description": "Not found"}},
)


# Response Models
class ChatResponse(BaseModel):
    """Response from chat endpoint."""

    response: str
    thread_id: str
    files_processed: Optional[int] = None


# Dependencies
def get_session_manager_dependency() -> SessionManager:
    """Dependency to get session manager."""
    return get_session_manager()


# Main endpoint
@router.post("/chat", response_model=ChatResponse)
async def unified_chat_endpoint(
    message: str = Form(..., max_length=settings.max_message_length),
    thread_id: Optional[str] = Form(None),
    files: List[UploadFile] = File(default=[]),
    session_manager: SessionManager = Depends(get_session_manager_dependency),
):
    """
    chat endpoint handling all interactions.

    Accepts:
    - message: User message (required)
    - thread_id: Session identifier for continuing conversations (optional)
    - files: PDF files for analysis (optional)

    Returns:
    - response: Agent's response
    - thread_id: Session identifier for next request
    - files_processed: Number of files processed (if any)
    """
    try:
        files_processed_count = 0
        temp_paths = []

        # Get or create session
        if thread_id:
            session = await session_manager.get_session(thread_id)
            if not session:
                # If thread_id provided but session doesn't exist, create new one
                thread_id, session = session_manager.create_session()
                logger.info(f"Created new session for invalid thread_id: {thread_id}")
        else:
            # Create new session
            thread_id, session = session_manager.create_session()
            logger.info(f"Created new session: {thread_id}")

        # Process files if provided - Filter out None/empty entries
        valid_files = [
            file
            for file in files
            if file and hasattr(file, "filename") and file.filename
        ]

        if valid_files:
            # Validate files
            if len(valid_files) > settings.max_files_per_request:
                raise HTTPException(
                    status_code=400,
                    detail=f"ניתן להעלות עד {settings.max_files_per_request} קבצים בו-זמנית",
                )

            # Validate all files are PDFs
            for file in valid_files:
                if not file.filename or not file.filename.lower().endswith(".pdf"):
                    raise HTTPException(
                        status_code=400,
                        detail=f"הקובץ {file.filename} אינו PDF. נתמכים קבצי PDF בלבד.",
                    )

            try:
                # Store file paths for the agent to process
                file_descriptions = []
                for file in valid_files:
                    # Create temporary file
                    with tempfile.NamedTemporaryFile(
                        delete=False, suffix=".pdf"
                    ) as tmp_file:
                        shutil.copyfileobj(file.file, tmp_file)
                        tmp_path = tmp_file.name
                        temp_paths.append(tmp_path)

                    filename = file.filename or "unknown_file.pdf"
                    files_processed_count += 1

                    # Store file info for the agent to use
                    file_descriptions.append(
                        f"קובץ: {filename} (נתיב זמני: {tmp_path})"
                    )

                    logger.info(
                        f"Saved document for processing: {filename} -> {tmp_path}"
                    )

                # Add file processing instruction to message for the agent
                if files_processed_count > 0:
                    file_list = "\n".join(file_descriptions)
                    file_context = f"\nקבצים שהועלו לניתוח ({files_processed_count} קבצים):\n{file_list}\n\nאנא נתח את הקבצים באמצעות הכלי analyze_document_from_path ולאחר מכן "
                    message = file_context + message

            except Exception as file_error:
                # Clean up on error
                for tmp_path in temp_paths:
                    try:
                        import os

                        os.unlink(tmp_path)
                    except Exception:
                        pass
                raise HTTPException(
                    status_code=500, detail=f"שגיאה בעיבוד הקבצים: {str(file_error)}"
                )
            finally:
                # Close file handles (but keep temp files for agent processing)
                if files:
                    for file in files:
                        if file.file:
                            try:
                                file.file.close()
                            except Exception:
                                pass

        # Create the orchestrator agent
        agent = create_mortgage_broker_orchestrator()

        # Run the agent with the user message
        result = await Runner.run(agent, message, session=session)

        # Clean up temporary files after agent processing
        for tmp_path in temp_paths:
            try:
                import os

                os.unlink(tmp_path)
                logger.debug(f"Cleaned up temp file: {tmp_path}")
            except Exception as cleanup_error:
                logger.warning(
                    f"Failed to cleanup temp file {tmp_path}: {cleanup_error}"
                )

        # Update session metadata
        if thread_id in session_manager._session_metadata:
            session_manager._session_metadata[thread_id]["message_count"] += (
                2  # User + assistant
            )

        return ChatResponse(
            response=result.final_output,
            thread_id=thread_id,
            files_processed=files_processed_count
            if files_processed_count > 0
            else None,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Chat endpoint failed: {e}")
        raise HTTPException(status_code=500, detail=f"שגיאה בעיבוד ההודעה: {str(e)}")
