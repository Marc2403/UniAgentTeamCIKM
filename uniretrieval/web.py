"""Web-collection post-processing: near-duplicate demotion and document priors.

Near duplicates are found at query time among the head of each ranking with
exact word-shingle Jaccard similarity (at most `window` documents, so a
MinHash index is unnecessary)."""

import re

from uniretrieval.data import Document
from uniretrieval.fusion import Ranking


def shingles(text: str, size: int, max_words: int = 3000) -> frozenset[int]:
    words = text.lower().split()[:max_words]
    if len(words) < size:
        return frozenset([hash(" ".join(words))])
    return frozenset(hash(" ".join(words[start : start + size])) for start in range(len(words) - size + 1))


def jaccard(first: frozenset, second: frozenset) -> float:
    if not first or not second:
        return 0.0
    return len(first & second) / len(first | second)


class NearDuplicateFilter:
    def __init__(self, documents: dict[str, Document], threshold: float, window: int, shingle_words: int) -> None:
        self.documents = documents
        self.threshold = threshold
        self.window = window
        self.shingle_words = shingle_words
        self._shingles: dict[str, frozenset[int]] = {}

    def _of(self, doc_id: str) -> frozenset[int]:
        if doc_id not in self._shingles:
            self._shingles[doc_id] = shingles(self.documents[doc_id].content, self.shingle_words)
        return self._shingles[doc_id]

    def apply(self, ranking: Ranking) -> tuple[Ranking, list[str]]:
        """Move documents that nearly duplicate a higher-ranked one to the end."""
        kept: list[tuple[str, float]] = []
        duplicates: list[tuple[str, float]] = []
        for doc_id, score in ranking[: self.window]:
            if any(jaccard(self._of(doc_id), self._of(other)) >= self.threshold for other, _ in kept):
                duplicates.append((doc_id, score))
            else:
                kept.append((doc_id, score))
        return kept + ranking[self.window :] + duplicates, [doc_id for doc_id, _ in duplicates]


class DocumentPriors:
    """Multiplicative penalty for near-empty pages and configured URL patterns."""

    def __init__(self, documents: dict[str, Document], min_content_chars: int, url_penalty_patterns: list[str], penalty: float) -> None:
        self.documents = documents
        self.min_content_chars = min_content_chars
        self.url_patterns = [re.compile(pattern) for pattern in url_penalty_patterns]
        self.penalty = penalty

    def is_penalised(self, doc_id: str) -> bool:
        document = self.documents[doc_id]
        if len(document.content) < self.min_content_chars:
            return True
        return any(pattern.search(document.url) for pattern in self.url_patterns)

    def apply(self, ranking: Ranking) -> tuple[Ranking, list[str]]:
        rescored = [(doc_id, score * self.penalty if self.is_penalised(doc_id) else score) for doc_id, score in ranking]
        penalised = [doc_id for doc_id, _ in ranking if self.is_penalised(doc_id)]
        return sorted(rescored, key=lambda item: -item[1]), penalised
