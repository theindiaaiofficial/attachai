"""Grounding validation tests for numeric claims, contact details, and guarantees."""

from __future__ import annotations

import unittest

from app.domain.enums import EvidenceState
from app.domain.models import KnowledgeVectorChunk
from app.services.grounding import GroundingService


class TestGrounding(unittest.TestCase):
    def setUp(self) -> None:
        self.grounding = GroundingService()
        self.chunk = KnowledgeVectorChunk(
            id="c1",
            client_id="t1",
            source_id="s1",
            source_filename="pricing.txt",
            version=1,
            is_active=True,
            chunk_index=0,
            content="Standard plan costs $29 per month. Support email is support@acme.com and phone is +1-800-555-0199.",
            embedding=[0.1] * 128,
        )

    def test_valid_supported_answer_passes(self) -> None:
        res = self.grounding.validate_answer(
            candidate_answer="The Standard plan costs $29 per month and you can email support@acme.com.",
            evidence_chunks=[self.chunk],
            evidence_state=EvidenceState.SUPPORTED,
            fallback_answer="Fallback",
        )
        self.assertTrue(res.is_grounded)
        self.assertEqual(res.evidence_state, EvidenceState.SUPPORTED)

    def test_invented_numeric_price_rejected(self) -> None:
        res = self.grounding.validate_answer(
            candidate_answer="The Standard plan costs $15 per month with a 50% discount.",
            evidence_chunks=[self.chunk],
            evidence_state=EvidenceState.SUPPORTED,
            fallback_answer="Fallback",
        )
        self.assertFalse(res.is_grounded)
        self.assertEqual(res.final_answer, "Fallback")
        self.assertTrue(any("unsupported_numeric_claim" in v for v in res.violations))

    def test_invented_email_and_phone_rejected(self) -> None:
        res_email = self.grounding.validate_answer(
            candidate_answer="Contact us at sales@invented-domain.com.",
            evidence_chunks=[self.chunk],
            evidence_state=EvidenceState.SUPPORTED,
            fallback_answer="Fallback",
        )
        self.assertFalse(res_email.is_grounded)
        self.assertIn("invented_email:sales@invented-domain.com", res_email.violations)

        res_phone = self.grounding.validate_answer(
            candidate_answer="Call us at +1-888-999-0000.",
            evidence_chunks=[self.chunk],
            evidence_state=EvidenceState.SUPPORTED,
            fallback_answer="Fallback",
        )
        self.assertFalse(res_phone.is_grounded)

    def test_unsupported_guarantee_rejected(self) -> None:
        res = self.grounding.validate_answer(
            candidate_answer="Our plan costs $29 and comes with a 100% guaranteed lifetime free upgrade.",
            evidence_chunks=[self.chunk],
            evidence_state=EvidenceState.SUPPORTED,
            fallback_answer="Fallback",
        )
        self.assertFalse(res.is_grounded)
        self.assertTrue(any("unsupported_guarantee" in v for v in res.violations))

    def test_unknown_evidence_returns_fallback(self) -> None:
        res = self.grounding.validate_answer(
            candidate_answer="Some answer",
            evidence_chunks=[],
            evidence_state=EvidenceState.UNKNOWN,
            fallback_answer="Configured fallback message",
        )
        self.assertFalse(res.is_grounded)
        self.assertEqual(res.final_answer, "Configured fallback message")


if __name__ == "__main__":
    unittest.main()
