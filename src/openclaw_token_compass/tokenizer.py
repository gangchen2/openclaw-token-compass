from __future__ import annotations

import math
import re
from functools import lru_cache

from .provider import get_provider_profile

_WORD_RE = re.compile(r"[A-Za-z0-9_]+")
_CJK_RE = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]")


@lru_cache(maxsize=128)
def _get_encoder(model: str):
    try:
        import tiktoken  # type: ignore
    except Exception:
        return None

    try:
        return tiktoken.encoding_for_model(model)
    except Exception:
        try:
            return tiktoken.get_encoding("cl100k_base")
        except Exception:
            return None


def _heuristic_token_count(text: str, *, chars_per_token: float) -> int:
    if not text:
        return 0

    cjk_chars = len(_CJK_RE.findall(text))
    words = _WORD_RE.findall(text)
    word_chars = sum(len(w) for w in words)

    latin_denominator = max(2.5, min(6.0, chars_per_token))
    latin_tokens = math.ceil(word_chars / latin_denominator) if word_chars else 0

    residue_chars = max(0, len(text) - cjk_chars - word_chars)
    residue_tokens = math.ceil(residue_chars / (latin_denominator + 1.5)) if residue_chars else 0

    estimate = cjk_chars + latin_tokens + residue_tokens
    return max(1, estimate)


def estimate_text_tokens(text: str | None, model: str, *, provider: str = "unknown") -> int:
    if not text:
        return 0

    profile = get_provider_profile(provider)

    base_tokens: int
    encoder = _get_encoder(model) if profile.prefer_tiktoken else None
    if encoder is not None:
        try:
            base_tokens = len(encoder.encode(text))
        except Exception:
            base_tokens = _heuristic_token_count(text, chars_per_token=profile.chars_per_token)
    else:
        base_tokens = _heuristic_token_count(text, chars_per_token=profile.chars_per_token)

    adjusted = round(base_tokens * profile.input_token_scale)
    return max(1, adjusted)
