"""TREC run files: `qid Q0 docno rank score tag`, gzip-compressed."""

import gzip
from pathlib import Path

from uniretrieval.fusion import Ranking


def validated(rankings: dict[str, Ranking], qids: list[str], fallback_doc_id: str, depth: int) -> dict[str, Ranking]:
    """At most `depth` unique documents per query, strictly decreasing scores,
    and every query present (a query without results gets `fallback_doc_id`)."""
    result = {}
    for qid in qids:
        seen, ranking = set(), []
        for doc_id, _ in rankings.get(qid, []):
            if doc_id not in seen:
                seen.add(doc_id)
                ranking.append(doc_id)
            if len(ranking) == depth:
                break
        ranking = ranking or [fallback_doc_id]
        result[qid] = [(doc_id, float(len(ranking) - rank)) for rank, doc_id in enumerate(ranking)]
    return result


def write_run(path: Path, rankings: dict[str, Ranking], tag: str) -> None:
    temporary = Path(path).with_suffix(".tmp")
    with gzip.open(temporary, "wt", encoding="utf-8") as handle:
        for qid, ranking in rankings.items():
            for rank, (doc_id, score) in enumerate(ranking, start=1):
                handle.write(f"{qid} Q0 {doc_id} {rank} {score:.4f} {tag}\n")
    temporary.replace(path)


def read_run(path: Path) -> dict[str, Ranking]:
    opener = gzip.open if str(path).endswith(".gz") else open
    rankings: dict[str, Ranking] = {}
    with opener(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            parts = line.split()
            if len(parts) >= 5:
                rankings.setdefault(parts[0], []).append((parts[2], float(parts[4])))
    # File order, as the official evaluator (tira -> trectools get_ndcg) uses it:
    # it does not re-sort by score, which matters for runs with tied scores.
    return rankings
