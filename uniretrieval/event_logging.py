"""Run trace per uniagent-code/cikm26/event-logging-contract/README.md.

Mirrors the baseline's event_logging.py (same fields, same event-id scheme,
each event chained onto the previous one of its case, string previews), but
collects events in memory because this pipeline processes all queries stage
by stage rather than one query at a time; `write()` dumps the trace, and may
be called again after later stages to replace the file."""

import gzip
import itertools
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STRING_LIMIT = 300
LIST_LIMIT = 30


def preview(value: Any) -> Any:
    """Bound the size of logged values while keeping them structured JSON:
    strings are whitespace-normalised and cut, lists cut, containers recursed."""
    if isinstance(value, str):
        text = " ".join(value.split())
        return text if len(text) <= STRING_LIMIT else text[: STRING_LIMIT - 1] + "…"
    if isinstance(value, dict):
        return {str(key): preview(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [preview(item) for item in list(value)[:LIST_LIMIT]]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return preview(str(value))


class Trace:
    def __init__(self, model: str) -> None:
        self.model = model or "-"
        self.events: list[dict[str, Any]] = []
        self._counter = itertools.count(1)
        self._tail: dict[str, str | None] = {}

    def log(
        self,
        case_id: str,
        event_type: str,
        *,
        tool: str | None = None,
        input: Any = None,
        output: Any = None,
        status: str = "ok",
        error: str | None = None,
        parent_event_id: str | None = None,
    ) -> str:
        event_id = f"evt-{next(self._counter):05d}"
        self.events.append(
            {
                "case_id": case_id,
                "event_id": event_id,
                "parent_event_id": parent_event_id if parent_event_id is not None else self._tail.get(case_id),
                "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
                "event_type": event_type,
                "model": self.model,
                "tool": tool,
                "input": preview(input),
                "output": preview(output),
                "status": status,
                "error": error,
            }
        )
        self._tail[case_id] = event_id
        return event_id

    def last_event(self, case_id: str) -> str | None:
        return self._tail.get(case_id)

    def write(self, path: Path) -> None:
        """Events grouped per case (in first-seen order) so each case ends with its decision."""
        order = {case_id: position for position, case_id in enumerate(dict.fromkeys(event["case_id"] for event in self.events))}
        events = sorted(self.events, key=lambda event: (order[event["case_id"]], int(event["event_id"][4:])))
        temporary = Path(path).with_suffix(".tmp")
        with gzip.open(temporary, "wt", encoding="utf-8") as handle:
            for event in events:
                handle.write(json.dumps(event, ensure_ascii=False) + "\n")
        temporary.replace(path)
