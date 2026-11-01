"""Document parser supporting PDF, DOCX, CSV, Markdown, and TXT with strict signature and structure checks."""

from __future__ import annotations

import io
import re
import xml.etree.ElementTree as ET
import zipfile
from typing import List
from xml.sax.saxutils import escape as xml_escape

from app.core.exceptions import ValidationError
from app.utils.csv_parser import parse_csv_content
from app.utils.validators import validate_upload_metadata


def build_valid_docx_bytes(paragraphs: List[str]) -> bytes:
    """
    Create a spec-compliant OOXML (.docx) ZIP archive containing:
    - [Content_Types].xml
    - _rels/.rels
    - word/_rels/document.xml.rels
    - word/document.xml
    """
    content_types_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        "</Types>"
    )
    root_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="word/document.xml"/>'
        "</Relationships>"
    )
    doc_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        "</Relationships>"
    )
    para_nodes = "".join(
        f"<w:p><w:r><w:t>{xml_escape(p)}</w:t></w:r></w:p>" for p in paragraphs if p is not None
    )
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{para_nodes}</w:body>"
        "</w:document>"
    )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types_xml)
        zf.writestr("_rels/.rels", root_rels_xml)
        zf.writestr("word/_rels/document.xml.rels", doc_rels_xml)
        zf.writestr("word/document.xml", document_xml)
    return buf.getvalue()


def build_valid_pdf_bytes(text: str) -> bytes:
    """
    Create a valid PDF 1.4 binary with a complete cross-reference table (`xref`),
    `trailer`, `startxref` byte offset, and `%%EOF` marker.
    """
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()] or [text.strip()]
    escaped_ops: List[str] = ["BT", "/F1 12 Tf", "50 750 Td", "14 TL"]
    for idx, line in enumerate(lines):
        safe_line = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        if idx == 0:
            escaped_ops.append(f"({safe_line}) Tj")
        else:
            escaped_ops.append(f"T* ({safe_line}) Tj")
    escaped_ops.append("ET")
    stream_body = "\n".join(escaped_ops).encode("latin-1", errors="replace")

    objects = [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n",
        f"4 0 obj\n<< /Length {len(stream_body)} >>\nstream\n".encode("ascii")
        + stream_body
        + b"\nendstream\nendobj\n",
        b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n",
    ]

    out = bytearray(b"%PDF-1.4\n")
    offsets: List[int] = []
    for obj in objects:
        offsets.append(len(out))
        out.extend(obj)

    xref_offset = len(out)
    out.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    out.extend(b"0000000000 65535 f \n")
    for off in offsets:
        out.extend(f"{off:010d} 00000 n \n".encode("ascii"))

    trailer = (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n"
    ).encode("ascii")
    out.extend(trailer)
    return bytes(out)


class DocumentParserService:
    """Extracts and validates text from PDF, DOCX, TXT, Markdown, and CSV documents."""

    def __init__(self, max_upload_size_bytes: int = 10 * 1024 * 1024) -> None:
        self.max_upload_size_bytes = max_upload_size_bytes

    def parse(self, filename: str, content: bytes, mime_type: str = "application/octet-stream") -> str:
        ext = validate_upload_metadata(
            filename=filename,
            mime_type=mime_type,
            size_bytes=len(content or b""),
            max_bytes=self.max_upload_size_bytes,
        )
        if ext in (".txt", ".md"):
            extracted = self._parse_text(content)
        elif ext == ".csv":
            extracted = self._parse_csv(content)
        elif ext == ".docx":
            extracted = self._parse_docx(content)
        elif ext == ".pdf":
            extracted = self._parse_pdf(content)
        else:
            raise ValidationError(f"Unsupported file extension: {ext}")

        cleaned = extracted.strip()
        if not cleaned:
            raise ValidationError(f"Document {filename!r} contains no extractable text.")
        return cleaned

    @staticmethod
    def _parse_text(content: bytes) -> str:
        try:
            return content.decode("utf-8")
        except UnicodeDecodeError:
            return content.decode("latin-1", errors="replace")

    def _parse_csv(self, content: bytes) -> str:
        raw_text = self._parse_text(content)
        _, _, formatted = parse_csv_content(raw_text)
        if not formatted.strip():
            raise ValidationError("CSV file contains no valid rows.")
        return formatted

    @staticmethod
    def _parse_docx(content: bytes) -> str:
        if not content.startswith(b"PK\x03\x04"):
            raise ValidationError("Invalid DOCX file signature (not a valid ZIP/OOXML package).")
        try:
            with zipfile.ZipFile(io.BytesIO(content), "r") as zf:
                names = set(zf.namelist())
                required_entries = {"[Content_Types].xml", "_rels/.rels", "word/document.xml"}
                missing = required_entries - names
                if missing:
                    raise ValidationError(
                        f"Malformed DOCX OOXML archive; missing required package entries: {', '.join(sorted(missing))}"
                    )
                xml_bytes = zf.read("word/document.xml")
        except zipfile.BadZipFile as exc:
            raise ValidationError("Corrupted DOCX ZIP archive.") from exc

        # Try python-docx if available, and fall back to direct OOXML element parsing
        try:
            import docx  # type: ignore

            doc = docx.Document(io.BytesIO(content))
            paragraphs = [p.text.strip() for p in doc.paragraphs if p.text and p.text.strip()]
            if paragraphs:
                return "\n\n".join(paragraphs)
        except ImportError:
            pass
        except Exception as exc:
            raise ValidationError(f"Failed to parse DOCX document: {exc}") from exc

        try:
            root = ET.fromstring(xml_bytes)
            ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
            paragraphs: List[str] = []
            for p_elem in root.findall(".//w:p", ns):
                runs = [t_elem.text for t_elem in p_elem.findall(".//w:t", ns) if t_elem.text]
                joined = "".join(runs).strip()
                if joined:
                    paragraphs.append(joined)
            return "\n\n".join(paragraphs)
        except ET.ParseError as exc:
            raise ValidationError("Invalid XML inside DOCX word/document.xml.") from exc

    @staticmethod
    def _parse_pdf(content: bytes) -> str:
        if not content.startswith(b"%PDF-"):
            raise ValidationError("Invalid PDF signature (missing %PDF- header).")
        if b"startxref" not in content or b"%%EOF" not in content:
            raise ValidationError("Invalid or truncated PDF structure (missing startxref / %%EOF).")

        # Use pypdf if installed in runtime
        try:
            import pypdf  # type: ignore

            reader = pypdf.PdfReader(io.BytesIO(content))
            pages = [page.extract_text() or "" for page in reader.pages]
            joined = "\n\n".join(p.strip() for p in pages if p.strip())
            if joined:
                return joined
        except ImportError:
            pass
        except Exception as exc:
            raise ValidationError(f"Failed to parse PDF document: {exc}") from exc

        # Extract text strings from valid PDF content streams
        raw_latin = content.decode("latin-1", errors="ignore")
        matches = re.findall(r"\(([^()\\]*(?:\\.[^()\\]*)*)\)\s*Tj", raw_latin)
        if not matches:
            matches = re.findall(r"\(([^()]+)\)", raw_latin)
        cleaned_lines: List[str] = []
        for m in matches:
            unescaped = m.replace("\\(", "(").replace("\\)", ")").replace("\\\\", "\\").strip()
            if unescaped and not unescaped.startswith("PDF-"):
                cleaned_lines.append(unescaped)
        return "\n".join(cleaned_lines)
