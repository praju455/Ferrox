from app.core.config import Settings
from app.services.catalog_import import CatalogCSVImporter
from app.services.chunking import DocumentChunker
from app.services.ingestion import IngestionService


def test_document_chunker_bounds_chunks_and_preserves_overlap():
    text = "\n\n".join(f"Section {index}: " + "x" * 90 for index in range(12))
    chunks = DocumentChunker(max_chars=300, overlap_chars=40).split(text)

    assert len(chunks) > 1
    assert all(len(chunk.text) <= 300 for chunk in chunks)
    assert all(chunk.start_char < chunk.end_char for chunk in chunks)
    assert chunks[1].start_char < chunks[0].end_char


def test_catalog_csv_importer_accepts_structured_columns_and_explicit_text():
    content = b"product_name,source_identifier,manufacturer,model,flow_rate\nPump One,datasheet,Acme,P-10,45 GPM\n"
    rows = CatalogCSVImporter(max_rows=10).parse(content, "catalog.csv")

    assert rows[0].product_name == "Pump One"
    assert rows[0].source_identifier == "datasheet"
    assert "Manufacturer: Acme" in rows[0].raw_content
    assert "Flow Rate: 45 GPM" in rows[0].raw_content


def test_catalog_csv_import_endpoint_queues_each_row(client):
    response = client.post(
        "/api/v1/imports/catalog",
        files={"file": ("catalog.csv", b"product_name,manufacturer,model\nPump One,Acme,P-10\nPump Two,Borex,P-20\n", "text/csv")},
    )

    assert response.status_code == 202
    body = response.json()
    assert body["imported_rows"] == 2
    assert body["total_items"] == 2
    assert all(item["status"] == "queued" for item in body["items"])


def test_page_text_uses_ocr_only_when_native_text_is_insufficient():
    class Page:
        def __init__(self):
            self.ocr_calls = 0

        def get_text(self, kind, **kwargs):
            return "OCR manufacturer Acme model P-10" if "textpage" in kwargs else ""

        def get_textpage_ocr(self, **kwargs):
            self.ocr_calls += 1
            assert kwargs == {"language": "eng", "dpi": 200, "full": True}
            return object()

    page = Page()
    ocr_pages = []
    failures = []
    text = IngestionService(Settings(_env_file=None))._extract_page_text(page, 1, ocr_pages, failures)

    assert text.startswith("OCR manufacturer")
    assert page.ocr_calls == 1
    assert ocr_pages == [1]
    assert failures == []


def test_page_text_records_ocr_runtime_failure():
    class Page:
        def get_text(self, kind, **kwargs):
            return ""

        def get_textpage_ocr(self, **kwargs):
            raise RuntimeError("Tesseract unavailable")

    failures = []
    text = IngestionService(Settings(_env_file=None))._extract_page_text(Page(), 3, [], failures)

    assert text == ""
    assert failures == [{"page": 3, "error": "Tesseract unavailable"}]
