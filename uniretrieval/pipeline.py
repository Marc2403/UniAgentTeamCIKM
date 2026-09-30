"""The retrieval pipeline: lexical candidates -> collection post-processing ->
optional dense / cross-encoder / LLM reranking of the head.

A complete lexical run (and its trace) is written before any neural stage
runs and rewritten after every stage, so a crash or an exhausted time budget
still leaves a valid run behind."""

import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from uniretrieval.budget import Budget, StageTimer
from uniretrieval.data import Document, Query
from uniretrieval.event_logging import Trace
from uniretrieval.fusion import Ranking, reciprocal_rank_fusion, rerank_head
from uniretrieval.law import LawCollection
from uniretrieval.lexical import LexicalSearcher, build_index
from uniretrieval.llm import ChatModel
from uniretrieval.query_expansion import expand, expansion_prompt
from uniretrieval.rerank_llm import LLMReranker, order_by_grades
from uniretrieval.run_io import validated, write_run
from uniretrieval.text import Decompounder, formulate_query
from uniretrieval.web import DocumentPriors, NearDuplicateFilter

RUN_FILE = "run.txt.gz"
TRACE_FILE = "run-trace.jsonl.log.gz"
TOP = 10


def needs_llm(config: dict) -> bool:
    return bool(config["query_expansion"]["enabled"] or config["llm_rerank"]["enabled"])


def _top(ranking: Ranking, count: int = TOP) -> list[str]:
    return [doc_id for doc_id, _ in ranking[:count]]


