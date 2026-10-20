#!/usr/bin/env python3
"""One evaluation over spot-check, dev and dev-extra queries with UMBRELA qrels.

Writes eval/combined/{qrels.txt,topics.jsonl} (ids <collection>:<origin>:<qid>)
and eval/results-combined.md: nDCG@10 overall and per collection / origin
with paired randomization tests, a repeated stratified 5-fold
cross-validation of choosing the best config, and LLM cost per query."""

import gzip
import json
import random
import re
import statistics
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from uniretrieval.devsets import included_query_lines  # noqa: E402
from uniretrieval.metrics import ndcg, randomization_test, read_qrels  # noqa: E402
from uniretrieval.run_io import read_run  # noqa: E402

CONFIGS = ["dph", "lexical-plus", "ce-minilm", "llm-k10", "llm-k20", "llm-k20-desc", "llm-k30"]
REFERENCES = ["lexical-plus", "llm-k20"]
LLM_CONFIGS = {"llm-k10": 10, "llm-k20": 20, "llm-k30": 30}
SETS = [  # collection, origin, runs, queries (qrels: <stem>.qrels.txt)
    ("de", "spot", "retrieval-de-spot-check", "eval/spotchecks/de/queries.jsonl"),
    ("en", "spot", "retrieval-en-spot-check", "eval/spotchecks/en/queries.jsonl"),
    ("law", "spot", "retrieval-hessian-law-de-spot-check", "eval/spotchecks/law/queries.jsonl"),
    ("de", "dev", "devset-de", "eval/devsets/de/queries.jsonl"),
    ("en", "dev", "devset-en", "eval/devsets/en/queries.jsonl"),
    ("law", "dev", "devset-law", "eval/devsets/law/queries.jsonl"),
    ("de", "extra", "devset-de-extra", "eval/devsets/de/dev-extra-de.jsonl"),
    ("en", "extra", "devset-en-extra", "eval/devsets/en/dev-extra-en.jsonl"),
    ("law", "extra", "devset-law-extra", "eval/devsets/law/dev-extra-law.jsonl"),
]
FOLDS, REPETITIONS = 5, 10
# Wall-clock LLM reranking of runs made without any cached answer (8 parallel
# requests to openai/gpt-oss-20b on OpenRouter): (run, seconds, calls).
UNCACHED_LATENCY = [
    ("retrieval-de-spot-check/llm-k10", 98.0, 249),
    ("retrieval-en-spot-check/llm-k10", 117.3, 249),
    ("retrieval-hessian-law-de-spot-check/llm-k10", 101.8, 150),
    ("retrieval-de-spot-check/llm-k20-desc", 156.4, 495),
    ("retrieval-en-spot-check/llm-k20-desc", 143.8, 492),
    ("retrieval-hessian-law-de-spot-check/llm-k20-desc", 74.6, 300),
]
PRICE_PER_TOKEN = {"prompt": 0.02e-6, "completion": 0.10e-6}  # OpenRouter list price, USD
PARAGRAPH_RE = re.compile(r"§\s*\d+")


def load():
    topics, qrels, scores, unjudged = {}, {}, {config: {} for config in CONFIGS}, Counter()
    tokens = {config: [] for config in LLM_CONFIGS}
    for collection, origin, runs, queries_file in SETS:
        queries_file = ROOT / queries_file
        set_qrels = read_qrels(queries_file.with_suffix(".qrels.txt"))
        for record in map(json.loads, included_query_lines(queries_file)):
            qid = str(record["qid"])
            if qid not in set_qrels:
                continue  # dropped: no document with grade >= 2
            topic_id = f"{collection}:{origin}:{qid}"
            original = record["original_query"]
            topics[topic_id] = {
                "id": topic_id, "collection": collection, "origin": origin, "qid": qid,
                "query": record["query"], "description": original.get("description", ""), "narrative": original.get("narrative", ""),
                "paragraph_in_narrative": bool(PARAGRAPH_RE.search(original.get("narrative", ""))),
            }
            qrels[topic_id] = set_qrels[qid]
        for config in CONFIGS:
            run = read_run(ROOT / "runs" / runs / config / "run.txt.gz")
            for topic_id in (t for t in topics if t.startswith(f"{collection}:{origin}:")):
                ranking = [doc_id for doc_id, _ in run.get(topics[topic_id]["qid"], [])]
                scores[config][topic_id] = ndcg(ranking, qrels[topic_id], 10)
                unjudged[config] += sum(doc_id not in qrels[topic_id] for doc_id in ranking[:10])
        for config in LLM_CONFIGS:
            per_query = Counter()
            with gzip.open(ROOT / "runs" / runs / config / "run-trace.jsonl.log.gz", "rt", encoding="utf-8") as handle:
                for event in map(json.loads, handle):
                    usage = (event.get("output") or {}).get("usage") if event["event_type"] == "model_call" else None
                    if usage:
                        per_query[(event["case_id"], "prompt")] += usage["prompt_tokens"]
                        per_query[(event["case_id"], "completion")] += usage["completion_tokens"]
            for topic_id in (t for t in topics if t.startswith(f"{collection}:{origin}:")):
                qid = topics[topic_id]["qid"]
                tokens[config].append((per_query[(qid, "prompt")], per_query[(qid, "completion")]))
    return topics, qrels, scores, unjudged, tokens


