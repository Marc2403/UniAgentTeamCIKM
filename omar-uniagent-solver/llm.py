import json
import re
from typing import Dict, Tuple

from openai import OpenAI

# JSON schema for the decision output. Passed as response_format so the
# model is constrained to emit valid JSON.
DECISION_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "case_decision",
        "schema": {
            "type": "object",
            "properties": {
                "result": {"type": "string", "enum": ["angenommen", "abgelehnt"]},
                "begruendung": {"type": "string"},
                "evidence": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "source_id": {"type": "string"},
                            "page": {"type": ["integer", "null"]},
                            "relevance": {"type": "string"},
                        },
                        "required": ["source_id", "relevance"],
                    },
                },
            },
            "required": ["result", "begruendung", "evidence"],
        },
    },
}


def make_client(base_url: str, api_key: str) -> OpenAI:
    # max_retries=0: for slow reasoning models, let the per-call timeout
    # be the single point of failure rather than silently multiplying it.
    return OpenAI(base_url=base_url, api_key=api_key, max_retries=0)


def call_model(
    client: OpenAI,
    model: str,
    prompt: str,
    timeout: float = 300.0,
    reasoning_effort: str | None = None,
    use_structured_output: bool = True,
) -> Tuple[str, Dict]:
    kwargs = dict(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        timeout=timeout,
        max_tokens=1500,
    )
    if use_structured_output:
        kwargs["response_format"] = DECISION_SCHEMA

    # reasoning_effort is not in the OpenAI SDK 1.55.3 schema, but vLLM
    # accepts it (gpt-oss supports low/medium/high). Pass it via extra_body
    # so the SDK forwards it to the server without a client-side type check.
    extra_body = {}
    if reasoning_effort:
        extra_body["reasoning_effort"] = reasoning_effort
    if extra_body:
        kwargs["extra_body"] = extra_body

    resp = client.chat.completions.create(**kwargs)
    text = resp.choices[0].message.content or ""
    usage = getattr(resp, "usage", None)
    usage_dict = {
        "prompt_tokens": getattr(usage, "prompt_tokens", None) if usage else None,
        "completion_tokens": getattr(usage, "completion_tokens", None) if usage else None,
        "total_tokens": getattr(usage, "total_tokens", None) if usage else None,
    }
    return text, usage_dict


def extract_json_object(text: str) -> dict:
    """Robust JSON extraction. Tries multiple strategies in order.

    With structured output enabled, strategy 1 should always succeed.
    The fallbacks exist for the case where a provider ignores response_format.
    """
    text = text.strip()

    # Strategy 1: direct parse (structured output path)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Strategy 2: strip markdown code fences
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    # Strategy 3: first { to last }
    i = text.find("{")
    j = text.rfind("}")
    if i != -1 and j > i:
        try:
            return json.loads(text[i:j + 1])
        except json.JSONDecodeError:
            pass

    # Strategy 4: json-repair for malformed JSON (missing quotes, commas, etc.)
    try:
        from json_repair import repair_json
        repaired = repair_json(text)
        if repaired:
            return json.loads(repaired)
    except Exception:
        pass

    raise ValueError(f"No JSON object found in model response: {text[:200]!r}")