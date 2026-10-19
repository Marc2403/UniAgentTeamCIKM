"""Render Rajesh's 18 plain-text synthetic cases (set B) as real PDFs in the dataset format of set A.

The source files in `rajesh-uniagent-solver/synthetic/synthetic/synthetic_cases` are plain text with a `.pdf`
extension, which `pdftotext` cannot read. The text is kept line by line; only the file format changes.

    python convert_rajesh.py [--out datasets] [--corpora <dir with hessian-law-de/ ...>]

Writes datasets/rajesh-{business-trip,expense-reimbursement,procurement}/ (inputs, ground-truth.jsonl) and
datasets/cases-rajesh.jsonl (label, Rajesh's category and reason, and whether we doubt the label).
"""
import argparse
import json
import shutil
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab import rl_config
from reportlab.platypus import Paragraph, Spacer

from make_synthetic import DEFAULT_CORPORA, H1, HERE, P, link_corpora, write

SOURCE = HERE.parents[1] / "rajesh-uniagent-solver/synthetic/synthetic/synthetic_cases"
DATASETS = {"dienstreiseantrag": "rajesh-business-trip", "auslagenerstattung": "rajesh-expense-reimbursement",
            "beschaffungsantrag": "rajesh-procurement"}
# Labels a reviewer could reasonably decide the other way (reason in the README).
UNCERTAIN = {
    "dienstreiseantrag-s01-clean-trip": "form names no costs and no means of transport",
    "dienstreiseantrag-k01-private-weekend": "a two-day private extension is allowed; the form claims no extra costs",
    "auslagenerstattung-r05-hotel-over-cap": "hotel bill without trip context claimed as an expense",
}


def story(text):
    lines = text.splitlines()
    flow = [Paragraph(escape(lines[0]), H1)] if lines else []
    for line in lines[1:]:
        flow.append(Paragraph(escape(line), P) if line.strip() else Spacer(1, 8))
    return flow


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=HERE / "datasets")
    parser.add_argument("--corpora", type=Path, default=DEFAULT_CORPORA)
    args = parser.parse_args()
    rl_config.invariant = 1  # byte-identical PDFs on every run
    labels = {row["antrag"]: row["result"] for row in map(json.loads, open(SOURCE / "ground-truth.jsonl", encoding="utf-8"))}
    categories = {row["antrag"]: row for row in map(json.loads, open(SOURCE / "categories.jsonl", encoding="utf-8"))}
    for dataset in DATASETS.values():
        shutil.rmtree(args.out / dataset / "inputs", ignore_errors=True)
    cases = []
    for case_id in sorted(labels):
        dataset = DATASETS[case_id.split("-")[0]]
        for source in sorted((SOURCE / case_id).glob("*.pdf")):
            write(args.out / dataset / "inputs" / case_id / source.name, story(source.read_text(encoding="utf-8")))
        cases.append({"dataset": dataset, "antrag": case_id, "result": labels[case_id],
                      "category": categories[case_id]["category"], "reason": categories[case_id]["reason"],
                      "uncertain": case_id in UNCERTAIN, "doubt": UNCERTAIN.get(case_id)})
    with open(args.out / "cases-rajesh.jsonl", "w", encoding="utf-8") as f:
        f.writelines(json.dumps(c, ensure_ascii=False) + "\n" for c in cases)
    for dataset in DATASETS.values():
        rows = [c for c in cases if c["dataset"] == dataset]
        with open(args.out / dataset / "ground-truth.jsonl", "w", encoding="utf-8") as f:
            f.writelines(json.dumps({"antrag": c["antrag"], "result": c["result"]}) + "\n" for c in rows)
        if args.corpora.is_dir():
            link_corpora(args.corpora, args.out / dataset / "inputs" / "retrieval-corpora")
        print(f"{dataset}: {len(rows)} cases, {sum(c['result'] == 'angenommen' for c in rows)} angenommen")


if __name__ == "__main__":
    main()
