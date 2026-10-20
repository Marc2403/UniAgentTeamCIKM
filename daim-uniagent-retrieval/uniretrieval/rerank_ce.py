"""Cross-encoder reranking on CPU (sentence-transformers)."""

from uniretrieval.data import Document, Query
from uniretrieval.fusion import Ranking
from uniretrieval.text import best_passage


class CrossEncoderReranker:
    def __init__(self, documents: dict[str, Document], settings: dict) -> None:
        import torch
        from sentence_transformers import CrossEncoder

        torch.set_num_threads(4)
        self.documents = documents
        self.settings = settings
        self.model = CrossEncoder(settings["model"], max_length=settings["max_length"], device="cpu")

    def rank(self, query: Query, doc_ids: list[str]) -> Ranking:
        text = f"{query.query} {query.description}".strip()
        pairs = [(text, best_passage(self.documents[doc_id], text, self.settings["max_passage_chars"])) for doc_id in doc_ids]
        if not pairs:
            return []
        scores = self.model.predict(pairs, batch_size=self.settings["batch_size"], show_progress_bar=False)
        return sorted(zip(doc_ids, map(float, scores)), key=lambda item: -item[1])