def mean(values):
    values = list(values)
    return sum(values) / len(values) if values else float("nan")


def cell(scores, config, ids):
    value = mean(scores[config][i] for i in ids)
    tests = []
    for reference in REFERENCES:
        if reference == config:
            tests.append("–")
        else:
            tests.append(f"{randomization_test([scores[config][i] for i in ids], [scores[reference][i] for i in ids]):.2f}")
    return f"{value:.3f} ({'/'.join(tests)})"


def folds(topics, seed):
    """Stratified by (collection, origin): shuffle each stratum, deal ids round-robin."""
    generator, assignment, position = random.Random(seed), {}, 0
    for stratum in sorted({(t["collection"], t["origin"]) for t in topics.values()}):
        ids = sorted(i for i, t in topics.items() if (t["collection"], t["origin"]) == stratum)
        generator.shuffle(ids)
        for topic_id in ids:
            assignment[topic_id] = position % FOLDS
            position += 1
    return assignment


def cross_validate(topics, scores):
    estimates, chosen = [], Counter()
    for seed in range(REPETITIONS):
        assignment = folds(topics, seed)
        tested = {}
        for fold in range(FOLDS):
            train = [i for i, f in assignment.items() if f != fold]
            test = [i for i, f in assignment.items() if f == fold]
            best = max(CONFIGS, key=lambda config: mean(scores[config][i] for i in train))
            chosen[best] += 1
            tested.update({i: scores[best][i] for i in test})
        estimates.append(mean(tested.values()))
    return estimates, chosen


def table(title, groups, scores):
    header = "| config | " + " | ".join(f"{name} (n={len(ids)})" for name, ids in groups) + " |"
    lines = [f"### {title}", "", header, "|" + "---|" * (len(groups) + 1)]
    lines += ["| " + config + " | " + " | ".join(cell(scores, config, ids) for _, ids in groups) + " |" for config in CONFIGS]
    return lines + [""]


