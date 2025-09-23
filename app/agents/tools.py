"""Utility tools exposed to the mortgage-broker agent."""

import logging
from typing import Any, Dict, List

from agents import function_tool

from .mortgage_calculator import MortgageCalculator, PropertyType, RiskProfile
from ..dependencies import get_document_analysis_service

logger = logging.getLogger(__name__)

_PROPERTY_TYPE_MAP = {
    PropertyType.FIRST_HOME.value: PropertyType.FIRST_HOME,
    PropertyType.UPGRADE.value: PropertyType.UPGRADE,
    PropertyType.INVESTMENT.value: PropertyType.INVESTMENT,
}

_RISK_PROFILE_MAP = {
    RiskProfile.CONSERVATIVE.value: RiskProfile.CONSERVATIVE,
    RiskProfile.STANDARD.value: RiskProfile.STANDARD,
    RiskProfile.AGGRESSIVE.value: RiskProfile.AGGRESSIVE,
}


def _format_currency(amount: float) -> str:
    """Return a human-friendly currency string."""
    return f"₪{amount:,.0f}" if amount is not None else "₪ לא זמין"


def _summarize_key_values(pairs: list[dict[str, Any]]) -> str:
    """Generate a compact summary of key-value pairs from OCR."""
    if not pairs:
        return "לא זוהו שדות מפתח במסמך."

    lines: list[str] = []
    for item in pairs:
        key = (item.get("key") or "").strip()
        value = (item.get("value") or "").strip()
        if not key and not value:
            continue
        lines.append(f"- {key or 'שדה ללא תיאור'}: {value or 'ערך חסר'}")

    return "\n".join(lines) if lines else "לא זוהו שדות מפתח במסמך."


def _summarize_tables(tables: list[dict[str, Any]]) -> str:
    """Summarize tables detected in the document."""
    if not tables:
        return "לא נמצאו טבלאות במסמך."

    summaries: list[str] = []
    for idx, table in enumerate(tables, start=1):
        row_count = table.get("row_count") or 0
        column_count = table.get("column_count") or 0
        summaries.append(f"טבלה {idx}: {row_count} שורות, {column_count} עמודות")

    return "\n".join(summaries)


@function_tool
def send_mock_lender_outreach(client_summary: str) -> str:
    """Mock sending the client's profile to multiple lenders."""
    # TODO: Replace with real email or lender API integration when available.
    return (
        "שלחתי מייל מסכם לבנק הפועלים, בנק לאומי ומזרחי-טפחות עם הנתונים: "
        + client_summary
    )


@function_tool
def fetch_mock_lender_offers(
    preferred_risk_profile: str = RiskProfile.STANDARD.value,
) -> Dict[str, Any]:
    """Return three fabricated lender offers for demo purposes."""
    # TODO: Replace mocked offers with live lender responses once integrations exist.
    base_offers: List[Dict[str, Any]] = [
        {
            "bank": "בנק הפועלים",
            "headline": "יציבות עם מרווחי פריים שמרניים",
            "tracks": [
                {"name": "פריים", "share": 0.33, "rate": "פריים - 0.1%"},
                {"name": "קבועה לא צמודה 25 שנה", "share": 0.42, "rate": "4.7%"},
                {"name": "משתנה כל 5 שנים צמודה", "share": 0.25, "rate": "3.2%"},
            ],
            "opening_fee": "₪2,450",
            "notes": "כולל אפשרות פירעון מוקדם חלקי ללא קנס עד 10% לשנה",
        },
        {
            "bank": "בנק לאומי",
            "headline": "דגש על רכיב לא צמוד ליציבות",
            "tracks": [
                {"name": "פריים", "share": 0.30, "rate": "פריים - 0.05%"},
                {"name": "קבועה לא צמודה 20 שנה", "share": 0.45, "rate": "4.6%"},
                {"name": "משתנה כל 5 שנים לא צמודה", "share": 0.25, "rate": "4.0%"},
            ],
            "opening_fee": "₪2,100",
            "notes": "דורש ביטוח חיים ורכוש דרך הסוכנות של הבנק",
        },
        {
            "bank": "מזרחי-טפחות",
            "headline": "גמישות לפרעון מוקדם והגדלת רכיב פריים",
            "tracks": [
                {"name": "פריים", "share": 0.40, "rate": "פריים - 0.15%"},
                {"name": "קבועה צמודה 18 שנה", "share": 0.35, "rate": "2.9%"},
                {"name": "משתנה כל 5 שנים צמודה", "share": 0.25, "rate": "3.1%"},
            ],
            "opening_fee": "₪2,650",
            "notes": "מאפשר גרייס חלקי לשנה הראשונה בכפוף לאישור אשראי",
        },
    ]

    return {
        "risk_profile": preferred_risk_profile,
        "offers": base_offers,
        "disclaimer": "נתונים לדוגמה עבור הדגמת התהליך בלבד",
    }


