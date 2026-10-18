# Gareth UniAgent — preserved policy-v3

Preserved on 18 October 2026 because v3 performed better than the later v4 on the established synthetic and public benchmarks. This is an experimental review snapshot, not an error-free release or proof of overall superiority. It is not necessarily the best configuration on every dataset.

## Verified results

Runtime: GPT-OSS-20B through OpenRouter/Groq, medium reasoning, temperature zero, maximum 8192 output tokens, one case worker. Source snapshot and exact tested image IDs are recorded in the accompanying manifests.

| Evaluation | Correct labels | Correct without fallback | Fallback decisions |
|---|---:|---:|---:|
| Team synthetic set, Gareth v3 | 30/36 (83.3%) | 28/36 | 4 |
| Same set, local team comparison | 29/36 (80.6%) | 29/36 | 0 |
| Official public spot-check, Gareth v3 | 18/21 (85.7%) | 16/21 | 2 |

Synthetic domains: travel 12/12, expenses 8/12, procurement 10/12. Official public domains: travel 5/5, expenses 6/8, procurement 7/8. All official evaluator invocations completed with zero invalid trace lines. Runtime errors remain; valid trace format does not mean error-free execution. The combined comparison cost $0.123731325 across 170 provider requests.

The team comparison preserved team source and pinned Python requirements, but reused a Python 3.10 local base instead of the normal Python 3.12 base. Decision-model/provider/settings were matched; extraction settings remain architecture-specific. The 36 synthetic labels were authored by a teammate and four are disputed. These cases informed development, so they do not establish unseen generalisation. Marc and Rajesh were not rerun here; historical scores are not substituted for matched results.

## What is preserved

`agent/` contains the v3 Python source, tests, pinned dependency declaration and standalone Dockerfile. The archived Python files match source-manifest.json. The portable Dockerfile sets script execution permissions during its build. The measured image ID identifies the actual image used for the reported run; rebuilding dependencies may not reproduce identical image bytes.

`evidence/` contains saved predictions, complete compressed event traces, errors, official evaluator outputs, immutable image IDs and provider usage/cost records. It contains no real API key. This snapshot retains v3's known retry/evidence-validation limitations; it does not silently incorporate v4 changes.

## Build and run

Build from this directory:

```sh
docker build --platform linux/amd64 -t gareth-uniagent-v3 ./agent
```

Set your credentials privately in your shell (do not commit them). Use the configuration names in `.env.example`; it deliberately contains no key. The input folder must contain case PDF folders and the supplied retrieval-corpora folder.

```sh
mkdir -p runs/review
docker run --rm --platform linux/amd64 \
  -e OPENAI_BASE_URL -e OPENAI_API_KEY -e OPENAI_MODEL \
  -e OPENAI_REASONING_EFFORT=medium -e UNIAGENT_STRUCTURED_OUTPUT=off \
  -e UNIAGENT_SNIPPET_MAX_CHARACTERS=700 \
  -v "$PWD/input:/input:ro" -v "$PWD/runs/review:/output" \
  gareth-uniagent-v3 --input /input --output /output --workers 1 --max-output-tokens 8192
```

Running makes paid provider requests. This direct command does not include the local evaluation service's $2 gateway ceiling; set a provider-side spending limit before use. The historical test gateway used fixed Groq routing. A direct OpenRouter run can route elsewhere, so record the actual provider before comparing results.

## Outstanding work

Known issues include empty/truncated response recovery, strict expense evidence formatting, policy scope across anonymised institutions, and misapplication of retrieved rules. The later v4 fixed one recovery defect but regressed on the established benchmarks. Do not call either version error-free. Local evaluator validation has passed, but a successful final TIRA submission/hidden-test result is not included or claimed.

## GitHub upload

Upload this directory's contents into a new folder such as `gareth-uniagent-solver/preserved-policy-v3/` on a new branch of the team repository. Keep the current solver separate for review. No repository upload has been performed automatically.
