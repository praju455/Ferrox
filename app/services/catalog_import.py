import csv
import io
from dataclasses import dataclass


@dataclass(frozen=True)
class CatalogRow:
    product_name: str
    source_identifier: str
    raw_content: str
    row_number: int


class CatalogCSVImporter:
    RESERVED_COLUMNS = {"product_name", "name", "source_identifier", "raw_content", "text"}

    def __init__(self, max_rows: int):
        self.max_rows = max_rows

    def parse(self, content: bytes, filename: str) -> list[CatalogRow]:
        try:
            decoded = content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValueError("Catalog CSV must be UTF-8 encoded") from exc
        try:
            dialect = csv.Sniffer().sniff(decoded[:8192], delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(io.StringIO(decoded), dialect=dialect)
        if not reader.fieldnames:
            raise ValueError("Catalog CSV requires a header row")
        headers = {self._header(name) for name in reader.fieldnames if name}
        if not headers.intersection({"product_name", "name"}):
            raise ValueError("Catalog CSV requires a product_name or name column")

        rows: list[CatalogRow] = []
        for row_number, raw_row in enumerate(reader, start=2):
            if len(rows) >= self.max_rows:
                raise ValueError(f"Catalog CSV exceeds the {self.max_rows} row limit")
            row = {self._header(key): (value or "").strip() for key, value in raw_row.items() if key}
            name = row.get("product_name") or row.get("name") or ""
            if not name:
                continue
            identifier = row.get("source_identifier") or f"{filename}:row-{row_number}"
            explicit_text = row.get("raw_content") or row.get("text")
            details = [f"{key.replace('_', ' ').title()}: {value}" for key, value in row.items() if key not in self.RESERVED_COLUMNS and value]
            raw_content = explicit_text or "\n".join(details)
            if not raw_content:
                raise ValueError(f"Catalog row {row_number} has no source attributes")
            rows.append(CatalogRow(name, identifier, raw_content, row_number))
        if not rows:
            raise ValueError("Catalog CSV contains no importable product rows")
        return rows

    @staticmethod
    def _header(value: str) -> str:
        return "_".join(value.strip().lower().replace("-", " ").split())
