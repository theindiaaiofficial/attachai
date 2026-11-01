"""RFC-4180 compliant CSV parser supporting quoted fields, escaped quotes, and multiline cells."""

from __future__ import annotations

import csv
import io
from typing import Dict, List, Tuple


def parse_csv_content(raw_text: str) -> Tuple[List[str], List[Dict[str, str]], str]:
    """
    Parse CSV content into (headers, rows, formatted_rag_text).
    Properly handles quoted fields, escaped quotes (""), and multiline values.
    """
    normalized = (raw_text or "").lstrip("\ufeff").strip()
    if not normalized:
        return [], [], ""

    reader = csv.reader(io.StringIO(normalized), dialect="excel", doublequote=True)
    all_rows = [[cell.strip() for cell in row] for row in reader if any(cell.strip() for cell in row)]
    if not all_rows:
        return [], [], ""

    headers = [h if h else f"column_{i + 1}" for i, h in enumerate(all_rows[0])]
    records: List[Dict[str, str]] = []
    formatted_blocks: List[str] = []

    for row_idx, row in enumerate(all_rows[1:], start=1):
        record: Dict[str, str] = {}
        pairs: List[str] = []
        for col_idx, header in enumerate(headers):
            val = row[col_idx] if col_idx < len(row) else ""
            record[header] = val
            if val:
                pairs.append(f"{header}: {val}")
        if pairs:
            records.append(record)
            formatted_blocks.append(f"Row {row_idx} — " + " | ".join(pairs))

    # Handle single-row CSV
    if not formatted_blocks and headers:
        formatted_blocks.append("Columns: " + ", ".join(headers))

    return headers, records, "\n\n".join(formatted_blocks)