@function_tool
def calculate_mortgage_eligibility(
    monthly_net_income: float,
    property_price: float,
    down_payment_available: float,
    existing_monthly_loans: float = 0.0,
    loan_years: int = 25,
    property_type: str = PropertyType.FIRST_HOME.value,
    risk_profile: str = RiskProfile.STANDARD.value,
) -> str:
    """Calculate Israeli mortgage eligibility using simple banking rules."""
    try:
        prop_type = _PROPERTY_TYPE_MAP.get(property_type, PropertyType.FIRST_HOME)
        risk = _RISK_PROFILE_MAP.get(risk_profile, RiskProfile.STANDARD)

        calc = MortgageCalculator.calculate_eligibility(
            monthly_net_income=monthly_net_income,
            property_price=property_price,
            down_payment_available=down_payment_available,
            property_type=prop_type,
            risk_profile=risk,
            existing_loans_payment=existing_monthly_loans,
            years=loan_years,
        )

        lines: list[str] = ["**סיכום בדיקת זכאות למשכנתא:**", ""]
        lines.append("**נתוני בסיס:**")
        lines.append(f"• הכנסה נטו חודשית: {_format_currency(monthly_net_income)}")
        lines.append(f"• מחיר נכס: {_format_currency(property_price)}")
        lines.append(f"• הון עצמי זמין: {_format_currency(down_payment_available)}")
        if existing_monthly_loans:
            lines.append(
                f"• התחייבויות חודשיות קיימות: {_format_currency(existing_monthly_loans)}"
            )
        lines.append(f"• סוג נכס: {prop_type.value}")
        lines.append(f"• פרופיל סיכון: {risk.value}")
        lines.append("")

        lines.append("**תוצאות:**")
        status = "זכאי" if calc.is_eligible else "לא זכאי"
        lines.append(f"• סטטוס: {status} ({calc.eligibility_notes})")
        lines.append(f"• סכום הלוואה מקסימלי: {_format_currency(calc.max_loan_amount)}")
        lines.append(
            f"• יכולת החזר חודשית: {_format_currency(calc.monthly_payment_capacity)}"
        )
        lines.append(
            f"• יחס החזר: {calc.debt_to_income_ratio:.1%} (מקסימום לפי פרופיל {MortgageCalculator.DTI_LIMITS[risk]:.0%})"
        )
        lines.append(
            f"• יחס מימון (LTV): {calc.loan_to_value_ratio:.0%} (מקסימום לפי סוג נכס {MortgageCalculator.LTV_LIMITS[prop_type]:.0%})"
        )
        lines.append(f"• הון עצמי נדרש: {_format_currency(calc.required_down_payment)}")
        lines.append("")

        if calc.is_eligible:
            lines.append("**תמהיל מומלץ:**")
            for track, ratio in calc.recommended_tracks.items():
                amount = calc.max_loan_amount * ratio
                lines.append(f"• {track}: {ratio:.0%} ({_format_currency(amount)})")

            if calc.market_based_recommendation:
                lines.append("")
                lines.append("**הסבר לבחירה:**")
                lines.append(calc.market_based_recommendation)
        else:
            lines.append("**כדי לשפר את הזכאות:**")
            adjustments = MortgageCalculator.adjust_for_eligibility(
                monthly_net_income,
                property_price,
                down_payment_available,
                prop_type,
                existing_monthly_loans,
            )
            if "reduce_price" in adjustments:
                lines.append(
                    f"• שקול/י להקטין את מחיר הנכס לכ-{_format_currency(adjustments['reduce_price'])}"
                )
            if "required_down_payment" in adjustments:
                extra = adjustments["required_down_payment"] - down_payment_available
                if extra > 0:
                    lines.append(f"• יש להשלים הון עצמי של {_format_currency(extra)}")
            if "required_income" in adjustments:
                extra_income = adjustments["required_income"] - monthly_net_income
                if extra_income > 0:
                    lines.append(
                        f"• יש צורך בהכנסה חודשית נוספת של {_format_currency(extra_income)}"
                    )

        return "\n".join(lines)

    except Exception as exc:
        logger.error("Eligibility calculation failed: %s", exc)
        return f"ERROR: eligibility calculation failed - {exc}"


@function_tool
async def analyze_document(
    file_path: str,
    locale: str = "he-IL",
) -> dict:
    """Run OCR on a document and return structured findings."""

    # TODO: Add schema validation and PII scrubbing before returning OCR results to the agent.
    try:
        service = get_document_analysis_service()
    except RuntimeError as exc:
        logger.error("Document analysis unavailable: %s", exc)
        return {"error": "OCR service is not configured."}

    try:
        analysis = await service.analyze_document(file_path, locale=locale)
    except Exception as exc:  # pragma: no cover - network failures
        logger.error("Document analysis failed: %s", exc)
        return {"error": f"document analysis failed - {exc}"}

    preview_text = analysis.text[:2000] if analysis.text else ""
    truncated = bool(analysis.text and len(analysis.text) > 2000)

    return {
        "file_path": file_path,
        "locale": locale,
        "text_preview": preview_text,
        "text_truncated": truncated,
        "key_value_pairs": analysis.key_value_pairs,
        "tables": analysis.tables,
        "warnings": analysis.warnings,
        "summary": {
            "key_values": _summarize_key_values(analysis.key_value_pairs),
            "tables": _summarize_tables(analysis.tables),
        },
    }


__all__ = [
    "calculate_mortgage_eligibility",
    "analyze_document",
    "send_mock_lender_outreach",
    "fetch_mock_lender_offers",
]
