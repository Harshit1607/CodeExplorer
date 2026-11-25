"""Shared Groq client helpers."""
import os
from typing import Any, Dict

from fastapi import HTTPException

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


def map_llm_error(e: Exception) -> HTTPException:
    """Turn a Groq error into a user-facing HTTPException. Unrecognized errors get a generic
    message; their details are only logged."""
    error_msg = str(e)
    low = error_msg.lower()
    print(f"LLM API error: {error_msg}")
    status = getattr(e, "status_code", None)

    if status == 413 or "request too large" in low or "reduce your message size" in low:
        return HTTPException(400, "The question context is too large for the AI's rate limit. Try a more specific question.")
    if status == 429 or "rate_limit" in low:
        # Upstream (Groq) quota is shared by every user of this server; pass its back-off through.
        retry_after = None
        try:
            retry_after = int(float(e.response.headers.get("retry-after")))  # type: ignore[attr-defined]
        except Exception:
            pass
        headers = {"Retry-After": str(max(1, retry_after))} if retry_after else None
        wait = f" Please try again in {retry_after}s." if retry_after else " Please wait a moment and try again."
        return HTTPException(429, "The AI service's rate limit was reached." + wait, headers=headers)
    if status == 401 or "invalid_api_key" in low or "invalid api key" in low:
        return HTTPException(401, "AI service authentication failed. Please check the API key.")
    if "model_not_found" in low or "does not exist" in low:
        return HTTPException(503, f"AI model '{config.GROQ_MODEL}' is unavailable. Set GROQ_MODEL to a model your key can access.")
    if "context_length_exceeded" in low or "maximum context length" in low:
        return HTTPException(400, "The question context is too long. Try asking about specific files.")
    if status == 503 or "service unavailable" in low:
        return HTTPException(503, "AI service is temporarily unavailable. Please try again later.")
    return HTTPException(500, "The AI request failed. Please try again later.")
