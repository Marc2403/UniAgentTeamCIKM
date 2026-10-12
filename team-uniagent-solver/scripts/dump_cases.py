#!/usr/bin/env python3
"""Write document type and extracted text of every case to debug/<case>/ (no LLM calls).

Example: scripts/dump_cases.py --input /data/business-trip-spot-check/inputs --input /data/task-2-procurement-spot-check/inputs
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from solver.pipeline import read_case  # noqa: E402
from solver.discovery import input_cases  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, default=Path("debug"))
    args = parser.parse_args()
    for input_root in args.input:
        for case in input_cases(input_root):
            facts = read_case(case)
            directory = args.output / case.name
            directory.mkdir(parents=True, exist_ok=True)
            for document in facts.documents:
                (directory / f"{document.name}.txt").write_text(document.text, encoding="utf-8")
            summary = {"case_type": facts.case_type, "scope": facts.scope, "documents": {document.name: document.document_type for document in facts.documents}}
            (directory / "documents.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"{case.name:26} {facts.scope:7} " + ", ".join(f"{document.name}={document.document_type}" for document in facts.documents))


if __name__ == "__main__":
    main()
