import json
import time
from dataclasses import dataclass
from typing import Any

import requests

from app.core.config import Settings
from app.services.llm import parse_json_object, validate_confidence
from app.services.observability import LLMCallEvent, LLMObserver


@dataclass(frozen=True)
class GroundedCitation:
    url: str
    title: str | None
    cited_text: str | None


@dataclass(frozen=True)
class GroundedField:
    value: Any
    unit: str | None
    confidence: float
    evidence: str | None
    citations: list[GroundedCitation]


class GeminiGroundedEnrichment:
    def __init__(self, settings: Settings, observer: LLMObserver | None = None):
        self.settings = settings
        self.observer = observer

    @property
    def enabled(self) -> bool:
        return self.settings.enable_grounded_enrichment and bool(self.settings.gemini_api_key)

    def enrich_field(
        self,
        product_id: str,
        product_name: str,
        category: str,
        field_name: str,
    ) -> GroundedField | None:
        if not self.enabled:
            return None
        prompt = (
            "Search authoritative manufacturer or distributor sources for exactly one industrial product attribute. "
            "Return JSON only with keys value, unit, confidence, evidence. Do not infer a value that the sources do "
            f"not explicitly support. Product: {product_name}. Category: {category}. Attribute: {field_name}."
        )
        started = time.perf_counter()
        try:
            response = requests.post(
                "https://generativelanguage.googleapis.com/v1beta/interactions",
                headers={"Content-Type": "application/json", "x-goog-api-key": self.settings.gemini_api_key or ""},
                json={
                    "model": self.settings.gemini_grounding_model,
                    "input": prompt,
                    "tools": [{"type": "google_search"}],
                },
                timeout=self.settings.llm_timeout_seconds,
            )
            response.raise_for_status()
            data = response.json()
            result = self._parse_response(data)
            self._record(product_id, "success", started, data)
            return result
        except Exception as exc:
            self._record(product_id, "error", started, {}, exc)
            raise

    def _parse_response(self, data: dict[str, Any]) -> GroundedField | None:
        text_blocks: list[dict[str, Any]] = []
        for step in data.get("steps", []):
            if step.get("type") == "model_output":
                text_blocks.extend(block for block in step.get("content", []) if block.get("type") == "text")
        if not text_blocks:
            return None
        combined_text = "\n".join(block.get("text", "") for block in text_blocks)
        payload = parse_json_object(combined_text)
        if "value" not in payload or "confidence" not in payload:
            return None
        validate_confidence(payload["confidence"])
        citations: list[GroundedCitation] = []
        seen_urls: set[str] = set()
        for block in text_blocks:
            block_text = block.get("text", "")
            for annotation in block.get("annotations", []):
                if annotation.get("type") != "url_citation" or not annotation.get("url"):
                    continue
                url = annotation["url"]
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                start = max(0, int(annotation.get("start_index", 0)))
                end = min(len(block_text), int(annotation.get("end_index", len(block_text))))
                citations.append(GroundedCitation(url, annotation.get("title"), block_text[start:end] or None))
        if not citations:
            return None
        return GroundedField(
            value=payload["value"],
            unit=payload.get("unit"),
            confidence=float(payload["confidence"]),
            evidence=payload.get("evidence"),
            citations=citations,
        )

    def _record(
        self,
        product_id: str,
        status: str,
        started: float,
        data: dict[str, Any],
        error: Exception | None = None,
    ) -> None:
        if self.observer is None:
            return
        usage = data.get("usage", {}) or data.get("usage_metadata", {})
        self.observer.record(
            LLMCallEvent(
                provider="gemini",
                model=self.settings.gemini_grounding_model,
                task="grounded_enrich",
                status=status,
                latency_ms=round((time.perf_counter() - started) * 1000),
                input_tokens=int(usage.get("input_tokens", usage.get("prompt_token_count", 0)) or 0),
                output_tokens=int(usage.get("output_tokens", usage.get("candidates_token_count", 0)) or 0),
                error=str(error) if error else None,
                product_id=product_id,
            )
        )
