"""Paragraph-aware text chunking with configurable size and overlap."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List


@dataclass
class TextChunk:
    chunk_index: int
    content: str


def chunk_text(text: str, chunk_size: int = 900, chunk_overlap: int = 120) -> List[TextChunk]:
    """Split extracted document text into overlapping chunks preserving paragraph boundaries."""
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be >= 0 and < chunk_size")

    cleaned = re.sub(r"\r\n?", "\n", text or "").strip()
    if not cleaned:
        return []

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", cleaned) if p.strip()]
    if not paragraphs:
        return []

    raw_chunks: List[str] = []
    current = ""

    for para in paragraphs:
        if len(para) > chunk_size:
            if current:
                raw_chunks.append(current.strip())
                current = ""
            # Slice oversized paragraph with overlap
            step = max(1, chunk_size - chunk_overlap)
            start = 0
            while start < len(para):
                piece = para[start : start + chunk_size].strip()
                if piece:
                    raw_chunks.append(piece)
                if start + chunk_size >= len(para):
                    break
                start += step
        else:
            candidate = f"{current}\n\n{para}".strip() if current else para
            if len(candidate) <= chunk_size:
                current = candidate
            else:
                if current:
                    raw_chunks.append(current.strip())
                    overlap_tail = current[-chunk_overlap:].strip() if chunk_overlap > 0 else ""
                    if overlap_tail and len(overlap_tail) + 2 + len(para) <= chunk_size:
                        current = f"{overlap_tail}\n\n{para}"
                    else:
                        current = para
                else:
                    current = para

    if current.strip():
        raw_chunks.append(current.strip())

    return [TextChunk(chunk_index=idx, content=chunk) for idx, chunk in enumerate(raw_chunks)]
