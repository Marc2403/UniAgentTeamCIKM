"""OpenAI-compatible chat client with retries, a response cache and token accounting."""

import hashlib
import json
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Protocol


@dataclass
class Completion:
    text: str
    usage: dict[str, int] = field(default_factory=dict)
    cached: bool = False


class ChatModel(Protocol):
    model_id: str

    def complete(self, prompt: str, max_tokens: int) -> Completion: ...


class TokenUsage:
    """Thread-safe totals of the tokens reported by the endpoint (cache hits excluded)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.calls = 0
        self.cached_calls = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0

    def add(self, completion: Completion) -> None:
        with self._lock:
            if completion.cached:
                self.cached_calls += 1
                return
            self.calls += 1
            self.prompt_tokens += completion.usage.get("prompt_tokens", 0)
            self.completion_tokens += completion.usage.get("completion_tokens", 0)

    def as_dict(self) -> dict[str, int]:
        return {
            "calls": self.calls,
            "cached_calls": self.cached_calls,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
        }


class ResponseCache:
    """One JSON file per (model, prompt, parameters) hash. Never shipped in the image."""

    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def key(*parts: object) -> str:
        return hashlib.sha256(json.dumps(parts, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()

    def get(self, key: str) -> Completion | None:
        path = self.directory / f"{key}.json"
        if not path.is_file():
            return None
        entry = json.loads(path.read_text(encoding="utf-8"))
        return Completion(entry["text"], entry.get("usage", {}), cached=True)

    def put(self, key: str, completion: Completion) -> None:
        path = self.directory / f"{key}.json"
        temporary = path.with_suffix(f".{threading.get_ident()}.tmp")
        temporary.write_text(json.dumps({"text": completion.text, "usage": completion.usage}, ensure_ascii=False), encoding="utf-8")
        temporary.replace(path)


def required_environment() -> tuple[str, str, str]:
    values = []
    for name in ("OPENAI_BASE_URL", "OPENAI_API_KEY", "OPENAI_MODEL"):
        value = os.environ.get(name, "").strip()
        if not value:
            raise RuntimeError(f"Required environment variable {name} is not set.")
        values.append(value)
    return values[0], values[1], values[2]


class OpenAIChatModel:
    def __init__(self, settings: dict, usage: TokenUsage, sleep: Callable[[float], None] = time.sleep) -> None:
        from openai import OpenAI

        base_url, api_key, self.model_id = required_environment()
        self._client = OpenAI(base_url=base_url, api_key=api_key, timeout=settings["timeout_seconds"], max_retries=0)
        self.settings = settings
        self.usage = usage
        self.cache = ResponseCache(settings["cache_dir"]) if settings.get("cache_dir") else None
        self._sleep = sleep

    def _request(self, prompt: str, max_tokens: int) -> Completion:
        parameters = {
            "model": self.model_id,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": self.settings["temperature"],
        }
        if self.settings.get("reasoning_effort"):
            parameters["reasoning_effort"] = self.settings["reasoning_effort"]
        response = self._client.chat.completions.create(**parameters)
        usage = response.usage
        return Completion(
            text=response.choices[0].message.content or "",
            usage={
                "prompt_tokens": getattr(usage, "prompt_tokens", 0) or 0,
                "completion_tokens": getattr(usage, "completion_tokens", 0) or 0,
            },
        )

    def complete(self, prompt: str, max_tokens: int) -> Completion:
        key = ResponseCache.key(self.model_id, prompt, max_tokens, self.settings["temperature"], self.settings.get("reasoning_effort"))
        cached = self.cache.get(key) if self.cache else None
        if cached is not None:
            self.usage.add(cached)
            return cached
        attempts = self.settings["max_retries"] + 1
        for attempt in range(attempts):
            try:
                completion = self._request(prompt, max_tokens)
                break
            except Exception:
                if attempt == attempts - 1:
                    raise
                self._sleep(2**attempt)
        self.usage.add(completion)
        if self.cache and completion.text.strip():
            self.cache.put(key, completion)
        return completion


class ScriptedChatModel:
    """Offline stand-in for tests: answers with `respond(prompt)`."""

    def __init__(self, respond: Callable[[str], str], usage: TokenUsage | None = None, model_id: str = "mock-llm") -> None:
        self.respond = respond
        self.usage = usage or TokenUsage()
        self.model_id = model_id
        self.prompts: list[str] = []
        self._lock = threading.Lock()

    def complete(self, prompt: str, max_tokens: int) -> Completion:
        with self._lock:
            self.prompts.append(prompt)
        completion = Completion(self.respond(prompt), {"prompt_tokens": len(prompt.split()), "completion_tokens": 5})
        self.usage.add(completion)
        return completion
