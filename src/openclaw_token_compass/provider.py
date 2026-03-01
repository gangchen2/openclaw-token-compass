from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class ProviderProfile:
    name: str
    input_token_scale: float
    default_output_ratio: float
    chars_per_token: float
    prefer_tiktoken: bool


_PROVIDER_ALIASES = {
    "azure": "azure_openai",
    "azure-openai": "azure_openai",
    "azure_openai": "azure_openai",
    "claude": "anthropic",
    "gemini": "google",
    "googleai": "google",
    "google_ai": "google",
    "openai_compatible": "openai",
    "openai-compatible": "openai",
    "unknown_provider": "unknown",
}


_PROVIDER_PROFILES: dict[str, ProviderProfile] = {
    "openai": ProviderProfile(
        name="openai",
        input_token_scale=1.00,
        default_output_ratio=0.35,
        chars_per_token=4.0,
        prefer_tiktoken=True,
    ),
    "azure_openai": ProviderProfile(
        name="azure_openai",
        input_token_scale=1.00,
        default_output_ratio=0.35,
        chars_per_token=4.0,
        prefer_tiktoken=True,
    ),
    "anthropic": ProviderProfile(
        name="anthropic",
        input_token_scale=1.08,
        default_output_ratio=0.42,
        chars_per_token=3.7,
        prefer_tiktoken=False,
    ),
    "google": ProviderProfile(
        name="google",
        input_token_scale=1.12,
        default_output_ratio=0.33,
        chars_per_token=3.5,
        prefer_tiktoken=False,
    ),
    "deepseek": ProviderProfile(
        name="deepseek",
        input_token_scale=1.00,
        default_output_ratio=0.34,
        chars_per_token=3.9,
        prefer_tiktoken=True,
    ),
    "openrouter": ProviderProfile(
        name="openrouter",
        input_token_scale=1.03,
        default_output_ratio=0.36,
        chars_per_token=3.9,
        prefer_tiktoken=True,
    ),
    "qwen": ProviderProfile(
        name="qwen",
        input_token_scale=1.05,
        default_output_ratio=0.36,
        chars_per_token=3.8,
        prefer_tiktoken=True,
    ),
    "moonshot": ProviderProfile(
        name="moonshot",
        input_token_scale=1.05,
        default_output_ratio=0.36,
        chars_per_token=3.8,
        prefer_tiktoken=True,
    ),
    "xai": ProviderProfile(
        name="xai",
        input_token_scale=1.00,
        default_output_ratio=0.35,
        chars_per_token=4.0,
        prefer_tiktoken=True,
    ),
    "unknown": ProviderProfile(
        name="unknown",
        input_token_scale=1.10,
        default_output_ratio=0.38,
        chars_per_token=3.7,
        prefer_tiktoken=False,
    ),
}


_INTERFACE_TO_PROVIDER = {
    "openai": "openai",
    "openai_compatible": "openai",
    "azure_openai": "azure_openai",
    "anthropic": "anthropic",
    "claude": "anthropic",
    "gemini": "google",
    "google": "google",
}


_MODEL_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^(gpt|o1|o3|o4|text-embedding|chatgpt)", re.IGNORECASE), "openai"),
    (re.compile(r"^claude", re.IGNORECASE), "anthropic"),
    (re.compile(r"^gemini", re.IGNORECASE), "google"),
    (re.compile(r"^deepseek", re.IGNORECASE), "deepseek"),
    (re.compile(r"^qwen", re.IGNORECASE), "qwen"),
    (re.compile(r"^(kimi|moonshot)", re.IGNORECASE), "moonshot"),
    (re.compile(r"^(grok|xai)", re.IGNORECASE), "xai"),
)


_URL_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"openai\.azure\.com", re.IGNORECASE), "azure_openai"),
    (re.compile(r"api\.openai\.com", re.IGNORECASE), "openai"),
    (re.compile(r"anthropic\.com", re.IGNORECASE), "anthropic"),
    (re.compile(r"generativelanguage\.googleapis\.com", re.IGNORECASE), "google"),
    (re.compile(r"googleapis\.com|ai\.google\.dev", re.IGNORECASE), "google"),
    (re.compile(r"openrouter\.ai", re.IGNORECASE), "openrouter"),
    (re.compile(r"deepseek\.com", re.IGNORECASE), "deepseek"),
)


_ENV_HINTS: tuple[tuple[str, str], ...] = (
    ("OPENCLAW_PROVIDER", ""),
    ("OPENAI_API_KEY", "openai"),
    ("AZURE_OPENAI_API_KEY", "azure_openai"),
    ("ANTHROPIC_API_KEY", "anthropic"),
    ("GOOGLE_API_KEY", "google"),
    ("GEMINI_API_KEY", "google"),
    ("OPENROUTER_API_KEY", "openrouter"),
    ("DEEPSEEK_API_KEY", "deepseek"),
)


def _as_clean_str(value: object | None) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        return ""
    return value.strip()


def normalize_provider_name(name: str | None) -> str:
    raw = _as_clean_str(name)
    if not raw:
        return ""
    normalized = raw.lower().replace("-", "_")
    return _PROVIDER_ALIASES.get(normalized, normalized)


def _is_concrete_provider(name: str) -> bool:
    return bool(name) and name not in {"unknown", "mixed"}


def _provider_from_interface(api_interface: str | None) -> str:
    normalized = normalize_provider_name(api_interface)
    if not normalized:
        return ""
    return _INTERFACE_TO_PROVIDER.get(normalized, normalized)


def _provider_from_url(*values: str | None) -> str:
    for value in values:
        text = _as_clean_str(value)
        if not text:
            continue
        for pattern, provider in _URL_RULES:
            if pattern.search(text):
                return provider
    return ""


def _provider_from_model(model: str | None) -> str:
    model_name = _as_clean_str(model)
    if not model_name:
        return ""
    for pattern, provider in _MODEL_RULES:
        if pattern.search(model_name):
            return provider
    return ""


def provider_from_env(env: Mapping[str, str] | None = None) -> str:
    source = env if env is not None else os.environ
    for key, fixed_provider in _ENV_HINTS:
        value = _as_clean_str(source.get(key))
        if not value:
            continue
        if fixed_provider:
            return fixed_provider
        normalized = normalize_provider_name(value)
        if _is_concrete_provider(normalized):
            return normalized
    return ""


def detect_provider(
    *,
    explicit_provider: str | None = None,
    api_interface: str | None = None,
    api_base: str | None = None,
    api_url: str | None = None,
    endpoint: str | None = None,
    model: str | None = None,
    env: Mapping[str, str] | None = None,
) -> tuple[str, str]:
    normalized = normalize_provider_name(explicit_provider)
    if _is_concrete_provider(normalized):
        return normalized, "explicit"

    from_interface = _provider_from_interface(api_interface)
    if _is_concrete_provider(from_interface):
        return from_interface, "api_interface"

    from_url = _provider_from_url(api_base, api_url, endpoint)
    if _is_concrete_provider(from_url):
        return from_url, "api_url"

    from_model = _provider_from_model(model)
    if _is_concrete_provider(from_model):
        return from_model, "model"

    from_env = provider_from_env(env)
    if _is_concrete_provider(from_env):
        return from_env, "env"

    return "unknown", "fallback"


def get_provider_profile(provider: str | None) -> ProviderProfile:
    normalized = normalize_provider_name(provider)
    if normalized in _PROVIDER_PROFILES:
        return _PROVIDER_PROFILES[normalized]
    return _PROVIDER_PROFILES["unknown"]
