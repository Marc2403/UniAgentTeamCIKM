#!/usr/bin/env python3
"""Evaluate one run: mean measures and a per-query table; optionally write metrics.json."""

import json
import sys
from pathlib import Path

import click

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from uniretrieval.metrics import MEASURES, mean, per_query, read_qrels  # noqa: E402
from uniretrieval.run_io import read_run  # noqa: E402


def evaluate_run(run_path: Path, qrels_path: Path) -> dict:
    results = per_query(read_run(run_path), read_qrels(qrels_path))
    return {"mean": mean(results), "per_query": results}


@click.command()
@click.option("--run", "run_path", required=True, type=click.Path(path_type=Path, exists=True))
@click.option("--qrels", "qrels_path", required=True, type=click.Path(path_type=Path, exists=True, dir_okay=False))
@click.option("--metrics", "metrics_path", default=None, type=click.Path(path_type=Path, dir_okay=False), help="Write metrics.json here, merged with stats.json next to the run.")
@click.option("--per-query/--no-per-query", "per_query_table", default=False, show_default=True)
def main(run_path: Path, qrels_path: Path, metrics_path: Path | None, per_query_table: bool) -> None:
    if run_path.is_dir():
        run_path = run_path / "run.txt.gz"
    evaluation = evaluate_run(run_path, qrels_path)
    if per_query_table:
        click.echo("qid\t" + "\t".join(MEASURES))
        for qid, values in sorted(evaluation["per_query"].items(), key=lambda item: item[0]):
            click.echo(qid + "\t" + "\t".join(f"{values[name]:.3f}" for name in MEASURES))
    click.echo(json.dumps({name: round(value, 4) for name, value in evaluation["mean"].items()}))
    if metrics_path is not None:
        stats_path = run_path.parent / "stats.json"
        stats = json.loads(stats_path.read_text(encoding="utf-8")) if stats_path.is_file() else {}
        metrics_path.write_text(json.dumps({**stats, **evaluation, "qrels": str(qrels_path)}, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
