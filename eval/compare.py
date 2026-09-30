#!/usr/bin/env python3
"""Table over all evaluated runs: runs/<dataset>/<config>/metrics.json.

One row per config, nDCG@10 per dataset (plus mean, runtime and tokens), and
the p-value of a paired randomization test against --reference per dataset."""

import json
import sys
from pathlib import Path

import click

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from uniretrieval.metrics import randomization_test  # noqa: E402


def load_metrics(runs: Path) -> dict[str, dict[str, dict]]:
    """{config: {dataset: metrics}}"""
    table: dict[str, dict[str, dict]] = {}
    for path in sorted(runs.glob("*/*/metrics.json")):
        table.setdefault(path.parent.name, {})[path.parent.parent.name] = json.loads(path.read_text(encoding="utf-8"))
    return table


def p_value(metrics: dict, reference: dict | None, measure: str) -> float | None:
    if reference is None:
        return None
    qids = sorted(set(metrics["per_query"]) & set(reference["per_query"]))
    if not qids:
        return None
    return randomization_test([metrics["per_query"][q][measure] for q in qids], [reference["per_query"][q][measure] for q in qids])


def render(table: dict[str, dict[str, dict]], datasets: list[str], measure: str, reference: str | None) -> str:
    header = ["config", *datasets, "mean", "seconds", "LLM tokens"]
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    for config, per_dataset in sorted(table.items(), key=lambda item: item[0]):
        cells, values, seconds, tokens = [config], [], 0.0, 0
        for dataset in datasets:
            metrics = per_dataset.get(dataset)
            if metrics is None:
                cells.append("–")
                continue
            value = metrics["mean"][measure]
            values.append(value)
            seconds += metrics.get("seconds", 0.0)
            usage = metrics.get("tokens") or {}
            tokens += usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0)
            p = p_value(metrics, table.get(reference, {}).get(dataset), measure) if config != reference else None
            cells.append(f"{value:.3f}" + (f" (p={p:.2f})" if p is not None else ""))
        cells.append(f"{sum(values) / len(values):.3f}" if len(values) == len(datasets) else "–")
        cells += [f"{seconds:.0f}", f"{tokens:,}"]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


@click.command()
@click.option("--runs", default=Path("runs"), type=click.Path(path_type=Path, file_okay=False), show_default=True)
@click.option("--measure", default="nDCG@10", show_default=True)
@click.option("--reference", default=None, help="Config to test every other config against.")
@click.option("--dataset", "datasets", multiple=True, help="Datasets (columns) to show; default: all found.")
@click.option("--output", default=None, type=click.Path(path_type=Path, dir_okay=False), help="Also write the table (Markdown) here.")
def main(runs: Path, measure: str, reference: str | None, datasets: tuple[str, ...], output: Path | None) -> None:
    table = load_metrics(runs)
    columns = list(datasets) or sorted({dataset for per_dataset in table.values() for dataset in per_dataset})
    rendered = render(table, columns, measure, reference)
    click.echo(rendered)
    if output is not None:
        output.write_text(rendered + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
