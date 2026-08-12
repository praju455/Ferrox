from app.core.config import Settings
from app.models import Citation, ExtractedField, Product
from app.services.catalog_schemas import schema_for_category
from app.services.enrichment import GeminiGroundedEnrichment, GroundedCitation, GroundedField
from app.services.pipeline import ProductPipeline


class FakeResponse:
    def raise_for_status(self):
        return None

    def json(self):
        text = '{"value":"120","unit":"GPM","confidence":0.88,"evidence":"Manufacturer rating"}'
        return {
            "steps": [
                {
                    "type": "model_output",
                    "content": [
                        {
                            "type": "text",
                            "text": text,
                            "annotations": [
                                {
                                    "type": "url_citation",
                                    "url": "https://manufacturer.example/axp-200",
                                    "title": "Manufacturer datasheet",
                                    "start_index": 0,
                                    "end_index": len(text),
                                }
                            ],
                        }
                    ],
                }
            ],
            "usage": {"input_tokens": 40, "output_tokens": 20},
        }


class RecordingObserver:
    def __init__(self):
        self.events = []

    def record(self, event):
        self.events.append(event)


def test_gemini_grounded_enrichment_requires_and_returns_citations(monkeypatch):
    captured = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["json"] = kwargs["json"]
        return FakeResponse()

    monkeypatch.setattr("app.services.enrichment.requests.post", fake_post)
    observer = RecordingObserver()
    service = GeminiGroundedEnrichment(
        Settings(enable_grounded_enrichment=True, gemini_api_key="test-key"),
        observer=observer,
    )

    result = service.enrich_field("product-1", "Aurora AXP-200", "Industrial Pump", "flow_rate")

    assert result is not None
    assert result.value == "120"
    assert result.citations[0].url == "https://manufacturer.example/axp-200"
    assert captured["json"]["tools"] == [{"type": "google_search"}]
    assert observer.events[0].task == "grounded_enrich"
    assert observer.events[0].input_tokens == 40


class FakeGroundedEnrichment:
    enabled = True

    def enrich_field(self, product_id, product_name, category, field_name):
        return GroundedField(
            value="Aurora Industrial",
            unit=None,
            confidence=0.9,
            evidence="Manufacturer product page",
            citations=[GroundedCitation("https://manufacturer.example/axp-200", "Aurora", "Manufacturer product page")],
        )


def test_pipeline_persists_only_citation_backed_enrichment(db_session):
    product = Product(
        name="Aurora AXP-200",
        category="Industrial Pump",
        dynamic_schema=schema_for_category("Industrial Pump"),
    )
    db_session.add(product)
    db_session.commit()

    pipeline = ProductPipeline(db_session, enrichment=FakeGroundedEnrichment())
    pipeline.enrich(product)
    db_session.commit()

    fields = db_session.query(ExtractedField).filter_by(product_id=product.id).all()
    citations = db_session.query(Citation).filter_by(product_id=product.id).all()
    assert fields
    assert len(citations) == len(fields)
    assert all(field.status.value == "enriched" for field in fields)
    assert all(field.validation["grounded"] is True for field in fields)
