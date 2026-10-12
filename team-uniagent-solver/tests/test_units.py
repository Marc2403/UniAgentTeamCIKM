from datetime import date

import pytest

from solver.checks import business_trip, expense, procurement
from solver.checks.common import FAIL, PASS, UNCLEAR, amounts_in_text, parse_amount, parse_date
from solver.classify import classify
from solver.discovery import case_type_for, rules_scope
from solver.extract import _verify_amounts, template
from solver.llm import extract_json_object
from solver.schemas import (
    AwardedOffer, AwardNote, CaseFacts, CostItem, CreditNote, DocumentFacts, FrameworkCart, Invoice, InvoiceDocument,
    LineItem, Offer, ProcurementApplication, ThirdPartyFunding, TripApplication, TripDocument,
)


@pytest.mark.parametrize(
    "text, expected",
    [
        ("2.667,00 €", 2667.0), ("€84.02", 84.02), ("USD 175.00", 175.0), ("1.200", 1200.0), ("-229,00 EUR", -229.0),
        ("94,40", 94.4), ("1,234.50", 1234.5), ("673,00 €", 673.0), (19.86, 19.86), ("—", None), (None, None), ("unvollständig", None),
    ],
)
def test_parse_amount(text, expected):
    assert parse_amount(text) == expected


@pytest.mark.parametrize(
    "text, expected",
    [
        ("20.10.2026", date(2026, 10, 20)), ("14. Oktober 2026", date(2026, 10, 14)), ("12-FEB-2027", date(2027, 2, 12)),
        ("2027-02-11", date(2027, 2, 11)), ("BON 4471 KASSE 03 13.03.27 10:42", date(2027, 3, 13)), ("Date 02-SEP-2027", date(2027, 9, 2)),
        ("Montag, 9. März 2026, 07:00 Uhr", date(2026, 3, 9)), ("September 2, 2027", date(2027, 9, 2)), ("Seite 1", None),
    ],
)
def test_parse_date(text, expected):
    assert parse_date(text) == expected


def test_amounts_in_text_reads_german_and_english_formats():
    assert amounts_in_text("Summe netto 2.667,00 € zzgl. 506,73 € Invoice total €94.40 USD 1,175.00") == [2667.0, 506.73, 94.4, 1175.0]


@pytest.mark.parametrize(
    "filename, text, expected",
    [
        ("vergabevermerk.pdf", "", "award_note"),
        ("email-beschaffungsantrag.pdf", "", "application"),
        ("rechnung-laborbedarf.pdf", "Pro-forma-Rechnung", "proforma_invoice"),
        ("email-stipendienzusage.pdf", "", "funding_commitment"),
        ("email-einladung.pdf", "Unfortunately our budget does not allow us to cover travel", "correspondence"),
        ("konferenz-anmeldebestaetigung.pdf", "Universität Kassel", "booking"),
        ("scan-17.pdf", "34121 Kassel, Deutschland Anmeldebestätigung", "other"),
        ("scan-18.pdf", "BON 4471 KASSE 03", "receipt"),
        ("dokument.pdf", "Gutschrift Nr. 12\nzu Rechnung 7", "credit_note"),
    ],
)
def test_classify(filename, text, expected):
    assert classify(filename, text) == expected


def test_case_type_and_scope():
    assert case_type_for("beschaffungsantrag-12") == "procurement"
    assert case_type_for("reisekosten-01") == "unknown"
    assert rules_scope("Technische Hochschule Sallstedt, Medienlabor") == "other"
    assert rules_scope("Universität Wernstadt, Zentrale Beschaffung") == "kassel"
    assert rules_scope("Hotel Musterstadt") == "kassel"


