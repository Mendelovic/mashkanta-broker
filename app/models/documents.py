"""Pydantic models for persisted document artifacts."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class DocumentKeyValue(BaseModel):
    """Represents a key-value pair extracted from a document."""

    key: str = ""
    value: str = ""
    confidence: Optional[float] = None
    page_number: Optional[int] = Field(default=None, ge=1)
    field_path: Optional[str] = None


class DocumentTableCell(BaseModel):
    """Represents a single cell inside an extracted table."""

    row_index: int = Field(ge=0)
    column_index: int = Field(ge=0)
    content: str = ""


class DocumentTable(BaseModel):
    """Represents a summary of a detected table."""

    row_count: Optional[int] = Field(default=None, ge=0)
    column_count: Optional[int] = Field(default=None, ge=0)
    rows: List[List[str]] = Field(default_factory=list)
    confidence: Optional[float] = None


class DocumentExtract(BaseModel):
    """Structured payload captured from OCR analysis."""

    locale: Optional[str] = None
    text_preview: Optional[str] = None
    text_truncated: bool = False
    summary: dict[str, str] = Field(default_factory=dict)
    key_value_pairs: List[DocumentKeyValue] = Field(default_factory=list)
    tables: List[DocumentTable] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class DocumentArtifact(BaseModel):
    """Persisted reference to an uploaded document."""

    id: str
    display_name: str
    original_filename: Optional[str] = None
    mime_type: Optional[str] = None
    document_type: str = "unknown"
    uploaded_at: datetime
    extracted_at: Optional[datetime] = None
    extract: Optional[DocumentExtract] = None


class DocumentArtifactSummary(BaseModel):
    """Lightweight view of a document artifact suitable for agent prompts."""

    id: str
    display_name: str
    document_type: str
    uploaded_at: datetime
    extracted_at: Optional[datetime] = None
    mime_type: Optional[str] = None
    locale: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)
    key_value_pairs: List[DocumentKeyValue] = Field(default_factory=list)
    tables: List[DocumentTable] = Field(default_factory=list)
    text_preview: Optional[str] = None
    text_truncated: bool = False
