from io import BytesIO

from openpyxl import Workbook

from app.services.xlsx_import import MultiSheetXLSXParser, XLSXCatalogImporter


def workbook_bytes() -> bytes:
    workbook = Workbook()
    source = workbook.active
    source.title = "Input"
    source.append(["Supplier catalog export"])
    source.append(["Mfg Part Num", "Part Desc", "E1 Brand", "Unused"])
    source.append(["AMP-13B", "Industrial peristaltic pump", "Bombas Boyser", "-"])
    source.append(["F-100", "Stainless fitting", "Acme", "N/A"])
    delivery = workbook.create_sheet("Delivery Format")
    delivery.append(["Manufacturer Part Number", "Product Title", "Invoice Description"])
    delivery.append(["AMP-13B", "BOYSER AMP-13B PUMP", "BOYSER PUMP"])
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def test_parser_preserves_multiple_sheets_headers_and_lineage():
    parsed = MultiSheetXLSXParser(max_rows=20).parse(workbook_bytes(), "sample.xlsx")

    assert [sheet.name for sheet in parsed.sheets] == ["Input", "Delivery Format"]
    assert parsed.sheets[0].header_row == 2
    assert parsed.sheets[0].original_columns["mfg_part_num"] == "Mfg Part Num"
    assert parsed.sheets[0].rows[0].row_number == 3
    assert "unused" not in parsed.sheets[0].rows[0].values
    assert parsed.content_sha256


def test_catalog_importer_uses_all_input_sheets_but_skips_delivery_output():
    rows = XLSXCatalogImporter(max_rows=20).parse(workbook_bytes(), "sample.xlsx")

    assert len(rows) == 2
    assert rows[0].product_name == "Bombas Boyser AMP-13B Industrial peristaltic pump"
    assert rows[0].source_identifier == "sample.xlsx:Input:row-3"
    assert "Mfg Part Num: AMP-13B" in rows[0].raw_content


def test_catalog_importer_can_select_one_named_sheet():
    rows = XLSXCatalogImporter(max_rows=20).parse(workbook_bytes(), "sample.xlsx", "Delivery Format")

    assert len(rows) == 1
    assert "BOYSER AMP-13B PUMP" in rows[0].raw_content
