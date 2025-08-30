import logging
from typing import List, Dict, Any
from ..models import (
    DocumentAnalysis, 
    ValidationResults, 
    IncomeConsistencyCheck, 
    DocumentType
)


logger = logging.getLogger(__name__)


class MortgageCalculatorService:
    """Service for mortgage calculations and cross-validation of financial data."""
    
    def cross_validate_financial_data(self, document_analyses: List[DocumentAnalysis]) -> ValidationResults:
        """Cross-validate data between different document types for consistency."""
        validation_results = ValidationResults(
            income_consistency=IncomeConsistencyCheck(status="unknown"),
            recommended_income=None,
            confidence_score=0.0,
            summary="No validation performed"
        )
        
        # Extract income data from different sources
        payslip_gross_data = []
        payslip_net_data = []
        form_106_data = None
        bank_data = None
        
        for doc_analysis in document_analyses:
            doc_type = doc_analysis.document_type
            data = doc_analysis.analysis
            
            if doc_type == DocumentType.PAYSLIP:
                if "gross_salary" in data and data["gross_salary"]:
                    payslip_gross_data.append(data["gross_salary"])
                if "net_salary" in data and data["net_salary"]:
                    payslip_net_data.append(data["net_salary"])
            elif doc_type in [DocumentType.ANNUAL_TAX_CERTIFICATE] and data.get("annual_gross_income"):
                form_106_data = data
            elif doc_type == DocumentType.BANK_STATEMENT and data.get("average_monthly_income"):
                bank_data = data
        
        # Validate income consistency (gross vs gross comparison)
        if payslip_gross_data and form_106_data and form_106_data.get("annual_gross_income"):
            validation_results = self._validate_gross_income_consistency(
                payslip_gross_data, form_106_data, validation_results
            )
        elif payslip_gross_data:
            # Only payslips available
            validation_results.recommended_income = sum(payslip_gross_data) / len(payslip_gross_data)
            validation_results.confidence_score = 0.7
            validation_results.warnings.append("No Form 106 available for income verification")
        elif form_106_data:
            # Only Form 106 available
            validation_results.recommended_income = form_106_data["annual_gross_income"] / 12
            validation_results.confidence_score = 0.6
            validation_results.warnings.append("No recent payslips for current income verification")
        
        # Validate with bank statement data if available
        if bank_data and bank_data.get("average_monthly_income") and payslip_net_data:
            validation_results = self._validate_bank_consistency(
                bank_data, payslip_net_data, validation_results
            )
        elif bank_data and bank_data.get("average_monthly_income") and validation_results.recommended_income:
            # Fallback: warn about gross vs bank comparison
            self._add_gross_bank_warning(bank_data, validation_results)
        
        # Generate summary
        validation_results.summary = self._generate_validation_summary(validation_results)
        
        return validation_results
    
    def create_comprehensive_mortgage_simulation(
        self, 
        document_analyses: List[DocumentAnalysis], 
        validation_results: ValidationResults
    ) -> str:
        """Create comprehensive mortgage simulation analysis from all documents."""
        
        recommended_income = validation_results.recommended_income or 0
        confidence_score = validation_results.confidence_score
        warnings = validation_results.warnings
        
        if not recommended_income or recommended_income <= 0:
            return "לא ניתן לבצע סימולציית משכנתא - לא נמצאו נתוני הכנסה מהימנים"
        
        # Calculate mortgage eligibility
        annual_income = recommended_income * 12
        
        # Standard Israeli mortgage calculations
        max_mortgage_conservative = annual_income * 4   # Conservative (80% LTV equivalent)
        max_mortgage_standard = annual_income * 4.5     # Standard bank practice  
        max_mortgage_aggressive = annual_income * 5     # Aggressive (requires excellent profile)
        
        # Monthly payment calculations (assuming 4% interest, 25 years)
        monthly_payment_conservative = max_mortgage_conservative * 0.0053  # Rough calculation
        monthly_payment_standard = max_mortgage_standard * 0.0053
        monthly_payment_aggressive = max_mortgage_aggressive * 0.0053
        
        # Build comprehensive analysis
        analysis = "=== סימולציית משכנתא מקיפה ===\n\n"
        
        # Document summary
        analysis += self._build_document_summary(document_analyses)
        analysis += f"\nרמת אמינות הנתונים: {confidence_score:.1%}\n"
        analysis += f"סטטוס אימות: {validation_results.summary}\n\n"
        
        # Income analysis
        analysis += "=== ניתוח הכנסות ===\n"
        analysis += f"הכנסה חודשית מאומתת: {recommended_income:,.0f} ₪\n"
        analysis += f"הכנסה שנתית: {annual_income:,.0f} ₪\n\n"
        
        # Mortgage eligibility scenarios
        analysis += "=== תרחישי זכאות למשכנתא ===\n\n"
        
        analysis += "תרחיש שמרני (מומלץ):\n"
        analysis += f"• סכום מקסימלי: {max_mortgage_conservative:,.0f} ₪\n"
        analysis += f"• תשלום חודשי משוער: {monthly_payment_conservative:,.0f} ₪\n"
        analysis += f"• אחוז מההכנסה הנטו: ~30-35%\n\n"
        
        analysis += "תרחיש סטנדרטי:\n"
        analysis += f"• סכום מקסימלי: {max_mortgage_standard:,.0f} ₪\n"
        analysis += f"• תשלום חודשי משוער: {monthly_payment_standard:,.0f} ₪\n"
        analysis += f"• אחוז מההכנסה הנטו: ~35-40%\n\n"
        
        analysis += "תרחיש אגרסיבי (דורש פרופיל מצוין):\n"
        analysis += f"• סכום מקסימלי: {max_mortgage_aggressive:,.0f} ₪\n"
        analysis += f"• תשלום חודשי משוער: {monthly_payment_aggressive:,.0f} ₪\n"
        analysis += f"• אחוז מההכנסה הנטו: ~40-45%\n\n"
        
        # Risk assessment
        analysis += "=== הערכת סיכונים ===\n"
        analysis += self._assess_risk_level(confidence_score)
        
        # Warnings
        if warnings:
            analysis += "\nהתראות:\n"
            for warning in warnings:
                analysis += f"• {warning}\n"
        
        analysis += "\n=== המלצות לשיפור הפרופיל ===\n"
        analysis += "• הכן 3-6 תלושי שכר עדכניים\n"
        analysis += "• הכן טופס 106 מהשנה האחרונה\n"
        analysis += "• הכן דפי חשבון מ-3 חודשים אחרונים\n"
        analysis += "• בדוק אפשרות לשיפור יחס החוב להכנסה\n"
        analysis += "• שמור על יציבות בהכנסות לפני הגשת הבקשה\n"
        
        analysis += "\nהערה: הסימולציה מבוססת על נתונים כלליים ואינה מהווה התחייבות בנקאית"
        
        return analysis
    
    def _validate_gross_income_consistency(
        self, 
        payslip_gross_data: List[float], 
        form_106_data: Dict[str, Any], 
        validation_results: ValidationResults
    ) -> ValidationResults:
        """Validate gross income consistency between payslips and Form 106."""
        avg_monthly_gross_payslip = sum(payslip_gross_data) / len(payslip_gross_data)
        annual_from_payslips = avg_monthly_gross_payslip * 12
        annual_from_106 = form_106_data["annual_gross_income"]
        
        # Check if annual income is consistent (within 15% tolerance)
        income_difference = abs(annual_from_payslips - annual_from_106)
        tolerance = annual_from_106 * 0.15
        
        if income_difference <= tolerance:
            validation_results.income_consistency.status = "consistent"
            validation_results.income_consistency.details.append(
                f"Payslips annual gross: {annual_from_payslips:,.0f} vs Form 106: {annual_from_106:,.0f}"
            )
            validation_results.recommended_income = avg_monthly_gross_payslip
            validation_results.confidence_score = 0.9
        else:
            validation_results.income_consistency.status = "inconsistent"
            validation_results.warnings.append(
                f"Income mismatch: Payslips suggest {annual_from_payslips:,.0f} annually, "
                f"but Form 106 shows {annual_from_106:,.0f}"
            )
            # Use the more conservative estimate
            validation_results.recommended_income = min(avg_monthly_gross_payslip, annual_from_106 / 12)
            validation_results.confidence_score = 0.6
        
        return validation_results
    
    def _validate_bank_consistency(
        self, 
        bank_data: Dict[str, Any], 
        payslip_net_data: List[float], 
        validation_results: ValidationResults
    ) -> ValidationResults:
        """Validate bank deposits against net salary."""
        bank_monthly = bank_data["average_monthly_income"]
        avg_monthly_net_payslip = sum(payslip_net_data) / len(payslip_net_data)
        
        # Check if bank deposits match expected NET salary (within 20% tolerance)
        deposit_difference = abs(bank_monthly - avg_monthly_net_payslip)
        bank_tolerance = avg_monthly_net_payslip * 0.20
        
        if deposit_difference <= bank_tolerance:
            current_confidence = validation_results.confidence_score
            validation_results.confidence_score = min(current_confidence + 0.1, 1.0)
            validation_results.income_consistency.details.append(
                f"Bank deposits ({bank_monthly:,.0f}) match net salary ({avg_monthly_net_payslip:,.0f})"
            )
        else:
            validation_results.warnings.append(
                f"Bank deposits ({bank_monthly:,.0f}) don't match expected net salary ({avg_monthly_net_payslip:,.0f})"
            )
        
        return validation_results
    
    def _add_gross_bank_warning(self, bank_data: Dict[str, Any], validation_results: ValidationResults):
        """Add warning about gross vs bank comparison."""
        bank_monthly = bank_data["average_monthly_income"]
        recommended_monthly = validation_results.recommended_income
        validation_results.warnings.append(
            f"Warning: Comparing gross income ({recommended_monthly:,.0f}) with bank deposits ({bank_monthly:,.0f}) - net salary data needed for accurate validation"
        )
    
    def _generate_validation_summary(self, validation_results: ValidationResults) -> str:
        """Generate validation summary text."""
        if validation_results.income_consistency.status == "consistent":
            return "Income data is consistent across documents"
        elif validation_results.income_consistency.status == "inconsistent":
            return "Income discrepancies found - using conservative estimate"
        else:
            return "Limited income verification available"
    
    def _build_document_summary(self, document_analyses: List[DocumentAnalysis]) -> str:
        """Build document summary section."""
        doc_types = [doc.document_type.value for doc in document_analyses]
        doc_counts = {doc_type: doc_types.count(doc_type) for doc_type in set(doc_types)}
        
        doc_names = {
            "payslip": "תלושי שכר",
            "annual_tax_certificate": "תעודת מס שנתית (106 או תחליף)",
            "bank_statement": "דפי חשבון",
            "loan_statement": "דוח הלוואות"
        }
        
        summary = "מסמכים שנותחו:\n"
        for doc_type, count in doc_counts.items():
            summary += f"• {doc_names.get(doc_type, doc_type)}: {count}\n"
        
        return summary
    
    def _assess_risk_level(self, confidence_score: float) -> str:
        """Assess risk level based on confidence score."""
        if confidence_score >= 0.8:
            return "רמת סיכון נמוכה - פרופיל מצוין למשכנתא\n"
        elif confidence_score >= 0.6:
            return "רמת סיכון בינונית - פרופיל טוב למשכנתא עם בדיקות נוספות\n"
        else:
            return "רמת סיכון גבוהה - נדרשת בדיקה מעמיקה נוספת\n"