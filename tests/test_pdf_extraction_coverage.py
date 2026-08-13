import pymupdf

from app.core.config import Settings
from app.services.catalog_schemas import schema_for_category
from app.services.ingestion import IngestionService
from app.services.llm import LLMRequest, MockIndustrialProvider
from app.services.storage import StoredObject


class MemoryStorage:
    backend = "memory"

    def __init__(self):
        self.objects = {}

    def put_bytes(self, key, content, content_type):
        self.objects[key] = content
        return StoredObject(self.backend, key, content_type, len(content), "0" * 64)


def make_table_pdf() -> bytes:
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 45), "BOMBAS BOYSER")
    page.insert_text((72, 60), "Model: AMP-13B\nProduct type: Industrial peristaltic pump\nFlow rate: 0.038 L/rev\nMax pressure: 8 bar")
    xs = [72, 180, 280]
    ys = [145, 169, 193, 217]
    for x in xs:
        page.draw_line((x, ys[0]), (x, ys[-1]))
    for y in ys:
        page.draw_line((xs[0], y), (xs[-1], y))
    rows = [["Pressure", "Torque"], ["1 bar", "20 Nm"], ["8 bar", "30 Nm"]]
    for row_index, row in enumerate(rows):
        for column_index, value in enumerate(row):
            page.insert_text((xs[column_index] + 5, ys[row_index] + 16), value, fontsize=9)
    content = document.tobytes()
    document.close()
    return content


def test_pdf_ingestion_preserves_page_and_table_relationships():
    source = IngestionService(Settings(), MemoryStorage()).from_pdf_bytes("product-1", make_table_pdf(), "pump.pdf")

    assert "--- Page 1 ---" in source.raw_content
    assert "--- Page 1 Table 1 ---" in source.raw_content
    assert "Pressure | Torque" in source.raw_content
    assert "1 bar | 20 Nm" in source.raw_content
    assert source.extracted_metadata["tables"] == 1
    assert source.extracted_metadata["layout_preserved"] is True


def test_pump_schema_and_mock_extraction_cover_explicit_complex_fields():
    schema = schema_for_category("Industrial Pump")
    expected = {
        "product_type", "connections", "max_pressure", "rotor_system", "available_hoses",
        "available_tubes", "pressure_torque", "pump_housing_material", "front_cover_material",
        "rotor_material", "rollers_material", "base_plate_material",
    }
    assert expected.issubset(schema["properties"])

    prompt = """Category: Industrial Pump
BOMBAS BOYSER
Model: AMP-13B
Product type: Industrial peristaltic pump
Flow rate: 0.038 L/rev
Connections: 3/8 BSP
Max pressure: 8 bar
Rotor system: Rollers
Available hoses: NR, NBR, EPDM, HYPALON, NR-A, NBR-A
Available tubes: Norprene
Pump housing: Aluminium EN-AC-44100
Front cover: Methacrylate
Rotor: Nodular Cast Iron EN-GJL-400
Rollers: Steel F-114
Base plate: Steel F-111
Pressure | Torque
1 bar | 20 Nm
8 bar | 30 Nm
"""
    result = MockIndustrialProvider().complete_json(LLMRequest(task="extract", prompt=prompt, response_schema=schema))

    assert result["fields"]["manufacturer"]["value"] == "BOMBAS BOYSER"
    assert result["fields"]["product_type"]["value"] == "Industrial peristaltic pump"
    assert result["fields"]["flow_rate"]["unit"].lower() == "l/rev"
    assert result["fields"]["available_hoses"]["value"] == ["NR", "NBR", "EPDM", "HYPALON", "NR-A", "NBR-A"]
    assert result["fields"]["pressure_torque"]["value"][0]["pressure"] == {"value": "1", "unit": "bar"}
    assert result["fields"]["pressure_torque"]["value"][1]["torque"] == {"value": "30", "unit": "Nm"}


def test_boyser_layout_text_preserves_multiline_specs_and_header_units():
    schema = schema_for_category("Industrial Pump")
    prompt = """Category: Industrial Pump
--- Page 1 ---
AMP-13B
Industrial peristaltic pump
Capacity: 0,038 l/rev
Connections: 3/8 ”
Max. Pressure: 8 bar
Rotor system: Rollers
Available hoses: NR
NBR
EPDM
HYPALON
NR-A
NBR-A
Available tubes: Norprene
--- Page 1 Table 1 ---
Pressure (bar) | Torque (Nm)
1 | 20
4 | 23
6 | 26
8 | 30
--- Page 2 ---
Bombas Boyser, S.L.
--- Page 2 Table 1 ---
Description | Material | Surface treatment
Pump housing | Allumnium EN-AC-44100 | Polyester powder coated
Rotor | Nodular Cast Iron EN-GJL-400 | Cataphoresis
--- Page 2 Table 2 ---
A | B | C | D | E | F | G | H | J | K | L | M | Connections
202 | 210 | * | 39 | 52 | 107 | 141 | 238 | 187 | 30 | 160 | 30 | 3/8 BSP
"""
    fields = MockIndustrialProvider().complete_json(LLMRequest(task="extract", prompt=prompt, response_schema=schema))["fields"]

    assert fields["manufacturer"]["value"].lower() == "bombas boyser"
    assert fields["model"]["value"] == "AMP-13B"
    assert fields["product_type"]["value"] == "Industrial peristaltic pump"
    assert fields["flow_rate"]["value"] == "0.038"
    assert fields["max_pressure"]["value"] == "8"
    assert len(fields["pressure_torque"]["value"]) == 4
    assert fields["construction_details"]["value"][0]["component"] == "Pump housing"
    assert fields["dimensional_data"]["value"]["connections"] == "3/8 BSP"
