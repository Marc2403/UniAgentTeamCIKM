import gzip
import json
import logging
import re
import time
from pathlib import Path
from typing import Dict, List

from rank_bm25 import BM25Okapi

log = logging.getLogger(__name__)

TOKEN_RE = re.compile(r"\w+", re.UNICODE)
MAX_DOC_CHARS = 1500
MAX_QUERY_TERMS = 500


def tokenize(text: str) -> List[str]:
    return [t.lower() for t in TOKEN_RE.findall(text)]


def discover_corpora(input_dir: Path) -> List[Path]:
    base = input_dir / "retrieval-corpora"
    if not base.is_dir():
        return []
    return sorted(
        p for p in base.iterdir()
        if p.is_dir() and (p / "documents.jsonl.gz").is_file()
    )


def load_corpus_docs(corpus_dir: Path, max_chars: int = MAX_DOC_CHARS) -> List[Dict]:
    path = corpus_dir / "documents.jsonl.gz"
    docs: List[Dict] = []
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue
            text = d.get("text") or d.get("content") or ""
            if len(text) > max_chars:
                text = text[:max_chars]
            docs.append({
                "doc_id": d.get("doc_id") or "",
                "url": d.get("url") or "",
                "title": d.get("title") or "",
                "corpus": corpus_dir.name,
                "text": text,
            })
    return docs


class Retriever:
    def __init__(self, docs, tokenized):
        self.docs = docs
        self.bm25 = BM25Okapi(tokenized) if tokenized else None

    def search(self, query_text: str, top_k: int = 8):
        if self.bm25 is None:
            return []
        qtokens = tokenize(query_text)[:MAX_QUERY_TERMS]
        if not qtokens:
            return []
        scores = self.bm25.get_scores(qtokens)
        idx_sorted = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
        out = []
        for i in idx_sorted:
            if scores[i] <= 0:
                continue
            d = dict(self.docs[i])
            d["score"] = float(scores[i])
            out.append(d)
        return out


def build_retriever(input_dir: Path) -> Retriever:
    t0 = time.time()
    corpus_dirs = discover_corpora(input_dir)
    log.info("Discovered %d corpora under %s", len(corpus_dirs), input_dir)

    all_docs: List[Dict] = []
    for cd in corpus_dirs:
        t1 = time.time()
        docs = load_corpus_docs(cd)
        all_docs.extend(docs)
        log.info("Loaded corpus %s: %d docs in %.1fs", cd.name, len(docs), time.time() - t1)

    if not all_docs:
        log.warning("No corpus documents loaded; retrieval will return empty results.")
        return Retriever([], [])

    t2 = time.time()
    tokenized = [tokenize(d["text"]) for d in all_docs]
    log.info("Tokenized %d docs in %.1fs", len(all_docs), time.time() - t2)

    t3 = time.time()
    retriever = Retriever(all_docs, tokenized)
    log.info("Built BM25 index in %.1fs (total %.1fs)", time.time() - t3, time.time() - t0)
    return retriever