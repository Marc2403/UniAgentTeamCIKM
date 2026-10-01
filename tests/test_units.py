"""Unit tests for the parts that need neither Java nor models."""

import gzip
import json
from collections import Counter
from datetime import date

import pytest

from uniretrieval.budget import Budget, StageTimer
from uniretrieval.config import load_config
from uniretrieval.data import Document, Query, detect_collection, detect_language
from uniretrieval.event_logging import Trace
from uniretrieval.fusion import reciprocal_rank_fusion, rerank_head
from uniretrieval.law import LawCollection, norm_key
from uniretrieval.llm import ScriptedChatModel
from uniretrieval.metrics import ndcg, per_query, randomization_test
from uniretrieval.query_expansion import parse_expansion
from uniretrieval.devsets import included_query_lines, qrels_path
from uniretrieval.rerank_llm import LLMReranker, UMBRELA_PROMPT, order_by_grades, parse_grade, parse_grade_umbrela
from uniretrieval.run_io import read_run, validated, write_run
from uniretrieval.text import Decompounder, best_passage, formulate_query, strip_narrative_boilerplate, url_tokens
from uniretrieval.web import NearDuplicateFilter

# Fields and checks of the official evaluator (uniagent-code/cikm26/evaluation/evaluate_submission.py).
REQUIRED_EVENT_FIELDS = ("case_id", "event_id", "parent_event_id", "timestamp", "event_type", "model", "tool", "input", "output", "status", "error")


def is_valid_event(entry) -> bool:
    return (
        isinstance(entry, dict)
        and all(field in entry for field in REQUIRED_EVENT_FIELDS)
        and isinstance(entry.get("model"), str)
        and bool(entry["model"].strip())
        and entry.get("status") in {"ok", "error"}
    )


def law_documents() -> dict[str, Document]:
    def norm(doc_id, title, content="", document_type="Gesetz"):
        return Document(doc_id, title, "", content, {"document_type": document_type})

    return {
        "hrkg-2-old": norm("hrkg-2-old", " §\xa02 HRKG | Landesnorm Hessen | Dienstreisen | gültig ab: 30.03.2005 | gültig bis: 31.12.2009", "Hessisches Reisekostengesetz\n(HRKG)\n§ 2 alt"),
        "hrkg-2": norm("hrkg-2", " §\xa02 HRKG | Landesnorm Hessen | Dienstreisen | gültig ab: 01.01.2010", "Hessisches Reisekostengesetz\n(HRKG)\n§ 2 Dienstreisen sind ..."),
        "hrkg-4-a": norm("hrkg-4-a", " §\xa04 HRKG | Landesnorm Hessen | Reisekostenerstattung | gültig ab: 01.01.2010 | gültig bis: 28.11.2024", "Hessisches Reisekostengesetz\n(HRKG)"),
        "hrkg-4-b": norm("hrkg-4-b", " §\xa04 HRKG | Landesnorm Hessen | Reisekostenerstattung | gültig ab: 29.11.2024", "Hessisches Reisekostengesetz\n(HRKG)"),
        "htgv": norm("htgv", "HTGV | Landesnorm Hessen | Hessische Trennungsgeldverordnung (HTGV) vom 20. Oktober 2011 | gültig ab: 01.01.2012", "...", "Verordnung"),
        "urteil": norm("urteil", "1 K 1657/12.KS | VG Kassel 1. Kammer | 29.03.2018 | Urteil", "Reisekosten eines Landrats ...", "Urteil"),
    }


class TestConfig:
    def test_extends_merges_parent_and_names_by_file(self, tmp_path):
        (tmp_path / "parent.yaml").write_text("query: {query_weight: 3}\nretrieval: {depth: 50}\n")
        (tmp_path / "child.yaml").write_text("extends: parent.yaml\nretrieval: {depth: 100}\n")
        config = load_config(tmp_path / "child.yaml")
        assert config["name"] == "child"
        assert config["query"]["query_weight"] == 3
        assert config["query"]["description_weight"] == 0
        assert config["retrieval"]["depth"] == 100


