#!/usr/bin/env python3
"""UniAgent 2026 Task 2: decide every case under --input as angenommen/abgelehnt.

Writes predictions.jsonl, run-trace.jsonl.log.gz (event-logging contract) and
run-stats.json (seconds and tokens per case) to --output.
"""

import argparse
import contextvars
import json
import os
import threading
import time
from pathlib import Path

from solver.checks.common import Finding
from solver.config import Settings
from solver.decide import Decision, fallback_decision
from solver.discovery import discover_corpora, input_cases
from solver.event_log import case_context, log_event, log_to_file, model_context
from solver.llm import ChatModel, OpenAIChatModel
from solver.pipeline import solve_case
from solver.retrieval import Retriever


def parse_settings() -> tuple[argparse.Namespace, Settings]:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--no-checks", action="store_true", help="ablation: model decides without deterministic checks")
    parser.add_argument("--no-retrieval", action="store_true", help="ablation: curated rule texts only, no corpus look-up")
    parser.add_argument("--no-hard-fail-override", action="store_true", help="let the model overrule hard check failures")
    parser.add_argument("--self-consistency", type=int, default=1, help="decision samples when a check stays unclear")
    parser.add_argument("--case-timeout", type=float, default=Settings.case_timeout_seconds)
    args = parser.parse_args()
    settings = Settings(
        use_checks=not args.no_checks,
        use_retrieval=not args.no_retrieval,
        hard_fail_override=not args.no_hard_fail_override,
        self_consistency_n=args.self_consistency,
        case_timeout_seconds=args.case_timeout,
        reasoning_effort=os.environ.get("OPENAI_REASONING_EFFORT", "").strip() or None,
        cache_dir=os.environ.get("SOLVER_CACHE_DIR", "").strip() or None,
    )
    return args, settings


def solve_with_watchdog(case: Path, llm: ChatModel | None, retriever: Retriever | None, settings: Settings, time_budget: float) -> tuple[Decision, list[Finding]]:
    """solve_case in a worker thread; if it overruns its deadline by the grace period, fall back and move on."""
    outcome: list[tuple[Decision, list[Finding]]] = []
    context = contextvars.copy_context()
    worker = threading.Thread(target=context.run, args=(lambda: outcome.append(solve_case(case, llm, retriever, settings, time_budget)),), daemon=True)
    worker.start()
    worker.join(min(settings.case_timeout_seconds, time_budget) + settings.watchdog_grace_seconds)
    if outcome:
        return outcome[0]
    log_event("error", input={"case_id": case.name}, status="error", error="Case watchdog: no decision within the time budget")
    return fallback_decision([], "Zeitlimit"), []


def main() -> None:
    args, settings = parse_settings()
    started = time.monotonic()
    llm = OpenAIChatModel(settings.max_output_tokens, settings.temperature, settings.llm_max_retries, settings.reasoning_effort, settings.cache_dir)
    cases = input_cases(args.input.resolve())
    args.output.mkdir(parents=True, exist_ok=True)
    stats = {"settings": settings.__dict__, "model": llm.model_id, "cases": {}}

    with log_to_file(args.output / "run-trace.jsonl.log.gz"), model_context(llm.model_id):
        print(f"{len(cases)} case(s): {', '.join(case.name for case in cases)}", flush=True)
        retriever = None
        if settings.use_retrieval:
            corpora = discover_corpora(args.input.resolve())
            index_started = time.monotonic()
            try:
                retriever = Retriever.build(corpora)
                log_event("tool_call", tool="build_index", input={"corpora": sorted(corpora)}, output={"seconds": round(time.monotonic() - index_started, 1)})
            except Exception as error:
                log_event("tool_call", tool="build_index", input={"corpora": sorted(corpora)}, status="error", error=str(error))
            stats["index_seconds"] = round(time.monotonic() - index_started, 1)
            print(f"Indexed {len(corpora)} corpora in {stats['index_seconds']} s", flush=True)

        with (args.output / "predictions.jsonl").open("w", encoding="utf-8") as predictions:
            for position, case in enumerate(cases):
                case_started = time.monotonic()
                usage_before = llm.usage.as_dict()
                # Share what is left of the run budget fairly among the remaining cases.
                remaining = settings.total_budget_seconds - (case_started - started)
                time_budget = max(remaining / (len(cases) - position), 0)
                with case_context(case.name):
                    decision, findings = solve_with_watchdog(case, llm if time_budget > 15 else None, retriever, settings, time_budget)
                    line = {"antrag": case.name, "result": decision.result, "begruendung": decision.begruendung}
                    log_event(
                        "decision",
                        output={
                            # decision/answer/evidence as named by the event-logging contract, plus the prediction line.
                            "decision": decision.result,
                            "answer": decision.begruendung,
                            "evidence": decision.belege,
                            **line,
                            "method": decision.method,
                            "findings": [finding.as_dict() for finding in findings],
                        },
                        status="error" if decision.method.startswith("fallback") else "ok",
                        error=decision.method if decision.method.startswith("fallback") else None,
                    )
                predictions.write(json.dumps(line, ensure_ascii=False) + "\n")
                predictions.flush()
                usage_after = llm.usage.as_dict()
                stats["cases"][case.name] = {
                    "result": decision.result,
                    "method": decision.method,
                    "seconds": round(time.monotonic() - case_started, 1),
                    **{key: usage_after[key] - usage_before[key] for key in usage_after},
                    "failed_checks": [finding.rule_id for finding in findings if finding.status == "fail"],
                }
                print(f"  {case.name}: {decision.result} [{decision.method}] {stats['cases'][case.name]['seconds']} s", flush=True)

    stats["total_seconds"] = round(time.monotonic() - started, 1)
    stats["usage"] = llm.usage.as_dict()
    (args.output / "run-stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Done in {stats['total_seconds']} s; usage {stats['usage']}", flush=True)


if __name__ == "__main__":
    main()
