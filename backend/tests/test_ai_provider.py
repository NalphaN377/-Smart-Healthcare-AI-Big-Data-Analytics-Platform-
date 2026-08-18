from types import SimpleNamespace

import pytest

from backend.app.ai.provider import OpenAICompatibleProvider


def test_provider_public_info_exposes_non_secret_configuration_only():
    provider = OpenAICompatibleProvider(
        api_key="never-expose-this",
        model="deepseek-v4-flash",
        base_url="https://api.deepseek.com",
        thinking_mode="disabled",
    )
    assert provider.public_info == {
        "name": "openai_compatible",
        "model": "deepseek-v4-flash",
        "thinking_mode": "disabled",
    }
    assert "never-expose-this" not in str(provider.public_info)


def test_provider_rejects_unknown_thinking_mode():
    with pytest.raises(ValueError):
        OpenAICompatibleProvider(
            api_key="test",
            model="test",
            thinking_mode="free_form",
        )


def test_deepseek_token_usage_is_normalized():
    response = SimpleNamespace(
        usage_metadata={
            "input_tokens": 120,
            "output_tokens": 30,
            "total_tokens": 150,
            "input_token_details": {"cache_read": 64},
        },
        response_metadata={
            "token_usage": {
                "prompt_tokens": 120,
                "completion_tokens": 30,
                "total_tokens": 150,
                "prompt_cache_hit_tokens": 64,
                "prompt_cache_miss_tokens": 56,
            }
        },
    )
    assert OpenAICompatibleProvider._extract_usage(response).model_dump() == {
        "input_tokens": 120,
        "output_tokens": 30,
        "total_tokens": 150,
        "cache_read_tokens": 64,
        "cache_miss_tokens": 56,
    }
