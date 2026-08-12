def test_ingest_text_and_run_pipeline(client):
    response = client.post(
        "/api/v1/products/ingest/text",
        json={
            "product_name": "VoltEdge Motor VM-10",
            "text": "Manufacturer: VoltEdge. Model: VM-10 motor. 10 HP. 230 V. 3 phase. 1750 RPM. TEFC.",
            "source_identifier": "manual",
        },
    )
    assert response.status_code == 200
    product_id = response.json()["id"]

    pipeline_response = client.post(f"/api/v1/products/{product_id}/pipeline", json={})
    assert pipeline_response.status_code == 200
    body = pipeline_response.json()
    assert body["category"] == "Electric Motor"
    assert any(field["field_name"] == "power_rating" for field in body["fields"])


def test_batch_processing_contract(client):
    response = client.post(
        "/api/v1/batches",
        json={
            "items": [
                {
                    "name": "ForgeMax Hex Bolt HX-050",
                    "sources": [
                        {
                            "source_type": "text",
                            "source_identifier": "catalog",
                            "raw_content": "Manufacturer: ForgeMax. Part number HX-050 bolt. Diameter: 1/2 in. Length: 2 in. Thread: 13 UNC. Material zinc plated steel. Grade 5.",
                        }
                    ],
                }
            ]
        },
    )
    assert response.status_code == 200
    assert response.json()["processed_items"] == 1
