import abc
import json
import re
from dataclasses import dataclass
from typing import Any

import requests

from app.core.config import Settings
from app.services.catalog_schemas import schema_for_category


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


class BaseHTTPJSONProvider(LLMProvider):
    api_key: str | None

    def __init__(self, name: str, api_key: str | None, model: str, timeout: int, max_retries: int = 2):
        self.name = name
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries

    def complete_json(self, request: LLMRequest) -> dict[str, Any]:
        if not self.api_key:
            raise LLMError(f"{self.name} API key is not configured")
        prompt = self._json_prompt(request)
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                content = self._complete_text(prompt)
                payload = parse_json_object(content)
                validate_llm_payload(request.task, payload, request.response_schema)
                return payload
            except Exception as exc:
                last_error = exc
                prompt = self._retry_prompt(request, exc)
        raise LLMError(f"{self.name} returned invalid JSON: {last_error}")

    @abc.abstractmethod
    def _complete_text(self, prompt: str) -> str:
        raise NotImplementedError

    def _json_prompt(self, request: LLMRequest) -> str:
        schema_text = json.dumps(request.response_schema, indent=2) if request.response_schema else "No formal schema supplied."
        return (
            "Return only valid JSON. Do not include markdown fences, prose, or comments.\n"
            f"Task: {request.task}\n"
            f"Expected response contract:\n{response_contract_for_task(request.task)}\n"
            f"Field schema, when applicable:\n{schema_text}\n\n"
            f"Input:\n{request.prompt}"
        )

    def _retry_prompt(self, request: LLMRequest, error: Exception) -> str:
        return (
            f"The previous response failed JSON validation: {error}.\n"
            "Return corrected valid JSON only.\n\n"
            + self._json_prompt(request)
        )


class GeminiProvider(BaseHTTPJSONProvider):
    def __init__(self, api_key: str | None, model: str, timeout: int):
        super().__init__("gemini", api_key, model, timeout)

    def _complete_text(self, prompt: str) -> str:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        response = requests.post(
            url,
            headers={"Content-Type": "application/json", "x-goog-api-key": self.api_key or ""},
            json={
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
        text = "".join(part.get("text", "") for part in parts)
        if not text:
            raise LLMError("Gemini response did not include text content")
        return text


class OpenAICompatibleProvider(BaseHTTPJSONProvider):
    endpoint: str

    def __init__(self, name: str, endpoint: str, api_key: str | None, model: str, timeout: int):
        super().__init__(name, api_key, model, timeout)
        self.endpoint = endpoint

    def _complete_text(self, prompt: str) -> str:
        response = requests.post(
            self.endpoint,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model,
                "temperature": 0,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": "You are an industrial catalog extraction engine. Return JSON only."},
                    {"role": "user", "content": prompt},
                ],
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content")
        if not content:
            raise LLMError(f"{self.name} response did not include message content")
        return content


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
            "gemini": GeminiProvider(settings.gemini_api_key, settings.gemini_model, settings.llm_timeout_seconds),
            "groq": OpenAICompatibleProvider(
                "groq",
                "https://api.groq.com/openai/v1/chat/completions",
                settings.groq_api_key,
                settings.groq_model,
                settings.llm_timeout_seconds,
            ),
            "openai": OpenAICompatibleProvider(
                "openai",
                "https://api.openai.com/v1/chat/completions",
                settings.openai_api_key,
                settings.openai_model,
                settings.llm_timeout_seconds,
            ),
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


def parse_json_object(content: str) -> dict[str, Any]:
    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*", "", content, flags=re.I)
        content = re.sub(r"\s*```$", "", content)
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", content, flags=re.S)
        if not match:
            raise
        payload = json.loads(match.group(0))
    if not isinstance(payload, dict):
        raise LLMError("LLM response must be a JSON object")
    return payload


def response_contract_for_task(task: str) -> str:
    contracts = {
        "classify": '{"category": "Industrial Pump | Bearing | Electric Motor | Fastener | other", "confidence": 0.0}',
        "extract": '{"fields": {"field_name": {"value": "...", "unit": null, "confidence": 0.0, "source_identifier": "...", "status": "extracted", "evidence": "..."}}}',
        "reconcile": '{"value": "...", "unit": null, "source_id": "...", "confidence": 0.0, "reason": "..."}',
        "semantic_validate": '{"valid": true, "issues": [], "confidence_delta": 0.0}',
        "enrich": '{"enriched_fields": {}, "notes": []}',
    }
    return contracts.get(task, "{}")


def validate_llm_payload(task: str, payload: dict[str, Any], response_schema: dict[str, Any] | None = None) -> None:
    if task == "classify":
        require_keys(payload, ["category", "confidence"])
        validate_confidence(payload["confidence"])
        return
    if task == "extract":
        fields = payload.get("fields")
        if not isinstance(fields, dict):
            raise LLMError("extract response must include fields object")
        expected_fields = set((response_schema or {}).get("properties", {}).keys())
        if expected_fields and not set(fields).issubset(expected_fields):
            unknown = sorted(set(fields) - expected_fields)
            raise LLMError(f"extract response included unknown fields: {unknown}")
        for field_name, field_payload in fields.items():
            if not isinstance(field_payload, dict):
                raise LLMError(f"{field_name} must be an object")
            require_keys(field_payload, ["value", "confidence", "source_identifier", "status"])
            validate_confidence(field_payload["confidence"])
            if field_payload["status"] != "extracted":
                raise LLMError(f"{field_name}.status must be extracted")
        return
    if task == "reconcile":
        require_keys(payload, ["value", "confidence", "reason"])
        validate_confidence(payload["confidence"])
        return
    if task == "semantic_validate":
        require_keys(payload, ["valid", "issues", "confidence_delta"])
        if not isinstance(payload["valid"], bool):
            raise LLMError("semantic_validate.valid must be boolean")
        if not isinstance(payload["issues"], list):
            raise LLMError("semantic_validate.issues must be a list")
        return
    if task == "enrich":
        require_keys(payload, ["enriched_fields"])
        if not isinstance(payload["enriched_fields"], dict):
            raise LLMError("enrich.enriched_fields must be an object")


def require_keys(payload: dict[str, Any], keys: list[str]) -> None:
    missing = [key for key in keys if key not in payload]
    if missing:
        raise LLMError(f"Missing required JSON keys: {missing}")


def validate_confidence(value: Any) -> None:
    if not isinstance(value, int | float) or value < 0 or value > 1:
        raise LLMError("confidence must be a number between 0 and 1")
