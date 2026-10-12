"""OpenAI-compatible chat client with timeouts, one retry, token accounting and a dev cache."""

import hashlib
import json
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol


@dataclass
class Completion:
    text: str
    usage: dict[str, int] = field(default_factory=dict)
    finish_reason: str | None = None
    cached: bool = False


class ChatModel(Protocol):
    model_id: str
    usage: "TokenUsage"

    def complete(self, messages: list[dict[str, str]], timeout: float, temperature: float | None = None, reasoning_effort: str | None = None) -> Completion: ...


class TokenUsage:
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
    """One JSON file per request hash; for local development only, never in the image."""

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
        return Completion(entry["text"], entry.get("usage", {}), entry.get("finish_reason"), cached=True)

    def put(self, key: str, completion: Completion) -> None:
        path = self.directory / f"{key}.json"
        temporary = path.with_suffix(f".{threading.get_ident()}.tmp")
        entry = {"text": completion.text, "usage": completion.usage, "finish_reason": completion.finish_reason}
        temporary.write_text(json.dumps(entry, ensure_ascii=False), encoding="utf-8")
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
    def __init__(
        self,
        max_tokens: int,
        temperature: float,
        max_retries: int,
        reasoning_effort: str | None = None,
        cache_dir: str | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        from openai import OpenAI

        base_url, api_key, self.model_id = required_environment()
        self._client = OpenAI(base_url=base_url, api_key=api_key, max_retries=0)
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.max_retries = max_retries
        self.reasoning_effort = reasoning_effort
        self.reasoning_supported = True
        self.cache = ResponseCache(Path(cache_dir)) if cache_dir else None
        self.usage = TokenUsage()
        self._sleep = sleep

    @staticmethod
    def _within(timeout: float, request: Callable[[], Completion]) -> Completion:
        """Run `request` in a daemon thread and abandon it at `timeout`.

        The HTTP read timeout alone never fires while a proxy keeps the connection alive; a daemon thread
        (unlike a ThreadPoolExecutor worker) also cannot hold the process open at exit.
        """
        outcome: dict[str, Any] = {}
        finished = threading.Event()

        def run() -> None:
            try:
                outcome["completion"] = request()
            except BaseException as error:  # handed to the caller below
                outcome["error"] = error
            finally:
                finished.set()

        threading.Thread(target=run, name="llm", daemon=True).start()
        if not finished.wait(timeout):
            raise TimeoutError(f"LLM call exceeded {timeout:.0f} s")
        if "error" in outcome:
            raise outcome["error"]
        return outcome["completion"]

    def _request(self, messages: list[dict[str, str]], timeout: float, temperature: float, reasoning_effort: str | None) -> Completion:
        parameters: dict[str, Any] = {
            "model": self.model_id,
            "messages": messages,
            "max_tokens": self.max_tokens,
            "temperature": temperature,
            "timeout": timeout,
        }
        if reasoning_effort and self.reasoning_supported:
            parameters["reasoning_effort"] = reasoning_effort
        try:
            response = self._client.chat.completions.create(**parameters)
        except Exception as error:
            # Models without reasoning controls (e.g. Qwen behind vLLM) may reject the parameter.
            if "reasoning_effort" not in parameters or "reasoning" not in str(error).lower():
                raise
            self.reasoning_supported = False
            del parameters["reasoning_effort"]
            response = self._client.chat.completions.create(**parameters)
        choice = response.choices[0]
        usage = response.usage
        return Completion(
            text=choice.message.content or "",
            usage={
                "prompt_tokens": getattr(usage, "prompt_tokens", 0) or 0,
                "completion_tokens": getattr(usage, "completion_tokens", 0) or 0,
            },
            finish_reason=choice.finish_reason,
        )

    def complete(self, messages: list[dict[str, str]], timeout: float, temperature: float | None = None, reasoning_effort: str | None = None) -> Completion:
        temperature = self.temperature if temperature is None else temperature
        reasoning_effort = reasoning_effort or self.reasoning_effort
        key = ResponseCache.key(self.model_id, messages, self.max_tokens, temperature, reasoning_effort)
        cached = self.cache.get(key) if self.cache and temperature == self.temperature else None
        if cached is not None:
            self.usage.add(cached)
            return cached
        deadline = time.monotonic() + timeout
        for attempt in range(self.max_retries + 1):
            remaining = deadline - time.monotonic()
            try:
                if remaining < 1:
                    raise TimeoutError("LLM time budget exhausted")
                completion = self._within(remaining, lambda: self._request(messages, remaining, temperature, reasoning_effort))
                break
            except Exception:
                if attempt == self.max_retries or deadline - time.monotonic() < 3:
                    raise
                self._sleep(2)
        self.usage.add(completion)
        if self.cache and completion.text.strip() and temperature == self.temperature:
            self.cache.put(key, completion)
        return completion


class ScriptedChatModel:
    """Offline stand-in for tests: answers with `respond(messages)`."""

    def __init__(self, respond: Callable[[list[dict[str, str]]], str], model_id: str = "mock-llm") -> None:
        self.respond = respond
        self.model_id = model_id
        self.usage = TokenUsage()
        self.calls: list[list[dict[str, str]]] = []

    def complete(self, messages: list[dict[str, str]], timeout: float, temperature: float | None = None, reasoning_effort: str | None = None) -> Completion:
        self.calls.append(messages)
        completion = Completion(self.respond(messages), {"prompt_tokens": 10, "completion_tokens": 5}, "stop")
        self.usage.add(completion)
        return completion


def extract_json_object(answer: str) -> dict[str, Any]:
    """The first JSON object in `answer`, tolerating markdown fences and prose around it."""
    text = answer.strip()
    if text.startswith("```"):
        text = "\n".join(line for line in text.splitlines() if not line.strip().startswith("```"))
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = None
        decoder = json.JSONDecoder()
        for position, character in enumerate(text):
            if character != "{":
                continue
            try:
                parsed, _ = decoder.raw_decode(text[position:])
                break
            except json.JSONDecodeError:
                continue
    if not isinstance(parsed, dict):
        raise ValueError(f"Model did not return a JSON object: {answer[:200]!r}")
    return parsed
