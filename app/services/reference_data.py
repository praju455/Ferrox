import re
from collections.abc import Iterable
from typing import Any
from urllib.parse import urlparse

from rapidfuzz import fuzz, process
from sqlalchemy import insert, select, update
from sqlalchemy.orm import Session

from app.models import ReferenceDataset, ReferenceRecord
from app.services.xlsx_import import MultiSheetXLSXParser, ParsedWorkbook


REFERENCE_DATASET_TYPES = {
    "manufacturer",
    "lov",
    "uom",
    "fraction",
    "faucets",
    "fittings",
    "ground_truth",
    "catalog_sample",
    "reference_index",
}

MANUFACTURER_KEYS = (
    "unilog_brand",
    "standard_manufacturer",
    "manufacturer_name",
    "manufacturer",
    "part_manuf",
    "brand",
    "e1_brand",
    "dib_brand",
)
PART_NUMBER_KEYS = ("mfg_part_num", "manufacturer_part_number", "part_number", "mpn", "sku", "item_number")
LOV_KEYS = ("lov_value", "allowed_value", "value", "attribute_value", "description", "name")
UOM_KEYS = ("standard_uom", "uom", "unit", "symbol", "abbreviation")
URL_KEY_PARTS = ("url", "website", "domain", "homepage")


def normalize_lookup(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


class ReferenceDataService:
    def __init__(self, db: Session, max_rows: int = 500_000):
        self.db = db
        self.parser = MultiSheetXLSXParser(max_rows=max_rows)
        self._manufacturer_cache: tuple[str, list[ReferenceRecord], dict[str, str]] | None = None

    def load_xlsx(self, dataset_type: str, content: bytes, filename: str) -> ReferenceDataset:
        if dataset_type not in REFERENCE_DATASET_TYPES:
            raise ValueError(f"Unsupported reference dataset type: {dataset_type}")
        workbook = self.parser.parse(content, filename)
        return self.store_workbook(dataset_type, workbook)

    def store_workbook(self, dataset_type: str, workbook: ParsedWorkbook) -> ReferenceDataset:
        if dataset_type == "manufacturer":
            self._manufacturer_cache = None
        self.db.execute(
            update(ReferenceDataset)
            .where(ReferenceDataset.dataset_type == dataset_type, ReferenceDataset.is_active.is_(True))
            .values(is_active=False)
        )
        metadata = self._metadata(dataset_type, workbook)
        dataset = ReferenceDataset(
            dataset_type=dataset_type,
            filename=workbook.filename,
            content_sha256=workbook.content_sha256,
            status="loading",
            row_count=workbook.row_count,
            sheet_names=[sheet.name for sheet in workbook.sheets],
            columns={sheet.name: [sheet.original_columns[column] for column in sheet.columns] for sheet in workbook.sheets},
            dataset_metadata=metadata,
            is_active=True,
        )
        self.db.add(dataset)
        self.db.flush()
        pending: list[dict[str, Any]] = []
        for sheet in workbook.sheets:
            for row in sheet.rows:
                lookup = self._lookup_key(dataset_type, row.values)
                pending.append(
                    {
                        "dataset_id": dataset.id,
                        "dataset_type": dataset_type,
                        "sheet_name": sheet.name,
                        "row_number": row.row_number,
                        "lookup_key": lookup,
                        "normalized_key": normalize_lookup(lookup) if lookup else None,
                        "payload": row.values,
                    }
                )
                if len(pending) >= 2_000:
                    self.db.execute(insert(ReferenceRecord), pending)
                    pending.clear()
        if pending:
            self.db.execute(insert(ReferenceRecord), pending)
        dataset.status = "ready"
        self.db.commit()
        self.db.refresh(dataset)
        return dataset

    def active_dataset(self, dataset_type: str) -> ReferenceDataset | None:
        return self.db.scalar(
            select(ReferenceDataset)
            .where(ReferenceDataset.dataset_type == dataset_type, ReferenceDataset.is_active.is_(True))
            .order_by(ReferenceDataset.created_at.desc())
        )

    def exact(self, dataset_type: str, value: Any) -> ReferenceRecord | None:
        dataset = self.active_dataset(dataset_type)
        if dataset is None:
            return None
        return self.db.scalar(
            select(ReferenceRecord).where(
                ReferenceRecord.dataset_id == dataset.id,
                ReferenceRecord.normalized_key == normalize_lookup(value),
            )
        )

    def canonical_manufacturer(self, value: Any, score_cutoff: float = 88.0) -> dict[str, Any] | None:
        exact = self.exact("manufacturer", value)
        if exact:
            return self._canonical_match(exact, 100.0)
        dataset = self.active_dataset("manufacturer")
        if dataset is None or not value:
            return None
        if self._manufacturer_cache is None or self._manufacturer_cache[0] != dataset.id:
            records = list(
                self.db.scalars(
                    select(ReferenceRecord).where(
                        ReferenceRecord.dataset_id == dataset.id,
                        ReferenceRecord.lookup_key.is_not(None),
                    )
                )
            )
            choices = {
                f"{record.id}:{index}": str(alias)
                for record in records
                for index, alias in enumerate(self._manufacturer_aliases(record.payload))
            }
            self._manufacturer_cache = (dataset.id, records, choices)
        _, records, choices = self._manufacturer_cache
        result = process.extractOne(str(value), choices, scorer=fuzz.WRatio, score_cutoff=score_cutoff)
        if result is None:
            return None
        _, score, choice_id = result
        record_id = str(choice_id).split(":", 1)[0]
        record = next(record for record in records if record.id == record_id)
        return self._canonical_match(record, float(score))

    def allowed_values(self, dataset_type: str = "lov", attribute: str | None = None) -> set[str]:
        dataset = self.active_dataset(dataset_type)
        if dataset is None:
            return set()
        values: set[str] = set()
        records = self.db.scalars(select(ReferenceRecord).where(ReferenceRecord.dataset_id == dataset.id))
        for record in records:
            if attribute and not self._record_matches_attribute(record.payload, attribute):
                continue
            value = self._first(record.payload, LOV_KEYS)
            if value not in (None, ""):
                values.add(str(value).strip())
        return values

    def canonical_uom(self, value: Any) -> str | None:
        record = self.exact("uom", value)
        if record is None:
            return None
        canonical = self._first(record.payload, UOM_KEYS)
        return str(canonical) if canonical not in (None, "") else record.lookup_key

    def fraction_for_decimal(self, value: float, tolerance: float = 0.0001) -> str | None:
        dataset = self.active_dataset("fraction")
        if dataset is None:
            return None
        for record in self.db.scalars(select(ReferenceRecord).where(ReferenceRecord.dataset_id == dataset.id)):
            pairs = self._fraction_pairs(record.payload)
            for decimal, fraction in pairs:
                if abs(decimal - value) <= tolerance:
                    return fraction
        return None

    def manufacturer_domains(self, manufacturer: str | None = None) -> set[str]:
        dataset = self.active_dataset("manufacturer")
        if dataset is None:
            return set()
        query = select(ReferenceRecord).where(ReferenceRecord.dataset_id == dataset.id)
        if manufacturer:
            normalized = normalize_lookup(manufacturer)
            query = query.where(ReferenceRecord.normalized_key == normalized)
        domains: set[str] = set()
        for record in self.db.scalars(query):
            for key, value in record.payload.items():
                if value and any(part in key for part in URL_KEY_PARTS):
                    domain = self._domain(str(value))
                    if domain:
                        domains.add(domain)
        return domains

    @staticmethod
    def _metadata(dataset_type: str, workbook: ParsedWorkbook) -> dict[str, Any]:
        metadata: dict[str, Any] = {"parser": "openpyxl", "preserves_all_visible_sheets": True}
        delivery_sheet = next((sheet for sheet in workbook.sheets if normalize_lookup(sheet.name) == "deliveryformat"), None)
        input_sheet = next((sheet for sheet in workbook.sheets if normalize_lookup(sheet.name) == "input"), None)
        if dataset_type == "ground_truth":
            metadata.update(
                {
                    "input_sheet": input_sheet.name if input_sheet else None,
                    "delivery_sheet": delivery_sheet.name if delivery_sheet else None,
                    "delivery_columns": [delivery_sheet.original_columns[column] for column in delivery_sheet.columns]
                    if delivery_sheet
                    else [],
                    "delivery_column_map": delivery_sheet.original_columns if delivery_sheet else {},
                }
            )
        return metadata

    @classmethod
    def _lookup_key(cls, dataset_type: str, payload: dict[str, Any]) -> str | None:
        aliases: Iterable[str]
        if dataset_type == "manufacturer":
            aliases = MANUFACTURER_KEYS
        elif dataset_type == "uom":
            aliases = UOM_KEYS
        elif dataset_type in {"lov", "faucets", "fittings"}:
            aliases = LOV_KEYS
        elif dataset_type in {"ground_truth", "catalog_sample"}:
            aliases = PART_NUMBER_KEYS
        else:
            aliases = payload.keys()
        value = cls._first(payload, aliases)
        return str(value).strip()[:1000] if value not in (None, "") else None

    @staticmethod
    def _first(payload: dict[str, Any], keys: Iterable[str]) -> Any:
        for key in keys:
            if payload.get(key) not in (None, ""):
                return payload[key]
        return None

    @classmethod
    def _canonical_match(cls, record: ReferenceRecord, score: float) -> dict[str, Any]:
        canonical = cls._first(record.payload, MANUFACTURER_KEYS) or record.lookup_key
        return {"value": canonical, "score": round(score, 2), "record_id": record.id, "payload": record.payload}

    @classmethod
    def _manufacturer_aliases(cls, payload: dict[str, Any]) -> list[str]:
        return [str(payload[key]) for key in MANUFACTURER_KEYS if payload.get(key) not in (None, "")]

    @staticmethod
    def _record_matches_attribute(payload: dict[str, Any], attribute: str) -> bool:
        normalized = normalize_lookup(attribute)
        keys = ("attribute", "attribute_name", "field", "field_name", "feature")
        return any(normalize_lookup(payload.get(key)) == normalized for key in keys if payload.get(key))

    @staticmethod
    def _fraction_pairs(payload: dict[str, Any]) -> list[tuple[float, str]]:
        pairs: list[tuple[float, str]] = []
        for key, raw_decimal in payload.items():
            if "decimal" not in key or raw_decimal in (None, ""):
                continue
            suffix = key.removeprefix("decimal")
            fraction = payload.get(f"fraction{suffix}") or payload.get(f"fraction_{suffix.lstrip('_')}")
            try:
                if fraction not in (None, ""):
                    pairs.append((float(raw_decimal), str(fraction)))
            except (TypeError, ValueError):
                continue
        return pairs

    @staticmethod
    def _domain(value: str) -> str | None:
        candidate = value if "://" in value else f"https://{value}"
        host = (urlparse(candidate).hostname or "").lower().strip(".")
        return host.removeprefix("www.") or None
