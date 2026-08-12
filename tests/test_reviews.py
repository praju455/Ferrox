from app.models import Product, ReviewItem


def test_review_list_detail_and_update(client, db_session):
    product = Product(name="Reviewable pump")
    db_session.add(product)
    db_session.flush()
    review = ReviewItem(product_id=product.id, field_name="flow_rate", reason="Conflict detected", severity="high")
    db_session.add(review)
    db_session.commit()

    list_response = client.get("/api/v1/reviews", params={"status": "open", "severity": "high", "product_id": product.id})
    assert list_response.status_code == 200
    assert list_response.json()[0]["id"] == review.id

    detail_response = client.get(f"/api/v1/reviews/{review.id}")
    assert detail_response.status_code == 200
    assert detail_response.json()["reason"] == "Conflict detected"

    update_response = client.patch(f"/api/v1/reviews/{review.id}", json={"status": "dismissed", "reason": "Not relevant"})
    assert update_response.status_code == 200
    assert update_response.json()["status"] == "dismissed"
    assert update_response.json()["reason"] == "Not relevant"


def test_field_correction_resolves_open_field_reviews(client, db_session):
    ingest_response = client.post(
        "/api/v1/products/ingest/text",
        json={
            "product_name": "Incomplete bearing",
            "text": "Bearing with manufacturer Borex only.",
            "source_identifier": "snippet",
        },
    )
    product_id = ingest_response.json()["id"]
    pipeline_response = client.post(f"/api/v1/products/{product_id}/pipeline", json={})
    assert pipeline_response.status_code == 200

    reviews_response = client.get("/api/v1/reviews", params={"product_id": product_id, "status": "open"})
    open_reviews = reviews_response.json()
    assert open_reviews
    field_name = open_reviews[0]["field_name"]

    correction_response = client.patch(
        f"/api/v1/products/{product_id}/fields/{field_name}",
        json={"value": "Corrected value", "unit": None, "confidence": 0.99, "evidence": "Reviewer supplied value"},
    )
    assert correction_response.status_code == 200
    corrected = correction_response.json()
    assert corrected["field_name"] == field_name
    assert corrected["value"] == "Corrected value"
    assert corrected["status"] == "validated"

    resolved_response = client.get("/api/v1/reviews", params={"product_id": product_id, "status": "open"})
    assert all(item["field_name"] != field_name for item in resolved_response.json())
