from typing import List, Optional
from pydantic import BaseModel, Field
from .document import DocumentAnalysis


class IncomeConsistencyCheck(BaseModel):
    """Results of income consistency validation between documents."""
    status: str = Field(..., description="Status: consistent, inconsistent, or unknown")
    details: List[str] = Field(default_factory=list)


class ValidationResults(BaseModel):
    """Cross-validation results for financial data across documents."""
    income_consistency: IncomeConsistencyCheck
    recommended_income: Optional[float] = Field(None, ge=0)
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    warnings: List[str] = Field(default_factory=list)
    summary: str


class DocumentClassificationSummary(BaseModel):
    """Summary of document classification for API response."""
    filename: str
    document_type: str
    confidence: int = Field(..., ge=0, le=100, description="Confidence percentage")


class IndividualAnalysisSummary(BaseModel):
    """Individual document analysis summary for API response."""
    filename: str
    document_type: str
    analysis: str


class CrossValidationResult(BaseModel):
    """Cross-validation result for API response."""
    check: str
    status: str
    details: List[str] = Field(default_factory=list)


class MortgageSimulationRequest(BaseModel):
    """Request model for mortgage simulation (implicitly defined by file uploads)."""
    pass  # Files are handled by FastAPI's File parameter


class MortgageSimulationResponse(BaseModel):
    """Response model for comprehensive mortgage simulation."""
    documents_processed: int = Field(..., ge=0)
    document_classifications: List[DocumentClassificationSummary]
    individual_analyses: List[IndividualAnalysisSummary]
    cross_validation: List[CrossValidationResult]
    comprehensive_mortgage_analysis: str = Field(..., description="Hebrew mortgage analysis text")


class MortgageScenario(BaseModel):
    """Individual mortgage eligibility scenario."""
    scenario_name: str
    max_amount: float = Field(..., ge=0)
    monthly_payment: float = Field(..., ge=0)
    income_percentage: str
    description: Optional[str] = None


class MortgageEligibility(BaseModel):
    """Calculated mortgage eligibility data."""
    monthly_income: float = Field(..., ge=0)
    annual_income: float = Field(..., ge=0)
    scenarios: List[MortgageScenario]
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    risk_level: str
    warnings: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)