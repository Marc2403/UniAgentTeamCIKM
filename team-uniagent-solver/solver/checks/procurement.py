"""Checks for procurement requests (Beschaffungsantrag)."""

import re

from solver.checks.common import FAIL, NOT_APPLICABLE, PASS, UNCLEAR, Finding, format_amount, same_amount
from solver.schemas import AwardNote, CaseFacts, FrameworkCart, Invoice, InvoiceDocument, LineItem, Offer, ProcurementApplication

DIRECT_AWARD_LIMIT = 1000.0
REQUIRED_OFFERS = 3
VAT_RATE = 0.19

# Product groups with a binding framework contract (rules_procurement.yaml, PROC_FRAMEWORK_CONTRACT).
FRAMEWORK_PRODUCTS = re.compile(
    r"\bPCs?\b|Desktop-?(?:PC|Rechner)|Arbeitsplatzrechner|\bNotebook|\bLaptop|tragbare[rn]? Rechner"
    r"|\bMonitor|\bBildschirm(?!lupe)"
    r"|Büromaterial|Schreibwaren|Kopierpapier|Druckerpapier|Büropapier"
    r"|Bürodrehstuhl|Drehstuhl|Bürostuhl|Seminarstuhl|Büromöbel|Schreibtisch|Rollcontainer|Aktenschrank"
    r"|Kopierer|Kopiergerät|Microsoft|MS[ -]Office|Office 365|Windows[ -]Lizenz",
    re.IGNORECASE,
)


def _first(facts: CaseFacts, model):
    found = facts.extracted(model)
    return found[0] if found else (None, None)


def _item_total(item: LineItem) -> float | None:
    if item.total is not None:
        return item.total
    if item.quantity is not None and item.unit_price is not None:
        return item.quantity * item.unit_price
    return None


def _items_sum(items: list[LineItem]) -> tuple[float | None, bool]:
    """(sum of position totals, whether every position is internally consistent)."""
    totals = [_item_total(item) for item in items]
    if not items or any(total is None for total in totals):
        return None, False
    consistent = all(
        item.quantity is None or item.unit_price is None or item.total is None or same_amount(item.quantity * item.unit_price, item.total)
        for item in items
    )
    return sum(totals), consistent


def is_framework_order(facts: CaseFacts) -> bool:
    _, application = _first(facts, ProcurementApplication)
    return bool(facts.extracted(FrameworkCart)) or bool(application and application.framework_order)


def order_net_total(facts: CaseFacts) -> float | None:
    """Net order value from the request, else its positions, else the framework basket."""
    _, application = _first(facts, ProcurementApplication)
    if application is not None:
        if application.net_total is not None:
            return application.net_total
        if application.gross_total is not None:
            return application.gross_total / (1 + VAT_RATE)
        items_sum, _ = _items_sum(application.items)
        if items_sum is not None:
            return items_sum / (1 + VAT_RATE) if application.prices_are_gross else items_sum
    _, cart = _first(facts, FrameworkCart)
    if cart is not None and cart.net_total is not None:
        return cart.net_total
    offers = [offer.net_total for _, offer in facts.extracted(Offer) if offer.net_total is not None]
    return min(offers) if offers else None


def check_total_matches_items(facts: CaseFacts) -> list[Finding]:
    findings = []
    documents = facts.extracted(ProcurementApplication) + facts.extracted(FrameworkCart) + facts.extracted(Offer)
    for document, data in documents:
        stated = data.net_total
        if isinstance(data, ProcurementApplication) and data.prices_are_gross and data.gross_total is not None:
            stated = data.gross_total
        items_sum, consistent = _items_sum(data.items)
        hard = not isinstance(data, Offer)
        if stated is None or items_sum is None:
            findings.append(Finding("PROC_TOTAL_MATCHES_ITEMS", UNCLEAR, f"{document.name}: Summe oder Positionen nicht vollständig lesbar.", [document.name], hard))
        elif same_amount(items_sum, stated) or same_amount(items_sum, getattr(data, "gross_total", None)):
            findings.append(Finding("PROC_TOTAL_MATCHES_ITEMS", PASS, f"{document.name}: Positionen ergeben {format_amount(items_sum)}, genannt {format_amount(stated)}.", [document.name], hard))
        elif not consistent:
            findings.append(Finding("PROC_TOTAL_MATCHES_ITEMS", UNCLEAR, f"{document.name}: Positionen nicht eindeutig lesbar (Menge × Einzelpreis ≠ Gesamtpreis).", [document.name], hard))
        else:
            deviation = stated - items_sum
            findings.append(
                Finding(
                    "PROC_TOTAL_MATCHES_ITEMS",
                    FAIL,
                    f"{document.name}: Die Positionen ergeben {format_amount(items_sum)}, das Dokument nennt aber {format_amount(stated)} "
                    f"(Abweichung {format_amount(deviation)}, {deviation / items_sum:+.0%}).",
                    [document.name],
                    hard,
                )
            )
    return findings


