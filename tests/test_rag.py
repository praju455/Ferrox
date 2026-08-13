from app.models import ExtractedField, FieldStatus, Product
from app.services.rag import InternalCatalogRAG
from app.services.search import SearchHit


def catalog_hit(chunk_id: str = "chunk-1") -> SearchHit:
    return SearchHit(
        chunk_id=chunk_id,
        source_id="source-1",
        product_id="product-1",
        product_name="Acme Pump P-10",
        source_identifier="manufacturer-datasheet",
        content="The Acme P-10 has a rated flow of 120 GPM.",
        score=0.91,
    )


class FakeSearch:
    def __init__(self, hits: list[SearchHit]):
        self.hits = hits

    def search(
        self,
        query: str,
        limit: int,
        exclude_product_id: str | None = None,
        product_id: str | None = None,
    ) -> list[SearchHit]:
        if product_id:
            return [hit for hit in self.hits[:limit] if hit.product_id == product_id]
        return self.hits[:limit]


class FakeLLM:
    def __init__(self, response: dict):
        self.response = response
        self.requests = []

    def complete_json(self, request):
        self.requests.append(request)
        return self.response


def test_internal_rag_returns_only_search_backed_citations():
    llm = FakeLLM({"answer": "The rated flow is 120 GPM.", "chunk_ids": ["chunk-1"]})
    rag = InternalCatalogRAG(FakeSearch([catalog_hit()]), llm)

    result = rag.answer("What is the rated flow?")

    assert result is not None
    assert result.answer == "The rated flow is 120 GPM."
    assert result.citations[0].url == "ferrox://source-chunks/chunk-1"
    assert result.matches[0].chunk_id == "chunk-1"


def test_internal_rag_rejects_fabricated_chunk_citations():
    llm = FakeLLM({"answer": "The rated flow is 999 GPM.", "chunk_ids": ["invented-chunk"]})
    rag = InternalCatalogRAG(FakeSearch([catalog_hit()]), llm)

    assert rag.answer("What is the rated flow?") is None


def test_internal_rag_enrichment_preserves_catalog_evidence():
    llm = FakeLLM({
        "value": 120,
        "unit": "GPM",
        "confidence": 0.88,
        "evidence": "rated flow of 120 GPM",
        "chunk_ids": ["chunk-1"],
    })
    rag = InternalCatalogRAG(FakeSearch([catalog_hit()]), llm)
    product = Product(id="product-1", name="Acme Pump P-10", category="Industrial Pump")
    product.fields = [
        ExtractedField(
            field_name="model",
            value="P-10",
            confidence=1.0,
            status=FieldStatus.validated,
        )
    ]

    result = rag.enrich_field(product, "flow_rate")

    assert result is not None
    assert result.value == 120
    assert result.unit == "GPM"
    assert result.citations[0].cited_text.startswith("The Acme P-10")
