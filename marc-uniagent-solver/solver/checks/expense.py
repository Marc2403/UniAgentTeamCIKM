"""Checks for reimbursement of privately advanced costs (Auslagenerstattung)."""

import re
from itertools import combinations

from solver.checks.common import FAIL, PASS, UNCLEAR, Finding, format_amount, same_amount
from solver.checks.procurement import framework_items
from solver.schemas import CaseFacts, CreditNote, Invoice, InvoiceDocument

INSTITUTION = re.compile(
    r"Universit(?:ä|ae)t|Hochschule|University|Lehrstuhl|Fachgebiet|Fachbereich|Institut\b|Fakultät|Labor\b|Professur|uni-\w+\.de",
    re.IGNORECASE,
)
# Catering and kitchen equipment for staff (rules_expense.yaml, EXP_HOSPITALITY).
HOSPITALITY = re.compile(
    r"\bKaffee\w*|\bTee\b|Teebeutel|Früchtetee|Kräutertee|Teeküche|Wasserkocher|Kaffeemaschine|\bBecher|\bTassen?\b"
    r"|\bGeschirr|\bMilch\b|\bZucker\b|\bKekse|\bGebäck|Süßigkeit|\bGetränk|Mineralwasser|\bSnacks?\b",
    re.IGNORECASE,
)
GUESTS = re.compile(r"\bGäste\b|\bGast\b|Besucher|Bewirtung extern|externe[rn]? (?:Teilnehm|Person)", re.IGNORECASE)
# Representation costs with a value limit or excluded outright (rules_expense.yaml, EXP_REPRESENTATION).
GUEST_GIFT = re.compile(r"Gastgeschenk|Geschenk für|gift for", re.IGNORECASE)
GIVEAWAY = re.compile(r"Give-?aways?|Werbemittel|Streuartikel|Messestand|Stand der Universität", re.IGNORECASE)
DECORATION = re.compile(r"Weihnachtsbaum|Christbaum|Weihnachtsschmuck|Adventskranz|Lichterkette|Dekoration|\bDeko\b", re.IGNORECASE)
GIFT_LIMIT = 30.0
GIVEAWAY_LIMIT = 10.0


def _invoices(facts: CaseFacts) -> list[tuple[str, Invoice]]:
    return [(document.name, invoice) for document, data in facts.extracted(InvoiceDocument) for invoice in data.invoices]


def check_real_invoice(facts: CaseFacts) -> list[Finding]:
    invoices = _invoices(facts)
    real = [(name, invoice) for name, invoice in invoices if not invoice.is_proforma]
    proforma_documents = {document.name for document in facts.of_type("proforma_invoice")}
    real = [(name, invoice) for name, invoice in real if name not in proforma_documents]
    if real:
        return [Finding("EXP_REAL_INVOICE", PASS, f"{len(real)} Rechnung(en)/Beleg(e) liegen vor.", sorted({name for name, _ in real}))]
    if proforma_documents or invoices:
        names = sorted(proforma_documents | {name for name, _ in invoices})
        return [Finding("EXP_REAL_INVOICE", FAIL, "Es liegt nur eine Pro-forma-Rechnung bzw. kein endgültiger Rechnungsbeleg vor; die eigentliche Rechnung fehlt.", names)]
    if not facts.of_type("invoice", "receipt", "booking"):
        return [Finding("EXP_REAL_INVOICE", FAIL, "Kein Rechnungs- oder Zahlungsbeleg eingereicht.", [])]
    return [Finding("EXP_REAL_INVOICE", UNCLEAR, "Belege nicht auswertbar.", [], False)]


