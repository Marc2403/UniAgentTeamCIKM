#!/usr/bin/env python3
"""Summarise runs written by run-mvp.sh: accuracy, wall time, per-case time, LLM calls, tokens, errors.

Usage: python evaluation/summarize.py evaluation/runs/<model>/<system> [...]
Token counts are read from model_call events (any of prompt/completion/total/input/output_tokens keys), so they
are only as complete as each system's own logging.
"""

import gzip
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

DATASETS = ("business-trip-spot-check", "task-2-procurement-spot-check", "task-2-expense-reimbursement-spot-check")
SHORT = {"business-trip-spot-check": "trip", "task-2-procurement-spot-check": "proc", "task-2-expense-reimbursement-spot-check": "exp"}


def token_counts(value) -> tuple[int, int]:
    """(prompt, completion) tokens found anywhere in a logged model output."""
    if isinstance(value, dict):
        prompt = value.get("prompt_tokens") or value.get("input_tokens") or 0
        completion = value.get("completion_tokens") or value.get("output_tokens") or 0
        if not (prompt or completion) and isinstance(value.get("total"), int):
            prompt = value["total"]
        if isinstance(prompt, int) and isinstance(completion, int) and (prompt or completion):
            return prompt, completion
        sums = [token_counts(item) for item in value.values()]
        return sum(p for p, _ in sums), sum(c for _, c in sums)
    if isinstance(value, list):
        sums = [token_counts(item) for item in value]
        return sum(p for p, _ in sums), sum(c for _, c in sums)
    return 0, 0


def summarise_dataset(run: Path) -> dict:
    # The evaluator prints a format notice before its JSON result.
    printed = (run / "evaluation.json").read_text(encoding="utf-8") if (run / "evaluation.json").is_file() else ""
    evaluation = json.loads(printed[printed.find("{"):]) if "{" in printed else {}
    wall = json.loads((run / "run.json").read_text()).get("wall_seconds") if (run / "run.json").is_file() else None
    cases, calls, prompt, completion, errors, fallbacks = defaultdict(list), 0, 0, 0, 0, 0
    trace = run / "run-trace.jsonl.log.gz"
    if trace.is_file():
        with gzip.open(trace, "rt", encoding="utf-8") as handle:
            for line in handle:
                event = json.loads(line)
                cases[event.get("case_id")].append(datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00")))
                if event.get("event_type") == "model_call":
                    calls += 1
                    p, c = token_counts(event.get("output"))
                    prompt, completion = prompt + p, completion + c
                if event.get("status") == "error":
                    errors += 1
                if event.get("event_type") == "decision" and (event.get("status") == "error" or "fallback" in json.dumps(event.get("output"), ensure_ascii=False).lower()):
                    fallbacks += 1
    durations = [(max(times) - min(times)).total_seconds() for case, times in cases.items() if case != "-"]
    count = max(len(durations), 1)
    return {
        "accuracy": evaluation.get("accuracy"),
        "invalid_log_lines": evaluation.get("invalid_log_lines"),
        "wall_seconds": wall,
        "max_case_seconds": round(max(durations), 1) if durations else None,
        "calls_per_case": round(calls / count, 1),
        "tokens_per_case": round((prompt + completion) / count),
        "error_events": errors,
        "fallback_decisions": fallbacks,
    }


def main() -> None:
    print("| System | trip | proc | exp | total | wall s (3 runs) | max s/case | calls/case | tokens/case | error events | fallbacks |")
    print("|---|---|---|---|---|---|---|---|---|---|---|")
    for system in map(Path, sys.argv[1:]):
        rows = {dataset: summarise_dataset(system / dataset) for dataset in DATASETS if (system / dataset).is_dir()}
        sizes = {"business-trip-spot-check": 5, "task-2-procurement-spot-check": 8, "task-2-expense-reimbursement-spot-check": 8}
        correct = sum(round((row["accuracy"] or 0) * sizes[name]) for name, row in rows.items())
        total = sum(sizes[name] for name in rows)
        cells = [f"{rows[d]['accuracy']:.2f}" if d in rows and rows[d]["accuracy"] is not None else "-" for d in DATASETS]
        weighted = lambda key: round(sum(rows[d][key] * sizes[d] for d in rows) / max(total, 1), 1)  # noqa: E731
        print(
            f"| {system.name} | {' | '.join(cells)} | {correct}/{total} | {sum(row['wall_seconds'] or 0 for row in rows.values())} "
            f"| {max((row['max_case_seconds'] or 0) for row in rows.values())} | {weighted('calls_per_case')} | {round(weighted('tokens_per_case'))} "
            f"| {sum(row['error_events'] for row in rows.values())} | {sum(row['fallback_decisions'] for row in rows.values())} |"
        )


if __name__ == "__main__":
    main()
