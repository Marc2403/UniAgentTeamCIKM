"""Document type from the file name, corrected by keywords in the text."""

import re

DOCUMENT_TYPES = (
    "application",
    "offer",
    "award_note",
    "framework_cart",
    "invoice",
    "proforma_invoice",
    "credit_note",
    "receipt",
    "bank_statement",
    "booking",
    "price_comparison",
    "funding_commitment",
    "correspondence",
    "other",
)

# First match wins, so more specific name parts come first.
_FILENAME_RULES = (
    ("vergabevermerk", "award_note"),
    ("warenkorb", "framework_cart"),
    ("preisvergleich", "price_comparison"),
    ("antrag", "application"),
    ("gutschrift", "credit_note"),
    ("stipendi", "funding_commitment"),
    ("angebot", "offer"),
    ("rechnung", "invoice"),
    ("invoice", "invoice"),
    ("quittung", "receipt"),
    ("kassenbon", "receipt"),
    ("beleg", "receipt"),
    ("kontoauszug", "bank_statement"),
    ("buchung", "booking"),
    ("registrierung", "booking"),
    ("anmelde", "booking"),
    ("ticket", "booking"),
    ("email", "correspondence"),
    ("e-mail", "correspondence"),
    ("korrespondenz", "correspondence"),
)

# Content overrides that hold whatever the file is called.
_PROFORMA = re.compile(r"pro[\s-]?forma", re.IGNORECASE)
_CREDIT_NOTE = re.compile(r"^\s*(?:Gutschrift|Credit note)\b", re.IGNORECASE | re.MULTILINE)
_FUNDING = re.compile(r"Stipendi|travel grant|Reisekostenzuschuss|Fördermittelzusage|Förderzusage", re.IGNORECASE)

# Used only when the file name says nothing.
_CONTENT_RULES = (
    (re.compile(r"Vergabevermerk", re.IGNORECASE), "award_note"),
    (re.compile(r"Warenkorb", re.IGNORECASE), "framework_cart"),
    (re.compile(r"Kontoauszug|Kreditkartenabrechnung|bank statement", re.IGNORECASE), "bank_statement"),
    (re.compile(r"Antrag auf|Beschaffungsantrag|Bestellanforderung", re.IGNORECASE), "application"),
    (re.compile(r"\bAngebot\b|\bquotation\b", re.IGNORECASE), "offer"),
    (re.compile(r"Rechnung|Invoice|Receipt|Quittung", re.IGNORECASE), "invoice"),
    (re.compile(r"\bBON\b|\bKASSE\b|RÜCKGELD|Kassenbon"), "receipt"),
    (re.compile(r"Buchungsbestätigung|Reservierung|booking", re.IGNORECASE), "booking"),
    (re.compile(r"^(?:Von|An|Betreff|From|To|Subject):", re.IGNORECASE | re.MULTILINE), "correspondence"),
)


def classify(filename: str, text: str) -> str:
    name = filename.lower()
    document_type = next((kind for part, kind in _FILENAME_RULES if part in name), None)
    head = text[:1500]
    if document_type in (None, "invoice", "receipt", "booking") and _PROFORMA.search(head):
        return "proforma_invoice"
    if document_type in (None, "invoice") and _CREDIT_NOTE.search(head):
        return "credit_note"
    if document_type in (None, "correspondence") and _FUNDING.search(text):
        return "funding_commitment"
    if document_type is not None:
        return document_type
    return next((kind for pattern, kind in _CONTENT_RULES if pattern.search(head)), "other")
