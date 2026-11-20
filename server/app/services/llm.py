"""Shared Groq client helpers."""
import os
from typing import Any, Dict

from app.core import config


def groq_api_key() -> str:
    key = os.getenv("GROQ_API_KEY") or ""
    return "" if key == "your_groq_api_key_here" else key


def completion_kwargs(max_tokens: int, temperature: float = 0.3) -> Dict[str, Any]:
    """Model-specific request parameters for chat.completions.create."""
    kwargs: Dict[str, Any] = {
        "model": config.GROQ_MODEL,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    model = config.GROQ_MODEL.lower()
    if config.GROQ_REASONING_EFFORT and "gpt-oss" in model:
        # Reasoning tokens count against the (small) free-tier TPM budget.
        kwargs["reasoning_effort"] = config.GROQ_REASONING_EFFORT
    return kwargs
