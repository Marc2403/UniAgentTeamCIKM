"""Checks for business-trip applications (Dienstreiseantrag)."""

from solver.checks.common import FAIL, PASS, UNCLEAR, Finding, format_amount
from solver.schemas import CaseFacts, TripApplication, TripDocument

DOMESTIC_HOTEL_LIMIT = 80.0
DOMESTIC = {"deutschland", "germany", "de", "brd", "bundesrepublik deutschland"}
# A1 certificates cover EU/EEA states and Switzerland.
A1_COUNTRIES = {
    "belgien", "bulgarien", "dänemark", "estland", "finnland", "frankreich", "griechenland", "irland", "island", "italien",
    "kroatien", "lettland", "liechtenstein", "litauen", "luxemburg", "malta", "niederlande", "norwegen", "österreich",
    "polen", "portugal", "rumänien", "schweden", "schweiz", "slowakei", "slowenien", "spanien", "tschechien", "ungarn", "zypern",
}


def _application(facts: CaseFacts) -> tuple[str | None, TripApplication | None]:
    found = facts.extracted(TripApplication)
    return (found[0][0].name, found[0][1]) if found else (None, None)


def _abroad(application: TripApplication) -> bool | None:
    if not application.destination_country:
        return None
    return application.destination_country.strip().lower() not in DOMESTIC


def check_submitted_before_start(facts: CaseFacts) -> list[Finding]:
    name, application = _application(facts)
    if application is None:
        return [Finding("TRIP_SUBMITTED_BEFORE_START", UNCLEAR, "Kein Antrag ausgewertet.", [], False)]
    start = application.departure or application.business_start
    if application.submission_date and start and application.submission_date > start:
        return [Finding("TRIP_SUBMITTED_BEFORE_START", FAIL, f"Antrag vom {application.submission_date:%d.%m.%Y}, Reisebeginn aber schon am {start:%d.%m.%Y}: keine Genehmigung vor Reiseantritt.", [name])]
    if application.late_submission_note:
        return [Finding("TRIP_SUBMITTED_BEFORE_START", FAIL, "Der Antrag bittet um nachträgliche Genehmigung einer bereits durchgeführten Reise.", [name])]
    if application.submission_date and start:
        return [Finding("TRIP_SUBMITTED_BEFORE_START", PASS, f"Antrag vom {application.submission_date:%d.%m.%Y}, Reisebeginn {start:%d.%m.%Y}.", [name])]
    return [Finding("TRIP_SUBMITTED_BEFORE_START", UNCLEAR, "Antragsdatum oder Reisebeginn fehlt.", [name], False)]


def check_dates_consistent(facts: CaseFacts) -> list[Finding]:
    name, application = _application(facts)
    if application is None:
        return []
    sequence = [
        ("Reisebeginn", application.departure),
        ("Beginn Dienstgeschäft", application.business_start),
        ("Ende Dienstgeschäft", application.business_end),
        ("Reiseende", application.return_date),
    ]
    known = [(label, day) for label, day in sequence if day is not None]
    contradictions = [
        f"{later_label} ({later:%d.%m.%Y}) liegt vor {earlier_label} ({earlier:%d.%m.%Y})"
        for index, (earlier_label, earlier) in enumerate(known)
        for later_label, later in known[index + 1 :]
        if later < earlier
    ]
    if contradictions:
        return [Finding("TRIP_DATES_CONSISTENT", FAIL, "Widersprüchliche Reisedaten: " + "; ".join(contradictions) + ".", [name])]
    if len(known) < 2:
        return [Finding("TRIP_DATES_CONSISTENT", UNCLEAR, "Reisedaten unvollständig.", [name], False)]
    return [Finding("TRIP_DATES_CONSISTENT", PASS, "Reisedaten sind in sich stimmig.", [name])]


def check_costs_complete(facts: CaseFacts) -> list[Finding]:
    name, application = _application(facts)
    if application is None:
        return []
    if not application.cost_items and application.total_requested is None:
        # Nothing about costs was extracted (e.g. dates only from the form fields): not evidence of a gap.
        return [Finding("TRIP_COSTS_COMPLETE", UNCLEAR, "Keine Kostenangaben ausgewertet.", [name], False)]
    open_items = [item.description or "?" for item in application.cost_items if item.amount is None]
    if open_items or application.total_requested is None:
        detail = "Kostenaufstellung unvollständig"
        if open_items:
            detail += f": ohne Betrag {', '.join(open_items)}"
        if application.total_requested is None:
            detail += "; Gesamtsumme steht nicht fest"
        return [Finding("TRIP_COSTS_COMPLETE", FAIL, detail + ".", [name])]
    return [Finding("TRIP_COSTS_COMPLETE", PASS, f"Alle Kostenpositionen beziffert, Summe {format_amount(application.total_requested)}.", [name])]


