#!/usr/bin/env python3
"""Compare baseline and candidate runs written by run-mvp.sh: accuracy per set, A/R errors, flips and the gate.

Usage: python evaluation/compare_runs.py --baseline <run> [<run>] --candidate <run> [<run>] [--sets S A B C]
A run is a directory with one subdirectory per dataset (predictions.jsonl, run-stats.json, evaluation.json).
Sets: S spot-checks, A synthetic-*, B rajesh-*, C coverage-*, H holdout-*. Cases marked uncertain in
synthetic/datasets/cases*.jsonl are left out of the gate and reported separately.
Gate (PLAN-MVP-VERBESSERUNG.md, Phase 5, points 1-5 without unit tests and traces, which are checked elsewhere):
1. S: no case right in every baseline run is wrong in every candidate run.
2. A, B, C: the same, uncertain cases excluded.
3. Correct predictions on A + B + C (summed over runs) do not fall.
4. Wrong rejections (R) on A + B + C do not rise.
5. Every run exited 0, 0 invalid log lines, max seconds per case < 240 (fallback decisions are reported alongside).
"""

import argparse
import json
from pathlib import Path
from typing import NamedTuple

HERE = Path(__file__).resolve().parent
SYNTHETIC = HERE / "synthetic" / "datasets"
SPOT_CHECKS = HERE.parents[1] / "uniagent-code" / "cikm26" / "datasets"
SET_PREFIXES = {"synthetic-": "A", "rajesh-": "B", "coverage-": "C", "holdout-": "H"}
GATE_SETS = ("A", "B", "C")
MAX_CASE_SECONDS = 240


class Row(NamedTuple):
    set: str
    dataset: str
    case: str
    gold: str
    uncertain: bool
    family: str
    predictions: dict  # group -> [result per run]


def set_of(dataset: str) -> str:
    return next((name for prefix, name in SET_PREFIXES.items() if dataset.startswith(prefix)), "S")


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def case_info() -> dict[tuple[str, str], dict]:
    return {(row["dataset"], row["antrag"]): row for path in sorted(SYNTHETIC.glob("cases*.jsonl")) for row in read_jsonl(path)}


def truths(dataset: str) -> dict[str, str]:
    folder = SYNTHETIC / dataset if (SYNTHETIC / dataset).is_dir() else SPOT_CHECKS / dataset
    return {row["antrag"]: row["result"] for row in read_jsonl(folder / "ground-truth.jsonl")}


def load_run(run: Path) -> dict:
    """{dataset: {"pred": {case: result}, "seconds": {case: s}, "exit": int, "invalid": int}}"""
    datasets = {}
    for folder in sorted(path for path in run.iterdir() if (path / "predictions.jsonl").is_file()):
        stats = json.loads((folder / "run-stats.json").read_text(encoding="utf-8")) if (folder / "run-stats.json").is_file() else {}
        printed = (folder / "evaluation.json").read_text(encoding="utf-8") if (folder / "evaluation.json").is_file() else ""
        evaluation = json.loads(printed[printed.find("{"):]) if "{" in printed else {}
        status = json.loads((folder / "run.json").read_text()) if (folder / "run.json").is_file() else {}
        datasets[folder.name] = {
            "pred": {row["antrag"]: row["result"] for row in read_jsonl(folder / "predictions.jsonl")},
            "seconds": {case: entry.get("seconds", 0) for case, entry in stats.get("cases", {}).items()},
            "fallbacks": sum(entry.get("method", "").startswith("fallback") for entry in stats.get("cases", {}).values()),
            "exit": status.get("exit_code"),
            "invalid": evaluation.get("invalid_log_lines"),
        }
    return datasets


