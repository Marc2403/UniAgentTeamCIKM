#!/usr/bin/env python3
import argparse
import json
import logging
import os
import sys
from pathlib import Path
import time

from config import load_llm_config
from event_logging import EventLogger
from llm import call_model, extract_json_object, make_client
from pdf_utils import extract_case
from retrieval import build_retriever

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger("predict")

# Prompt size caps, kept small so the dev free tier (e.g. Groq's 8000 TPM)
# accepts the request. TIRA's hosted vLLM models accept much larger prompts,
# but lean prompts also help the efficiency score, so these caps are safe
# to leave in place for the real run.
MAX_CASE_CHARS_FOR_PROMPT = 6000
MAX_PASSAGE_CHARS = 1200
MAX_QUERY_CHARS = 2000
TOP_K_PASSAGES = 3

PROMPT_TEMPLATE = """Du bist ein Sachbearbeiter der Universitätsverwaltung und prüfst einen Fall nach den einschlägigen Regeln (Hessisches Recht, Regelungen der Universität Kassel).

Falltyp: {case_type}

Fallsachverhalt (aus den PDFs extrahiert):
---
{case_text}
---

Relevante Regelstellen aus den bereitgestellten Corpora:
---
{passages}
---

Aufgabe: Entscheide, ob der Antrag angenommen ("angenommen") oder abgelehnt ("abgelehnt") werden muss. Berücksichtige nur materielle Probleme, keine Pseudonymisierungs-Artefakte. Nutze Datumsangaben ausschließlich aus den Dokumenten.

Antworte ausschließlich mit einem JSON-Objekt in exakt dieser Form:
{{
  "result": "angenommen" oder "abgelehnt",
  "begruendung": "<kurze deutsche Begründung mit Verweis auf Dokumente und Regeln>",
  "evidence": [
    {{"source_id": "<doc_id oder Dateiname>", "page": null, "relevance": "<kurze Erläuterung>"}}
  ]
}}"""


def case_type_from_name(name: str) -> str:
    if name.startswith("dienstreiseantrag-"):
        return "dienstreiseantrag"
    if name.startswith("auslagenerstattung-"):
        return "auslagenerstattung"
    if name.startswith("beschaffungsantrag-"):
        return "beschaffungsantrag"
    return "unknown"


def find_case_dirs(input_dir: Path):
    for p in sorted(input_dir.iterdir()):
        if p.is_dir() and p.name != "retrieval-corpora":
            yield p


