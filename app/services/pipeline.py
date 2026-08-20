import json
from collections import defaultdict
from statistics import mean
from typing import Any

from sqlalchemy.orm import Session
from sqlalchemy import select

from app.core.config import get_settings
from app.models import Citation, ExtractedField, FieldStatus, Product, ReviewItem, Source
from app.services.catalog_schemas import schema_for_category
from app.services.chunking import DocumentChunker
from app.services.enrichment import GeminiGroundedEnrichment
from app.services.llm import LLMClient, LLMRequest
from app.services.observability import SQLAlchemyLLMObserver
from app.services.rag import InternalCatalogRAG
from app.services.reference_data import ReferenceDataService
from app.services.reconciliation import WeightedVotingReconciler
from app.services.search import DuplicateDetector, SemanticSearchService, SourceChunkIndexer
from app.services.validation import EngineeringValidator


class ProductPipeline:
    STAGES = ("index", "classify", "extract", "reconcile", "validate", "enrich", "score", "deduplicate")

    def __init__(
        self,
        db: Session,
        llm: LLMClient | None = None,
        enrichment: GeminiGroundedEnrichment | None = None,
    ):
        self.db = db
        settings = get_settings()
        observer = SQLAlchemyLLMObserver(db, settings)
        self.llm = llm or LLMClient(settings, observer=observer)
        self.enrichment = enrichment or GeminiGroundedEnrichment(settings, observer=observer)
        self.chunker = DocumentChunker(settings.document_chunk_chars, settings.document_chunk_overlap_chars)
        self.reconciler = WeightedVotingReconciler()
        self.validator = EngineeringValidator(self.reconciler.normalizer)
        self.indexer = SourceChunkIndexer(db, settings)
        self.search = SemanticSearchService(db, settings, self.indexer.embeddings)
        self.duplicate_detector = DuplicateDetector(self.search, settings.duplicate_similarity_threshold)
        self.internal_rag = InternalCatalogRAG(self.search, self.llm)
        self.references = ReferenceDataService(db, settings.max_reference_rows)
        self.manufacturer_domains = settings.manufacturer_domains

    def run(
        self,
        product: Product,
        source_ids: list[str] | None = None,
        stages: list[str] | None = None,
    ) -> Product:
        if hasattr(self.llm, "set_product_id"):
            self.llm.set_product_id(product.id)
        sources = [source for source in product.sources if source_ids is None or source.id in source_ids]
        selected = set(stages or self.STAGES)
        if "index" in selected and sources:
            self.indexer.index_sources(product, sources)
        if "classify" in selected and sources:
            self.classify(product, sources)
        if "extract" in selected and sources:
            self.extract(product, sources)
        if "reconcile" in selected:
            self.reconcile(product)
        if "validate" in selected:
            self.validate(product)
        if "enrich" in selected:
            self.enrich(product)
        if "score" in selected:
            self.score_and_queue(product)
        if "deduplicate" in selected:
            self.detect_duplicates(product)
        self.db.commit()
        self.db.refresh(product)
        return product

    def classify(self, product: Product, sources: list[Source]) -> None:
        excerpts = []
        for source in sources:
            chunks = self.chunker.split(source.raw_content)
            excerpts.extend(chunk.text[:4000] for chunk in chunks[:2])
        raw = "\n\n".join(excerpts)[:16_000]
        result = self.llm.complete_json(LLMRequest(task="classify", prompt=raw))
        product.category = result["category"]
        product.dynamic_schema = schema_for_category(product.category)

    def extract(self, product: Product, sources: list[Source]) -> None:
        if not product.category or not product.dynamic_schema:
            self.classify(product, sources)
        existing_by_name = {
            field.field_name: field
            for field in self.db.scalars(
                select(ExtractedField).where(ExtractedField.product_id == product.id)
            )
        }
        for source in sources:
            source_chunks = self.chunker.split(source.raw_content)
            for chunk in source_chunks:
                prompt = (
                    f"Category: {product.category}\nSource ID: {source.id}\nChunk: {chunk.identifier} of {len(source_chunks)}\n"
                    "Extract every schema field explicitly supported by this chunk. Preserve table row relationships "
                    "as arrays of objects and preserve lists as arrays. Do not convert pressure into head, do not collapse "
                    "a pressure-to-torque table into separate unrelated values, and do not infer absent specifications.\n\n"
                    f"{chunk.text}"
                )
                result = self.llm.complete_json(LLMRequest(task="extract", prompt=prompt, response_schema=product.dynamic_schema))
                self._store_extraction_candidates(product, source, chunk.identifier, result, existing_by_name)
        self.db.flush()

    def _store_extraction_candidates(
        self,
        product: Product,
        source: Source,
        chunk_identifier: str,
        result: dict[str, Any],
        existing_by_name: dict[str, ExtractedField],
    ) -> None:
        for field_name, payload in result.get("fields", {}).items():
            if payload.get("value") in (None, "", []):
                continue
            candidate = {
                "value": payload.get("value"),
                "unit": payload.get("unit"),
                "confidence": float(payload.get("confidence") or 0),
                "source_id": source.id,
                "source_identifier": source.source_identifier,
                "authority_rank": source.authority_rank,
                "evidence": payload.get("evidence"),
                "chunk_identifier": chunk_identifier,
            }
            existing = existing_by_name.get(field_name)
            if existing is None:
                existing = ExtractedField(
                    product_id=product.id,
                    source_id=source.id,
                    field_name=field_name,
                    value=candidate["value"],
                    unit=candidate["unit"],
                    confidence=candidate["confidence"],
                    status=FieldStatus.extracted,
                    evidence=candidate["evidence"],
                    alternatives=[candidate],
                )
                self.db.add(existing)
                existing_by_name[field_name] = existing
            else:
                alternatives = existing.alternatives or []
                candidate_key = (candidate["source_id"], self._value_key(candidate["value"]), candidate["unit"])
                existing_keys = {
                    (item.get("source_id"), self._value_key(item.get("value")), item.get("unit"))
                    for item in alternatives
                }
                if candidate_key not in existing_keys:
                    alternatives.append(candidate)
                existing.alternatives = alternatives

    def reconcile(self, product: Product) -> None:
        for field in product.fields:
            alternatives = field.alternatives or []
            distinct = {
                self.reconciler.normalizer.comparison_key(field.field_name, item.get("value"), item.get("unit"))
                for item in alternatives if item.get("value") is not None
            }
            if len(distinct) <= 1:
                continue
            decision = self.reconciler.reconcile(field.field_name, alternatives, self._llm_tie_breaker)
            if decision is None:
                continue
            field.value = decision.value
            field.unit = decision.unit
            field.source_id = decision.source_id
            field.confidence = decision.confidence
            field.status = FieldStatus.conflict_resolved
            field.validation = {"reconciliation_reason": decision.reason, "reconciliation": decision.audit}

    def validate(self, product: Product) -> None:
        required = set((product.dynamic_schema or {}).get("required", []))
        by_name = {field.field_name: field for field in product.fields}
        cross_field_issues = self.validator.cross_field_issues(product)
        for field in product.fields:
            engineering = self.validator.validate_field(product.category, field)
            field.value = engineering.value
            field.unit = engineering.unit
            issues = [*engineering.issues, *cross_field_issues.get(field.field_name, [])]
            semantic = self.llm.complete_json(LLMRequest(
                task="semantic_validate",
                prompt=f"Category: {product.category}\nField: {field.field_name}\nValue: {field.value}\nUnit: {field.unit}\nEvidence: {field.evidence}",
            ))
            valid = not issues and semantic.get("valid", False)
            field.validation = {
                **(field.validation or {}),
                "engineering_checks": engineering.checks,
                "rule_issues": sorted(set(issues)),
                "semantic_issues": semantic.get("issues", []),
                "valid": valid,
            }
            if valid and field.status != FieldStatus.conflict_resolved:
                field.status = FieldStatus.validated
            elif not valid:
                field.status = FieldStatus.needs_review
                self._ensure_open_review(
                    product,
                    field.field_name,
                    reason="Engineering or semantic validation failed",
                    severity="high" if issues else "medium",
                    payload={"rule_issues": sorted(set(issues)), "semantic_issues": semantic.get("issues", [])},
                )
        for missing in sorted(required - set(by_name)):
            self._ensure_open_review(
                product,
                missing,
                reason="Required field is missing",
                severity="high",
                payload={},
            )

    def enrich(self, product: Product) -> None:
        required = set((product.dynamic_schema or {}).get("required", []))
        existing = {field.field_name for field in product.fields if field.value not in (None, "")}
        for name in sorted(required - existing):
            result = None
            provider = "internal-rag"
            try:
                result = self.internal_rag.enrich_field(product, name)
            except Exception as exc:
                self._ensure_open_review(
                    product,
                    name,
                    reason="Internal catalog enrichment failed",
                    severity="medium",
                    payload={"error": str(exc)[:500]},
                )
            if result is None and self.enrichment.enabled:
                provider = "gemini"
                try:
                    domains = self._manufacturer_domains(product)
                    result = self.enrichment.enrich_field(
                        product.id,
                        product.name,
                        product.category or "Unknown",
                        name,
                        domains,
                    )
                except Exception as exc:
                    self._ensure_open_review(
                        product,
                        name,
                        reason="Grounded enrichment failed",
                        severity="medium",
                        payload={"error": str(exc)[:500]},
                    )
            if result is None:
                continue
            field = ExtractedField(
                product_id=product.id,
                source_id=None,
                field_name=name,
                value=result.value,
                unit=result.unit,
                confidence=result.confidence,
                status=FieldStatus.enriched,
                evidence=result.evidence,
                alternatives=[],
                validation={"grounded": True, "citation_count": len(result.citations), "grounding_provider": provider},
            )
            self.db.add(field)
            self.db.flush()
            for citation in result.citations:
                self.db.add(
                    Citation(
                        product_id=product.id,
                        extracted_field_id=field.id,
                        url=citation.url,
                        title=citation.title,
                        cited_text=citation.cited_text,
                        provider=provider,
                    )
                )

    def _manufacturer_domains(self, product: Product) -> set[str]:
        manufacturer = next(
            (str(field.value) for field in product.fields if field.field_name == "manufacturer" and field.value),
            None,
        )
        domains = set(self.manufacturer_domains)
        domains.update(self.references.manufacturer_domains(manufacturer))
        domains.update(
            str((source.extracted_metadata or {}).get("hostname", "")).lower()
            for source in product.sources
            if source.manufacturer_owned and (source.extracted_metadata or {}).get("hostname")
        )
        return {domain.removeprefix("www.") for domain in domains if domain}

    def score_and_queue(self, product: Product) -> None:
        required = (product.dynamic_schema or {}).get("required", [])
        present = {field.field_name for field in product.fields if field.value not in (None, "")}
        product.completeness_score = len(present.intersection(required)) / len(required) if required else 0.0
        product.confidence_score = mean([field.confidence for field in product.fields]) if product.fields else 0.0
        for field in product.fields:
            if field.confidence < 0.5 or field.value in (None, ""):
                self._ensure_open_review(
                    product,
                    field.field_name,
                    reason="Low confidence or missing extracted value",
                    severity="medium",
                    payload={"confidence": field.confidence, "value": field.value},
                )

    def detect_duplicates(self, product: Product) -> None:
        for hit in self.duplicate_detector.find(product):
            self._ensure_open_review(
                product,
                None,
                reason="Potential duplicate product",
                severity="high",
                payload={
                    "candidate_product_id": hit.product_id,
                    "candidate_product_name": hit.product_name,
                    "similarity": hit.score,
                    "source_id": hit.source_id,
                },
            )

    def _ensure_open_review(
        self,
        product: Product,
        field_name: str | None,
        reason: str,
        severity: str,
        payload: dict[str, Any],
    ) -> None:
        existing = self.db.scalar(
            select(ReviewItem).where(
                ReviewItem.product_id == product.id,
                ReviewItem.field_name == field_name,
                ReviewItem.reason == reason,
                ReviewItem.status == "open",
            )
        )
        if existing is None:
            self.db.add(
                ReviewItem(
                    product_id=product.id,
                    field_name=field_name,
                    reason=reason,
                    severity=severity,
                    payload=payload,
                )
            )

    def _llm_tie_breaker(self, candidates: list[dict[str, Any]]) -> dict[str, Any]:
        prompt = "VALUES_JSON:" + json.dumps(candidates)
        result = self.llm.complete_json(LLMRequest(task="reconcile", prompt=prompt))
        source_id = result.get("source_id")
        return next((candidate for candidate in candidates if candidate.get("source_id") == source_id), candidates[0])

    @staticmethod
    def _value_key(value: Any) -> str:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
