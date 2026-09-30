"""Pipeline configuration: built-in defaults, overridden by a YAML file.

A config file may name a parent via `extends: <file>` (resolved relative to the
file), so ablation configs only list what they change.
"""

import copy
from pathlib import Path
from typing import Any

import yaml

DEFAULTS: dict[str, Any] = {
    "name": "default",
    "collection": "auto",  # auto | web | law
    "query": {
        "query_weight": 1,
        "description_weight": 0,
        "narrative_weight": 0,
        "strip_narrative_boilerplate": True,
    },
    "index": {
        "title_repeat": 1,
        "url_tokens": False,
        "decompound": {
            "enabled": False,
            "min_word_length": 8,
            "min_part_length": 4,
            "min_part_frequency": 5,
            "vocabulary_max_chars": 20000,
        },
        "passages": {"enabled": False, "words": 250, "stride": 125},
    },
    "retrieval": {
        "depth": 1000,
        # Each ranker: {index: body|title|passages, wmodel, controls, prf, query_variant, weight}
        "rankers": [{"index": "body", "wmodel": "BM25"}],
        "fusion": {"k": 60},
        "passage_aggregation": "max",  # max | sum2
    },
    "law": {
        "abbreviations": False,
        "paragraph_injection": False,
        "abbreviation_ranking_weight": 0.0,
        "versions": False,
        "doctype_prior_weight": 0.0,
    },
    "web": {
        "dedup": {"enabled": False, "threshold": 0.9, "window": 100, "shingle_words": 5},
        "priors": {"enabled": False, "min_content_chars": 0, "url_penalty_patterns": [], "penalty": 0.5},
    },
    "query_expansion": {
        "enabled": False,
        "weight": 1.0,
        "max_tokens": 1024,
    },
    "dense": {
        "enabled": False,
        "model": "/models/multilingual-e5-small",
        "depth": 100,
        "weight": 1.0,
        "max_length": 512,
        "batch_size": 16,
    },
    "cross_encoder": {
        "enabled": False,
        "model": "/models/mmarco-mMiniLMv2-L12-H384-v1",
        "depth": 50,
        "weight": 1.0,
        "max_length": 512,
        "batch_size": 16,
        "max_passage_chars": 2000,
    },
    "llm_rerank": {
        "enabled": False,
        "depth": 20,
        "max_passage_chars": 2000,
        "query_text": "query",  # query | query+description | all
        "combination": "grade_primary",  # grade_primary | rrf
        "weight": 1.0,
        "max_tokens": 1024,
    },
    "llm": {
        "concurrency": 8,
        "timeout_seconds": 60,
        "max_retries": 2,
        "temperature": 0.0,
        "reasoning_effort": "low",
        "cache_dir": None,
    },
    "budget": {"total_seconds": 12600, "reserve_seconds": 300},
}


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _read_with_parents(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"Config {path} must be a YAML mapping.")
    parent = raw.pop("extends", None)
    if parent is None:
        return raw
    return deep_merge(_read_with_parents(path.parent / parent), raw)


def load_config(path: Path | None) -> dict[str, Any]:
    if path is None:
        return copy.deepcopy(DEFAULTS)
    config = deep_merge(DEFAULTS, _read_with_parents(Path(path)))
    config["name"] = Path(path).stem
    return config
