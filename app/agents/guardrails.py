"""Guardrail definitions for the mortgage broker agent."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from agents.tool_guardrails import (
    ToolGuardrailFunctionOutput,
    ToolInputGuardrail,
    ToolInputGuardrailData,
    ToolOutputGuardrail,
    ToolOutputGuardrailData,
)

from ..models.context import ChatRunContext
from ..services import session_manager

_HEBREW_NO_INTAKE_MESSAGE = (
    "לא ניתן להריץ בדיקת זכאות לפני שהסתיים ראיון הלקוח ואושר תקציר הנתונים. "
    "אסוף ואמת את כל פרטי ההכנסות, ההתחייבויות והנכס, ואז סכם אותם עם הלקוח והשתמש בכלי "
    "`submit_intake_record`."
)

_HEBREW_NO_PLANNING_MESSAGE = (
    "לא ניתן לכייל בדיקת זכאות לפני שמחשבים הקשר תכנון עדכני. "
    "השתמש בכלי `compute_planning_context` מיד לאחר סיכום הנתונים עם הלקוח."
)


def _ensure_intake_exists(data: ToolInputGuardrailData) -> ToolGuardrailFunctionOutput:
    tool_ctx = data.context
    chat_context = getattr(tool_ctx, "context", None)

    if not isinstance(chat_context, ChatRunContext):
        return ToolGuardrailFunctionOutput.allow()

    session = session_manager.get_session(chat_context.session_id)
    if session is None or session.get_intake_record() is None:
        return ToolGuardrailFunctionOutput.reject_content(
            message=_HEBREW_NO_INTAKE_MESSAGE,
            output_info={"reason": "missing_intake_record"},
        )

    return ToolGuardrailFunctionOutput.allow()


def _extract_output_dict(obj: Any) -> Optional[Dict[str, Any]]:
    if isinstance(obj, dict):
        return obj
    if isinstance(obj, str):
        try:
            parsed = json.loads(obj)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            return None
    return None


def _compose_violation_message(violations: List[str]) -> str:
    header = "בדיקת הזכאות הופסקה כי נמצאו חריגות מול כללי בנק ישראל:"
    formatted = "\n".join(f"- {item}" for item in violations)
    footer = (
        "בקש מהלקוח לשנות את מאפייני ההלוואה (הון עצמי, תקופת החזר, הכנסה ועוד) "
        "ורק לאחר מכן נסה שוב להריץ את הבדיקה."
    )
    return f"{header}\n{formatted}\n{footer}"


def _enforce_boi_constraints(
    data: ToolOutputGuardrailData,
) -> ToolGuardrailFunctionOutput:
    payload = _extract_output_dict(data.output)
    if not payload:
        return ToolGuardrailFunctionOutput.allow()

    eligibility = payload.get("eligibility", {})
    inputs = payload.get("inputs", {})
    limits = eligibility.get("limits", {})

    if not eligibility or not limits:
        return ToolGuardrailFunctionOutput.allow()

    violations: List[str] = []

    dti = eligibility.get("debt_to_income_ratio")
    dti_limit = limits.get("dti_limit")
    if isinstance(dti, (int, float)) and isinstance(dti_limit, (int, float)):
        if dti > dti_limit + 1e-6:
            violations.append(
                f"יחס ההחזר להכנסה ({dti:.1%}) גבוה מהמגבלה ({dti_limit:.0%})."
            )

    ltv = eligibility.get("loan_to_value_ratio")
    ltv_limit = limits.get("ltv_limit")
    if isinstance(ltv, (int, float)) and isinstance(ltv_limit, (int, float)):
        if ltv > ltv_limit + 1e-6:
            violations.append(
                f"יחס המימון לנכס ({ltv:.0%}) חורג מהמותר ({ltv_limit:.0%})."
            )

    loan_years = inputs.get("loan_years")
    if isinstance(loan_years, (int, float)) and loan_years > 30:
        violations.append("תקופת ההלוואה ארוכה מ-30 שנים, בניגוד להוראות בנק ישראל.")

    if not eligibility.get("is_eligible") and not violations:
        notes = eligibility.get("eligibility_notes")
        if isinstance(notes, str) and notes.strip():
            violations.append(notes.strip())

    if not violations:
        return ToolGuardrailFunctionOutput.allow(output_info={"compliance": "pass"})

    message = _compose_violation_message(violations)
    return ToolGuardrailFunctionOutput.reject_content(
        message=message,
        output_info={"violations": violations},
    )


intake_required_guardrail = ToolInputGuardrail(
    guardrail_function=_ensure_intake_exists,
    name="ensure_intake_before_eligibility",
)


def _ensure_planning_context_exists(
    data: ToolInputGuardrailData,
) -> ToolGuardrailFunctionOutput:
    tool_ctx = data.context
    chat_context = getattr(tool_ctx, "context", None)

    if not isinstance(chat_context, ChatRunContext):
        return ToolGuardrailFunctionOutput.allow()

    session = session_manager.get_session(chat_context.session_id)
    if session is None or session.get_planning_context() is None:
        return ToolGuardrailFunctionOutput.reject_content(
            message=_HEBREW_NO_PLANNING_MESSAGE,
            output_info={"reason": "missing_planning_context"},
        )

    return ToolGuardrailFunctionOutput.allow()


planning_required_guardrail = ToolInputGuardrail(
    guardrail_function=_ensure_planning_context_exists,
    name="ensure_planning_before_eligibility",
)

eligibility_compliance_guardrail = ToolOutputGuardrail(
    guardrail_function=_enforce_boi_constraints,
    name="enforce_boi_constraints",
)

__all__ = [
    "intake_required_guardrail",
    "planning_required_guardrail",
    "eligibility_compliance_guardrail",
]
