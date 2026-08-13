import pytest

from app.models import ExtractedField, Product
from app.services.reconciliation import WeightedVotingReconciler
from app.services.units import UnitNormalizer
from app.services.validation import EngineeringValidator


def test_unit_normalizer_converts_common_industrial_units():
    normalizer = UnitNormalizer()

    flow = normalizer.normalize("flow_rate", "120", "GPM")
    power = normalizer.normalize("power_rating", "5", "HP")
    diameter = normalizer.normalize("diameter", "2", "in")

    assert flow is not None and flow.unit == "L/min" and flow.value == pytest.approx(454.249414, rel=1e-6)
    assert power is not None and power.unit == "kW" and power.value == pytest.approx(3.7285, rel=1e-4)
    assert diameter is not None and diameter.unit == "mm" and diameter.value == pytest.approx(50.8)


def test_weighted_voting_counts_independent_sources_not_repeated_chunks():
    candidates = [
        {"value": "120", "unit": "GPM", "source_id": "pdf", "authority_rank": 1, "confidence": 0.9, "chunk_identifier": "chunk-1"},
        {"value": "120", "unit": "GPM", "source_id": "pdf", "authority_rank": 1, "confidence": 0.88, "chunk_identifier": "chunk-2"},
        {"value": "454.249414", "unit": "L/min", "source_id": "catalog", "authority_rank": 2, "confidence": 0.8},
        {"value": "110", "unit": "GPM", "source_id": "web", "authority_rank": 3, "confidence": 0.95},
    ]

    decision = WeightedVotingReconciler().reconcile("flow_rate", candidates)

    assert decision is not None
    assert decision.source_id == "pdf"
    winning_group = decision.audit["groups"][0]
    assert winning_group["source_count"] == 2
    assert winning_group["candidate_count"] == 3
    assert decision.audit["method"] == "weighted_source_vote"


def test_engineering_validator_normalizes_and_flags_invalid_ranges():
    validator = EngineeringValidator()
    valid = ExtractedField(product_id="p", field_name="max_pressure", value="116.03", unit="psi", confidence=0.9)
    excessive = ExtractedField(product_id="p", field_name="max_pressure", value="6000", unit="bar", confidence=0.9)

    normalized = validator.validate_field("Industrial Pump", valid)
    rejected = validator.validate_field("Industrial Pump", excessive)

    assert normalized.issues == []
    assert normalized.unit == "bar"
    assert normalized.value == pytest.approx(8.0, rel=1e-3)
    assert "value_above_engineering_limit" in rejected.issues


def test_engineering_validator_checks_bearing_geometry():
    product = Product(id="p", name="Invalid bearing", category="Bearing")
    product.fields = [
        ExtractedField(product_id="p", field_name="bore_diameter", value="50", unit="mm", confidence=0.9),
        ExtractedField(product_id="p", field_name="outside_diameter", value="40", unit="mm", confidence=0.9),
    ]

    issues = EngineeringValidator().cross_field_issues(product)

    assert issues == {"outside_diameter": ["outside_diameter_must_exceed_bore"]}
