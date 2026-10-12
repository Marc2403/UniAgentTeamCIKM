"""Event logging per ../uniagent-code/cikm26/event-logging-contract/README.md.

Mirrors the reference implementation of the solving baselines
(`solving-smolagents-with-retrieval/event_logging.py`) without the smolagents
dependency: every event carries case_id, event_id, parent_event_id, timestamp,
event_type, model, tool, input, output, status and error. Within a
`case_context()` each event becomes the parent of the next, so every case is one
causal chain from its `input` event to its final `decision` event.
"""

import contextlib
import contextvars
import gzip
import itertools
import json
import sys
import threading
from datetime import datetime, timezone
from typing import IO, Any, Iterator

_current_case: contextvars.ContextVar[str] = contextvars.ContextVar("event_log_case", default="-")
_current_model: contextvars.ContextVar[str] = contextvars.ContextVar("event_log_model", default="-")
_current_parent: contextvars.ContextVar[str | None] = contextvars.ContextVar("event_log_parent", default=None)
_destination: contextvars.ContextVar[IO[str] | None] = contextvars.ContextVar("event_log_destination", default=None)
_counter = itertools.count(1)
_write_lock = threading.Lock()
# Cases whose decision is logged: a worker abandoned by the watchdog must not log after it.
_sealed: set[str] = set()

# Strings are whitespace-normalised and cut to this many characters; other JSON
# values stay native when their encoding fits, else become a truncated string.
PREVIEW_LIMIT = 200


@contextlib.contextmanager
def case_context(case_id: str) -> Iterator[None]:
    case_token = _current_case.set(case_id)
    parent_token = _current_parent.set(None)
    try:
        yield
    finally:
        _current_case.reset(case_token)
        _current_parent.reset(parent_token)


@contextlib.contextmanager
def model_context(model_id: str) -> Iterator[None]:
    token = _current_model.set(model_id)
    try:
        yield
    finally:
        _current_model.reset(token)


@contextlib.contextmanager
def log_to_file(path: Any) -> Iterator[None]:
    with gzip.open(path, "wt", encoding="utf-8") as destination:
        token = _destination.set(destination)
        try:
            yield
        finally:
            _destination.reset(token)


def preview(value: Any, limit: int = PREVIEW_LIMIT) -> Any:
    if isinstance(value, str):
        text = value
    else:
        text = json.dumps(value, ensure_ascii=False, default=str)
        if len(text) <= limit:
            return value
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _preview_all(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, dict):
        return {key: preview(item) for key, item in value.items()}
    return preview(value)


def log_event(
    event_type: str,
    *,
    tool: str | None = None,
    input: Any = None,
    output: Any = None,
    status: str = "ok",
    error: str | None = None,
) -> str:
    """Write one event, chained onto the previous event of the active case; return its id.

    A `decision` event seals its case: later events of that case are dropped, so every trace ends with it.
    """
    case_id = _current_case.get()
    event_id = f"evt-{next(_counter):05d}"
    if case_id in _sealed:
        return event_id
    entry = {
        "case_id": case_id,
        "event_id": event_id,
        "parent_event_id": _current_parent.get(),
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "event_type": event_type,
        "model": _current_model.get(),
        "tool": tool,
        "input": _preview_all(input),
        "output": _preview_all(output),
        "status": status,
        "error": error,
    }
    destination = _destination.get() or sys.stdout
    with _write_lock:
        if case_id in _sealed:
            return event_id
        if event_type == "decision" and case_id != "-":
            _sealed.add(case_id)
        print(json.dumps(entry, ensure_ascii=False, default=str), file=destination, flush=True)
    _current_parent.set(event_id)
    return event_id
