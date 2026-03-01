from __future__ import annotations

from openclaw_token_compass.provider import detect_provider, get_provider_profile


def test_detect_provider_priority_order():
    provider, source = detect_provider(
        explicit_provider="anthropic",
        api_interface="openai",
        api_url="https://api.openai.com/v1",
        model="gpt-4o",
    )
    assert provider == "anthropic"
    assert source == "explicit"


def test_detect_provider_from_interface_and_url():
    provider_interface, source_interface = detect_provider(
        api_interface="gemini",
        model="custom",
    )
    assert provider_interface == "google"
    assert source_interface == "api_interface"

    provider_url, source_url = detect_provider(
        api_url="https://api.anthropic.com/v1/messages",
        model="custom",
    )
    assert provider_url == "anthropic"
    assert source_url == "api_url"


def test_detect_provider_from_model_and_env():
    provider_model, source_model = detect_provider(model="claude-3-7-sonnet")
    assert provider_model == "anthropic"
    assert source_model == "model"

    provider_env, source_env = detect_provider(model="", env={"OPENAI_API_KEY": "sk-demo"})
    assert provider_env == "openai"
    assert source_env == "env"


def test_get_provider_profile_defaults():
    profile = get_provider_profile("google")
    assert profile.default_output_ratio > 0

    unknown_profile = get_provider_profile("something_new")
    assert unknown_profile.name == "unknown"
