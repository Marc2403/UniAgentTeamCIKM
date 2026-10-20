"""End-to-end tests with real PyTerrier indexes and a scripted LLM (run inside Docker)."""

import gzip
import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from retrieve import main
from test_units import is_valid_event, law_documents
from uniretrieval.budget import Budget
from uniretrieval.config import load_config
from uniretrieval.data import Document, Query, load_dataset
from uniretrieval.llm import ScriptedChatModel
from uniretrieval.pipeline import Pipeline
from uniretrieval.run_io import read_run

CONFIGS = Path(__file__).resolve().parent.parent / "configs"

WEB_DOCUMENTS = {
    "travel": Document("travel", "Dienstreisemanagement", "https://example.org/personal/dienstreisen", "Die Erstattung der Reisekosten und Übernachtungskosten bei Dienstreisen erfolgt nach Antrag."),
    "travel-copy": Document("travel-copy", "Dienstreisemanagement", "https://example.org/personal/dienstreisen-alt", "Die Erstattung der Reisekosten und Übernachtungskosten bei Dienstreisen erfolgt nach Antrag."),
    "library": Document("library", "Zeitschriften", "https://example.org/ub/zeitschriften", "Gedruckte und elektronische Zeitschriften der Universitätsbibliothek."),
    "licence": Document("licence", "Campuslizenz", "https://example.org/its/lizenzen", "Microsoft Campuslizenz beantragen und Software beschaffen."),
}
WEB_QUERIES = [
    Query("1", "Übernachtung Kosten Dienstreise", "Welche Übernachtungskosten werden erstattet?", "Relevant sind Regelungen zum Übernachtungsgeld.", "de"),
    Query("2", "Zeitschriften", "Wie finde ich Zeitschriften?", "", "de"),
    Query("3", "und oder", "", "", "de"),
]


