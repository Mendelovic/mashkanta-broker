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
    "לא ניתן להריץ ביקת זכאות לפני שהסתים ראיון הלקוח ואושר סיכום נתונים. "
    "לאסוף ואמת את כל פרטי ההכנסה, החיובות והנכס, ואז סכם אותם עם הלקוח ושתמש בכלי של `submit_intake_record`."
)

_HEBREW_NO_PLANNING_MESSAGE = (
    "לא ניתן לכיל ביקת זכאות לפני חשוב תכנון עדכני. "
    "השתמש בכלי `compute_planning_context` מיד אחר סיכום לקוח."
)

_HEBREW_NO_OPTIMIZATION_MESSAGE = (
    "לא ניתן להריץ ביקת זכאות לפני שלבי עובר תרכיב תחזוקת עדכני. "
    "השתמש בכלי `run_mix_optimization` אחר בדוות ההקשר התכנון."
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
    footer = "בקש מהלקוח לשנות את מאפיי הלוואה (הון עצמי, תקופה, הכנסה נסופית) ואז אחר כך נסה שוב להריץ את הבדיקה."
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

    assessed_payment = eligibility.get("assessed_monthly_payment")
    pti_limit = limits.get("pti_limit")
    dti_limit = limits.get("dti_limit")
    applied_pti_limit = pti_limit if isinstance(pti_limit, (int, float)) else dti_limit

    dti = eligibility.get("debt_to_income_ratio")
    if isinstance(dti, (int, float)) and isinstance(applied_pti_limit, (int, float)):
        if dti > applied_pti_limit + 1e-6:
            if isinstance(assessed_payment, (int, float)):
                violations.append(
                    "תשלום חודשי של "
                    f"{assessed_payment:,.0f} ₪ מגביל יחס החזר של {dti:.1%} וחורג את המגבלה ({applied_pti_limit:.0%})."
                )
            else:
                violations.append(
                    f"יחס החזר ({dti:.1%}) חורג מהמגבלה ({applied_pti_limit:.0%})."
                )

    ltv = eligibility.get("loan_to_value_ratio")
    ltv_limit = limits.get("ltv_limit")
    if isinstance(ltv, (int, float)) and isinstance(ltv_limit, (int, float)):
        if ltv > ltv_limit + 1e-6:
            violations.append(f"חלק מימון ({ltv:.0%}) חורג מהמגבלה ({ltv_limit:.0%}).")

    loan_years = inputs.get("loan_years")
    if isinstance(loan_years, (int, float)) and loan_years > 30:
        violations.append("תקופת הלוואה עולה מ-30 שנים, נגדד להוראות בנק ישראל.")

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


def _ensure_optimization_exists(
    data: ToolInputGuardrailData,
) -> ToolGuardrailFunctionOutput:
    tool_ctx = data.context
    chat_context = getattr(tool_ctx, "context", None)

    if not isinstance(chat_context, ChatRunContext):
        return ToolGuardrailFunctionOutput.allow()

    session = session_manager.get_session(chat_context.session_id)
    if session is None or session.get_optimization_result() is None:
        return ToolGuardrailFunctionOutput.reject_content(
            message=_HEBREW_NO_OPTIMIZATION_MESSAGE,
            output_info={"reason": "missing_optimization"},
        )

    return ToolGuardrailFunctionOutput.allow()


optimization_required_guardrail = ToolInputGuardrail(
    guardrail_function=_ensure_optimization_exists,
    name="ensure_optimization_before_eligibility",
)

eligibility_compliance_guardrail = ToolOutputGuardrail(
    guardrail_function=_enforce_boi_constraints,
    name="enforce_boi_constraints",
)

__all__ = [
    "intake_required_guardrail",
    "planning_required_guardrail",
    "optimization_required_guardrail",
    "eligibility_compliance_guardrail",
]
