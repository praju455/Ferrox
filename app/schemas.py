from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl, model_validator


class SourceIn(BaseModel):
    source_type: Literal["pdf", "url", "text"]
    source_identifier: str = Field(min_length=1, max_length=500)
    raw_content: str | None = None
    url: HttpUrl | None = None
    content_base64: str | None = None

    @model_validator(mode="after")
    def validate_source_payload(self) -> "SourceIn":
        if self.source_type == "text" and not self.raw_content:
            raise ValueError("Text sources require raw_content")
        if self.source_type == "url" and self.url is None:
            raise ValueError("URL sources require url")
        if self.source_type == "pdf" and not self.content_base64:
            raise ValueError("PDF sources require content_base64")
        return self


class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    sources: list[SourceIn] = Field(default_factory=list)


class ProductCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class ProductRead(BaseModel):
    id: str
    name: str
    category: str | None
    dynamic_schema: dict[str, Any] | None
    completeness_score: float
    confidence_score: float
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TextIngestionRequest(BaseModel):
    product_name: str = Field(min_length=1, max_length=255)
    text: str = Field(min_length=1)
    source_identifier: str = "manual-text"


class UrlIngestionRequest(BaseModel):
    product_name: str = Field(min_length=1, max_length=255)
    url: HttpUrl


class TextSourceCreate(BaseModel):
    text: str = Field(min_length=1)
    source_identifier: str = Field(default="manual-text", min_length=1, max_length=500)


class UrlSourceCreate(BaseModel):
    url: HttpUrl


class SourceRead(BaseModel):
    id: str
    product_id: str
    source_type: str
    source_identifier: str
    raw_content: str
    extracted_metadata: dict[str, Any] | None
    storage_backend: str | None
    storage_key: str | None
    content_type: str | None
    content_length: int | None
    content_sha256: str | None
    authority_rank: int
    created_at: datetime

    model_config = {"from_attributes": True}


class ExtractedFieldRead(BaseModel):
    field_name: str
    value: Any
    unit: str | None
    confidence: float
    source_id: str | None
    status: str
    evidence: str | None
    alternatives: list[dict[str, Any]] | None
    validation: dict[str, Any] | None
    citations: list["CitationRead"] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class ProductDetail(ProductRead):
    sources: list[SourceRead] = Field(default_factory=list)
    fields: list[ExtractedFieldRead] = Field(default_factory=list)
    citations: list["CitationRead"] = Field(default_factory=list)


class CitationRead(BaseModel):
    id: str
    product_id: str
    extracted_field_id: str
    url: str
    title: str | None
    cited_text: str | None
    provider: str
    retrieved_at: datetime

    model_config = {"from_attributes": True}


class LLMRunRead(BaseModel):
    id: str
    product_id: str | None
    provider: str
    model: str
    task: str
    status: str
    latency_ms: int
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float
    error: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int


class UserCreateRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=12, max_length=128)
    full_name: str = Field(min_length=1, max_length=255)
    role: Literal["reviewer", "admin"] = "reviewer"


class UserUpdateRequest(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    password: str | None = Field(default=None, min_length=12, max_length=128)
    role: Literal["reviewer", "admin"] | None = None
    is_active: bool | None = None


class UserRead(BaseModel):
    id: str
    email: str
    full_name: str
    role: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None

    model_config = {"from_attributes": True}


class PipelineRunRequest(BaseModel):
    source_ids: list[str] | None = None
    stages: list[Literal["classify", "extract", "reconcile", "validate", "enrich", "score"]] | None = None


class PipelineJobRead(BaseModel):
    id: str
    product_id: str
    status: str
    source_ids: list[str] | None
    stages: list[str] | None
    error: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class BatchCreateRequest(BaseModel):
    items: list[ProductCreate]


class BatchRead(BaseModel):
    id: str
    status: str
    total_items: int
    processed_items: int
    failed_items: int

    model_config = {"from_attributes": True}


class BatchItemRead(BaseModel):
    id: str
    batch_id: str
    product_id: str | None
    status: str
    error: str | None
    payload: dict[str, Any]

    model_config = {"from_attributes": True}


class BatchDetail(BatchRead):
    items: list[BatchItemRead] = Field(default_factory=list)


class BatchProcessRequest(BaseModel):
    include_failed: bool = True


class ReviewItemRead(BaseModel):
    id: str
    product_id: str
    field_name: str | None
    reason: str
    severity: str
    status: str
    payload: dict[str, Any] | None

    model_config = {"from_attributes": True}


class ReviewItemUpdate(BaseModel):
    status: Literal["open", "resolved", "dismissed"] | None = None
    severity: Literal["low", "medium", "high"] | None = None
    reason: str | None = Field(default=None, min_length=1)
    payload: dict[str, Any] | None = None


class FieldCorrectionRequest(BaseModel):
    value: Any | None = None
    unit: str | None = None
    confidence: float = Field(default=1.0, ge=0, le=1)
    evidence: str | None = None
    resolve_reviews: bool = True
