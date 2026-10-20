"""Evaluation measures (trec_eval conventions), a paired randomization test, and qrels IO.

nDCG uses linear gains and log2 discounts; queries without relevant documents
in the qrels are skipped, queries missing from a run count as 0."""

import math
import random
from pathlib import Path

from uniretrieval.fusion import Ranking

Qrels = dict[str, dict[str, int]]


def read_qrels(path: Path) -> Qrels:
    qrels: Qrels = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) >= 4:
            qrels.setdefault(parts[0], {})[parts[2]] = int(parts[3])
    return qrels


def ndcg(ranking: list[str], judgments: dict[str, int], depth: int) -> float:
    gains = sorted((grade for grade in judgments.values() if grade > 0), reverse=True)[:depth]
    ideal = sum(gain / math.log2(rank + 2) for rank, gain in enumerate(gains))
    if ideal == 0:
        return 0.0
    actual = sum(max(judgments.get(doc_id, 0), 0) / math.log2(rank + 2) for rank, doc_id in enumerate(ranking[:depth]))
    return actual / ideal


def reciprocal_rank(ranking: list[str], judgments: dict[str, int], depth: int) -> float:
    for rank, doc_id in enumerate(ranking[:depth], start=1):
        if judgments.get(doc_id, 0) > 0:
            return 1.0 / rank
    return 0.0


def recall(ranking: list[str], judgments: dict[str, int], depth: int) -> float:
    relevant = {doc_id for doc_id, grade in judgments.items() if grade > 0}
    return len(relevant & set(ranking[:depth])) / len(relevant) if relevant else 0.0


MEASURES = {
    "nDCG@10": lambda ranking, judgments: ndcg(ranking, judgments, 10),
    "nDCG@20": lambda ranking, judgments: ndcg(ranking, judgments, 20),
    "MRR@10": lambda ranking, judgments: reciprocal_rank(ranking, judgments, 10),
    "R@100": lambda ranking, judgments: recall(ranking, judgments, 100),
    "R@1000": lambda ranking, judgments: recall(ranking, judgments, 1000),
}


def per_query(run: dict[str, Ranking], qrels: Qrels) -> dict[str, dict[str, float]]:
    results = {}
    for qid, judgments in qrels.items():
        if not any(grade > 0 for grade in judgments.values()):
            continue
        ranking = [doc_id for doc_id, _ in run.get(qid, [])]
        results[qid] = {name: measure(ranking, judgments) for name, measure in MEASURES.items()}
    return results


def mean(per_query_results: dict[str, dict[str, float]]) -> dict[str, float]:
    if not per_query_results:
        return {name: 0.0 for name in MEASURES}
    return {name: sum(values[name] for values in per_query_results.values()) / len(per_query_results) for name in MEASURES}


def randomization_test(first: list[float], second: list[float], trials: int = 10000, seed: int = 0) -> float:
    """Two-sided p-value of the mean difference of paired per-query scores."""
    if len(first) != len(second):
        raise ValueError("Paired scores must have equal length.")
    differences = [a - b for a, b in zip(first, second)]
    observed = abs(sum(differences))
    generator = random.Random(seed)
    extreme = sum(
        1 for _ in range(trials) if abs(sum(difference if generator.random() < 0.5 else -difference for difference in differences)) >= observed - 1e-12
    )
    return (extreme + 1) / (trials + 1)
