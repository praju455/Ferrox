def test_pipeline_records_llm_attempts_and_exposes_prometheus_metrics(client):
    product = client.post(
        "/api/v1/products/ingest/text",
        json={
            "product_name": "VoltEdge VM-10",
            "text": "VoltEdge VM-10 motor. 10 HP. 230 V. 1750 RPM.",
            "source_identifier": "catalog",
        },
    ).json()
    pipeline = client.post(
        f"/api/v1/products/{product['id']}/pipeline",
        json={"stages": ["classify"]},
    )
    assert pipeline.status_code == 200

    runs = client.get("/api/v1/observability/llm-runs", params={"product_id": product["id"]})
    assert runs.status_code == 200
    assert any(run["provider"] == "mock" and run["status"] == "success" for run in runs.json())
    assert any(run["provider"] == "gemini" and run["status"] == "error" for run in runs.json())

    metrics = client.get("/api/v1/metrics")
    assert metrics.status_code == 200
    assert "ferrox_llm_calls_total" in metrics.text
    assert "ferrox_http_requests_total" in metrics.text