def config(tmp_path: Path, **overrides) -> dict:
    lines = ["extends: " + str(CONFIGS / "ablations" / "q2-desc.yaml")]
    lines += [f"{key}: {json.dumps(value)}" for key, value in overrides.items()]
    (tmp_path / "test.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return load_config(tmp_path / "test.yaml")


def events(output: Path) -> list[dict]:
    return [json.loads(line) for line in gzip.open(output / "run-trace.jsonl.log.gz", "rt", encoding="utf-8")]


def assert_valid_outputs(output: Path, qids: list[str]) -> dict:
    run = read_run(output / "run.txt.gz")
    assert sorted(run) == sorted(qids)
    for ranking in run.values():
        doc_ids = [doc_id for doc_id, _ in ranking]
        scores = [score for _, score in ranking]
        assert len(doc_ids) == len(set(doc_ids))
        assert scores == sorted(scores, reverse=True) and len(set(scores)) == len(scores)
    trace = events(output)
    assert all(is_valid_event(event) for event in trace)
    last_per_case = {event["case_id"]: event for event in trace}
    assert set(last_per_case) == set(qids)
    assert all(event["event_type"] == "decision" for event in last_per_case.values())
    return run


def test_lexical_pipeline_with_decompounding_and_dedup(tmp_path):
    settings = config(
        tmp_path,
        index={"decompound": {"enabled": True, "min_part_frequency": 1}, "url_tokens": True},
        web={"dedup": {"enabled": True, "threshold": 0.9}},
        retrieval={"rankers": [{"index": "body", "wmodel": "DPH"}, {"index": "title", "wmodel": "BM25"}, {"index": "body", "wmodel": "DPH", "prf": "Bo1"}]},
    )
    Pipeline(settings, WEB_QUERIES, WEB_DOCUMENTS, "de", "web", tmp_path / "out").run()
    run = assert_valid_outputs(tmp_path / "out", ["1", "2", "3"])
    assert run["1"][0][0] == "travel"
    assert [doc_id for doc_id, _ in run["1"]][-1] == "travel-copy"
    assert run["2"][0][0] == "library"
    assert run["3"] == [("travel", 1.0)]  # stopword-only query falls back to a placeholder document


def test_passage_index(tmp_path):
    settings = config(tmp_path, index={"passages": {"words": 5, "stride": 3}}, retrieval={"rankers": [{"index": "passages", "wmodel": "BM25"}]})
    Pipeline(settings, WEB_QUERIES[:2], WEB_DOCUMENTS, "de", "web", tmp_path / "out").run()
    run = assert_valid_outputs(tmp_path / "out", ["1", "2"])
    assert run["2"][0][0] == "library"


def test_law_pipeline_injects_current_paragraph(tmp_path):
    documents = law_documents()
    settings = config(tmp_path, law={"abbreviations": True, "paragraph_injection": True, "versions": True, "doctype_prior_weight": 1.0})
    queries = [Query("1", "Reisekostenerstattung HRKG", "", "Relevant ist § 4 HRKG.", "de"), Query("2", "Reisekosten Landrat", "", "Relevant ist das Urteil.", "de")]
    Pipeline(settings, queries, documents, "de", "law", tmp_path / "out").run()
    run = assert_valid_outputs(tmp_path / "out", ["1", "2"])
    assert run["1"][0][0] == "hrkg-4-b"
    assert run["2"][0][0] == "urteil"


def test_llm_rerank_and_query_expansion_with_mock(tmp_path):
    def respond(prompt: str) -> str:
        if "JSON-Objekt" in prompt:
            return '{"terms": ["Hotel", "Übernachtungsgeld"], "passage": "Übernachtungskosten werden erstattet."}'
        return '{"O": 3}' if "Campuslizenz" in prompt.split("Passage:")[1] else '{"O": 0}'

    model = ScriptedChatModel(respond, model_id="gpt-oss-20b")
    settings = config(
        tmp_path,
        query_expansion={"enabled": True},
        llm_rerank={"enabled": True, "depth": 3},
        retrieval={"rankers": [{"index": "body", "wmodel": "DPH"}, {"index": "body", "wmodel": "DPH", "query_variant": "expanded"}]},
    )
    queries = [Query("4", "Software Zeitschriften", "", "", "de")]
    stats = Pipeline(settings, queries, WEB_DOCUMENTS, "de", "web", tmp_path / "out", chat_model=model).run()
    run = assert_valid_outputs(tmp_path / "out", ["4"])
    assert run["4"][0][0] == "licence"  # the mock grades only the licence page as relevant
    trace = events(tmp_path / "out")
    assert {event["model"] for event in trace} == {"gpt-oss-20b"}
    judgments = [event for event in trace if event["event_type"] == "model_call" and event["input"]["purpose"] == "relevance_judgment"]
    assert len(judgments) == 3 and all(event["output"]["grade"] in {0, 3} for event in judgments)
    assert stats["tokens"]["calls"] == 4


def test_llm_failures_fall_back_to_lexical_ranking_and_are_logged(tmp_path):
    def fail(prompt: str) -> str:
        raise TimeoutError("endpoint down")

    settings = config(tmp_path, llm_rerank={"enabled": True, "depth": 3})
    lexical = config(tmp_path)
    Pipeline(lexical, WEB_QUERIES[:2], WEB_DOCUMENTS, "de", "web", tmp_path / "lexical").run()
    Pipeline(settings, WEB_QUERIES[:2], WEB_DOCUMENTS, "de", "web", tmp_path / "out", chat_model=ScriptedChatModel(fail)).run()
    run = assert_valid_outputs(tmp_path / "out", ["1", "2"])
    assert run == read_run(tmp_path / "lexical" / "run.txt.gz")
    trace = events(tmp_path / "out")
    assert any(event["status"] == "error" and "endpoint down" in event["error"] for event in trace)


def test_exhausted_budget_skips_llm_stage_but_writes_valid_run(tmp_path):
    model = ScriptedChatModel(lambda prompt: '{"O": 3}')
    settings = config(tmp_path, llm_rerank={"enabled": True, "depth": 3})
    Pipeline(settings, WEB_QUERIES[:2], WEB_DOCUMENTS, "de", "web", tmp_path / "out", chat_model=model, budget=Budget(1, 0)).run()
    assert_valid_outputs(tmp_path / "out", ["1", "2"])
    assert model.prompts == []
    assert any(event["output"] == {"skipped": "time budget"} for event in events(tmp_path / "out"))


def write_dataset(directory: Path) -> None:
    directory.mkdir()
    with gzip.open(directory / "documents.jsonl.gz", "wt", encoding="utf-8") as handle:
        for document in WEB_DOCUMENTS.values():
            handle.write(json.dumps({"doc_id": document.doc_id, "url": document.url, "title": document.title, "content": document.content, "language": "de"}) + "\n")
    (directory / "queries.jsonl").write_text(
        "".join(
            json.dumps({"qid": int(query.qid), "query": query.query, "original_query": {"language": "de", "description": query.description, "narrative": query.narrative}}) + "\n"
            for query in WEB_QUERIES
        ),
        encoding="utf-8",
    )


def test_cli_end_to_end(tmp_path):
    write_dataset(tmp_path / "dataset")
    queries, documents = load_dataset(str(tmp_path / "dataset"))
    assert documents["travel"].url == "https://example.org/personal/dienstreisen"
    result = CliRunner().invoke(main, ["--dataset", str(tmp_path / "dataset"), "--output", str(tmp_path / "out"), "--config", str(CONFIGS / "lexical-best.yaml")])
    assert result.exit_code == 0, result.output
    assert_valid_outputs(tmp_path / "out", ["1", "2", "3"])


def test_cli_fails_fast_without_llm_environment(tmp_path, monkeypatch):
    write_dataset(tmp_path / "dataset")
    for name in ("OPENAI_BASE_URL", "OPENAI_API_KEY", "OPENAI_MODEL"):
        monkeypatch.delenv(name, raising=False)
    (tmp_path / "llm.yaml").write_text("llm_rerank: {enabled: true}\n")
    result = CliRunner().invoke(main, ["--dataset", str(tmp_path / "dataset"), "--output", str(tmp_path / "out"), "--config", str(tmp_path / "llm.yaml")])
    assert result.exit_code != 0
    assert "OPENAI_BASE_URL" in result.output


@pytest.mark.parametrize("path", sorted(CONFIGS.rglob("*.yaml")), ids=lambda path: path.relative_to(CONFIGS).as_posix())
def test_every_config_loads(path):
    load_config(path)