class TestData:
    def test_language_must_be_unique(self):
        with pytest.raises(ValueError, match="found: de, en"):
            detect_language([Query("1", "a", language="de"), Query("2", "b", language="en")])

    def test_collection_detected_from_legal_metadata(self):
        assert detect_collection(law_documents()) == "law"
        assert detect_collection({"d": Document("d", "t", "u", "c")}) == "web"


class TestDevsets:
    def test_excluded_queries_are_skipped_and_qrels_sit_next_to_the_set(self, tmp_path):
        (tmp_path / "dev-extra-de.jsonl").write_text('{"qid": 1}\n{"qid": 2}\n\n{"qid": 3}\n', encoding="utf-8")
        (tmp_path / "excluded.txt").write_text("# duplicates\n2\n", encoding="utf-8")
        assert included_query_lines(tmp_path / "dev-extra-de.jsonl") == ['{"qid": 1}', '{"qid": 3}']
        assert qrels_path(tmp_path / "dev-extra-de.jsonl") == tmp_path / "dev-extra-de.qrels.txt"


class TestText:
    def test_query_parts_are_weighted_and_narrative_boilerplate_removed(self):
        query = Query("1", "Dienstreise", "Wie beantrage ich sie?", "Relevant sind Dokumente zum Dienstreiseantrag.")
        text = formulate_query(query, {"query_weight": 2, "description_weight": 1, "narrative_weight": 1})
        assert text == "Dienstreise Dienstreise Wie beantrage ich sie? Dienstreiseantrag."

    def test_english_narrative_boilerplate(self):
        assert strip_narrative_boilerplate("Relevant documents describe the travel workflow.") == "describe the travel workflow."

    def test_url_tokens(self):
        assert url_tokens("https://www.example.org/finanzen/reise-kosten/antrag.html") == "finanzen reise kosten antrag"

    def test_decompounder_splits_with_linking_s(self):
        vocabulary = Counter({"übernachtung": 50, "kosten": 80, "übernachtungskosten": 3, "reise": 40})
        decompounder = Decompounder(vocabulary, min_part_length=4, min_part_frequency=5)
        assert decompounder.split("Übernachtungskosten") == ["übernachtung", "kosten"]
        assert decompounder.split("Reise") == []
        assert decompounder.expand("Übernachtungskosten erstatten") == "Übernachtungskosten erstatten übernachtung kosten"

    def test_decompounder_keeps_words_more_frequent_than_their_parts(self):
        vocabulary = Counter({"verwaltung": 1000, "verw": 6, "altung": 6})
        assert Decompounder(vocabulary, min_part_length=4).split("verwaltung") == []

    def test_best_passage_picks_matching_window(self):
        content = "Einleitung " * 200 + "Übernachtungsgeld beträgt 20 Euro pro Nacht. " + "Schluss " * 200
        passage = best_passage(Document("d", "Titel", "", content), "Übernachtungsgeld Nacht", 300)
        assert passage.startswith("Titel\n")
        assert "Übernachtungsgeld" in passage and len(passage) <= 300


class TestFusion:
    def test_rrf_rewards_agreement(self):
        fused = reciprocal_rank_fusion([[("a", 3), ("b", 2)], [("b", 9), ("c", 1)]])
        assert [doc_id for doc_id, _ in fused] == ["b", "a", "c"]

    def test_rerank_head_keeps_tail(self):
        ranking = [("a", 4.0), ("b", 3.0), ("c", 2.0), ("d", 1.0)]
        reranked = rerank_head(ranking, [("b", 1.0), ("a", 0.5)], weight=10.0)
        assert [doc_id for doc_id, _ in reranked] == ["b", "a", "c", "d"]
        assert [score for _, score in reranked] == sorted([score for _, score in reranked], reverse=True)


