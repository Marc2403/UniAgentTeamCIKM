"""PyTerrier indexes and lexical rankers.

Indexes:
- `body`: title (repeated), optional URL path words, content
- `title`: title and URL path words
- `passages`: overlapping content windows, aggregated back to documents
"""

import hashlib
import json
import shutil
import tempfile
from pathlib import Path
from typing import Callable, Iterable

import pandas as pd
import pyterrier as pt

from uniretrieval.data import Document
from uniretrieval.fusion import Ranking
from uniretrieval.text import passages, url_tokens

STOPWORDS_FILE = Path(__file__).resolve().parent.parent / "german-stopwords.txt"
PASSAGE_SEPARATOR = "::p"


def terrier_settings(language: str) -> dict:
    """Same stemmer/stopwords/tokeniser as the organisers' PyTerrier baseline."""
    if language == "de":
        return {
            "stemmer": pt.TerrierStemmer.german,
            "stopwords": STOPWORDS_FILE.read_text(encoding="utf-8").splitlines(),
            "tokeniser": pt.TerrierTokeniser.utf,
        }
    if language == "en":
        return {
            "stemmer": pt.TerrierStemmer.porter,
            "stopwords": pt.TerrierStopwords.terrier,
            "tokeniser": pt.TerrierTokeniser.english,
        }
    raise ValueError(f"Unsupported language: {language}")


def document_views(
    documents: dict[str, Document], name: str, settings: dict, preprocess: Callable[[str], str]
) -> Iterable[dict]:
    """The indexed text of every document for index `name`."""
    for doc_id, document in documents.items():
        url_words = url_tokens(document.url) if settings.get("url_tokens") else ""
        if name == "title":
            yield {"docno": doc_id, "text": preprocess(f"{document.title} {url_words}")}
        elif name == "body":
            title = " ".join([document.title] * int(settings.get("title_repeat", 1)))
            yield {"docno": doc_id, "text": preprocess(f"{title} {url_words}\n{document.content}")}
        elif name == "passages":
            windows = passages(document.content, settings["passages"]["words"], settings["passages"]["stride"])
            for number, window in enumerate(windows):
                yield {"docno": f"{doc_id}{PASSAGE_SEPARATOR}{number}", "text": preprocess(f"{document.title}\n{window}")}
        else:
            raise ValueError(f"Unknown index: {name}")


def _cache_key(dataset_key: str, name: str, language: str, settings: dict) -> str:
    payload = json.dumps([dataset_key, name, language, settings], sort_keys=True, default=str)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


def build_index(
    documents: dict[str, Document],
    name: str,
    language: str,
    settings: dict,
    preprocess: Callable[[str], str],
    cache_directory: Path | None = None,
    dataset_key: str = "",
):
    """Build (or reuse from `cache_directory`) one Terrier index."""
    if cache_directory is not None:
        directory = Path(cache_directory) / f"{name}-{_cache_key(dataset_key, name, language, settings)}"
        if (directory / "data.properties").is_file():
            return pt.IndexFactory.of(str(directory.resolve()))
        shutil.rmtree(directory, ignore_errors=True)
    else:
        directory = Path(tempfile.mkdtemp(prefix=f"uniretrieval-{name}-"))
    indexer = pt.IterDictIndexer(
        str(directory.resolve()),
        overwrite=True,
        meta={"docno": 128},
        **terrier_settings(language),
    )
    reference = indexer.index(document_views(documents, name, settings, preprocess))
    return pt.IndexFactory.of(reference)


class LexicalSearcher:
    def __init__(self, indexes: dict, language: str, depth: int, passage_aggregation: str = "max") -> None:
        self.indexes = indexes
        self.depth = depth
        self.passage_aggregation = passage_aggregation
        self._tokeniser = pt.TerrierTokeniser.java_tokeniser(terrier_settings(language)["tokeniser"])

    def tokenise(self, text: str) -> str:
        return " ".join(self._tokeniser.getTokens(text))

    def _pipeline(self, ranker: dict):
        index = self.indexes[ranker["index"]]
        depth = self.depth * 3 if ranker["index"] == "passages" else self.depth

        def retriever():
            return pt.terrier.Retriever(
                index, wmodel=ranker["wmodel"], controls=ranker.get("controls") or {}, num_results=depth
            )

        prf = ranker.get("prf")
        if not prf:
            return retriever()
        expansions = {"Bo1": pt.rewrite.Bo1QueryExpansion, "KL": pt.rewrite.KLQueryExpansion}
        if prf not in expansions:
            raise ValueError(f"Unknown PRF method: {prf}")
        return retriever() >> expansions[prf](index) >> retriever()

    def search(self, ranker: dict, queries: dict[str, str]) -> dict[str, Ranking]:
        """Run one ranker for all queries ({qid: text}); empty queries get empty rankings."""
        rankings: dict[str, Ranking] = {qid: [] for qid in queries}
        topics = pd.DataFrame(
            [{"qid": qid, "query": self.tokenise(text)} for qid, text in queries.items()],
            columns=["qid", "query"],
        )
        topics = topics[topics["query"].str.strip() != ""]
        if topics.empty:
            return rankings
        results = self._pipeline(ranker).transform(topics)
        for qid, group in results.groupby("qid"):
            ordered = group.sort_values("rank")
            pairs = list(zip(ordered["docno"].astype(str), ordered["score"].astype(float)))
            if ranker["index"] == "passages":
                pairs = self._aggregate_passages(pairs)
            rankings[str(qid)] = pairs[: self.depth]
        return rankings

    def _aggregate_passages(self, pairs: Ranking) -> Ranking:
        per_document: dict[str, list[float]] = {}
        for passage_id, score in pairs:
            per_document.setdefault(passage_id.split(PASSAGE_SEPARATOR)[0], []).append(score)
        if self.passage_aggregation == "max":
            scores = {doc_id: max(values) for doc_id, values in per_document.items()}
        elif self.passage_aggregation == "sum2":
            scores = {doc_id: sum(sorted(values, reverse=True)[:2]) for doc_id, values in per_document.items()}
        else:
            raise ValueError(f"Unknown passage aggregation: {self.passage_aggregation}")
        return sorted(scores.items(), key=lambda item: (-item[1], item[0]))
