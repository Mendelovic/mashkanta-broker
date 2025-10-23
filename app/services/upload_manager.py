"""Utilities for handling chat file uploads."""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
from dataclasses import dataclass
from typing import List, Optional

from fastapi import HTTPException, UploadFile

from ..config import settings

logger = logging.getLogger(__name__)


@dataclass
class UploadProcessingResult:
    message_prefix: str
    temp_paths: List[str]
    files_processed: int


def _close_uploads(files: Optional[list[UploadFile]]) -> None:
    for uploaded in files or []:
        try:
            uploaded.file.close()
        except Exception:  # pragma: no cover - defensive
            pass


def process_uploads(files: Optional[list[UploadFile]]) -> UploadProcessingResult:
    candidate_files = [
        file for file in files or [] if file and getattr(file, "filename", None)
    ]
    if not candidate_files:
        _close_uploads(files)
        return UploadProcessingResult(
            message_prefix="", temp_paths=[], files_processed=0
        )

    if len(candidate_files) > settings.max_files_per_request:
        _close_uploads(files)
        raise HTTPException(
            status_code=400,
            detail=f"You can upload up to {settings.max_files_per_request} files per request.",
        )

    upload_lines: list[str] = []
    temp_paths: list[str] = []

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
            upload_lines.append(f"- {display_name}: {temp_path}")
            logger.info(
                "Stored uploaded document for analysis: %s -> %s",
                uploaded.filename,
                temp_path,
            )
    finally:
        _close_uploads(files)

    message_prefix = ""
    if upload_lines:
        message_prefix = "\n[DOCUMENT_UPLOADS]\n" + "\n".join(upload_lines) + "\n\n"

    return UploadProcessingResult(
        message_prefix=message_prefix,
        temp_paths=temp_paths,
        files_processed=len(temp_paths),
    )


def cleanup_temp_paths(temp_paths: List[str]) -> None:
    for temp_path in temp_paths:
        try:
            os.unlink(temp_path)
            logger.debug("Removed temp document: %s", temp_path)
        except OSError:
            logger.warning("Failed to remove temp document: %s", temp_path)


__all__ = ["UploadProcessingResult", "process_uploads", "cleanup_temp_paths"]
