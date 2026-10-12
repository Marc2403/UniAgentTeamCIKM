"""Extraction schemas per document type and the per-case fact bundle.

Every field is optional: the model answers `null` for what a document does not
say, and the checks treat a missing value as `unclear`, never as a violation.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

from solver.checks.common import parse_amount, parse_date


def _to_bool(value: Any) -> bool | None:
    if value is None or isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "ja", "yes", "1", "x"}:
        return True
    if text in {"false", "nein", "no", "0"}:
        return False
    return None


def _to_int(value: Any) -> int | None:
    amount = parse_amount(value)
    return None if amount is None else int(round(amount))


def _to_text(value: Any) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split())
    return text or None


Amount = Annotated[float | None, BeforeValidator(parse_amount)]
Day = Annotated[date | None, BeforeValidator(parse_date)]
Flag = Annotated[bool | None, BeforeValidator(_to_bool)]
Count = Annotated[int | None, BeforeValidator(_to_int)]
Text = Annotated[str | None, BeforeValidator(_to_text)]


class Extraction(BaseModel):
    model_config = ConfigDict(extra="ignore")


class LineItem(Extraction):
    description: Text = Field(None, description="Artikel-/Leistungsbezeichnung wie im Dokument")
    quantity: Amount = Field(None, description="Menge")
    unit_price: Amount = Field(None, description="Einzelpreis")
    total: Amount = Field(None, description="Positionsbetrag (Gesamtpreis der Zeile)")


class ProcurementApplication(Extraction):
    date: Day = Field(None, description="Datum des Antrags bzw. der E-Mail")
    supplier: Text = Field(None, description="vorgesehener Lieferant / Händler / Webshop(s)")
    offer_reference: Text = Field(None, description="Nummer des zugrunde liegenden Angebots oder Warenkorbs")
    items: list[LineItem] = Field(default_factory=list, description="alle Positionen")
    prices_are_gross: Flag = Field(None, description="true, wenn die Positionspreise brutto (inkl. MwSt.) angegeben sind")
    net_total: Amount = Field(None, description="im Antrag genannte Summe netto")
    vat: Amount = Field(None, description="im Antrag genannte Umsatzsteuer")
    gross_total: Amount = Field(None, description="im Antrag genannte Summe brutto")
    framework_order: Flag = Field(None, description="true, wenn ausdrücklich ein Abruf aus einem Rahmenvertrag / Rahmenvertragskatalog / WPS vorliegt")
    offers_obtained: Count = Field(None, description="Anzahl der laut Antrag eingeholten Angebote")
    missing_offers_reason: Text = Field(None, description="Begründung, falls weniger Angebote als üblich eingeholt wurden (z. B. Direktvergabe, Alleinstellung), sonst null")
    approved_by_budget_holder: Flag = Field(None, description="true, wenn die/der Kostenstellenverantwortliche beauftragt/zugestimmt hat")


class Offer(Extraction):
    number: Text = Field(None, description="Angebotsnummer")
    vendor: Text = Field(None, description="anbietende Firma")
    date: Day = Field(None, description="Angebotsdatum")
    items: list[LineItem] = Field(default_factory=list, description="alle Positionen")
    net_total: Amount = Field(None, description="Summe netto")
    vat: Amount = Field(None, description="Umsatzsteuer")
    gross_total: Amount = Field(None, description="Angebotssumme brutto")


class AwardedOffer(Extraction):
    number: Text = Field(None, description="Angebotsnummer laut Vermerk")
    vendor: Text = Field(None, description="Bieter")
    net: Amount = Field(None, description="netto laut Vermerk")
    gross: Amount = Field(None, description="brutto laut Vermerk")
    rank: Count = Field(None, description="Rang laut Vermerk")


class AwardNote(Extraction):
    offers: list[AwardedOffer] = Field(default_factory=list, description="alle im Vermerk gewerteten Angebote")
    winner_vendor: Text = Field(None, description="Bieter, der den Zuschlag erhält")
    winner_net: Amount = Field(None, description="Zuschlagsbetrag netto")


class FrameworkCart(Extraction):
    catalogue: Text = Field(None, description="Katalog / Rahmenvertrag")
    supplier: Text = Field(None, description="Lieferant (Rahmenvertragspartner)")
    number: Text = Field(None, description="Warenkorbnummer")
    items: list[LineItem] = Field(default_factory=list, description="alle Positionen")
    net_total: Amount = Field(None, description="Warenwert netto")
    gross_total: Amount = Field(None, description="Gesamt brutto")


class Invoice(Extraction):
    number: Text = Field(None, description="Rechnungs-/Beleg-/Quittungsnummer")
    date: Day = Field(None, description="Rechnungsdatum")
    issuer: Text = Field(None, description="Aussteller / Verkäufer")
    recipient: Text = Field(None, description="Rechnungsempfänger mit Anschrift, genau wie angegeben (bei Kassenbon ohne Empfänger null)")
    recipient_is_institution: Flag = Field(None, description="true, wenn Rechnungsempfänger oder Lieferadresse eine Hochschule/Universität oder deren Einrichtung ist (auch c/o), false bei reiner Privatanschrift")
    order_number: Text = Field(None, description="Bestell-/Auftragsnummer")
    items: list[LineItem] = Field(default_factory=list, description="alle Positionen")
    net_total: Amount = Field(None, description="Summe netto")
    gross_total: Amount = Field(None, description="Rechnungsbetrag / Gesamtbetrag brutto in Belegwährung")
    currency: Text = Field(None, description="Währung, z. B. EUR oder USD")
    paid: Flag = Field(None, description="true, wenn der Beleg als bezahlt ausgewiesen ist")
    is_proforma: Flag = Field(None, description="true, wenn es eine Pro-forma-Rechnung, ein Angebot oder ein Warenkorb ist und keine echte Rechnung")
    handwritten_note: Text = Field(None, description="handschriftlicher oder nachträglicher Vermerk (z. B. Verwendungszweck, 'sachlich richtig', Erstattungsbetrag), sonst null")
    claimed_amount: Amount = Field(None, description="ausdrücklich zur Erstattung geltend gemachter Betrag, falls vermerkt")


class InvoiceDocument(Extraction):
    invoices: list[Invoice] = Field(default_factory=list, description="jede im Dokument enthaltene Rechnung bzw. jeder Beleg einzeln")


class CreditNote(Extraction):
    number: Text = Field(None, description="Gutschriftsnummer")
    refers_to: Text = Field(None, description="Rechnungsnummer, auf die sich die Gutschrift bezieht")
    gross_total: Amount = Field(None, description="Gutschriftsbetrag brutto")
    handwritten_note: Text = Field(None, description="handschriftlicher Vermerk, sonst null")
    claimed_amount: Amount = Field(None, description="ausdrücklich zur Erstattung geltend gemachter Betrag, falls vermerkt")


class CostItem(Extraction):
    description: Text = Field(None, description="Kostenposition")
    amount: Amount = Field(None, description="Betrag; null, wenn offen, '—' oder nicht angegeben")


class TripApplication(Extraction):
    submission_date: Day = Field(None, description="Datum der Antragstellung")
    departure: Day = Field(None, description="Reisebeginn (Abreise)")
    return_date: Day = Field(None, description="Reiseende (Rückkehr)")
    business_start: Day = Field(None, description="Beginn Dienstgeschäft")
    business_end: Day = Field(None, description="Ende Dienstgeschäft")
    destination: Text = Field(None, description="Reiseziel")
    destination_country: Text = Field(None, description="Land des Reiseziels auf Deutsch, z. B. Deutschland, Frankreich, USA")
    abroad_field: Text = Field(None, description="Feld 'Reise ins Ausland': 'ja', 'nein' oder 'leer', wenn nicht angekreuzt")
    a1_certificate: Text = Field(None, description="Angabe zur A1-Bescheinigung, sonst null")
    transport: Text = Field(None, description="Verkehrsmittel")
    cost_items: list[CostItem] = Field(default_factory=list, description="alle Kostenpositionen der Kostenaufstellung")
    total_requested: Amount = Field(None, description="Summe der beantragten Kosten; null, wenn offen oder 'unvollständig'")
    financing: Text = Field(None, description="Angabe im Feld Finanzierung")
    mentions_third_party_funding: Flag = Field(None, description="true, wenn der Antrag ein Stipendium oder eine Kostenübernahme durch Dritte erwähnt oder anrechnet")
    private_stay_days: Count = Field(None, description="Anzahl Tage privater Aufenthalt (0, wenn keiner)")
    private_costs_excluded: Flag = Field(None, description="true, wenn private Mehrkosten ausdrücklich herausgerechnet und selbst getragen werden")
    nightly_rate: Amount = Field(None, description="Übernachtungspreis pro Nacht")
    late_submission_note: Flag = Field(None, description="true, wenn der Antrag selbst eine nachträgliche Genehmigung erbittet oder die Reise schon stattgefunden hat")


class ThirdPartyFunding(Extraction):
    provider: Text = Field(None, description="wer zahlt")
    max_amount: Amount = Field(None, description="Höchstbetrag")
    currency: Text = Field(None, description="Währung")
    covers: list[str] = Field(default_factory=list, description="abgedeckte Kostenarten, z. B. Flug, Unterkunft, Registrierung")


class TripDocument(Extraction):
    summary: Text = Field(None, description="ein Satz: was belegt das Dokument")
    third_party_funding: ThirdPartyFunding | None = Field(None, description="nur wenn ein Dritter (Stipendium, Veranstalter, Förderer) die Übernahme von Reisekosten verbindlich zusagt, sonst null")


SCHEMAS: dict[tuple[str, str], type[Extraction]] = {
    ("procurement", "application"): ProcurementApplication,
    ("procurement", "offer"): Offer,
    ("procurement", "award_note"): AwardNote,
    ("procurement", "framework_cart"): FrameworkCart,
    ("procurement", "invoice"): InvoiceDocument,
    ("expense", "invoice"): InvoiceDocument,
    ("expense", "receipt"): InvoiceDocument,
    ("expense", "proforma_invoice"): InvoiceDocument,
    ("expense", "booking"): InvoiceDocument,
    ("expense", "credit_note"): CreditNote,
    ("business_trip", "application"): TripApplication,
    ("business_trip", "funding_commitment"): TripDocument,
    ("business_trip", "correspondence"): TripDocument,
}


def schema_for(case_type: str, document_type: str) -> type[Extraction] | None:
    """The schema to extract, or None when no check needs facts from this document type."""
    return SCHEMAS.get((case_type, document_type))


@dataclass
class DocumentFacts:
    name: str
    document_type: str
    text: str
    data: Extraction | None = None
    error: str | None = None


@dataclass
class CaseFacts:
    case_id: str
    case_type: str
    scope: str
    documents: list[DocumentFacts] = field(default_factory=list)
    # Per position description: labels from solver.labels (framework_group, catering).
    item_labels: dict[str, dict] = field(default_factory=dict)

    def of_type(self, *document_types: str) -> list[DocumentFacts]:
        return [document for document in self.documents if document.document_type in document_types]

    def extracted(self, model: type[Extraction]) -> list[tuple[DocumentFacts, Extraction]]:
        return [(document, document.data) for document in self.documents if isinstance(document.data, model)]

    @property
    def text(self) -> str:
        return "\n".join(document.text for document in self.documents)
