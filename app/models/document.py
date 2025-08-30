from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class FinancialData(BaseModel):
    """Unified financial data extracted from any document."""

    # Personal info
    person_name: Optional[str] = None

    # Salary/Income data
    monthly_gross_salary: Optional[float] = None
    monthly_net_salary: Optional[float] = None
    annual_gross_income: Optional[float] = None
    annual_net_income: Optional[float] = None

    # Employment info
    employer_name: Optional[str] = None
    pay_period: Optional[str] = None
    tax_year: Optional[int] = None

    # Banking info
    account_balance: Optional[float] = None
    monthly_deposits: List[float] = Field(default_factory=list)
    monthly_expenses: List[float] = Field(default_factory=list)
    average_monthly_income: Optional[float] = None

    # Tax info
    total_tax_paid: Optional[float] = None

    # Metadata
    confidence: float = Field(..., ge=0.0, le=1.0)
    data_sources: List[str] = Field(
        default_factory=list
    )  # What types of data were found


class DocumentAnalysis(BaseModel):
    """Complete analysis result for a single document."""

    filename: str
    financial_data: FinancialData
    confidence: float = Field(..., ge=0.0, le=1.0)
    chunks_processed: Optional[int] = Field(default=None, ge=1)
    total_length: Optional[int] = Field(default=None, ge=0)
    error: Optional[str] = None


class StructuredData(BaseModel):
    """Structured data extracted from Azure Document Intelligence."""

    key_value_pairs: List[Dict[str, str]] = Field(default_factory=list)
    tables: List[Dict[str, Any]] = Field(default_factory=list)
    fields: Dict[str, Any] = Field(default_factory=dict)
