import ipaddress
import logging
import socket
from urllib.parse import urlparse

import pymupdf
import requests
from bs4 import BeautifulSoup

from app.core.config import Settings
from app.models import Source, SourceType
from app.services.storage import ObjectStorage, source_object_key


logger = logging.getLogger("ferrox.ingestion")


def authority_rank(source_type: SourceType) -> int:
    return {SourceType.pdf: 1, SourceType.text: 2, SourceType.url: 3}[source_type]


class IngestionService:
    def __init__(self, settings: Settings, storage: ObjectStorage | None = None):
        self.settings = settings
        self.storage = storage

    def from_text(self, product_id: str, text: str, identifier: str) -> Source:
        return self._source(product_id, SourceType.text, identifier, text, {"parser": "plain-text"})

    def from_url(self, product_id: str, url: str) -> Source:
        self._validate_public_url(url)
        response = requests.get(
            url,
            timeout=self.settings.scraper_timeout_seconds,
            headers={"User-Agent": "FerroxBot/0.1"},
        )
        response.raise_for_status()
        self._validate_public_url(response.url)
        soup = BeautifulSoup(response.text, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        text = " ".join(soup.get_text(separator=" ").split())
        return self._source(product_id, SourceType.url, url, text, {"parser": "requests+beautifulsoup"})

    @staticmethod
    def _validate_public_url(url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("Only public HTTP and HTTPS URLs are supported")
        hostname = parsed.hostname.lower()
        if hostname == "localhost" or hostname.endswith(".localhost") or hostname.endswith(".local"):
            raise ValueError("Private network URLs are not supported")
        try:
            addresses = {item[4][0] for item in socket.getaddrinfo(hostname, parsed.port or 443)}
        except socket.gaierror as exc:
            raise ValueError("Source URL hostname could not be resolved") from exc
        for address in addresses:
            ip = ipaddress.ip_address(address)
            if not ip.is_global:
                raise ValueError("Private network URLs are not supported")

    def from_pdf_bytes(self, product_id: str, content: bytes, filename: str) -> Source:
        if len(content) > self.settings.max_pdf_upload_bytes:
            raise ValueError("PDF upload is too large")
        if not content.startswith(b"%PDF"):
            raise ValueError("Uploaded content is not a valid PDF")
        chunks: list[str] = []
        table_count = 0
        ocr_pages: list[int] = []
        ocr_failures: list[dict[str, str | int]] = []
        has_text = False
        with pymupdf.open(stream=content, filetype="pdf") as doc:
            for page_number, page in enumerate(doc, start=1):
                page_text = self._extract_page_text(page, page_number, ocr_pages, ocr_failures)
                has_text = has_text or bool(page_text)
                page_parts = [f"--- Page {page_number} ---", page_text]
                try:
                    tables = page.find_tables()
                    for table_number, table in enumerate(tables.tables, start=1):
                        rows = table.extract()
                        if not rows:
                            continue
                        table_count += 1
                        page_parts.append(f"--- Page {page_number} Table {table_number} ---")
                        page_parts.extend(self._format_table_row(row) for row in rows)
                except Exception:
                    logger.warning("PDF table detection failed on page %s", page_number, exc_info=True)
                chunks.append("\n".join(part for part in page_parts if part))
        if not has_text:
            if ocr_failures:
                raise ValueError("PDF contains no extractable text and OCR is unavailable or failed")
            raise ValueError("PDF contains no extractable text")
        if self.storage is None:
            raise RuntimeError("PDF ingestion requires object storage")
        stored = self.storage.put_bytes(source_object_key(product_id, filename), content, "application/pdf")
        source = self._source(
            product_id,
            SourceType.pdf,
            filename,
            "\n".join(chunks),
            {
                "parser": "pymupdf",
                "pages": len(chunks),
                "tables": table_count,
                "layout_preserved": True,
                "ocr_pages": ocr_pages,
                "ocr_failures": ocr_failures,
            },
        )
        source.storage_backend = stored.backend
        source.storage_key = stored.key
        source.content_type = stored.content_type
        source.content_length = stored.content_length
        source.content_sha256 = stored.sha256
        return source

    def _extract_page_text(
        self,
        page,
        page_number: int,
        ocr_pages: list[int],
        ocr_failures: list[dict[str, str | int]],
    ) -> str:
        page_text = page.get_text("text", sort=True).strip()
        if not self.settings.enable_pdf_ocr or len(page_text) >= self.settings.pdf_ocr_min_text_chars:
            return page_text
        try:
            textpage = page.get_textpage_ocr(
                language=self.settings.pdf_ocr_language,
                dpi=self.settings.pdf_ocr_dpi,
                full=True,
            )
            ocr_text = page.get_text("text", textpage=textpage, sort=True).strip()
            if len(ocr_text) > len(page_text):
                ocr_pages.append(page_number)
                return ocr_text
        except Exception as exc:
            logger.warning("PDF OCR failed on page %s", page_number, exc_info=True)
            ocr_failures.append({"page": page_number, "error": str(exc)[:300]})
        return page_text

    @staticmethod
    def _format_table_row(row: list[str | None]) -> str:
        cells = [
            "; ".join(" ".join(line.split()) for line in (cell or "").splitlines() if line.strip())
            for cell in row
        ]
        return " | ".join(cells)

    def _source(self, product_id: str, source_type: SourceType, identifier: str, text: str, metadata: dict) -> Source:
        return Source(
            product_id=product_id,
            source_type=source_type,
            source_identifier=identifier,
            raw_content=text[: self.settings.max_source_chars],
            extracted_metadata=metadata,
            authority_rank=authority_rank(source_type),
        )
