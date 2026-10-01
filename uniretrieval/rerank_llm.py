"""Pointwise LLM reranking with the prompt the organisers judge with.

The qrels are built by UMBRELA 0.0.7 (`qrel_fewshot_bing.txt`, zero examples)
with gpt-oss-20b (see uniagent-code/cikm26/dataset-construction/create_qrels.py),
so the reranker asks the same question and parses the answer the same way."""

import json
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from uniretrieval.data import Document, Query
from uniretrieval.llm import ChatModel, Completion
from uniretrieval.text import best_passage

UMBRELA_PROMPT = """Given a query and a passage, you must provide a score on an integer scale of 0 to 3 with the following meanings:
0 = represent that the passage has nothing to do with the query, 
1 = represents that the passage seems related to the query but does not answer it, 
2 = represents that the passage has some answer for the query, but the answer may be a bit unclear, or hidden amongst extraneous information and 
3 = represents that the passage is dedicated to the query and contains the exact answer.

Following are some of the examples of relevance categorizations for different categories:



Assume that you are writing a report on the subject of the topic. If you would use any of the information contained in the passage in such a report, mark it 1. If the passage is primarily about the topic mark it 3, or contains vital information about the topic, mark it 2. Otherwise, mark it 0.

Query: {query}
Passage: {passage}

Split this problem into steps:
Consider the underlying intent of the search.
Measure how well the content matches a likely intent of the query (M).
Measure how trustworthy the web page is (T).
Consider the aspects above and the relative importance of each, and decide on a final score (O). Final score must be an integer value only.
Produce a JSON dictionary of scores without providing any reasoning."""

# UMBRELA's patterns first, then looser fallbacks for chattier outputs.
GRADE_PATTERNS = [
    re.compile(pattern, re.IGNORECASE | re.DOTALL)
    for pattern in (
        # UMBRELA's keys in its order, but with optional whitespace: gpt-oss-20b
        # emits compact JSON ('{"score":3}') that UMBRELA's '": ' patterns miss.
        r'"o"\s*:\s*"?(0|1|2|3)',
        r'"overall_score"\s*:\s*"?(0|1|2|3)',
        r'"overall"\s*:\s*"?(0|1|2|3)',
        r'"overall score"\s*:\s*"?(0|1|2|3)',
        r'"final score"\s*:\s*"?(0|1|2|3)',
        r'"final_score"\s*:\s*"?(0|1|2|3)',
        r'"score"\s*:\s*"?(0|1|2|3)',
        r'"o_score"\s*:\s*"?(0|1|2|3)',
        r'"(?:final|relevance|relevance_score)"\s*:\s*"?(0|1|2|3)',
        r"final\s*score\W{0,5}(0|1|2|3)",
        r"\bo\W{1,4}(0|1|2|3)\b",
    )
]


UMBRELA_0_0_7_PATTERNS = [
    re.compile(pattern, re.IGNORECASE | re.MULTILINE | re.DOTALL)
    for pattern in (
        r'"o": (0|1|2|3)',
        r'"overall_score": (0|1|2|3)',
        r'"overall": (0|1|2|3)',
        r'"overall score": (0|1|2|3)',
        r'"final score": (0|1|2|3)',
        r'"final_score": (0|1|2|3)',
        r'"score": (0|1|2|3)',
        r'"o_score": (0|1|2|3)',
    )
]


def parse_grade_umbrela(response: str) -> tuple[int, bool]:
    """UMBRELA 0.0.7's `parse_fewshot_response`: (grade, parsed); unparsed answers become 0."""
    text = response.strip().lower()
    for pattern in UMBRELA_0_0_7_PATTERNS:
        match = pattern.search(text)
        if match:
            return int(match.group(1)), True
    return 0, False


def _single_value_grade(text: str) -> int | None:
    """The grade of a one-entry JSON object under any key, e.g. the query
    itself ('{"office keys": 2}'), or of a bare digit."""
    if text in {"0", "1", "2", "3"}:
        return int(text)
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, dict) and len(parsed) == 1:
        value = next(iter(parsed.values()))
        if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 3:
            return value
    return None


def parse_grade(response: str) -> int | None:
    text = response.strip().lower()
    for pattern in GRADE_PATTERNS:
        match = pattern.search(text)
        if match:
            return int(match.group(1))
    return _single_value_grade(text)


def query_text(query: Query, mode: str) -> str:
    if mode == "query":
        return query.query
    if mode == "query+description":
        return f"{query.query} ({query.description})" if query.description else query.query
    if mode == "all":
        return " ".join(part for part in (query.query, query.description, query.narrative) if part)
    raise ValueError(f"Unknown llm_rerank.query_text: {mode}")


@dataclass
class Judgment:
    doc_id: str
    prompt: str
    completion: Completion | None
    grade: int | None
    error: str | None = None


class LLMReranker:
    def __init__(self, model: ChatModel, documents: dict[str, Document], settings: dict, concurrency: int) -> None:
        self.model = model
        self.documents = documents
        self.settings = settings
        self.concurrency = concurrency

    def prompt(self, query: Query, doc_id: str) -> str:
        text = query_text(query, self.settings["query_text"])
        passage = best_passage(self.documents[doc_id], f"{text} {query.description}", self.settings["max_passage_chars"])
        return UMBRELA_PROMPT.format(query=text, passage=passage)

    def _judge(self, query: Query, doc_id: str) -> Judgment:
        prompt = self.prompt(query, doc_id)
        try:
            completion = self.model.complete(prompt, self.settings["max_tokens"])
        except Exception as error:
            return Judgment(doc_id, prompt, None, None, f"{type(error).__name__}: {error}")
        grade = parse_grade(completion.text)
        error = None if grade is not None else "unparseable grade"
        return Judgment(doc_id, prompt, completion, grade, error)

    def judge(self, query: Query, doc_ids: list[str]) -> list[Judgment]:
        with ThreadPoolExecutor(max_workers=self.concurrency) as pool:
            return list(pool.map(lambda doc_id: self._judge(query, doc_id), doc_ids))


def order_by_grades(head: list[tuple[str, float]], judgments: list[Judgment]) -> list[tuple[str, float]]:
    """Grade first, previous order second. Unjudged documents keep their
    previous grade-less position by counting as grade 1 (between clearly
    irrelevant and relevant)."""
    grades = {judgment.doc_id: judgment.grade for judgment in judgments}
    positions = {doc_id: position for position, (doc_id, _) in enumerate(head)}
    return sorted(head, key=lambda item: (-(grades.get(item[0]) if grades.get(item[0]) is not None else 1), positions[item[0]]))
