import gzip
import json
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import predict  # noqa: E402
from scripts.validate_trace import validate  # noqa: E402
from solver.config import Settings  # noqa: E402
from solver.event_log import case_context, log_event, log_to_file  # noqa: E402
from solver.llm import ScriptedChatModel  # noqa: E402
from solver.pdf import read_pdf  # noqa: E402
from solver.pipeline import solve_case  # noqa: E402


def write_pdf(path: Path, lines: list[str]) -> None:
    """A minimal one-page PDF with a text layer."""
    escaped = [line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") for line in lines]
    content = "BT /F1 10 Tf 50 780 Td 14 TL " + " ".join(f"({line}) '" for line in escaped) + " ET"
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        f"<< /Length {len(content.encode('cp1252'))} >>\nstream\n{content}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    ]
    output = b"%PDF-1.4\n"
    offsets = []
    for number, body in enumerate(objects, 1):
        offsets.append(len(output))
        output += f"{number} 0 obj\n{body}\nendobj\n".encode("cp1252")
    xref = len(output)
    output += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("cp1252")
    output += "".join(f"{offset:010d} 00000 n \n" for offset in offsets).encode("cp1252")
    output += f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode("cp1252")
    path.write_bytes(output)


APPLICATION_LINES = [
    "Universität Wernstadt Beschaffungsantrag / Bestellanforderung Datum: 18.05.2027",
    "1 Labornetzgerät 3 740,00 € 2.220,00 €",
    "2 Schnittstellenmodul 3 60,00 € 180,00 €",
    "Summe netto 3.384,00 €",
]

EXTRACTIONS = {
    "ProcurementApplication": {
        "date": "2027-05-18", "net_total": 3384.0,
        "items": [{"description": "Labornetzgerät", "quantity": 3, "unit_price": 740, "total": 2220}, {"description": "Schnittstellenmodul", "quantity": 3, "unit_price": 60, "total": 180}],
    },
}


def scripted(decision: str = "angenommen") -> ScriptedChatModel:
    def respond(messages):
        prompt = messages[-1]["content"]
        for schema, answer in EXTRACTIONS.items():
            if "Vorlage" in prompt and schema_marker(schema) in prompt:
                return json.dumps(answer)
        return json.dumps({"result": decision, "begruendung": "Begründung des Modells.", "belege": []})

    return ScriptedChatModel(respond)


def schema_marker(schema: str) -> str:
    return {"ProcurementApplication": "offers_obtained"}[schema]


@pytest.fixture
def procurement_case(tmp_path):
    case = tmp_path / "inputs" / "beschaffungsantrag-01"
    case.mkdir(parents=True)
    write_pdf(case / "beschaffungsantrag.pdf", APPLICATION_LINES)
    return case


def run_case(case: Path, llm, tmp_path: Path, settings: Settings = Settings(use_retrieval=False)):
    with log_to_file(tmp_path / "trace.jsonl.gz"), case_context(case.name):
        decision, findings = solve_case(case, llm, None, settings, 240)
    events = [json.loads(line) for line in gzip.open(tmp_path / "trace.jsonl.gz", "rt", encoding="utf-8")]
    return decision, findings, events


def test_pdf_text_layer_is_read(procurement_case):
    pdf = read_pdf(procurement_case / "beschaffungsantrag.pdf")
    assert pdf.error is None and "3.384,00" in pdf.text


def test_hard_failure_rejects_even_if_model_accepts(procurement_case, tmp_path):
    decision, findings, events = run_case(procurement_case, scripted("angenommen"), tmp_path)
    assert decision.result == "abgelehnt" and decision.method == "hard_fail"
    assert any(finding.rule_id == "PROC_TOTAL_MATCHES_ITEMS" and finding.status == "fail" for finding in findings)
    assert {"input", "tool_call", "model_call", "observation"} <= {event["event_type"] for event in events}


def test_model_overrules_nothing_without_hard_failures(procurement_case, tmp_path):
    decision, _, _ = run_case(procurement_case, scripted("angenommen"), tmp_path, Settings(use_retrieval=False, hard_fail_override=False))
    assert decision.result == "angenommen" and decision.method == "llm"


def test_unreachable_model_falls_back_to_checks(procurement_case, tmp_path):
    def fail(messages):
        raise TimeoutError("endpoint down")

    decision, _, events = run_case(procurement_case, ScriptedChatModel(fail), tmp_path)
    assert decision.result == "abgelehnt" and decision.method.startswith("fallback")
    assert any(event["status"] == "error" and "endpoint down" in event["error"] for event in events)


def test_garbage_answers_and_broken_pdf_still_give_a_decision(procurement_case, tmp_path):
    (procurement_case / "kaputt.pdf").write_bytes(b"%PDF-1.4 garbage")
    decision, _, events = run_case(procurement_case, ScriptedChatModel(lambda messages: "kein JSON"), tmp_path)
    assert decision.result in ("angenommen", "abgelehnt") and decision.begruendung
    assert any(event["tool"] == "read_pdf" and event["status"] == "error" for event in events)


def test_predict_writes_one_valid_line_per_case(procurement_case, tmp_path, monkeypatch):
    unknown = procurement_case.parent / "reisekostenabrechnung-01"
    unknown.mkdir()
    write_pdf(unknown / "beleg.pdf", ["Quittung 12,00 EUR"])
    (procurement_case.parent / "leer").mkdir()
    (procurement_case.parent / "auslagenerstattung-09").mkdir()
    monkeypatch.setattr(predict, "OpenAIChatModel", lambda *args: scripted("angenommen"))
    output = tmp_path / "output"
    monkeypatch.setattr(sys, "argv", ["predict.py", "--input", str(procurement_case.parent), "--output", str(output), "--no-retrieval"])
    predict.main()
    lines = [json.loads(line) for line in (output / "predictions.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [line["antrag"] for line in lines] == ["auslagenerstattung-09", "beschaffungsantrag-01", "reisekostenabrechnung-01"]
    assert lines[0]["result"] == "abgelehnt" and lines[1]["result"] == "abgelehnt"
    assert validate(output) == []
    decisions = [json.loads(line) for line in gzip.open(output / "run-trace.jsonl.log.gz", "rt", encoding="utf-8") if '"decision"' in line]
    assert all({"decision", "answer", "evidence"} <= set(event["output"]) for event in decisions if event["event_type"] == "decision")


def test_watchdog_falls_back_and_seals_the_trace(procurement_case, tmp_path, monkeypatch):
    release = threading.Event()

    def hang(case, llm, retriever, settings, time_budget):
        release.wait(5)
        log_event("model_call", input={"purpose": "late"})
        return None

    monkeypatch.setattr(predict, "solve_case", hang)
    settings = Settings(use_retrieval=False, case_timeout_seconds=0.2, watchdog_grace_seconds=0.1)
    with log_to_file(tmp_path / "trace.jsonl.gz"), case_context(procurement_case.name):
        decision, findings = predict.solve_with_watchdog(procurement_case, None, None, settings, 240)
        log_event("decision", output={"decision": decision.result})
        release.set()
        time.sleep(0.2)
    events = [json.loads(line) for line in gzip.open(tmp_path / "trace.jsonl.gz", "rt", encoding="utf-8")]
    assert decision.result == "abgelehnt" and decision.method.startswith("fallback") and findings == []
    assert [event["event_type"] for event in events] == ["error", "decision"]


def test_llm_call_is_abandoned_at_its_deadline(monkeypatch):
    from solver.llm import OpenAIChatModel

    for name, value in (("OPENAI_BASE_URL", "http://localhost:1/v1"), ("OPENAI_API_KEY", "x"), ("OPENAI_MODEL", "m")):
        monkeypatch.setenv(name, value)
    model = OpenAIChatModel(max_tokens=10, temperature=0, max_retries=0)
    request_threads = []

    def hang(*args):
        request_threads.append(threading.current_thread())
        time.sleep(5)

    monkeypatch.setattr(model, "_request", hang)
    started = time.monotonic()
    with pytest.raises(TimeoutError):
        model.complete([{"role": "user", "content": "hi"}], timeout=2)
    assert time.monotonic() - started < 3
    # An abandoned request must not keep the interpreter alive after predict.py has written its output.
    assert request_threads and request_threads[0].daemon


def test_rejected_json_mode_is_dropped_once(monkeypatch):
    from types import SimpleNamespace

    from solver.llm import OpenAIChatModel

    for name, value in (("OPENAI_BASE_URL", "http://localhost:1/v1"), ("OPENAI_API_KEY", "x"), ("OPENAI_MODEL", "m")):
        monkeypatch.setenv(name, value)
    model = OpenAIChatModel(max_tokens=10, temperature=0, max_retries=0)
    sent = []

    def create(**parameters):
        sent.append(sorted(parameters))
        if "response_format" in parameters:
            raise ValueError("400: response_format json_object is not supported by this model")
        message = SimpleNamespace(content='{"ok": true}')
        return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason="stop")], usage=None)

    monkeypatch.setattr(model._client.chat.completions, "create", create)
    assert model.complete([{"role": "user", "content": "hi"}], timeout=5).text == '{"ok": true}'
    model.complete([{"role": "user", "content": "hi again"}], timeout=5)
    assert ["response_format" in parameters for parameters in sent] == [True, False, False]