def check_service_reference(facts: CaseFacts) -> list[Finding]:
    invoices = _invoices(facts)
    if not invoices:
        return [Finding("EXP_SERVICE_REFERENCE", UNCLEAR, "Keine Belege ausgewertet.", [], False)]
    receipt_texts = {document.name: document.text for document in facts.of_type("receipt")}
    private = []
    for name, invoice in invoices:
        institutional = invoice.recipient_is_institution or INSTITUTION.search(invoice.recipient or "")
        # A till receipt has no addressee; a purpose noted on it establishes the service reference.
        noted = bool(invoice.handwritten_note) and (invoice.recipient is None or INSTITUTION.search(invoice.handwritten_note))
        # The extraction may report the shop as recipient or drop the note; the receipt text itself still shows it.
        noted_on_receipt = bool(INSTITUTION.search(receipt_texts.get(name, "")))
        if not (institutional or noted or noted_on_receipt):
            private.append((name, invoice))
    if not private:
        return [Finding("EXP_SERVICE_REFERENCE", PASS, "Rechnungsempfänger ist die Hochschule/Einrichtung oder der dienstliche Zweck ist auf dem Beleg vermerkt.", [name for name, _ in invoices])]
    details = "; ".join(f"{name}: Empfänger {invoice.recipient or 'nicht angegeben'}" for name, invoice in private)
    # Hard only when no document of the case names an institution; otherwise the extraction may have missed it.
    hard = not INSTITUTION.search(facts.text)
    return [Finding("EXP_SERVICE_REFERENCE", FAIL, f"Kein dienstlicher Bezug erkennbar ({details}); weder Hochschule noch dienstlicher Zweck genannt.", [name for name, _ in private], hard)]


def _key_items(invoice: Invoice) -> frozenset[str]:
    return frozenset(" ".join((item.description or "").lower().split()) for item in invoice.items if item.description)


def check_duplicates(facts: CaseFacts) -> list[Finding]:
    proforma_documents = {document.name for document in facts.of_type("proforma_invoice")}
    # A pro-forma invoice and the final invoice of the same order are one purchase, not two claims.
    invoices = [(name, invoice) for name, invoice in _invoices(facts) if not invoice.is_proforma and name not in proforma_documents]
    duplicates = []
    for (first_name, first), (second_name, second) in combinations(invoices, 2):
        same_number = first.number and first.number == second.number
        same_order = first.order_number and first.order_number == second.order_number
        same_items = _key_items(first) and _key_items(first) == _key_items(second)
        same_total = first.gross_total is not None and same_amount(first.gross_total, second.gross_total, relative=0.0, absolute=0.01)
        if same_number or (same_total and (same_order or same_items)):
            duplicates.append(
                f"{first.number or first_name} und {second.number or second_name} betreffen dieselbe Bestellung"
                f"{' ' + first.order_number if same_order else ''} über je {format_amount(first.gross_total)}"
            )
    if duplicates:
        return [Finding("EXP_DUPLICATE", FAIL, "; ".join(duplicates) + ": doppelte Abrechnung.", sorted({name for name, _ in invoices}))]
    return [Finding("EXP_DUPLICATE", PASS, "Keine doppelt eingereichte Bestellung.", [])] if len(invoices) > 1 else []


def check_credit_notes(facts: CaseFacts) -> list[Finding]:
    credits = facts.extracted(CreditNote)
    if not credits:
        return []
    invoices = _invoices(facts)
    if any(invoice.gross_total is None for _, invoice in invoices) or any(note.gross_total is None for _, note in credits):
        return [Finding("EXP_CREDIT_NOTES", UNCLEAR, "Beträge von Rechnungen oder Gutschriften nicht lesbar.", [], False)]
    balance = sum(invoice.gross_total for _, invoice in invoices) - sum(abs(note.gross_total) for _, note in credits)
    claims = [amount for amount in [note.claimed_amount for _, note in credits] + [invoice.claimed_amount for _, invoice in invoices] if amount is not None]
    sources = [document.name for document, _ in credits]
    if not claims:
        return [Finding("EXP_CREDIT_NOTES", UNCLEAR, f"Saldo aus Rechnungen abzüglich Gutschriften: {format_amount(balance)}; geltend gemachter Betrag nicht vermerkt.", sources, False)]
    claim = claims[0]
    if same_amount(claim, balance, relative=0.0, absolute=0.05):
        return [Finding("EXP_CREDIT_NOTES", PASS, f"Geltend gemacht {format_amount(claim)} = Rechnungen abzüglich Gutschriften.", sources)]
    return [Finding("EXP_CREDIT_NOTES", FAIL, f"Geltend gemacht {format_amount(claim)}, Rechnungen abzüglich Gutschriften ergeben aber {format_amount(balance)}.", sources)]


