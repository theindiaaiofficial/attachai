"""Evidence-aware grounding validator preventing hallucinated numbers, prices, dates, contacts, and guarantees."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List

from app.domain.enums import EvidenceState
from app.domain.models import KnowledgeVectorChunk
from app.utils.pii import EMAIL_REGEX, PHONE_REGEX

NUMBER_TOKEN_RE = re.compile(r"(?:[$£€₹]\s*)?\b\d+(?:[.,]\d+)?%?\b")
UNSUPPORTED_GUARANTEE_PATTERNS = (
    "100% guaranteed",
    "lifetime free",
    "unlimited free",
    "instant full refund without conditions",
    "guaranteed profit",
)


@dataclass
class GroundingValidationResult:
    is_grounded: bool
    final_answer: str
    evidence_state: EvidenceState
    violations: List[str] = field(default_factory=list)


class GroundingService:
    """
    Checks generated answers against retrieved evidence chunks for:
    - Unsupported numerical claims, prices, and percentages
    - Invented email addresses or phone numbers
    - Unsupported guarantees or absolute claims absent from evidence
    - Insufficient evidence state (UNKNOWN)
    """

    @staticmethod
    def _normalize_number(token: str) -> str:
        cleaned = re.sub(r"^[$£€₹\s]+", "", token.strip())
        cleaned = cleaned.replace(",", "")
        return cleaned.rstrip("%")

    def validate_answer(
        self,
        candidate_answer: str,
        evidence_chunks: List[KnowledgeVectorChunk],
        evidence_state: EvidenceState,
        fallback_answer: str,
    ) -> GroundingValidationResult:
        if evidence_state == EvidenceState.UNKNOWN or not evidence_chunks:
            return GroundingValidationResult(
                is_grounded=False,
                final_answer=fallback_answer,
                evidence_state=EvidenceState.UNKNOWN,
                violations=["insufficient_evidence"],
            )

        evidence_text = "\n".join(c.content for c in evidence_chunks)
        evidence_lower = evidence_text.lower()
        answer_lower = (candidate_answer or "").lower()
        violations: List[str] = []

        # 1. Validate numeric / price / date claims
        evidence_numbers = {
            self._normalize_number(m.group(0)) for m in NUMBER_TOKEN_RE.finditer(evidence_text)
        }
        answer_numbers = {
            self._normalize_number(m.group(0)) for m in NUMBER_TOKEN_RE.finditer(candidate_answer)
        }
        # Allow basic ordinal digits "1" or "2" only if not currency/percentage, but reject any invented numbers
        for raw_match in NUMBER_TOKEN_RE.finditer(candidate_answer):
            raw_tok = raw_match.group(0).strip()
            norm_num = self._normalize_number(raw_tok)
            is_price_or_pct = any(ch in raw_tok for ch in ("$", "£", "€", "₹", "%"))
            if norm_num not in evidence_numbers:
                if is_price_or_pct or len(norm_num) >= 2 or norm_num not in ("1", "2"):
                    violations.append(f"unsupported_numeric_claim:{raw_tok}")

        # 2. Validate contact details (emails & phones)
        evidence_emails = {m.group(0).lower() for m in EMAIL_REGEX.finditer(evidence_text)}
        for email_match in EMAIL_REGEX.finditer(candidate_answer):
            found_email = email_match.group(0).lower()
            if found_email not in evidence_emails:
                violations.append(f"invented_email:{found_email}")

        evidence_phones = {re.sub(r"\D", "", m.group(0)) for m in PHONE_REGEX.finditer(evidence_text)}
        for phone_match in PHONE_REGEX.finditer(candidate_answer):
            digits = re.sub(r"\D", "", phone_match.group(0))
            if len(digits) >= 7 and digits not in evidence_phones:
                violations.append(f"invented_phone:{phone_match.group(0)}")

        # 3. Validate unsupported guarantees
        for phrase in UNSUPPORTED_GUARANTEE_PATTERNS:
            if phrase in answer_lower and phrase not in evidence_lower:
                violations.append(f"unsupported_guarantee:{phrase}")

        if violations:
            return GroundingValidationResult(
                is_grounded=False,
                final_answer=fallback_answer,
                evidence_state=EvidenceState.UNKNOWN,
                violations=violations,
            )

        return GroundingValidationResult(
            is_grounded=True,
            final_answer=candidate_answer.strip(),
            evidence_state=evidence_state,
            violations=[],
        )
