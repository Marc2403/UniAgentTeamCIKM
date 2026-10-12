"""Checks for reimbursement of privately advanced costs (Auslagenerstattung)."""

import re
from itertools import combinations

from solver.checks.common import FAIL, PASS, UNCLEAR, Finding, format_amount, same_amount
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
    private = []
    for name, invoice in invoices:
        institutional = invoice.recipient_is_institution or INSTITUTION.search(invoice.recipient or "")
        # A till receipt has no addressee; a purpose noted on it establishes the service reference.
        noted = bool(invoice.handwritten_note) and (invoice.recipient is None or INSTITUTION.search(invoice.handwritten_note))
        if not (institutional or noted):
            private.append((name, invoice))
    if not private:
        return [Finding("EXP_SERVICE_REFERENCE", PASS, "Rechnungsempfänger ist die Hochschule/Einrichtung oder der dienstliche Zweck ist auf dem Beleg vermerkt.", [name for name, _ in invoices])]
    details = "; ".join(f"{name}: Empfänger {invoice.recipient or 'nicht angegeben'}" for name, invoice in private)
    return [Finding("EXP_SERVICE_REFERENCE", FAIL, f"Kein dienstlicher Bezug erkennbar ({details}); weder Hochschule noch dienstlicher Zweck genannt.", [name for name, _ in private])]


def _key_items(invoice: Invoice) -> frozenset[str]:
    return frozenset(" ".join((item.description or "").lower().split()) for item in invoice.items if item.description)


def check_duplicates(facts: CaseFacts) -> list[Finding]:
    invoices = _invoices(facts)
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
            if item.description and (HOSPITALITY.search(item.description) or facts.item_labels.get(item.description, {}).get("catering")):
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
    check_foreign_currency,
)