def build_prompt(case_type: str, case_text: str, retrieved) -> str:
    if retrieved:
        blocks = []
        for i, r in enumerate(retrieved, 1):
            passage = (r["text"] or "")[:MAX_PASSAGE_CHARS]
            blocks.append(
                f"[{i}] doc_id={r['doc_id']} | {r['title']} | {r['url']}\n{passage}"
            )
        passages = "\n\n".join(blocks)
    else:
        passages = "(keine Regelstellen gefunden)"
    return PROMPT_TEMPLATE.format(
        case_type=case_type,
        case_text=case_text,
        passages=passages,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    input_dir: Path = args.input
    output_dir: Path = args.output
    if not input_dir.is_dir():
        print(f"Input directory not found: {input_dir}", file=sys.stderr)
        return 2
    output_dir.mkdir(parents=True, exist_ok=True)

    skip_llm = os.environ.get("UNIAGENT_SKIP_LLM") == "1"

    if skip_llm:
        model_id = "-"
        client = None
        cfg = {"model": "-", "reasoning_effort": None}
    else:
        cfg = load_llm_config(required=True)
        model_id = cfg["model"]
        client = make_client(cfg["base_url"], cfg["api_key"])

    predictions_path = output_dir / "predictions.jsonl"
    trace_path = output_dir / "run-trace.jsonl.log.gz"
    logger = EventLogger(trace_path, model_id=model_id)

    retriever = build_retriever(input_dir)

    with predictions_path.open("w", encoding="utf-8") as pred_fh:
        for case_dir in find_case_dirs(input_dir):
            case_id = case_dir.name
            if not skip_llm:
                time.sleep(22)
            case_type = case_type_from_name(case_id)
            root_event_id = None
            result = "abgelehnt"
            begruendung = "Fallback: abgelehnt."
            evidence = []

            try:
                root_event_id = logger.emit(
                    case_id=case_id,
                    event_type="input",
                    parent_event_id=None,
                    input={"path": str(case_dir)},
                    output={"case_type": case_type},
                )

                extracted = extract_case(case_dir)
                doc_meta = [
                    {"name": d["name"], "chars": d["chars"], "status": d["status"]}
                    for d in extracted["documents"]
                ]
                logger.emit(
                    case_id=case_id,
                    event_type="observation",
                    parent_event_id=root_event_id,
                    input={"case_type": case_type},
                    output={
                        "documents": doc_meta,
                        "total_chars": len(extracted["full_text"]),
                    },
                    tool="pypdf.extract_text",
                )

                case_text = extracted["full_text"]
                if not case_text:
                    result = "abgelehnt"
                    begruendung = "Kein extrahierbarer Text; Fallback: abgelehnt."
                    logger.emit(
                        case_id=case_id,
                        event_type="error",
                        parent_event_id=root_event_id,
                        input={"case_type": case_type},
                        output={},
                        status="error",
                        error="empty_text_layer",
                    )
                else:
                    # Cap the case text and query so dev free-tier rate limits
                    # (e.g. Groq 8000 TPM) are not exceeded. TIRA's hosted models
                    # accept much larger prompts; these caps are safe to keep.
                    case_text_for_prompt = case_text[:MAX_CASE_CHARS_FOR_PROMPT]
                    query_text = (case_type + " " + case_text)[:MAX_QUERY_CHARS]
                    retrieved = retriever.search(query_text, top_k=TOP_K_PASSAGES)

                    logger.emit(
                        case_id=case_id,
                        event_type="observation",
                        parent_event_id=root_event_id,
                        input={"query_preview": query_text[:200]},
                        output={
                            "retrieved": [
                                {
                                    "doc_id": r["doc_id"],
                                    "score": r["score"],
                                    "corpus": r["corpus"],
                                }
                                for r in retrieved
                            ]
                        },
                        tool="bm25.search",
                    )

                    if skip_llm or client is None:
                        result = "abgelehnt"
                        begruendung = "LLM deaktiviert (UNIAGENT_SKIP_LLM=1); Fallback: abgelehnt."
                        evidence = []
                    else:
                        prompt = build_prompt(case_type, case_text_for_prompt, retrieved)
                        response_text, usage = call_model(
                            client=client,
                            model=cfg["model"],
                            prompt=prompt,
                            timeout=300.0,
                            reasoning_effort=cfg.get("reasoning_effort"),
                            use_structured_output=True,
                        )
                        logger.emit(
                            case_id=case_id,
                            event_type="model_call",
                            parent_event_id=root_event_id,
                            input={
                                "prompt": prompt,
                                "case_type": case_type,
                                "documents": [d["name"] for d in extracted["documents"]],
                            },
                            output={
                                "response": response_text,
                                "usage": usage,
                                "settings": {
                                    "model": cfg["model"],
                                    "temperature": 0,
                                    "reasoning_effort": cfg.get("reasoning_effort"),
                                },
                            },
                        )
                        parsed = extract_json_object(response_text)
                        r = parsed.get("result")
                        if r in ("angenommen", "abgelehnt"):
                            result = r
                        else:
                            raise ValueError(f"Unexpected result value: {r!r}")
                        begruendung = str(parsed.get("begruendung") or "").strip() or begruendung
                        ev = parsed.get("evidence") or []
                        if isinstance(ev, list):
                            evidence = [
                                {
                                    "source_id": str(e.get("source_id", "")),
                                    "page": e.get("page"),
                                    "relevance": str(e.get("relevance", "")),
                                }
                                for e in ev
                                if isinstance(e, dict)
                            ]

            except Exception as exc:
                error_text = f"{type(exc).__name__}: {exc}"
                log.exception("case %s failed", case_id)
                logger.emit(
                    case_id=case_id,
                    event_type="error",
                    parent_event_id=root_event_id,
                    input={"case_id": case_id},
                    output={},
                    status="error",
                    error=error_text,
                )
                result = "abgelehnt"
                begruendung = "Fehler bei der Verarbeitung; Fallback: abgelehnt."
                evidence = []

            decision_output = {
                "decision": result,
                "label": result,
                "answer": begruendung,
                "evidence": evidence,
            }
            logger.emit(
                case_id=case_id,
                event_type="decision",
                parent_event_id=root_event_id,
                input={"case_type": case_type},
                output=decision_output,
            )
            pred_fh.write(
                json.dumps(
                    {"antrag": case_id, "result": result, "begruendung": begruendung},
                    ensure_ascii=False,
                )
                + "\n"
            )
            pred_fh.flush()

    logger.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())