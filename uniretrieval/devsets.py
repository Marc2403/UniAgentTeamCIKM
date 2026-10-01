"""Dev-set files: eval/devsets/<collection>/<set>.jsonl queries, with
`<set>.qrels.txt` judgments next to them and `excluded.txt` (one qid per line,
`#` comments) listing queries left out of judging and evaluation."""

import json
from pathlib import Path


def excluded_qids(directory: Path) -> set[str]:
    path = Path(directory) / "excluded.txt"
    if not path.is_file():
        return set()
    lines = (line.split("#", 1)[0].strip() for line in path.read_text(encoding="utf-8").splitlines())
    return {line for line in lines if line}


def included_query_lines(queries_file: Path) -> list[str]:
    """The JSONL lines of `queries_file` whose qid is not excluded."""
    excluded = excluded_qids(Path(queries_file).parent)
    lines = [line for line in Path(queries_file).read_text(encoding="utf-8").splitlines() if line.strip()]
    return [line for line in lines if str(json.loads(line)["qid"]) not in excluded]


def qrels_path(queries_file: Path) -> Path:
    return Path(queries_file).with_suffix(".qrels.txt")
