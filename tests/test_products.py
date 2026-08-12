import fitz

from app.models import SourceType
from app.services.ingestion import IngestionService


def test_product_accepts_text_url_and_pdf_sources(client, monkeypatch):
    product_response = client.post("/api/v1/products", json={"name": "Aurora AXP-200"})
    assert product_response.status_code == 201
    product_id = product_response.json()["id"]

    text_response = client.post(
        f"/api/v1/products/{product_id}/sources/text",
        json={"text": "Model AXP-200. Flow rate 120 GPM.", "source_identifier": "catalog"},
    )
    assert text_response.status_code == 201

    def fake_from_url(self, target_product_id, url):
        return self._source(
            target_product_id,
            SourceType.url,
            url,
            "Supplier page for AXP-200 with 110 GPM flow rate.",
            {"parser": "test"},
        )

    monkeypatch.setattr(IngestionService, "from_url", fake_from_url)
    url_response = client.post(
        f"/api/v1/products/{product_id}/sources/url",
        json={"url": "https://example.com/axp-200"},
    )
    assert url_response.status_code == 201

    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "AXP-200 pump datasheet - 120 GPM - 5 HP")
    pdf_response = client.post(
        f"/api/v1/products/{product_id}/sources/pdf",
        files={"file": ("AXP-200.pdf", document.tobytes(), "application/pdf")},
    )
    document.close()
    assert pdf_response.status_code == 201

    sources_response = client.get(f"/api/v1/products/{product_id}/sources")
    assert sources_response.status_code == 200
    sources = sources_response.json()
    assert {source["source_type"] for source in sources} == {"text", "url", "pdf"}
    assert all(source["raw_content"] for source in sources)

    detail_response = client.get(f"/api/v1/products/{product_id}")
    assert len(detail_response.json()["sources"]) == 3


def test_products_can_be_listed_searched_and_deleted(client):
    first = client.post("/api/v1/products", json={"name": "Aurora Pump"}).json()
    client.post("/api/v1/products", json={"name": "Borex Bearing"})

    search_response = client.get("/api/v1/products", params={"search": "Aurora"})
    assert search_response.status_code == 200
    assert [product["id"] for product in search_response.json()] == [first["id"]]

    delete_response = client.delete(f"/api/v1/products/{first['id']}")
    assert delete_response.status_code == 204
    assert client.get(f"/api/v1/products/{first['id']}").status_code == 404


def test_pipeline_runs_only_requested_stages(client):
    product = client.post("/api/v1/products", json={"name": "VoltEdge VM-10"}).json()
    product_id = product["id"]
    client.post(
        f"/api/v1/products/{product_id}/sources/text",
        json={
            "text": "Manufacturer: VoltEdge. Model: VM-10 motor. 10 HP. 230 V. 1750 RPM.",
            "source_identifier": "datasheet",
        },
    )

    classify_response = client.post(
        f"/api/v1/products/{product_id}/pipeline",
        json={"stages": ["classify"]},
    )
    assert classify_response.status_code == 200
    assert classify_response.json()["category"] == "Electric Motor"
    assert classify_response.json()["fields"] == []

    extract_response = client.post(
        f"/api/v1/products/{product_id}/pipeline",
        json={"stages": ["extract"]},
    )
    assert extract_response.status_code == 200
    assert extract_response.json()["fields"]


def test_repeated_validation_does_not_duplicate_missing_field_reviews(client):
    product = client.post("/api/v1/products", json={"name": "Incomplete bearing"}).json()
    product_id = product["id"]
    client.post(
        f"/api/v1/products/{product_id}/sources/text",
        json={"text": "Bearing made by Borex.", "source_identifier": "snippet"},
    )
    client.post(f"/api/v1/products/{product_id}/pipeline", json={"stages": ["classify", "validate"]})
    client.post(f"/api/v1/products/{product_id}/pipeline", json={"stages": ["validate"]})

    reviews = client.get("/api/v1/reviews", params={"product_id": product_id}).json()
    keys = [(review["field_name"], review["reason"]) for review in reviews]
    assert len(keys) == len(set(keys))
