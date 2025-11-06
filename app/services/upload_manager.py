"""Utilities for handling chat file uploads."""

from __future__ import annotations

import logging
import mimetypes
import os
import shutil
import tempfile
import uuid
from dataclasses import dataclass
from typing import List, Optional

from fastapi import HTTPException, UploadFile

from ..config import settings

logger = logging.getLogger(__name__)


@dataclass
class UploadProcessingResult:
    temp_paths: List[str]
    files_processed: int
    documents: List["UploadedDocument"]


@dataclass
class UploadedDocument:
    document_id: str
    temp_path: str
    display_name: str
    original_filename: Optional[str]
    mime_type: Optional[str]
    document_type: str = "unknown"


def _close_uploads(files: Optional[list[UploadFile]]) -> None:
    for uploaded in files or []:
        try:
            uploaded.file.close()
        except Exception:  # pragma: no cover - defensive
            pass


def _infer_document_type(filename: str, mime_type: Optional[str]) -> str:
    lowered = filename.lower()
    if any(
        keyword in lowered for keyword in ("pay", "salary", "tlush", "תלוש", "תשלום")
    ):
        return "payslip"
    if any(
        keyword in lowered for keyword in ("bank", "statement", "חשבונ", "עובר ושב")
    ):
        return "bank_statement"
    if any(keyword in lowered for keyword in ("appraisal", "assessment", "שמא")):
        return "appraisal"
    if any(keyword in lowered for keyword in ("contract", "agreement", "הסכם", "חוזה")):
        return "contract"
    if mime_type and mime_type.startswith("image/"):
        return "image"
    return "unknown"


def process_uploads(files: Optional[list[UploadFile]]) -> UploadProcessingResult:
    candidate_files = [
        file for file in files or [] if file and getattr(file, "filename", None)
    ]
    if not candidate_files:
        _close_uploads(files)
        return UploadProcessingResult(
            temp_paths=[],
            files_processed=0,
            documents=[],
        )

    if len(candidate_files) > settings.max_files_per_request:
        _close_uploads(files)
        raise HTTPException(
            status_code=400,
            detail=f"You can upload up to {settings.max_files_per_request} files per request.",
        )

    temp_paths: list[str] = []
    documents: list[UploadedDocument] = []

    try:
        for uploaded in candidate_files:
            filename = uploaded.filename or ""
            lowered = filename.lower()
            if not lowered.endswith((".pdf", ".png", ".jpg", ".jpeg")):
                raise HTTPException(
                    status_code=400,
                    detail="Only PDF and image files (PNG/JPG) are supported.",
                )

            suffix = os.path.splitext(lowered)[1] or ".pdf"
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                shutil.copyfileobj(uploaded.file, tmp)
                temp_path = tmp.name
                temp_paths.append(temp_path)

            display_name = uploaded.filename or os.path.basename(temp_path)
            mime_type = mimetypes.guess_type(display_name)[0]
            document_id = uuid.uuid4().hex
            document_type = _infer_document_type(display_name, mime_type)
            documents.append(
                UploadedDocument(
                    document_id=document_id,
                    temp_path=temp_path,
                    display_name=display_name,
                    original_filename=uploaded.filename,
                    mime_type=mime_type,
                    document_type=document_type,
                )
            )
            logger.info(
                "Stored uploaded document for analysis",
                extra={
                    "original_filename": uploaded.filename,
                    "temp_path": temp_path,
                    "document_id": document_id,
                    "document_type": document_type,
                },
            )
    finally:
        _close_uploads(files)

    return UploadProcessingResult(
        temp_paths=temp_paths,
        files_processed=len(temp_paths),
        documents=documents,
    )


def cleanup_temp_paths(temp_paths: List[str]) -> None:
    for temp_path in temp_paths:
        try:
            os.unlink(temp_path)
            logger.debug("Removed temp document: %s", temp_path)
        except OSError:
            logger.warning("Failed to remove temp document: %s", temp_path)


__all__ = [
    "UploadProcessingResult",
    "UploadedDocument",
    "process_uploads",
    "cleanup_temp_paths",
]
