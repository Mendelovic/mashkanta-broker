from functools import lru_cache
from .services import (
    GPTService,
    DocumentProcessorService,
    DocumentAnalysisService,
)


@lru_cache()
def get_gpt_service() -> GPTService:
    """Get singleton instance of GPT service."""
    return GPTService()


@lru_cache()
def get_document_processor_service() -> DocumentProcessorService:
    """Get singleton instance of document processor service."""
    return DocumentProcessorService()


@lru_cache()
def get_document_analysis_service() -> DocumentAnalysisService:
    """Get singleton instance of document analysis service."""
    gpt_service = get_gpt_service()
    document_processor = get_document_processor_service()
    return DocumentAnalysisService(gpt_service, document_processor)
