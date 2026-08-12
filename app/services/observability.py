from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import LLMRun


try:
    from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

    def metrics_payload() -> bytes:
        return generate_latest()

    METRICS_CONTENT_TYPE = CONTENT_TYPE_LATEST
except ImportError:
    _fallback_metrics: dict[str, float] = {}

    class _FallbackMetric:
        def __init__(self, name: str, description: str, labels: list[str]):
            self.name = name
            _fallback_metrics.setdefault(name, 0.0)

        def labels(self, *values: str) -> "_FallbackMetric":
            return self

        def inc(self, amount: float = 1.0) -> None:
            _fallback_metrics[self.name] += amount

        def observe(self, value: float) -> None:
            _fallback_metrics[self.name] += value

    Counter = Histogram = _FallbackMetric
    METRICS_CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"

    def metrics_payload() -> bytes:
        return "".join(f"{name} {value}\n" for name, value in sorted(_fallback_metrics.items())).encode()


LLM_CALLS = Counter(
    "ferrox_llm_calls_total",
    "LLM provider attempts",
    ["provider", "model", "task", "status"],
)
LLM_LATENCY = Histogram(
    "ferrox_llm_call_duration_seconds",
    "LLM provider latency",
    ["provider", "model", "task"],
)
LLM_TOKENS = Counter(
    "ferrox_llm_tokens_total",
    "LLM tokens by direction",
    ["provider", "model", "task", "direction"],
)
LLM_COST = Counter(
    "ferrox_llm_estimated_cost_usd_total",
    "Estimated LLM cost from configured per-token rates",
    ["provider", "model", "task"],
)
HTTP_REQUESTS = Counter(
    "ferrox_http_requests_total",
    "HTTP requests",
    ["method", "route", "status"],
)
HTTP_LATENCY = Histogram(
    "ferrox_http_request_duration_seconds",
    "HTTP request latency",
    ["method", "route"],
)


@dataclass(frozen=True)
class LLMCallEvent:
    provider: str
    model: str
    task: str
    status: str
    latency_ms: int
    input_tokens: int = 0
    output_tokens: int = 0
    error: str | None = None
    product_id: str | None = None


class LLMObserver(Protocol):
    def record(self, event: LLMCallEvent) -> None: ...


class SQLAlchemyLLMObserver:
    def __init__(self, db: Session, settings: Settings):
        self.db = db
        self.settings = settings

    def record(self, event: LLMCallEvent) -> None:
        input_rate, output_rate = self.settings.llm_cost_rates(event.provider)
        estimated_cost = (
            event.input_tokens * input_rate + event.output_tokens * output_rate
        ) / 1_000_000
        LLM_CALLS.labels(event.provider, event.model, event.task, event.status).inc()
        LLM_LATENCY.labels(event.provider, event.model, event.task).observe(event.latency_ms / 1000)
        LLM_TOKENS.labels(event.provider, event.model, event.task, "input").inc(event.input_tokens)
        LLM_TOKENS.labels(event.provider, event.model, event.task, "output").inc(event.output_tokens)
        LLM_COST.labels(event.provider, event.model, event.task).inc(estimated_cost)
        self.db.add(
            LLMRun(
                product_id=event.product_id,
                provider=event.provider,
                model=event.model,
                task=event.task,
                status=event.status,
                latency_ms=event.latency_ms,
                input_tokens=event.input_tokens,
                output_tokens=event.output_tokens,
                estimated_cost_usd=estimated_cost,
                error=event.error[:4000] if event.error else None,
            )
        )
