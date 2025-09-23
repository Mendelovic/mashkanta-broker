"""Dependency helpers for FastAPI routes and tools."""

from functools import lru_cache

from .services import DocumentAnalysisService


@lru_cache()
def get_document_analysis_service() -> DocumentAnalysisService:
    """Return a singleton Azure Document Intelligence wrapper."""
    return DocumentAnalysisService()


__all__ = ["get_document_analysis_service"]
