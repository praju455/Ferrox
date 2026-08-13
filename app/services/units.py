import json
import re
from dataclasses import dataclass
from typing import Any

import pint


@dataclass(frozen=True)
class NormalizedMeasurement:
    value: float
    unit: str
    dimension: str


class UnitNormalizer:
    CANONICAL_UNITS = {
        "head": "meter",
        "power_rating": "kilowatt",
        "max_pressure": "bar",
        "bore_diameter": "millimeter",
        "outside_diameter": "millimeter",
        "diameter": "millimeter",
        "length": "millimeter",
        "load_rating": "kilonewton",
        "voltage": "volt",
        "speed_rpm": "revolutions_per_minute",
        "torque": "newton * meter",
    }
    DISPLAY_UNITS = {
        "meter": "m",
        "kilowatt": "kW",
        "bar": "bar",
        "millimeter": "mm",
        "kilonewton": "kN",
        "volt": "V",
        "revolutions_per_minute": "rpm",
        "liter / minute": "L/min",
        "liter / turn": "L/rev",
        "meter * newton": "N*m",
    }
    UNIT_ALIASES = {
        "gpm": "gallon / minute",
        "lpm": "liter / minute",
        "l/min": "liter / minute",
        "m3/h": "meter ** 3 / hour",
        "m³/h": "meter ** 3 / hour",
        "l/rev": "liter / turn",
        "ml/rev": "milliliter / turn",
        "hp": "horsepower",
        "kw": "kilowatt",
        "nm": "newton * meter",
        "n·m": "newton * meter",
        "n m": "newton * meter",
        "rpm": "revolutions_per_minute",
        "in": "inch",
        '"': "inch",
    }

    def __init__(self):
        self.registry = pint.UnitRegistry(autoconvert_offset_to_baseunit=True)

    def normalize(self, field_name: str, value: Any, unit: str | None) -> NormalizedMeasurement | None:
        if isinstance(value, bool) or isinstance(value, (dict, list)) or value is None:
            return None
        magnitude = self._number(value)
        if magnitude is None or not unit:
            return None
        parsed_unit = self._unit(unit)
        try:
            quantity = self.registry.Quantity(magnitude, parsed_unit)
            target = self._target(field_name, parsed_unit)
            normalized = quantity.to(target) if target else quantity
        except (pint.PintError, ValueError, TypeError, AttributeError):
            return None
        target_name = str(normalized.units)
        return NormalizedMeasurement(
            value=round(float(normalized.magnitude), 9),
            unit=self.DISPLAY_UNITS.get(target_name, f"{normalized.units:~}"),
            dimension=str(normalized.dimensionality),
        )

    def comparison_key(self, field_name: str, value: Any, unit: str | None) -> str:
        measurement = self.normalize(field_name, value, unit)
        if measurement:
            return f"measurement:{measurement.value:.9g}:{measurement.dimension}"
        if isinstance(value, str):
            compact = " ".join(value.casefold().split())
            return f"text:{compact}:{(unit or '').casefold()}"
        return "json:" + json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)

    def is_numeric(self, value: Any) -> bool:
        return self._number(value) is not None

    @staticmethod
    def _number(value: Any) -> float | None:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
        if not isinstance(value, str):
            return None
        compact = value.strip().replace(",", ".")
        if re.fullmatch(r"[-+]?\d+(?:\.\d+)?", compact):
            return float(compact)
        return None

    def _target(self, field_name: str, parsed_unit: str) -> str | None:
        if field_name == "flow_rate":
            return "liter / turn" if "turn" in parsed_unit else "liter / minute"
        return self.CANONICAL_UNITS.get(field_name)

    @classmethod
    def _unit(cls, unit: str) -> str:
        compact = " ".join(unit.strip().lower().replace("per", "/").split())
        return cls.UNIT_ALIASES.get(compact, compact)
