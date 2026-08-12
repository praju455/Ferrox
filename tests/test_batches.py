import base64

import fitz

from app.models import BatchItem, BatchJob, Product
from app.models import SourceType
from app.services.ingestion import IngestionService


def test_batch_list_detail_and_item_payloads(client):
    response = client.post(
        "/api/v1/batches",
        json={
            "items": [
                {
                    "name": "ClearFlow Pump CFP-44",
                    "sources": [
                        {
                            "source_type": "text",
                            "source_identifier": "datasheet",
                            "raw_content": "Manufacturer: ClearFlow. Model: CFP-44. Flow rate 44 GPM. 28 ft head. 1 HP.",
                        }
                    ],
                }
            ]
        },
    )
    assert response.status_code == 202
    batch_id = response.json()["id"]
    assert response.json()["status"] == "queued"

    process_response = client.post(f"/api/v1/batches/{batch_id}/process")
    assert process_response.status_code == 200

    list_response = client.get("/api/v1/batches", params={"status": "completed"})
    assert list_response.status_code == 200
    assert any(batch["id"] == batch_id for batch in list_response.json())

    detail_response = client.get(f"/api/v1/batches/{batch_id}")
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["processed_items"] == 1
    assert detail["items"][0]["status"] == "processed"
    assert detail["items"][0]["payload"]["name"] == "ClearFlow Pump CFP-44"


def test_batch_process_retries_failed_items(client, db_session):
    product = Product(name="Retry pump")
    db_session.add(product)
    db_session.flush()
    batch = BatchJob(status="completed_with_errors", total_items=1, processed_items=0, failed_items=1)
    db_session.add(batch)
    db_session.flush()
    item = BatchItem(
        batch_id=batch.id,
        product_id=product.id,
        status="failed",
        error="temporary failure",
        payload={"name": "Retry pump", "sources": []},
    )
    db_session.add(item)
    db_session.commit()

    response = client.post(f"/api/v1/batches/{batch.id}/process", json={"include_failed": True})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["processed_items"] == 1
    assert body["failed_items"] == 0
    assert body["items"][0]["error"] is None


def test_async_batch_ingests_url_and_durable_pdf(client, monkeypatch):
    def fake_from_url(self, product_id, url):
        return self._source(
            product_id,
            SourceType.url,
            url,
            "ClearFlow CFP-44 pump supplier page with 42 GPM flow.",
            {"parser": "test"},
        )

    monkeypatch.setattr(IngestionService, "from_url", fake_from_url)
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "ClearFlow CFP-44 datasheet. Flow 44 GPM. Head 28 ft. 1 HP.")
    pdf_bytes = document.tobytes()
    document.close()

    response = client.post(
        "/api/v1/batches",
        json={
            "items": [
                {
                    "name": "ClearFlow CFP-44",
                    "sources": [
                        {
                            "source_type": "url",
                            "source_identifier": "supplier-page",
                            "url": "https://example.com/cfp-44",
                        },
                        {
                            "source_type": "pdf",
                            "source_identifier": "CFP-44.pdf",
                            "content_base64": base64.b64encode(pdf_bytes).decode("ascii"),
                        },
                    ],
                }
            ]
        },
    )
    assert response.status_code == 202
    batch_id = response.json()["id"]

    processed = client.post(f"/api/v1/batches/{batch_id}/process")
    assert processed.status_code == 200
    assert processed.json()["status"] == "completed"
    product_id = processed.json()["items"][0]["product_id"]

    sources = client.get(f"/api/v1/products/{product_id}/sources").json()
    assert {source["source_type"] for source in sources} == {"url", "pdf"}
    pdf_source = next(source for source in sources if source["source_type"] == "pdf")
    assert pdf_source["storage_backend"] == "local"
    assert pdf_source["content_length"] == len(pdf_bytes)
    assert len(pdf_source["content_sha256"]) == 64
    batch_detail = client.get(f"/api/v1/batches/{batch_id}").json()
    pdf_payload = next(source for source in batch_detail["items"][0]["payload"]["sources"] if source["source_type"] == "pdf")
    assert "content_base64" not in pdf_payload
    assert pdf_payload["stored"] is True

    download = client.get(f"/api/v1/products/{product_id}/sources/{pdf_source['id']}/content")
    assert download.status_code == 200
    assert download.content == pdf_bytes
