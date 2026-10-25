#!/usr/bin/env python3
"""Accuracy of predictions.jsonl files against the spot-check ground truth.

Example (inside the image):
  scripts/evaluate_local.py --run runs/full/business-trip-spot-check --truth /data/business-trip-spot-check/ground-truth.jsonl ...
Each --run directory is paired with the --truth file at the same position. Prints accuracy overall and per
case-type prefix, seconds and tokens per case (from run-stats.json), and every wrong case with the gold reason.
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path


def read_jsonl(path: Path) -> dict[str, dict]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return {row["antrag"]: row for row in rows}


def evaluate(runs: list[Path], truths: list[Path]) -> dict:
    per_prefix = defaultdict(lambda: [0, 0])
    errors, seconds, tokens, cases = [], 0.0, 0, 0
    for run, truth_path in zip(runs, truths, strict=True):
        truth = read_jsonl(truth_path)
        predictions = read_jsonl(run / "predictions.jsonl")
        stats_path = run / "run-stats.json"
        stats = json.loads(stats_path.read_text(encoding="utf-8"))["cases"] if stats_path.is_file() else {}
        for case_id, gold in sorted(truth.items()):
            prefix = case_id.rsplit("-", 1)[0]
            predicted = predictions.get(case_id, {}).get("result", "<missing>")
            per_prefix[prefix][1] += 1
            if predicted == gold["result"]:
                per_prefix[prefix][0] += 1
            else:
                errors.append({"antrag": case_id, "predicted": predicted, "gold": gold["result"], "gold_begruendung": gold.get("begruendung", ""), "begruendung": predictions.get(case_id, {}).get("begruendung", "")})
            case_stats = stats.get(case_id, {})
            seconds += case_stats.get("seconds", 0.0)
            tokens += case_stats.get("prompt_tokens", 0) + case_stats.get("completion_tokens", 0)
            cases += 1
    correct = sum(value[0] for value in per_prefix.values())
    return {
        "accuracy": correct / cases if cases else 0.0,
        "correct": correct,
        "cases": cases,
        "per_prefix": {prefix: {"accuracy": right / total, "correct": right, "cases": total} for prefix, (right, total) in sorted(per_prefix.items())},
        "seconds_per_case": seconds / cases if cases else 0.0,
        "tokens_per_case": tokens / cases if cases else 0.0,
        "errors": errors,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", type=Path, action="append", required=True)
    parser.add_argument("--truth", type=Path, action="append", required=True)
    parser.add_argument("--json", action="store_true", help="print the full report as JSON")
    args = parser.parse_args()
    report = evaluate(args.run, args.truth)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=1))
        return
    print("| Falltyp | Accuracy | richtig/Fälle |\n|---|---|---|")
    for prefix, row in report["per_prefix"].items():
        print(f"| {prefix} | {row['accuracy']:.2f} | {row['correct']}/{row['cases']} |")
    print(f"| **gesamt** | **{report['accuracy']:.2f}** | {report['correct']}/{report['cases']} |")
    print(f"\nSekunden/Fall: {report['seconds_per_case']:.1f}, Tokens/Fall: {report['tokens_per_case']:.0f}")
    for error in report["errors"]:
        print(f"\nFALSCH {error['antrag']}: vorhergesagt {error['predicted']}, Gold {error['gold']}\n  Gold: {error['gold_begruendung']}\n  System: {error['begruendung']}")


if __name__ == "__main__":
    main()
