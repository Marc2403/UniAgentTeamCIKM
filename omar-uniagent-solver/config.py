import os
from urllib.parse import urlparse


def _require_scheme(value: str, env_name: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise RuntimeError(
            f"{env_name} must be a full URL starting with http:// or https:// "
            f"(got {value!r})."
        )
    return value


def load_llm_config(required: bool = True):
    base_url = os.environ.get("OPENAI_BASE_URL", "").strip()
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    model = os.environ.get("OPENAI_MODEL", "").strip()
    reasoning_effort = os.environ.get("OPENAI_REASONING_EFFORT", "").strip() or None

    if required and (not base_url or not api_key or not model):
        raise RuntimeError(
            "Missing LLM configuration: OPENAI_BASE_URL, OPENAI_API_KEY and "
            "OPENAI_MODEL must all be set."
        )

    if base_url:
        _require_scheme(base_url, "OPENAI_BASE_URL")

    if required and (model.startswith("[") or base_url.startswith("[")):
        raise RuntimeError(
            "LLM configuration contains placeholder brackets; fill in real "
            "OPENAI_BASE_URL/OPENAI_MODEL values."
        )

    return {
        "base_url": base_url,
        "api_key": api_key,
        "model": model,
        "reasoning_effort": reasoning_effort,
    }