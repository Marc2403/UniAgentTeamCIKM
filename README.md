# UniAgent Team CIKM – MVP Comparison

Each team member puts their MVP in a separate folder `<name>-<project>/` at the repo root.
Each folder is self-contained (own README, dependencies, `.gitignore`).

| Folder | Author | Approach |
|---|---|---|
| [`marc-uniagent-solver/`](marc-uniagent-solver/) | Marc M (@Marc2403) | Task 2 (Solving): LLM extracts, Python checks rules, LLM decides; BM25 retrieval. Results: [`RESULTS.md`](marc-uniagent-solver/RESULTS.md) |
| [`omar-uniagent-solver/`](omar-uniagent-solver/) | Omar (@omar005) | BM25 retrieval + LLM structured JSON |
| [`rajesh-uniagent-solver/`](rajesh-uniagent-solver/) | Rajesh | hull-v4: deterministic rules (T1, T2, E1, E3, P1) + six LLM yes/no labelers (L1–L6) |
| [`gareth-uniagent-solver/`](gareth-uniagent-solver/) | Gareth | Deterministic PDF extraction, retrieval and numeric checks + LLM decision with review and repair attempt. Start with [`READ-ME-FIRST.md`](gareth-uniagent-solver/READ-ME-FIRST.md) |
| [`team-uniagent-solver/`](team-uniagent-solver/) | Team | Combined system: Marc's pipeline as base plus the components that survived the ablation. Comparison: [`evaluation/EVALUATION.md`](evaluation/EVALUATION.md), ablations: [`ABLATIONS.md`](team-uniagent-solver/ABLATIONS.md) |
| [`daim-uniagent-retrieval/`](daim-uniagent-retrieval/) | Marc M (@Marc2403) | Task 1 (Retrieval): PyTerrier lexical pipeline with collection-specific post-processing and LLM reranking of the top 30. Results: [`eval/results-combined.md`](daim-uniagent-retrieval/eval/results-combined.md) |

## Adding your MVP

1. Clone the repo and create a branch: `git checkout -b <name>-mvp`
2. Copy your MVP into `<name>-<project>/`, without secrets (`.env`, API keys) or run artifacts
3. Add a row to the table above
4. Push and open a pull request against `main`
