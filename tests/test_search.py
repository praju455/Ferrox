from app.core.config import Settings
from app.models import Product
from app.services.ingestion import IngestionService
from app.services.search import DuplicateDetector, EmbeddingProvider, SemanticSearchService, SourceChunkIndexer


def add_product(db_session, name: str, text: str) -> Product:
    product = Product(name=name)
    db_session.add(product)
    db_session.flush()
    db_session.add(IngestionService(Settings(_env_file=None)).from_text(product.id, text, "catalog"))
    db_session.commit()
    db_session.refresh(product)
    return product


def test_source_chunks_are_indexed_and_searched_in_sqlite(db_session):
    settings = Settings(_env_file=None, embedding_chunk_chars=1000, embedding_chunk_overlap_chars=100)
    pump = add_product(db_session, "Acme Pump P-10", "Acme centrifugal water pump P-10 flow rate 120 GPM cast iron")
    bearing = add_product(db_session, "Borex Bearing B-20", "Borex ball bearing B-20 bore diameter 20 mm chrome steel")
    indexer = SourceChunkIndexer(db_session, settings)
    indexer.index_sources(pump, pump.sources)
    indexer.index_sources(bearing, bearing.sources)
    db_session.commit()

    hits = SemanticSearchService(db_session, settings, indexer.embeddings).search("centrifugal water pump 120 GPM", 2)

    assert hits[0].product_id == pump.id
    assert hits[0].score > hits[1].score


def test_duplicate_detector_groups_best_chunk_per_product(db_session):
    settings = Settings(
        _env_file=None,
        embedding_chunk_chars=1000,
        embedding_chunk_overlap_chars=100,
        duplicate_similarity_threshold=0.5,
    )
    original = add_product(db_session, "Acme Pump P-10", "Acme centrifugal pump model P-10 flow rate 120 GPM")
    duplicate = add_product(db_session, "Acme P10 Pump", "Acme centrifugal pump P-10 rated flow 120 GPM")
    indexer = SourceChunkIndexer(db_session, settings)
    indexer.index_sources(original, original.sources)
    indexer.index_sources(duplicate, duplicate.sources)
    db_session.commit()

    hits = DuplicateDetector(SemanticSearchService(db_session, settings, indexer.embeddings), 0.2).find(original)

    assert any(hit.product_id == duplicate.id for hit in hits)


def test_gemini_embedding_provider_requests_retrieval_configuration(monkeypatch):
    captured = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"embedding": {"values": [1.0] + [0.0] * 767}}

    def fake_post(url, headers, json, timeout):
        captured.update({"url": url, "headers": headers, "json": json, "timeout": timeout})
        return Response()

    monkeypatch.setattr("app.services.search.requests.post", fake_post)
    provider = EmbeddingProvider(Settings(_env_file=None, gemini_api_key="key"))

    embedding = provider.embed("industrial pump", "RETRIEVAL_DOCUMENT", "Pump P-10")

    assert len(embedding) == 768
    assert captured["json"]["outputDimensionality"] == 768
    assert captured["json"]["taskType"] == "RETRIEVAL_DOCUMENT"
    assert captured["json"]["title"] == "Pump P-10"
    assert "embedContentConfig" not in captured["json"]


def test_semantic_search_can_be_scoped_to_one_product(db_session):
    settings = Settings(_env_file=None, embedding_chunk_chars=1000, embedding_chunk_overlap_chars=100)
    first = add_product(db_session, "Acme Pump P-10", "Acme pump rated flow 120 GPM")
    second = add_product(db_session, "Acme Pump P-20", "Acme pump rated flow 180 GPM")
    indexer = SourceChunkIndexer(db_session, settings)
    indexer.index_sources(first, first.sources)
    indexer.index_sources(second, second.sources)
    db_session.commit()

    hits = SemanticSearchService(db_session, settings, indexer.embeddings).search(
        "Acme pump flow",
        10,
        product_id=second.id,
    )

    assert hits
    assert {hit.product_id for hit in hits} == {second.id}
