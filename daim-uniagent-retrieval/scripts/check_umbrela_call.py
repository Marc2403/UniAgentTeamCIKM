#!/usr/bin/env python3
"""Replay the organisers' UMBRELA 0.0.7 call and count how often it yields no usable grade.

UMBRELA's GPTJudge.run_gpt sends the system prompt "You are a helpful
assistant.", the prompt, and max_tokens=100, nothing else; the passage is the
full document text. For the top-k documents of a run on each spot-check this
records finish reason, empty content, and whether UMBRELA's own parser finds a
grade. Raw answers go to --output (JSONL)."""

import gzip
import json
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import click

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from uniretrieval.llm import raw_chat, required_environment  # noqa: E402
from uniretrieval.rerank_llm import UMBRELA_PROMPT, parse_grade, parse_grade_umbrela  # noqa: E402
from uniretrieval.run_io import read_run  # noqa: E402

SYSTEM_PROMPT = "You are a helpful assistant."


def texts(dataset: Path, wanted: set[str]) -> dict[str, str]:
    found = {}
    with gzip.open(dataset / "documents.jsonl.gz", "rt", encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            if record["doc_id"] in wanted:
                found[record["doc_id"]] = record["text"]
    return found


@click.command()
@click.option("--dataset", "datasets", multiple=True, required=True, type=click.Path(path_type=Path, exists=True, file_okay=False))
@click.option("--runs", default=Path("runs"), type=click.Path(path_type=Path, file_okay=False), show_default=True)
@click.option("--run-config", default="lexical-plus", show_default=True)
@click.option("--k", "depth", default=5, show_default=True)
@click.option("--max-tokens", default=100, show_default=True)
@click.option("--output", required=True, type=click.Path(path_type=Path, dir_okay=False))
def main(datasets, runs: Path, run_config: str, depth: int, max_tokens: int, output: Path) -> None:
    from openai import OpenAI

    base_url, api_key, model = required_environment()
    client = OpenAI(base_url=base_url, api_key=api_key, timeout=120, max_retries=3)

    requests = []
    for dataset in datasets:
        queries = {str(json.loads(line)["qid"]): json.loads(line)["query"] for line in (dataset / "queries.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()}
        run = read_run(runs / dataset.name / run_config / "run.txt.gz")
        pairs = [(qid, doc_id) for qid in queries for doc_id, _ in run.get(qid, [])[:depth]]
        documents = texts(dataset, {doc_id for _, doc_id in pairs})
        requests += [(dataset.name, qid, doc_id, UMBRELA_PROMPT.format(query=queries[qid], passage=documents[doc_id])) for qid, doc_id in pairs]

    def call(request):
        dataset, qid, doc_id, prompt = request
        entry = {"dataset": dataset, "qid": qid, "doc_id": doc_id, "prompt_chars": len(prompt)}
        try:
            entry.update(raw_chat(client, model, [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}], max_tokens=max_tokens), error=None)
        except Exception as error:
            entry["error"] = f"{type(error).__name__}: {error}"
        return entry

    with ThreadPoolExecutor(max_workers=8) as executor:
        entries = list(executor.map(call, requests))
    output.write_text("".join(json.dumps(entry, ensure_ascii=False) + "\n" for entry in entries), encoding="utf-8")

    ok = [entry for entry in entries if entry["error"] is None]
    summary = {
        "model": model,
        "max_tokens": max_tokens,
        "calls": len(entries),
        "api_errors": len(entries) - len(ok),
        "finish_reason": dict(Counter(entry["finish_reason"] for entry in ok)),
        "empty_content": sum(1 for entry in ok if not entry["content"].strip()),
        "truncated_with_empty_content": sum(1 for entry in ok if entry["finish_reason"] == "length" and not entry["content"].strip()),
        "umbrela_parser_finds_grade": sum(1 for entry in ok if parse_grade_umbrela(entry["content"])[1]),
        "robust_parser_finds_grade": sum(1 for entry in ok if parse_grade(entry["content"]) is not None),
        "completion_tokens_mean": round(sum(entry["usage"]["completion_tokens"] for entry in ok) / max(len(ok), 1), 1),
        "prompt_tokens_total": sum(entry["usage"]["prompt_tokens"] for entry in ok),
        "per_dataset": {
            dataset.name: {
                "calls": sum(1 for entry in ok if entry["dataset"] == dataset.name),
                "empty_content": sum(1 for entry in ok if entry["dataset"] == dataset.name and not entry["content"].strip()),
                "umbrela_parser_finds_grade": sum(1 for entry in ok if entry["dataset"] == dataset.name and parse_grade_umbrela(entry["content"])[1]),
            }
            for dataset in datasets
        },
    }
    click.echo(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
