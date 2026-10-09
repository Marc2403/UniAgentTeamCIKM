"""Curated rule base: one YAML file per case type, each rule citing its corpus sources."""

from functools import cache
from pathlib import Path

import yaml

DIRECTORY = Path(__file__).parent


@cache
def _load(case_type: str) -> tuple[dict, ...]:
    path = DIRECTORY / f"rules_{case_type}.yaml"
    return tuple(yaml.safe_load(path.read_text(encoding="utf-8")) or []) if path.is_file() else ()


def rules_for(case_type: str, scope: str) -> list[dict]:
    return [rule for rule in _load(case_type) if scope in rule.get("applies_to", [])]


def rule_by_id(case_type: str, rule_id: str) -> dict | None:
    return next((rule for rule in _load(case_type) if rule["id"] == rule_id), None)
