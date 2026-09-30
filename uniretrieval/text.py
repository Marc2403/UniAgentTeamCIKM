"""Text preprocessing that happens before Terrier's own tokeniser/stemmer:
query formulation, URL tokens, German decompounding, passage splitting."""

import re
from collections import Counter
from typing import Iterable

from uniretrieval.data import Document, Query

WORD_RE = re.compile(r"[^\W\d_]+", re.UNICODE)
TOKEN_RE = re.compile(r"\w+", re.UNICODE)

# Leading meta phrases of narratives ("Relevant sind Dokumente zum ...") that
# describe the judging task rather than the information need.
NARRATIVE_BOILERPLATE = [
    re.compile(
        r"^\s*relevant\s+(?:sind|ist)\s+(?:(?:die|der|das|alle)\s+)?"
        r"(?:(?:dokumente|seiten|informationen|unterlagen|anleitungen|angaben)\s+)?"
        r"(?:(?:zu[mr]?|über|mit|für|die|der)\s+)?",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*relevant\s+(?:documents|pages|information)?\s*"
        r"(?:are|is|include|includes)?\s*(?:those\s+)?(?:that|which)?\s*",
        re.IGNORECASE,
    ),
]


def strip_narrative_boilerplate(narrative: str) -> str:
    for pattern in NARRATIVE_BOILERPLATE:
        stripped = pattern.sub("", narrative, count=1)
        if stripped != narrative:
            return stripped
    return narrative


def formulate_query(query: Query, settings: dict) -> str:
    """Weighted bag of words: each part is repeated `<part>_weight` times,
    which raises its query-term frequency in Terrier's weighting models."""
    narrative = query.narrative
    if settings.get("strip_narrative_boilerplate", True):
        narrative = strip_narrative_boilerplate(narrative)
    parts = []
    for text, weight in (
        (query.query, settings.get("query_weight", 1)),
        (query.description, settings.get("description_weight", 0)),
        (narrative, settings.get("narrative_weight", 0)),
    ):
        parts.extend([text] * int(weight))
    formulated = " ".join(part for part in parts if part)
    return formulated or query.query or query.description


def url_tokens(url: str) -> str:
    """Path words of a URL (`/finanzen/reisekosten.html` -> `finanzen reisekosten`)."""
    path = re.sub(r"^[a-z]+://[^/]+", "", url)
    path = re.sub(r"\.(html?|php|aspx?|pdf)$", "", path)
    return " ".join(token for token in re.split(r"[/\-_.?=&#]+", path) if token and not token.isdigit())


class Decompounder:
    """Corpus-frequency compound splitting (Koehn & Knight, 2003).

    A word is split into parts that are themselves frequent corpus words,
    allowing German linking elements ("Übernachtung-s-kosten"), if the
    geometric mean of the part frequencies beats the frequency of the word.
    """

    LINKERS = ("", "s", "es", "n", "en", "e")

    def __init__(
        self,
        vocabulary: Counter,
        min_word_length: int = 8,
        min_part_length: int = 4,
        min_part_frequency: int = 5,
    ) -> None:
        self.vocabulary = vocabulary
        self.min_word_length = min_word_length
        self.min_part_length = min_part_length
        self.min_part_frequency = min_part_frequency
        self._cache: dict[str, list[str]] = {}

    @classmethod
    def from_texts(cls, texts: Iterable[str], vocabulary_max_chars: int = 20000, **settings) -> "Decompounder":
        vocabulary: Counter = Counter()
        for text in texts:
            vocabulary.update(word.lower() for word in WORD_RE.findall(text[:vocabulary_max_chars]))
        return cls(vocabulary, **settings)

    def _is_part(self, word: str) -> bool:
        return len(word) >= self.min_part_length and self.vocabulary[word] >= self.min_part_frequency

    def _candidates(self, word: str, depth: int) -> list[list[str]]:
        candidates = []
        for cut in range(self.min_part_length, len(word) - self.min_part_length + 1):
            left, right = word[:cut], word[cut:]
            for linker in self.LINKERS:
                if linker and not left.endswith(linker):
                    continue
                stem = left[: len(left) - len(linker)]
                if not self._is_part(stem):
                    continue
                if self._is_part(right):
                    candidates.append([stem, right])
                if depth > 0:
                    candidates.extend([stem, *rest] for rest in self._candidates(right, depth - 1))
        return candidates

    def split(self, word: str) -> list[str]:
        """Parts of `word` (lowercased), or [] if it is not a compound."""
        word = word.lower()
        if word in self._cache:
            return self._cache[word]
        parts: list[str] = []
        if len(word) >= self.min_word_length:
            best_score = float(self.vocabulary[word])
            for candidate in self._candidates(word, depth=1):
                score = 1.0
                for part in candidate:
                    score *= self.vocabulary[part]
                score **= 1.0 / len(candidate)
                if score > best_score:
                    best_score, parts = score, candidate
        self._cache[word] = parts
        return parts

    def expand(self, text: str) -> str:
        """`text` followed by the parts of every compound in it."""
        extra = [part for word in WORD_RE.findall(text) for part in self.split(word)]
        return f"{text} {' '.join(extra)}" if extra else text


def passages(text: str, words: int, stride: int) -> list[str]:
    tokens = text.split()
    if len(tokens) <= words:
        return [text]
    return [" ".join(tokens[start : start + words]) for start in range(0, len(tokens) - words + stride, stride)]


def best_passage(document: Document, query_text: str, max_chars: int) -> str:
    """Title plus the window of the content that contains the most query words
    (matched on 5-character prefixes, a cheap stand-in for stemming)."""
    head = f"{document.title}\n" if document.title else ""
    budget = max(max_chars - len(head), 0)
    content = document.content
    if len(content) <= budget:
        return head + content
    prefixes = {token.lower()[:5] for token in TOKEN_RE.findall(query_text) if len(token) > 2}
    step = max(budget // 4, 1)
    best_start, best_hits = 0, -1
    for start in range(0, len(content) - budget + step, step):
        window = content[start : start + budget]
        hits = sum(1 for token in TOKEN_RE.findall(window) if token.lower()[:5] in prefixes)
        if hits > best_hits:
            best_start, best_hits = start, hits
    return head + content[best_start : best_start + budget]
