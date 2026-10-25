"""BM25 over every retrieval corpus found at runtime (bm25s, language-specific stemming)."""

import gzip
import json
import re
from dataclasses import dataclass
from pathlib import Path

import bm25s
import Stemmer

GERMAN_STOPWORDS = Path(__file__).parent / "knowledge" / "german-stopwords.txt"
LANGUAGE_SUFFIX = re.compile(r"-(de|en)$")
STEMMER_LANGUAGES = {"de": "german", "en": "english"}
# Long court decisions are cut so the index stays within the time budget; the head
# carries title, headnote and the cited norms.
MAX_INDEXED_CHARACTERS = 20000


@dataclass
class Hit:
    corpus: str
    doc_id: str
    title: str
    url: str
    score: float
    passage: str

    def as_dict(self) -> dict:
        return {"corpus": self.corpus, "doc_id": self.doc_id, "title": self.title, "url": self.url, "score": round(self.score, 3), "passage": self.passage}


def _text(document: dict) -> str:
    text = document.get("text") or document.get("content") or ""
    return text if isinstance(text, str) else ""


def corpus_language(name: str, documents: list[dict]) -> str:
    match = LANGUAGE_SUFFIX.search(name)
    if match:
        return match.group(1)
    language = next((document.get("language") for document in documents if document.get("language")), "de")
    return language if language in STEMMER_LANGUAGES else "de"


class CorpusIndex:
    def __init__(self, name: str, documents: list[dict]) -> None:
        self.name = name
        self.language = corpus_language(name, documents)
        self.documents = documents
        self.positions = {str(document["doc_id"]): position for position, document in enumerate(documents)}
        self.stemmer = Stemmer.Stemmer(STEMMER_LANGUAGES[self.language])
        self.stopwords = GERMAN_STOPWORDS.read_text(encoding="utf-8").split() if self.language == "de" else "en"
        texts = [f"{document.get('title') or ''}\n{_text(document)[:MAX_INDEXED_CHARACTERS]}" for document in documents]
        self.retriever = bm25s.BM25()
        self.retriever.index(self._tokenize(texts), show_progress=False)

    @classmethod
    def load(cls, name: str, path: Path) -> "CorpusIndex":
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            documents = [json.loads(line) for line in handle if line.strip()]
        if not documents:
            raise ValueError(f"No documents in {path}")
        return cls(name, documents)

    def _tokenize(self, texts: list[str]):
        return bm25s.tokenize(texts, stopwords=self.stopwords, stemmer=self.stemmer, show_progress=False)

    def search(self, query: str, k: int) -> list[Hit]:
        tokens = self._tokenize([query])
        if not tokens.vocab:
            return []
        positions, scores = self.retriever.retrieve(tokens, k=min(k, len(self.documents)), show_progress=False)
        hits = []
        for position, score in zip(positions[0], scores[0]):
            if score <= 0:
                continue
            document = self.documents[int(position)]
            hits.append(Hit(self.name, str(document["doc_id"]), document.get("title") or "", document.get("url") or "", float(score), best_passage(_text(document), query)))
        return hits

    def get(self, doc_id: str) -> dict | None:
        position = self.positions.get(doc_id)
        return None if position is None else self.documents[position]


def _words(text: str) -> set[str]:
    return {word[:6] for word in re.findall(r"\w{4,}", text.lower())}


def best_passage(text: str, query: str, size: int = 600) -> str:
    """The window of `text` sharing the most word stems with `query`."""
    if len(text) <= size:
        return " ".join(text.split())
    wanted = _words(query)
    best_start, best_overlap = 0, -1
    for start in range(0, len(text) - size // 2, size // 3):
        overlap = len(wanted & _words(text[start : start + size]))
        if overlap > best_overlap:
            best_start, best_overlap = start, overlap
    return " ".join(text[best_start : best_start + size].split())


class Retriever:
    def __init__(self, indexes: list[CorpusIndex]) -> None:
        self.indexes = {index.name: index for index in indexes}

    @classmethod
    def build(cls, corpora: dict[str, Path]) -> "Retriever":
        return cls([CorpusIndex.load(name, path) for name, path in corpora.items()])

    def search(self, query: str, k: int, corpora: list[str] | None = None) -> list[Hit]:
        names = corpora or list(self.indexes)
        hits = [hit for name in names if name in self.indexes for hit in self.indexes[name].search(query, k)]
        return sorted(hits, key=lambda hit: hit.score, reverse=True)[:k]

    def get(self, corpus: str, doc_id: str) -> dict | None:
        index = self.indexes.get(corpus)
        return index.get(doc_id) if index else None
