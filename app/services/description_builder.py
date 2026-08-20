import re
from dataclasses import dataclass
from fractions import Fraction
from typing import Any, Callable


EMPTY_VALUES = {"", "-", "--", "n/a", "na", "none", "null", "unbranded", "-- unbranded --"}
IDENTITY_FIELDS = {"manufacturer", "brand", "model", "part_number", "manufacturer_part_number", "product_type", "item_type", "series"}
CATEGORY_ATTRIBUTE_ORDER = {
    "industrial pump": ("flow_rate", "max_pressure", "connections", "power_rating", "material"),
    "pump": ("flow_rate", "max_pressure", "connections", "power_rating", "material"),
    "faucet": ("faucet_type", "mounting_type", "number_of_handles", "flow_rate", "finish", "material"),
    "fitting": ("fitting_type", "connection_type", "nominal_size", "schedule", "material", "finish"),
    "bearing": ("bore_diameter", "outside_diameter", "width", "load_rating", "material"),
    "electric motor": ("power_rating", "voltage", "phase", "speed_rpm", "enclosure"),
    "fastener": ("diameter", "length", "thread_pitch", "material", "grade", "finish"),
}


@dataclass(frozen=True)
class DescriptionSet:
    invoice_description: str
    mobile_description: str
    product_title: str
    short_description: str
    long_description: str

    def as_dict(self) -> dict[str, str]:
        return {
            "invoice_description": self.invoice_description,
            "mobile_description": self.mobile_description,
            "product_title": self.product_title,
            "short_description": self.short_description,
            "long_description": self.long_description,
        }


class DeterministicDescriptionBuilder:
    def __init__(
        self,
        fraction_lookup: Callable[[float], str | None] | None = None,
        uom_lookup: Callable[[Any], str | None] | None = None,
    ):
        self.fraction_lookup = fraction_lookup
        self.uom_lookup = uom_lookup

    def build(self, category: str | None, values: dict[str, Any]) -> DescriptionSet:
        cleaned = {key: value for key, value in values.items() if self._present(value)}
        brand = self._text(cleaned.get("brand") or cleaned.get("manufacturer"))
        manufacturer = self._text(cleaned.get("manufacturer"))
        series = self._text(cleaned.get("series"))
        part = self._text(
            cleaned.get("manufacturer_part_number") or cleaned.get("part_number") or cleaned.get("model")
        )
        item_type = self._text(cleaned.get("item_type") or cleaned.get("product_type") or category or "Product")
        attributes = self._ordered_attributes(category, cleaned)

        title_tokens = self._dedupe([brand, series, part, item_type, *[value for _, value in attributes[:5]]])
        title = self._join(title_tokens)
        invoice_tokens = self._dedupe([item_type, series, part, *[value for _, value in attributes[:5]]])
        invoice = self._truncate(self._join(invoice_tokens).upper(), 40)
        mobile_tokens = self._dedupe([manufacturer, brand, item_type, series, part, *[value for _, value in attributes[:2]]])
        mobile = self._truncate(self._join(mobile_tokens), 80)
        long_tokens = self._dedupe([brand, item_type, series, part, *[value for _, value in attributes]])
        long_description = self._join(long_tokens, separator=", ")
        return DescriptionSet(
            invoice_description=invoice,
            mobile_description=mobile,
            product_title=title,
            short_description=title,
            long_description=long_description,
        )

    def format_measurement(self, value: Any, unit: str | None = None) -> str:
        rendered = self._fractional(value) if unit and unit.lower() in {"in", "inch", "inches", '"'} else self._text(value)
        canonical_unit = self.uom_lookup(unit) if unit and self.uom_lookup else unit
        return self._join([rendered, self._text(canonical_unit)])

    def _ordered_attributes(self, category: str | None, values: dict[str, Any]) -> list[tuple[str, str]]:
        order = CATEGORY_ATTRIBUTE_ORDER.get((category or "").lower(), ())
        remaining = sorted(
            key for key in values if key not in IDENTITY_FIELDS and key not in order and not key.endswith("_record_id")
        )
        attributes: list[tuple[str, str]] = []
        for key in (*order, *remaining):
            if key not in values:
                continue
            value = values[key]
            if isinstance(value, dict) and "value" in value:
                rendered = self.format_measurement(value.get("value"), value.get("unit"))
            elif isinstance(value, (list, dict)):
                continue
            else:
                rendered = self._text(value)
            if rendered:
                attributes.append((key, rendered))
        return attributes

    def _fractional(self, value: Any) -> str:
        try:
            decimal = float(value)
        except (TypeError, ValueError):
            return self._text(value)
        whole = int(decimal)
        remainder = decimal - whole
        fraction = self.fraction_lookup(remainder) if self.fraction_lookup and remainder else None
        if not fraction and remainder:
            approximate = Fraction(remainder).limit_denominator(64)
            fraction = f"{approximate.numerator}/{approximate.denominator}" if approximate.numerator else None
        if whole and fraction:
            return f"{whole}-{fraction}"
        return fraction or str(whole)

    @staticmethod
    def _present(value: Any) -> bool:
        if value is None or value == [] or value == {}:
            return False
        return str(value).strip().lower() not in EMPTY_VALUES

    @staticmethod
    def _text(value: Any) -> str:
        if value in (None, ""):
            return ""
        return re.sub(r"\s+", " ", str(value)).strip(" ,")

    @staticmethod
    def _dedupe(values: list[str]) -> list[str]:
        seen: set[str] = set()
        output: list[str] = []
        for value in values:
            key = value.casefold()
            if value and key not in seen:
                seen.add(key)
                output.append(value)
        return output

    @staticmethod
    def _join(values: list[str], separator: str = " ") -> str:
        return separator.join(value for value in values if value).strip()

    @staticmethod
    def _truncate(value: str, limit: int) -> str:
        if len(value) <= limit:
            return value
        clipped = value[: limit + 1].rsplit(" ", 1)[0]
        return (clipped or value[:limit]).rstrip(" ,")
