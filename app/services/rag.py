import json
from dataclasses import dataclass
from typing import Any

from app.models import Product
from app.services.enrichment import GroundedCitation, GroundedField
from app.services.llm import LLMClient, LLMRequest
from app.services.search import SearchHit, SemanticSearchService


@dataclass(frozen=True)
class CatalogRAGAnswer:
    answer: str
    citations: list[GroundedCitation]
    matches: list[SearchHit]


class InternalCatalogRAG:
    def __init__(self, search: SemanticSearchService, llm: LLMClient):
        self.search = search
        self.llm = llm

    def enrich_field(self, product: Product, field_name: str, limit: int = 8) -> GroundedField | None:
        identity = " ".join(
            str(field.value)
            for field in product.fields
            if field.field_name in {"manufacturer", "model", "part_number"} and field.value
        )
        query = f"{product.name} {identity} {product.category or ''} {field_name}"
        hits = self.search.search(query, limit, manufacturer_owned_only=True)
        if not hits:
            return None
        result = self.llm.complete_json(LLMRequest(task="internal_enrich", prompt=self._prompt(query, hits)))
        if result.get("value") in (None, ""):
            return None
        citations = self._citations(result.get("chunk_ids", []), hits)
        if not citations:
            return None
        return GroundedField(
            value=result["value"],
            unit=result.get("unit"),
            confidence=float(result["confidence"]),
            evidence=result.get("evidence"),
            citations=citations,
        )

    def answer(self, query: str, limit: int = 8, product_id: str | None = None) -> CatalogRAGAnswer | None:
        hits = self.search.search(query, limit, product_id=product_id)
        if not hits:
            return None
        result = self.llm.complete_json(LLMRequest(task="rag_answer", prompt=self._prompt(query, hits)))
        citations = self._citations(result.get("chunk_ids", []), hits)
        if not result.get("answer") or not citations:
            return None
        cited_ids = set(result["chunk_ids"])
        return CatalogRAGAnswer(result["answer"], citations, [hit for hit in hits if hit.chunk_id in cited_ids])

    @staticmethod
    def _prompt(query: str, hits: list[SearchHit]) -> str:
        contexts = [
            {
                "chunk_id": hit.chunk_id,
                "product_id": hit.product_id,
                "product_name": hit.product_name,
                "source_identifier": hit.source_identifier,
                "content": hit.content,
                "similarity": hit.score,
            }
            for hit in hits
        ]
        return (
            "Use only the supplied catalog chunks. Cite every factual answer by returning the exact supporting chunk_ids. "
            "If the chunks do not explicitly support the requested value or answer, return null/empty output.\n"
            f"QUERY: {query}\nCONTEXTS_JSON: {json.dumps(contexts)}"
        )

    @staticmethod
    def _citations(chunk_ids: list[str], hits: list[SearchHit]) -> list[GroundedCitation]:
        by_id = {hit.chunk_id: hit for hit in hits}
        citations = []
        for chunk_id in dict.fromkeys(chunk_ids):
            hit = by_id.get(chunk_id)
            if hit is None:
                continue
            citations.append(GroundedCitation(
                url=f"ferrox://source-chunks/{hit.chunk_id}",
                title=f"{hit.product_name} - {hit.source_identifier}",
                cited_text=hit.content[:1000],
            ))
        return citations
