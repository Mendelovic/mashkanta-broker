from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum


class DocumentType(str, Enum):
    """Supported document types for financial analysis."""
    PAYSLIP = "payslip"
    ANNUAL_TAX_CERTIFICATE = "annual_tax_certificate"
    BANK_STATEMENT = "bank_statement"
    LOAN_STATEMENT = "loan_statement"
    UNKNOWN = "unknown"


class DocumentClassificationResult(BaseModel):
    """Result of document classification."""
    document_type: DocumentType
    confidence: float = Field(..., ge=0.0, le=1.0)
    reasoning: Optional[str] = None


class PayslipData(BaseModel):
    """Extracted data from a payslip document."""
    gross_salary: Optional[float] = Field(None, ge=0)
    net_salary: Optional[float] = Field(None, ge=0)
    employee_name: Optional[str] = None
    pay_period: Optional[str] = None
    employer_name: Optional[str] = None
    confidence: float = Field(..., ge=0.0, le=1.0)


class AnnualTaxCertificateData(BaseModel):
    """Extracted data from an annual tax certificate (Form 106 or equivalent)."""
    annual_gross_income: Optional[float] = Field(None, ge=0)
    annual_net_income: Optional[float] = Field(None, ge=0)
    tax_year: Optional[int] = Field(None, ge=1900, le=2100)
    total_tax_paid: Optional[float] = Field(None, ge=0)
    employee_name: Optional[str] = None
    confidence: float = Field(..., ge=0.0, le=1.0)


class BankStatementData(BaseModel):
    """Extracted data from a bank statement."""
    account_balance: Optional[float] = None
    monthly_deposits: List[float] = Field(default_factory=list)
    monthly_expenses: List[float] = Field(default_factory=list)
    average_monthly_income: Optional[float] = Field(None, ge=0)
    account_holder: Optional[str] = None
    statement_period: Optional[str] = None
    confidence: float = Field(..., ge=0.0, le=1.0)


class DocumentAnalysis(BaseModel):
    """Complete analysis result for a single document."""
    filename: str
    document_type: DocumentType
    analysis: Dict[str, Any]
    confidence: float = Field(..., ge=0.0, le=1.0)
    chunks_processed: Optional[int] = Field(default=None, ge=1)
    total_length: Optional[int] = Field(default=None, ge=0)
    error: Optional[str] = None


class StructuredData(BaseModel):
    """Structured data extracted from Azure Document Intelligence."""
    key_value_pairs: List[Dict[str, str]] = Field(default_factory=list)
    tables: List[Dict[str, Any]] = Field(default_factory=list)
    fields: Dict[str, Any] = Field(default_factory=dict)