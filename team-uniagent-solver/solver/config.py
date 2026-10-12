"""Run settings: feature flags for the ablations and the time limits of the TIRA sandbox."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    use_checks: bool = True
    use_retrieval: bool = True
    hard_fail_override: bool = True
    self_consistency_n: int = 1
    # TIRA: 5 min per case and 4 h per run; keep a safety margin on both.
    case_timeout_seconds: float = 240.0
    # The watchdog abandons a case this long after its deadline (240 + 30 < 300 s TIRA limit).
    watchdog_grace_seconds: float = 30.0
    total_budget_seconds: float = 3.75 * 3600
    llm_call_timeout_seconds: float = 120.0
    llm_max_retries: int = 1
    temperature: float = 0.0
    max_output_tokens: int = 8192
    # Decision call; OPENAI_REASONING_EFFORT overrides. Low gave the same spot-check accuracy as the provider
    # default with gpt-oss-20b, with the slowest case at 23 s instead of 65-100 s (ABLATIONS.md).
    reasoning_effort: str | None = "low"
    # Copying fields out of a document needs little reasoning.
    extraction_reasoning_effort: str | None = "low"
    extraction_workers: int = 4
    max_document_characters: int = 12000
    max_prompt_document_characters: int = 30000
    retrieval_hits: int = 2
    cache_dir: str | None = None
