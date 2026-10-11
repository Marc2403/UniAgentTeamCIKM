import gzip
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


class EventLogger:
    def __init__(self, path: Path, model_id: str = "-"):
        self.path = path
        self.model_id = model_id or "-"
        self._fh = gzip.open(path, "wt", encoding="utf-8")

    def _timestamp(self) -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def emit(
        self,
        case_id: str,
        event_type: str,
        parent_event_id: Optional[str] = None,
        input: Optional[Any] = None,
        output: Optional[Any] = None,
        status: str = "ok",
        error: Optional[str] = None,
        model: Optional[str] = None,
        tool: Optional[str] = None,
    ) -> str:
        event_id = uuid.uuid4().hex
        if not model:
            model = self.model_id
        if not model:
            model = "-"

        event = {
            "case_id": case_id,
            "event_id": event_id,
            "parent_event_id": parent_event_id,
            "timestamp": self._timestamp(),
            "event_type": event_type,
            "model": model,
            "tool": tool,
            "input": input if input is not None else {},
            "output": output if output is not None else {},
            "status": status,
            "error": error,
        }
        self._fh.write(json.dumps(event, ensure_ascii=False) + "\n")
        self._fh.flush()
        return event_id

    def close(self) -> None:
        self._fh.close()