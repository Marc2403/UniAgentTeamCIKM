"""Find the cases and background corpora of an input directory."""

import re
from pathlib import Path

CORPORA_DIRECTORY = "retrieval-corpora"

CASE_TYPE_PREFIXES = {
    "dienstreiseantrag": "business_trip",
    "auslagenerstattung": "expense",
    "beschaffungsantrag": "procurement",
}

CASE_TYPE_LABELS = {
    "business_trip": "Dienstreiseantrag",
    "expense": "Auslagenerstattung",
    "procurement": "Beschaffungsantrag",
    "unknown": "Verwaltungsvorgang",
}

# The dataset READMEs name two pseudonymised institutions: Wernstadt cases (and the
# business-trip cases of the University of Kassel itself) follow the Kassel rules and the
# Hessian travel law; Sallstedt cases fall under another state's law that is not in the corpora.
_OTHER_STATE = re.compile(r"Sallstedt", re.IGNORECASE)
_KASSEL_RULES = re.compile(r"Universit(?:ä|ae)t\s+(?:Kassel|Wernstadt)|uni-(?:kassel|wernstadt)|University of Kassel", re.IGNORECASE)


def case_type_for(case_id: str) -> str:
    for prefix, case_type in CASE_TYPE_PREFIXES.items():
        if case_id == prefix or case_id.startswith(f"{prefix}-"):
            return case_type
    return "unknown"


def input_cases(input_root: Path) -> list[Path]:
    """Every directory directly below `input_root` that holds at least one PDF."""
    if not input_root.is_dir():
        raise ValueError(f"Input directory does not exist: {input_root}")
    return sorted(
        path
        for path in input_root.iterdir()
        if path.is_dir() and path.name != CORPORA_DIRECTORY and any(path.glob("*.pdf"))
    )


def discover_corpora(input_root: Path) -> dict[str, Path]:
    """Every retrieval-corpora/<name>/documents.jsonl.gz, found at runtime."""
    return {path.parent.name: path for path in sorted((input_root / CORPORA_DIRECTORY).glob("*/documents.jsonl.gz"))}


def rules_scope(case_text: str) -> str:
    """`other` for institutions under another state's law, else `kassel`."""
    if _OTHER_STATE.search(case_text) and not _KASSEL_RULES.search(case_text):
        return "other"
    return "kassel"
