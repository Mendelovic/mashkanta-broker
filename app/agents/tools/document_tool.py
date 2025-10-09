"""Document analysis tool for the mortgage broker agent."""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from agents import function_tool
from azure.ai.documentintelligence.aio import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import DocumentAnalysisFeature
from azure.core.credentials import AzureKeyCredential

from ...config import settings

logger = logging.getLogger(__name__)

_document_client: DocumentIntelligenceClient | None = None


def _get_document_client() -> DocumentIntelligenceClient:
    """Return a cached Azure Document Intelligence client."""
    global _document_client

    if _document_client is not None:
        return _document_client

    if not settings.azure_doc_intel_endpoint or not settings.azure_doc_intel_key:
        raise RuntimeError(
            "Azure Document Intelligence credentials are not configured."
        )

    _document_client = DocumentIntelligenceClient(
        endpoint=settings.azure_doc_intel_endpoint,
        credential=AzureKeyCredential(settings.azure_doc_intel_key),
    )
    return _document_client


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
async def analyze_document(
    file_path: str,
    locale: str = "he-IL",
) -> dict:
    """Run OCR on a document and return structured findings."""

    try:
        client = _get_document_client()
    except RuntimeError as exc:
        logger.error("Document analysis unavailable: %s", exc)
        return {"error": "OCR service is not configured."}

    try:
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


__all__ = ["analyze_document"]
