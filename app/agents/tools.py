import logging
from typing import List, Dict
from agents import function_tool

from ..models import DocumentAnalysis
from ..dependencies import (
    get_document_analysis_service,
)


logger = logging.getLogger(__name__)

# Global storage for processed documents in a session
# In a real application, this would be stored in Redis or a database
SESSION_DOCUMENTS: Dict[str, List[DocumentAnalysis]] = {}


@function_tool
async def analyze_document_from_path(
    file_path: str, filename: str, session_id: str = "default"
) -> str:
    """
    Analyze a financial document from a file path and extract data.

    Args:
        file_path: Path to the document file (PDF)
        filename: Original filename for reference
        session_id: Session ID for document storage (optional)

    Returns:
        Hebrew description of the document analysis results
    """
    try:
        # Get the document analysis service
        doc_service = get_document_analysis_service()

        # Analyze the document
        analysis = await doc_service.analyze_document(file_path, filename)

        # Store in session documents
        if session_id not in SESSION_DOCUMENTS:
            SESSION_DOCUMENTS[session_id] = []
        SESSION_DOCUMENTS[session_id].append(analysis)

        confidence_percent = int(analysis.confidence * 100)

        if analysis.error:
            return f"שגיאה בניתוח המסמך '{filename}': {analysis.error}"

        result = f"ניתוח המסמך '{filename}':\n"
        result += f"רמת ביטחון: {confidence_percent}%\n"

        # Add extracted financial data
        data = analysis.financial_data

        # Show found data types
        if data.data_sources:
            types_str = ", ".join(data.data_sources)
            result += f"סוגי נתונים שנמצאו: {types_str}\n"

        # Show salary information if available
        if data.monthly_gross_salary or data.monthly_net_salary:
            result += "\nנתוני שכר:\n"
            if data.monthly_gross_salary:
                result += f"• שכר ברוטו חודשי: {data.monthly_gross_salary:,.0f} ₪\n"
            if data.monthly_net_salary:
                result += f"• שכר נטו חודשי: {data.monthly_net_salary:,.0f} ₪\n"
            if data.employer_name:
                result += f"• מעסיק: {data.employer_name}\n"
            if data.pay_period:
                result += f"• תקופת שכר: {data.pay_period}\n"

        # Show annual income if available
        if data.annual_gross_income or data.annual_net_income:
            result += "\nנתוני הכנסה שנתית:\n"
            if data.annual_gross_income:
                result += f"• הכנסה שנתית ברוטו: {data.annual_gross_income:,.0f} ₪\n"
            if data.annual_net_income:
                result += f"• הכנסה שנתית נטו: {data.annual_net_income:,.0f} ₪\n"
            if data.tax_year:
                result += f"• שנת המס: {data.tax_year}\n"
            if data.total_tax_paid:
                result += f"• סה״כ מס ששולם: {data.total_tax_paid:,.0f} ₪\n"

        # Show banking information if available
        if (
            data.account_balance is not None
            or data.monthly_deposits
            or data.monthly_expenses
        ):
            result += "\nנתוני בנקאות:\n"
            if data.account_balance is not None:
                result += f"• יתרה נוכחית: {data.account_balance:,.0f} ₪\n"
            if data.average_monthly_income:
                result += (
                    f"• הכנסה חודשית ממוצעת: {data.average_monthly_income:,.0f} ₪\n"
                )
            if data.monthly_deposits:
                result += f"• סה״כ הפקדות: {len(data.monthly_deposits)} פעולות\n"
            if data.monthly_expenses:
                result += f"• סה״כ הוצאות: {len(data.monthly_expenses)} פעולות\n"

        # Show personal info if available
        if data.person_name:
            result += f"\nשם: {data.person_name}\n"

        result += f'\nהמסמך נשמר לצורך חישוב משכנתא. סה"כ מסמכים בהפעלה: {len(SESSION_DOCUMENTS[session_id])}'

        return result

    except Exception as e:
        logger.error(f"Error in analyze_document_from_path: {e}")
        return f"שגיאה בניתוח המסמך: {str(e)}"


