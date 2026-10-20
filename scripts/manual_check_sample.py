#!/usr/bin/env python3
"""Blind manual check of the LLM judge: sample query-document pairs that only
one of two configs ranks in its top 10, and build an offline grading page.

Writes eval/manual_check/check.html (shows only query, description,
narrative and the document's title, URL and text, in random order) and
eval/manual_check/key.json (pair id -> config, rank, LLM grades, doc_id).

Sampling: 30 pairs, 15 per config, at most one per query; every collection
(de/en/law) and origin (spot/dev/extra) gets 10 pairs: three strata on a
random diagonal get 4 pairs (2 + 2), the other six get 3 (2 + 1, alternating
which config gets two)."""

import gzip
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from uniretrieval.metrics import read_qrels  # noqa: E402
from uniretrieval.run_io import read_run  # noqa: E402

SEED = 20261001
CONFIGS = ("llm-k30", "lexical-plus")
COLLECTIONS = ("de", "en", "law")
ORIGINS = ("spot", "dev", "extra")
RUNS = {
    ("de", "spot"): "retrieval-de-spot-check",
    ("en", "spot"): "retrieval-en-spot-check",
    ("law", "spot"): "retrieval-hessian-law-de-spot-check",
    **{(c, "dev"): f"devset-{c}" for c in COLLECTIONS},
    **{(c, "extra"): f"devset-{c}-extra" for c in COLLECTIONS},
}
DOCUMENTS = {
    "de": "retrieval-de-spot-check",
    "en": "retrieval-en-spot-check",
    "law": "retrieval-hessian-law-de-spot-check",
}
OUTPUT = ROOT / "eval" / "manual_check"
TEMPLATE = Path(__file__).with_name("manual_check_template.html")


def allocation(generator: random.Random) -> dict[tuple[str, str], dict[str, int]]:
    """Pairs per stratum and config: 10 per collection, 10 per origin, 15 per config."""
    origins = list(ORIGINS)
    generator.shuffle(origins)
    diagonal = {(collection, origins[index]) for index, collection in enumerate(COLLECTIONS)}
    plan, extra_for_first = {}, True
    for collection in COLLECTIONS:
        for origin in ORIGINS:
            if (collection, origin) in diagonal:
                plan[(collection, origin)] = {CONFIGS[0]: 2, CONFIGS[1]: 2}
            else:
                first = 2 if extra_for_first else 1
                plan[(collection, origin)] = {CONFIGS[0]: first, CONFIGS[1]: 3 - first}
                extra_for_first = not extra_for_first
    return plan


def reranker_grades(trace_path: Path) -> dict[tuple[str, str], int]:
    grades = {}
    with gzip.open(trace_path, "rt", encoding="utf-8") as handle:
        for event in map(json.loads, handle):
            output = event.get("output") or {}
            if event["event_type"] == "model_call" and "grade" in output:
                grades[(event["case_id"], event["input"]["doc_id"])] = output["grade"]
    return grades


def documents(collection: str, wanted: set[str]) -> dict[str, dict]:
    found = {}
    path = ROOT.parent / "uniagent-code" / "cikm26" / "datasets" / DOCUMENTS[collection] / "documents.jsonl.gz"
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for record in map(json.loads, handle):
            if record["doc_id"] in wanted:
                found[record["doc_id"]] = record
    return found


def main() -> None:
    generator = random.Random(SEED)
    topics = [json.loads(line) for line in (ROOT / "eval" / "combined" / "topics.jsonl").read_text(encoding="utf-8").splitlines()]
    qrels = read_qrels(ROOT / "eval" / "combined" / "qrels.txt")
    plan = allocation(generator)

    chosen = []
    for (collection, origin), per_config in plan.items():
        run_directory = ROOT / "runs" / RUNS[(collection, origin)]
        rankings = {config: read_run(run_directory / config / "run.txt.gz") for config in CONFIGS}
        stratum = [topic for topic in topics if topic["collection"] == collection and topic["origin"] == origin]
        generator.shuffle(stratum)
        demand = [config for config in CONFIGS for _ in range(per_config[config])]
        generator.shuffle(demand)
        for config in demand:
            other = CONFIGS[1 - CONFIGS.index(config)]
            for topic in stratum:
                if any(pair["topic"]["id"] == topic["id"] for pair in chosen):
                    continue
                own = [doc_id for doc_id, _ in rankings[config].get(topic["qid"], [])[:10]]
                theirs = {doc_id for doc_id, _ in rankings[other].get(topic["qid"], [])[:10]}
                unique = [doc_id for doc_id in own if doc_id not in theirs]
                if unique:
                    doc_id = generator.choice(unique)
                    chosen.append({"topic": topic, "config": config, "doc_id": doc_id, "rank": own.index(doc_id) + 1, "run_directory": run_directory})
                    break
            else:
                raise SystemExit(f"No candidate left for {config} in {collection}/{origin}.")

    generator.shuffle(chosen)
    texts = {}
    for collection in COLLECTIONS:
        texts.update(documents(collection, {pair["doc_id"] for pair in chosen if pair["topic"]["collection"] == collection}))
    trace_grades = {}
    for run_directory in {pair["run_directory"] for pair in chosen}:
        trace_grades[run_directory] = reranker_grades(run_directory / "llm-k30" / "run-trace.jsonl.log.gz")

    pages, key = [], {}
    for number, pair in enumerate(chosen, start=1):
        pair_id = f"P{number:02d}"
        topic, document = pair["topic"], texts[pair["doc_id"]]
        pages.append(
            {
                "id": pair_id,
                "query": topic["query"],
                "description": topic["description"],
                "narrative": topic["narrative"],
                "title": document.get("title", ""),
                "url": document.get("url", ""),
                "text": document.get("content") or document.get("text", ""),
            }
        )
        key[pair_id] = {
            "topic": topic["id"],
            "config": pair["config"],
            "rank": pair["rank"],
            "doc_id": pair["doc_id"],
            "judge_grade": qrels[topic["id"]].get(pair["doc_id"]),
            "reranker_grade": trace_grades[pair["run_directory"]].get((topic["qid"], pair["doc_id"])),
        }

    OUTPUT.mkdir(parents=True, exist_ok=True)
    data = json.dumps(pages, ensure_ascii=False).replace("</", "<\\/")
    (OUTPUT / "check.html").write_text(TEMPLATE.read_text(encoding="utf-8").replace("__PAIRS__", data), encoding="utf-8")
    (OUTPUT / "key.json").write_text(json.dumps({"seed": SEED, "pairs": key}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(pages)} pairs -> {OUTPUT / 'check.html'}; key in {OUTPUT / 'key.json'}")


if __name__ == "__main__":
    main()
