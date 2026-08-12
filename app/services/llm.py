import abc
import json
import re
from dataclasses import dataclass
from typing import Any

import requests

from app.core.config import Settings
from app.services.catalog_schemas import PREDEFINED_SCHEMAS, schema_for_category


class LLMError(RuntimeError):
    pass


@dataclass(frozen=True)
class LLMRequest:
    task: str
    prompt: str
    response_schema: dict[str, Any] | None = None


class LLMProvider(abc.ABC):
    name: str

    @abc.abstractmethod
    def complete_json(self, request: LLMRequest) -> dict[str, Any]:
        raise NotImplementedError


class HTTPJSONProvider(LLMProvider):
    endpoint: str
    api_key: str | None

    def __init__(self, name: str, api_key: str | None, timeout: int):
        self.name = name
        self.api_key = api_key
        self.timeout = timeout

    def complete_json(self, request: LLMRequest) -> dict[str, Any]:
        if not self.api_key:
            raise LLMError(f"{self.name} API key is not configured")
        raise LLMError(f"{self.name} live integration is configured but not implemented in test mode")


class MockIndustrialProvider(LLMProvider):
    name = "mock"

    def complete_json(self, request: LLMRequest) -> dict[str, Any]:
        text = request.prompt.lower()
        if request.task == "classify":
            if "bearing" in text:
                return {"category": "Bearing", "confidence": 0.91}
            if "motor" in text or "rpm" in text or "voltage" in text:
                return {"category": "Electric Motor", "confidence": 0.9}
            if "bolt" in text or "screw" in text or "thread" in text:
                return {"category": "Fastener", "confidence": 0.86}
            return {"category": "Industrial Pump", "confidence": 0.88}
        if request.task == "extract":
            category_match = re.search(r"category:\s*(.+)", request.prompt, re.I)
            category = category_match.group(1).splitlines()[0].strip() if category_match else "Industrial Pump"
            schema = schema_for_category(category)
            return {"fields": {field: self._extract_field(field, request.prompt) for field in schema["properties"]}}
        if request.task == "reconcile":
            values = json.loads(request.prompt.split("VALUES_JSON:", 1)[1])
            ranked = sorted(values, key=lambda item: (item.get("authority_rank", 9), -item.get("confidence", 0)))
            winner = ranked[0]
            return {
                "value": winner["value"],
                "unit": winner.get("unit"),
                "source_id": winner.get("source_id"),
                "confidence": min(1.0, winner.get("confidence", 0.5) + 0.05),
                "reason": "Selected highest-authority source, then confidence.",
            }
        if request.task == "semantic_validate":
            return {"valid": True, "issues": [], "confidence_delta": 0.0}
        if request.task == "enrich":
            return {"enriched_fields": {}, "notes": ["No external enrichment performed in mock mode."]}
        raise LLMError(f"Unsupported task: {request.task}")

    def _extract_field(self, field: str, text: str) -> dict[str, Any]:
        patterns = {
            "manufacturer": r"(?:manufacturer|make|brand)[:\s]+([A-Za-z0-9 -]+)",
            "model": r"(?:model|part)[:\s]+([A-Za-z0-9_.-]+)",
            "part_number": r"(?:part number|part|pn)[:\s]+([A-Za-z0-9_.-]+)",
            "flow_rate": r"([0-9]+(?:\.[0-9]+)?)\s*(gpm|lpm|m3/h)",
            "head": r"([0-9]+(?:\.[0-9]+)?)\s*(ft|m)\s*(?:head)?",
            "power_rating": r"([0-9]+(?:\.[0-9]+)?)\s*(hp|kw)",
            "material": r"(cast iron|stainless steel|carbon steel|chrome steel|brass|zinc plated steel)",
            "connection_size": r"([0-9]+(?:\.[0-9]+)?)\s*(in|inch|npt)",
            "bore_diameter": r"bore[:\s]+([0-9]+(?:\.[0-9]+)?)\s*(mm|in)",
            "outside_diameter": r"(?:outside diameter|od)[:\s]+([0-9]+(?:\.[0-9]+)?)\s*(mm|in)",
            "load_rating": r"load[:\s]+([0-9]+(?:\.[0-9]+)?)\s*(kn|lb)",
            "voltage": r"([0-9]+)\s*v",
            "phase": r"([13])\s*phase",
            "speed_rpm": r"([0-9]+)\s*rpm",
            "enclosure": r"(tefc|odp|ip55|ip56|nema\s*[0-9]+)",
            "diameter": r"diameter[:\s]+([0-9/.-]+)\s*(in|mm)",
            "length": r"length[:\s]+([0-9/.-]+)\s*(in|mm)",
            "thread_pitch": r"(?:thread pitch|thread)[:\s]+([A-Za-z0-9./ -]+)",
            "grade": r"(grade\s*[0-9.]+|class\s*[0-9.]+)",
        }
        match = re.search(patterns.get(field, rf"{field}[:\s]+([^\n,;]+)"), text, re.I)
        value = None
        unit = None
        evidence = None
        confidence = 0.15
        if match:
            value = match.group(1).strip()
            if len(match.groups()) > 1:
                unit = match.group(2).strip()
            evidence = match.group(0).strip()
            confidence = 0.78
        return {
            "value": value,
            "unit": unit,
            "confidence": confidence,
            "source_identifier": "mock-source",
            "status": "extracted",
            "evidence": evidence,
        }


class LLMClient:
    def __init__(self, settings: Settings):
        providers = {
            "gemini": HTTPJSONProvider("gemini", settings.gemini_api_key, settings.llm_timeout_seconds),
            "groq": HTTPJSONProvider("groq", settings.groq_api_key, settings.llm_timeout_seconds),
            "openai": HTTPJSONProvider("openai", settings.openai_api_key, settings.llm_timeout_seconds),
            "mock": MockIndustrialProvider(),
        }
        self.providers = [providers[name] for name in settings.provider_order if name in providers]
        self.providers.append(providers["mock"])

    def complete_json(self, request: LLMRequest) -> dict[str, Any]:
        last_error: Exception | None = None
        for provider in self.providers:
            try:
                return provider.complete_json(request)
            except Exception as exc:
                last_error = exc
        raise LLMError(str(last_error) if last_error else "No LLM providers configured")
