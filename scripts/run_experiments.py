#!/usr/bin/env python3
"""Run configs on datasets and evaluate: runs/<dataset>/<config>/{run.txt.gz,
run-trace.jsonl.log.gz, stats.json, metrics.json, config.yaml}.

A dataset argument is a directory with queries.jsonl, documents.jsonl.gz and
qrels.txt (spot-checks), or `name=docs_dir:devset_dir` to evaluate a dev set
(queries.jsonl + qrels.txt in devset_dir) on another dataset's documents."""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import click

ROOT = Path(__file__).resolve().parent.parent


def resolve(dataset: str) -> tuple[str, Path, Path, Path | None]:
    """(name, input directory, qrels, temporary directory to clean up)"""
    if "=" not in dataset:
        path = Path(dataset)
        return path.name, path, path / "qrels.txt", None
    name, spec = dataset.split("=", 1)
    documents_directory, devset_directory = (Path(part) for part in spec.split(":", 1))
    temporary = Path(tempfile.mkdtemp(prefix=f"devset-{name}-"))
    documents = next(documents_directory.glob("documents.jsonl*"))
    (temporary / documents.name).symlink_to(documents.resolve())
    shutil.copy(devset_directory / "queries.jsonl", temporary / "queries.jsonl")
    return name, temporary, devset_directory / "qrels.txt", temporary


@click.command()
@click.option("--config", "configs", multiple=True, required=True, type=click.Path(path_type=Path, exists=True, dir_okay=False))
@click.option("--dataset", "datasets", multiple=True, required=True)
@click.option("--runs", default=ROOT / "runs", type=click.Path(path_type=Path, file_okay=False), show_default=True)
@click.option("--index-cache", default=ROOT / ".cache" / "indexes", type=click.Path(path_type=Path, file_okay=False), show_default=True)
@click.option("--llm-cache", default=ROOT / ".cache" / "llm", type=click.Path(path_type=Path, file_okay=False), show_default=True)
@click.option("--skip-existing/--rerun", default=True, show_default=True)
def main(configs, datasets, runs: Path, index_cache: Path, llm_cache: Path, skip_existing: bool) -> None:
    failures = []
    for dataset in datasets:
        name, input_directory, qrels, temporary = resolve(dataset)
        try:
            for config in configs:
                output = runs / name / config.stem
                if skip_existing and (output / "metrics.json").is_file():
                    click.echo(f"skip {name}/{config.stem}")
                    continue
                click.echo(f"== {name} / {config.stem}")
                output.mkdir(parents=True, exist_ok=True)
                shutil.copy(config, output / "config.yaml")
                command = [
                    sys.executable, str(ROOT / "retrieve.py"),
                    "--dataset", str(input_directory), "--output", str(output), "--config", str(config),
                    "--index-cache", str(index_cache), "--llm-cache", str(llm_cache),
                ]
                if subprocess.run(command).returncode != 0:
                    failures.append(f"{name}/{config.stem}")
                    continue
                if not qrels.is_file():
                    click.echo(f"no qrels for {name} yet; run kept for pooling (scripts/judge_devset.sh)")
                    continue
                subprocess.run(
                    [sys.executable, str(ROOT / "eval" / "evaluate.py"), "--run", str(output / "run.txt.gz"),
                     "--qrels", str(qrels), "--metrics", str(output / "metrics.json")],
                    check=True,
                )
        finally:
            if temporary is not None:
                shutil.rmtree(temporary, ignore_errors=True)
    if failures:
        raise click.ClickException("Failed: " + ", ".join(failures))


if __name__ == "__main__":
    main()
