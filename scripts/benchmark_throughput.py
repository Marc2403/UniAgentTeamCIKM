#!/usr/bin/env python3
"""Measure CPU throughput of the neural models and extrapolate to test-collection sizes.

Run pinned to the TIRA budget of 4 cores, e.g.
  docker run --cpus 4 ... python3 scripts/benchmark_throughput.py --dataset /data/retrieval-de-spot-check"""

import json
import sys
import time
from pathlib import Path

import click

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from uniretrieval.data import load_dataset  # noqa: E402

BUDGET_SECONDS = 4 * 3600


@click.command()
@click.option("--dataset", required=True)
@click.option("--embedding-model", "embedding_models", multiple=True, default=["/models/multilingual-e5-small", "/models/multilingual-e5-base"])
@click.option("--cross-encoder", "cross_encoders", multiple=True, default=["/models/mmarco-mMiniLMv2-L12-H384-v1", "/models/bge-reranker-v2-m3"])
@click.option("--samples", default=128, show_default=True)
@click.option("--sizes", default="30000,100000,300000", show_default=True, help="Collection sizes to extrapolate full-collection embedding to.")
@click.option("--queries", default=100, show_default=True, help="Queries to extrapolate reranking to.")
def main(dataset, embedding_models, cross_encoders, samples, sizes, queries) -> None:
    import torch
    from sentence_transformers import CrossEncoder, SentenceTransformer

    torch.set_num_threads(4)
    _, documents = load_dataset(dataset)
    texts = [document.text[:4000] for document in list(documents.values())[:samples]]
    report = {"threads": torch.get_num_threads(), "samples": len(texts), "embedding": {}, "cross_encoder": {}}

    for path in embedding_models:
        model = SentenceTransformer(path, device="cpu")
        model.max_seq_length = 512
        started = time.perf_counter()
        model.encode([f"passage: {text}" for text in texts], batch_size=16, show_progress_bar=False)
        per_second = len(texts) / (time.perf_counter() - started)
        report["embedding"][Path(path).name] = {
            "docs_per_second": round(per_second, 2),
            "full_collection_hours": {size: round(int(size) / per_second / 3600, 2) for size in sizes.split(",")},
            "rerank_top100_hours": round(queries * 100 / per_second / 3600, 3),
        }

    for path in cross_encoders:
        model = CrossEncoder(path, max_length=512, device="cpu")
        pairs = [("Übernachtungskosten bei Dienstreisen", text[:2000]) for text in texts]
        started = time.perf_counter()
        model.predict(pairs, batch_size=16, show_progress_bar=False)
        per_second = len(pairs) / (time.perf_counter() - started)
        report["cross_encoder"][Path(path).name] = {
            "pairs_per_second": round(per_second, 2),
            **{f"hours_top{depth}": round(queries * depth / per_second / 3600, 3) for depth in (20, 30, 50)},
        }

    report["budget_hours"] = BUDGET_SECONDS / 3600
    click.echo(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
