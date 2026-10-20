#!/usr/bin/env python3
"""DAIM retrieval system for UniAgent 2026, Task 1.

Writes run.txt.gz (TREC), run-trace.jsonl.log.gz (event-logging contract) and
stats.json (timings, token usage) to --output."""

import hashlib
from pathlib import Path

import click

from uniretrieval.budget import Budget
from uniretrieval.config import load_config
from uniretrieval.data import detect_collection, detect_language, load_dataset
from uniretrieval.llm import OpenAIChatModel, TokenUsage
from uniretrieval.pipeline import Pipeline, needs_llm


def dataset_key(dataset: str) -> str:
    """Identifies the dataset contents for the index cache."""
    parts = [dataset]
    for name in ("documents.jsonl.gz", "documents.jsonl"):
        documents = Path(dataset) / name
        if documents.is_file():
            stat = documents.stat()
            parts = [str(documents.resolve()), str(stat.st_size), str(stat.st_mtime_ns)]
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()


@click.command()
@click.option("--dataset", required=True, help="The TIRA dataset ID or local dataset directory.")
@click.option("--output", required=True, type=click.Path(path_type=Path, file_okay=False), help="The output directory.")
@click.option(
    "--config",
    "config_path",
    default=Path(__file__).resolve().parent / "configs" / "lexical-plus.yaml",
    show_default=True,
    type=click.Path(path_type=Path, exists=True, dir_okay=False),
    help="Pipeline configuration (YAML).",
)
@click.option(
    "--index-cache",
    default=None,
    type=click.Path(path_type=Path, file_okay=False),
    help="Reuse Terrier indexes across runs (experiments only).",
)
@click.option("--llm-cache", default=None, type=click.Path(path_type=Path, file_okay=False), help="Cache LLM responses here (experiments only).")
def main(dataset: str, output: Path, config_path: Path, index_cache: Path | None, llm_cache: Path | None) -> None:
    config = load_config(config_path)
    budget = Budget(config["budget"]["total_seconds"], config["budget"]["reserve_seconds"])
    if llm_cache is not None:
        config["llm"]["cache_dir"] = str(llm_cache)

    chat_model = None
    if needs_llm(config):
        try:
            chat_model = OpenAIChatModel(config["llm"], TokenUsage())
        except RuntimeError as error:
            raise click.ClickException(str(error)) from error

    queries, documents = load_dataset(dataset)
    try:
        language = detect_language(queries)
    except ValueError as error:
        raise click.ClickException(str(error)) from error
    if not documents:
        raise click.ClickException("The dataset has no documents.")
    collection = detect_collection(documents, config["collection"])
    click.echo(f"{len(queries)} queries, {len(documents)} documents, language={language}, collection={collection}, config={config['name']}")

    pipeline = Pipeline(
        config,
        queries,
        documents,
        language,
        collection,
        output,
        chat_model=chat_model,
        index_cache=index_cache,
        dataset_key=dataset_key(dataset),
        budget=budget,
    )
    stats = pipeline.run()
    click.echo(f"Done in {stats['seconds']:.0f}s: {stats['timings']} tokens={stats['tokens']}")


if __name__ == "__main__":
    main()