class TestLaw:
    def test_norm_keys(self):
        documents = law_documents()
        assert norm_key(documents["hrkg-2"]) == ("HRKG", "2")
        assert norm_key(documents["htgv"]) == ("HTGV", "")
        assert norm_key(documents["urteil"]) is None

    def test_current_version_is_in_force_and_latest(self):
        law = LawCollection(law_documents(), today=date(2026, 9, 27))
        assert law.current_version(["hrkg-4-a", "hrkg-4-b"]) == "hrkg-4-b"
        assert law.current_version(["hrkg-2-old", "hrkg-2"]) == "hrkg-2"

    def test_abbreviations_are_learned_from_the_collection(self):
        law = LawCollection(law_documents())
        assert law.abbreviations["HRKG"] == "Hessisches Reisekostengesetz"
        assert law.abbreviations["HTGV"] == "Hessische Trennungsgeldverordnung"
        assert law.expand_abbreviations("Übernachtungsgeld HRKG") == "Hessisches Reisekostengesetz"
        assert law.expand_abbreviations("Verwaltungsvorschriften Reisekostengesetz Hessen") == "HRKG"

    def test_paragraph_references_resolve_to_current_version(self):
        law = LawCollection(law_documents(), today=date(2026, 9, 27))
        query = Query("1", "Reisekosten", "", "Relevant ist § 4 Abs. 1 HRKG und § 2 des HRKG.")
        assert law.referenced_paragraphs(query) == ["hrkg-4-b", "hrkg-2"]

    def test_intent(self):
        law = LawCollection(law_documents())
        assert law.intent(Query("1", "Rückforderung", "", "Relevant ist das Urteil zur Rückforderung.")) == "decision"
        assert law.intent(Query("2", "Übernachtungsgeld", "", "Relevant ist § 8 HRKG.")) == "norm"
        assert law.intent(Query("3", "Reisekosten", "", "")) is None

    def test_collapse_versions_shows_current_version_once(self):
        law = LawCollection(law_documents(), today=date(2026, 9, 27))
        ranking = [("hrkg-4-a", 5.0), ("urteil", 4.0), ("hrkg-4-b", 3.0), ("hrkg-2-old", 2.0)]
        collapsed, demoted = law.collapse_versions(ranking)
        assert [doc_id for doc_id, _ in collapsed] == ["hrkg-4-b", "urteil", "hrkg-2", "hrkg-4-a", "hrkg-2-old"]
        assert demoted == ["hrkg-4-a", "hrkg-2-old"]


class TestWeb:
    def test_near_duplicates_move_to_the_end(self):
        text = "die erstattung von reisekosten erfolgt nach dem hessischen reisekostengesetz " * 5
        documents = {
            "a": Document("a", "", "", text),
            "b": Document("b", "", "", text + " kontakt"),
            "c": Document("c", "", "", "ganz anderer inhalt über bibliotheken und zeitschriften " * 5),
        }
        ranking, duplicates = NearDuplicateFilter(documents, 0.8, 100, 5).apply([("a", 3.0), ("b", 2.0), ("c", 1.0)])
        assert [doc_id for doc_id, _ in ranking] == ["a", "c", "b"]
        assert duplicates == ["b"]


class TestMetricsAndRuns:
    def test_ndcg_single_relevant(self):
        assert ndcg(["x", "rel"], {"rel": 1}, 10) == pytest.approx(1 / 1.5849625, rel=1e-6)
        assert ndcg(["rel"], {"rel": 1}, 10) == 1.0

    def test_missing_query_counts_as_zero(self):
        assert per_query({}, {"q": {"d": 1}})["q"]["nDCG@10"] == 0.0

    def test_randomization_test(self):
        assert randomization_test([1.0] * 20, [0.0] * 20) < 0.01
        assert randomization_test([0.5] * 20, [0.5] * 20) == 1.0

    def test_validated_run_is_complete_unique_and_strictly_decreasing(self, tmp_path):
        rankings = validated({"1": [("a", 1.0), ("a", 0.5), ("b", 0.5)]}, ["1", "2"], "fallback", depth=1000)
        write_run(tmp_path / "run.txt.gz", rankings, "tag")
        lines = gzip.open(tmp_path / "run.txt.gz", "rt").read().splitlines()
        assert lines == ["1 Q0 a 1 2.0000 tag", "1 Q0 b 2 1.0000 tag", "2 Q0 fallback 1 1.0000 tag"]
        assert read_run(tmp_path / "run.txt.gz") == {"1": [("a", 2.0), ("b", 1.0)], "2": [("fallback", 1.0)]}


