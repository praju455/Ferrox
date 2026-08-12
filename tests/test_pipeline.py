from app.models import Product
from app.services.ingestion import IngestionService
from app.services.pipeline import ProductPipeline
from app.core.config import get_settings


def test_pipeline_extracts_and_reconciles_conflicting_sources(db_session):
    product = Product(name="Aurora End-Suction Pump AXP-200")
    db_session.add(product)
    db_session.flush()
    ingestion = IngestionService(get_settings())
    db_session.add(ingestion.from_text(product.id, "Manufacturer: Aurora. Model: AXP-200. Flow rate 120 GPM. 50 ft head. 5 HP. Material cast iron.", "datasheet"))
    db_session.add(ingestion.from_text(product.id, "Aurora AXP-200 pump marketing page says flow rate 110 GPM and 5 HP.", "web"))
    db_session.commit()

    ProductPipeline(db_session).run(product)

    assert product.category == "Industrial Pump"
    assert product.dynamic_schema["required"]
    assert product.completeness_score > 0
    flow = next(field for field in product.fields if field.field_name == "flow_rate")
    assert flow.status in {"conflict_resolved", "validated"}
    assert flow.value == "120"


def test_low_confidence_missing_values_create_review_items(db_session):
    product = Product(name="Incomplete bearing")
    db_session.add(product)
    db_session.flush()
    db_session.add(IngestionService(get_settings()).from_text(product.id, "Bearing with manufacturer Borex only.", "snippet"))
    db_session.commit()

    ProductPipeline(db_session).run(product)

    assert product.reviews