def check_hospitality(facts: CaseFacts) -> list[Finding]:
    if facts.scope != "kassel":
        return []
    hits = []
    for name, invoice in _invoices(facts):
        for item in invoice.items:
            if item.description and HOSPITALITY.search(item.description):
                hits.append((name, item.description))
    if not hits:
        return [Finding("EXP_HOSPITALITY", PASS, "Keine Bewirtungs- oder Küchenartikel.", [])]
    if GUESTS.search(facts.text):
        return [Finding("EXP_HOSPITALITY", UNCLEAR, f"Bewirtungsartikel ({'; '.join(text for _, text in hits)}), Gäste werden erwähnt.", sorted({name for name, _ in hits}), False)]
    return [
        Finding(
            "EXP_HOSPITALITY",
            FAIL,
            f"Verpflegung/Küchenausstattung ohne externe Gäste: {'; '.join(text for _, text in hits)}.",
            sorted({name for name, _ in hits}),
        )
    ]


def check_framework_products(facts: CaseFacts) -> list[Finding]:
    if facts.scope != "kassel":
        return []
    invoices = _invoices(facts)
    covered = framework_items([item.description for _, invoice in invoices for item in invoice.items if item.description])
    if not covered:
        return []
    return [Finding("EXP_FRAMEWORK_PRODUCTS", FAIL, f"Rahmenvertragsprodukte privat gekauft: {'; '.join(covered)}; sie sind ausschließlich beim Rahmenvertragspartner zu bestellen.", sorted({name for name, _ in invoices}), False)]


def _unit_gross(invoice: Invoice) -> list[tuple[str, float]]:
    """Gross price per piece; reliable only for a single-position invoice, else the printed unit price."""
    if len(invoice.items) == 1 and invoice.gross_total and invoice.items[0].quantity:
        return [(invoice.items[0].description or "?", invoice.gross_total / invoice.items[0].quantity)]
    return [(item.description or "?", item.unit_price) for item in invoice.items if item.unit_price is not None]


def check_representation(facts: CaseFacts) -> list[Finding]:
    if facts.scope != "kassel":
        return []
    invoices = _invoices(facts)
    names = sorted({name for name, _ in invoices})
    findings = []
    decoration = sorted({item.description for _, invoice in invoices for item in invoice.items if item.description and DECORATION.search(item.description)})
    if decoration:
        findings.append(Finding("EXP_REPRESENTATION", FAIL, f"Schmuck- und Dekorationsartikel: {'; '.join(decoration)}; nicht erstattungsfähig.", names, False))
    totals = [invoice.gross_total for _, invoice in invoices if invoice.gross_total is not None]
    if GUEST_GIFT.search(facts.text) and totals:
        total = sum(totals)
        status = FAIL if total > GIFT_LIMIT + 0.005 else PASS
        findings.append(Finding("EXP_REPRESENTATION", status, f"Gastgeschenk über {format_amount(total)}; übernahmefähig bis {format_amount(GIFT_LIMIT)}.", names, False))
    if GIVEAWAY.search(facts.text):
        units = [(description, price) for _, invoice in invoices for description, price in _unit_gross(invoice)]
        above = [f"{description} ({format_amount(price)} je Stück)" for description, price in units if price > GIVEAWAY_LIMIT + 0.005]
        if above:
            findings.append(Finding("EXP_REPRESENTATION", FAIL, f"Give-aways über {format_amount(GIVEAWAY_LIMIT)} je Stück: {'; '.join(above)}.", names, False))
        elif units:
            findings.append(Finding("EXP_REPRESENTATION", PASS, f"Give-aways bis {format_amount(GIVEAWAY_LIMIT)} je Stück.", names, False))
    return findings


def check_foreign_currency(facts: CaseFacts) -> list[Finding]:
    foreign = [(name, invoice) for name, invoice in _invoices(facts) if invoice.currency and invoice.currency.upper() not in {"EUR", "€", "EURO"}]
    if not foreign:
        return []
    proof = facts.of_type("bank_statement")
    names = [name for name, _ in foreign]
    if proof:
        return [Finding("EXP_FOREIGN_CURRENCY", PASS, "Fremdwährungsbeleg mit Konto-/Kartenabrechnung.", names + [document.name for document in proof], False)]
    return [Finding("EXP_FOREIGN_CURRENCY", UNCLEAR, "Fremdwährungsbeleg ohne Konto-/Kartenabrechnung; Euro-Betrag nicht belegt.", names, False)]


CHECKS = (
    check_real_invoice,
    check_service_reference,
    check_duplicates,
    check_credit_notes,
    check_hospitality,
    check_framework_products,
    check_representation,
    check_foreign_currency,
)
