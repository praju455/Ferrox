from app.models import ExtractedField, FieldStatus, LLMRun, Product, ReviewItem
from app.services.analytics import CatalogAnalyticsService


def seed_analytics_data(db_session):
    product = Product(
        name="Acme Pump P-10",
        category="Industrial Pump",
        completeness_score=0.75,
        confidence_score=0.82,
    )
    db_session.add(product)
    db_session.flush()
    db_session.add(ExtractedField(
        product_id=product.id,
        field_name="flow_rate",
        value=120,
        unit="GPM",
        confidence=0.82,
        status=FieldStatus.validated,
        validation={"valid": True, "rule_issues": []},
    ))
    db_session.add(ReviewItem(
        product_id=product.id,
        field_name="head",
        reason="Required field is missing",
        severity="high",
        status="open",
    ))
    db_session.add(LLMRun(
        product_id=product.id,
        provider="gemini",
        model="gemini-test",
        task="extract",
        status="success",
        latency_ms=125,
        input_tokens=100,
        output_tokens=20,
        estimated_cost_usd=0.001,
    ))
    db_session.commit()


def test_catalog_analytics_summarizes_quality_and_provider_runs(db_session):
    seed_analytics_data(db_session)

    report = CatalogAnalyticsService(db_session).report()

    assert report["totals"]["products"] == 1
    assert report["totals"]["open_reviews"] == 1
    assert report["quality"]["average_completeness"] == 0.75
    assert report["quality"]["validation_pass_rate"] == 1.0
    assert report["categories"] == [{"label": "Industrial Pump", "count": 1}]
    assert report["providers"][0]["success_rate"] == 1.0
    assert report["providers"][0]["tokens"] == 120


def test_catalog_analytics_api_and_csv_export(client, db_session):
    seed_analytics_data(db_session)

    response = client.get("/api/v1/analytics/catalog")
    export = client.get("/api/v1/analytics/catalog.csv")

    assert response.status_code == 200
    assert response.json()["totals"]["products"] == 1
    assert export.status_code == 200
    assert export.headers["content-type"].startswith("text/csv")
    assert "quality,average_completeness,0.75" in export.text
