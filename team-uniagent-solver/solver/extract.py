"""LLM extraction of one document into its Pydantic schema, validated and cross-checked against the text."""

import json
import re
import time
import typing

from pydantic import BaseModel, ValidationError

from solver.checks.common import parse_amount, parse_date
from solver.discovery import CASE_TYPE_LABELS
from solver.event_log import log_event
from solver.llm import ChatModel, extract_json_object
from solver.schemas import AwardNote, Extraction, FrameworkCart, InvoiceDocument, LineItem, Offer, ProcurementApplication

SYSTEM_PROMPT = (
    "Du liest ein einzelnes Dokument aus einem Verwaltungsvorgang einer Hochschule und überträgst Angaben in JSON.\n"
    "Antworte ausschließlich mit einem JSON-Objekt nach der Vorlage, ohne Markdown und ohne Kommentare.\n"
    "Übernimm nur, was im Dokument steht; was fehlt, offen ('—') oder unleserlich ist, wird null. "
    "Rechne nichts nach und korrigiere nichts: übernimm Beträge genau wie gedruckt, als Zahl mit Punkt als "
    "Dezimaltrenner und ohne Währungszeichen (2.667,00 € -> 2667.0). Datumsangaben als YYYY-MM-DD.\n"
    "Der Text stammt aus einer PDF; Tabellenspalten können verschoben sein. Ordne Menge, Einzelpreis und "
    "Gesamtpreis jeder Position sorgfältig zu."
)

_VALIDATOR_HINTS = {
    parse_amount: "Zahl|null",
    parse_date: '"YYYY-MM-DD"|null',
}


def _hint(annotation, metadata) -> object:
    for item in metadata:
        function = getattr(item, "func", None)
        if function in _VALIDATOR_HINTS:
            return _VALIDATOR_HINTS[function]
        if function is not None:
            name = function.__name__
            return {"_to_bool": "true|false|null", "_to_int": "Ganzzahl|null", "_to_text": '"Text"|null'}.get(name, "null")
    origin = typing.get_origin(annotation)
    if origin is list:
        (argument,) = typing.get_args(annotation)
        return [template(argument)] if isinstance(argument, type) and issubclass(argument, BaseModel) else ['"Text"']
    arguments = [argument for argument in typing.get_args(annotation) if argument is not type(None)]
    if arguments and isinstance(arguments[0], type) and issubclass(arguments[0], BaseModel):
        return template(arguments[0])
    return '"Text"|null'


def template(model: type[BaseModel]) -> dict:
    """A JSON template naming each field's type and meaning, derived from the schema."""
    result = {}
    for name, info in model.model_fields.items():
        hint = _hint(info.annotation, info.metadata)
        if isinstance(hint, str) and info.description:
            hint = f"{hint} – {info.description}"
        elif isinstance(hint, (list, dict)) and info.description:
            result[f"{name} ({info.description})"] = hint
            continue
        result[name] = hint
    return result


def user_prompt(case_type: str, name: str, document_type: str, text: str, model: type[Extraction], max_characters: int) -> str:
    if len(text) > max_characters:
        text = text[:max_characters] + "\n[… gekürzt]"
    guide = json.dumps(template(model), ensure_ascii=False, indent=1)
    return (
        f"Vorgang: {CASE_TYPE_LABELS[case_type]}\nDokument: {name} (Typ: {document_type})\n\n"
        "Vorlage (Schlüssel ohne Klammerzusatz verwenden):\n"
        f"{guide}\n\nDOKUMENT:\n{text}"
    )


def _clean_keys(value):
    """Drop the explanatory '(…)' suffix a model may copy from the template keys."""
    if isinstance(value, dict):
        return {re.sub(r"\s*\(.*$", "", key): _clean_keys(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_clean_keys(item) for item in value]
    return value


def _printed(amount: float | None, text: str) -> bool:
    if amount is None:
        return True
    german = f"{amount:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    english = f"{amount:,.2f}"
    candidates = {german, english, german.replace(".", ""), english.replace(",", "")}
    if amount == int(amount):
        candidates |= {f"{int(amount):,}".replace(",", "."), str(int(amount))}
    return any(re.search(rf"(?<![\d.,]){re.escape(candidate)}(?![\d,]|\.\d)", text) for candidate in candidates)


def _verify_amounts(data: Extraction, text: str) -> list[str]:
    """Null every total the document does not actually print, so a misread never becomes a violation."""
    removed = []

    def check(owner: BaseModel, field: str, label: str) -> None:
        value = getattr(owner, field)
        if not _printed(value, text):
            removed.append(f"{label}={value}")
            setattr(owner, field, None)

    def check_items(items: list[LineItem], label: str) -> None:
        for position, item in enumerate(items, 1):
            check(item, "total", f"{label}.items[{position}].total")
            check(item, "unit_price", f"{label}.items[{position}].unit_price")

    if isinstance(data, (ProcurementApplication, Offer, FrameworkCart)):
        for field in ("net_total", "gross_total"):
            check(data, field, field)
        check_items(data.items, "")
    elif isinstance(data, AwardNote):
        for position, entry in enumerate(data.offers, 1):
            check(entry, "net", f"offers[{position}].net")
            check(entry, "gross", f"offers[{position}].gross")
    elif isinstance(data, InvoiceDocument):
        for position, invoice in enumerate(data.invoices, 1):
            check(invoice, "gross_total", f"invoices[{position}].gross_total")
            check_items(invoice.items, f"invoices[{position}]")
    return removed


def extract_document(
    llm: ChatModel,
    case_type: str,
    name: str,
    document_type: str,
    text: str,
    model: type[Extraction],
    deadline: float,
    call_timeout: float,
    max_characters: int,
    reasoning_effort: str | None = None,
) -> Extraction | None:
    """Ask for the schema, validate, retry once with the error; log every attempt."""
    prompt = user_prompt(case_type, name, document_type, text, model, max_characters)
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}]
    for attempt in (1, 2):
        remaining = deadline - time.monotonic()
        if remaining < 5:
            log_event("error", input={"document": name}, status="error", error="Case time budget exhausted before extraction")
            return None
        try:
            completion = llm.complete(messages, timeout=min(call_timeout, remaining), reasoning_effort=reasoning_effort)
        except Exception as error:
            log_event("model_call", input={"purpose": "extract", "document": name, "schema": model.__name__, "prompt": prompt}, status="error", error=str(error))
            return None
        log_event(
            "model_call",
            input={"purpose": "extract", "document": name, "schema": model.__name__, "attempt": attempt, "prompt": prompt},
            output={"response": completion.text, "usage": completion.usage, "finish_reason": completion.finish_reason, "cached": completion.cached},
        )
        try:
            data = model.model_validate(_clean_keys(extract_json_object(completion.text)))
        except (ValueError, ValidationError) as error:
            log_event("error", input={"document": name}, output={"response": completion.text}, status="error", error=f"Invalid extraction: {error}")
            messages += [
                {"role": "assistant", "content": completion.text},
                {"role": "user", "content": f"Die Antwort war ungültig ({str(error)[:300]}). Antworte nur mit dem JSON-Objekt nach der Vorlage."},
            ]
            continue
        removed = _verify_amounts(data, text)
        log_event("observation", tool=None, input={"document": name}, output={"facts": data.model_dump(mode="json", exclude_none=True), "unverified_amounts_removed": removed})
        return data
    return None
