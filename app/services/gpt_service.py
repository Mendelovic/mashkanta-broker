import json
import logging
from typing import Tuple, Dict, Any
from openai import AsyncOpenAI

from ..config import settings
from ..models import DocumentType, DocumentClassificationResult


logger = logging.getLogger(__name__)


class GPTService:
    """Service for interacting with OpenAI GPT models."""
    
    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
    
    async def classify_document_type(
        self, 
        document_content: str, 
        structured_data: Dict[str, Any]
    ) -> Tuple[DocumentType, float]:
        """Classify Hebrew financial document type using GPT."""
        
        # Prepare structured data summary for GPT
        key_value_summary = ""
        if structured_data.get("key_value_pairs"):
            key_value_summary = "\n".join([
                f"Key: '{kv.get('key', '')}' -> Value: '{kv.get('value', '')}'"
                for kv in structured_data["key_value_pairs"][:10]  # First 10 pairs
            ])
        
        table_summary = ""
        if structured_data.get("tables"):
            table_summary = f"Found {len(structured_data['tables'])} tables with content"
        
        # Use first chunk for classification (will be handled by text processing service)
        from ..utils.text_processing import chunk_document_content
        chunks = chunk_document_content(document_content, max_chunk_size=4000)
        representative_content = chunks[0]
        if len(chunks) > 1:
            middle_chunk = chunks[len(chunks) // 2] if len(chunks) > 2 else chunks[-1]
            representative_content = f"{chunks[0]}\n\n[...middle section...]\n\n{middle_chunk[:1000]}"
        
        prompt = self._build_classification_prompt(
            representative_content, key_value_summary, table_summary
        )
        
        try:
            response = await self.client.chat.completions.create(
                model=settings.gpt_model,
                messages=[
                    {
                        "role": "system", 
                        "content": "You are an expert in Israeli financial documents. Analyze documents and classify them accurately."
                    },
                    {"role": "user", "content": prompt}
                ],
            )
            
            response_content = response.choices[0].message.content
            if response_content is None:
                logger.error("GPT returned None content")
                return DocumentType.UNKNOWN, 0.0
            
            logger.info(f"GPT classification response: {response_content}")
            
            result = self._parse_classification_response(response_content)
            document_type = DocumentType(result.get("document_type", "unknown"))
            confidence = float(result.get("confidence", 0.0))
            
            return document_type, confidence
            
        except Exception as e:
            logger.error(f"GPT classification error: {e}")
            return DocumentType.UNKNOWN, 0.0
    
    async def extract_financial_data(
        self, 
        document_type: DocumentType, 
        content: str, 
        structured_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Extract financial data from Hebrew documents using GPT."""
        
        # Prepare Azure structured data for GPT
        azure_data_summary = {
            "key_value_pairs": [],
            "tables": [],
            "fields": structured_data.get("fields", {})
        }
        
        # Format key-value pairs
        if structured_data.get("key_value_pairs"):
            for kv in structured_data["key_value_pairs"]:
                azure_data_summary["key_value_pairs"].append({
                    "key": kv.get("key", ""),
                    "value": kv.get("value", "")
                })
        
        # Format tables
        if structured_data.get("tables"):
            for table in structured_data["tables"]:
                table_data = []
                for cell in table.get("cells", []):
                    table_data.append({
                        "row": cell.get("row_index", 0),
                        "col": cell.get("column_index", 0),
                        "content": cell.get("content", "")
                    })
                azure_data_summary["tables"].append(table_data)
        
        prompt = self._build_extraction_prompt(document_type, content, azure_data_summary)
        if not prompt:
            return {"confidence": 0.0, "error": "Unknown document type"}
        
        try:
            response = await self.client.chat.completions.create(
                model=settings.gpt_model,
                messages=[
                    {
                        "role": "system", 
                        "content": "You are an expert at extracting financial data from Hebrew documents. Be precise with numbers and return valid JSON only."
                    },
                    {"role": "user", "content": prompt}
                ],
            )
            
            response_content = response.choices[0].message.content
            if response_content is None:
                logger.error("GPT returned None content for extraction")
                return {"confidence": 0.0, "error": "No response content"}
            
            logger.info(f"GPT extraction response: {response_content}")
            
            return self._parse_extraction_response(response_content)
            
        except Exception as e:
            logger.error(f"GPT extraction error: {e}")
            return {"confidence": 0.0, "error": str(e)}
    
    def _build_classification_prompt(
        self, 
        content: str, 
        key_value_summary: str, 
        table_summary: str
    ) -> str:
        """Build the prompt for document classification."""
        return f"""
Classify this Hebrew financial document. Analyze the content and determine the document type.

Document Content (representative sections):
{content}

Key-Value Pairs Found:
{key_value_summary}

Table Information:
{table_summary}

Possible document types:
1. payslip - תלוש שכר (monthly salary statement)
2. annual_tax_certificate - תעודת מס שנתית (Form 106 or replacement - במקום טופס 106)  
3. bank_statement - דף חשבון בנק (bank account statement)
4. loan_statement - דוח הלוואה (loan statement)

Return ONLY a JSON object with:
{{
    "document_type": "one of the types above",
    "confidence": "number between 0.0 and 1.0",
    "reasoning": "brief explanation in English"
}}
"""
    
    def _build_extraction_prompt(
        self, 
        document_type: DocumentType, 
        content: str, 
        azure_data_summary: Dict[str, Any]
    ) -> str:
        """Build the prompt for data extraction based on document type."""
        
        if document_type == DocumentType.PAYSLIP:
            return f"""
Extract salary information from this Hebrew payslip.

Document Content:
{content}

Azure Extracted Data:
Key-Value Pairs: {azure_data_summary["key_value_pairs"]}
Tables: {azure_data_summary["tables"]}

Extract the following fields:
- gross_salary: Monthly gross salary (שכר ברוטו)
- net_salary: Monthly net salary (שכר נטו, לתשלום)
- employee_name: Employee name
- pay_period: Pay period/month
- employer_name: Employer name

Ignore year-to-date totals, focus on monthly amounts.
Return ONLY JSON:
{{
    "gross_salary": number or null,
    "net_salary": number or null,
    "employee_name": "string or null",
    "pay_period": "string or null",
    "employer_name": "string or null",
    "confidence": number between 0.0 and 1.0 based on data clarity and certainty
}}
"""
        
        elif document_type == DocumentType.ANNUAL_TAX_CERTIFICATE:
            return f"""
Extract annual tax information from this Hebrew document (Form 106 or replacement).

Document Content:
{content}

Azure Extracted Data:
Key-Value Pairs: {azure_data_summary["key_value_pairs"]}
Tables: {azure_data_summary["tables"]}

Extract:
- annual_gross_income: Annual gross income (הכנסה שנתית, סה״כ ברוטו)
- annual_net_income: Annual net income (if available)
- tax_year: Year (שנת המס, לשנת)
- total_tax_paid: Total tax paid (מס שנתי, סה״כ מס)
- employee_name: Employee name

Return ONLY JSON:
{{
    "annual_gross_income": number or null,
    "annual_net_income": number or null,
    "tax_year": number or null,
    "total_tax_paid": number or null,
    "employee_name": "string or null",
    "confidence": number between 0.0 and 1.0 based on data clarity and certainty
}}
"""
        
        elif document_type == DocumentType.BANK_STATEMENT:
            return f"""
Extract bank statement information from this Hebrew document.

Document Content:
{content}

Azure Extracted Data:
Key-Value Pairs: {azure_data_summary["key_value_pairs"]}
Tables: {azure_data_summary["tables"]}

Extract:
- account_balance: Current balance (יתרה נוכחית)
- monthly_deposits: List of deposit amounts (זיכוי, הפקדה)
- monthly_expenses: List of expense amounts (חיוב)
- account_holder: Account holder name
- statement_period: Statement period

Return ONLY JSON:
{{
    "account_balance": number or null,
    "monthly_deposits": [list of numbers],
    "monthly_expenses": [list of numbers],
    "average_monthly_income": number or null,
    "account_holder": "string or null",
    "statement_period": "string or null",
    "confidence": number between 0.0 and 1.0 based on data clarity and certainty
}}
"""
        
        return ""
    
    def _parse_classification_response(self, response_content: str) -> Dict[str, Any]:
        """Parse GPT classification response."""
        try:
            # Strip markdown code blocks if present
            cleaned_content = response_content.strip()
            if cleaned_content.startswith('```json'):
                cleaned_content = cleaned_content[7:]  # Remove ```json
            if cleaned_content.endswith('```'):
                cleaned_content = cleaned_content[:-3]  # Remove ```
            cleaned_content = cleaned_content.strip()
            
            return json.loads(cleaned_content)
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
            logger.error(f"Raw response: '{response_content}'")
            return {"document_type": "unknown", "confidence": 0.0}
    
    def _parse_extraction_response(self, response_content: str) -> Dict[str, Any]:
        """Parse GPT extraction response."""
        try:
            # Strip markdown code blocks if present
            cleaned_content = response_content.strip()
            if cleaned_content.startswith('```json'):
                cleaned_content = cleaned_content[7:]  # Remove ```json
            if cleaned_content.endswith('```'):
                cleaned_content = cleaned_content[:-3]  # Remove ```
            cleaned_content = cleaned_content.strip()
            
            return json.loads(cleaned_content)
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error in extraction: {e}")
            logger.error(f"Raw extraction response: '{response_content}'")
            return {"confidence": 0.0, "error": f"JSON decode failed: {e}"}