def main() -> None:
    topics, qrels, scores, unjudged, tokens = load()
    combined = ROOT / "eval" / "combined"
    combined.mkdir(parents=True, exist_ok=True)
    (combined / "topics.jsonl").write_text("".join(json.dumps(t, ensure_ascii=False) + "\n" for t in topics.values()), encoding="utf-8")
    (combined / "qrels.txt").write_text(
        "".join(f"{i} 0 {doc_id} {grade}\n" for i in topics for doc_id, grade in sorted(qrels[i].items())), encoding="utf-8"
    )

    ids = list(topics)
    by = lambda key, value: [i for i in ids if topics[i][key] == value]  # noqa: E731
    law = by("collection", "law")
    lines = [
        "# Combined evaluation: spot-check, dev and dev-extra queries with UMBRELA qrels",
        "",
        f"{len(ids)} queries ({', '.join(f'{c}: {len(by('collection', c))}' for c in ('de', 'en', 'law'))}; "
        f"{', '.join(f'{o}: {len(by('origin', o))}' for o in ('spot', 'dev', 'extra'))}). "
        "Qrels: gpt-oss-20b with the unchanged UMBRELA 0.0.7 prompt, robust parser, over the top-10 of all configs "
        "(spot-checks: plus the organisers' relevant document). nDCG@10; in brackets two-sided paired randomization "
        "test p-values against lexical-plus / llm-k20.",
        "",
        "Unjudged documents in the top 10: " + ", ".join(f"{c} {unjudged[c]}" for c in CONFIGS) + ".",
        "",
    ]
    lines += table("Overall and per collection", [("all", ids)] + [(c, by("collection", c)) for c in ("de", "en", "law")], scores)
    lines += table("Per origin", [(o, by("origin", o)) for o in ("spot", "dev", "extra")], scores)
    lines += table(
        "Law: spot-check vs. dev/extra, and § reference in the narrative",
        [
            ("law spot", [i for i in law if topics[i]["origin"] == "spot"]),
            ("law dev+extra", [i for i in law if topics[i]["origin"] != "spot"]),
            ("law with §", [i for i in law if topics[i]["paragraph_in_narrative"]]),
            ("law without §", [i for i in law if not topics[i]["paragraph_in_narrative"]]),
        ],
        scores,
    )

    estimates, chosen = cross_validate(topics, scores)
    lines += [
        f"### Cross-validation ({FOLDS}-fold, stratified by collection × origin, {REPETITIONS} seeds)",
        "",
        "Each round picks the config with the best mean nDCG@10 on the 4 training folds and scores it on the test fold.",
        "",
        f"- Selection procedure: **{statistics.mean(estimates):.3f} ± {statistics.stdev(estimates):.3f}** (mean ± sd over repetitions)",
        "- Chosen in " + f"{FOLDS * REPETITIONS} rounds: " + ", ".join(f"{c} {n}×" for c, n in chosen.most_common()),
        "- Fixed config (all queries): " + ", ".join(f"{c} {mean(scores[c].values()):.3f}" for c in CONFIGS),
        "",
    ]

    seconds_per_call = [seconds / calls for _, seconds, calls in UNCACHED_LATENCY]
    lines += [
        "### LLM reranking cost without cache",
        "",
        f"Tokens: from the run traces (cached answers keep their original usage), mean over all {len(ids)} queries. "
        f"Time: measured wall clock per call in uncached runs with 8 parallel requests, "
        f"{min(seconds_per_call):.2f}–{max(seconds_per_call):.2f} s (mean {mean(seconds_per_call):.2f} s), times depth. "
        "Price: OpenRouter list price for openai/gpt-oss-20b ($0.02 / $0.10 per million prompt / completion tokens).",
        "",
        "| config | prompt tokens/query | completion tokens/query | seconds/query | 50 queries: tokens | 50 queries: minutes | 50 queries: USD |",
        "|---|---|---|---|---|---|---|",
    ]
    for config, depth in LLM_CONFIGS.items():
        prompt = mean(p for p, _ in tokens[config])
        completion = mean(c for _, c in tokens[config])
        seconds = [depth * s for s in seconds_per_call]
        usd = 50 * (prompt * PRICE_PER_TOKEN["prompt"] + completion * PRICE_PER_TOKEN["completion"])
        lines.append(
            f"| {config} | {prompt:,.0f} | {completion:,.0f} | {mean(seconds):.1f} ({min(seconds):.1f}–{max(seconds):.1f}) | "
            f"{50 * (prompt + completion):,.0f} | {50 * mean(seconds) / 60:.1f} ({50 * min(seconds) / 60:.1f}–{50 * max(seconds) / 60:.1f}) | {usd:.3f} |"
        )
    original_grades = Counter()
    for collection, origin, runs, queries_file in SETS:
        if origin != "spot":
            continue
        organisers = read_qrels(ROOT.parent / "uniagent-code" / "cikm26" / "datasets" / runs / "qrels.txt")
        for qid, judgments in organisers.items():
            for doc_id in judgments:
                original_grades[qrels[f"{collection}:spot:{qid}"].get(doc_id, "unjudged")] += 1
    judged = [
        json.loads(line)
        for path in sorted((ROOT / "eval").glob("*/*/*.judgments.jsonl"))
        for line in path.read_text(encoding="utf-8").splitlines()
    ]
    prompt = sum(entry["usage"]["prompt_tokens"] for entry in judged if entry.get("usage"))
    completion = sum(entry["usage"]["completion_tokens"] for entry in judged if entry.get("usage"))
    lines += [
        "",
        "### Plausibility and judging cost",
        "",
        "- Grade of the organisers' relevant spot-check document in the new qrels: "
        + ", ".join(f"{grade}: {count}" for grade, count in sorted(original_grades.items(), key=str)),
        f"- All qrels: {len(judged):,} judgments, {prompt:,} prompt + {completion:,} completion tokens, "
        f"${prompt * PRICE_PER_TOKEN['prompt'] + completion * PRICE_PER_TOKEN['completion']:.2f} at list price.",
    ]
    report = "\n".join(lines) + "\n"
    (ROOT / "eval" / "results-combined.md").write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
