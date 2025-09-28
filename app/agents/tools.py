"""Utility tools exposed to the mortgage-broker agent."""

# TODO: Split mortgage, timeline, and OCR helpers into separate modules if this keeps growing.
import logging
import uuid
from typing import Any, Dict, List, Optional, TypedDict

from agents import function_tool
from agents.tool_context import ToolContext
from azure.ai.documentintelligence.aio import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import DocumentAnalysisFeature
from azure.core.credentials import AzureKeyCredential

from .mortgage_calculator import MortgageCalculator, PropertyType, RiskProfile
from ..config import settings
from ..models.context import ChatRunContext
from ..models.timeline import (
    TimelineDetail,
    TimelineState,
    TimelineEvent,
    TimelineEventStatus,
    TimelineEventType,
    TimelineStage,
)
from ..services.session_manager import get_session

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

# TODO: Close the cached DocumentIntelligenceClient during app shutdown to release resources.
_document_client: DocumentIntelligenceClient | None = None


def _get_document_client() -> DocumentIntelligenceClient:
    """Return a cached Azure Document Intelligence client."""
    global _document_client

    if _document_client is not None:
        return _document_client

    if not settings.azure_doc_intel_endpoint or not settings.azure_doc_intel_key:
        raise RuntimeError("Azure Document Intelligence credentials are not configured.")

    _document_client = DocumentIntelligenceClient(
        endpoint=settings.azure_doc_intel_endpoint,
        credential=AzureKeyCredential(settings.azure_doc_intel_key),
    )
    return _document_client


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


class TimelineDetailInput(TypedDict, total=False):
    """Key/value pair accepted by the timeline event tool."""

    label: str
    value: str


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
def record_timeline_event(
    ctx: ToolContext[ChatRunContext],
    *,
    title: str,
    stage: str,
    event_type: str,
    status: str = TimelineEventStatus.ACTIVE.value,
    description: Optional[str] = None,
    bank_name: Optional[str] = None,
    details: Optional[list[TimelineDetailInput]] = None,
    event_id: Optional[str] = None,
) -> str:
    """Create or update a timeline event for the active chat session."""

    context = getattr(ctx, "context", None)
    if not isinstance(context, ChatRunContext):
        return "ERROR: timeline context unavailable for this tool call."

    session = get_session(context.session_id)
    if session is None:
        return f"ERROR: session {context.session_id} not found."

    try:
        stage_enum = TimelineStage(stage)
    except ValueError:
        valid = ", ".join(stage.value for stage in TimelineStage)
        return f"ERROR: unknown stage '{stage}'. Expected one of: {valid}."

    try:
        type_enum = TimelineEventType(event_type)
    except ValueError:
        valid = ", ".join(t.value for t in TimelineEventType)
        return f"ERROR: unknown event_type '{event_type}'. Expected one of: {valid}."

    try:
        status_enum = TimelineEventStatus(status)
    except ValueError:
        valid = ", ".join(s.value for s in TimelineEventStatus)
        return f"ERROR: unknown status '{status}'. Expected one of: {valid}."

    detail_items: list[TimelineDetail] = []
    if details:
        for entry in details:
            label = str(entry.get("label", "")).strip()
            value = str(entry.get("value", "")).strip()
            if not label and not value:
                continue
            detail_items.append(
                TimelineDetail(label=label or "detail", value=value or "")
            )

    new_event = TimelineEvent(
        id=event_id or uuid.uuid4().hex,
        type=type_enum,
        title=title,
        stage=stage_enum,
        status=status_enum,
        description=description,
        bank_name=bank_name,
        details=detail_items,
    )

    def _apply_timeline(state: TimelineState) -> None:
        state.upsert_event(new_event)

    state = session.apply_timeline_update(_apply_timeline)

    logger.info(
        "timeline event recorded",
        extra={"session_id": context.session_id, "event_id": new_event.id},
    )

    return (
        f"Timeline updated: event={new_event.id}, stage={new_event.stage.value}, "
        f"status={new_event.status.value}, version={state.version}"
    )


@function_tool
async def analyze_document(
    file_path: str,
    locale: str = "he-IL",
) -> dict:
    """Run OCR on a document and return structured findings."""

    # TODO: Add schema validation and PII scrubbing before returning OCR results to the agent.
    try:
        client = _get_document_client()
    except RuntimeError as exc:
        logger.error("Document analysis unavailable: %s", exc)
        return {"error": "OCR service is not configured."}

    try:
        # TODO: Offload file IO to a worker when concurrency grows so we don't block the event loop.
        with open(file_path, "rb") as stream:
            poller = await client.begin_analyze_document(
                "prebuilt-layout",
                stream,
                locale=locale,
                features=[DocumentAnalysisFeature.KEY_VALUE_PAIRS],
            )
        result = await poller.result()
    except Exception as exc:  # pragma: no cover - network failures
        logger.error("Document analysis failed: %s", exc)
        return {"error": f"document analysis failed - {exc}"}

    full_text = result.content or ""

    kv_pairs: List[Dict[str, Any]] = []
    for pair in getattr(result, "key_value_pairs", None) or []:
        kv_pairs.append(
            {
                "key": pair.key.content if getattr(pair, "key", None) else "",
                "value": pair.value.content if getattr(pair, "value", None) else "",
                "confidence": getattr(pair, "confidence", None),
            }
        )

    table_entries: List[Dict[str, Any]] = []
    for table in getattr(result, "tables", None) or []:
        rows: List[List[str]] = []
        cells = getattr(table, "cells", None) or []
        max_row = max((cell.row_index for cell in cells), default=-1)
        for _ in range(max_row + 1):
            rows.append([])
        for cell in cells:
            while len(rows[cell.row_index]) <= cell.column_index:
                rows[cell.row_index].append("")
            rows[cell.row_index][cell.column_index] = cell.content or ""
        table_entries.append(
            {
                "row_count": getattr(table, "row_count", None),
                "column_count": getattr(table, "column_count", None),
                "rows": rows,
                "confidence": getattr(table, "confidence", None),
            }
        )

    warnings = [w.code for w in (getattr(result, "warnings", None) or [])]

    preview_text = full_text[:2000]
    truncated = bool(full_text and len(full_text) > 2000)

    return {
        "file_path": file_path,
        "locale": locale,
        "text_preview": preview_text,
        "text_truncated": truncated,
        "key_value_pairs": kv_pairs,
        "tables": table_entries,
        "warnings": warnings,
        "summary": {
            "key_values": _summarize_key_values(kv_pairs),
            "tables": _summarize_tables(table_entries),
        },
    }


__all__ = [
    "calculate_mortgage_eligibility",
    "analyze_document",
    "send_mock_lender_outreach",
    "fetch_mock_lender_offers",
    "record_timeline_event",
]
