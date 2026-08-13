import csv
import io
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import BatchJob, Citation, ExtractedField, LLMRun, Product, ReviewItem, Source, SourceChunk


class CatalogAnalyticsService:
    def __init__(self, db: Session):
        self.db = db

    def report(self) -> dict[str, Any]:
        products = list(self.db.scalars(select(Product)))
        fields = list(self.db.scalars(select(ExtractedField)))
        reviews = list(self.db.scalars(select(ReviewItem)))

        totals = {
            "products": len(products),
            "sources": self._count(Source),
            "source_chunks": self._count(SourceChunk),
            "fields": len(fields),
            "citations": self._count(Citation),
            "open_reviews": sum(review.status.value == "open" for review in reviews),
            "batch_runs": self._count(BatchJob),
            "llm_runs": self._count(LLMRun),
        }
        valid_fields = sum(bool((field.validation or {}).get("valid")) for field in fields)
        cited_field_count = self.db.scalar(select(func.count(func.distinct(Citation.extracted_field_id)))) or 0
        quality = {
            "average_completeness": self._average(product.completeness_score for product in products),
            "average_confidence": self._average(product.confidence_score for product in products),
            "validation_pass_rate": valid_fields / len(fields) if fields else 0.0,
            "citation_coverage": cited_field_count / len(fields) if fields else 0.0,
            "review_rate": totals["open_reviews"] / len(products) if products else 0.0,
        }
        validation_issues = Counter(
            issue
            for field in fields
            for issue in [
                *((field.validation or {}).get("rule_issues") or []),
                *((field.validation or {}).get("semantic_issues") or []),
            ]
        )
        return {
            "generated_at": datetime.now(timezone.utc),
            "totals": totals,
            "quality": {name: round(value, 6) for name, value in quality.items()},
            "categories": self._breakdown(Product.category, "Unclassified"),
            "source_types": self._breakdown(Source.source_type),
            "field_statuses": self._breakdown(ExtractedField.status),
            "review_severities": self._breakdown(ReviewItem.severity, where=ReviewItem.status == "open"),
            "batch_statuses": self._breakdown(BatchJob.status),
            "completeness_bands": self._completeness_bands(products),
            "validation_issues": [
                {"label": label, "count": count}
                for label, count in validation_issues.most_common(20)
            ],
            "providers": self._provider_performance(),
        }

    def csv_report(self) -> str:
        report = self.report()
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["section", "metric", "value", "secondary_value"])
        for name, value in report["totals"].items():
            writer.writerow(["totals", name, value, ""])
        for name, value in report["quality"].items():
            writer.writerow(["quality", name, value, ""])
        for section in ("categories", "source_types", "field_statuses", "review_severities", "batch_statuses", "completeness_bands", "validation_issues"):
            for item in report[section]:
                writer.writerow([section, item["label"], item["count"], ""])
        for provider in report["providers"]:
            writer.writerow(["providers", provider["provider"], provider["runs"], provider["estimated_cost_usd"]])
        return output.getvalue()

    def _count(self, model: type) -> int:
        return int(self.db.scalar(select(func.count()).select_from(model)) or 0)

    def _breakdown(self, column, empty_label: str = "Unknown", where=None) -> list[dict[str, Any]]:
        statement = select(column, func.count()).group_by(column).order_by(func.count().desc())
        if where is not None:
            statement = statement.where(where)
        rows = self.db.execute(statement).all()
        return [
            {
                "label": getattr(label, "value", label) or empty_label,
                "count": int(count),
            }
            for label, count in rows
        ]

    def _provider_performance(self) -> list[dict[str, Any]]:
        rows = self.db.execute(
            select(
                LLMRun.provider,
                func.count(),
                func.avg(LLMRun.latency_ms),
                func.sum(LLMRun.input_tokens + LLMRun.output_tokens),
                func.sum(LLMRun.estimated_cost_usd),
            )
            .group_by(LLMRun.provider)
            .order_by(func.count().desc())
        ).all()
        providers = []
        for provider, runs, latency, tokens, cost in rows:
            successful = self.db.scalar(
                select(func.count()).select_from(LLMRun).where(LLMRun.provider == provider, LLMRun.status == "success")
            ) or 0
            providers.append({
                "provider": provider,
                "runs": int(runs),
                "success_rate": round(successful / runs, 6) if runs else 0.0,
                "average_latency_ms": round(float(latency or 0), 2),
                "tokens": int(tokens or 0),
                "estimated_cost_usd": round(float(cost or 0), 8),
            })
        return providers

    @staticmethod
    def _average(values) -> float:
        values = list(values)
        return sum(values) / len(values) if values else 0.0

    @staticmethod
    def _completeness_bands(products: list[Product]) -> list[dict[str, Any]]:
        bands = Counter()
        for product in products:
            score = product.completeness_score
            if score >= 0.9:
                bands["90-100%"] += 1
            elif score >= 0.7:
                bands["70-89%"] += 1
            elif score >= 0.4:
                bands["40-69%"] += 1
            else:
                bands["0-39%"] += 1
        return [{"label": label, "count": bands[label]} for label in ("90-100%", "70-89%", "40-69%", "0-39%")]
