
# Omar's UniAgent 2026 Task 2 MVP



Design C: BM25 retrieval + single LLM call with structured JSON output.



## Deterministic

PDF extraction (pypdf), corpus discovery, BM25 retrieval, case-type routing, trace logging.



## LLM

One call per case. Model set by OPENAI_MODEL. reasoning_effort sent only if OPENAI_REASONING_EFFORT is set.



## Dev runtime model

/scratch/models/gpt-oss-20b served by vLLM on an A100. TIRA injects its own model.



## Known failures

Procurement accuracy 0.50 (4/8). Cause not yet diagnosed.



## Development assistant

DeepSeek (model: TODO)