def check_foreign_travel(facts: CaseFacts) -> list[Finding]:
    name, application = _application(facts)
    if application is None or facts.scope != "kassel":
        return []
    abroad = _abroad(application)
    if abroad is None:
        return [Finding("TRIP_FOREIGN_TRAVEL", UNCLEAR, "Zielland unbekannt.", [name], False)]
    if not abroad:
        return []
    field = (application.abroad_field or "").strip().lower()
    if not field.startswith("ja"):
        return [Finding("TRIP_FOREIGN_TRAVEL", FAIL, f"Reise nach {application.destination_country}, das Pflichtfeld 'Reise ins Ausland' ist aber nicht mit ja ausgefüllt ({application.abroad_field or 'leer'}).", [name])]
    if application.destination_country.strip().lower() in A1_COUNTRIES and not application.a1_certificate:
        return [Finding("TRIP_FOREIGN_TRAVEL", UNCLEAR, f"Reise nach {application.destination_country} ohne Angabe zur A1-Bescheinigung.", [name], False)]
    return [Finding("TRIP_FOREIGN_TRAVEL", PASS, f"Auslandsreise ({application.destination_country}) korrekt angegeben.", [name])]


def check_third_party_funding(facts: CaseFacts) -> list[Finding]:
    name, application = _application(facts)
    grants = [(document.name, data.third_party_funding) for document, data in facts.extracted(TripDocument) if data.third_party_funding is not None]
    if not grants:
        return []
    sources = [grant_name for grant_name, _ in grants]
    if application is None:
        return [Finding("TRIP_THIRD_PARTY_FUNDING", UNCLEAR, "Drittmittelzusage vorhanden, Antrag nicht ausgewertet.", sources, False)]
    funding = grants[0][1]
    described = f"{funding.provider or 'Dritte'} übernimmt {', '.join(funding.covers) or 'Kosten'}" + (f" bis {funding.max_amount:,.0f} {funding.currency or ''}".rstrip() if funding.max_amount else "")
    if application.mentions_third_party_funding:
        return [Finding("TRIP_THIRD_PARTY_FUNDING", PASS, f"{described}; der Antrag berücksichtigt dies.", sources + [name])]
    return [
        Finding(
            "TRIP_THIRD_PARTY_FUNDING",
            FAIL,
            f"{described}, der Antrag beantragt die Kosten dennoch voll ({format_amount(application.total_requested)}) und erwähnt die Förderung nicht (Finanzierung: {application.financing or 'k. A.'}): mögliche Doppelfinanzierung.",
            sources + [name],
            # Whether a third party bindingly covers costs is the model's reading of a letter, not a checked fact.
            False,
        )
    ]


def check_hotel_rate(facts: CaseFacts) -> list[Finding]:
    name, application = _application(facts)
    if application is None or application.nightly_rate is None or facts.scope != "kassel":
        return []
    if _abroad(application):
        return [Finding("TRIP_HOTEL_RATE", UNCLEAR, f"Auslandsübernachtung {format_amount(application.nightly_rate)}/Nacht; Satz der ARV nicht im Korpus.", [name], False)]
    if application.nightly_rate > DOMESTIC_HOTEL_LIMIT:
        return [Finding("TRIP_HOTEL_RATE", FAIL, f"Übernachtung {format_amount(application.nightly_rate)}/Nacht über der Inlandsgrenze von {format_amount(DOMESTIC_HOTEL_LIMIT)}; Notwendigkeit muss begründet sein.", [name], False)]
    return [Finding("TRIP_HOTEL_RATE", PASS, f"Übernachtung {format_amount(application.nightly_rate)}/Nacht innerhalb der Grenze.", [name], False)]


def check_private_stay(facts: CaseFacts) -> list[Finding]:
    name, application = _application(facts)
    if application is None or not application.private_stay_days:
        return []
    if application.private_costs_excluded:
        return [Finding("TRIP_PRIVATE_STAY", PASS, f"{application.private_stay_days} Tage privat; private Mehrkosten sind herausgerechnet und werden selbst getragen.", [name], False)]
    status = FAIL if application.private_costs_excluded is False else UNCLEAR
    return [Finding("TRIP_PRIVATE_STAY", status, f"{application.private_stay_days} Tage privater Aufenthalt; Abgrenzung der privaten Kosten nicht belegt.", [name], False)]


CHECKS = (
    check_submitted_before_start,
    check_dates_consistent,
    check_costs_complete,
    check_foreign_travel,
    check_third_party_funding,
    check_hotel_rate,
    check_private_stay,
)
