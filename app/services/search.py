import hashlib
import math
import re
from dataclasses import dataclass
from typing import Any

import requests
from pgvector.sqlalchemy import VECTOR
from sqlalchemy import cast, delete, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import Product, Source, SourceChunk
from app.services.chunking import DocumentChunker


@dataclass(frozen=True)
class SearchHit:
    chunk_id: str
    source_id: str
    product_id: str
    product_name: str
    source_identifier: str
    content: str
    score: float


class EmbeddingProvider:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.model = settings.embedding_model if settings.gemini_api_key else "local-hash-v1"

    def embed(self, text: str, task_type: str = "RETRIEVAL_DOCUMENT", title: str | None = None) -> list[float]:
        if self.settings.gemini_api_key:
            return self._gemini_embed(text, task_type, title)
        return self._local_embed(text)

    def _gemini_embed(self, text: str, task_type: str, title: str | None) -> list[float]:
        payload: dict[str, Any] = {
            "model": f"models/{self.settings.embedding_model}",
            "content": {"parts": [{"text": text}]},
            "taskType": task_type,
            "outputDimensionality": self.settings.embedding_dimensions,
        }
        if title and task_type == "RETRIEVAL_DOCUMENT":
            payload["title"] = title
        response = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.settings.embedding_model}:embedContent",
            headers={"Content-Type": "application/json", "x-goog-api-key": self.settings.gemini_api_key or ""},
            json=payload,
            timeout=self.settings.llm_timeout_seconds,
        )
        response.raise_for_status()
        values = response.json().get("embedding", {}).get("values", [])
        if len(values) != self.settings.embedding_dimensions:
            raise RuntimeError("Gemini returned an unexpected embedding dimension")
        return self._normalize([float(value) for value in values])

    def _local_embed(self, text: str) -> list[float]:
        dimensions = self.settings.embedding_dimensions
        vector = [0.0] * dimensions
        tokens = re.findall(r"[a-z0-9]+", text.casefold())
        features = [*tokens, *(f"{left}_{right}" for left, right in zip(tokens, tokens[1:]))]
        for feature in features:
            digest = hashlib.sha256(feature.encode()).digest()
            index = int.from_bytes(digest[:4], "big") % dimensions
            sign = 1.0 if digest[4] & 1 else -1.0
            vector[index] += sign
        return self._normalize(vector)

    @staticmethod
    def _normalize(vector: list[float]) -> list[float]:
        norm = math.sqrt(sum(value * value for value in vector))
        return [value / norm for value in vector] if norm else vector


class SourceChunkIndexer:
    def __init__(self, db: Session, settings: Settings, embeddings: EmbeddingProvider | None = None):
        self.db = db
        self.settings = settings
        self.embeddings = embeddings or EmbeddingProvider(settings)
        self.chunker = DocumentChunker(settings.embedding_chunk_chars, settings.embedding_chunk_overlap_chars)

    def index_sources(self, product: Product, sources: list[Source]) -> int:
        count = 0
        for source in sources:
            self.db.execute(delete(SourceChunk).where(SourceChunk.source_id == source.id))
            for chunk in self.chunker.split(source.raw_content):
                content_hash = hashlib.sha256(chunk.text.encode()).hexdigest()
                self.db.add(SourceChunk(
                    source_id=source.id,
                    product_id=product.id,
                    chunk_index=chunk.index,
                    content=chunk.text,
                    content_sha256=content_hash,
                    embedding_model=self.embeddings.model,
                    embedding=self.embeddings.embed(chunk.text, "RETRIEVAL_DOCUMENT", product.name),
                    chunk_metadata={"start_char": chunk.start_char, "end_char": chunk.end_char},
                ))
                count += 1
        self.db.flush()
        return count


class SemanticSearchService:
    def __init__(self, db: Session, settings: Settings, embeddings: EmbeddingProvider | None = None):
        self.db = db
        self.settings = settings
        self.embeddings = embeddings or EmbeddingProvider(settings)

    def search(
        self,
        query: str,
        limit: int,
        exclude_product_id: str | None = None,
        product_id: str | None = None,
    ) -> list[SearchHit]:
        query_vector = self.embeddings.embed(query, "RETRIEVAL_QUERY")
        if self.db.bind and self.db.bind.dialect.name == "postgresql":
            return self._postgres_search(query_vector, limit, exclude_product_id, product_id)
        return self._python_search(query_vector, limit, exclude_product_id, product_id)

    def _postgres_search(
        self,
        query_vector: list[float],
        limit: int,
        exclude_product_id: str | None,
        product_id: str | None,
    ) -> list[SearchHit]:
        vector_column = cast(SourceChunk.embedding, VECTOR(self.settings.embedding_dimensions))
        distance = vector_column.cosine_distance(query_vector).label("distance")
        statement = select(SourceChunk, distance).where(SourceChunk.embedding.is_not(None))
        if exclude_product_id:
            statement = statement.where(SourceChunk.product_id != exclude_product_id)
        if product_id:
            statement = statement.where(SourceChunk.product_id == product_id)
        rows = self.db.execute(statement.order_by(distance).limit(limit)).all()
        return [self._hit(chunk, max(0.0, 1.0 - float(distance_value))) for chunk, distance_value in rows]

    def _python_search(
        self,
        query_vector: list[float],
        limit: int,
        exclude_product_id: str | None,
        product_id: str | None,
    ) -> list[SearchHit]:
        statement = select(SourceChunk)
        if exclude_product_id:
            statement = statement.where(SourceChunk.product_id != exclude_product_id)
        if product_id:
            statement = statement.where(SourceChunk.product_id == product_id)
        ranked = []
        for chunk in self.db.scalars(statement):
            vector = chunk.embedding or []
            if len(vector) != len(query_vector):
                continue
            score = sum(float(left) * float(right) for left, right in zip(query_vector, vector))
            ranked.append((score, chunk))
        ranked.sort(key=lambda item: item[0], reverse=True)
        return [self._hit(chunk, max(0.0, min(1.0, score))) for score, chunk in ranked[:limit]]

    @staticmethod
    def _hit(chunk: SourceChunk, score: float) -> SearchHit:
        return SearchHit(
            chunk_id=chunk.id,
            source_id=chunk.source_id,
            product_id=chunk.product_id,
            product_name=chunk.product.name,
            source_identifier=chunk.source.source_identifier,
            content=chunk.content,
            score=round(score, 6),
        )


class DuplicateDetector:
    def __init__(self, search: SemanticSearchService, threshold: float):
        self.search = search
        self.threshold = threshold

    def find(self, product: Product, limit: int = 10) -> list[SearchHit]:
        field_text = " ".join(
            f"{field.field_name} {field.value} {field.unit or ''}"
            for field in product.fields if field.value not in (None, "")
        )
        hits = self.search.search(f"{product.name} {product.category or ''} {field_text}", limit * 4, product.id)
        best_by_product: dict[str, SearchHit] = {}
        for hit in hits:
            current = best_by_product.get(hit.product_id)
            if hit.score >= self.threshold and (current is None or hit.score > current.score):
                best_by_product[hit.product_id] = hit
        return sorted(best_by_product.values(), key=lambda hit: hit.score, reverse=True)[:limit]
