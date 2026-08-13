from copy import deepcopy
from typing import Any


BASE_FIELD = {
    "type": "object",
    "additionalProperties": False,
    "required": ["value", "confidence", "source_identifier", "status"],
    "properties": {
        "value": {"type": ["string", "number", "boolean", "array", "object", "null"]},
        "unit": {"type": ["string", "null"]},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "source_identifier": {"type": "string"},
        "status": {"const": "extracted"},
        "evidence": {"type": ["string", "null"]},
    },
}


def field_schema(description: str) -> dict[str, Any]:
    field = deepcopy(BASE_FIELD)
    field["description"] = description
    field["properties"]["value"]["description"] = description
    return field


def typed_field_schema(description: str, value_schema: dict[str, Any]) -> dict[str, Any]:
    field = field_schema(description)
    field["properties"]["value"] = {**deepcopy(value_schema), "description": description}
    return field


STRING_LIST_VALUE = {"type": ["array", "null"], "items": {"type": "string"}}

PRESSURE_TORQUE_VALUE = {
    "type": ["array", "null"],
    "items": {
        "type": "object",
        "required": ["pressure", "torque"],
        "additionalProperties": False,
        "properties": {
            "pressure": {
                "type": "object",
                "required": ["value", "unit"],
                "additionalProperties": False,
                "properties": {"value": {"type": ["string", "number"]}, "unit": {"type": "string"}},
            },
            "torque": {
                "type": "object",
                "required": ["value", "unit"],
                "additionalProperties": False,
                "properties": {"value": {"type": ["string", "number"]}, "unit": {"type": "string"}},
            },
        },
    },
}

CONSTRUCTION_VALUE = {
    "type": ["array", "null"],
    "items": {
        "type": "object",
        "required": ["component", "material", "surface_treatment"],
        "additionalProperties": False,
        "properties": {
            "component": {"type": "string"},
            "material": {"type": ["string", "array", "null"], "items": {"type": "string"}},
            "surface_treatment": {"type": ["string", "array", "null"], "items": {"type": "string"}},
        },
    },
}

DIMENSIONAL_VALUE = {
    "type": ["object", "null"],
    "additionalProperties": {"type": ["string", "number", "null"]},
}


PREDEFINED_SCHEMAS: dict[str, dict[str, Any]] = {
    "Industrial Pump": {
        "required": ["manufacturer", "model", "product_type", "flow_rate"],
        "properties": {
            "manufacturer": field_schema("Manufacturer or brand exactly as printed in the document header or specifications."),
            "model": field_schema("Manufacturer model, series, or catalog designation."),
            "product_type": field_schema("Specific pump technology or subtype, such as peristaltic or end-suction centrifugal pump."),
            "description": field_schema("Explicit product description from the source; do not generate marketing copy."),
            "flow_rate": field_schema("Capacity, displacement, or flow value. Preserve units such as GPM, L/min, or L/rev."),
            "head": field_schema("Explicit head rating only. Leave null when the source provides pressure instead of head."),
            "power_rating": field_schema("Explicit motor or drive power rating only."),
            "material": field_schema("General wetted-part, casing, or primary construction material when stated generically."),
            "connection_size": field_schema("Single connection size and standard, retained for backward compatibility."),
            "connections": field_schema("One connection or a list of connections, preserving size and standard such as 3/8 in BSP."),
            "max_pressure": field_schema("Maximum working or discharge pressure, not a pressure row from an operating table."),
            "rotor_system": field_schema("Rotor or compression system, such as rollers or shoes."),
            "available_hoses": typed_field_schema("List of explicitly available hose materials or variants.", STRING_LIST_VALUE),
            "available_tubes": typed_field_schema("List of explicitly available tube materials or variants.", STRING_LIST_VALUE),
            "pressure_torque": typed_field_schema("Array of row objects preserving pressure-to-torque relationships from a table.", PRESSURE_TORQUE_VALUE),
            "pump_housing_material": field_schema("Pump housing material and grade."),
            "front_cover_material": field_schema("Front cover material and grade."),
            "rotor_material": field_schema("Rotor material and grade."),
            "rollers_material": field_schema("Roller material and grade."),
            "base_plate_material": field_schema("Base plate material and grade."),
            "connection_materials": typed_field_schema("List of connection materials and optional variants from the construction table.", STRING_LIST_VALUE),
            "construction_details": typed_field_schema("Construction-table rows preserving component, material, and surface-treatment relationships.", CONSTRUCTION_VALUE),
            "dimensional_data": typed_field_schema("Dimension labels and values exactly as printed; do not assume a unit absent from the source.", DIMENSIONAL_VALUE),
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
