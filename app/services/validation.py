from dataclasses import dataclass, field as dataclass_field
from typing import Any

from app.models import ExtractedField, Product
from app.services.units import UnitNormalizer


@dataclass(frozen=True)
class EngineeringValidationResult:
    value: Any
    unit: str | None
    issues: list[str]
    checks: dict[str, Any] = dataclass_field(default_factory=dict)


class EngineeringValidator:
    RULES = {
        "Industrial Pump": {
            "flow_rate": (0.0, 5_000_000.0),
            "head": (0.0, 5_000.0),
            "power_rating": (0.0, 100_000.0),
            "max_pressure": (0.0, 5_000.0),
        },
        "Bearing": {
            "bore_diameter": (0.0, 10_000.0),
            "outside_diameter": (0.0, 20_000.0),
            "load_rating": (0.0, 1_000_000.0),
        },
        "Electric Motor": {
            "power_rating": (0.0, 200_000.0),
            "voltage": (0.0, 1_000_000.0),
            "speed_rpm": (0.0, 200_000.0),
        },
        "Fastener": {
            "diameter": (0.0, 10_000.0),
            "length": (0.0, 100_000.0),
        },
    }

    def __init__(self, normalizer: UnitNormalizer | None = None):
        self.normalizer = normalizer or UnitNormalizer()

    def validate_field(self, category: str | None, field: ExtractedField) -> EngineeringValidationResult:
        issues: list[str] = []
        checks: dict[str, Any] = {}
        value = field.value
        unit = field.unit
        rules = self.RULES.get(category or "", {})

        if not 0 <= field.confidence <= 1:
            issues.append("confidence_out_of_range")
        if field.field_name == "phase" and value not in (1, 3, "1", "3"):
            issues.append("invalid_motor_phase")
        if field.field_name == "pressure_torque":
            return self._validate_pressure_torque(field, issues, checks)
        if field.field_name in rules:
            if value is None:
                issues.append("numeric_field_missing")
            elif not self.normalizer.is_numeric(value):
                issues.append("numeric_value_invalid")
            elif not unit:
                issues.append("unit_missing")
            else:
                normalized = self.normalizer.normalize(field.field_name, value, unit)
                if normalized is None:
                    issues.append("unit_unrecognized_or_incompatible")
                else:
                    minimum, maximum = rules[field.field_name]
                    checks["original"] = {"value": value, "unit": unit}
                    checks["normalized"] = {"value": normalized.value, "unit": normalized.unit, "dimension": normalized.dimension}
                    value, unit = normalized.value, normalized.unit
                    if value <= minimum:
                        issues.append("value_must_be_positive")
                    if value > maximum:
                        issues.append("value_above_engineering_limit")
        return EngineeringValidationResult(value, unit, issues, checks)

    def cross_field_issues(self, product: Product) -> dict[str, list[str]]:
        fields = {field.field_name: field for field in product.fields}
        issues: dict[str, list[str]] = {}
        if product.category == "Bearing" and {"bore_diameter", "outside_diameter"}.issubset(fields):
            bore = self.normalizer.normalize("bore_diameter", fields["bore_diameter"].value, fields["bore_diameter"].unit)
            outside = self.normalizer.normalize("outside_diameter", fields["outside_diameter"].value, fields["outside_diameter"].unit)
            if bore and outside and outside.value <= bore.value:
                issues.setdefault("outside_diameter", []).append("outside_diameter_must_exceed_bore")
        return issues

    def _validate_pressure_torque(
        self,
        field: ExtractedField,
        issues: list[str],
        checks: dict[str, Any],
    ) -> EngineeringValidationResult:
        if not isinstance(field.value, list) or not field.value:
            return EngineeringValidationResult(field.value, field.unit, [*issues, "pressure_torque_rows_missing"], checks)
        normalized_rows = []
        previous_pressure = -1.0
        for row in field.value:
            if not isinstance(row, dict) or not isinstance(row.get("pressure"), dict) or not isinstance(row.get("torque"), dict):
                issues.append("pressure_torque_row_invalid")
                continue
            pressure = self.normalizer.normalize("max_pressure", row["pressure"].get("value"), row["pressure"].get("unit"))
            torque = self.normalizer.normalize("torque", row["torque"].get("value"), row["torque"].get("unit"))
            if pressure is None or torque is None:
                issues.append("pressure_torque_unit_invalid")
                continue
            if pressure.value <= previous_pressure:
                issues.append("pressure_rows_not_strictly_increasing")
            previous_pressure = pressure.value
            normalized_rows.append({
                "pressure": {"value": pressure.value, "unit": pressure.unit},
                "torque": {"value": torque.value, "unit": torque.unit},
            })
        checks["normalized_rows"] = len(normalized_rows)
        return EngineeringValidationResult(normalized_rows or field.value, None, sorted(set(issues)), checks)
