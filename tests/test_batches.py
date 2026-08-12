from app.models import BatchItem, BatchJob, Product


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
    assert response.status_code == 200
    batch_id = response.json()["id"]

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