def _normalise(text: str | None) -> str:
    return re.sub(r"[^0-9a-z]", "", (text or "").lower())


_LEGAL_FORMS = {"gmbh", "kg", "ohg", "ag", "ek", "co", "mbh", "gbr", "ug", "und"}


def _vendor_words(text: str | None) -> set[str]:
    return {word for word in re.findall(r"[a-zäöüß]{3,}", (text or "").lower()) if word not in _LEGAL_FORMS}


def _matching_offer(offers: list[tuple], number: str | None, vendor: str | None):
    """The offer document with the same number (prefix match for cut-off numbers) or vendor name."""
    wanted = _normalise(number)
    if len(wanted) >= 4:
        for document, offer in offers:
            actual = _normalise(offer.number)
            if actual and (actual.startswith(wanted) or wanted.startswith(actual)):
                return document, offer
    wanted_words = _vendor_words(vendor)
    if wanted_words:
        best = max(offers, key=lambda pair: len(wanted_words & _vendor_words(pair[1].vendor)), default=None)
        if best and wanted_words & _vendor_words(best[1].vendor):
            return best
    return None


def check_award_matches_offers(facts: CaseFacts) -> list[Finding]:
    offers = facts.extracted(Offer)
    findings = []
    for document, note in facts.extracted(AwardNote):
        mismatches, unmatched = [], []
        for entry in note.offers:
            match = _matching_offer(offers, entry.number, entry.vendor)
            if match is None or entry.net is None or match[1].net_total is None:
                unmatched.append(entry.number or entry.vendor or "?")
            elif not same_amount(entry.net, match[1].net_total):
                mismatches.append(
                    f"Angebot {entry.number or entry.vendor} steht im Vermerk mit {format_amount(entry.net)} netto, "
                    f"das Angebotsdokument {match[0].name} lautet über {format_amount(match[1].net_total)} netto"
                )
        if mismatches:
            findings.append(Finding("PROC_AWARD_MATCHES_OFFERS", FAIL, f"{document.name}: " + "; ".join(mismatches) + ".", [document.name]))
        elif unmatched or not note.offers:
            findings.append(Finding("PROC_AWARD_MATCHES_OFFERS", UNCLEAR, f"{document.name}: Angebote ohne zuordenbares Dokument: {', '.join(unmatched) or 'keine Angebote gelesen'}.", [document.name], False))
        else:
            findings.append(Finding("PROC_AWARD_MATCHES_OFFERS", PASS, f"{document.name}: Alle {len(note.offers)} Beträge stimmen mit den Angebotsdokumenten überein.", [document.name]))
    return findings


def check_cheapest_offer(facts: CaseFacts) -> list[Finding]:
    offers = [(document, offer) for document, offer in facts.extracted(Offer) if offer.net_total is not None]
    if len(offers) < 2:
        return []
    _, application = _first(facts, ProcurementApplication)
    _, note = _first(facts, AwardNote)
    chosen = None
    if application is not None:
        chosen = _matching_offer(offers, application.offer_reference, application.supplier)
    if chosen is None and note is not None:
        chosen = _matching_offer(offers, None, note.winner_vendor)
    if chosen is None:
        return [Finding("PROC_CHEAPEST_OFFER", UNCLEAR, "Gewähltes Angebot nicht eindeutig zuzuordnen.", [], False)]
    cheapest_document, cheapest = min(offers, key=lambda pair: pair[1].net_total)
    if chosen[1].net_total <= cheapest.net_total + 1.0:
        return [Finding("PROC_CHEAPEST_OFFER", PASS, f"Gewählt ist das günstigste Angebot ({chosen[0].name}, {format_amount(chosen[1].net_total)} netto).", [chosen[0].name], False)]
    return [
        Finding(
            "PROC_CHEAPEST_OFFER",
            FAIL,
            f"Gewählt ist {chosen[0].name} mit {format_amount(chosen[1].net_total)} netto, günstiger ist {cheapest_document.name} mit {format_amount(cheapest.net_total)} netto.",
            [chosen[0].name, cheapest_document.name],
            False,
        )
    ]


