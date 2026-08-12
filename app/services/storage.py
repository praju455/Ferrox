import hashlib
import mimetypes
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Protocol

from app.core.config import Settings


@dataclass(frozen=True)
class StoredObject:
    backend: str
    key: str
    content_type: str
    content_length: int
    sha256: str


class ObjectStorage(Protocol):
    backend: str

    def put_bytes(self, key: str, content: bytes, content_type: str) -> StoredObject: ...

    def open(self, key: str) -> BinaryIO: ...

    def delete(self, key: str) -> None: ...

    def presigned_get_url(self, key: str, expires_seconds: int = 900) -> str | None: ...


def source_object_key(product_id: str, filename: str) -> str:
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "-", Path(filename).name).strip("-.") or "source.pdf"
    return f"products/{product_id}/sources/{uuid.uuid4()}-{safe_name}"


class LocalObjectStorage:
    backend = "local"

    def __init__(self, root: str):
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if self.root not in path.parents:
            raise ValueError("Invalid object key")
        return path

    def put_bytes(self, key: str, content: bytes, content_type: str) -> StoredObject:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return StoredObject(
            backend=self.backend,
            key=key,
            content_type=content_type,
            content_length=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
        )

    def open(self, key: str) -> BinaryIO:
        return self._path(key).open("rb")

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def presigned_get_url(self, key: str, expires_seconds: int = 900) -> str | None:
        return None


class S3ObjectStorage:
    backend = "s3"

    def __init__(self, settings: Settings):
        import boto3
        from botocore.config import Config

        self.bucket = settings.s3_bucket
        kwargs = {
            "service_name": "s3",
            "region_name": settings.s3_region,
            "endpoint_url": settings.s3_endpoint_url,
            "config": Config(s3={"addressing_style": "path" if settings.s3_force_path_style else "auto"}),
        }
        if settings.s3_access_key_id:
            kwargs["aws_access_key_id"] = settings.s3_access_key_id
        if settings.s3_secret_access_key:
            kwargs["aws_secret_access_key"] = settings.s3_secret_access_key
        self.client = boto3.client(**kwargs)
        self.encryption = settings.s3_server_side_encryption

    def put_bytes(self, key: str, content: bytes, content_type: str) -> StoredObject:
        sha256 = hashlib.sha256(content).hexdigest()
        request = {
            "Bucket": self.bucket,
            "Key": key,
            "Body": content,
            "ContentType": content_type,
            "Metadata": {"sha256": sha256},
        }
        if self.encryption:
            request["ServerSideEncryption"] = self.encryption
        self.client.put_object(**request)
        return StoredObject(self.backend, key, content_type, len(content), sha256)

    def open(self, key: str) -> BinaryIO:
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"]

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def presigned_get_url(self, key: str, expires_seconds: int = 900) -> str:
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=expires_seconds,
        )


def build_object_storage(settings: Settings) -> ObjectStorage:
    backend = settings.object_storage_backend.lower()
    if backend == "local":
        return LocalObjectStorage(settings.local_storage_path)
    if backend == "s3":
        return S3ObjectStorage(settings)
    raise ValueError(f"Unsupported object storage backend: {settings.object_storage_backend}")


def guess_content_type(filename: str) -> str:
    return mimetypes.guess_type(filename)[0] or "application/octet-stream"
