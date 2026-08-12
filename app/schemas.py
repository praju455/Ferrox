from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl


class SourceIn(BaseModel):
    source_type: Literal["pdf", "url", "text"]
    source_identifier: str
    raw_content: str | None = None


class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    sources: list[SourceIn] = Field(default_factory=list)


class ProductRead(BaseModel):
    id: str
    name: str
    category: str | None
    dynamic_schema: dict[str, Any] | None
    completeness_score: float
    confidence_score: float

    model_config = {"from_attributes": True}


class TextIngestionRequest(BaseModel):
    product_name: str = Field(min_length=1, max_length=255)
    text: str = Field(min_length=1)
    source_identifier: str = "manual-text"


class UrlIngestionRequest(BaseModel):
    product_name: str = Field(min_length=1, max_length=255)
    url: HttpUrl


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

    model_config = {"from_attributes": True}


class ProductDetail(ProductRead):
    fields: list[ExtractedFieldRead] = Field(default_factory=list)


class PipelineRunRequest(BaseModel):
    source_ids: list[str] | None = None
    stages: list[str] | None = None


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
