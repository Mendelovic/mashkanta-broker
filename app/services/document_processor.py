import logging
from typing import Optional
from azure.core.credentials import AzureKeyCredential
from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import DocumentAnalysisFeature

from ..config import settings
from ..models import StructuredData


logger = logging.getLogger(__name__)


class DocumentProcessorService:
    """Service for processing documents with Azure Document Intelligence."""

    def __init__(self):
        self.client = self._init_client()

    def _init_client(self) -> Optional[DocumentIntelligenceClient]:
        """Initialize Azure Document Intelligence client."""
        if not settings.azure_doc_intel_endpoint or not settings.azure_doc_intel_key:
            logger.warning("Azure Document Intelligence credentials not configured")
            return None

        try:
            return DocumentIntelligenceClient(
                endpoint=settings.azure_doc_intel_endpoint,
                credential=AzureKeyCredential(settings.azure_doc_intel_key),
            )
        except Exception as e:
            logger.error(
                f"Failed to initialize Azure Document Intelligence client: {e}"
            )
            return None

    def is_available(self) -> bool:
        """Check if the service is available."""
        return self.client is not None

    async def process_document(self, file_path: str) -> tuple[str, StructuredData]:
        """
        Process a document and extract text content and structured data.

        Args:
            file_path: Path to the PDF file to process

        Returns:
            Tuple of (text_content, structured_data)

        Raises:
            Exception: If document processing fails
        """
        if not self.client:
            raise Exception("Azure Document Intelligence client not available")

        try:
            with open(file_path, "rb") as f:
                poller = self.client.begin_analyze_document(
                    model_id="prebuilt-layout",
                    body=f,
                    features=[DocumentAnalysisFeature.KEY_VALUE_PAIRS],
                    locale="he-IL",
                )
                result = poller.result()

            # Extract content and structured data
            content = result.content or ""
            structured_data = self._extract_structured_data(result)

            return content, structured_data

        except Exception as e:
            logger.error(f"Document processing failed for {file_path}: {e}")
            raise Exception(f"OCR failed: {str(e)}")

    def _extract_structured_data(self, result) -> StructuredData:
        """Extract structured data from Azure Document Intelligence result."""
        structured_data = StructuredData()

        # Extract key-value pairs
        if result.key_value_pairs:
            for kv in result.key_value_pairs:
                structured_data.key_value_pairs.append(
                    {
                        "key": kv.key.content if kv.key else "",
                        "value": kv.value.content if kv.value else "",
                    }
                )

        # Extract tables
        if result.tables:
            for table in result.tables:
                table_data = {"cells": []}
                if table.cells:
                    for cell in table.cells:
                        table_data["cells"].append(
                            {
                                "row_index": cell.row_index,
                                "column_index": cell.column_index,
                                "content": cell.content,
                            }
                        )
                structured_data.tables.append(table_data)

        # Extract fields
        if hasattr(result, "documents") and result.documents:
            structured_data.fields = getattr(result.documents[0], "fields", {})

        return structured_data
