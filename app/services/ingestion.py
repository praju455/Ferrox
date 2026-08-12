import ipaddress
import socket
from urllib.parse import urlparse

import fitz
import requests
from bs4 import BeautifulSoup

from app.core.config import Settings
from app.models import Source, SourceType
from app.services.storage import ObjectStorage, source_object_key


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
        with fitz.open(stream=content, filetype="pdf") as doc:
            for page in doc:
                chunks.append(page.get_text("text"))
        if self.storage is None:
            raise RuntimeError("PDF ingestion requires object storage")
        stored = self.storage.put_bytes(source_object_key(product_id, filename), content, "application/pdf")
        source = self._source(
            product_id,
            SourceType.pdf,
            filename,
            "\n".join(chunks),
            {"parser": "pymupdf", "pages": len(chunks)},
        )
        source.storage_backend = stored.backend
        source.storage_key = stored.key
        source.content_type = stored.content_type
        source.content_length = stored.content_length
        source.content_sha256 = stored.sha256
        return source

    def _source(self, product_id: str, source_type: SourceType, identifier: str, text: str, metadata: dict) -> Source:
        return Source(
            product_id=product_id,
            source_type=source_type,
            source_identifier=identifier,
            raw_content=text[: self.settings.max_source_chars],
            extracted_metadata=metadata,
            authority_rank=authority_rank(source_type),
        )
