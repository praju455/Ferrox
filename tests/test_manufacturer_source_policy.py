from app.core.config import Settings
from app.services.enrichment import GeminiGroundedEnrichment


class CitationResponse:
    def __init__(self, url):
        self.url = url

    def raise_for_status(self):
        return None

    def json(self):
        text = '{"value":"Brass","unit":null,"confidence":0.91,"evidence":"Product page"}'
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
                                    "url": self.url,
                                    "title": "Product page",
                                    "start_index": 0,
                                    "end_index": len(text),
                                }
                            ],
                        }
                    ],
                }
            ]
        }


def test_grounded_enrichment_rejects_distributor_citations(monkeypatch):
    monkeypatch.setattr(
        "app.services.enrichment.requests.post",
        lambda *args, **kwargs: CitationResponse("https://marketplace.example/acme-pump"),
    )
    service = GeminiGroundedEnrichment(Settings(enable_grounded_enrichment=True, gemini_api_key="key"))

    result = service.enrich_field("p1", "Acme Pump", "Pump", "material", {"acme.com"})

    assert result is None


def test_grounded_enrichment_accepts_manufacturer_subdomains(monkeypatch):
    monkeypatch.setattr(
        "app.services.enrichment.requests.post",
        lambda *args, **kwargs: CitationResponse("https://products.acme.com/pump"),
    )
    service = GeminiGroundedEnrichment(Settings(enable_grounded_enrichment=True, gemini_api_key="key"))

    result = service.enrich_field("p1", "Acme Pump", "Pump", "material", {"acme.com"})

    assert result is not None
    assert result.value == "Brass"


def test_grounded_enrichment_does_not_search_without_approved_domains(monkeypatch):
    monkeypatch.setattr(
        "app.services.enrichment.requests.post",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("network must not be called")),
    )
    service = GeminiGroundedEnrichment(Settings(enable_grounded_enrichment=True, gemini_api_key="key"))

    assert service.enrich_field("p1", "Acme Pump", "Pump", "material", set()) is None
