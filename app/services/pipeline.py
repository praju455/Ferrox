from collections import defaultdict
from statistics import mean
from typing import Any

from sqlalchemy.orm import Session
from sqlalchemy import select

from app.core.config import get_settings
from app.models import ExtractedField, FieldStatus, Product, ReviewItem, Source
from app.services.catalog_schemas import schema_for_category
from app.services.llm import LLMClient, LLMRequest


class ProductPipeline:
    STAGES = ("classify", "extract", "reconcile", "validate", "enrich", "score")

    def __init__(self, db: Session, llm: LLMClient | None = None):
        self.db = db
        self.llm = llm or LLMClient(get_settings())

    def run(
        self,
        product: Product,
        source_ids: list[str] | None = None,
        stages: list[str] | None = None,
    ) -> Product:
        sources = [source for source in product.sources if source_ids is None or source.id in source_ids]
        selected = set(stages or self.STAGES)
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
        self.db.commit()
        self.db.refresh(product)
        return product

    def classify(self, product: Product, sources: list[Source]) -> None:
        raw = "\n\n".join(source.raw_content[:4000] for source in sources)
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
            prompt = f"Category: {product.category}\nSource ID: {source.id}\n\n{source.raw_content}"
            result = self.llm.complete_json(LLMRequest(task="extract", prompt=prompt, response_schema=product.dynamic_schema))
            for field_name, payload in result.get("fields", {}).items():
                candidate = {
                    "value": payload.get("value"),
                    "unit": payload.get("unit"),
                    "confidence": float(payload.get("confidence") or 0),
                    "source_id": source.id,
                    "source_identifier": source.source_identifier,
                    "authority_rank": source.authority_rank,
                    "evidence": payload.get("evidence"),
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
                    candidate_key = (candidate["source_id"], candidate["value"], candidate["unit"])
                    existing_keys = {
                        (item.get("source_id"), item.get("value"), item.get("unit"))
                        for item in alternatives
                    }
                    if candidate_key not in existing_keys:
                        alternatives.append(candidate)
                    existing.alternatives = alternatives
        self.db.flush()

    def reconcile(self, product: Product) -> None:
        for field in product.fields:
            alternatives = field.alternatives or []
            distinct = {f"{item.get('value')}|{item.get('unit')}" for item in alternatives if item.get("value") is not None}
            if len(distinct) <= 1:
                continue
            prompt = "VALUES_JSON:" + __import__("json").dumps(alternatives)
            result = self.llm.complete_json(LLMRequest(task="reconcile", prompt=prompt))
            field.value = result.get("value")
            field.unit = result.get("unit")
            field.source_id = result.get("source_id")
            field.confidence = float(result.get("confidence") or field.confidence)
            field.status = FieldStatus.conflict_resolved
            field.validation = {"reconciliation_reason": result.get("reason")}

    def validate(self, product: Product) -> None:
        required = set((product.dynamic_schema or {}).get("required", []))
        by_name = {field.field_name: field for field in product.fields}
        for field in product.fields:
            issues = self._rule_issues(field)
            semantic = self.llm.complete_json(LLMRequest(task="semantic_validate", prompt=f"{product.category} {field.field_name} {field.value} {field.unit}"))
            valid = not issues and semantic.get("valid", False)
            field.validation = {**(field.validation or {}), "rule_issues": issues, "semantic_issues": semantic.get("issues", []), "valid": valid}
            if valid and field.status != FieldStatus.conflict_resolved:
                field.status = FieldStatus.validated
            elif not valid:
                field.status = FieldStatus.needs_review
        for missing in sorted(required - set(by_name)):
            self._ensure_open_review(
                product,
                missing,
                reason="Required field is missing",
                severity="high",
                payload={},
            )

    def enrich(self, product: Product) -> None:
        result = self.llm.complete_json(LLMRequest(task="enrich", prompt=f"{product.category} {product.name}"))
        for name, payload in result.get("enriched_fields", {}).items():
            if not any(field.field_name == name for field in product.fields):
                self.db.add(ExtractedField(
                    product_id=product.id,
                    source_id=None,
                    field_name=name,
                    value=payload.get("value"),
                    unit=payload.get("unit"),
                    confidence=float(payload.get("confidence") or 0.4),
                    status=FieldStatus.enriched,
                    evidence=payload.get("evidence"),
                    alternatives=[],
                    validation={"enrichment_note": payload.get("note")},
                ))

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

    def _ensure_open_review(
        self,
        product: Product,
        field_name: str,
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

    def _rule_issues(self, field: ExtractedField) -> list[str]:
        issues = []
        if field.confidence < 0 or field.confidence > 1:
            issues.append("confidence_out_of_range")
        if any(token in field.field_name for token in ["flow_rate", "head", "power", "diameter", "length", "voltage", "speed"]) and field.value is None:
            issues.append("numeric_field_missing")
        return issues