class Pipeline:
    def __init__(
        self,
        config: dict,
        queries: list[Query],
        documents: dict[str, Document],
        language: str,
        collection: str,
        output: Path,
        chat_model: ChatModel | None = None,
        index_cache: Path | None = None,
        dataset_key: str = "",
        budget: Budget | None = None,
    ) -> None:
        if needs_llm(config) and chat_model is None:
            raise ValueError("This configuration calls an LLM but no chat model was given.")
        self.config = config
        self.queries = queries
        self.documents = documents
        self.language = language
        self.collection = collection
        self.output = Path(output)
        self.chat_model = chat_model
        self.index_cache = index_cache
        self.dataset_key = dataset_key
        self.budget = budget or Budget(config["budget"]["total_seconds"], config["budget"]["reserve_seconds"])
        self.trace = Trace(chat_model.model_id if chat_model is not None and needs_llm(config) else "-")
        self.law = LawCollection(documents) if collection == "law" else None
        self.timings: dict[str, float] = {}
        self.rankings: dict[str, Ranking] = {}
        self.written_stage: str | None = None

    # -- helpers ----------------------------------------------------------

    def _timed(self, stage: str, started: float) -> None:
        self.timings[stage] = round(self.timings.get(stage, 0.0) + time.monotonic() - started, 3)

    def _write(self, stage: str) -> None:
        qids = [query.qid for query in self.queries]
        fallback = next(iter(self.documents))
        final = validated(self.rankings, qids, fallback, self.config["retrieval"]["depth"])
        write_run(self.output / RUN_FILE, final, f"daim-{self.config['name']}")
        self.trace.write(self.output / TRACE_FILE)
        self.written_stage = stage

    # -- lexical stage ----------------------------------------------------

    def _preprocessor(self):
        settings = self.config["index"]["decompound"]
        if not settings["enabled"]:
            return lambda text: text
        started = time.monotonic()
        decompounder = Decompounder.from_texts(
            (document.text for document in self.documents.values()),
            vocabulary_max_chars=settings["vocabulary_max_chars"],
            min_word_length=settings["min_word_length"],
            min_part_length=settings["min_part_length"],
            min_part_frequency=settings["min_part_frequency"],
        )
        self._timed("decompound_vocabulary", started)
        return decompounder.expand

    def _query_variants(self, preprocess) -> dict[str, dict[str, str]]:
        base = {}
        for query in self.queries:
            text = formulate_query(query, self.config["query"])
            if self.law is not None and self.config["law"]["abbreviations"]:
                text = f"{text} {self.law.expand_abbreviations(text)}".strip()
            base[query.qid] = text
        variants = {"base": base}
        if self.config["query_expansion"]["enabled"]:
            variants["expanded"] = self._expanded_queries(base)
        return {name: {qid: preprocess(text) for qid, text in texts.items()} for name, texts in variants.items()}

    def _expanded_queries(self, base: dict[str, str]) -> dict[str, str]:
        started = time.monotonic()
        settings = self.config["query_expansion"]

        def call(query: Query):
            try:
                return expand(self.chat_model, query, self.language, settings["max_tokens"]), None
            except Exception as error:
                return None, f"{type(error).__name__}: {error}"

        with ThreadPoolExecutor(max_workers=self.config["llm"]["concurrency"]) as pool:
            results = list(pool.map(call, self.queries))
        expanded = {}
        for query, (result, error) in zip(self.queries, results):
            if result is None:
                self.trace.log(
                    query.qid,
                    "model_call",
                    input={"purpose": "query_expansion", "prompt": expansion_prompt(query, self.language)},
                    status="error",
                    error=error,
                )
                expanded[query.qid] = base[query.qid]
                continue
            text, completion, parsed = result
            self.trace.log(
                query.qid,
                "model_call",
                input={"purpose": "query_expansion", "prompt": expansion_prompt(query, self.language)},
                output={"response": completion.text, "terms": parsed["terms"], "usage": completion.usage, "cached": completion.cached},
            )
            expanded[query.qid] = f"{base[query.qid]} {text}"
        self._timed("query_expansion", started)
        return expanded

    def _lexical(self) -> None:
        preprocess = self._preprocessor()
        retrieval = self.config["retrieval"]
        rankers = retrieval["rankers"]
        started = time.monotonic()
        indexes = {
            name: build_index(self.documents, name, self.language, self.config["index"], preprocess, self.index_cache, self.dataset_key)
            for name in dict.fromkeys(ranker["index"] for ranker in rankers)
        }
        self._timed("indexing", started)

        variants = self._query_variants(preprocess)
        searcher = LexicalSearcher(indexes, self.language, retrieval["depth"], retrieval["passage_aggregation"])
        started = time.monotonic()
        per_ranker = []
        for ranker in rankers:
            variant = ranker.get("query_variant", "base")
            if variant not in variants:
                raise ValueError(f"Ranker uses query variant '{variant}', which this configuration does not produce.")
            per_ranker.append(searcher.search(ranker, variants[variant]))
        self._timed("lexical_retrieval", started)

        weights = [float(ranker.get("weight", 1.0)) for ranker in rankers]
        for query in self.queries:
            rankings = [ranking[query.qid] for ranking in per_ranker]
            # RRF even for one ranker, so post-processing bonuses share one score scale.
            fused = reciprocal_rank_fusion(rankings, weights, retrieval["fusion"]["k"])
            self.trace.log(
                query.qid,
                "tool_call",
                tool="lexical_retrieval",
                input={"query_text": variants["base"][query.qid], "rankers": rankers},
                output={"hits": len(fused), "top": _top(fused), "per_ranker_top": [_top(ranking, 3) for ranking in rankings]},
            )
            self.rankings[query.qid] = fused

    # -- collection post-processing ---------------------------------------

    def _postprocess_law(self, query: Query, ranking: Ranking) -> tuple[Ranking, dict[str, Any]]:
        settings, law = self.config["law"], self.law
        notes: dict[str, Any] = {}
        k = self.config["retrieval"]["fusion"]["k"]
        if settings["abbreviation_ranking_weight"] > 0:
            referenced = law.referenced_abbreviations(query)
            if referenced:
                ranking = reciprocal_rank_fusion(
                    [ranking, law.abbreviation_ranking(ranking, referenced)], [1.0, settings["abbreviation_ranking_weight"]], k
                )
                notes["abbreviations"] = referenced
        if settings["doctype_prior_weight"] > 0:
            intent = law.intent(query)
            if intent is not None:
                bonus = settings["doctype_prior_weight"] / (k + 1)
                ranking = sorted(
                    ((doc_id, score + bonus if law.is_decision(doc_id) == (intent == "decision") else score) for doc_id, score in ranking),
                    key=lambda item: -item[1],
                )
                notes["intent"] = intent
        if settings["paragraph_injection"]:
            injected = law.referenced_paragraphs(query)
            if injected:
                top_score = (ranking[0][1] if ranking else 0.0) + 1.0
                head = [(doc_id, top_score + len(injected) - position) for position, doc_id in enumerate(injected)]
                ranking = head + [(doc_id, score) for doc_id, score in ranking if doc_id not in injected]
                notes["injected"] = injected
        if settings["versions"]:
            ranking, demoted = law.collapse_versions(ranking)
            notes["demoted_versions"] = demoted
        return ranking, notes

    def _postprocess(self) -> None:
        started = time.monotonic()
        web = self.config["web"]
        dedup = NearDuplicateFilter(self.documents, **{key: web["dedup"][key] for key in ("threshold", "window", "shingle_words")})
        priors = DocumentPriors(
            self.documents,
            web["priors"]["min_content_chars"],
            web["priors"]["url_penalty_patterns"],
            web["priors"]["penalty"],
        )
        for query in self.queries:
            ranking, notes = self.rankings[query.qid], {}
            if self.law is not None:
                ranking, notes = self._postprocess_law(query, ranking)
            else:
                if web["priors"]["enabled"]:
                    ranking, notes["penalised"] = priors.apply(ranking)
                if web["dedup"]["enabled"]:
                    ranking, notes["near_duplicates"] = dedup.apply(ranking)
            if notes:
                self.trace.log(query.qid, "tool_call", tool=f"{self.collection}_postprocess", input={"collection": self.collection}, output={**notes, "top": _top(ranking)})
            self.rankings[query.qid] = ranking
        self._timed("postprocess", started)

    # -- neural stages ----------------------------------------------------

    def _rerank_stage(self, stage: str, settings: dict, scorer_factory) -> None:
        started = time.monotonic()
        scorer = scorer_factory()
        timer = StageTimer(self.budget, initial_estimate=5.0)
        for query in self.queries:
            if not timer.allows_next():
                self.trace.log(query.qid, "observation", tool=None, input={"stage": stage}, output={"skipped": "time budget"})
                continue
            item_started = time.monotonic()
            head_ids = _top(self.rankings[query.qid], settings["depth"])
            try:
                reranked = scorer.rank(query, head_ids)
            except Exception as error:
                self.trace.log(query.qid, "tool_call", tool=stage, input={"candidates": head_ids}, status="error", error=f"{type(error).__name__}: {error}")
                continue
            self.rankings[query.qid] = rerank_head(self.rankings[query.qid], reranked, settings["weight"], self.config["retrieval"]["fusion"]["k"])
            self.trace.log(
                query.qid,
                "tool_call",
                tool=stage,
                input={"candidates": head_ids, "model": Path(settings["model"]).name},
                output={"scores": [[doc_id, round(score, 4)] for doc_id, score in reranked[:TOP]], "top": _top(self.rankings[query.qid])},
            )
            timer.record(time.monotonic() - item_started)
        self._timed(stage, started)

    def _llm_rerank(self) -> None:
        started = time.monotonic()
        settings = self.config["llm_rerank"]
        reranker = LLMReranker(self.chat_model, self.documents, settings, self.config["llm"]["concurrency"])
        timer = StageTimer(self.budget, initial_estimate=30.0)
        k = self.config["retrieval"]["fusion"]["k"]
        for query in self.queries:
            if not timer.allows_next():
                self.trace.log(query.qid, "observation", input={"stage": "llm_rerank"}, output={"skipped": "time budget"})
                continue
            item_started = time.monotonic()
            ranking = self.rankings[query.qid]
            head = ranking[: settings["depth"]]
            judgments = reranker.judge(query, [doc_id for doc_id, _ in head])
            parent = self.trace.last_event(query.qid)
            for judgment in judgments:
                completion = judgment.completion
                self.trace.log(
                    query.qid,
                    "model_call",
                    input={"purpose": "relevance_judgment", "doc_id": judgment.doc_id, "prompt": judgment.prompt},
                    output=None if completion is None else {
                        "response": completion.text,
                        "grade": judgment.grade,
                        "usage": completion.usage,
                        "cached": completion.cached,
                    },
                    status="ok" if judgment.error is None else "error",
                    error=judgment.error,
                    parent_event_id=parent,
                )
            if all(judgment.grade is None for judgment in judgments):
                self.trace.log(query.qid, "error", input={"stage": "llm_rerank"}, status="error", error="no usable judgment; keeping previous ranking")
            elif settings["combination"] == "grade_primary":
                self.rankings[query.qid] = order_by_grades(head, judgments) + ranking[settings["depth"] :]
            elif settings["combination"] == "rrf":
                graded = order_by_grades(head, judgments)
                self.rankings[query.qid] = rerank_head(ranking, graded, settings["weight"], k)
            else:
                raise ValueError(f"Unknown llm_rerank.combination: {settings['combination']}")
            timer.record(time.monotonic() - item_started)
        self._timed("llm_rerank", started)

    # -- run --------------------------------------------------------------

    def _finish(self) -> None:
        grades: dict[tuple[str, str], Any] = {}
        for event in self.trace.events:
            output = event.get("output")
            if event["event_type"] == "model_call" and isinstance(output, dict) and "grade" in output:
                grades[(event["case_id"], event["input"]["doc_id"])] = output["grade"]
        for query in self.queries:
            top = _top(self.rankings[query.qid])
            self.trace.log(query.qid, "observation", input={"stage": "final"}, output={"top": top})
            self.trace.log(
                query.qid,
                "decision",
                output={
                    "decision": "ranking",
                    "answer": top,
                    "evidence": [
                        {"source_id": doc_id, "rank": rank, "title": self.documents[doc_id].title, "llm_grade": grades.get((query.qid, doc_id))}
                        for rank, doc_id in enumerate(top, start=1)
                    ],
                },
            )

    def run(self) -> dict[str, Any]:
        self.output.mkdir(parents=True, exist_ok=True)
        for query in self.queries:
            self.trace.log(
                query.qid,
                "input",
                input={"query": query.query, "description": query.description, "narrative": query.narrative, "language": query.language},
            )
        self._lexical()
        self._postprocess()
        self._write("lexical")

        if self.config["dense"]["enabled"]:
            from uniretrieval.dense import DenseScorer

            self._rerank_stage("dense", self.config["dense"], lambda: DenseScorer(self.documents, self.config["dense"]))
            self._write("dense")
        if self.config["cross_encoder"]["enabled"]:
            from uniretrieval.rerank_ce import CrossEncoderReranker

            self._rerank_stage(
                "cross_encoder", self.config["cross_encoder"], lambda: CrossEncoderReranker(self.documents, self.config["cross_encoder"])
            )
            self._write("cross_encoder")
        if self.config["llm_rerank"]["enabled"]:
            self._llm_rerank()
            self._write("llm_rerank")

        self._finish()
        self._write("final")
        stats = {
            "config": self.config["name"],
            "collection": self.collection,
            "language": self.language,
            "queries": len(self.queries),
            "documents": len(self.documents),
            "seconds": round(self.budget.elapsed(), 3),
            "timings": self.timings,
            "tokens": getattr(getattr(self.chat_model, "usage", None), "as_dict", dict)(),
        }
        (self.output / "stats.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")
        return stats