@function_tool
def get_session_documents_status(session_id: str = "default") -> str:
    """
    Get status of all documents processed in the current session.

    Args:
        session_id: Session ID to check (optional)

    Returns:
        Hebrew summary of processed documents
    """
    try:
        documents = SESSION_DOCUMENTS.get(session_id, [])

        if not documents:
            return "לא נמצאו מסמכים מעובדים בהפעלה הנוכחית."

        result = f"סטטוס מסמכים בהפעלה הנוכחית ({len(documents)} מסמכים):\n\n"

        # Track what types of data we have across all documents
        found_salary_data = False
        found_annual_income = False
        found_bank_data = False

        for i, doc in enumerate(documents, 1):
            confidence_percent = int(doc.confidence * 100)

            result += f"{i}. {doc.filename}\n"
            result += f"   ביטחון: {confidence_percent}%\n"

            # Show what data was found in this document
            data = doc.financial_data
            data_types = []

            if data.monthly_gross_salary or data.monthly_net_salary:
                data_types.append("נתוני שכר")
                found_salary_data = True
            if data.annual_gross_income or data.annual_net_income:
                data_types.append("הכנסה שנתית")
                found_annual_income = True
            if (
                data.account_balance is not None
                or data.monthly_deposits
                or data.monthly_expenses
            ):
                data_types.append("נתוני בנק")
                found_bank_data = True

            if data_types:
                result += f"   נתונים: {', '.join(data_types)}\n"
            else:
                result += "   נתונים: לא זוהו נתונים פיננסיים\n"

            if doc.error:
                result += f"   שגיאה: {doc.error}\n"

            result += "\n"

        # Add recommendations for missing data types
        missing_docs = []

        if not found_salary_data:
            missing_docs.append("תלושי שכר (מומלץ 2-3 תלושים אחרונים)")
        if not found_annual_income:
            missing_docs.append("תעודת מס שנתית (טופס 106)")
        if not found_bank_data:
            missing_docs.append("דפי חשבון (מומלץ 3 חודשים אחרונים)")

        if missing_docs:
            result += "מסמכים חסרים שמומלץ להעלות:\n"
            for missing in missing_docs:
                result += f"• {missing}\n"
        else:
            result += "כל סוגי הנתונים הנדרשים נמצאו. ניתן לבצע חישוב משכנתא."

        return result

    except Exception as e:
        logger.error(f"Error in get_session_documents_status: {e}")
        return f"שגיאה בקבלת סטטוס המסמכים: {str(e)}"


@function_tool
def clear_session_documents(session_id: str = "default") -> str:
    """
    Clear all documents from the current session.

    Args:
        session_id: Session ID to clear (optional)

    Returns:
        Confirmation message in Hebrew
    """
    try:
        if session_id in SESSION_DOCUMENTS:
            doc_count = len(SESSION_DOCUMENTS[session_id])
            del SESSION_DOCUMENTS[session_id]
            return (
                f"נוקו {doc_count} מסמכים מההפעלה הנוכחית. ניתן להתחיל עם מסמכים חדשים."
            )
        else:
            return "לא נמצאו מסמכים לניקוי בהפעלה הנוכחית."

    except Exception as e:
        logger.error(f"Error in clear_session_documents: {e}")
        return f"שגיאה בניקוי המסמכים: {str(e)}"


@function_tool
def get_mortgage_advice(income_range: str = "", family_status: str = "") -> str:
    """
    Provide general mortgage advice based on income and family situation.

    Args:
        income_range: Income range in Hebrew (e.g., "10,000-15,000", "מעל 20,000")
        family_status: Family status in Hebrew (e.g., "זוג צעיר", "משפחה עם ילדים")

    Returns:
        General mortgage advice in Hebrew
    """
    try:
        advice = "עצות כלליות למשכנתא:\n\n"

        # General advice based on income
        advice += "עצות בהתאם להכנסה:\n"
        if "10,000-15,000" in income_range or "עד 15" in income_range:
            advice += "• שקלו משכנתא משותפת עם הורים\n"
            advice += "• בדקו תמיכת המדינה לזוגות צעירים\n"
            advice += "• עדיפות לדירות קטנות יותר כהשקעה ראשונה\n"
        elif "15,000-25,000" in income_range or (
            "15" in income_range and "25" in income_range
        ):
            advice += "• ניתן לשקול משכנתא סטנדרטית\n"
            advice += "• מומלץ לחסוך הון עצמי של 20-25%\n"
            advice += "• בדקו משכנתא משולבת (קבועה + משתנה)\n"
        elif "מעל 25" in income_range or "25,000+" in income_range:
            advice += "• ניתן לשקול משכנתא גבוהה יותר\n"
            advice += "• שקלו השקעה בנכסים נוספים\n"
            advice += "• מומלץ ייעוץ מקצועי להשקעות\n"

        advice += "\nעצות כלליות:\n"
        advice += "• חשוב לוודא יציבות תעסוקתית לפחות שנה\n"
        advice += "• מומלץ לקבל הצעות מכמה בנקים\n"
        advice += "• לשמור על יחס חוב להכנסה נמוך מ-40%\n"
        advice += "• חסכו הון עצמי לפחות 20% ממחיר הנכס\n"
        advice += "• כללו בתכנון גם עלויות רכישה נוספות (מס, עורך דין, וכו')\n"

        # Family status specific advice
        if family_status:
            advice += f"\nעצות בהתאם למצב המשפחתי ({family_status}):\n"
            if "זוג צעיר" in family_status:
                advice += "• שקלו תוכניות סיוע ממשלתיות לזוגות צעירים\n"
                advice += "• תכננו לגידול משפחתי עתידי בבחירת הדירה\n"
            elif "ילדים" in family_status:
                advice += "• חשבו על גודל הדירה והסביבה החינוכית\n"
                advice += "• שקלו ביטוח משכנתא למקרה אובדן כושר עבודה\n"

        advice += "\nהערה: עצות אלה הן כלליות בלבד. מומלץ ליעץ עם יועץ משכנתאות מקצועי."

        return advice

    except Exception as e:
        logger.error(f"Error in get_mortgage_advice: {e}")
        return f"שגיאה במתן עצה כללית: {str(e)}"
