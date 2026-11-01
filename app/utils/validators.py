"""Input, filename, storage path, and lead validators."""

from __future__ import annotations

import re
from typing import Tuple

from app.core.exceptions import ValidationError

ALLOWED_EXTENSIONS = {".txt", ".md", ".csv", ".docx", ".pdf"}
ALLOWED_MIME_TYPES = {
    "text/plain",
    "text/markdown",
    "text/csv",
    "application/csv",
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/octet-stream",
}

SLUG_REGEX = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
EMAIL_VALIDATION_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def sanitize_filename(filename: str) -> str:
    """Normalize a filename safely without path traversal characters."""
    if not filename or not filename.strip():
        raise ValidationError("Filename is required.")
    base = filename.replace("\\", "/").split("/")[-1].strip()
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._")
    if not safe:
        safe = "document.txt"
    return safe[:120]


def build_storage_object_path(client_id: str, source_id: str, filename: str) -> Tuple[str, str]:
    """
    Build collision-free object storage path `<tenant-id>/<source-id>/<safe-filename>`.
    Returns (safe_filename, storage_path).
    """
    safe_name = sanitize_filename(filename)
    return safe_name, f"{client_id}/{source_id}/{safe_name}"


def detect_extension(filename: str) -> str:
    safe = sanitize_filename(filename).lower()
    if "." not in safe:
        return ""
    return "." + safe.rsplit(".", 1)[-1]


def validate_upload_metadata(filename: str, mime_type: str, size_bytes: int, max_bytes: int) -> str:
    """Validate file extension, MIME type, and size limit. Returns normalized extension."""
    if size_bytes <= 0:
        raise ValidationError("Uploaded file is empty.")
    if size_bytes > max_bytes:
        raise ValidationError(f"File exceeds maximum allowed size of {max_bytes} bytes.")

    ext = detect_extension(filename)
    if ext not in ALLOWED_EXTENSIONS:
        raise ValidationError(
            f"Unsupported document format {ext or filename!r}. Supported formats: PDF, DOCX, TXT, Markdown, CSV."
        )
    normalized_mime = (mime_type or "application/octet-stream").split(";")[0].strip().lower()
    if normalized_mime and normalized_mime not in ALLOWED_MIME_TYPES:
        raise ValidationError(f"Unsupported MIME type: {normalized_mime}")
    return ext


def validate_slug(slug: str) -> str:
    cleaned = (slug or "").strip().lower()
    if not cleaned or not SLUG_REGEX.match(cleaned):
        raise ValidationError("Slug must contain lowercase letters, numbers, and hyphens only.")
    return cleaned


def validate_lead_fields(name: str, email: str, phone: str) -> Tuple[str, str, str]:
    clean_name = (name or "").strip()
    clean_email = (email or "").strip().lower()
    clean_phone = (phone or "").strip()

    if not clean_name:
        raise ValidationError("Lead name is required.")
    if not clean_email and not clean_phone:
        raise ValidationError("Either an email address or a phone number is required.")
    if clean_email and not EMAIL_VALIDATION_REGEX.match(clean_email):
        raise ValidationError("Invalid email address format.")
    return clean_name, clean_email, clean_phone
