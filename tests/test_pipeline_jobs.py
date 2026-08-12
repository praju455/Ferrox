from app.models import PipelineJob
from app.services.jobs import process_next_pipeline_job


def create_product_with_source(client):
    product = client.post("/api/v1/products", json={"name": "VoltEdge VM-10"}).json()
    client.post(
        f"/api/v1/products/{product['id']}/sources/text",
        json={
            "text": "Manufacturer: VoltEdge. Model VM-10 motor. 10 HP. 230 V. 1750 RPM. TEFC.",
            "source_identifier": "datasheet",
        },
    )
    return product


def test_pipeline_job_lifecycle(client):
    product = create_product_with_source(client)

    create_response = client.post(
        f"/api/v1/products/{product['id']}/pipeline/jobs",
        json={"stages": ["classify", "extract", "validate", "score"]},
    )
    assert create_response.status_code == 202
    job = create_response.json()
    assert job["status"] == "queued"

    process_response = client.post(f"/api/v1/pipeline/jobs/{job['id']}/process")
    assert process_response.status_code == 200
    assert process_response.json()["status"] == "completed"
    assert process_response.json()["started_at"] is not None
    assert process_response.json()["completed_at"] is not None

    product_response = client.get(f"/api/v1/products/{product['id']}")
    assert product_response.json()["category"] == "Electric Motor"
    assert product_response.json()["fields"]

    second_process = client.post(f"/api/v1/pipeline/jobs/{job['id']}/process")
    assert second_process.status_code == 409


def test_pipeline_jobs_can_be_listed_and_read(client):
    product = create_product_with_source(client)
    job = client.post(f"/api/v1/products/{product['id']}/pipeline/jobs", json={}).json()

    list_response = client.get(
        "/api/v1/pipeline/jobs",
        params={"product_id": product["id"], "status": "queued"},
    )
    assert list_response.status_code == 200
    assert [item["id"] for item in list_response.json()] == [job["id"]]

    detail_response = client.get(f"/api/v1/pipeline/jobs/{job['id']}")
    assert detail_response.status_code == 200
    assert detail_response.json()["product_id"] == product["id"]


def test_worker_claims_oldest_queued_job(db_session):
    from app.models import Product, Source, SourceType

    product = Product(name="Worker pump")
    db_session.add(product)
    db_session.flush()
    db_session.add(
        Source(
            product_id=product.id,
            source_type=SourceType.text,
            source_identifier="worker-test",
            raw_content="Manufacturer: Aurora. Model P-1 pump. Flow rate 50 GPM. Head 30 ft. 2 HP.",
            authority_rank=2,
        )
    )
    job = PipelineJob(product_id=product.id, stages=["classify"])
    db_session.add(job)
    db_session.commit()

    processed = process_next_pipeline_job(db_session)

    assert processed is not None
    assert processed.id == job.id
    assert processed.status == "completed"
    assert product.category == "Industrial Pump"
