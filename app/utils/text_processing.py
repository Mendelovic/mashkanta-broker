from typing import List, Optional
from ..config import settings


def chunk_document_content(
    content: str, max_chunk_size: Optional[int] = None
) -> List[str]:
    """
    Split document content into overlapping chunks for better processing of long documents.
    Uses intelligent splitting to preserve context at boundaries.
    """
    if max_chunk_size is None:
        max_chunk_size = settings.chunk_size

    if len(content) <= max_chunk_size:
        return [content]

    chunks = []
    overlap_size = int(
        max_chunk_size * settings.chunk_overlap_ratio
    )  # 25% overlap by default

    start = 0
    while start < len(content):
        end = start + max_chunk_size

        if end >= len(content):
            # Last chunk
            chunks.append(content[start:])
            break

        # Try to break at sentence or line boundaries to preserve context
        chunk = content[start:end]

        # Look for good break points (sentence end, line break, period)
        break_chars = ["\n\n", ".\n", ". ", "\n"]
        best_break = -1

        for break_char in break_chars:
            last_break = chunk.rfind(break_char)
            if last_break > max_chunk_size * 0.7:  # At least 70% of chunk
                best_break = last_break + len(break_char)
                break

        if best_break > 0:
            chunks.append(content[start : start + best_break])
            start = start + best_break - overlap_size
        else:
            # No good break point found, just split at max size
            chunks.append(chunk)
            start = end - overlap_size

    return chunks
