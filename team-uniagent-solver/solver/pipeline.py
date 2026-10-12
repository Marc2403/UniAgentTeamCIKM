"""One case end to end: parse, classify, extract, check, retrieve, decide. Never raises."""

import contextvars
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from solver.checks import run_checks
from solver.checks.common import FAIL, UNCLEAR, Finding
from solver.classify import classify
from solver.config import Settings
from solver.decide import Decision, decide, fallback_decision
from solver.discovery import case_type_for, rules_scope
from solver.event_log import log_event
from solver.extract import extract_document
from solver.knowledge import rule_by_id, rules_for
from solver.labels import label_items
from solver.llm import ChatModel
from solver.pdf import read_pdf
from solver.retrieval import Retriever, best_passage
from solver.schemas import CaseFacts, DocumentFacts, schema_for


def read_case(case_directory: Path, deadline: float) -> CaseFacts:
    case_id = case_directory.name
    case_type = case_type_for(case_id)
    pdfs = sorted(path for path in case_directory.iterdir() if path.is_file() and path.suffix.lower() == ".pdf")
    others = sorted(path.name for path in case_directory.iterdir() if path.is_file() and path not in pdfs)
    log_event("input", input={"case_id": case_id, "case_type": case_type, "documents": [path.name for path in pdfs], "unsupported_files": others})
    documents = []
    for path in pdfs:
        if time.monotonic() > deadline:
            log_event("error", input={"document": path.name}, status="error", error="Case time budget exhausted before reading this PDF")
            continue
        pdf = read_pdf(path)
        log_event(
            "tool_call",
            tool="read_pdf",
            input={"case_id": case_id, "filename": path.name},
            output={"method": pdf.method, "pages": len(pdf.pages), "text": pdf.text},
            status="error" if pdf.error else "ok",
            error=pdf.error,
        )
        documents.append(DocumentFacts(path.name, classify(path.name, pdf.text), pdf.text, error=pdf.error))
    # A request sent as an e-mail thread without its own form is the application.
    if case_type in ("procurement", "business_trip") and not any(document.document_type == "application" for document in documents):
        thread = next((document for document in documents if document.document_type == "correspondence"), None)
        if thread is not None:
            thread.document_type = "application"
    facts = CaseFacts(case_id, case_type, rules_scope("\n".join(document.text for document in documents)), documents)
    log_event("observation", input={"step": "classify"}, output={"scope": facts.scope, "types": {document.name: document.document_type for document in documents}})
    return facts


def extract_facts(llm: ChatModel, facts: CaseFacts, settings: Settings, deadline: float) -> None:
    """Extract all documents of the case in parallel; each thread logs under a copy of the case context."""
    jobs = [(document, schema_for(facts.case_type, document.document_type)) for document in facts.documents]
    jobs = [(document, model) for document, model in jobs if model is not None and document.text]

    def extract(document, model):
        return extract_document(
            llm, facts.case_type, document.name, document.document_type, document.text, model, deadline,
            settings.llm_call_timeout_seconds, settings.max_document_characters, settings.extraction_reasoning_effort,
        )

    with ThreadPoolExecutor(max_workers=max(1, settings.extraction_workers)) as pool:
        futures = [pool.submit(contextvars.copy_context().run, extract, document, model) for document, model in jobs]
        for (document, _), future in zip(jobs, futures):
            document.data = future.result()


def rule_passages(retriever: Retriever | None, rules: list[dict]) -> dict[str, str]:
    """The wording of each curated rule's first source that is present in the corpora."""
    passages = {}
    for rule in rules if retriever else []:
        for source in rule.get("sources", []):
            document = retriever.get(source["corpus"], source["doc_id"])
            if document is not None:
                passages[rule["id"]] = best_passage(document.get("text") or document.get("content") or "", rule.get("query") or rule["text"], 500)
                break
    if passages:
        log_event("observation", input={"step": "rule_sources"}, output={"cited": sorted(passages)})
    return passages


def look_up(retriever: Retriever | None, facts: CaseFacts, findings: list[Finding], hits_per_query: int) -> list[dict]:
    """BM25 look-up for every failed or unclear finding whose rule names a query."""
    if retriever is None:
        return []
    hits, seen = [], set()
    for rule_id in dict.fromkeys(finding.rule_id for finding in findings if finding.status in (FAIL, UNCLEAR)):
        rule = rule_by_id(facts.case_type, rule_id)
        if not rule or not rule.get("query"):
            continue
        try:
            found = retriever.search(rule["query"], hits_per_query)
        except Exception as error:
            log_event("tool_call", tool="retrieve", input={"query": rule["query"]}, status="error", error=str(error))
            continue
        log_event("tool_call", tool="retrieve", input={"query": rule["query"], "k": hits_per_query}, output=[f"{hit.corpus}:{hit.doc_id}" for hit in found])
        for hit in found:
            if (hit.corpus, hit.doc_id) not in seen:
                seen.add((hit.corpus, hit.doc_id))
                hits.append(hit.as_dict())
    return hits


def solve_case(case_directory: Path, llm: ChatModel | None, retriever: Retriever | None, settings: Settings, time_budget: float) -> tuple[Decision, list[Finding]]:
    deadline = time.monotonic() + min(settings.case_timeout_seconds, time_budget)
    findings: list[Finding] = []
    try:
        facts = read_case(case_directory, deadline)
        if not facts.text.strip():
            # Task README: an application is checked for completeness; without any readable document it is not.
            return Decision("abgelehnt", "Der Vorgang enthält keine lesbaren Unterlagen; der Antrag ist nicht prüfbar.", method="no_documents"), findings
        if settings.use_checks:
            if llm is not None:
                extract_facts(llm, facts, settings, deadline)
                label_items(llm, facts, deadline, settings.llm_call_timeout_seconds)
            findings = run_checks(facts)
            log_event("observation", input={"step": "checks"}, output={"findings": [finding.as_dict() for finding in findings]})
        rules = rules_for(facts.case_type, facts.scope)
        passages = rule_passages(retriever, rules)
        hits = look_up(retriever, facts, findings, settings.retrieval_hits)
        decision = decide(
            llm, facts, findings, rules, passages, hits, deadline,
            settings.llm_call_timeout_seconds, settings.hard_fail_override, settings.self_consistency_n,
            settings.max_prompt_document_characters,
        )
    except Exception as error:
        log_event("error", input={"case_id": case_directory.name}, status="error", error=f"{type(error).__name__}: {error}")
        decision = fallback_decision(findings, f"Fehler: {error}")
    return decision, findings
