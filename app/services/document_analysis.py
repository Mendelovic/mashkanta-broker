"""Azure Document Intelligence wrapper."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List

from azure.ai.documentintelligence.aio import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import (
    AnalyzeResult,
    DocumentAnalysisFeature,
)
from azure.core.credentials import AzureKeyCredential

from ..config import settings

logger = logging.getLogger(__name__)


@dataclass
class AnalyzedDocument:
    """Structured information extracted from a document."""

    text: str
    key_value_pairs: List[Dict[str, Any]] = field(default_factory=list)
    tables: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class DocumentAnalysisService:
    """Lightweight wrapper around Azure Document Intelligence."""

    def __init__(self) -> None:
        if not settings.azure_doc_intel_endpoint or not settings.azure_doc_intel_key:
            raise RuntimeError(
                "Azure Document Intelligence credentials are not configured."
            )

        self._client = DocumentIntelligenceClient(
            endpoint=settings.azure_doc_intel_endpoint,
            credential=AzureKeyCredential(settings.azure_doc_intel_key),
        )

    async def analyze_document(
        self, file_path: str, *, locale: str = "he-IL"
    ) -> AnalyzedDocument:
        """Run OCR + layout extraction on the given file."""
        try:
            with open(file_path, "rb") as stream:
                poller = await self._client.begin_analyze_document(
                    "prebuilt-layout",
                    stream,
                    locale=locale,
                    features=[DocumentAnalysisFeature.KEY_VALUE_PAIRS],
                )

            result: AnalyzeResult = await poller.result()
        except Exception as exc:  # pragma: no cover - network errors
            logger.error("Azure Document Intelligence failed: %s", exc)
            raise RuntimeError(f"Azure Document Intelligence failed: {exc}") from exc

        full_text = result.content or ""

        kv_pairs: List[Dict[str, Any]] = []
        if result.key_value_pairs:
            for pair in result.key_value_pairs:
                kv_pairs.append(
                    {
                        "key": pair.key.content if pair.key else "",
                        "value": pair.value.content if pair.value else "",
                        "confidence": pair.confidence,
                    }
                )

        table_entries: List[Dict[str, Any]] = []
        if result.tables:
            for table in result.tables:
                rows: List[List[str]] = []
                max_row = max((cell.row_index for cell in table.cells), default=-1)
                for _ in range(max_row + 1):
                    rows.append([])
                for cell in table.cells:
                    # Expand row to fit this column
                    while len(rows[cell.row_index]) <= cell.column_index:
                        rows[cell.row_index].append("")
                    rows[cell.row_index][cell.column_index] = cell.content or ""
                table_entries.append(
                    {
                        "row_count": table.row_count,
                        "column_count": table.column_count,
                        "rows": rows,
                        "confidence": getattr(table, "confidence", None),
                    }
                )

        warnings = [w.code for w in result.warnings] if result.warnings else []

        return AnalyzedDocument(
            text=full_text,
            key_value_pairs=kv_pairs,
            tables=table_entries,
            warnings=warnings,
        )


__all__ = ["DocumentAnalysisService", "AnalyzedDocument"]
