import abc
import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Any

import requests

from app.core.config import Settings
from app.services.catalog_schemas import schema_for_category
from app.services.observability import LLMCallEvent, LLMObserver


logger = logging.getLogger("ferrox.llm")


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
        self.last_usage = {"input_tokens": 0, "output_tokens": 0}

    def complete_json(self, request: LLMRequest) -> dict[str, Any]:
        if not self.api_key:
            raise LLMError(f"{self.name} API key is not configured")
        prompt = self._json_prompt(request)
        self.last_usage = {"input_tokens": 0, "output_tokens": 0}
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
        usage = data.get("usageMetadata", {})
        self.last_usage = {
            "input_tokens": int(usage.get("promptTokenCount", 0) or 0),
            "output_tokens": int(usage.get("candidatesTokenCount", 0) or 0),
        }
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
        usage = data.get("usage", {})
        self.last_usage = {
            "input_tokens": int(usage.get("prompt_tokens", 0) or 0),
            "output_tokens": int(usage.get("completion_tokens", 0) or 0),
        }
        content = data.get("choices", [{}])[0].get("message", {}).get("content")
        if not content:
            raise LLMError(f"{self.name} response did not include message content")
        return content


class MockIndustrialProvider(LLMProvider):
    name = "mock"
    model = "deterministic-local"
    last_usage = {"input_tokens": 0, "output_tokens": 0}

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
        if request.task == "internal_enrich":
            return {"value": None, "unit": None, "confidence": 0.0, "evidence": None, "chunk_ids": []}
        if request.task == "rag_answer":
            return {"answer": None, "chunk_ids": []}
        raise LLMError(f"Unsupported task: {request.task}")

    def _extract_field(self, field: str, text: str) -> dict[str, Any]:
        patterns = {
            "manufacturer": r"(?:manufacturer|make|brand)[:\s]+([A-Za-z0-9 &'()\-]+)",
            "model": r"(?:model|part)[:\s]+([A-Za-z0-9_.-]+)",
            "part_number": r"(?:part number|part|pn)[:\s]+([A-Za-z0-9_.-]+)",
            "product_type": r"(?:product\s*type[:\s]+)?((?:industrial\s+)?(?:peristaltic|centrifugal|diaphragm|gear|screw)\s+pump)",
            "description": r"description\s*:\s*([^\n]+)",
            "flow_rate": r"(?:capacity|flow(?:\s+rate)?)?[:\s]*([0-9]+(?:[.,][0-9]+)?)\s*(gpm|lpm|l/min|m3/h|l/rev|ml/rev)",
            "head": r"([0-9]+(?:\.[0-9]+)?)\s*(ft|m)\s*(?:head)?",
            "power_rating": r"([0-9]+(?:\.[0-9]+)?)\s*(hp|kw)",
            "material": r"(cast iron|stainless steel|carbon steel|chrome steel|brass|zinc plated steel)",
            "connection_size": r"(?:connection(?:\s+size)?s?[:\s]+)?([0-9]+(?:\.[0-9]+)?|[0-9]+/[0-9]+)\s*(in|inch|[\"”“]|npt|bsp)(?:\s*(bsp|npt))?",
            "connections": r"connections?[:\s]+([^\n.;]+)",
            "max_pressure": r"(?:max\.?|maximum)(?:\s+working)?\s+pressure[:\s]+([0-9]+(?:\.[0-9]+)?)\s*(bar|psi|kpa|mpa)",
            "rotor_system": r"rotor\s+system[:\s]+([^\n,;]+)",
            "pump_housing_material": r"pump\s+housing[:\s]+([^\n,;]+)",
            "front_cover_material": r"front\s+cover[:\s]+([^\n,;]+)",
            "rotor_material": r"(?:rotor\s+material|rotor(?!\s+system))[:\s|]+([^\n|,;]+)",
            "rollers_material": r"rollers?[:\s]+([^\n,;]+)",
            "base_plate_material": r"base\s+plate[:\s]+([^\n,;]+)",
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
        if field in {"available_hoses", "available_tubes"}:
            label = "hoses?" if field == "available_hoses" else "tubes?"
            stop = r"available\s+tubes?" if field == "available_hoses" else r"pressure\s*\("
            list_match = re.search(rf"(?:available\s+)?{label}[:\s]+(.+?)(?=\n\s*(?:{stop})|\n---|$)", text, re.I | re.S)
            if list_match:
                evidence = list_match.group(0).strip()
                values = [item.strip().rstrip(".") for item in re.split(r"\s*,\s*|\s*\n\s*", list_match.group(1)) if item.strip()]
                return self._field_payload(values, None, 0.82, evidence)
        if field == "pressure_torque":
            rows = []
            header_table = re.search(r"Pressure\s*\((bar|psi)\)\s*\|\s*Torque\s*\((N\s*m|Nm|N·m)\)\)?\s*\n((?:\s*[0-9.]+\s*\|\s*[0-9.]+\s*\n?)+)", text, re.I)
            explicit_rows = list(re.finditer(r"([0-9]+(?:\.[0-9]+)?)\s*(bar|psi)\s*(?:\||->|→|:|\s{2,})\s*([0-9]+(?:\.[0-9]+)?)\s*(n\s*m|nm|n·m)", text, re.I))
            for row in explicit_rows:
                rows.append({
                    "pressure": {"value": row.group(1), "unit": row.group(2)},
                    "torque": {"value": row.group(3), "unit": row.group(4)},
                })
            if header_table:
                for row in re.finditer(r"([0-9]+(?:\.[0-9]+)?)\s*\|\s*([0-9]+(?:\.[0-9]+)?)", header_table.group(3)):
                    rows.append({
                        "pressure": {"value": row.group(1), "unit": header_table.group(1)},
                        "torque": {"value": row.group(2), "unit": header_table.group(2)},
                    })
            if rows:
                evidence = header_table.group(0).strip() if header_table else "; ".join(row.group(0) for row in explicit_rows)
                return self._field_payload(rows, None, 0.84, evidence)
        if field == "connection_materials":
            row = re.search(r"Connections\s*\|\s*(.+?)\s*\|", text, re.I | re.S)
            if row:
                values = [item.strip() for item in re.split(r"\s*;\s*|\n", row.group(1)) if item.strip()]
                return self._field_payload(values, None, 0.8, row.group(0).strip())
        if field == "construction_details":
            rows = self._construction_rows(text)
            if rows:
                return self._field_payload(rows, None, 0.82, "Construction table")
        if field == "dimensional_data":
            dimensions = self._dimension_row(text)
            if dimensions:
                return self._field_payload(dimensions, None, 0.8, "Dimensional table")
        if field == "material" and self._construction_rows(text):
            return self._field_payload(None, None, 0.15, None)
        component_fields = {
            "pump_housing_material": "Pump housing",
            "front_cover_material": "Front cover",
            "rotor_material": "Rotor",
            "rollers_material": "Rollers",
            "base_plate_material": "Base plate",
        }
        if field in component_fields:
            for row in self._construction_rows(text):
                if row["component"].lower() == component_fields[field].lower() and row["material"]:
                    return self._field_payload(row["material"], None, 0.82, str(row))
        if field in {"connections", "connection_size"}:
            connection = re.search(r"([0-9]+/[0-9]+)\s*[\"”“]?\s*(BSP|NPT)\b", text, re.I)
            if connection:
                value = connection.group(1)
                unit = connection.group(2).upper()
                return self._field_payload(value, unit, 0.84, connection.group(0).strip())
        match = re.search(patterns.get(field, rf"{field}[:\s]+([^\n,;]+)"), text, re.I)
        if field == "manufacturer" and not match:
            match = re.search(r"\b(Bombas\s+Boyser)(?:,\s*S\.L\.)?", text, re.I)
        if field == "model" and not match:
            match = re.search(r"^\s*([A-Z]{2,}[A-Z0-9]*-[A-Z0-9-]+)\s*$", text, re.M)
        value = None
        unit = None
        evidence = None
        confidence = 0.15
        if match:
            value = match.group(1).strip().replace(",", ".") if field == "flow_rate" else match.group(1).strip()
            if len(match.groups()) > 1:
                unit = match.group(2).strip()
            if field == "connection_size" and len(match.groups()) > 2 and match.group(3):
                unit = f"{unit} {match.group(3).strip()}"
            evidence = match.group(0).strip()
            confidence = 0.78
        return self._field_payload(value, unit, confidence, evidence)

    @staticmethod
    def _construction_rows(text: str) -> list[dict[str, Any]]:
        table = re.search(r"--- Page \d+ Table \d+ ---\nDescription\s*\|\s*Material\s*\|\s*Surface treatment\n(.+?)(?=\n---|\Z)", text, re.I | re.S)
        if not table:
            return []
        rows = []
        for line in table.group(1).splitlines():
            cells = [cell.strip() or None for cell in line.split("|")]
            if len(cells) < 3 or not cells[0]:
                continue
            if cells[1] is None and cells[0].lower().startswith("front cover "):
                cells = ["Front cover", cells[0][len("Front cover "):].removesuffix(" --").strip(), None]
            elif cells[1] is None and cells[0].lower().startswith("rollers "):
                match = re.match(r"Rollers\s+(.+?)\s+(Blueing)$", cells[0], re.I)
                if match:
                    cells = ["Rollers", match.group(1), match.group(2)]
            material = [item.strip() for item in cells[1].split(";")] if cells[1] and ";" in cells[1] else cells[1]
            treatment = [item.strip() for item in cells[2].split(";")] if cells[2] and ";" in cells[2] else cells[2]
            rows.append({"component": cells[0], "material": material, "surface_treatment": treatment})
        return rows

    @staticmethod
    def _dimension_row(text: str) -> dict[str, Any]:
        match = re.search(
            r"A\s*\|\s*B\s*\|\s*C\s*\|\s*D\s*\|\s*E\s*\|\s*F\s*\|\s*G\s*\|\s*H\s*\|\s*J\s*\|\s*K\s*\|\s*L\s*\|\s*M\s*\|\s*Connections\s*\n([^\n]+)",
            text,
            re.I,
        )
        if not match:
            return {}
        labels = ["A", "B", "C", "D", "E", "F", "G", "H", "J", "K", "L", "M", "connections"]
        values = [value.strip() for value in match.group(1).split("|")]
        if len(values) == len(labels) and not any(values[1:]):
            tokens = values[0].split()
            if len(tokens) >= len(labels):
                values = tokens[: len(labels) - 1] + [" ".join(tokens[len(labels) - 1 :])]
        return dict(zip(labels, values, strict=False)) if len(values) == len(labels) else {}

    @staticmethod
    def _field_payload(value: Any, unit: str | None, confidence: float, evidence: str | None) -> dict[str, Any]:
        return {
            "value": value,
            "unit": unit,
            "confidence": confidence,
            "source_identifier": "mock-source",
            "status": "extracted",
            "evidence": evidence,
        }


class LLMClient:
    def __init__(self, settings: Settings, observer: LLMObserver | None = None):
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
        self.observer = observer
        self.product_id: str | None = None

    def set_product_id(self, product_id: str | None) -> None:
        self.product_id = product_id

    def complete_json(self, request: LLMRequest) -> dict[str, Any]:
        last_error: Exception | None = None
        for provider in self.providers:
            started = time.perf_counter()
            try:
                result = provider.complete_json(request)
                validate_llm_payload(request.task, result, request.response_schema)
                self._record(provider, request.task, "success", started)
                return result
            except Exception as exc:
                last_error = exc
                self._record(provider, request.task, "error", started, exc)
        raise LLMError(str(last_error) if last_error else "No LLM providers configured")

    def _record(
        self,
        provider: LLMProvider,
        task: str,
        status: str,
        started: float,
        error: Exception | None = None,
    ) -> None:
        if self.observer is None:
            return
        usage = getattr(provider, "last_usage", {})
        try:
            self.observer.record(
                LLMCallEvent(
                    provider=provider.name,
                    model=getattr(provider, "model", "unknown"),
                    task=task,
                    status=status,
                    latency_ms=round((time.perf_counter() - started) * 1000),
                    input_tokens=int(usage.get("input_tokens", 0) or 0),
                    output_tokens=int(usage.get("output_tokens", 0) or 0),
                    error=str(error) if error else None,
                    product_id=self.product_id,
                )
            )
        except Exception:
            logger.exception("Failed to record LLM telemetry")


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
        "internal_enrich": '{"value": null, "unit": null, "confidence": 0.0, "evidence": null, "chunk_ids": ["chunk-id"]}',
        "rag_answer": '{"answer": null, "chunk_ids": ["chunk-id"]}',
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
            field_schema = (response_schema or {}).get("properties", {}).get(field_name, {})
            validate_schema_value(field_payload, field_schema, field_name)
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
        return
    if task == "internal_enrich":
        require_keys(payload, ["value", "confidence", "chunk_ids"])
        validate_confidence(payload["confidence"])
        if not isinstance(payload["chunk_ids"], list) or not all(isinstance(item, str) for item in payload["chunk_ids"]):
            raise LLMError("internal_enrich.chunk_ids must be a list of strings")
        return
    if task == "rag_answer":
        require_keys(payload, ["answer", "chunk_ids"])
        if payload["answer"] is not None and not isinstance(payload["answer"], str):
            raise LLMError("rag_answer.answer must be a string or null")
        if not isinstance(payload["chunk_ids"], list) or not all(isinstance(item, str) for item in payload["chunk_ids"]):
            raise LLMError("rag_answer.chunk_ids must be a list of strings")


def require_keys(payload: dict[str, Any], keys: list[str]) -> None:
    missing = [key for key in keys if key not in payload]
    if missing:
        raise LLMError(f"Missing required JSON keys: {missing}")


def validate_confidence(value: Any) -> None:
    if not isinstance(value, int | float) or value < 0 or value > 1:
        raise LLMError("confidence must be a number between 0 and 1")


def validate_schema_value(value: Any, schema: dict[str, Any], path: str) -> None:
    if not schema:
        return
    allowed = schema.get("type")
    allowed_types = allowed if isinstance(allowed, list) else [allowed]
    type_checks = {
        "null": lambda item: item is None,
        "string": lambda item: isinstance(item, str),
        "number": lambda item: isinstance(item, int | float) and not isinstance(item, bool),
        "boolean": lambda item: isinstance(item, bool),
        "array": lambda item: isinstance(item, list),
        "object": lambda item: isinstance(item, dict),
    }
    if allowed_types and not any(type_checks.get(kind, lambda _: True)(value) for kind in allowed_types):
        raise LLMError(f"{path} does not match allowed type(s): {allowed_types}")
    if "const" in schema and value != schema["const"]:
        raise LLMError(f"{path} must equal {schema['const']!r}")
    if isinstance(value, list) and schema.get("items"):
        for index, item in enumerate(value):
            validate_schema_value(item, schema["items"], f"{path}[{index}]")
    if isinstance(value, dict):
        missing = [name for name in schema.get("required", []) if name not in value]
        if missing:
            raise LLMError(f"{path} is missing required keys: {missing}")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            unknown = sorted(set(value) - set(properties))
            if unknown:
                raise LLMError(f"{path} includes unknown keys: {unknown}")
        for name, item in value.items():
            child_schema = properties.get(name)
            if child_schema is None and isinstance(schema.get("additionalProperties"), dict):
                child_schema = schema["additionalProperties"]
            if child_schema:
                validate_schema_value(item, child_schema, f"{path}.{name}")
