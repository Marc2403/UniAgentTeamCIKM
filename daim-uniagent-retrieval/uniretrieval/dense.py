"""Dense scoring of lexical candidates with an E5 embedding model on CPU.

Embedding the whole collection at query time does not fit the 4-CPU budget
for the test corpora (see scripts/benchmark_throughput.py), so the model only
re-scores the head of the lexical ranking; embeddings are cached per document."""

from uniretrieval.data import Document, Query
from uniretrieval.fusion import Ranking


class DenseScorer:
    def __init__(self, documents: dict[str, Document], settings: dict) -> None:
        import torch
        from sentence_transformers import SentenceTransformer

        torch.set_num_threads(4)
        self.documents = documents
        self.settings = settings
        self.model = SentenceTransformer(settings["model"], device="cpu")
        self.model.max_seq_length = settings["max_length"]
        self._embeddings: dict = {}

    def _encode(self, texts: list[str]):
        return self.model.encode(
            texts, batch_size=self.settings["batch_size"], normalize_embeddings=True, show_progress_bar=False, convert_to_numpy=True
        )

    def rank(self, query: Query, doc_ids: list[str]) -> Ranking:
        missing = [doc_id for doc_id in doc_ids if doc_id not in self._embeddings]
        if missing:
            texts = [f"passage: {self.documents[doc_id].text[:4000]}" for doc_id in missing]
            for doc_id, vector in zip(missing, self._encode(texts)):
                self._embeddings[doc_id] = vector
        if not doc_ids:
            return []
        query_vector = self._encode([f"query: {query.query} {query.description}".strip()])[0]
        scores = {doc_id: float(self._embeddings[doc_id] @ query_vector) for doc_id in doc_ids}
        return sorted(scores.items(), key=lambda item: -item[1])
