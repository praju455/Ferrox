import pytest

from app.services.llm import (
    BaseHTTPJSONProvider,
    GeminiProvider,
    LLMError,
    LLMRequest,
    OpenAICompatibleProvider,
    parse_json_object,
)


def test_parse_json_object_accepts_markdown_fenced_json():
    assert parse_json_object('```json\n{"category": "Bearing", "confidence": 0.9}\n```') == {
        "category": "Bearing",
        "confidence": 0.9,
    }


def test_http_provider_retries_malformed_json_then_validates():
    class FlakyProvider(BaseHTTPJSONProvider):
        def __init__(self):
            super().__init__("flaky", "key", "model", 5, max_retries=1)
            self.calls = 0

        def _complete_text(self, prompt: str) -> str:
            self.calls += 1
            if self.calls == 1:
                return "not json"
            return '{"category": "Industrial Pump", "confidence": 0.88}'

    provider = FlakyProvider()
    result = provider.complete_json(LLMRequest(task="classify", prompt="pump"))

    assert result["category"] == "Industrial Pump"
    assert provider.calls == 2


def test_http_provider_rejects_schema_unknown_extraction_field():
    class BadProvider(BaseHTTPJSONProvider):
        def __init__(self):
            super().__init__("bad", "key", "model", 5, max_retries=0)

        def _complete_text(self, prompt: str) -> str:
            return '{"fields": {"unknown": {"value": "x", "confidence": 0.8, "source_identifier": "s", "status": "extracted"}}}'

    with pytest.raises(LLMError):
        BadProvider().complete_json(
            LLMRequest(
                task="extract",
                prompt="source",
                response_schema={"properties": {"manufacturer": {"type": "object"}}},
            )
        )


def test_gemini_provider_posts_generate_content_json_request(monkeypatch):
    captured = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"candidates": [{"content": {"parts": [{"text": '{"category": "Bearing", "confidence": 0.9}'}]}}]}

    def fake_post(url, headers, json, timeout):
        captured.update({"url": url, "headers": headers, "json": json, "timeout": timeout})
        return Response()

    monkeypatch.setattr("app.services.llm.requests.post", fake_post)

    result = GeminiProvider("gemini-key", "gemini-test", 7).complete_json(LLMRequest(task="classify", prompt="bearing"))

    assert result["category"] == "Bearing"
    assert "gemini-test:generateContent" in captured["url"]
    assert captured["headers"]["x-goog-api-key"] == "gemini-key"
    assert captured["json"]["generationConfig"]["responseMimeType"] == "application/json"
    assert captured["timeout"] == 7


def test_openai_compatible_provider_uses_json_object_mode(monkeypatch):
    captured = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": '{"valid": true, "issues": [], "confidence_delta": 0.0}'}}]}

    def fake_post(url, headers, json, timeout):
        captured.update({"url": url, "headers": headers, "json": json, "timeout": timeout})
        return Response()

    monkeypatch.setattr("app.services.llm.requests.post", fake_post)

    provider = OpenAICompatibleProvider("groq", "https://api.groq.com/openai/v1/chat/completions", "groq-key", "model-x", 9)
    result = provider.complete_json(LLMRequest(task="semantic_validate", prompt="validate"))

    assert result["valid"] is True
    assert captured["headers"]["Authorization"] == "Bearer groq-key"
    assert captured["json"]["model"] == "model-x"
    assert captured["json"]["response_format"] == {"type": "json_object"}
