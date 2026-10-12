"""Narrow LLM labeler for item positions (after Rajesh's yes/no labelers): the model only classifies, Python decides.

One call per case labels every extracted position with the framework-contract product group it belongs to
(rules_procurement.yaml, PROC_FRAMEWORK_CONTRACT) and whether it is catering or kitchen supplies
(rules_expense.yaml, EXP_HOSPITALITY). The checks combine these labels with their keyword patterns.
"""

import json
import time

from solver.event_log import log_event
from solver.llm import ChatModel, extract_json_object
from solver.schemas import CaseFacts, InvoiceDocument, ProcurementApplication

FRAMEWORK_GROUPS = (
    "Büromaterial", "PCs/Notebooks", "Monitore", "Büropapiere", "Bürodrehstühle", "Seminarstühle", "Büromobiliar",
    "Kopiergeräte", "Microsoft-Software",
)

SYSTEM_PROMPT = (
    "Du ordnest Rechnungs- und Bestellpositionen einer Hochschule Kategorien zu. Antworte nur mit JSON, ohne Markdown.\n"
    "framework_group: eine dieser Produktgruppen mit Rahmenvertrag, wenn die Position eindeutig dazu gehört, sonst null: "
    + ", ".join(FRAMEWORK_GROUPS)
    + ". Laborgeräte, Messgeräte, Bücher, Druckaufträge und Spezialzubehör gehören nicht dazu.\n"
    "catering: true, wenn die Position Lebensmittel, Getränke oder Küchen-/Bewirtungsausstattung ist (z. B. Kaffee, Tee, "
    "Wasserkocher, Tassen), sonst false.\n"
    'Format: {"items":[{"index":1,"framework_group":null,"catering":false}]}'
)


def item_descriptions(facts: CaseFacts) -> list[str]:
    descriptions = [item.description for _, data in facts.extracted(ProcurementApplication) for item in data.items]
    descriptions += [item.description for _, data in facts.extracted(InvoiceDocument) for invoice in data.invoices for item in invoice.items]
    return list(dict.fromkeys(description for description in descriptions if description))


def label_items(llm: ChatModel, facts: CaseFacts, deadline: float, call_timeout: float) -> None:
    """Store {description: {"framework_group": str | None, "catering": bool}} in facts.item_labels; log the call."""
    descriptions = item_descriptions(facts)
    remaining = deadline - time.monotonic()
    if facts.case_type not in ("procurement", "expense") or facts.scope != "kassel" or not descriptions or remaining < 10:
        return
    prompt = "Positionen:\n" + "\n".join(f"{index}. {description}" for index, description in enumerate(descriptions, 1))
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}]
    try:
        completion = llm.complete(messages, timeout=min(call_timeout, remaining), reasoning_effort="low")
    except Exception as error:
        log_event("model_call", input={"purpose": "label_items", "prompt": prompt}, status="error", error=str(error))
        return
    log_event(
        "model_call",
        input={"purpose": "label_items", "prompt": prompt},
        output={"response": completion.text, "usage": completion.usage, "finish_reason": completion.finish_reason, "cached": completion.cached},
    )
    try:
        entries = extract_json_object(completion.text).get("items") or []
        for entry in entries:
            index = int(entry.get("index", 0))
            if 1 <= index <= len(descriptions):
                group = entry.get("framework_group")
                facts.item_labels[descriptions[index - 1]] = {
                    "framework_group": group if group in FRAMEWORK_GROUPS else None,
                    "catering": entry.get("catering") is True,
                }
    except (ValueError, TypeError, AttributeError) as error:
        log_event("error", output={"response": completion.text}, status="error", error=f"Invalid item labels: {error}")
        return
    log_event("observation", input={"step": "label_items"}, output={"labels": json.dumps(facts.item_labels, ensure_ascii=False)})