def mark(gold: str, predicted: str | None) -> str:
    if predicted == gold:
        return "ok"
    return "**A**" if predicted == "angenommen" else "**R**" if predicted == "abgelehnt" else "-"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--baseline", type=Path, nargs="+", required=True)
    parser.add_argument("--candidate", type=Path, nargs="*", default=[])
    parser.add_argument("--sets", nargs="+", default=["S", "A", "B", "C"])
    parser.add_argument("--cases", action="store_true", help="print the per-case table")
    parser.add_argument("--summary", action="store_true", help="accuracy table only, no case names (for the holdout)")
    args = parser.parse_args()
    info = case_info()
    groups = {"baseline": [load_run(run) for run in args.baseline], "candidate": [load_run(run) for run in args.candidate]}
    datasets = sorted({d for runs in groups.values() for run in runs for d in run if set_of(d) in args.sets})

    rows = []
    for dataset in datasets:
        meta_by_case = {case: meta for (d, case), meta in info.items() if d == dataset}
        for case, gold in sorted(truths(dataset).items()):
            meta = meta_by_case.get(case, {})
            predictions = {group: [run.get(dataset, {}).get("pred", {}).get(case) for run in runs] for group, runs in groups.items()}
            rows.append(Row(set_of(dataset), dataset, case, gold, bool(meta.get("uncertain")), meta.get("family", ""), predictions))

    def tally(selected: list[Row], group: str) -> tuple[int, int, int, int]:
        """(right, wrong angenommen, wrong abgelehnt, predictions) over all runs of the group."""
        pairs = [(row.gold, p) for row in selected for p in row.predictions[group]]
        return (sum(p == gold for gold, p in pairs), sum(p == "angenommen" != gold for gold, p in pairs),
                sum(p == "abgelehnt" != gold for gold, p in pairs), len(pairs))

    print("## Accuracy (summed over runs; uncertain cases separate)\n")
    print("| Set | Cases | Baseline right/total | A | R | Candidate right/total | A | R | uncertain: baseline | candidate |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    sets = [s for s in ("S", "A", "B", "C", "H") if s in args.sets]
    for name in sets + ["A+B+C"]:
        members = GATE_SETS if name == "A+B+C" else (name,)
        certain = [r for r in rows if r.set in members and not r.uncertain]
        uncertain = [r for r in rows if r.set in members and r.uncertain]
        if not certain and not uncertain:
            continue
        b, c = tally(certain, "baseline"), tally(certain, "candidate")
        ub, uc = tally(uncertain, "baseline"), tally(uncertain, "candidate")
        cand = f"{c[0]}/{c[3]} | {c[1]} | {c[2]}" if groups["candidate"] else "- | - | -"
        print(f"| {name} | {len(certain)} (+{len(uncertain)}?) | {b[0]}/{b[3]} | {b[1]} | {b[2]} | {cand} | "
              f"{ub[0]}/{ub[3]} | {f'{uc[0]}/{uc[3]}' if groups['candidate'] else '–'} |")

    if args.summary:
        return
    families = sorted({r.family for r in rows if r.family})
    if families:
        print("\n## By family (certain cases, summed over runs)\n")
        print("| Family | Cases | Baseline | Candidate |")
        print("|---|---|---|---|")
        for family in families:
            selected = [r for r in rows if r.family == family and not r.uncertain]
            b, c = tally(selected, "baseline"), tally(selected, "candidate")
            print(f"| {family} | {len(selected)} | {b[0]}/{b[3]} | {f'{c[0]}/{c[3]}' if groups['candidate'] else '–'} |")

    def stable(preds, gold, right):
        return bool(preds) and all(p is not None for p in preds) and all((p == gold) == right for p in preds)

    unstable = [r for r in rows if len({p for p in r.predictions["baseline"]}) > 1]
    flips, regressions = [], []
    for r in rows:
        if not groups["candidate"]:
            break
        before = "right" if stable(r.predictions["baseline"], r.gold, True) else "wrong" if stable(r.predictions["baseline"], r.gold, False) else "mixed"
        after = "right" if stable(r.predictions["candidate"], r.gold, True) else "wrong" if stable(r.predictions["candidate"], r.gold, False) else "mixed"
        if before != after:
            flips.append((r, before, after))
        if before == "right" and after == "wrong" and not r.uncertain:
            regressions.append(r)

    print(f"\n## Unstable in the baseline ({len(unstable)})\n")
    for r in unstable:
        print(f"- {r.set} {r.case} ({r.dataset}){' (?)' if r.uncertain else ''}: gold {r.gold}, baseline {', '.join(mark(r.gold, p) for p in r.predictions['baseline'])}")

    if groups["candidate"]:
        print(f"\n## Flips baseline -> candidate ({len(flips)})\n")
        for r, before, after in flips:
            print(f"- {r.set} {r.case}{' (?)' if r.uncertain else ''}: gold {r.gold}, {before} -> {after} "
                  f"(baseline {', '.join(mark(r.gold, p) for p in r.predictions['baseline'])}; candidate {', '.join(mark(r.gold, p) for p in r.predictions['candidate'])})")

        gate_rows = [r for r in rows if r.set in GATE_SETS and not r.uncertain]
        b, c = tally(gate_rows, "baseline"), tally(gate_rows, "candidate")
        # Compare rates so a different number of runs per group does not distort the gate.
        rate = lambda t: t[0] / t[3] if t[3] else 0.0  # noqa: E731
        r_rate = lambda t: t[2] / t[3] if t[3] else 0.0  # noqa: E731
        ops = []
        for run_path, run in zip(args.candidate, groups["candidate"]):
            for dataset, data in run.items():
                if set_of(dataset) not in args.sets:
                    continue
                worst = max(data["seconds"].values(), default=0)
                if data["exit"] not in (0, None) or data["invalid"] not in (0, None) or worst >= MAX_CASE_SECONDS:
                    ops.append(f"{run_path.name}/{dataset}: exit {data['exit']}, invalid {data['invalid']}, max {worst} s")
        fallbacks = sum(data["fallbacks"] for run in groups["candidate"] for d, data in run.items() if set_of(d) in args.sets)
        max_seconds = max((s for run in groups["candidate"] for d, data in run.items() if set_of(d) in args.sets for s in data["seconds"].values()), default=0)
        checks = [
            ("1 S: no stable right -> stable wrong", not [r for r in regressions if r.set == "S"], ", ".join(r.case for r in regressions if r.set == "S")),
            ("2 A/B/C: no stable right -> stable wrong", not [r for r in regressions if r.set in GATE_SETS], ", ".join(f"{r.set}:{r.case}" for r in regressions if r.set in GATE_SETS)),
            ("3 accuracy A+B+C not lower", rate(c) >= rate(b) - 1e-9, f"{b[0]}/{b[3]} -> {c[0]}/{c[3]}"),
            ("4 wrong rejections A+B+C not higher", r_rate(c) <= r_rate(b) + 1e-9, f"{b[2]} -> {c[2]}"),
            ("5 exit 0, 0 invalid log lines, max s/case < 240", not ops, ("; ".join(ops) or f"max {max_seconds} s") + f"; {fallbacks} fallback decisions"),
        ]
        print("\n## Gate\n")
        print("| Point | Result | Detail |")
        print("|---|---|---|")
        for label, passed, detail in checks:
            print(f"| {label} | {'pass' if passed else '**FAIL**'} | {detail} |")
        print(f"\nGate: {'PASSED' if all(passed for _, passed, _ in checks) else 'FAILED'}")

    if args.cases:
        print("\n## Per case\n")
        print("| Set | Case | Gold | (?) | Family | Baseline | Candidate |")
        print("|---|---|---|---|---|---|---|")
        for r in rows:
            print(f"| {r.set} | {r.case} | {r.gold} | {'?' if r.uncertain else ''} | {r.family} | {', '.join(mark(r.gold, p) for p in r.predictions['baseline'])} | "
                  f"{', '.join(mark(r.gold, p) for p in r.predictions['candidate'])} |")


if __name__ == "__main__":
    main()
