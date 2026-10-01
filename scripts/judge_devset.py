#!/usr/bin/env python3
"""Judge a dev set the way the organisers build qrels, but parse robustly.

Pools the top-k documents of every run under --runs for the non-excluded
queries of --queries, and asks OPENAI_MODEL the UMBRELA 0.0.7 prompt
(unchanged: system prompt "You are a helpful assistant.", keyword query,
full document text). Every raw answer goes to <stem>.judgments.jsonl
(resumable), so qrels can be recomputed with either parser:

  <stem>.qrels.txt                 robust parser (uniretrieval.rerank_llm.parse_grade)
  <stem>.qrels-umbrela-parser.txt  UMBRELA 0.0.7's parser (unparsed -> 0)

Queries without any document of grade >= 2 (robust parser) are left out of
both qrels files and listed in <stem>.dropped.txt."""

import gzip
import json
import sys
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import click

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from uniretrieval.devsets import included_query_lines, qrels_path  # noqa: E402
from uniretrieval.llm import raw_chat, required_environment  # noqa: E402
from uniretrieval.rerank_llm import UMBRELA_PROMPT, parse_grade, parse_grade_umbrela  # noqa: E402
from uniretrieval.run_io import read_run  # noqa: E402

SYSTEM_PROMPT = "You are a helpful assistant."


def document_texts(documents_directory: Path, wanted: set[str]) -> dict[str, str]:
    """The `text` field (what tira's loader returns as default_text()) of the wanted documents."""
    path = next(Path(documents_directory).glob("documents.jsonl*"))
    opener = gzip.open if path.suffix == ".gz" else open
    texts = {}
    with opener(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            if record["doc_id"] in wanted:
                texts[record["doc_id"]] = record.get("text") or f"{record.get('title', '')} {record.get('content', '')}"
    return texts


def pool(runs_directory: Path, qids: set[str], depth: int) -> dict[str, list[str]]:
    pooled: dict[str, set[str]] = {qid: set() for qid in qids}
    run_files = sorted(Path(runs_directory).glob("*/run.txt.gz"))
    if not run_files:
        raise click.ClickException(f"No runs below {runs_directory}.")
    for run_file in run_files:
        for qid, ranking in read_run(run_file).items():
            if qid in pooled:
                pooled[qid].update(doc_id for doc_id, _ in ranking[:depth])
    return {qid: sorted(doc_ids) for qid, doc_ids in pooled.items()}


def write_qrels(path: Path, grades: dict[tuple[str, str], int], qids: list[str]) -> None:
    lines = [f"{qid} 0 {doc_id} {grade}" for (qid, doc_id), grade in sorted(grades.items()) if qid in qids]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


@click.command()
@click.option("--documents", required=True, type=click.Path(path_type=Path, exists=True, file_okay=False))
@click.option("--queries", "queries_file", required=True, type=click.Path(path_type=Path, exists=True, dir_okay=False))
@click.option("--runs", required=True, type=click.Path(path_type=Path, exists=True, file_okay=False), help="runs/<dev set name>")
@click.option("--k", "depth", default=10, show_default=True)
@click.option("--max-tokens", default=4096, show_default=True, help="UMBRELA sends 100; gpt-oss spends most of that on reasoning.")
@click.option("--concurrency", default=8, show_default=True)
def main(documents: Path, queries_file: Path, runs: Path, depth: int, max_tokens: int, concurrency: int) -> None:
    from openai import OpenAI

    base_url, api_key, model = required_environment()
    client = OpenAI(base_url=base_url, api_key=api_key, timeout=120, max_retries=3)

    queries = {str(record["qid"]): record for record in map(json.loads, included_query_lines(queries_file))}
    pooled = pool(runs, set(queries), depth)
    texts = document_texts(documents, {doc_id for doc_ids in pooled.values() for doc_id in doc_ids})

    judgments_path = queries_file.with_suffix(".judgments.jsonl")
    done = set()
    if judgments_path.is_file():
        for line in judgments_path.read_text(encoding="utf-8").splitlines():
            entry = json.loads(line)
            if entry.get("error") is None:
                done.add((entry["qid"], entry["doc_id"]))
    todo = [(qid, doc_id) for qid, doc_ids in pooled.items() for doc_id in doc_ids if (qid, doc_id) not in done]
    click.echo(f"{len(queries)} queries, {sum(map(len, pooled.values()))} pooled pairs, {len(todo)} to judge")

    lock = threading.Lock()

    def judge(pair: tuple[str, str]) -> None:
        qid, doc_id = pair
        prompt = UMBRELA_PROMPT.format(query=queries[qid]["query"], passage=texts[doc_id])
        messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}]
        entry = {"qid": qid, "doc_id": doc_id, "model": model, "max_tokens": max_tokens}
        try:
            entry.update(raw_chat(client, model, messages, max_tokens=max_tokens), error=None)
        except Exception as error:
            entry["error"] = f"{type(error).__name__}: {error}"
        with lock, judgments_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        list(executor.map(judge, todo))

    robust: dict[tuple[str, str], int] = {}
    umbrela: dict[tuple[str, str], int] = {}
    unparsed = Counter()
    for line in judgments_path.read_text(encoding="utf-8").splitlines():
        entry = json.loads(line)
        key = (entry["qid"], entry["doc_id"])
        if entry.get("error") is not None or entry["qid"] not in queries or entry["doc_id"] not in pooled[entry["qid"]]:
            continue
        grade = parse_grade(entry["content"])
        if grade is None:
            unparsed["robust"] += 1
        robust[key] = grade if grade is not None else 0
        umbrela_grade, parsed = parse_grade_umbrela(entry["content"])
        unparsed["umbrela"] += not parsed
        umbrela[key] = umbrela_grade

    missing = [pair for pair in ((qid, doc_id) for qid, doc_ids in pooled.items() for doc_id in doc_ids) if pair not in robust]
    kept = sorted(qid for qid in queries if any(robust.get((qid, doc_id), 0) >= 2 for doc_id in pooled[qid]))
    dropped = sorted(set(queries) - set(kept))
    write_qrels(qrels_path(queries_file), robust, kept)
    write_qrels(queries_file.with_suffix(".qrels-umbrela-parser.txt"), umbrela, kept)
    queries_file.with_suffix(".dropped.txt").write_text("".join(f"{qid}\n" for qid in dropped), encoding="utf-8")

    click.echo(f"judged {len(robust)} pairs; still missing (errors): {len(missing)}")
    click.echo(f"unparsed answers: robust parser {unparsed['robust']}, UMBRELA 0.0.7 parser {unparsed['umbrela']}")
    click.echo(f"kept {len(kept)} queries, dropped {len(dropped)} without any grade >= 2: {' '.join(dropped)}")
    click.echo("grade distribution (robust): " + str(dict(sorted(Counter(robust.values()).items()))))


if __name__ == "__main__":
    main()
