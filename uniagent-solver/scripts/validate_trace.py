#!/usr/bin/env python3
"""Check a run-trace.jsonl.log.gz against the event-logging contract and predictions.jsonl.

Checks: every line is a JSON object with all required fields, `model` is never empty, `status` is ok|error,
an error status always carries an error message, every parent_event_id refers to an earlier event of the
same case, every case ends with exactly one `decision` event, and predictions.jsonl has one line per case.
Exit code 1 on any violation.
"""

import argparse
import gzip
import json
import sys
from collections import defaultdict
from pathlib import Path

REQUIRED_FIELDS = ("case_id", "event_id", "parent_event_id", "timestamp", "event_type", "model", "tool", "input", "output", "status", "error")


def validate(run: Path) -> list[str]:
    problems = []
    events_by_case: dict[str, list[dict]] = defaultdict(list)
    seen_ids: dict[str, str] = {}
    with gzip.open(run / "run-trace.jsonl.log.gz", "rt", encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            try:
                event = json.loads(line)
            except json.JSONDecodeError as error:
                problems.append(f"line {number}: not JSON ({error})")
                continue
            missing = [field for field in REQUIRED_FIELDS if field not in event]
            if missing:
                problems.append(f"line {number}: missing {missing}")
            if not isinstance(event.get("model"), str) or not event["model"].strip():
                problems.append(f"line {number}: empty model")
            if event.get("status") not in ("ok", "error"):
                problems.append(f"line {number}: status {event.get('status')!r}")
            if event.get("status") == "error" and not event.get("error"):
                problems.append(f"line {number}: error status without message")
            parent = event.get("parent_event_id")
            if parent is not None and seen_ids.get(parent) != event.get("case_id"):
                problems.append(f"line {number}: parent {parent} is not an earlier event of {event.get('case_id')}")
            seen_ids[event.get("event_id")] = event.get("case_id")
            events_by_case[event.get("case_id")].append(event)
    predictions = [json.loads(line) for line in (run / "predictions.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    predicted = [row["antrag"] for row in predictions]
    if len(predicted) != len(set(predicted)):
        problems.append("predictions.jsonl has duplicate cases")
    for row in predictions:
        if row.get("result") not in ("angenommen", "abgelehnt") or not row.get("begruendung"):
            problems.append(f"{row.get('antrag')}: invalid prediction {row}")
        events = events_by_case.get(row["antrag"], [])
        decisions = [event for event in events if event["event_type"] == "decision"]
        if not events or events[-1]["event_type"] != "decision" or len(decisions) != 1:
            problems.append(f"{row['antrag']}: trace does not end with exactly one decision event")
    for case_id in events_by_case:
        if case_id != "-" and case_id not in predicted:
            problems.append(f"{case_id}: traced but no prediction")
    return problems


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runs", type=Path, nargs="+", help="output directories of predict.py")
    args = parser.parse_args()
    failed = False
    for run in args.runs:
        problems = validate(run)
        failed |= bool(problems)
        print(f"{run}: {'OK' if not problems else f'{len(problems)} problem(s)'}")
        for problem in problems[:20]:
            print(f"  - {problem}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
