"""Document analysis tool for the mortgage broker agent."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, List

from agents import function_tool
from agents.tool_context import ToolContext
from azure.ai.documentintelligence.aio import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import DocumentAnalysisFeature
from azure.core.credentials import AzureKeyCredential

from ...config import settings
from ...models.context import ChatRunContext
from ...models.documents import DocumentExtract, DocumentKeyValue, DocumentTable
from ...services import session_manager

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _document_client() -> AsyncIterator[DocumentIntelligenceClient]:
    """Yield a short-lived Azure Document Intelligence client and ensure cleanup."""

    if not settings.azure_doc_intel_endpoint or not settings.azure_doc_intel_key:
        raise RuntimeError(
            "Azure Document Intelligence credentials are not configured."
        )

    client = DocumentIntelligenceClient(
        endpoint=settings.azure_doc_intel_endpoint,
        credential=AzureKeyCredential(settings.azure_doc_intel_key),
    )

    try:
        yield client
    finally:
        await client.close()


def _summarize_key_values(pairs: List[DocumentKeyValue]) -> str:
    """Generate a compact summary of key-value pairs from OCR."""
    if not pairs:
        return "לא זוהו שדות מפתח במסמך."

    lines: list[str] = []
    for item in pairs:
        key = item.key.strip()
        value = item.value.strip()
        if not key and not value:
            continue
        lines.append(f"- {key or 'שדה ללא תיאור'}: {value or 'ערך חסר'}")

    return "\n".join(lines) if lines else "לא זוהו שדות מפתח במסמך."


def _summarize_tables(tables: List[DocumentTable]) -> str:
    """Summarize tables detected in the document."""
    if not tables:
        return "לא נמצאו טבלאות במסמך."

    summaries: list[str] = []
    for idx, table in enumerate(tables, start=1):
        row_count = table.row_count or 0
        column_count = table.column_count or 0
        summaries.append(f"טבלה {idx}: {row_count} שורות, {column_count} עמודות")

    return "\n".join(summaries)


def _build_extract_payload(
    *,
    locale: str,
    full_text: str,
    kv_pairs: List[DocumentKeyValue],
    tables: List[DocumentTable],
    warnings: list[str],
) -> DocumentExtract:
    preview_text = full_text[:2000]
    truncated = bool(full_text and len(full_text) > 2000)
    return DocumentExtract(
        locale=locale,
        text_preview=preview_text,
        text_truncated=truncated,
        key_value_pairs=kv_pairs,
        tables=tables,
        warnings=warnings,
        summary={
            "key_values": _summarize_key_values(kv_pairs),
            "tables": _summarize_tables(tables),
        },
    )


def _convert_key_values(raw_pairs: Any) -> List[DocumentKeyValue]:
    converted: list[DocumentKeyValue] = []
    for pair in raw_pairs or []:
        try:
            converted.append(
                DocumentKeyValue(
                    key=pair.key.content if getattr(pair, "key", None) else "",
                    value=pair.value.content if getattr(pair, "value", None) else "",
                    confidence=getattr(pair, "confidence", None),
                    page_number=(
                        pair.key.bounding_regions[0].page_number
                        if getattr(pair, "key", None)
                        and getattr(pair.key, "bounding_regions", None)
                        else None
                    ),
                )
            )
        except Exception:  # pragma: no cover - defensive
            continue
    return converted


def _convert_tables(raw_tables: Any) -> List[DocumentTable]:
    converted: list[DocumentTable] = []
    for table in raw_tables or []:
        try:
            rows: list[list[str]] = []
            cells = getattr(table, "cells", None) or []
            max_row = max((cell.row_index for cell in cells), default=-1)
            for _ in range(max_row + 1):
                rows.append([])
            for cell in cells:
                while len(rows[cell.row_index]) <= cell.column_index:
                    rows[cell.row_index].append("")
                rows[cell.row_index][cell.column_index] = cell.content or ""
            converted.append(
                DocumentTable(
                    row_count=getattr(table, "row_count", None),
                    column_count=getattr(table, "column_count", None),
                    rows=rows,
                    confidence=getattr(table, "confidence", None),
                )
            )
        except Exception:  # pragma: no cover - defensive
            continue
    return converted


@function_tool
async def analyze_document(
    ctx: ToolContext[ChatRunContext],
    document_id: str,
    locale: str = "he-IL",
) -> dict[str, Any]:
    """Run OCR on a document, persist structured findings, and return them."""

    context = getattr(ctx, "context", None)
    if not isinstance(context, ChatRunContext):
        return {"error": "analyze_document requires chat session context."}

    session = session_manager.get_session(context.session_id)
    if session is None:
        logger.error("Session %s not found for document analysis", context.session_id)
        return {"error": f"session {context.session_id} not found"}

    linked_document = session.get_document(document_id)
    if linked_document is None:
        logger.warning(
            "Requested document %s not found in session %s",
            document_id,
            context.session_id,
        )
        return {"error": f"document {document_id} not found"}

    temp_path = session.get_document_temp_path(document_id)
    if not temp_path:
        logger.warning(
            "Document %s has no available temp path for session %s",
            document_id,
            context.session_id,
        )
        return {
            "error": (
                "document source is not available for OCR. Please upload it again."
            )
        }

    try:
        async with _document_client() as client:
            try:
                with open(temp_path, "rb") as stream:
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
    except RuntimeError as exc:
        logger.error("Document analysis unavailable: %s", exc)
        return {"error": "OCR service is not configured."}
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Document analysis failed to initialize: %s", exc)
        return {"error": f"document analysis failed - {exc}"}

    full_text = result.content or ""
    kv_pairs = _convert_key_values(getattr(result, "key_value_pairs", None))
    tables = _convert_tables(getattr(result, "tables", None))
    warnings = [w.code for w in (getattr(result, "warnings", None) or [])]

    extract_payload = _build_extract_payload(
        locale=locale,
        full_text=full_text,
        kv_pairs=kv_pairs,
        tables=tables,
        warnings=warnings,
    )

    persisted = session.set_document_extract(
        linked_document.id,
        extract_payload,
    )
    document_type = (
        persisted.document_type if persisted else linked_document.document_type
    )

    response = {
        "document_id": linked_document.id,
        "locale": locale,
        "text_preview": extract_payload.text_preview,
        "text_truncated": extract_payload.text_truncated,
        "key_value_pairs": [kv.model_dump() for kv in kv_pairs],
        "tables": [table.model_dump() for table in tables],
        "warnings": warnings,
        "summary": extract_payload.summary,
        "document_type": document_type,
        "stored": True,
    }

    if warnings:
        logger.warning(
            "Document %s analysis warnings: %s",
            linked_document.id,
            warnings,
            extra={"session_id": context.session_id},
        )

    return response


__all__ = ["analyze_document"]
