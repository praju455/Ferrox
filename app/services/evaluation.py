import csv
import io
import re
from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import EvaluationRun, ProductDeliveryRecord, ReferenceDataset, ReferenceRecord
from app.services.delivery import UnilogDeliveryService
from app.services.reference_data import ReferenceDataService, normalize_lookup


IDENTITY_COLUMNS = {
    "manufacturerpartnumber",
    "mfgpartnum",
    "partnumber",
    "mpn",
    "sku",
    "itemnumber",
}
MANUFACTURER_COLUMNS = {"manufacturer", "manufacturername", "mfgname", "brand", "brandname"}
TAXONOMY_PARTS = ("category", "classpath", "taxonomy", "unspsc", "department", "dept", "class", "fine")


class GroundTruthEvaluationService:
    def __init__(self, db: Session):
        self.db = db
        self.references = ReferenceDataService(db)

    def run(self, dataset_id: str, generate_missing: bool = True) -> EvaluationRun:
        dataset = self.db.get(ReferenceDataset, dataset_id)
        if dataset is None or dataset.dataset_type != "ground_truth":
            raise ValueError("Evaluation requires a ground_truth reference dataset")
        delivery_sheet = (dataset.dataset_metadata or {}).get("delivery_sheet")
        if not delivery_sheet:
            raise ValueError("Ground-truth workbook requires a Delivery Format worksheet")
        if generate_missing:
            self._generate_missing_deliveries()
        expected_rows = list(
            self.db.scalars(
                select(ReferenceRecord)
                .where(ReferenceRecord.dataset_id == dataset.id, ReferenceRecord.sheet_name == delivery_sheet)
                .order_by(ReferenceRecord.row_number)
            )
        )
        actual_by_key = self._actual_by_key()
        lov_index = self._lov_index()
        totals = defaultdict(int)
        row_results: list[dict[str, Any]] = []
        for expected in expected_rows:
            sku = expected.lookup_key or f"row-{expected.row_number}"
            actual = actual_by_key.get(normalize_lookup(sku))
            result = self._compare_row(expected, actual, lov_index)
            row_results.append(result)
            for key, value in result["counts"].items():
                totals[key] += value
        run = EvaluationRun(
            ground_truth_dataset_id=dataset.id,
            status="completed",
            total_items=len(expected_rows),
            matched_items=totals["matched_items"],
            field_accuracy=self._ratio(totals["correct_fields"], totals["compared_fields"]),
            character_limit_compliance=self._ratio(totals["valid_descriptions"], totals["checked_descriptions"]),
            lov_compliance=self._ratio(totals["valid_lov_values"], totals["checked_lov_values"]),
            manufacturer_accuracy=self._ratio(totals["correct_manufacturer"], totals["checked_manufacturer"]),
            taxonomy_accuracy=self._ratio(totals["correct_taxonomy"], totals["checked_taxonomy"]),
            metrics={
                **dict(totals),
                "unmatched_items": len(expected_rows) - totals["matched_items"],
                "evaluated_delivery_columns": len((dataset.dataset_metadata or {}).get("delivery_columns", [])),
                "comparison": "nonblank ground-truth cells only",
            },
            row_results=row_results,
        )
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        return run

    def export_csv(self, run: EvaluationRun) -> str:
        output = io.StringIO()
        writer = csv.DictWriter(
            output,
            fieldnames=["sku", "ground_truth_row", "matched", "correct_fields", "compared_fields", "field_accuracy", "errors"],
        )
        writer.writeheader()
        for row in run.row_results:
            writer.writerow(
                {
                    "sku": row["sku"],
                    "ground_truth_row": row["ground_truth_row"],
                    "matched": row["matched"],
                    "correct_fields": row["counts"].get("correct_fields", 0),
                    "compared_fields": row["counts"].get("compared_fields", 0),
                    "field_accuracy": row["field_accuracy"],
                    "errors": " | ".join(
                        f"{error['field']}: expected={error['expected']!r}, actual={error['actual']!r}"
                        for error in row["errors"]
                    ),
                }
            )
        return output.getvalue()

    def _generate_missing_deliveries(self) -> None:
        existing = set(self.db.scalars(select(ProductDeliveryRecord.product_id)))
        from app.models import Product

        delivery_service = UnilogDeliveryService(self.db)
        for product in self.db.scalars(select(Product).order_by(Product.created_at)):
            if product.id not in existing:
                delivery_service.generate(product)

    def _actual_by_key(self) -> dict[str, ProductDeliveryRecord]:
        index: dict[str, ProductDeliveryRecord] = {}
        for record in self.db.scalars(select(ProductDeliveryRecord)):
            for column, value in record.fields.items():
                if normalize_lookup(column) in IDENTITY_COLUMNS and value not in (None, ""):
                    index[normalize_lookup(value)] = record
        return index

    def _compare_row(
        self,
        expected: ReferenceRecord,
        actual: ProductDeliveryRecord | None,
        lov_index: dict[str, set[str]],
    ) -> dict[str, Any]:
        counts = defaultdict(int)
        errors: list[dict[str, Any]] = []
        if actual is None:
            compared = sum(value not in (None, "", [], {}) for value in expected.payload.values())
            counts["compared_fields"] = compared
            for field, value in expected.payload.items():
                if value in (None, "", [], {}):
                    continue
                normalized_field = normalize_lookup(field)
                if normalized_field in MANUFACTURER_COLUMNS:
                    counts["checked_manufacturer"] += 1
                if any(part in normalized_field for part in TAXONOMY_PARTS):
                    counts["checked_taxonomy"] += 1
                if normalized_field in {"invoicedesc", "invoicedescription", "mobiledesc", "mobiledescription"}:
                    counts["checked_descriptions"] += 1
                if normalized_field in lov_index:
                    counts["checked_lov_values"] += 1
            return {
                "sku": expected.lookup_key or f"row-{expected.row_number}",
                "ground_truth_row": expected.row_number,
                "matched": False,
                "field_accuracy": 0.0,
                "counts": dict(counts),
                "errors": [{"field": "record", "expected": "matching product", "actual": "not found"}],
            }
        counts["matched_items"] = 1
        actual_normalized = {normalize_lookup(key): value for key, value in actual.fields.items()}
        for source_field, expected_value in expected.payload.items():
            if expected_value in (None, "", [], {}):
                continue
            normalized_field = normalize_lookup(source_field)
            actual_value = actual_normalized.get(normalized_field, "")
            counts["compared_fields"] += 1
            matches = self._equal(expected_value, actual_value)
            if matches:
                counts["correct_fields"] += 1
            elif len(errors) < 50:
                errors.append({"field": normalized_field, "expected": expected_value, "actual": actual_value})
            if normalized_field in MANUFACTURER_COLUMNS:
                counts["checked_manufacturer"] += 1
                counts["correct_manufacturer"] += int(matches)
            if any(part in normalized_field for part in TAXONOMY_PARTS):
                counts["checked_taxonomy"] += 1
                counts["correct_taxonomy"] += int(matches)
            if normalized_field in {"invoicedesc", "invoicedescription"}:
                counts["checked_descriptions"] += 1
                counts["valid_descriptions"] += int(bool(actual_value) and len(str(actual_value)) <= 40 and str(actual_value).upper() == str(actual_value))
            elif normalized_field in {"mobiledesc", "mobiledescription"}:
                counts["checked_descriptions"] += 1
                counts["valid_descriptions"] += int(60 <= len(str(actual_value)) <= 80)
            allowed = lov_index.get(normalized_field)
            if allowed:
                counts["checked_lov_values"] += 1
                counts["valid_lov_values"] += int(actual_value not in (None, "") and normalize_lookup(actual_value) in allowed)
        compared = counts["compared_fields"]
        return {
            "sku": expected.lookup_key or f"row-{expected.row_number}",
            "ground_truth_row": expected.row_number,
            "matched": True,
            "product_id": actual.product_id,
            "field_accuracy": self._ratio(counts["correct_fields"], compared),
            "counts": dict(counts),
            "errors": errors,
        }

    def _lov_index(self) -> dict[str, set[str]]:
        index: dict[str, set[str]] = defaultdict(set)
        for dataset_type in ("lov", "faucets", "fittings"):
            dataset = self.references.active_dataset(dataset_type)
            if dataset is None:
                continue
            for record in self.db.scalars(select(ReferenceRecord).where(ReferenceRecord.dataset_id == dataset.id)):
                attribute = next(
                    (record.payload.get(key) for key in ("attribute_name", "attribute", "field_name", "field") if record.payload.get(key)),
                    None,
                )
                value = next(
                    (record.payload.get(key) for key in ("lov_value", "allowed_value", "canonical_value", "value", "name") if record.payload.get(key)),
                    None,
                )
                if attribute and value:
                    index[normalize_lookup(attribute)].add(normalize_lookup(value))
        return index

    @staticmethod
    def _equal(expected: Any, actual: Any) -> bool:
        if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
            return abs(float(expected) - float(actual)) <= 1e-9
        normalize = lambda value: re.sub(r"\s+", " ", str(value or "")).strip().casefold()
        return normalize(expected) == normalize(actual)

    @staticmethod
    def _ratio(numerator: int, denominator: int) -> float:
        return round(numerator / denominator, 6) if denominator else 0.0