def test_extract_json_object_tolerates_fences_and_prose():
    assert extract_json_object('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json_object('Hier: {"result": "abgelehnt"} fertig') == {"result": "abgelehnt"}
    with pytest.raises(ValueError):
        extract_json_object("keine Antwort")


def test_template_lists_every_field_with_its_type():
    guide = template(TripApplication)
    assert guide["submission_date"].startswith('"YYYY-MM-DD"|null')
    assert any(key.startswith("cost_items") for key in guide)


def test_unprinted_amounts_are_removed():
    offer = Offer(net_total=2600.0, gross_total=3999.0, items=[LineItem(description="Kamera", quantity=1, unit_price=2380, total=2380)])
    removed = _verify_amounts(offer, "Kamera 1 2.380,00 € 2.380,00 € Summe netto 2.600,00 € brutto 3.094,00 €")
    assert offer.net_total == 2600.0 and offer.gross_total is None and removed == ["gross_total=3999.0"]


def facts(case_type, *documents, scope="kassel"):
    return CaseFacts("case-x", case_type, scope, [DocumentFacts(name, kind, text, data) for name, kind, text, data in documents])


def statuses(findings):
    return {finding.rule_id: finding.status for finding in findings}


# Procurement

def application(**fields):
    return ("antrag.pdf", "application", "", ProcurementApplication(**fields))


def offer(name, number, vendor, net):
    return (name, "offer", "", Offer(number=number, vendor=vendor, net_total=net, gross_total=round(net * 1.19, 2)))


def test_stated_total_above_positions_fails():
    items = [LineItem(description="Netzgerät", quantity=3, unit_price=740, total=2220), LineItem(description="Modul", quantity=3, unit_price=60, total=180)]
    findings = procurement.check_total_matches_items(facts("procurement", application(items=items, net_total=3384.0)))
    assert findings[0].status == FAIL and findings[0].hard


def test_gross_positions_match_gross_total():
    items = [LineItem(description="Board", quantity=8, unit_price=14.8, total=118.4), LineItem(description="Matte", quantity=2, unit_price=29.95, total=59.9)]
    findings = procurement.check_total_matches_items(facts("procurement", application(items=items, gross_total=178.3, prices_are_gross=True)))
    assert findings[0].status == PASS


def test_award_note_with_wrong_offer_amount_fails():
    note = AwardNote(offers=[AwardedOffer(number="A-1", vendor="Alpha GmbH", net=2600), AwardedOffer(number="B-22", vendor="Beta KG", net=3243)])
    case = facts("procurement", offer("angebot-1.pdf", "A-1", "Alpha GmbH", 2600), offer("angebot-2.pdf", "B-22", "Beta KG", 2350), ("vergabevermerk.pdf", "award_note", "", note))
    assert procurement.check_award_matches_offers(case)[0].status == FAIL


def test_award_number_cut_off_still_matches():
    note = AwardNote(offers=[AwardedOffer(number="ELS-A-2027-2", vendor="Sturm", net=2586)])
    case = facts("procurement", offer("angebot-2.pdf", "ELS-A-2027-219", "Elektro Sturm GmbH", 2586), ("vergabevermerk.pdf", "award_note", "", note))
    assert procurement.check_award_matches_offers(case)[0].status == PASS


def test_direct_award_below_limit_passes_with_one_offer():
    case = facts("procurement", application(net_total=673.0), offer("angebot-1.pdf", "D-1", "Delta", 673.0))
    assert procurement.check_comparison_offers(case)[0].status == PASS


def test_two_offers_above_limit_fail_only_under_kassel_rules():
    documents = (application(net_total=2670.0), offer("angebot-1.pdf", "I-1", "Iota", 2670.0), offer("angebot-2.pdf", "S-1", "Sigma", 2765.0))
    assert procurement.check_comparison_offers(facts("procurement", *documents))[0].hard
    assert not procurement.check_comparison_offers(facts("procurement", *documents, scope="other"))[0].hard


def test_framework_products_outside_framework_fail():
    items = [LineItem(description="Monitor 27 Zoll, WQHD", quantity=2, unit_price=169, total=338), LineItem(description="Multimeter", quantity=1, unit_price=38.5, total=38.5)]
    assert procurement.check_framework_contract(facts("procurement", application(items=items)))[0].status == FAIL
    cart = ("warenkorb.pdf", "framework_cart", "", FrameworkCart(catalogue="Rahmenvertrag IT"))
    assert procurement.check_framework_contract(facts("procurement", application(items=items), cart))[0].status == PASS
    assert procurement.check_comparison_offers(facts("procurement", application(items=items, net_total=2971.8), cart))[0].status == PASS


def test_cheapest_offer_identified_by_reference():
    case = facts("procurement", application(offer_reference="A-1", supplier="Alpha"), offer("angebot-1.pdf", "A-1", "Alpha", 2600), offer("angebot-2.pdf", "B-2", "Beta", 2350))
    assert procurement.check_cheapest_offer(case)[0].status == FAIL


# Expense

def invoice_document(name, *invoices, kind="invoice"):
    return (name, kind, "", InvoiceDocument(invoices=list(invoices)))


def test_proforma_only_fails():
    case = facts("expense", invoice_document("rechnung.pdf", Invoice(is_proforma=True, gross_total=88.93), kind="proforma_invoice"))
    assert expense.check_real_invoice(case)[0].status == FAIL


def test_private_recipient_without_note_fails_and_receipt_with_note_passes():
    private = facts("expense", invoice_document("rechnung.pdf", Invoice(recipient="Erika Muster, Hauptstr. 1, 95444 Bayreuth", recipient_is_institution=False)))
    assert expense.check_service_reference(private)[0].status == FAIL
    receipt = facts("expense", invoice_document("beleg.pdf", Invoice(recipient=None, handwritten_note="Kabelbinder für Versuchsstand"), kind="receipt"))
    assert expense.check_service_reference(receipt)[0].status == PASS


def test_same_order_invoiced_twice_fails_but_reprint_does_not():
    items = [LineItem(description="Adapter"), LineItem(description="Kabel")]
    twice = facts("expense", invoice_document("r1.pdf", Invoice(number="1", order_number="O-9", gross_total=103.44, items=items)), invoice_document("r2.pdf", Invoice(number="2", order_number="O-9", gross_total=103.44, items=items)))
    assert expense.check_duplicates(twice)[0].status == FAIL
    reprint = facts("expense", invoice_document("r.pdf", Invoice(number="1", order_number="A-1", gross_total=121.38), Invoice(number="2", order_number="A-1", gross_total=83.32)))
    assert expense.check_duplicates(reprint)[0].status == PASS


def test_claimed_balance_after_credit_note():
    invoices = invoice_document("r.pdf", Invoice(gross_total=121.38), Invoice(gross_total=83.32))
    right = facts("expense", invoices, ("gs.pdf", "credit_note", "", CreditNote(gross_total=69.02, claimed_amount=135.68)))
    wrong = facts("expense", invoices, ("gs.pdf", "credit_note", "", CreditNote(gross_total=69.02, claimed_amount=204.70)))
    assert expense.check_credit_notes(right)[0].status == PASS
    assert expense.check_credit_notes(wrong)[0].status == FAIL


def test_kitchen_supplies_fail_but_lab_beaker_does_not():
    kitchen = facts("expense", invoice_document("r.pdf", Invoice(items=[LineItem(description="Kaffee ganze Bohne, 1 kg"), LineItem(description="Wasserkocher")])))
    assert expense.check_hospitality(kitchen)[0].status == FAIL
    lab = facts("expense", invoice_document("r.pdf", Invoice(items=[LineItem(description="Messbecher 500 ml"), LineItem(description="Pipettenspitzen")])))
    assert expense.check_hospitality(lab)[0].status == PASS


# Business trip

def trip(**fields):
    return ("antrag.pdf", "application", "", TripApplication(**fields))


def test_application_after_departure_fails():
    case = facts("business_trip", trip(submission_date="20.10.2026", departure="2026-10-14"))
    assert business_trip.check_submitted_before_start(case)[0].status == FAIL


def test_business_end_before_start_fails():
    case = facts("business_trip", trip(departure="2026-03-09", business_start="2026-03-10", business_end="2026-02-11", return_date="2026-03-11"))
    assert business_trip.check_dates_consistent(case)[0].status == FAIL


def test_open_cost_item_fails():
    case = facts("business_trip", trip(cost_items=[CostItem(description="Hinfahrt", amount=145), CostItem(description="Rückfahrt", amount=None)], total_requested=None))
    assert business_trip.check_costs_complete(case)[0].status == FAIL


def test_foreign_trip_needs_abroad_field():
    assert business_trip.check_foreign_travel(facts("business_trip", trip(destination_country="Frankreich", abroad_field="leer")))[0].status == FAIL
    assert business_trip.check_foreign_travel(facts("business_trip", trip(destination_country="USA", abroad_field="ja")))[0].status == PASS
    assert business_trip.check_foreign_travel(facts("business_trip", trip(destination_country="Deutschland", abroad_field="nein"))) == []


def test_unmentioned_grant_is_double_funding():
    grant = ("email.pdf", "funding_commitment", "", TripDocument(third_party_funding=ThirdPartyFunding(provider="Verein", max_amount=1200, currency="USD", covers=["Flug", "Unterkunft"])))
    assert business_trip.check_third_party_funding(facts("business_trip", trip(mentions_third_party_funding=False, total_requested=1910), grant))[0].status == FAIL
    assert business_trip.check_third_party_funding(facts("business_trip", trip(mentions_third_party_funding=True), grant))[0].status == PASS


def test_private_stay_with_costs_excluded_passes():
    assert business_trip.check_private_stay(facts("business_trip", trip(private_stay_days=6, private_costs_excluded=True)))[0].status == PASS
    assert business_trip.check_private_stay(facts("business_trip", trip(private_stay_days=6)))[0].status == UNCLEAR


def test_form_dates_fill_gaps_left_by_extraction():
    from solver.extract import fill_form_dates
    from solver.schemas import CaseFacts, DocumentFacts, TripApplication

    text = "Datum der Antragstellung: 20.10.2026\nStart: Mittwoch, 14. Oktober 2026, 07:10 Uhr\nEnde Dienstgeschäft: 15.10.2026, 17:00 Uhr"
    extracted = DocumentFacts("antrag.pdf", "application", text, TripApplication(submission_date="2026-10-21"))
    missing = DocumentFacts("antrag.pdf", "application", text)
    for document in (extracted, missing):
        fill_form_dates(CaseFacts("dienstreiseantrag-01", "business_trip", "kassel", [document]))
    assert extracted.data.submission_date == date(2026, 10, 21) and extracted.data.departure == date(2026, 10, 14)
    assert missing.data.submission_date == date(2026, 10, 20) and missing.data.business_end == date(2026, 10, 15)