class TestEventLogging:
    def test_events_are_contract_valid_chained_and_end_with_decision(self, tmp_path):
        trace = Trace("-")
        trace.log("q1", "input", input={"query": "x"})
        trace.log("q2", "input", input={"query": "y"})
        first = trace.log("q1", "tool_call", tool="lexical_retrieval", output={"top": ["a"] * 50})
        trace.log("q1", "model_call", status="error", error="timeout")
        trace.log("q1", "decision", output={"decision": "ranking", "answer": ["a"]})
        trace.log("q2", "decision", output={"decision": "ranking", "answer": []})
        trace.write(tmp_path / "trace.gz")
        events = [json.loads(line) for line in gzip.open(tmp_path / "trace.gz", "rt")]
        assert all(is_valid_event(event) for event in events)
        assert [event["case_id"] for event in events] == ["q1"] * 4 + ["q2"] * 2
        assert events[0]["parent_event_id"] is None and events[1]["parent_event_id"] == events[0]["event_id"]
        assert events[2]["parent_event_id"] == first
        assert events[3]["event_type"] == "decision" and events[-1]["event_type"] == "decision"
        assert len(events[1]["output"]["top"]) == 30

    def test_model_is_never_empty(self):
        trace = Trace("")
        trace.log("q", "input")
        assert trace.events[0]["model"] == "-"


class TestLLM:
    def test_umbrela_prompt_placeholders(self):
        assert UMBRELA_PROMPT.count("{query}") == 1 and UMBRELA_PROMPT.count("{passage}") == 1
        assert "Produce a JSON dictionary of scores without providing any reasoning." in UMBRELA_PROMPT

    @pytest.mark.parametrize(
        "response, grade",
        [
            ('{"M": 2, "T": 1, "O": 3}', 3),
            ('{"score":3}', 3),
            ('{"M":1,"T":2,"O":0}', 0),
            ('```json\n{"final_score": 1}\n```', 1),
            ("Final score: 2", 2),
            ('{"Softwarelizenzen beschaffen": 3}', 3),
            ('{"relevance": 1}', 1),
            ('{"intent":1,"match":0,"trustworthiness":3,"final":0}', 0),
            ("2", 2),
            ('{"a": 1, "b": 2}', None),
            ('{"Office keys": 7}', None),
            ("", None),
            ("keine Ahnung", None),
        ],
    )
    def test_parse_grade(self, response, grade):
        assert parse_grade(response) == grade

    def test_grades_first_then_previous_order_and_failures_count_as_one(self):
        documents = {doc_id: Document(doc_id, doc_id, "", "text") for doc_id in "abcd"}
        grades = {"a": '{"O": 0}', "b": '{"O": 3}', "c": "garbage", "d": '{"O": 2}'}
        model = ScriptedChatModel(lambda prompt: grades[prompt.split("Passage: ")[1][0]])
        settings = {"query_text": "query", "max_passage_chars": 500, "max_tokens": 10}
        judgments = LLMReranker(model, documents, settings, concurrency=4).judge(Query("1", "q"), list("abcd"))
        assert [judgment.grade for judgment in judgments] == [0, 3, None, 2]
        ordered = order_by_grades([(doc_id, 1.0) for doc_id in "abcd"], judgments)
        assert [doc_id for doc_id, _ in ordered] == ["b", "d", "c", "a"]
        assert model.usage.calls == 4

    @pytest.mark.parametrize(
        "response, expected",
        [('{"score": 3}', (3, True)), ('{"score":3}', (0, False)), ('{"M": 1, "O": 2}', (2, True)), ("", (0, False))],
    )
    def test_umbrela_0_0_7_parser_needs_a_space_after_the_colon(self, response, expected):
        assert parse_grade_umbrela(response) == expected

    def test_parse_expansion_tolerates_chatter(self):
        parsed = parse_expansion('Here you go:\n```json\n{"terms": ["Reisekosten", 3], "passage": "Die Erstattung ..."}\n```')
        assert parsed == {"terms": ["Reisekosten", "3"], "passage": "Die Erstattung ..."}


class TestBudget:
    def test_stage_timer_stops_when_estimate_exceeds_remaining_time(self):
        now = [0.0]
        budget = Budget(100, 10, clock=lambda: now[0])
        timer = StageTimer(budget, initial_estimate=5)
        assert timer.allows_next()
        timer.record(40)
        now[0] = 55
        assert not timer.allows_next()
