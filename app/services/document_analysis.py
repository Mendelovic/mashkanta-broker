import logging
from typing import List, Dict, Any
from ..models.document import DocumentAnalysis, FinancialData
from ..utils.text_processing import chunk_document_content
from .gpt_service import GPTService
from .document_processor import DocumentProcessorService


logger = logging.getLogger(__name__)


class DocumentAnalysisService:
    """Service for analyzing documents and extracting financial data."""

    def __init__(
        self, gpt_service: GPTService, document_processor: DocumentProcessorService
    ):
        self.gpt_service = gpt_service
        self.document_processor = document_processor

    async def analyze_document(self, file_path: str, filename: str) -> DocumentAnalysis:
        """
        Analyze a single document and extract financial data.

        Args:
            file_path: Path to the document file
            filename: Original filename for reference

        Returns:
            DocumentAnalysis object with extracted data
        """
        try:
            # Extract text and structured data from document
            content, structured_data = await self.document_processor.process_document(
                file_path
            )
            structured_data_dict = structured_data.model_dump()

            # Extract financial data directly - no classification needed
            chunks = chunk_document_content(content)
            if len(chunks) > 1:
                logger.info(
                    f"Document {filename} split into {len(chunks)} chunks for processing"
                )
                financial_data = await self._process_document_chunks(
                    chunks, structured_data_dict
                )
            else:
                financial_data = await self.gpt_service.extract_financial_data(
                    content, structured_data_dict
                )

            return DocumentAnalysis(
                filename=filename,
                financial_data=financial_data,
                confidence=financial_data.confidence,
                chunks_processed=len(chunks) if len(chunks) > 1 else None,
                total_length=len(content) if len(chunks) > 1 else None,
            )

        except Exception as e:
            logger.error(f"Document analysis failed for {filename}: {e}")
            return DocumentAnalysis(
                filename=filename,
                financial_data=FinancialData(confidence=0.0),
                confidence=0.0,
                error=str(e),
            )

    async def _process_document_chunks(
        self,
        chunks: List[str],
        structured_data: Dict[str, Any],
    ) -> FinancialData:
        """Process multiple document chunks and merge results intelligently."""
        all_results = []

        for i, chunk in enumerate(chunks):
            chunk_result = await self.gpt_service.extract_financial_data(
                chunk, structured_data
            )
            all_results.append(chunk_result)

        # Merge results from all chunks intelligently
        merged_result = self._merge_chunk_results(all_results, chunks)

        return merged_result

    def _merge_chunk_results(
        self,
        all_results: List[FinancialData],
        chunks: List[str],
    ) -> FinancialData:
        """Merge results from multiple chunks by taking best data from each."""
        if not all_results:
            return FinancialData(confidence=0.0)

        # Find the chunk with highest confidence for base data
        best_result = max(all_results, key=lambda x: x.confidence)

        # Merge additional data from other chunks
        merged_data = {}

        # Take best non-null values for single-value fields
        single_value_fields = [
            "person_name",
            "monthly_gross_salary",
            "monthly_net_salary",
            "annual_gross_income",
            "annual_net_income",
            "employer_name",
            "pay_period",
            "tax_year",
            "total_tax_paid",
            "account_balance",
            "average_monthly_income",
        ]

        for field in single_value_fields:
            # Find the best value across all results
            best_value = None
            best_confidence = 0

            for result in all_results:
                value = getattr(result, field, None)
                if value is not None and result.confidence > best_confidence:
                    best_value = value
                    best_confidence = result.confidence

            merged_data[field] = best_value

        # Aggregate list fields (deposits and expenses)
        all_deposits = []
        all_expenses = []
        all_data_sources = set()

        for result in all_results:
            if result.monthly_deposits:
                all_deposits.extend(result.monthly_deposits)
            if result.monthly_expenses:
                all_expenses.extend(result.monthly_expenses)
            if result.data_sources:
                all_data_sources.update(result.data_sources)

        merged_data["monthly_deposits"] = all_deposits
        merged_data["monthly_expenses"] = all_expenses
        merged_data["data_sources"] = list(all_data_sources)

        # Use best overall confidence
        merged_data["confidence"] = max(r.confidence for r in all_results)

        return FinancialData(**merged_data)
