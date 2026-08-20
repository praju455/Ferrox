from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import ExtractedField, Product, ProductDeliveryRecord, ReferenceDataset
from app.services.description_builder import DeterministicDescriptionBuilder
from app.services.reference_data import ReferenceDataService, normalize_lookup


CORE_DELIVERY_COLUMNS = [
    "Manufacturer Name",
    "Brand Name",
    "Manufacturer Part Number",
    "Category",
    "Product Title",
    "Short Description",
    "Long Description",
    "Invoice Description",
    "Mobile Description",
]
OUTPUT_ALIASES = {
    "manufacturername": "manufacturer",
    "manufacturer": "manufacturer",
    "mfgname": "manufacturer",
    "brandname": "brand",
    "brand": "brand",
    "manufacturerpartnumber": "manufacturer_part_number",
    "mfgpartnum": "manufacturer_part_number",
    "mpn": "manufacturer_part_number",
    "partnumber": "manufacturer_part_number",
    "category": "category",
    "classpath": "category",
    "producttitle": "product_title",
    "shortdesc": "short_description",
    "shortdescription": "short_description",
    "longdesc": "long_description",
    "longdescription": "long_description",
    "invoicedesc": "invoice_description",
    "invoicedescription": "invoice_description",
    "mobiledesc": "mobile_description",
    "mobiledescription": "mobile_description",
}


class UnilogDeliveryService:
    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()
        self.references = ReferenceDataService(db, self.settings.max_reference_rows)
        self.builder = DeterministicDescriptionBuilder(
            fraction_lookup=self.references.fraction_for_decimal,
            uom_lookup=self.references.canonical_uom,
        )

    def generate(self, product: Product) -> ProductDeliveryRecord:
        ground_truth = self.references.active_dataset("ground_truth")
        columns = self._delivery_columns(ground_truth)
        values = self._canonical_values(product)
        descriptions = self.builder.build(product.category, values).as_dict()
        combined = {**values, **descriptions, "category": product.category or ""}
        fields = {column: self._value_for_column(column, combined) for column in columns}
        populated = sum(value not in (None, "", [], {}) for value in fields.values())
        expected = self.settings.delivery_expected_columns
        quality = {
            "schema_ready": bool(ground_truth and len(columns) == expected),
            "expected_columns": expected,
            "actual_columns": len(columns),
            "populated_columns": populated,
            "coverage": populated / len(columns) if columns else 0.0,
            "uses_approved_manufacturer": bool(values.get("manufacturer_master_record_id")),
            "deterministic_descriptions": True,
            "unsupported_fields_left_blank": True,
        }
        record = self.db.scalar(select(ProductDeliveryRecord).where(ProductDeliveryRecord.product_id == product.id))
        if record is None:
            record = ProductDeliveryRecord(product_id=product.id)
            self.db.add(record)
        record.schema_dataset_id = ground_truth.id if ground_truth else None
        record.schema_version = ground_truth.content_sha256[:12] if ground_truth else "unilog-core-v1"
        record.fields = fields
        record.descriptions = descriptions
        record.quality = quality
        self.db.commit()
        self.db.refresh(record)
        return record

    def _canonical_values(self, product: Product) -> dict[str, Any]:
        fields = list(
            self.db.scalars(select(ExtractedField).where(ExtractedField.product_id == product.id))
        )
        values: dict[str, Any] = {}
        for field in fields:
            value = field.value
            if field.unit and not isinstance(value, (dict, list)):
                value = {"value": value, "unit": self.references.canonical_uom(field.unit) or field.unit}
            values[field.field_name] = value
        manufacturer = self._scalar(values.get("manufacturer") or values.get("manufacturer_name"))
        match = self.references.canonical_manufacturer(manufacturer) if manufacturer else None
        if match:
            values["manufacturer"] = match["value"]
            values["manufacturer_master_record_id"] = match["record_id"]
            brand = self._first(match["payload"], ("brand_name", "unilog_brand", "brand"))
            if brand:
                values["brand"] = brand
        elif manufacturer:
            values["manufacturer"] = manufacturer
        values.setdefault("brand", values.get("manufacturer"))
        part = self._scalar(
            values.get("manufacturer_part_number") or values.get("part_number") or values.get("model")
        )
        if part:
            values["manufacturer_part_number"] = part
        values.setdefault("product_type", product.category or "Product")
        return values

    @staticmethod
    def _delivery_columns(dataset: ReferenceDataset | None) -> list[str]:
        if dataset:
            metadata = dataset.dataset_metadata or {}
            columns = metadata.get("delivery_columns") or []
            if columns:
                return list(columns)
            delivery_name = next((name for name in dataset.sheet_names if normalize_lookup(name) == "deliveryformat"), None)
            if delivery_name and dataset.columns.get(delivery_name):
                return list(dataset.columns[delivery_name])
        return CORE_DELIVERY_COLUMNS

    @staticmethod
    def _value_for_column(column: str, values: dict[str, Any]) -> Any:
        normalized = normalize_lookup(column)
        canonical = OUTPUT_ALIASES.get(normalized)
        if canonical:
            return UnilogDeliveryService._scalar(values.get(canonical))
        for key, value in values.items():
            if normalize_lookup(key) == normalized:
                return UnilogDeliveryService._scalar(value)
        return ""

    @staticmethod
    def _scalar(value: Any) -> Any:
        if isinstance(value, dict) and "value" in value:
            unit = value.get("unit")
            return f"{value['value']} {unit}".strip() if unit else value["value"]
        if isinstance(value, (dict, list)):
            return value
        return value

    @staticmethod
    def _first(payload: dict[str, Any], keys: tuple[str, ...]) -> Any:
        return next((payload[key] for key in keys if payload.get(key) not in (None, "")), None)
