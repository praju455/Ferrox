from copy import deepcopy
from typing import Any


BASE_FIELD = {
    "type": "object",
    "required": ["value", "confidence", "source_identifier", "status"],
    "properties": {
        "value": {"type": ["string", "number", "boolean", "null"]},
        "unit": {"type": ["string", "null"]},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "source_identifier": {"type": "string"},
        "status": {"const": "extracted"},
        "evidence": {"type": ["string", "null"]},
    },
}


PREDEFINED_SCHEMAS: dict[str, dict[str, Any]] = {
    "Industrial Pump": {
        "required": ["manufacturer", "model", "flow_rate", "head", "power_rating", "material"],
        "properties": {
            "manufacturer": deepcopy(BASE_FIELD),
            "model": deepcopy(BASE_FIELD),
            "flow_rate": deepcopy(BASE_FIELD),
            "head": deepcopy(BASE_FIELD),
            "power_rating": deepcopy(BASE_FIELD),
            "material": deepcopy(BASE_FIELD),
            "connection_size": deepcopy(BASE_FIELD),
        },
    },
    "Bearing": {
        "required": ["manufacturer", "model", "bore_diameter", "outside_diameter", "load_rating", "material"],
        "properties": {
            "manufacturer": deepcopy(BASE_FIELD),
            "model": deepcopy(BASE_FIELD),
            "bore_diameter": deepcopy(BASE_FIELD),
            "outside_diameter": deepcopy(BASE_FIELD),
            "load_rating": deepcopy(BASE_FIELD),
            "material": deepcopy(BASE_FIELD),
            "seal_type": deepcopy(BASE_FIELD),
        },
    },
    "Electric Motor": {
        "required": ["manufacturer", "model", "power_rating", "voltage", "phase", "speed_rpm", "enclosure"],
        "properties": {
            "manufacturer": deepcopy(BASE_FIELD),
            "model": deepcopy(BASE_FIELD),
            "power_rating": deepcopy(BASE_FIELD),
            "voltage": deepcopy(BASE_FIELD),
            "phase": deepcopy(BASE_FIELD),
            "speed_rpm": deepcopy(BASE_FIELD),
            "enclosure": deepcopy(BASE_FIELD),
        },
    },
    "Fastener": {
        "required": ["manufacturer", "part_number", "diameter", "length", "thread_pitch", "material", "grade"],
        "properties": {
            "manufacturer": deepcopy(BASE_FIELD),
            "part_number": deepcopy(BASE_FIELD),
            "diameter": deepcopy(BASE_FIELD),
            "length": deepcopy(BASE_FIELD),
            "thread_pitch": deepcopy(BASE_FIELD),
            "material": deepcopy(BASE_FIELD),
            "grade": deepcopy(BASE_FIELD),
        },
    },
}


def schema_for_category(category: str) -> dict[str, Any]:
    schema = PREDEFINED_SCHEMAS.get(category) or {
        "required": ["manufacturer", "model", "description"],
        "properties": {
            "manufacturer": deepcopy(BASE_FIELD),
            "model": deepcopy(BASE_FIELD),
            "description": deepcopy(BASE_FIELD),
        },
    }
    return {
        "title": f"{category} extraction schema",
        "type": "object",
        "additionalProperties": False,
        **deepcopy(schema),
    }
