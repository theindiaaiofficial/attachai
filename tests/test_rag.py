"""Advanced RAG retrieval, RRF fusion, evidence evaluation, and grounding tests."""

from __future__ import annotations

import unittest

from app.domain.enums import EvidenceState
from app.domain.models import MessageRecord
from tests.conftest import IsolatedOrbitTestEnv


class TestRagAndEvidence(unittest.TestCase):
    def setUp(self) -> None:
        self.env = IsolatedOrbitTestEnv()
        self.t1, _ = self.env.create_sample_tenant(name="PureGym", slug="puregym")
        self.t2, _ = self.env.create_sample_tenant(name="Gousto", slug="gousto")

        self.env.container.knowledge_service.ingest_document(
            client_id=self.t1["id"],
            filename="gym_membership.txt",
            content=(
                b"PureGym Core Membership costs $25 per month with 24/7 gym access. "
                b"Plus Membership costs $39 per month and includes multi-gym access and guest passes. "
                b"Opening hours: Open 24 hours a day, 7 days a week."
            ),
        )
        self.env.container.knowledge_service.ingest_document(
            client_id=self.t2["id"],
            filename="recipe_boxes.txt",
            content=b"Gousto 4-recipe family box costs $48 per week with free Sunday delivery.",
        )

    def tearDown(self) -> None:
        self.env.cleanup()

    def test_supported_evidence_for_matching_tenant_question(self) -> None:
        res = self.env.container.rag_service.retrieve(
            client_id=self.t1["id"],
            query="What is the price of the PureGym Core Membership and opening hours?",
        )
        self.assertEqual(res.evidence_state, EvidenceState.SUPPORTED)
        self.assertGreaterEqual(len(res.chunks), 1)
        self.assertIn("$25", res.chunks[0].content)

    def test_tenant_isolation_never_retrieves_other_tenant_chunks(self) -> None:
        res = self.env.container.rag_service.retrieve(
            client_id=self.t1["id"],
            query="How much is the Gousto 4-recipe family box?",
        )
        self.assertEqual(res.evidence_state, EvidenceState.UNKNOWN)
        self.assertEqual(len(res.chunks), 0)

    def test_weak_similarity_chunks_do_not_falsely_report_supported(self) -> None:
        res = self.env.container.rag_service.retrieve(
            client_id=self.t1["id"],
            query="Do you offer cryptocurrency mortgage refinancing in Antarctica?",
            min_similarity=0.01,
        )
        self.assertEqual(res.evidence_state, EvidenceState.UNKNOWN)

    def test_multilingual_hindi_and_hinglish_query_expansion_retrieves_evidence(self) -> None:
        res_hi = self.env.container.rag_service.retrieve(
            client_id=self.t1["id"],
            query="PureGym membership ki kimat aur samay kya hai?",
        )
        self.assertIn(res_hi.evidence_state, (EvidenceState.SUPPORTED, EvidenceState.PARTIAL))
        self.assertGreaterEqual(len(res_hi.chunks), 1)

        res_deva = self.env.container.rag_service.retrieve(
            client_id=self.t1["id"],
            query="सदस्यता की कीमत और समय क्या है?",
        )
        self.assertIn(res_deva.evidence_state, (EvidenceState.SUPPORTED, EvidenceState.PARTIAL))

    def test_followup_pronoun_resolution_uses_conversation_history(self) -> None:
        history = [
            MessageRecord(
                id="m1",
                conversation_id="c1",
                client_id=self.t1["id"],
                role="user",
                content="Tell me about Plus Membership",
            )
        ]
        res = self.env.container.rag_service.retrieve(
            client_id=self.t1["id"],
            query="What is the price of that?",
            history=history,
        )
        self.assertIn(res.evidence_state, (EvidenceState.SUPPORTED, EvidenceState.PARTIAL))
        self.assertTrue(any("$39" in c.content for c in res.chunks))


if __name__ == "__main__":
    unittest.main()
