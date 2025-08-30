import logging
from typing import List, Dict, Any
from ..models import DocumentAnalysis, DocumentType
from ..utils.text_processing import chunk_document_content
from .gpt_service import GPTService
from .document_processor import DocumentProcessorService


logger = logging.getLogger(__name__)


class DocumentAnalysisService:
    """Service for analyzing documents and extracting financial data."""
    
    def __init__(self, gpt_service: GPTService, document_processor: DocumentProcessorService):
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
            content, structured_data = await self.document_processor.process_document(file_path)
            structured_data_dict = structured_data.model_dump()
            
            # Classify document type
            doc_type, confidence = await self.gpt_service.classify_document_type(
                content, structured_data_dict
            )
            
            # Extract financial data using chunking strategy for longer documents
            chunks = chunk_document_content(content)
            if len(chunks) > 1:
                logger.info(f"Document {filename} split into {len(chunks)} chunks for processing")
                analysis_data = await self._process_document_chunks(
                    doc_type, chunks, structured_data_dict
                )
            else:
                analysis_data = await self.gpt_service.extract_financial_data(
                    doc_type, content, structured_data_dict
                )
            
            return DocumentAnalysis(
                filename=filename,
                document_type=doc_type,
                analysis=analysis_data,
                confidence=confidence,
                chunks_processed=len(chunks) if len(chunks) > 1 else None,
                total_length=len(content) if len(chunks) > 1 else None
            )
            
        except Exception as e:
            logger.error(f"Document analysis failed for {filename}: {e}")
            return DocumentAnalysis(
                filename=filename,
                document_type=DocumentType.UNKNOWN,
                analysis={"error": str(e)},
                confidence=0.0,
                error=str(e)
            )
    
    async def _process_document_chunks(
        self, 
        document_type: DocumentType, 
        chunks: List[str], 
        structured_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Process multiple document chunks and merge results intelligently."""
        all_results = []
        
        for i, chunk in enumerate(chunks):
            chunk_result = await self.gpt_service.extract_financial_data(
                document_type, chunk, structured_data
            )
            chunk_result["chunk_index"] = i
            all_results.append(chunk_result)
        
        # Merge results from all chunks intelligently
        merged_result = self._merge_chunk_results(document_type, all_results, chunks)
        
        return merged_result
    
    def _merge_chunk_results(
        self, 
        document_type: DocumentType, 
        all_results: List[Dict[str, Any]], 
        chunks: List[str]
    ) -> Dict[str, Any]:
        """Merge results from multiple chunks based on document type."""
        merged_result: Dict[str, Any] = {"confidence": 0.0}
        
        if document_type == DocumentType.PAYSLIP:
            # For payslips, find the single best chunk based on overall confidence
            if all_results:
                best_result_chunk = max(all_results, key=lambda x: x.get("confidence", 0))
                # Use all data from that best chunk
                merged_result = {
                    "gross_salary": best_result_chunk.get("gross_salary"),
                    "net_salary": best_result_chunk.get("net_salary"),
                    "employee_name": best_result_chunk.get("employee_name"),
                    "pay_period": best_result_chunk.get("pay_period"),
                    "employer_name": best_result_chunk.get("employer_name"),
                    "confidence": best_result_chunk.get("confidence", 0)
                }
        
        elif document_type == DocumentType.ANNUAL_TAX_CERTIFICATE:
            # For tax certificates, take best result overall
            if all_results:
                best_result = max(all_results, key=lambda x: x.get("confidence", 0))
                merged_result = dict(best_result)
        
        elif document_type == DocumentType.BANK_STATEMENT:
            # For bank statements, aggregate deposits and expenses from all chunks
            all_deposits = []
            all_expenses = []
            best_balance = None
            best_confidence = 0
            
            for result in all_results:
                if result.get("monthly_deposits"):
                    all_deposits.extend(result["monthly_deposits"])
                if result.get("monthly_expenses"):
                    all_expenses.extend(result["monthly_expenses"])
                if result.get("account_balance") and result.get("confidence", 0) > best_confidence:
                    best_balance = result["account_balance"]
                    best_confidence = result.get("confidence", 0)
            
            merged_result = {
                "account_balance": best_balance,
                "monthly_deposits": all_deposits,
                "monthly_expenses": all_expenses,
                "average_monthly_income": sum(all_deposits) / len(all_deposits) if all_deposits else None,
                "confidence": max(r.get("confidence", 0) for r in all_results) if all_results else 0
            }
        
        # Add chunk processing info
        merged_result["chunks_processed"] = len(chunks)
        merged_result["total_length"] = sum(len(chunk) for chunk in chunks)
        
        return merged_result