"""Tenant-isolated multi-query RAG engine with RRF fusion, reranking, and evidence evaluation."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from app.domain.enums import EvidenceState
from app.domain.models import KnowledgeVectorChunk, MessageRecord
from app.providers.embeddings import BaseEmbeddingProvider
from app.providers.llm import BaseLlmProvider, LlmChatMessage
from app.providers.vector import BaseVectorProvider

WORD_RE = re.compile(r"[\w\u0900-\u097F]+", re.UNICODE)

STOPWORDS: Set[str] = {
    "what", "are", "is", "the", "a", "an", "for", "to", "of", "in", "on", "at",
    "do", "you", "have", "can", "please", "tell", "me", "about", "how", "much",
    "does", "it", "that", "this", "they", "their", "your", "our", "and", "or",
    "with", "from", "by", "kya", "hai", "hain", "ka", "ki", "ke", "mein", "se",
    "ko", "aur", "batao", "bataiye", "aap", "aapka", "aapki", "kitna", "kitne",
    "kab", "kahan", "uske", "iske", "baare", "bare", "क्या", "है", "हैं", "का",
    "की", "के", "में", "से", "को", "और", "बताइए", "आप", "आपका", "आपकी", "कितना",
}

# Cross-lingual concept synonyms so Hindi / Hinglish business queries retrieve English/mixed documents and vice versa
MULTILINGUAL_SYNONYMS: Dict[str, List[str]] = {
    "price": ["pricing", "cost", "fee", "rate", "membership", "plan", "किराया", "कीमत", "फीस", "सदस्यता"],
    "pricing": ["price", "cost", "fee", "membership", "plan", "कीमत", "फीस"],
    "cost": ["price", "pricing", "fee", "rate", "कीमत", "खर्च"],
    "kimat": ["price", "pricing", "cost", "fee", "rate", "membership"],
    "keemat": ["price", "pricing", "cost", "fee", "rate"],
    "fees": ["price", "pricing", "cost", "fee", "membership"],
    "fee": ["price", "pricing", "cost", "membership"],
    "kiraya": ["price", "rent", "cost", "rate"],
    "कीमत": ["price", "pricing", "cost", "fee", "rate", "membership", "plan"],
    "फीस": ["price", "pricing", "cost", "fee", "membership"],
    "शुल्क": ["price", "fee", "cost", "charge"],
    "सदस्यता": ["membership", "subscription", "plan", "price"],
    "hours": ["opening", "timing", "schedule", "open", "close", "समय", "टाइम"],
    "timing": ["hours", "opening", "schedule", "open", "close", "समय"],
    "samay": ["hours", "opening", "timing", "schedule", "open"],
    "time": ["hours", "opening", "timing", "schedule", "open"],
    "समय": ["hours", "opening", "timing", "schedule", "open", "close"],
    "कब": ["when", "hours", "opening", "timing", "schedule"],
    "खुलता": ["open", "opening", "hours", "timing"],
    "refund": ["return", "cancellation", "policy", "money back", "रिफंड", "वापसी"],
    "cancel": ["cancellation", "refund", "policy", "रद्द"],
    "policy": ["rules", "terms", "refund", "cancellation", "नीति"],
    "रिफंड": ["refund", "return", "cancellation", "policy"],
    "contact": ["email", "phone", "support", "reach", "call", "संपर्क", "फोन"],
    "संपर्क": ["contact", "email", "phone", "support"],
    "services": ["offer", "features", "plans", "facilities", "सेवाएं", "सुविधाएं"],
    "सेवाएं": ["services", "offer", "features", "plans"],
    "सुविधाएं": ["facilities", "services", "amenities", "features"],
    "delivery": ["shipping", "dispatch", "order", "डिलीवरी"],
    "डिलीवरी": ["delivery", "shipping", "order"],
}

FOLLOWUP_MARKERS = (
    "it", "that", "this", "those", "them", "its", "uske", "iske", "uska", "iska",
    "unke", "wahi", "us", "उसके", "इसके", "उसका", "इसका", "उनके", "उसी",
)


@dataclass
class RetrievalResult:
    evidence_state: EvidenceState
    chunks: List[KnowledgeVectorChunk] = field(default_factory=list)
    sources: List[Dict[str, Any]] = field(default_factory=list)
    expanded_queries: List[str] = field(default_factory=list)
    reformulated_query: str = ""
    top_score: float = 0.0
    coverage_ratio: float = 0.0


class AdvancedRagService:
    """
    Implements tenant-isolated hybrid retrieval:
    1. Conversational follow-up resolution using bounded prior turns
    2. Multi-query decomposition + multilingual query expansion
    3. Optional bounded LLM query reformulation connected directly to retrieval
    4. Dense vector search + paginated lexical/phrase matching
    5. Reciprocal Rank Fusion (RRF) + reranking
    6. Strict Evidence Assessment (SUPPORTED, PARTIAL, UNKNOWN)
    """

    def __init__(
        self,
        embedding_provider: BaseEmbeddingProvider,
        vector_provider: BaseVectorProvider,
        llm_provider: Optional[BaseLlmProvider] = None,
        enable_query_reformulation: bool = True,
    ) -> None:
        self.embedding_provider = embedding_provider
        self.vector_provider = vector_provider
        self.llm_provider = llm_provider
        self.enable_query_reformulation = enable_query_reformulation

    @staticmethod
    def tokenize(text: str) -> List[str]:
        return [w.lower() for w in WORD_RE.findall(text or "") if len(w) >= 2]

    def extract_significant_terms(self, text: str) -> List[str]:
        tokens = self.tokenize(text)
        terms = [t for t in tokens if t not in STOPWORDS]
        return terms if terms else tokens

    def resolve_followup_query(self, query: str, history: List[MessageRecord]) -> str:
        """Resolve pronouns/references ('it', 'that', 'uske baare mein') against recent turns."""
        tokens = set(self.tokenize(query))
        has_reference = any(marker in tokens for marker in FOLLOWUP_MARKERS) or len(tokens) <= 4
        if not has_reference or not history:
            return query

        recent_user_turns = [m.content for m in history if m.role == "user" and m.content.strip()]
        if not recent_user_turns:
            return query
        last_context = recent_user_turns[-1]
        context_terms = self.extract_significant_terms(last_context)[:6]
        if not context_terms:
            return query
        return f"{query} ({' '.join(context_terms)})"

    def build_query_variants(self, query: str, history: List[MessageRecord]) -> Tuple[List[str], str]:
        """Generate resolved, expanded, decomposed, and LLM-reformulated queries."""
        resolved = self.resolve_followup_query(query, history)
        variants: List[str] = [query.strip()]
        if resolved.strip() and resolved.strip() != query.strip():
            variants.append(resolved.strip())

        # Sub-query decomposition on conjunctions
        parts = [
            p.strip()
            for p in re.split(r"(?:\band\b|\bor\b|\baur\b|और|\?|,|;)", resolved, flags=re.IGNORECASE)
            if len(p.strip()) >= 6
        ]
        for p in parts[:3]:
            if p not in variants:
                variants.append(p)

        # Multilingual synonym expansion
        tokens = self.tokenize(resolved)
        expanded_terms: List[str] = []
        for tok in tokens:
            if tok in MULTILINGUAL_SYNONYMS:
                expanded_terms.extend(MULTILINGUAL_SYNONYMS[tok])
        if expanded_terms:
            unique_exp = list(dict.fromkeys(expanded_terms))[:10]
            variants.append(f"{resolved} {' '.join(unique_exp)}")

        reformulated = ""
        if self.enable_query_reformulation and self.llm_provider is not None:
            try:
                res = self.llm_provider.generate(
                    messages=[
                        LlmChatMessage(
                            role="system",
                            content=(
                                "[ORBIT_DIRECTIVE_START]QUERY_REFORMULATION[ORBIT_DIRECTIVE_END]\n"
                                "Rewrite the user question into a concise search query preserving key entities."
                            ),
                        ),
                        LlmChatMessage(role="user", content=resolved),
                    ],
                    temperature=0.0,
                    max_tokens=80,
                )
                candidate = res.content.strip()
                if candidate and candidate not in variants:
                    reformulated = candidate
                    variants.append(candidate)
                else:
                    reformulated = resolved
            except Exception:
                reformulated = resolved

        return variants[:6], reformulated

    def _paginated_lexical_search(
        self,
        client_id: str,
        queries: List[str],
        top_k: int = 5,
    ) -> List[Tuple[KnowledgeVectorChunk, float]]:
        """Scan tenant's active chunks using proper pagination (never assuming a single fixed page)."""
        query_terms: Set[str] = set()
        for q in queries:
            for t in self.extract_significant_terms(q):
                query_terms.add(t)
                if t in MULTILINGUAL_SYNONYMS:
                    query_terms.update(w.lower() for w in MULTILINGUAL_SYNONYMS[t])

        if not query_terms:
            return []

        scored: List[Tuple[KnowledgeVectorChunk, float]] = []
        page = 1
        page_size = 50
        while True:
            batch, total = self.vector_provider.list_active_chunks(
                client_id=client_id, page=page, page_size=page_size
            )
            if not batch:
                break
            for chunk in batch:
                if chunk.client_id != client_id or not chunk.is_active:
                    continue
                chunk_lower = chunk.content.lower()
                chunk_tokens = set(self.tokenize(chunk_lower))
                matched = query_terms.intersection(chunk_tokens)
                phrase_hits = sum(1 for term in query_terms if " " in term and term in chunk_lower)
                hit_count = len(matched) + phrase_hits * 2
                if hit_count > 0:
                    lexical_score = min(1.0, hit_count / max(1.0, min(len(query_terms), 5.0)))
                    scored.append((chunk, lexical_score))
            if page * page_size >= total:
                break
            page += 1

        scored.sort(key=lambda item: item[1], reverse=True)
        return scored[: max(1, top_k * 2)]

    def retrieve(
        self,
        client_id: str,
        query: str,
        history: Optional[List[MessageRecord]] = None,
        top_k: int = 5,
        min_similarity: float = 0.25,
    ) -> RetrievalResult:
        history = history or []
        variants, reformulated = self.build_query_variants(query, history)

        # 1. Dense vector retrieval across query variants
        dense_rankings: List[List[KnowledgeVectorChunk]] = []
        for variant in variants:
            q_emb = self.embedding_provider.embed_query(variant)
            hits = self.vector_provider.search(
                client_id=client_id,
                query_embedding=q_emb,
                top_k=max(3, top_k),
                min_similarity=min(0.15, min_similarity),
            )
            # Enforce explicit tenant check
            safe_hits = [h for h in hits if h.client_id == client_id]
            dense_rankings.append(safe_hits)

        # 2. Paginated lexical retrieval
        lexical_hits = self._paginated_lexical_search(
            client_id=client_id,
            queries=variants,
            top_k=top_k,
        )

        # 3. Reciprocal Rank Fusion (RRF) + Reranking
        rrf_scores: Dict[str, float] = {}
        chunk_map: Dict[str, KnowledgeVectorChunk] = {}
        best_dense_sim: Dict[str, float] = {}
        best_lex_sim: Dict[str, float] = {}

        k_rrf = 60.0
        for ranking in dense_rankings:
            for rank_idx, chunk in enumerate(ranking):
                rrf_scores[chunk.id] = rrf_scores.get(chunk.id, 0.0) + (1.0 / (k_rrf + rank_idx + 1))
                chunk_map[chunk.id] = chunk
                best_dense_sim[chunk.id] = max(best_dense_sim.get(chunk.id, 0.0), chunk.similarity)

        for rank_idx, (chunk, lex_score) in enumerate(lexical_hits):
            rrf_scores[chunk.id] = rrf_scores.get(chunk.id, 0.0) + (1.2 / (k_rrf + rank_idx + 1))
            chunk_map[chunk.id] = chunk
            best_lex_sim[chunk.id] = max(best_lex_sim.get(chunk.id, 0.0), lex_score)

        if not chunk_map:
            return RetrievalResult(
                evidence_state=EvidenceState.UNKNOWN,
                chunks=[],
                sources=[],
                expanded_queries=variants,
                reformulated_query=reformulated,
                top_score=0.0,
                coverage_ratio=0.0,
            )

        # Rerank combining dense similarity, lexical overlap, and RRF rank
        reranked: List[KnowledgeVectorChunk] = []
        for cid, chunk in chunk_map.items():
            d_sim = best_dense_sim.get(cid, 0.0)
            l_sim = best_lex_sim.get(cid, 0.0)
            rrf_bonus = min(0.15, rrf_scores.get(cid, 0.0) * 3.0)
            combined_score = round((0.45 * d_sim) + (0.45 * l_sim) + rrf_bonus, 4)
            chunk.similarity = combined_score
            if combined_score >= min_similarity or l_sim >= 0.35:
                reranked.append(chunk)

        reranked.sort(key=lambda c: c.similarity, reverse=True)
        top_chunks = reranked[: max(1, top_k)]

        # 4. Evidence Assessment (distinguishing retrieval relevance from actual factual coverage)
        evidence_state, coverage_ratio = self._assess_evidence(
            original_query=query,
            resolved_query=variants[1] if len(variants) > 1 else query,
            chunks=top_chunks,
            min_similarity=min_similarity,
        )

        sources = [
            {
                "id": c.id,
                "sourceId": c.source_id,
                "filename": c.source_filename,
                "chunkIndex": c.chunk_index,
                "version": c.version,
                "similarity": round(c.similarity, 4),
                "snippet": c.content[:220],
            }
            for c in top_chunks
        ]

        return RetrievalResult(
            evidence_state=evidence_state,
            chunks=top_chunks if evidence_state != EvidenceState.UNKNOWN else [],
            sources=sources if evidence_state != EvidenceState.UNKNOWN else [],
            expanded_queries=variants,
            reformulated_query=reformulated,
            top_score=top_chunks[0].similarity if top_chunks else 0.0,
            coverage_ratio=coverage_ratio,
        )

    def _assess_evidence(
        self,
        original_query: str,
        resolved_query: str,
        chunks: List[KnowledgeVectorChunk],
        min_similarity: float,
    ) -> Tuple[EvidenceState, float]:
        """
        Never mark an answer SUPPORTED merely because two chunks pass a weak similarity threshold.
        Evaluate whether retrieved chunks actually cover the significant concepts of the query.
        """
        if not chunks:
            return EvidenceState.UNKNOWN, 0.0

        query_terms = self.extract_significant_terms(resolved_query or original_query)
        if not query_terms:
            return EvidenceState.UNKNOWN, 0.0

        combined_evidence_lower = " ".join(c.content.lower() for c in chunks)
        evidence_tokens = set(self.tokenize(combined_evidence_lower))

        covered_terms = 0
        for term in query_terms:
            synonyms = {term}
            if term in MULTILINGUAL_SYNONYMS:
                synonyms.update(w.lower() for w in MULTILINGUAL_SYNONYMS[term])
            if synonyms.intersection(evidence_tokens) or any(s in combined_evidence_lower for s in synonyms if len(s) >= 4):
                covered_terms += 1

        coverage = round(covered_terms / max(1, len(query_terms)), 4)
        top_sim = chunks[0].similarity

        if coverage == 0.0 or top_sim < min_similarity:
            return EvidenceState.UNKNOWN, coverage
        if coverage >= 0.50 and top_sim >= max(min_similarity, 0.30):
            return EvidenceState.SUPPORTED, coverage
        if coverage >= 0.25 and top_sim >= min_similarity:
            return EvidenceState.PARTIAL, coverage
        return EvidenceState.UNKNOWN, coverage
