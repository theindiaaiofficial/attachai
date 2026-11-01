"""Knowledge ingestion, valid DOCX/PDF fixtures, CSV quoting, and safe versioned reindexing tests."""

from __future__ import annotations

import io
import unittest
import zipfile

from app.core.exceptions import ValidationError
from app.services.parser import build_valid_docx_bytes, build_valid_pdf_bytes
from tests.conftest import IsolatedOrbitTestEnv


class TestKnowledge(unittest.TestCase):
    def setUp(self) -> None:
        self.env = IsolatedOrbitTestEnv(max_upload_size_bytes=50_000)
        self.tenant, self.api_key = self.env.create_sample_tenant()
        self.client_id = self.tenant["id"]

    def tearDown(self) -> None:
        self.env.cleanup()

    def test_txt_and_markdown_ingestion(self) -> None:
        txt_rec = self.env.container.knowledge_service.ingest_document(
            client_id=self.client_id,
            filename="hours.txt",
            content=b"Our gym is open 24 hours a day, 7 days a week.",
            mime_type="text/plain",
        )
        self.assertEqual(txt_rec.status, "ready")
        self.assertGreaterEqual(txt_rec.chunk_count, 1)

        md_rec = self.env.container.knowledge_service.ingest_document(
            client_id=self.client_id,
            filename="plans.md",
            content=b"# Membership Plans\n\nCore Plan costs $29/month.\nPlus Plan costs $49/month.",
            mime_type="text/markdown",
        )
        self.assertEqual(md_rec.status, "ready")
        self.assertGreaterEqual(md_rec.chunk_count, 1)

    def test_csv_ingestion_with_quoted_escaped_and_multiline_fields(self) -> None:
        csv_bytes = (
            b'Plan,Price,Details\n'
            b'"Core ""24/7"" Access","$29.99","Includes:\n- Free weights\n- Cardio zone"\n'
        )
        rec = self.env.container.knowledge_service.ingest_document(
            client_id=self.client_id,
            filename="pricing.csv",
            content=csv_bytes,
            mime_type="text/csv",
        )
        self.assertEqual(rec.status, "ready")
        chunks, total = self.env.container.vector_provider.list_active_chunks(self.client_id)
        self.assertEqual(total, 1)
        self.assertIn('Core "24/7" Access', chunks[0].content)
        self.assertIn("$29.99", chunks[0].content)

    def test_valid_docx_ingestion_and_invalid_docx_rejection(self) -> None:
        valid_docx = build_valid_docx_bytes(
            [
                "PureGym Personal Training Policy",
                "Sessions cost £35 per hour and require 24 hours notice for cancellation.",
            ]
        )
        rec = self.env.container.knowledge_service.ingest_document(
            client_id=self.client_id,
            filename="pt_policy.docx",
            content=valid_docx,
            mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        self.assertEqual(rec.status, "ready")
        self.assertGreaterEqual(rec.chunk_count, 1)

        # Invalid DOCX missing [Content_Types].xml and _rels/.rels must be rejected by parser validation
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("word/document.xml", "<w:document/>")
        with self.assertRaises(ValidationError):
            self.env.container.knowledge_service.ingest_document(
                client_id=self.client_id,
                filename="broken.docx",
                content=buf.getvalue(),
            )

    def test_valid_pdf_ingestion_and_truncated_pdf_rejection(self) -> None:
        valid_pdf = build_valid_pdf_bytes(
            "Gousto Recipe Box Delivery: Standard delivery is free on orders over £30."
        )
        rec = self.env.container.knowledge_service.ingest_document(
            client_id=self.client_id,
            filename="delivery.pdf",
            content=valid_pdf,
            mime_type="application/pdf",
        )
        self.assertEqual(rec.status, "ready")
        self.assertGreaterEqual(rec.chunk_count, 1)

        # PDF without startxref must be rejected
        invalid_pdf = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n"
        with self.assertRaises(ValidationError):
            self.env.container.knowledge_service.ingest_document(
                client_id=self.client_id,
                filename="truncated.pdf",
                content=invalid_pdf,
                mime_type="application/pdf",
            )

    def test_unsupported_format_empty_file_and_oversized_file_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            self.env.container.knowledge_service.ingest_document(
                client_id=self.client_id,
                filename="malware.exe",
                content=b"binary",
            )
        with self.assertRaises(ValidationError):
            self.env.container.knowledge_service.ingest_document(
                client_id=self.client_id,
                filename="empty.txt",
                content=b"   ",
            )
        with self.assertRaises(ValidationError):
            self.env.container.knowledge_service.ingest_document(
                client_id=self.client_id,
                filename="huge.txt",
                content=b"x" * 60_000,
            )

    def test_safe_version_replacement_and_failed_reupload_preserves_active_index(self) -> None:
        v1 = self.env.container.knowledge_service.ingest_document(
            client_id=self.client_id,
            filename="policy.txt",
            content=b"Refund window is 14 days from purchase.",
            mime_type="text/plain",
        )
        self.assertEqual(v1.active_version, 1)

        # Re-upload valid v2
        v2 = self.env.container.knowledge_service.ingest_document(
            client_id=self.client_id,
            filename="policy.txt",
            content=b"Refund window is now 30 days from purchase.",
            mime_type="text/plain",
        )
        self.assertEqual(v2.active_version, 2)
        chunks, _ = self.env.container.vector_provider.list_active_chunks(self.client_id)
        self.assertEqual(len(chunks), 1)
        self.assertIn("30 days", chunks[0].content)

        # Now attempt a failing re-upload (empty content) -> v2 must remain active!
        with self.assertRaises(ValidationError):
            self.env.container.knowledge_service.ingest_document(
                client_id=self.client_id,
                filename="policy.txt",
                content=b"   ",
                mime_type="text/plain",
            )
        after_fail = self.env.container.repository.get_knowledge_file(self.client_id, v2.id)
        self.assertIsNotNone(after_fail)
        assert after_fail is not None
        self.assertEqual(after_fail.status, "ready")
        self.assertEqual(after_fail.active_version, 2)
        active_chunks, _ = self.env.container.vector_provider.list_active_chunks(self.client_id)
        self.assertEqual(len(active_chunks), 1)
        self.assertIn("30 days", active_chunks[0].content)

    def test_rebuild_document_increments_active_version_safely(self) -> None:
        rec = self.env.container.knowledge_service.ingest_document(
            client_id=self.client_id,
            filename="guide.txt",
            content=b"Support email is help@acme.com and phone is +1-555-234-5678.",
            mime_type="text/plain",
        )
        rebuilt = self.env.container.knowledge_service.rebuild_document(self.client_id, rec.id)
        self.assertEqual(rebuilt.status, "ready")
        self.assertEqual(rebuilt.active_version, 2)


if __name__ == "__main__":
    unittest.main()
