import os

import pytest

from app.core.config import Settings
from app.services.llm import GeminiProvider, LLMRequest, OpenAICompatibleProvider


@pytest.mark.live_llm
@pytest.mark.parametrize("provider_name", ["gemini", "groq", "openai"])
def test_live_provider_returns_valid_classification(provider_name):
    settings = Settings()
    if provider_name == "gemini":
        key = os.getenv("GEMINI_API_KEY")
        provider = GeminiProvider(key, settings.gemini_model, settings.llm_timeout_seconds)
    elif provider_name == "groq":
        key = os.getenv("GROQ_API_KEY")
        provider = OpenAICompatibleProvider(
            "groq",
            "https://api.groq.com/openai/v1/chat/completions",
            key,
            settings.groq_model,
            settings.llm_timeout_seconds,
        )
    else:
        key = os.getenv("OPENAI_API_KEY")
        provider = OpenAICompatibleProvider(
            "openai",
            "https://api.openai.com/v1/chat/completions",
            key,
            settings.openai_model,
            settings.llm_timeout_seconds,
        )
    if not key:
        pytest.skip(f"{provider_name} key is not configured")
    result = provider.complete_json(
        LLMRequest(task="classify", prompt="Industrial motor, 10 HP, 230 V, 1750 RPM, TEFC enclosure.")
    )
    assert result["category"] == "Electric Motor"
    assert 0 <= result["confidence"] <= 1
