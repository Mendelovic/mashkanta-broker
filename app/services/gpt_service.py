import json
import logging
from typing import Dict, Any
from openai import AsyncOpenAI

from ..config import settings
from ..models.document import FinancialData


logger = logging.getLogger(__name__)


class GPTService:
    """Service for interacting with OpenAI GPT models."""

    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)

    async def extract_financial_data(
        self, document_content: str, structured_data: Dict[str, Any]
    ) -> FinancialData:
        """Extract financial data from any Hebrew document using GPT."""

        # Prepare structured data summary for GPT
        key_value_summary = ""
        if structured_data.get("key_value_pairs"):
            key_value_summary = "\n".join(
                [
                    f"Key: '{kv.get('key', '')}' -> Value: '{kv.get('value', '')}'"
                    for kv in structured_data["key_value_pairs"][
                        :15
                    ]  # More pairs for better extraction
                ]
            )

        table_summary = ""
        if structured_data.get("tables"):
            tables_content = []
            for i, table in enumerate(structured_data["tables"][:3]):  # First 3 tables
                table_data = []
                for cell in table.get("cells", [])[:20]:  # First 20 cells per table
                    table_data.append(
                        f"Row {cell.get('row_index', 0)}, Col {cell.get('column_index', 0)}: {cell.get('content', '')}"
                    )
                tables_content.append(f"Table {i + 1}:\n" + "\n".join(table_data))
            table_summary = "\n\n".join(tables_content)

        # Use first chunk for extraction
        from ..utils.text_processing import chunk_document_content

        chunks = chunk_document_content(document_content, max_chunk_size=6000)
        representative_content = chunks[0]
        if len(chunks) > 1:
            middle_chunk = chunks[len(chunks) // 2] if len(chunks) > 2 else chunks[-1]
            representative_content = (
                f"{chunks[0]}\n\n[...middle section...]\n\n{middle_chunk[:1500]}"
            )

        prompt = self._build_extraction_prompt(
            representative_content, key_value_summary, table_summary
        )

        try:
            response = await self.client.chat.completions.create(
                model="gpt-5-mini",
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert at extracting financial data from Hebrew documents. Extract all available financial information regardless of document type.",
                    },
                    {"role": "user", "content": prompt},
                ],
            )

            response_content = response.choices[0].message.content
            if response_content is None:
                logger.error("GPT returned None content for extraction")
                return FinancialData(confidence=0.0)

            logger.info(f"GPT extraction response: {response_content}")

            return self._parse_financial_data_response(response_content)

        except Exception as e:
            logger.error(f"GPT extraction error: {e}")
            return FinancialData(confidence=0.0)

    def _build_extraction_prompt(
        self, content: str, key_value_summary: str, table_summary: str
    ) -> str:
        """Build the prompt for financial data extraction from any document."""
        return f"""
Extract ALL available financial information from this Hebrew document. Don't worry about document type - just extract any financial data you can find.

Document Content:
{content}

Key-Value Pairs Found:
{key_value_summary}

Table Content:
{table_summary}

Extract ANY available financial information including:
- Personal info: person_name
- Salary: monthly_gross_salary, monthly_net_salary, employer_name, pay_period
- Annual income: annual_gross_income, annual_net_income, tax_year, total_tax_paid
- Banking: account_balance, monthly_deposits, monthly_expenses, average_monthly_income
- Any other financial amounts or dates

Note what types of data you found in data_sources (e.g., ["salary_info", "tax_data", "bank_transactions"])

Return ONLY JSON:
{{
    "person_name": "string or null",
    "monthly_gross_salary": number or null,
    "monthly_net_salary": number or null,
    "annual_gross_income": number or null,
    "annual_net_income": number or null,
    "employer_name": "string or null",
    "pay_period": "string or null",
    "tax_year": number or null,
    "total_tax_paid": number or null,
    "account_balance": number or null,
    "monthly_deposits": [list of numbers],
    "monthly_expenses": [list of numbers],
    "average_monthly_income": number or null,
    "confidence": number between 0.0 and 1.0,
    "data_sources": ["list of data types found"]
}}
"""

    def _parse_financial_data_response(self, response_content: str) -> FinancialData:
        """Parse GPT financial data extraction response."""
        try:
            # Strip markdown code blocks if present
            cleaned_content = response_content.strip()
            if cleaned_content.startswith("```json"):
                cleaned_content = cleaned_content[7:]  # Remove ```json
            if cleaned_content.endswith("```"):
                cleaned_content = cleaned_content[:-3]  # Remove ```
            cleaned_content = cleaned_content.strip()

            data = json.loads(cleaned_content)
            return FinancialData(**data)
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"JSON decode error in extraction: {e}")
            logger.error(f"Raw extraction response: '{response_content}'")
            return FinancialData(confidence=0.0)
