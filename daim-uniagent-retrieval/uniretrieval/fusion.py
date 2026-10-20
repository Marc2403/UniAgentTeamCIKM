"""Rank fusion. A ranking is a list of (doc_id, score), best first."""

Ranking = list[tuple[str, float]]


def reciprocal_rank_fusion(rankings: list[Ranking], weights: list[float] | None = None, k: int = 60) -> Ranking:
    weights = weights if weights is not None else [1.0] * len(rankings)
    if len(weights) != len(rankings):
        raise ValueError("Need exactly one weight per ranking.")
    scores: dict[str, float] = {}
    for ranking, weight in zip(rankings, weights):
        for rank, (doc_id, _) in enumerate(ranking, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + weight / (k + rank)
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))


def rerank_head(ranking: Ranking, head_ranking: Ranking, weight: float, k: int = 60) -> Ranking:
    """Fuse a reranker's ordering of the head of `ranking` with the head's
    current ordering; the tail below the head keeps its order."""
    head_ids = {doc_id for doc_id, _ in head_ranking}
    head = [(doc_id, score) for doc_id, score in ranking if doc_id in head_ids]
    tail = [(doc_id, score) for doc_id, score in ranking if doc_id not in head_ids]
    fused = reciprocal_rank_fusion([head, head_ranking], [1.0, weight], k)
    return rescore(fused + tail)


def rescore(ranking: Ranking) -> Ranking:
    """Replace scores by strictly decreasing values that encode the order."""
    size = len(ranking)
    return [(doc_id, float(size - rank)) for rank, (doc_id, _) in enumerate(ranking)]