def check_comparison_offers(facts: CaseFacts) -> list[Finding]:
    if is_framework_order(facts):
        return [Finding("PROC_COMPARISON_OFFERS", PASS, "Abruf aus einem Rahmenvertrag: Vergleichsangebote entfallen.", [])]
    net = order_net_total(facts)
    if net is None:
        return [Finding("PROC_COMPARISON_OFFERS", UNCLEAR, "Auftragswert nicht bestimmbar.", [], False)]
    if net < DIRECT_AWARD_LIMIT:
        return [Finding("PROC_COMPARISON_OFFERS", PASS, f"Auftragswert {format_amount(net)} netto liegt unter {format_amount(DIRECT_AWARD_LIMIT)}: Direktvergabe zulässig.", [])]
    offer_documents = facts.of_type("offer")
    _, note = _first(facts, AwardNote)
    count = max(len(offer_documents), len(note.offers) if note else 0)
    sources = [document.name for document in offer_documents]
    if count >= REQUIRED_OFFERS:
        return [Finding("PROC_COMPARISON_OFFERS", PASS, f"{count} Angebote liegen vor (Auftragswert {format_amount(net)} netto).", sources)]
    _, application = _first(facts, ProcurementApplication)
    detail = f"Auftragswert {format_amount(net)} netto, aber nur {count} Angebot(e) dokumentiert; erforderlich sind {REQUIRED_OFFERS}."
    if application is not None and application.missing_offers_reason:
        return [Finding("PROC_COMPARISON_OFFERS", UNCLEAR, f"{detail} Angegebene Begründung: {application.missing_offers_reason}", sources, False)]
    return [Finding("PROC_COMPARISON_OFFERS", FAIL, detail, sources, facts.scope == "kassel")]


def _ordered_items(facts: CaseFacts) -> list[str]:
    descriptions = [item.description for _, data in facts.extracted(ProcurementApplication) for item in data.items]
    descriptions += [item.description for _, data in facts.extracted(InvoiceDocument) for invoice in data.invoices for item in invoice.items]
    return [description for description in descriptions if description]


def check_framework_contract(facts: CaseFacts) -> list[Finding]:
    if facts.scope != "kassel":
        return [Finding("PROC_FRAMEWORK_CONTRACT", NOT_APPLICABLE, "Rahmenverträge der Universität Kassel gelten für diese Einrichtung nicht.", [], False)]
    covered = sorted({
        description
        for description in _ordered_items(facts)
        if FRAMEWORK_PRODUCTS.search(description) or facts.item_labels.get(description, {}).get("framework_group")
    })
    if not covered:
        return [Finding("PROC_FRAMEWORK_CONTRACT", PASS, "Keine Position aus einem Rahmenvertragssortiment.", [])]
    if is_framework_order(facts):
        return [Finding("PROC_FRAMEWORK_CONTRACT", PASS, f"Rahmenvertragsartikel ({'; '.join(covered)}) werden über den Rahmenvertrag bestellt.", [])]
    return [
        Finding(
            "PROC_FRAMEWORK_CONTRACT",
            FAIL,
            f"Rahmenvertragsprodukte außerhalb des Rahmenvertrags bestellt: {'; '.join(covered)}.",
            [document.name for document in facts.of_type("application")],
        )
    ]


def check_invoices_match_offer(facts: CaseFacts) -> list[Finding]:
    invoices: list[Invoice] = [invoice for _, data in facts.extracted(InvoiceDocument) for invoice in data.invoices]
    offers = facts.extracted(Offer)
    if not invoices or not offers:
        return []
    _, application = _first(facts, ProcurementApplication)
    chosen = _matching_offer(offers, application.offer_reference if application else None, application.supplier if application else None)
    if chosen is None:
        chosen = _matching_offer(offers, None, invoices[0].issuer)
    if chosen is None or any(invoice.gross_total is None for invoice in invoices):
        return [Finding("PROC_INVOICES_MATCH_OFFER", UNCLEAR, "Rechnungen keinem Angebot sicher zuzuordnen.", [], False)]
    invoiced = sum(invoice.gross_total for invoice in invoices)
    status = PASS if same_amount(invoiced, chosen[1].gross_total) or same_amount(invoiced, chosen[1].net_total) else FAIL
    detail = f"{len(invoices)} Rechnung(en) über zusammen {format_amount(invoiced)}, Angebot {chosen[0].name}: {format_amount(chosen[1].gross_total)} brutto."
    return [Finding("PROC_INVOICES_MATCH_OFFER", status, detail, [chosen[0].name], False)]


CHECKS = (
    check_total_matches_items,
    check_award_matches_offers,
    check_cheapest_offer,
    check_comparison_offers,
    check_framework_contract,
    check_invoices_match_offer,
)
