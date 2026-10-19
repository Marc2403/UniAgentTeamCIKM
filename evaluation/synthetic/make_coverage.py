"""Render the coverage cases (set C) and the holdout cases (set H) for Task 2 as PDFs.

Everything here is invented. Each case tests one rule of `RULES.md` (or, in family C3, several) and cites its corpus
source; the label is ours and is explained by a decision-trail document outside `inputs/`. Families:
C1 organisers' layouts (`orga_layouts.py`), C2 counterfactual pairs built on spot-check cases (one fact changed),
C3 file complexity (threads, contradictions, partial invoices), C4 cases that look suspicious but are correct,
C5 free text written by another LLM (`--generate-c5`, cached in `datasets/c5-texts.json`).

    python make_coverage.py [--out datasets] [--corpora <dir with hessian-law-de/ ...>]

Writes datasets/{coverage,holdout}-{business-trip,expense-reimbursement,procurement}/ (inputs, decision-trail,
ground-truth.jsonl) and datasets/cases-{coverage,holdout}.jsonl (family, rule, source, document types, label).
"""
import argparse
import json
import shutil
import zlib
from datetime import date
from pathlib import Path

from reportlab import rl_config
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, Spacer

import make_synthetic as ms
import orga_layouts as o
from make_synthetic import DEFAULT_CORPORA, HAND, HERE, P, RECEIPT_MARGINS, RECEIPT_PAGE, link_corpora

SRC_TRIP, SRC_FIN, SRC_PROC, SRC_FRAME, SRC_CATER = ms.SRC_TRIP, ms.SRC_FIN, ms.SRC_PROC, ms.SRC_FRAME, ms.SRC_CATER
SRC_VV_HRKG = "VVHE-VVHE000013868"  # hessian-law-de: Verwaltungsvorschriften zum HRKG

KINDS = {"trip": ("business-trip", "dienstreiseantrag"), "exp": ("expense-reimbursement", "auslagenerstattung"),
         "proc": ("procurement", "beschaffungsantrag")}
CASES = []
OUT = HERE / "datasets"
C5_TEXTS = {}

WEEKDAYS = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
MONTHS = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November",
          "Dezember"]
OWA_KASSEL = "https://outlook.office.example/mail/id/AAQk"
OWA_WERN = "https://owa.uni-wernstadt.de/owa/#path=/mail/inbox"


def e(x):
    """Amount in the organisers' notation (HTML entity for the euro sign)."""
    return ms.eur(x, "&#8364;")


def de(day):
    return f"{day:%d.%m.%Y}"


def long_de(day, time=None):
    text = f"{WEEKDAYS[day.weekday()]}, {day.day}. {MONTHS[day.month - 1]} {day.year}"
    return f"{text}, {time} Uhr" if time else text


def changed_de(day):
    return f"{day.day}. {MONTHS[day.month - 1]} {day.year}"


def odd_font(word):
    """A word the pseudonymiser replaced, set in another font."""
    return f'<font name="Times-Roman">{word}</font>'


REDACTED = '<font backColor="black" color="black">' + "&#160;" * 18 + "</font>"  # blacked-out signature, no text


def ref(c, digits):
    """A reference number that is stable across runs (str hash is salted per process)."""
    return f"{zlib.crc32(c.id.encode()) % 10 ** digits:0{digits}d}"


class Case:
    def __init__(self, set_name, kind, number, label, family, rule, source, pattern, why, *, who, mailbox,
                 uncertain=False):
        dataset_suffix, prefix = KINDS[kind]
        self.dataset = f"{set_name}-{dataset_suffix}"
        self.id = f"{prefix}-{set_name[0]}{number}"
        self.kind, self.label, self.who, self.mailbox = kind, label, who, mailbox
        self.inputs = OUT / self.dataset / "inputs" / self.id
        self.trail_dir = OUT / self.dataset / "decision-trail" / self.id
        self.doc_types = []
        self.record = {"dataset": self.dataset, "antrag": self.id, "label": label, "family": family, "rule": rule,
                       "source_doc_id": source, "pattern": pattern, "reason": why, "uncertain": uncertain,
                       "doc_types": self.doc_types}
        CASES.append(self)

    def path(self, name, doc_type):
        self.doc_types.append(doc_type)
        path = self.inputs / name
        path.parent.mkdir(parents=True, exist_ok=True)
        return str(path)

    def write(self, name, doc_type, *stories, **layout):
        ms.write(Path(self.path(name, doc_type)), *stories, **layout)

    def trail(self, name, *, subject, sender, sent, body, cc=None, kassel=True):
        """The decision document: e-mail of the approving office to the applicant."""
        self.trail_dir.mkdir(parents=True, exist_ok=True)
        o.email_pdf(str(self.trail_dir / name), mailbox=self.mailbox, url=(OWA_KASSEL + "T") if kassel else OWA_WERN,
                    subject=subject, sender=sender, sent=sent, to=f"{self.who} &lt;{self.mailbox}&gt;", cc=cc, body=body)


def trip_trail(c, reisenummer, sent, why, cc=None):
    ok = c.label == "angenommen"
    if ok:
        body = ["Guten Tag,", f"Ihr Antrag auf Genehmigung einer Dienstreise (Reisenummer {reisenummer}) wurde genehmigt.",
                f"Anmerkung der genehmigenden Instanz: {why}",
                "Die Reisekostenabrechnung ist innerhalb der Ausschlussfrist von sechs Monaten nach Reiseende "
                "einzureichen.", "Mit freundlichen Grüßen<br/>ESS-Reisemanagement<br/>Universität Kassel &#183; "
                                 "Abteilung Personal und Organisation"]
        c.trail("genehmigt.pdf", subject=f"[Extern] Ihr Dienstreiseantrag {reisenummer} wurde genehmigt",
                sender="ESS-Reisemanagement, Universität Kassel &lt;noreply-ess@uni-kassel.de&gt;", sent=sent, body=body,
                cc=cc)
    else:
        body = ["Guten Tag,", f"vielen Dank für Ihren Antrag (Reisenummer {reisenummer}). {why}",
                "Der Antrag kann in der vorliegenden Form nicht genehmigt werden.",
                "Mit freundlichen Grüßen<br/>i. A. Corinna Delfs<br/>Abteilung Personal und Organisation &#183; "
                "Reisekostenstelle"]
        c.trail("email-rueckfrage-reisekostenstelle.pdf",
                subject=f"[Extern] Ihr Dienstreiseantrag {reisenummer} &#8211; Rückfrage",
                sender="Reisekostenstelle, Universität Kassel &lt;dienstreisegenehmigung@uni-kassel.de&gt;", sent=sent,
                body=body, cc=cc)


def exp_trail(c, sent, why, kassel=False):
    ok = c.label == "angenommen"
    office = "Finanzbuchhaltung, Universität Kassel" if kassel else "Finanzbuchhaltung, Universität Wernstadt"
    body = ["Guten Tag,", why, "Die Erstattung wird angewiesen." if ok else
            "Eine Erstattung ist in dieser Form nicht möglich.", "Mit freundlichen Grüßen<br/>Finanzbuchhaltung"]
    c.trail("erstattung-angewiesen.pdf" if ok else "email-rueckfrage-finanzbuchhaltung.pdf",
            subject="Ihre Abrechnung privat verauslagter Kosten" + ("" if ok else " &#8211; Rückfrage"),
            sender=f"{office} &lt;kostenerstattung@uni-{'kassel' if kassel else 'wernstadt'}.de&gt;", sent=sent,
            body=body, kassel=kassel)


def proc_trail(c, sent, why, kassel=False):
    ok = c.label == "angenommen"
    body = ["Guten Tag,", why, "Die Bestellung wird ausgelöst." if ok else
            "Wir können die Bestellung in dieser Form nicht auslösen.", "Mit freundlichen Grüßen<br/>Zentrale Beschaffung"]
    c.trail("bestellfreigabe.pdf" if ok else "email-rueckfrage-beschaffung.pdf",
            subject="Ihre Bestellanforderung" + (" &#8211; Freigabe" if ok else " &#8211; Rückfrage"),
            sender="Zentrale Beschaffung &lt;beschaffung@uni-wernstadt.de&gt;", sent=sent, body=body, kassel=kassel)


def costs(rows):
    """(position, qty, amount) -> organiser cost rows and the total."""
    return [(pos, str(qty), e(amount)) for pos, qty, amount in rows], sum(amount for _, _, amount in rows)


def orga_trip(c, *, rnr, pnr, fg, ziel, ausland, anlass, grund, verkehr, antrag, start, ende, bstart, bend, kosten,
              finanzierung, begruendung, privat="keiner", arbeitstage="", a1=None, hinweis=None, geaendert=None,
              status="Antrag eingereicht", genehmigt="---", name=None):
    rows, total = costs(kosten)
    verlauf = [("Start:", long_de(*start) + " (Abreise vom Wohnort)"), ("Ende:", long_de(*ende) + " (Rückkehr zum Wohnort)"),
               ("Beginn Dienstgeschäft:", f"{de(bstart[0])}, {bstart[1]} Uhr"),
               ("Ende Dienstgeschäft:", f"{de(bend[0])}, {bend[1]} Uhr"), ("priv. Aufenthalt:", privat),
               ("Arbeitstage:", arbeitstage)]
    if a1:
        verlauf.append(("A1-Bescheinigung:", a1))
    o.antrag_pdf(
        c.path("antrag-dienstreisegenehmigung.pdf", "trip_form"), reisenummer=rnr, name=name or c.who, fachgebiet=fg,
        personalnummer=pnr, status=status, geaendert_am=changed_de(geaendert or antrag), genehmigt_von=genehmigt,
        allgemein=[("Reiseziel:", ziel), ("Anlass:", anlass), ("Grund der Reise:", grund),
                   ("Reise ins Ausland:", "[X] ja &#160;&#160; [ ] nein" if ausland else "[ ] ja &#160;&#160; [X] nein"),
                   ("Verkehrsmittel:", verkehr), ("Datum der Antragstellung:", de(antrag))],
        verlauf=verlauf, kosten=rows, kosten_total=("Summe (Schätzung)", e(total)), finanzierung=finanzierung,
        begruendung=begruendung, hinweis=hinweis, antragsdatum=de(antrag))
    return total


def mail(c, name, *, subject, sender, sent, body, cc=None, to=None, doc_type="email", kassel=True, mailbox=None):
    o.email_pdf(c.path(name, doc_type), mailbox=mailbox or c.mailbox, url=(OWA_KASSEL + "E") if kassel else OWA_WERN,
                subject=subject, sender=sender, sent=sent, to=to or f"{c.who} &lt;{c.mailbox}&gt;", cc=cc, body=body)


def vendor_doc(c, name, doc_type, **kw):
    o.invoice_pdf(c.path(name, doc_type), **kw)


def rail(c, *, out, back, price_each, booked, name="bahn-buchung.pdf", note=None):
    """Rail booking (reserved, paid on departure) for an outward and a return journey."""
    net = round(price_each / 1.07, 2)
    vendor_doc(c, name, "booking", vendor="Nordbahn Fernverkehr AG", vendor_addr=["Gleisfeld 4", "60329 Frankfurt am Main"],
               recipient=[c.who, "c/o Universität Kassel", "Fachbereich 16", "34121 Kassel"],
               refs=[("Auftragsnummer:", f"0045{ref(c, 8)}"), ("Buchungsdatum:", de(booked)),
                     ("Status:", "reserviert, zahlbar bei Abreise")],
               heading="Buchungsbestätigung", intro="Reservierung, noch keine Rechnung",
               items=[[out, "1", "7 % (D)", e(net), e(price_each)], [back, "1", "7 % (D)", e(net), e(price_each)]],
               sums=[("Summe (brutto)", e(2 * price_each))],
               notes=[note or "Dieses Dokument berechtigt nicht zur Fahrt."], closing="Mit freundlichen Grüßen")


def hotel(c, *, vendor, addr, nights, rate, period, booked, recipient=None, name="hotel-reservierung.pdf", notes=()):
    vendor_doc(c, name, "booking", vendor=vendor, vendor_addr=addr,
               recipient=recipient or ["Universität Kassel", "Fachbereich 16", f"Gast: {c.who}", "Wilhelmshöher Allee 71-73",
                                       "34121 Kassel"],
               refs=[("Reservierungsnr.:", f"R-{ref(c, 5)}"), ("Datum:", de(booked))],
               heading="Reservierungsbestätigung",
               items=[[f"Einzelzimmer, {period}", str(nights), "7 % (D)", e(round(rate / 1.07, 2)), e(rate)]],
               sums=[("Summe (brutto)", e(nights * rate))],
               notes=list(notes) or ["Rechnungsanschrift: Universität Kassel. Kostenfreie Stornierung bis 18 Uhr am Anreisetag."],
               closing="Wir freuen uns auf Ihren Besuch.")


# =========================================================================== #
#                     C1  organisers' layouts, business trip                   #
# =========================================================================== #

def c1_trip():
    # 101 abgelehnt: destination on the list of excluded countries
    c = Case("coverage", "trip", 101, "abgelehnt", "C1", "T05", SRC_TRIP, "Workshop in Kyjiw (Ukraine), sonst vollständig",
             "Dienstreisen in die Ukraine werden laut Dienstreisemanagement bis auf Weiteres nicht genehmigt.",
             who="Dr. Oleksandr Brenninkmeyer", mailbox="o.brenninkmeyer@uni-kassel.de")
    orga_trip(c, rnr="3381040112", pnr="052214", fg="Fachgebiet Energiemanagement", ziel="Kyjiw, UKRAINE", ausland=True,
              anlass="Workshop &#8222;Resilient Power Grids&#8220; der Polytechnischen Universität Kyjiw",
              grund="Eingeladener Vortrag und Vorbereitung eines gemeinsamen Horizon-Antrags", verkehr="Flug (Economy), Bahn",
              antrag=date(2027, 3, 1), start=(date(2027, 5, 10), "05:50"), ende=(date(2027, 5, 13), "22:40"),
              bstart=(date(2027, 5, 11), "09:00"), bend=(date(2027, 5, 12), "17:30"), arbeitstage="4",
              a1="nicht erforderlich (kein EU/EWR-Staat)",
              kosten=[("Flug Frankfurt&#8211;Rzeszów, Hin- und Rückflug", 1, 312.00), ("Bahn Przemysl&#8211;Kyjiw, Hin- und Rückfahrt", 1, 96.00),
                      ("Unterkunft, 3 Nächte (Satz laut ARV)", 3, 294.00)],
              finanzierung="Fachgebietsbudget Energiemanagement, Kostenstelle 4652-01",
              begruendung="Vortrag auf Einladung der Polytechnischen Universität Kyjiw; Abstimmung des gemeinsamen Antrags "
                          "im Cluster 5 von Horizon Europe. Die Einladung liegt bei.")
    mail(c, "einladung-workshop.pdf", subject="Invitation &#8211; Resilient Power Grids Workshop, Kyiv, 11&#8211;12 May 2027",
         sender="Prof. Iryna Kovalchuk &lt;i.kovalchuk@kpi-energy.example&gt;", sent="Mi 03.02.2027 11:20",
         body=["Dear Dr. Brenninkmeyer,", "we would be delighted to welcome you as an invited speaker at our workshop "
               "&#8222;Resilient Power Grids&#8220; on 11&#8211;12 May 2027 at our campus in Kyiv.",
               "Accommodation can be arranged at the university guest house. Unfortunately we cannot cover travel costs.",
               "With kind regards,<br/>Iryna Kovalchuk"])
    vendor_doc(c, "flug-angebot.pdf", "offer", vendor="Reisebüro am Königsplatz", vendor_addr=["Königsplatz 37", "34117 Kassel"],
               recipient=["Universität Kassel", "z. Hd. Dr. Oleksandr Brenninkmeyer", "34121 Kassel"],
               refs=[("Angebotsnummer:", "RK-2027-0388"), ("Datum:", "26.02.2027")], heading="Flugangebot",
               items=[["10.05.2027 FRA 07:05 &#8211; RZE 09:10, Economy", "1", "&#8212;", e(156), e(156)],
                      ["13.05.2027 RZE 19:40 &#8211; FRA 21:50, Economy", "1", "&#8212;", e(156), e(156)]],
               sums=[("Gesamt", e(312))], notes=["Preisvergleich: Verbindung über Warschau 344,00 &#8364;; dieses Angebot "
                                                 "ist das günstigste."], closing="Mit freundlichen Grüßen")
    trip_trail(c, "3381040112", "Fr 05.03.2027 09:12", "Dienstreisen in die Ukraine werden nach dem Hinweis auf der Seite "
               "Dienstreisemanagement bis auf Weiteres nicht genehmigt. Das gilt unabhängig von der Vollständigkeit der Unterlagen.")

    # 102 angenommen: foreign trip to a country that is not excluded
    c = Case("coverage", "trip", 102, "angenommen", "C1", "T05", SRC_TRIP,
             "Tagung in Amman (Jordanien), Land nicht auf der Ausschlussliste, vollständig",
             "Jordanien steht nicht auf der Liste der ausgeschlossenen Länder; Antrag rechtzeitig, Flug mit Preisvergleich.",
             who="Dr. Hanna Lüdeking-Saleh", mailbox="h.luedeking@uni-kassel.de")
    orga_trip(c, rnr="3381040135", pnr="047730", fg="Fachgebiet Siedlungswasserwirtschaft", ziel="Amman, JORDANIEN",
              ausland=True, anlass="International Water Reuse Conference 2027",
              grund="Vortrag des angenommenen Beitrags &#8222;Greywater Reuse in Arid Cities&#8220;",
              verkehr="Flug (Economy)", antrag=date(2027, 2, 15), start=(date(2027, 4, 19), "06:10"),
              ende=(date(2027, 4, 22), "23:30"), bstart=(date(2027, 4, 20), "08:30"), bend=(date(2027, 4, 21), "17:00"),
              arbeitstage="4", a1="nicht erforderlich (kein EU/EWR-Staat)",
              kosten=[("Flug Frankfurt&#8211;Amman, Hin- und Rückflug, Economy", 1, 418.00),
                      ("Konferenzgebühr", 1, 350.00), ("Unterkunft, 3 Nächte (Satz laut ARV)", 3, 303.00)],
              finanzierung="Drittmittelprojekt WaterCycle-MENA, Kostenstelle 6640-22 (Reisemittel)",
              begruendung="Vorstellung der Projektergebnisse; Annahmebestätigung und Programm liegen bei.")
    mail(c, "annahme-beitrag.pdf", subject="IWRC 2027 &#8211; Acceptance of your contribution #57",
         sender="IWRC 2027 Programme Committee &lt;programme@iwrc2027.example&gt;", sent="Mo 25.01.2027 18:02",
         body=["Dear Dr. Lüdeking-Saleh,", "your paper #57 &#8222;Greywater Reuse in Arid Cities&#8220; has been accepted "
               "for oral presentation at the International Water Reuse Conference, Amman, 20&#8211;21 April 2027.",
               "Your talk is scheduled on 20 April, 14:30. Registration fee: 350 EUR.", "Best regards,<br/>Programme Committee"])
    vendor_doc(c, "flug-preisvergleich.pdf", "price_comparison", vendor="Reisebüro Campus Kassel GmbH",
               vendor_addr=["Königsplatz 47", "34117 Kassel"], recipient=["Universität Kassel", "z. Hd. Dr. Hanna Lüdeking-Saleh",
                                                                          "34121 Kassel"],
               refs=[("Angebotsnummer:", "RCK-2027-0215"), ("Datum:", "12.02.2027")], heading="Flugangebot mit Preisvergleich",
               items=[["FRA&#8211;AMM&#8211;FRA direkt, Economy (gewählt)", "1", "&#8212;", e(418), e(418)],
                      ["FRA&#8211;IST&#8211;AMM, Umstieg, Economy", "1", "&#8212;", e(455), e(455)]],
               sums=[("Gewähltes Angebot", e(418))], closing="Mit freundlichen Grüßen")
    trip_trail(c, "3381040135", "Mo 22.02.2027 08:05", "Reiseziel Jordanien ohne Reisebeschränkung; Preisvergleich liegt vor.")

    # 103 abgelehnt: domestic hotel above 80 EUR, no reason
    c = Case("coverage", "trip", 103, "abgelehnt", "C1", "T06", SRC_TRIP, "Inland, Hotel 112 €/Nacht ohne Begründung",
             "Übernachtung 112,00 € je Nacht über der Inlandsgrenze von 80,00 €; die Notwendigkeit ist im Antrag nicht begründet.",
             who="Jannik Szymanski-Oberle", mailbox="j.szymanski@uni-kassel.de")
    orga_trip(c, rnr="3381040177", pnr="058821", fg="Fachgebiet Mensch-Maschine-Systemtechnik", ziel="Stuttgart",
              ausland=False, anlass="Fachtagung Usability Engineering 2027", grund="Teilnahme und Posterbeitrag",
              verkehr="Bahn, 2. Klasse", antrag=date(2027, 4, 6), start=(date(2027, 6, 14), "07:15"),
              ende=(date(2027, 6, 16), "19:40"), bstart=(date(2027, 6, 14), "13:00"), bend=(date(2027, 6, 16), "13:00"),
              arbeitstage="3", kosten=[("Tagungsgebühr", 1, 260.00), ("Bahn Kassel&#8211;Stuttgart, Hin- und Rückfahrt", 1, 134.00),
                                        ("Übernachtung Hotel Schlossgarten-Residenz, 2 Nächte à 112,00 &#8364;", 2, 224.00)],
              finanzierung="Fachgebietsbudget, Kostenstelle 4661-02",
              begruendung="Posterbeitrag zur Evaluation adaptiver Assistenzsysteme; Programm liegt bei.")
    hotel(c, vendor="Hotel Schlossgarten-Residenz", addr=["Königstraße 12", "70173 Stuttgart"], nights=2, rate=112.00,
          period="14.06.&#8211;16.06.2027, inkl. Frühstück", booked=date(2027, 4, 5))
    vendor_doc(c, "tagungsprogramm.pdf", "programme", vendor="Fachtagung Usability Engineering 2027",
               vendor_addr=["c/o UE-Forum e.V.", "Nobelstraße 10", "70569 Stuttgart"], recipient=["Programmübersicht"],
               refs=[("Stand:", "01.04.2027")], heading="Programm 14.&#8211;16. Juni 2027",
               intro="Postersession am 15.06.2027, 10:30&#8211;12:00 Uhr; Teilnahmegebühr 260,00 &#8364;.")
    trip_trail(c, "3381040177", "Fr 09.04.2027 10:40", "Die beantragten Übernachtungskosten von 112,00 &#8364; je Nacht "
               "überschreiten die Höchstgrenze von 80,00 &#8364;. Höhere Kosten werden nur erstattet, wenn ihre Notwendigkeit "
               "bei Antragstellung schriftlich begründet ist; eine Begründung fehlt.")

    # 104 angenommen: hotel above 80 EUR with written reason (Ballungsraum, trade fair)
    c = Case("coverage", "trip", 104, "angenommen", "C1", "T06", SRC_VV_HRKG,
             "Hotel 109 €/Nacht in München zur Messezeit, Notwendigkeit im Antrag begründet, Recherche beigefügt",
             "Begründung bei Antragstellung (Messeaufschlag, Ballungsraum) und Recherche liegen vor; Satz damit erstattungsfähig.",
             who="Dr. Clara Wendelken", mailbox="c.wendelken@uni-kassel.de")
    orga_trip(c, rnr="3381040190", pnr="043318", fg="Fachgebiet Technische Informatik", ziel="München", ausland=False,
              anlass="electronica 2027, Fachmesse und Embedded Forum", grund="Vortrag im Embedded Forum",
              verkehr="Bahn, 2. Klasse", antrag=date(2027, 9, 6), start=(date(2027, 11, 9), "06:40"),
              ende=(date(2027, 11, 11), "20:10"), bstart=(date(2027, 11, 9), "12:00"), bend=(date(2027, 11, 11), "14:00"),
              arbeitstage="3", kosten=[("Bahn Kassel&#8211;München, Hin- und Rückfahrt", 1, 162.00),
                                        ("Übernachtung, 2 Nächte à 109,00 &#8364;", 2, 218.00)],
              finanzierung="Fachgebietsbudget, Kostenstelle 4615-01",
              begruendung="Vortrag &#8222;Energieeffiziente Firmware-Updates&#8220; im Embedded Forum der Messe.",
              hinweis="Begründung Übernachtungskosten: Während der Messe liegen alle Hotels im Stadtgebiet München und im "
                      "Umkreis von 25 km über 80,00 &#8364;; das gebuchte Zimmer ist das günstigste verfügbare (Ausdruck der "
                      "Recherche vom 05.09.2027 liegt bei).")
    vendor_doc(c, "unterkunftsrecherche.pdf", "price_comparison", vendor="hotelvergleich.example",
               vendor_addr=["Ausdruck 05.09.2027, 21:14"], recipient=["Suche: München + 25 km, 09.&#8211;11.11.2027, 1 Person"],
               refs=[("Sortierung:", "Preis aufsteigend")], heading="Suchergebnis",
               items=[["Pension Laim (ausgebucht)", "&#8212;", "&#8212;", e(74), e(79)],
                      ["Hotel Garching Nord (verfügbar)", "&#8212;", "&#8212;", e(101.87), e(109)],
                      ["Hotel Messestadt Ost (verfügbar)", "&#8212;", "&#8212;", e(130.84), e(140)]],
               notes=["Hinweis des Portals: Wegen einer Messe ist die Verfügbarkeit stark eingeschränkt."])
    hotel(c, vendor="Hotel Garching Nord", addr=["Schleißheimer Straße 4", "85748 Garching"], nights=2, rate=109.00,
          period="09.11.&#8211;11.11.2027", booked=date(2027, 9, 5))
    trip_trail(c, "3381040190", "Mi 08.09.2027 07:58", "Die Übernachtungskosten über 80,00 &#8364; sind mit dem Messeaufschlag "
               "nachvollziehbar begründet und die Recherche liegt bei.")

    # 105 abgelehnt: fee for the talk -> side activity
    c = Case("coverage", "trip", 105, "abgelehnt", "C1", "T10", SRC_TRIP,
             "Eingeladener Vortrag, Einladung nennt Honorar 500 €, Reisekosten beantragt",
             "Das Honorar von 500 EUR deutet auf eine Nebentätigkeit; eine Dienstreisegenehmigung ist dann grundsätzlich nicht möglich.",
             who="Prof. Dr. Benedikt Asamoah-Fries", mailbox="b.asamoah@uni-kassel.de")
    orga_trip(c, rnr="3381040211", pnr="031076", fg="Fachgebiet Regelungstechnik", ziel="Hannover", ausland=False,
              anlass="Industrieforum Antriebstechnik 2027", grund="Eingeladener Fachvortrag", verkehr="Bahn, 2. Klasse",
              antrag=date(2027, 3, 22), start=(date(2027, 5, 6), "07:30"), ende=(date(2027, 5, 6), "19:15"),
              bstart=(date(2027, 5, 6), "10:00"), bend=(date(2027, 5, 6), "16:00"), arbeitstage="1",
              kosten=[("Bahn Kassel&#8211;Hannover, Hin- und Rückfahrt", 1, 88.00), ("Tagegeld (Abwesenheit &gt; 8 Std.)", 1, 14.00)],
              finanzierung="Professurbudget, Kostenstelle 4610-00", begruendung="Transfervortrag; die Einladung liegt bei.")
    mail(c, "einladung-industrieforum.pdf", subject="Ihr Vortrag beim Industrieforum Antriebstechnik am 6. Mai 2027",
         sender="Forum Antriebstechnik Niedersachsen e.V. &lt;forum@antriebstechnik-nds.example&gt;", sent="Do 11.03.2027 14:31",
         body=["Sehr geehrter Herr Prof. Asamoah-Fries,", "herzlichen Dank für Ihre Zusage. Ihr Vortrag "
               "&#8222;Prädiktive Regelung elektrischer Antriebe&#8220; ist für 11:15 Uhr eingeplant (40 Minuten).",
               "Für den Vortrag zahlen wir Ihnen wie besprochen ein Honorar von 500,00 EUR; bitte senden Sie uns nach der "
               "Veranstaltung Ihre Honorarrechnung. Reisekosten erstatten wir nicht.",
               "Mit freundlichen Grüßen<br/>Geschäftsstelle"])
    trip_trail(c, "3381040211", "Mo 29.03.2027 11:02", "Laut Einladung erhalten Sie für den Vortrag ein Honorar von 500,00 EUR. "
               "Ein Honorar deutet auf eine Nebentätigkeit und damit auf eine privat veranlasste Reise hin; eine "
               "Dienstreisegenehmigung und Reisekostenabrechnung ist dann grundsätzlich nicht möglich.")

    # 106 angenommen: invited talk, invitation explicitly without fee
    c = Case("coverage", "trip", 106, "angenommen", "C1", "T10", SRC_TRIP,
             "Eingeladener Vortrag an einer Universität, ausdrücklich ohne Honorar", "Kein Honorar, dienstliches Interesse belegt.",
             who="Dr. Mirjam Okonjo-Hartl", mailbox="m.okonjo@uni-kassel.de")
    orga_trip(c, rnr="3381040236", pnr="049917", fg="Fachgebiet Datenbanken", ziel="Jena", ausland=False,
              anlass="Kolloquium des Instituts für Informatik der Universität Jena", grund="Eingeladener Kolloquiumsvortrag",
              verkehr="Bahn, 2. Klasse", antrag=date(2027, 4, 12), start=(date(2027, 5, 19), "08:05"),
              ende=(date(2027, 5, 19), "20:30"), bstart=(date(2027, 5, 19), "11:00"), bend=(date(2027, 5, 19), "17:00"),
              arbeitstage="1", kosten=[("Bahn Kassel&#8211;Jena, Hin- und Rückfahrt", 1, 72.00), ("Tagegeld", 1, 14.00)],
              finanzierung="Fachgebietsbudget, Kostenstelle 4622-01",
              begruendung="Vortrag und Gespräche über eine gemeinsame Doktorandenbetreuung.")
    mail(c, "einladung-kolloquium.pdf", subject="Einladung Kolloquium Informatik, 19. Mai 2027",
         sender="Prof. Dr. Gernot Halbritter &lt;g.halbritter@inf.uni-jena.example&gt;", sent="Fr 02.04.2027 09:44",
         body=["Liebe Frau Okonjo-Hartl,", "wir laden Sie herzlich ein, am 19. Mai 2027 um 14:15 Uhr in unserem Kolloquium "
               "über Ihre Arbeiten zu Anfrageoptimierung zu sprechen.", "Ein Honorar ist nicht vorgesehen; die Reisekosten "
               "trägt nach unserer Absprache Ihre Dienststelle.", "Viele Grüße<br/>Gernot Halbritter"])
    trip_trail(c, "3381040236", "Do 15.04.2027 08:20", "Dienstliches Interesse durch die Einladung belegt; kein Honorar.")

    # 107 abgelehnt: online-only conference submitted as a business trip
    c = Case("coverage", "trip", 107, "abgelehnt", "C1", "T11", SRC_TRIP,
             "Ausschließlich virtuelle Tagung als Dienstreise mit Tagegeld beantragt",
             "Online durchgeführte Tagungen sind keine Dienstreisen; die Gebühr ist über das Formular Privat verauslagte Kosten geltend zu machen.",
             who="Leonie Aydemir-Strack", mailbox="l.aydemir@uni-kassel.de")
    orga_trip(c, rnr="3381040259", pnr="060142", fg="Fachgebiet Wirtschaftsinformatik", ziel="online (Zoom), Dienstort Kassel",
              ausland=False, anlass="Virtual Workshop on Process Mining 2027", grund="Teilnahme und Kurzvortrag",
              verkehr="keins", antrag=date(2027, 2, 8), start=(date(2027, 3, 17), "08:30"), ende=(date(2027, 3, 18), "17:30"),
              bstart=(date(2027, 3, 17), "09:00"), bend=(date(2027, 3, 18), "17:00"), arbeitstage="2",
              kosten=[("Teilnahmegebühr", 1, 120.00), ("Tagegeld 2 Tage", 2, 28.00)],
              finanzierung="Fachgebietsbudget, Kostenstelle 4691-03",
              begruendung="Kurzvortrag im virtuellen Workshop; die Zugangsdaten liegen bei.")
    mail(c, "zugangsdaten-workshop.pdf", subject="VWPM 2027 &#8211; your access link",
         sender="VWPM Organisers &lt;contact@vwpm2027.example&gt;", sent="Mo 01.02.2027 10:00",
         body=["Dear participant,", "the Virtual Workshop on Process Mining takes place <b>exclusively online</b> on 17&#8211;18 "
               "March 2027. Your personal Zoom link will be sent the day before.", "Registration fee: 120 EUR.",
               "Kind regards,<br/>The organisers"])
    trip_trail(c, "3381040259", "Do 11.02.2027 13:15", "Der Workshop findet ausschließlich online statt. Online durchgeführte "
               "Tagungen sind keine Dienstreisen; die Teilnahmegebühr ist über das Formular &#8222;Privat verauslagte "
               "Kosten&#8220; bei der Finanzabteilung geltend zu machen, Tagegeld entsteht nicht.")

    # 108 angenommen: hybrid conference attended on site
    c = Case("coverage", "trip", 108, "angenommen", "C1", "T11", SRC_TRIP,
             "Hybride Tagung, Teilnahme vor Ort in Bremen mit Vortrag", "Teilnahme vor Ort; 'hybrid' macht sie nicht zur Online-Tagung.",
             who="Dr. Tamino Vollrath", mailbox="t.vollrath@uni-kassel.de")
    orga_trip(c, rnr="3381040273", pnr="044401", fg="Fachgebiet Mikrosystemtechnik", ziel="Bremen", ausland=False,
              anlass="MikroSystemTage 2027 (hybrid)", grund="Vortrag vor Ort", verkehr="Bahn, 2. Klasse",
              antrag=date(2027, 7, 1), start=(date(2027, 9, 21), "06:55"), ende=(date(2027, 9, 22), "21:10"),
              bstart=(date(2027, 9, 21), "11:00"), bend=(date(2027, 9, 22), "16:30"), arbeitstage="2",
              kosten=[("Tagungsgebühr (Präsenz)", 1, 340.00), ("Bahn Kassel&#8211;Bremen, Hin- und Rückfahrt", 1, 104.00),
                      ("Übernachtung, 1 Nacht", 1, 79.00)],
              finanzierung="Fachgebietsbudget, Kostenstelle 4633-02", begruendung="Vortrag im Track Sensorik, Programm liegt bei.")
    vendor_doc(c, "programm-mikrosystemtage.pdf", "programme", vendor="MikroSystemTage 2027",
               vendor_addr=["Congress Centrum Bremen", "Findorffstraße 101", "28215 Bremen"], recipient=["Programmauszug"],
               refs=[("Stand:", "20.06.2027")], heading="Programm 21.&#8211;22. September 2027",
               intro="Die Tagung findet hybrid statt: vor Ort im Congress Centrum Bremen und mit Livestream. Vortragende "
                     "präsentieren vor Ort.",
               items=[["Session S4 Sensorik, 21.09.2027, 15:20 Uhr: Vollrath, &#8222;MEMS-Gassensoren im Feldtest&#8220;", "", "", "", ""]])
    trip_trail(c, "3381040273", "Mo 05.07.2027 08:40", "Vortrag vor Ort in Bremen; die hybride Durchführung ändert daran nichts.")

    # 109 abgelehnt: flight abroad without price comparison
    c = Case("coverage", "trip", 109, "abgelehnt", "C1", "T13", SRC_TRIP, "Flugreise nach Lissabon ohne Preisvergleich",
             "Bei Flugreisen ist dem Antrag ein Preisvergleich beizufügen; es liegt nur ein einzelnes Flugticket vor.",
             who="Fenja Albrecht-Nwosu", mailbox="f.albrecht@uni-kassel.de")
    orga_trip(c, rnr="3381040295", pnr="062250", fg="Fachgebiet Kommunikationstechnik", ziel="Lissabon, PORTUGAL",
              ausland=True, anlass="European Conference on Networks 2027", grund="Vortrag des angenommenen Beitrags",
              verkehr="Flug (Economy)", antrag=date(2027, 3, 29), start=(date(2027, 6, 7), "05:30"),
              ende=(date(2027, 6, 10), "23:15"), bstart=(date(2027, 6, 8), "09:00"), bend=(date(2027, 6, 9), "18:00"),
              arbeitstage="4", a1="beantragt am 29.03.2027",
              kosten=[("Flug Frankfurt&#8211;Lissabon, Hin- und Rückflug, Tarif Flex", 1, 486.00), ("Konferenzgebühr", 1, 420.00),
                      ("Unterkunft, 3 Nächte", 3, 285.00)],
              finanzierung="Drittmittelprojekt 6612-04", begruendung="Vortrag; Annahmebestätigung liegt bei.")
    vendor_doc(c, "flugbuchung.pdf", "booking", vendor="Nordluft Airlines", vendor_addr=["Flughafenring 2", "60549 Frankfurt"],
               recipient=["Fenja Albrecht-Nwosu", "Universität Kassel"], refs=[("Buchungscode:", "NLX4QT"), ("Datum:", "27.03.2027")],
               heading="Reservierung", items=[["FRA&#8211;LIS 07.06.2027 / LIS&#8211;FRA 10.06.2027, Economy Flex", "1", "&#8212;", e(486), e(486)]],
               sums=[("Gesamt", e(486))], notes=["Reservierung 72 Stunden gültig."])
    trip_trail(c, "3381040295", "Do 01.04.2027 10:22", "Bei Flugreisen ist dem Dienstreiseantrag ein Preisvergleich beizufügen. "
               "Beigefügt ist nur die Reservierung eines Flex-Tarifs, ein Vergleich mit anderen Verbindungen oder Tarifen fehlt.")

    # 110 angenommen: flight abroad with price comparison
    c = Case("coverage", "trip", 110, "angenommen", "C1", "T13", SRC_TRIP, "Flugreise nach Porto mit Preisvergleich des Reisebüros",
             "Preisvergleich liegt vor, günstigste Verbindung gewählt.", who="Dr. Ruben Kolbeck", mailbox="r.kolbeck@uni-kassel.de")
    orga_trip(c, rnr="3381040318", pnr="039964", fg="Fachgebiet Produktionsorganisation", ziel="Porto, PORTUGAL", ausland=True,
              anlass="International Conference on Production Research 2027", grund="Vortrag", verkehr="Flug (Economy)",
              antrag=date(2027, 4, 26), start=(date(2027, 7, 12), "06:00"), ende=(date(2027, 7, 15), "22:45"),
              bstart=(date(2027, 7, 13), "09:00"), bend=(date(2027, 7, 14), "17:30"), arbeitstage="4",
              a1="beantragt am 26.04.2027 (Vorlauf &gt; 8 Wochen)",
              kosten=[("Flug Frankfurt&#8211;Porto, Hin- und Rückflug, Economy", 1, 298.00), ("Konferenzgebühr", 1, 390.00),
                      ("Unterkunft, 3 Nächte", 3, 270.00)],
              finanzierung="Fachgebietsbudget, Kostenstelle 4670-01", begruendung="Vortrag; Annahmebestätigung liegt bei.")
    vendor_doc(c, "flugangebot-preisvergleich.pdf", "price_comparison", vendor="Reisebüro Campus Kassel GmbH",
               vendor_addr=["Königsplatz 47", "34117 Kassel"], recipient=["Universität Kassel", "z. Hd. Dr. Ruben Kolbeck", "34121 Kassel"],
               refs=[("Angebotsnummer:", "RCK-2027-0611"), ("Datum:", "23.04.2027")], heading="Flugangebot",
               items=[["FRA&#8211;OPO&#8211;FRA direkt, Economy Classic (empfohlen)", "1", "&#8212;", e(298), e(298)],
                      ["FRA&#8211;LIS&#8211;OPO, Umstieg, Economy", "1", "&#8212;", e(341), e(341)],
                      ["Bahn Kassel&#8211;Porto (2 Tage Reisezeit je Richtung)", "1", "&#8212;", e(612), e(612)]],
               sums=[("Angebot", e(298))], closing="Mit freundlichen Grüßen")
    trip_trail(c, "3381040318", "Fr 30.04.2027 09:01", "Preisvergleich liegt vor; die günstigste Verbindung wurde gewählt.")

    # 111 abgelehnt: domestic flight more expensive than rail, no reason
    c = Case("coverage", "trip", 111, "abgelehnt", "C1", "T14", SRC_TRIP,
             "Inlandsflug Frankfurt–Hamburg teurer als die Bahn, keine dienstlichen Gründe",
             "Inlandsflüge kommen nur in Betracht, wenn die Bahn teurer ist oder besondere dienstliche Gründe in einer Anlage dargelegt sind; beides fehlt.",
             who="Moritz Ebeling-Tran", mailbox="m.ebeling@uni-kassel.de")
    orga_trip(c, rnr="3381040340", pnr="057702", fg="Fachgebiet Fahrzeugsysteme", ziel="Hamburg", ausland=False,
              anlass="Projekttreffen Verbund H2Mobil", grund="Teilnahme am Projekttreffen", verkehr="Flug Frankfurt&#8211;Hamburg",
              antrag=date(2027, 5, 3), start=(date(2027, 6, 2), "06:00"), ende=(date(2027, 6, 2), "21:30"),
              bstart=(date(2027, 6, 2), "10:30"), bend=(date(2027, 6, 2), "16:00"), arbeitstage="1",
              kosten=[("Flug FRA&#8211;HAM&#8211;FRA, Economy", 1, 289.00), ("Bahn Kassel&#8211;Frankfurt Flughafen, Hin- und Rückfahrt", 1, 58.00)],
              finanzierung="Drittmittelprojekt H2Mobil, Kostenstelle 6655-10", begruendung="Projekttreffen; Einladung liegt bei.")
    mail(c, "einladung-projekttreffen.pdf", subject="H2Mobil &#8211; Projekttreffen am 2. Juni 2027 in Hamburg",
         sender="Projektbüro H2Mobil &lt;office@h2mobil.example&gt;", sent="Di 20.04.2027 16:12",
         body=["Liebe Partner,", "unser Projekttreffen findet am 2. Juni 2027 von 10:30 bis 16:00 Uhr im HafenCity-Campus statt.",
               "Viele Grüße<br/>Projektbüro"])
    vendor_doc(c, "verbindungsauskunft.pdf", "price_comparison", vendor="Nordbahn Fernverkehr AG",
               vendor_addr=["Gleisfeld 4", "60329 Frankfurt am Main"], recipient=[c.who], refs=[("Auskunft vom:", "30.04.2027")],
               heading="Verbindungsauskunft", items=[["Kassel-Wilhelmshöhe &#8211; Hamburg Hbf, 06:15&#8211;08:22 Uhr, Hin- und Rückfahrt, Flexpreis", "1", "7 % (D)", e(130.84), e(140)]],
               notes=["Fahrzeit 2:07 Std. je Richtung."])
    trip_trail(c, "3381040340", "Do 06.05.2027 08:55", "Flugkosten kommen im Inland nur in Betracht, wenn bei Benutzung der Bahn "
               "höhere Kosten entstehen oder besondere dienstliche Gründe vorliegen, die in einer Anlage darzulegen sind. Die "
               "beigefügte Auskunft zeigt eine Bahnverbindung für 140,00 &#8364;, der Flug kostet 289,00 &#8364; zuzüglich Zubringer.")

    # 112 angenommen: domestic flight cheaper than rail, comparison attached
    c = Case("coverage", "trip", 112, "angenommen", "C1", "T14", SRC_TRIP,
             "Inlandsflug Paderborn–München günstiger als die Bahn, Vergleich beigefügt", "Flug günstiger als die Bahn, Vergleich liegt bei.",
             who="Dr. Selma Brüggemann", mailbox="s.brueggemann@uni-kassel.de")
    orga_trip(c, rnr="3381040362", pnr="046690", fg="Fachgebiet Elektrische Energieversorgung", ziel="München", ausland=False,
              anlass="Gutachtersitzung DFG-Schwerpunktprogramm", grund="Teilnahme als Gutachterin", verkehr="Flug (Economy)",
              antrag=date(2027, 8, 30), start=(date(2027, 10, 7), "05:45"), ende=(date(2027, 10, 7), "22:20"),
              bstart=(date(2027, 10, 7), "10:00"), bend=(date(2027, 10, 7), "17:00"), arbeitstage="1",
              kosten=[("Flug Paderborn&#8211;München, Hin- und Rückflug, Economy", 1, 118.00),
                      ("Bahn Kassel&#8211;Paderborn, Hin- und Rückfahrt", 1, 46.00)],
              finanzierung="Fachgebietsbudget, Kostenstelle 4640-00", begruendung="Gutachtersitzung; Einladung liegt bei.",
              hinweis="Preisvergleich: Bahn Kassel&#8211;München Hin- und Rückfahrt 198,00 &#8364; (Auskunft anbei); Flug "
                      "einschließlich Zubringer 164,00 &#8364;.")
    vendor_doc(c, "preisvergleich-bahn-flug.pdf", "price_comparison", vendor="Reisebüro am Königsplatz",
               vendor_addr=["Königsplatz 37", "34117 Kassel"], recipient=["Universität Kassel", f"z. Hd. {c.who}"],
               refs=[("Datum:", "27.08.2027")], heading="Preisvergleich",
               items=[["Flug PAD&#8211;MUC&#8211;PAD, Economy, 07.10.2027", "1", "&#8212;", e(118), e(118)],
                      ["Bahn Kassel&#8211;Paderborn, Hin- und Rückfahrt", "1", "7 % (D)", e(42.99), e(46)],
                      ["Vergleich: Bahn Kassel&#8211;München, Hin- und Rückfahrt, Flexpreis", "1", "7 % (D)", e(185.05), e(198)]],
               sums=[("Flug inkl. Zubringer", e(164)), ("Bahn", e(198))])
    trip_trail(c, "3381040362", "Mi 01.09.2027 08:30", "Der Flug ist einschließlich Zubringer günstiger als die Bahn; Vergleich liegt bei.")

    # 113 abgelehnt: conference dinner claimed
    c = Case("coverage", "trip", 113, "abgelehnt", "C1", "T18", SRC_TRIP, "Conference Dinner 85 € in der Kostenaufstellung beantragt",
             "Kosten für Begleit- und Abendprogramme wie das Conference Dinner sind nicht erstattungsfähig; Verpflegung ist mit dem Tagegeld abgegolten.",
             who="Dr. Pia Hollensteiner", mailbox="p.hollensteiner@uni-kassel.de")
    orga_trip(c, rnr="3381040385", pnr="050073", fg="Fachgebiet Bauphysik", ziel="Wien, ÖSTERREICH", ausland=True,
              anlass="International Building Physics Conference 2027", grund="Vortrag", verkehr="Bahn, 2. Klasse",
              antrag=date(2027, 5, 17), start=(date(2027, 8, 30), "06:20"), ende=(date(2027, 9, 2), "21:50"),
              bstart=(date(2027, 8, 31), "09:00"), bend=(date(2027, 9, 1), "18:00"), arbeitstage="4",
              a1="beantragt am 17.05.2027 (Vorlauf &gt; 8 Wochen)",
              kosten=[("Konferenzgebühr", 1, 480.00), ("Conference Dinner 31.08.2027", 1, 85.00),
                      ("Bahn Kassel&#8211;Wien, Hin- und Rückfahrt", 1, 198.00), ("Unterkunft, 3 Nächte", 3, 291.00)],
              finanzierung="Fachgebietsbudget, Kostenstelle 4511-02", begruendung="Vortrag; Annahme und Programm liegen bei.")
    vendor_doc(c, "registrierung-ibpc.pdf", "booking", vendor="IBPC 2027 Conference Office",
               vendor_addr=["Karlsplatz 13", "1040 Wien", "Österreich"], recipient=["Universität Kassel", f"z. Hd. {c.who}", "34121 Kassel"],
               refs=[("Registrierung:", "IBPC27-0991"), ("Datum:", "12.05.2027")], heading="Registration Confirmation",
               items=[["Full registration", "1", "0 %", e(480), e(480)], ["Conference Dinner, 31.08.2027 (optional)", "1", "0 %", e(85), e(85)]],
               sums=[("Total", e(565))], payment=[("Status", "offen &#8211; Zahlung nach Genehmigung")])
    trip_trail(c, "3381040385", "Fr 21.05.2027 09:47", "In der Kostenaufstellung ist das Conference Dinner mit 85,00 &#8364; "
               "enthalten. Kosten für Begleit- und Abendprogramme sind nicht erstattungsfähig, Verpflegung ist mit dem Tagegeld "
               "abgegolten. Bitte korrigieren Sie die Kostenaufstellung.")


# =========================================================================== #
#                  C1  organisers' layouts, expense reimbursement              #
# =========================================================================== #

def wern(unit, person, extra=()):
    return ["Universität Wernstadt", unit, f"z. Hd. {person}", *extra, "Am Lindenhang 40", "35291 Wernstadt"]


def retail(rows):
    """(description, qty, unit gross, vat rate) -> organiser item rows and sums (net, VAT, gross)."""
    items, net, gross = [], 0.0, 0.0
    for desc, qty, unit, vat in rows:
        line = round(qty * unit, 2)
        line_net = round(line / (1 + vat), 2)
        items.append([desc, str(qty), f"{int(vat * 100)} %", e(line_net), e(line)])
        net, gross = round(net + line_net, 2), round(gross + line, 2)
    return items, [("Summe netto", e(net)), ("zzgl. USt", e(round(gross - net, 2))), ("Rechnungsbetrag", e(gross))], gross


def shop_invoice(c, name, *, vendor, addr, recipient, number, day, rows, payment="Kartenzahlung, bezahlt", notes=(),
                 heading="Rechnung", order=None, doc_type="invoice"):
    items, sums, gross = retail(rows)
    refs = [("Rechnungsnr.", number), ("Rechnungsdatum", de(day))] + ([("Bestellnr.", order)] if order else [])
    vendor_doc(c, name, doc_type, vendor=vendor, vendor_addr=addr, recipient=recipient, refs=refs, heading=heading,
               items=items, sums=sums, payment=[("Zahlung", payment)], notes=list(notes))
    return gross


def receipt(c, name, lines, note=None, doc_type="receipt"):
    c.write(name, doc_type, ms.till_receipt(lines, note), pagesize=RECEIPT_PAGE, margins=RECEIPT_MARGINS)


def c1_expense():
    # 114 abgelehnt: larger purchase bought privately instead of via SAP
    c = Case("coverage", "exp", 114, "abgelehnt", "C1", "E04", SRC_FIN,
             "Oszilloskop für 1.249 € privat im Webshop gekauft und als Auslage eingereicht",
             "Beschaffungen laufen über das SAP-Beschaffungsprogramm; privat verauslagt werden nur kleinere, zeitlich dringende "
             "Anschaffungen. Ein Messgerät für 1.249,00 € ist keine solche Anschaffung, eine Dringlichkeit ist nicht erkennbar.",
             who="Dr. Konstantin Mehrtens-Ali", mailbox="k.mehrtens@uni-wernstadt.de")
    shop_invoice(c, "rechnung-oszilloskop.pdf", vendor="Messtechnik-Direkt24 GmbH", addr=["Lise-Meitner-Straße 3", "24223 Schwentinental"],
                 recipient=wern("Lehrstuhl für Leistungselektronik", "Dr. Konstantin Mehrtens-Ali"), number="MD24-27-118804",
                 day=date(2027, 3, 4), rows=[("Digital-Speicheroszilloskop 4 Kanäle, 200 MHz", 1, 1249.00, 0.19)],
                 payment="Kreditkarte, bezahlt am 04.03.2027")
    mail(c, "anschreiben-erstattung.pdf", subject="Erstattung Oszilloskop", kassel=False,
         sender=f"{c.who} &lt;{c.mailbox}&gt;", to="Finanzbuchhaltung &lt;kostenerstattung@uni-wernstadt.de&gt;",
         sent="Mo 08.03.2027 09:15", body=["Sehr geehrte Damen und Herren,", "anbei die Rechnung für ein Oszilloskop für "
         "unseren Messplatz, das ich privat bezahlt habe. Bitte erstatten Sie mir 1.249,00 &#8364;.", "Viele Grüße<br/>K. Mehrtens-Ali"])
    exp_trail(c, "Mi 10.03.2027 11:30", "Beschaffungen sind über das SAP-Beschaffungsprogramm zu bestellen. Privat verauslagt "
              "und erstattet werden nur kleinere, zeitlich dringende Anschaffungen; ein Oszilloskop für 1.249,00 &#8364; ist "
              "über die Zentrale Beschaffung zu bestellen.")

    # 115 angenommen: small urgent purchase with purpose note
    c = Case("coverage", "exp", 115, "angenommen", "C1", "E04", SRC_FIN,
             "Batterien und Kabeltrommel für eine Feldmessung am Folgetag im Baumarkt gekauft, Zweck vermerkt",
             "Kleine, dringende Anschaffung mit Originalbeleg und Zweckvermerk.", who="Ilka Fröhlich-Danso",
             mailbox="i.froehlich@uni-wernstadt.de")
    receipt(c, "kassenbon.pdf", ["BAUMARKT HAGEDORN", "Industriestraße 22", "33100 Paderborn", "", "BATTERIE MONO D 8ER   1 x 12,99",
                                 "KABELTROMMEL 25M IP44  1 x 25,48", "", "SUMME EUR             38,47", "EC-KARTE              38,47",
                                 "MWST 19% NETTO 32,33 MWST 6,14", "BON 2281 KASSE 02 22.04.27 17:41"],
            note=["Für Feldmessung Wetterstation Lichtenau am 23.04.", "Lehrstuhl Umweltmesstechnik, I. Fröhlich-Danso"])
    exp_trail(c, "Di 27.04.2027 10:10", "Originalbeleg mit Zweckvermerk; kleine, dringende Anschaffung für die Feldmessung.")

    # 116 angenommen: online conference fee claimed as expense
    c = Case("coverage", "exp", 116, "angenommen", "C1", "E09", SRC_TRIP,
             "Gebühr einer reinen Online-Tagung als privat verauslagte Kosten eingereicht",
             "Teilnahmegebühren für Online-Konferenzen sind genau über die Abrechnung privat verauslagter Kosten geltend zu machen.",
             who="Dr. Aurelia Nkemelu", mailbox="a.nkemelu@uni-wernstadt.de")
    shop_invoice(c, "rechnung-online-tagung.pdf", vendor="Deutsche Gesellschaft für Signalverarbeitung e.V.",
                 addr=["Geschäftsstelle", "Paulinenstraße 9", "53111 Bonn"],
                 recipient=wern("Lehrstuhl für Nachrichtentechnik", "Dr. Aurelia Nkemelu"), number="DGSV-27-0412",
                 day=date(2027, 5, 3), rows=[("Teilnahme Online-Fachtagung Signalverarbeitung 2027 (12.&#8211;13.05.2027, virtuell)", 1, 95.00, 0.19)],
                 payment="Kreditkarte, bezahlt", notes=["Die Tagung findet ausschließlich online statt; die Zugangsdaten werden per E-Mail versandt."])
    exp_trail(c, "Mo 17.05.2027 08:45", "Online-Tagungen sind keine Dienstreisen; die Gebühr wird als privat verauslagte Kosten erstattet.")

    # 117 abgelehnt: framework product (notebook) bought privately
    c = Case("coverage", "exp", 117, "abgelehnt", "C1", "E10", SRC_FRAME,
             "Notebook im Elektronikmarkt privat gekauft, Rechnung an den Lehrstuhl",
             "Für Notebooks besteht ein verbindlicher Rahmenvertrag; sie sind ausschließlich beim Rahmenvertragspartner über WPS zu bestellen.",
             who="Tobias Ngata-Weiland", mailbox="t.ngata@uni-wernstadt.de")
    shop_invoice(c, "rechnung-elektronikmarkt.pdf", vendor="TechWelt Elektronikmärkte GmbH", addr=["Ostring 140", "44787 Bochum"],
                 recipient=wern("Lehrstuhl für Robotik", "Tobias Ngata-Weiland"), number="TW-0441-27-7712",
                 day=date(2027, 6, 11), rows=[("Notebook 14 Zoll, 16 GB RAM, 512 GB SSD", 1, 749.00, 0.19),
                                              ("Notebook-Tasche", 1, 24.99, 0.19)], payment="EC-Karte, bezahlt")
    exp_trail(c, "Do 17.06.2027 13:20", "Für PCs, Notebooks und Monitore besteht ein verbindlicher Rahmenvertrag; Notebooks "
              "sind ausschließlich beim Rahmenvertragspartner über das WPS-System zu bestellen. Eine Erstattung des privat "
              "gekauften Geräts ist nicht möglich.")

    # 118 angenommen: small item outside any framework contract
    c = Case("coverage", "exp", 118, "angenommen", "C1", "E10", SRC_FRAME,
             "Netzwerk-Kabeltester für das Labor, kein Rahmenvertragsprodukt", "Kein Rahmenvertragsprodukt, Rechnung an den Lehrstuhl.",
             who="Greta Iwanowa-Stamm", mailbox="g.iwanowa@uni-wernstadt.de")
    shop_invoice(c, "rechnung-kabeltester.pdf", vendor="Netzwerkbedarf Lohmann e.K.", addr=["Am Hafen 5", "26122 Oldenburg"],
                 recipient=wern("Lehrstuhl für Rechnernetze", "Greta Iwanowa-Stamm", ["Labor R 2.07"]), number="NL-27-30551",
                 day=date(2027, 2, 9), rows=[("Netzwerk-Kabeltester RJ45/RJ11 mit Remote-Einheit", 1, 64.90, 0.19)])
    exp_trail(c, "Fr 12.02.2027 09:30", "Originalrechnung an den Lehrstuhl, kein Rahmenvertragsprodukt.")

    # 119 abgelehnt: decoration
    c = Case("coverage", "exp", 119, "abgelehnt", "C1", "E11", SRC_FIN, "Adventsdekoration für das Institutsfoyer",
             "Schmuck- und Dekorationsartikel wie Weihnachtsdekoration sind nach der Bewirtungskostenrichtlinie nicht erstattungsfähig.",
             who="Renate Kowalski-Bähr", mailbox="r.kowalski@uni-wernstadt.de")
    shop_invoice(c, "rechnung-dekoration.pdf", vendor="Gartencenter Blumenhof Riedel", addr=["Weinbergstraße 40", "97080 Würzburg"],
                 recipient=wern("Institut für Elektrische Energietechnik", "Renate Kowalski-Bähr", ["Sekretariat"]),
                 number="BR-27-11-2207", day=date(2027, 11, 26),
                 rows=[("Adventskranz Tanne, Ø 40 cm", 1, 34.90, 0.07), ("LED-Lichterkette 10 m warmweiß", 2, 14.95, 0.19),
                       ("Weihnachtsstern im Topf", 3, 7.20, 0.07)], payment="bar, bezahlt",
                 notes=["Für das Foyer des Instituts, Gebäude B (handschriftlich)"])
    exp_trail(c, "Do 02.12.2027 10:05", "Beschaffungen von Schmuck- und Dekorationsartikeln, z. B. Weihnachtsdekoration, sind "
              "nach der Bewirtungskostenrichtlinie nicht erstattungsfähig.")

    # 120 abgelehnt: guest gift above 30 EUR
    c = Case("coverage", "exp", 120, "abgelehnt", "C1", "E12", SRC_FIN, "Gastgeschenk 48,80 € bei einer Dienstreise nach Krakau",
             "Gastgeschenke bei Dienstreisen können nur bis 30,00 € übernommen werden; 48,80 € überschreiten die Grenze.",
             who="Prof. Dr. Wiebke Sandoval", mailbox="w.sandoval@uni-wernstadt.de")
    shop_invoice(c, "rechnung-gastgeschenk.pdf", vendor="Buchhandlung am Markt Wernstadt", addr=["Marktplatz 7", "35291 Wernstadt"],
                 recipient=wern("Lehrstuhl für Hochspannungstechnik", "Prof. Dr. Wiebke Sandoval"), number="BM-27-04471",
                 day=date(2027, 9, 14), rows=[("Bildband &#8222;Wernstadt und das Lahntal&#8220;", 1, 39.90, 0.07),
                                              ("Präsentverpackung mit Grußkarte", 1, 8.90, 0.19)],
                 payment="EC-Karte, bezahlt", notes=["Gastgeschenk für die Partnerfakultät der TU Krakau, Dienstreise 20.&#8211;22.09.2027 (handschriftlich)"])
    exp_trail(c, "Mo 04.10.2027 09:00", "Kleinere Gastgeschenke bei Dienstreisen können übernommen werden, sofern sie einen "
              "Wert von 30,00 &#8364; nicht übersteigen. Das Geschenk kostet 48,80 &#8364;.")

    # 121 angenommen: guest gift below 30 EUR
    c = Case("coverage", "exp", 121, "angenommen", "C1", "E12", SRC_FIN, "Gastgeschenk 27,50 € bei einer Dienstreise nach Lyon",
             "Gastgeschenk bei einer Dienstreise unter 30,00 €, sozial übliche Geste.", who="Dr. Lorenz Achterberg",
             mailbox="l.achterberg@uni-wernstadt.de")
    shop_invoice(c, "rechnung-gastgeschenk.pdf", vendor="Buchhandlung am Markt Wernstadt", addr=["Marktplatz 7", "35291 Wernstadt"],
                 recipient=wern("Lehrstuhl für Mikroelektronik", "Dr. Lorenz Achterberg"), number="BM-27-03318",
                 day=date(2027, 6, 2), rows=[("Bildband &#8222;Wernstadt und das Lahntal&#8220;", 1, 27.50, 0.07)],
                 payment="EC-Karte, bezahlt", notes=["Gastgeschenk für die Gastgeber am INSA Lyon, Dienstreise 07.&#8211;09.06.2027 (handschriftlich)"])
    exp_trail(c, "Mi 16.06.2027 14:12", "Gastgeschenk bei einer Dienstreise im Rahmen von 30,00 &#8364;.")

    # 122 abgelehnt: give-aways above 10 EUR each
    c = Case("coverage", "exp", 122, "abgelehnt", "C1", "E13", SRC_FIN, "120 USB-Sticks à 12,90 € als Give-aways für den Messestand",
             "Give-aways auf Messen sind nur bis zu einem Wert von 10,00 € übernahmefähig; 12,90 € je Stück liegen darüber.",
             who="Marlene Osei-Brandt", mailbox="m.osei@uni-wernstadt.de")
    shop_invoice(c, "rechnung-werbemittel.pdf", vendor="Werbemittel Stöckl GmbH", addr=["Gewerbering 18", "94469 Deggendorf"],
                 recipient=wern("Presse- und Öffentlichkeitsarbeit", "Marlene Osei-Brandt"), number="WS-27-20331",
                 day=date(2027, 3, 18), rows=[("USB-Stick 32 GB mit Logo-Gravur", 120, 12.90, 0.19)], payment="Überweisung, bezahlt",
                 notes=["Für den Stand der Universität auf der Hannover Messe 2027 (handschriftlich)"])
    exp_trail(c, "Fr 26.03.2027 11:44", "Werbemaßnahmen auf Messen sind übernahmefähig, Give-aways aber nur bis zu einem Wert "
              "von 10,00 &#8364;. Die USB-Sticks kosten 12,90 &#8364; je Stück.")

    # 123 angenommen: give-aways below 10 EUR each
    c = Case("coverage", "exp", 123, "angenommen", "C1", "E13", SRC_FIN, "200 Notizblöcke à 1,95 € als Give-aways für die Messe",
             "Give-aways bis 10,00 € je Stück für den Messestand sind übernahmefähig.", who="Hendrik Tiedemann-Obi",
             mailbox="h.tiedemann@uni-wernstadt.de")
    shop_invoice(c, "rechnung-werbemittel.pdf", vendor="Werbemittel Stöckl GmbH", addr=["Gewerbering 18", "94469 Deggendorf"],
                 recipient=wern("Zentrale Studienberatung", "Hendrik Tiedemann-Obi"), number="WS-27-20877",
                 day=date(2027, 4, 2), rows=[("Notizblock A6 mit Logo, 50 Blatt", 200, 1.95, 0.19)], payment="Überweisung, bezahlt",
                 notes=["Für den Stand der Universität auf der Bildungsmesse didacta 2027 (handschriftlich)"])
    exp_trail(c, "Mo 12.04.2027 08:20", "Give-aways für den Messestand unter 10,00 &#8364; je Stück.")

    # 124 abgelehnt: Christmas party catering
    c = Case("coverage", "exp", 124, "abgelehnt", "C1", "E14", SRC_FIN, "Catering der Weihnachtsfeier des Fachgebiets",
             "Bewirtungen bei geselligen Veranstaltungen wie Weihnachtsfeiern und Bewirtungen ohne externe Personen sind nicht erstattungsfähig.",
             who="Dr. Sophie Lindqvist-Adeyemi", mailbox="s.lindqvist@uni-wernstadt.de")
    shop_invoice(c, "rechnung-catering.pdf", vendor="Partyservice Kornblume", addr=["Lindenstraße 3", "35287 Amöneburg"],
                 recipient=wern("Fachgebiet Optische Technologien", "Dr. Sophie Lindqvist-Adeyemi"), number="KB-27-1218",
                 day=date(2027, 12, 17), rows=[("Fingerfood-Buffet, 18 Personen", 18, 9.80, 0.07), ("Glühwein, 10 l", 1, 38.20, 0.19)],
                 payment="bar, bezahlt", notes=["Weihnachtsfeier Fachgebiet am 16.12.2027 (handschriftlich)"])
    exp_trail(c, "Di 21.12.2027 10:00", "Bewirtungskosten für Veranstaltungen geselliger Art, z. B. Weihnachtsfeiern, sowie "
              "Bewirtungen ohne externe Personen sind nach der Bewirtungskostenrichtlinie nicht erstattungsfähig.")


# =========================================================================== #
#                       C1  organisers' layouts, procurement                   #
# =========================================================================== #

def write_offers(c, fg, quotes):
    """quotes: (vendor, address lines, number, date, items) -> one offer PDF each; returns [(vendor, number, date, net, gross)]."""
    out = []
    for i, (vendor, lines, number, day, items) in enumerate(quotes, 1):
        story, net, gross = ms.offer(vendor=vendor, vendor_lines=lines, recipient=ms.recip(fg, c.who), number=number,
                                     date=day, valid="30 Tage", items=items)
        c.write(f"angebot-{i}.pdf", "offer", story)
        out.append((vendor, number, day, net, gross))
    return out


def proc_form(c, **kw):
    form, net, gross = ms.proc_form(requester=c.who, **kw)
    c.write("beschaffungsantrag.pdf", "application", form)
    return net, gross


def c1_procurement():
    # 125 abgelehnt: copy paper (framework contract) from a local dealer
    c = Case("coverage", "proc", 125, "abgelehnt", "C1", "P02", SRC_FRAME,
             "40 Kartons Kopierpapier beim örtlichen Händler mit drei Angeboten statt über WPS",
             "Für Büro- und Kopierpapier besteht ein Rahmenvertrag; Rahmenvertragsprodukte sind ausschließlich beim Rahmenvertragspartner über WPS zu bestellen.",
             who="Petra Hoffmann-Diallo", mailbox="p.hoffmann@uni-wernstadt.de")
    fg, paper = "Fachgebiet Theoretische Elektrotechnik", "Kopierpapier A4, 80 g/m², Karton à 5 x 500 Blatt"
    write_offers(c, fg, [("Papierhaus Wernstadt GmbH", ["Bahnhofstraße 21", "35291 Wernstadt"], "PW-27-0815", "02.02.2027", [(paper, 40, 23.40)]),
                         ("Bürobedarf Schaller KG", ["Ludwigstraße 4", "35390 Gießen"], "BS-A-2207", "03.02.2027", [(paper, 40, 24.10)]),
                         ("Office-Versand Lorenz", ["Hafenweg 30", "48155 Münster"], "OVL-27-118", "03.02.2027", [(paper, 40, 25.30)])])
    proc_form(c, number="ZB-2027-0144", date="05.02.2027", fachgebiet=fg, phone="0561 7390-4410",
              kostenstelle="71 4410 / Auftrag 2140090", holder="Prof. Dr. Achim Lauterbach", category="Verbrauchsmaterial",
              framework=False, procedure="Preisvergleich, drei schriftliche Angebote", offers=3,
              supplier="Papierhaus Wernstadt GmbH (Angebot PW-27-0815)", items=[(paper, 40, 23.40)],
              begruendung="Jahresbedarf Kopierpapier für Lehrstuhl und Praktikum; günstigstes von drei Angeboten.")
    proc_trail(c, "Di 09.02.2027 10:20", "Für Büro- und Kopierpapier besteht ein Rahmenvertrag des Landes, der über das "
               "WPS-System zu buchen ist. Rahmenvertragsprodukte müssen ausschließlich beim Rahmenvertragspartner bestellt "
               "werden; Angebote anderer Händler ersetzen das nicht.")

    # 126 abgelehnt: budget holder has not commissioned the order
    c = Case("coverage", "proc", 126, "abgelehnt", "C1", "P03", SRC_PROC,
             "Antrag ohne Unterschrift der Kostenstellenbevollmächtigten, 'wird nachgereicht'",
             "Bestellungen müssen von der/dem Kostenstellenbevollmächtigten beauftragt werden; die Unterschrift fehlt.",
             who="Jonte Rasmussen", mailbox="j.rasmussen@uni-wernstadt.de")
    fg, sensor = "Fachgebiet Antriebstechnik", "Drehmomentsensor 0&#8211;50 Nm mit Messverstärker"
    write_offers(c, fg, [("Sensorik Thalheim GmbH", ["Am Kanal 8", "09221 Neukirchen"], "ST-27-0402", "11.05.2027", [(sensor, 1, 1890.00)]),
                         ("Messwelt Brandis KG", ["Leipziger Straße 3", "04821 Brandis"], "MB-2027-91", "12.05.2027", [(sensor, 1, 1985.00)]),
                         ("Torque Systems Rehfeld", ["Werkstraße 12", "72762 Reutlingen"], "TSR-0119", "12.05.2027", [(sensor, 1, 2040.00)])])
    proc_form(c, number="ZB-2027-0466", date="14.05.2027", fachgebiet=fg, phone="0561 7390-4588",
              kostenstelle="71 4588 / Auftrag 2140301", holder="Prof. Dr. Wenke Albers-Okafor", category="Anlage",
              framework=False, procedure="Preisvergleich, drei schriftliche Angebote", offers=3,
              supplier="Sensorik Thalheim GmbH (Angebot ST-27-0402)", items=[(sensor, 1, 1890.00)], signed=False,
              begruendung="Sensor für den Antriebsprüfstand; günstigstes Angebot. Die Unterschrift von Frau Prof. "
                          "Albers-Okafor wird nach ihrer Rückkehr nachgereicht.")
    proc_trail(c, "Di 18.05.2027 09:05", "Bestellungen müssen von der/dem Kostenstellenbevollmächtigten beauftragt werden. Der "
               "Antrag ist nicht unterschrieben; eine Beauftragung durch Frau Prof. Albers-Okafor liegt nicht vor.")

    # 127 angenommen: budget holder commissions by separate e-mail
    c = Case("coverage", "proc", 127, "angenommen", "C1", "P03", SRC_PROC,
             "Beauftragung des Kostenstellenbevollmächtigten per separater E-Mail statt Unterschrift",
             "Der Kostenstellenbevollmächtigte beauftragt die Bestellung schriftlich per E-Mail; drei Angebote, günstigstes gewählt.",
             who="Dr. Anouk Verbeek-Haas", mailbox="a.verbeek@uni-wernstadt.de")
    fg, table = "Fachgebiet Photonik", "Optischer Tisch 1200 x 900 mm, passiv gedämpft"
    write_offers(c, fg, [("Optomechanik Harz GmbH", ["Bergstraße 2", "38640 Goslar"], "OH-27-1044", "07.09.2027", [(table, 1, 2310.00)]),
                         ("Laserlab Supply Kranz", ["Uferweg 7", "07745 Jena"], "LSK-27-0388", "08.09.2027", [(table, 1, 2395.00)]),
                         ("Vibration Control Mertens", ["Daimlerstraße 30", "70372 Stuttgart"], "VCM-A-0712", "09.09.2027", [(table, 1, 2480.00)])])
    proc_form(c, number="ZB-2027-0712", date="13.09.2027", fachgebiet=fg, phone="0561 7390-4633",
              kostenstelle="71 4633 / Auftrag 2140512", holder="Prof. Dr. Ingmar Støvring", category="Anlage",
              framework=False, procedure="Preisvergleich, drei schriftliche Angebote", offers=3,
              supplier="Optomechanik Harz GmbH (Angebot OH-27-1044)", items=[(table, 1, 2310.00)], signed=False,
              begruendung="Aufbau des Interferometers; günstigstes von drei Angeboten. Beauftragung durch Prof. Støvring per "
                          "E-Mail vom 13.09.2027 (anbei).")
    mail(c, "email-beauftragung.pdf", kassel=False, subject="AW: Beschaffungsantrag ZB-2027-0712 optischer Tisch",
         sender="Prof. Dr. Ingmar Støvring &lt;i.stovring@uni-wernstadt.de&gt;", sent="Mo 13.09.2027 16:48",
         to="Zentrale Beschaffung &lt;beschaffung@uni-wernstadt.de&gt;", cc=f"{c.who} &lt;{c.mailbox}&gt;",
         body=["Sehr geehrte Damen und Herren,", "als Kostenstellenbevollmächtigter der Kostenstelle 71 4633 beauftrage ich die "
               "Bestellung gemäß Beschaffungsantrag ZB-2027-0712 (Optomechanik Harz GmbH, 2.310,00 &#8364; netto). Ich bin "
               "bis Ende September auf Dienstreise und kann den Antrag nicht unterschreiben.", "Mit freundlichen Grüßen<br/>Ingmar Støvring"])
    proc_trail(c, "Mi 15.09.2027 08:50", "Beauftragung durch den Kostenstellenbevollmächtigten per E-Mail liegt vor; drei "
               "Angebote, günstigstes gewählt.")

    # 128 abgelehnt: bottled gas (framework contract) from a regional dealer
    c = Case("coverage", "proc", 128, "abgelehnt", "C1", "P08", SRC_FRAME,
             "Argon-Flaschen beim regionalen Gashändler mit drei Angeboten statt aus dem WPS-Katalog Flaschengase",
             "Für Flaschengase (außer Helium) besteht ein Rahmenvertrag; die Produkte müssen über den WPS-Katalog bestellt werden.",
             who="Dr. Elif Brandenburger", mailbox="e.brandenburger@uni-wernstadt.de")
    fg, argon, rent = "Fachgebiet Schweißtechnik", "Argon 4.6, Flasche 50 l, Füllung", "Flaschenmiete 12 Monate"
    write_offers(c, fg, [("Gase-Service Mittelhessen GmbH", ["Industriepark 4", "35415 Pohlheim"], "GSM-27-310", "18.10.2027",
                          [(argon, 6, 214.00), (rent, 6, 38.00)]),
                         ("TechnoGas Wetzlar", ["Hermannsteiner Str. 9", "35576 Wetzlar"], "TGW-A-0981", "19.10.2027",
                          [(argon, 6, 225.00), (rent, 6, 40.00)]),
                         ("Schweißfachhandel Krick", ["Am Bahndamm 1", "35037 Marburg"], "SK-27-077", "19.10.2027",
                          [(argon, 6, 231.00), (rent, 6, 36.00)])])
    proc_form(c, number="ZB-2027-0855", date="21.10.2027", fachgebiet=fg, phone="0561 7390-4702",
              kostenstelle="71 4702 / Auftrag 2140620", holder="Prof. Dr. Malte Grünewald", category="Verbrauchsmaterial",
              framework=False, procedure="Preisvergleich, drei schriftliche Angebote", offers=3,
              supplier="Gase-Service Mittelhessen GmbH (Angebot GSM-27-310)", items=[(argon, 6, 214.00), (rent, 6, 38.00)],
              begruendung="Schutzgas für die Schweißversuche im Wintersemester; günstigstes Angebot.")
    proc_trail(c, "Mo 25.10.2027 09:40", "Für Flaschengase (außer Helium) besteht ein Rahmenvertrag mit der Linde GmbH; die "
               "Produkte sind im WPS-System unter dem Katalog Rahmenvertrag Flaschengase gelistet und müssen hierüber bestellt "
               "werden.")

    # 129 angenommen: nitrogen bottles from the WPS framework catalogue
    c = Case("coverage", "proc", 129, "angenommen", "C1", "P08", SRC_FRAME,
             "Stickstoff-Flaschen aus dem WPS-Katalog Rahmenvertrag Flaschengase, keine Vergleichsangebote",
             "Abruf aus dem Rahmenvertrag über WPS; Vergleichsangebote entfallen.", who="Lukas Ferreira-Hahn",
             mailbox="l.ferreira@uni-wernstadt.de")
    fg = "Fachgebiet Werkstofftechnik"
    gas = [("Stickstoff 5.0, Flasche 50 l, Füllung", 8, 96.40), ("Flaschenmiete 12 Monate", 8, 31.00)]
    cart, _ = ms.wps_cart(number="WK-0027-31907", catalog="Rahmenvertrag Flaschengase (außer Helium)",
                          supplier="Linde GmbH, Pullach", created="03.11.2027", buyer=c.who, account="71 4715 / Auftrag 2140640",
                          items=[("LG-N50-50", *gas[0]), ("LG-MIETE-12", *gas[1])])
    c.write("warenkorb-wps.pdf", "framework_cart", cart)
    proc_form(c, number="ZB-2027-0890", date="03.11.2027", fachgebiet=fg, phone="0561 7390-4715",
              kostenstelle="71 4715 / Auftrag 2140640", holder="Prof. Dr. Hilde Ostendorf", category="Verbrauchsmaterial",
              framework=True, procedure="Abruf Rahmenvertrag (WPS)", offers=0, supplier="Linde GmbH (Rahmenvertragspartner)",
              items=gas, begruendung="Inertgas für den Glühofen; Abruf aus dem Rahmenvertrag Flaschengase, Warenkorb anbei.")
    proc_trail(c, "Do 04.11.2027 10:15", "Abruf aus dem Rahmenvertrag Flaschengase über WPS; Vergleichsangebote sind nicht erforderlich.")


# =========================================================================== #
#        C2  counterfactual pairs on spot-check cases: one fact changed        #
# =========================================================================== #

def c2_conference_trip(number, label, antrag, why):
    """Built on business-trip-spot-check/dienstreiseantrag-02; only the application date differs within the pair."""
    c = Case("coverage", "trip", number, label, "C2", "T01", SRC_TRIP,
             f"Paar zu trip-02: Konferenzreise nach Gent, Antrag am {de(antrag)}", why,
             who="Dr. Johanna Ruhwedel-Asante", mailbox="j.ruhwedel@uni-kassel.de")
    orga_trip(c, rnr=f"33810412{number % 100:02d}", pnr="045512", fg="Fachgebiet Eingebettete Systeme", ziel="Gent, BELGIEN",
              ausland=True, anlass="EuroDep 2027 &#8211; European Symposium on Dependable Computing",
              grund="Vortrag des nach Peer-Review angenommenen Beitrags &#8222;Fault Injection for Sensor Fusion&#8220;",
              verkehr="Bahn, 2. Klasse", antrag=antrag, start=(date(2027, 11, 8), "06:45"), ende=(date(2027, 11, 11), "20:50"),
              bstart=(date(2027, 11, 9), "09:00"), bend=(date(2027, 11, 10), "17:30"), arbeitstage="4 (Anreise + 2 Konferenztage + Abreise)",
              a1="beantragt am 30.08.2027 (Vorlauf &gt; 8 Wochen)",
              kosten=[("Konferenzregistrierung (Early Bird)", 1, 420.00), ("Bahn Kassel&#8211;Gent, Hin- und Rückfahrt", 1, 166.00),
                      ("Unterkunft, 3 Nächte à 78,00 &#8364;", 3, 234.00), ("Verpflegungsmehraufwand (Pauschale BE)", 1, 58.00)],
              finanzierung="Drittmittelprojekt SafeFusion, Kostenstelle 6618-03 (Reisemittel)",
              begruendung="Der Beitrag wurde nach Peer-Review angenommen (Bestätigung anbei). Die Unterkunft liegt im "
                          "Konferenzhotel innerhalb des Auslandsübernachtungssatzes für Belgien.")
    mail(c, "email-annahmebestaetigung.pdf", subject="EuroDep 2027 &#8211; Paper Acceptance Notification (#73)",
         sender="EuroDep 2027 Program Chairs &lt;chairs@eurodep2027.example&gt;", sent="Mi 18.08.2027 22:10",
         body=["Dear Dr. Ruhwedel-Asante,", "we are pleased to inform you that your submission #73 &#8222;Fault Injection for "
               "Sensor Fusion&#8220; has been <b>accepted</b> for presentation at EuroDep 2027 in Ghent, Belgium, 9&#8211;10 "
               "November 2027.", "At least one author must register and present on site. Early-bird registration (420 EUR) "
               "closes on 15 September 2027.", "Best regards,<br/>The EuroDep 2027 Program Committee"])
    vendor_doc(c, "konferenz-registrierung.pdf", "booking", vendor="EuroDep 2027 Conference Office",
               vendor_addr=["c/o Congress Ghent NV", "Van Rysselberghedreef 2", "9000 Gent", "Belgien"],
               recipient=["Universität Kassel", "Fachbereich 16 &#183; Fachgebiet Eingebettete Systeme",
                          "z. Hd. Dr. Johanna Ruhwedel-Asante", "Wilhelmshöher Allee 71-73", "34121 Kassel"],
               refs=[("Registrierungsnummer:", "ED27-R-0218"), ("Rechnungsdatum:", "06.09.2027")],
               heading="Registration Confirmation / Rechnung",
               items=[["Full registration, early bird", "1", "0 % (reverse charge)", e(420), e(420)]],
               sums=[("Summe (brutto)", e(420))], payment=[("Status", "offen &#8211; Zahlung nach Genehmigung der Dienstreise")],
               notes=["Das optionale Conference Dinner (70,00 EUR) wurde nicht gebucht."])
    rail(c, out="Kassel-Wilhelmshöhe &#8594; Gent-Sint-Pieters, 08.11.2027, 06:45 Uhr, 2. Klasse",
         back="Gent-Sint-Pieters &#8594; Kassel-Wilhelmshöhe, 11.11.2027, 13:58 Uhr, 2. Klasse", price_each=83.00,
         booked=date(2027, 9, 3), note="Preisvergleich Flug Frankfurt&#8211;Brüssel ab 236,00 EUR; die Bahn ist wirtschaftlicher.")
    return c


def c2_grant_trip(number, label, credited, why):
    """Built on business-trip-spot-check/dienstreiseantrag-05; only whether the grant is credited differs."""
    c = Case("coverage", "trip", number, label, "C2", "T09", SRC_TRIP,
             "Paar zu trip-05: Reisestipendium für Flug und Unterkunft " + ("angerechnet" if credited else "nicht angerechnet"),
             why, who="Malik Steenbergen", mailbox="m.steenbergen@uni-kassel.de")
    kosten = [("Flug Frankfurt&#8211;Vancouver, Hin- und Rückflug, Economy", 1, 940.00),
              ("Konferenzregistrierung (Student Rate)", 1, 380.00), ("Unterkunft, 5 Nächte à 118,00 &#8364;", 5, 590.00),
              ("Transfer / Nahverkehr vor Ort", 1, 45.00)]
    if credited:
        kosten.append(("abzgl. Reisestipendium VDWI (Flug und Unterkunft, Höchstbetrag)", 1, -1000.00))
    orga_trip(c, rnr=f"33810413{number % 100:02d}", pnr="063318", fg="Fachgebiet Kunststofftechnik", ziel="Vancouver, KANADA",
              ausland=True, anlass="International Conference on Composite Materials 2027",
              grund="Posterbeitrag im Rahmen des Promotionsprojekts", verkehr="Flug (Economy)", antrag=date(2027, 4, 19),
              start=(date(2027, 7, 25), "09:10"), ende=(date(2027, 7, 31), "14:30"), bstart=(date(2027, 7, 26), "09:00"),
              bend=(date(2027, 7, 29), "18:00"), arbeitstage="6",
              kosten=kosten,
              finanzierung=("Reisestipendium VDWI bis 1.000 EUR für Flug und Unterkunft (angerechnet); Restbetrag aus dem "
                            "Lehrstuhlbudget, Kostenstelle 4730-02") if credited else
                           "Lehrstuhlbudget Kunststofftechnik, Kostenstelle 4730-02 (volle Summe)",
              begruendung="Posterbeitrag aus dem Promotionsprojekt auf der wichtigsten Fachtagung des Gebiets. " +
                          ("Die Stipendienzusage liegt bei und ist in der Kostenaufstellung angerechnet." if credited else
                           "Ich bitte um vollständige Übernahme der Reisekosten."))
    mail(c, "email-stipendienzusage.pdf", subject="Nachwuchsreisestipendium &#8211; Zusage ICCM 2027",
         sender="Geschäftsstelle VDWI e. V. &lt;stipendien@vdwi.example&gt;", sent="Di 06.04.2027 15:20",
         body=["Sehr geehrter Herr Steenbergen,", "für Ihre Teilnahme an der ICCM 2027 in Vancouver erhalten Sie ein "
               "<b>Nachwuchsreisestipendium von bis zu 1.000 EUR</b> zur Deckung von <b>Flug und Unterkunft</b>.",
               "Eine Doppelfinanzierung derselben Kostenpositionen ist ausgeschlossen. Bitte informieren Sie Ihre "
               "Reisekostenstelle über diese Zusage.", "Mit freundlichen Grüßen<br/>Geschäftsstelle"])
    vendor_doc(c, "flug-angebot.pdf", "offer", vendor="Reisebüro Campus Kassel GmbH", vendor_addr=["Königsplatz 47", "34117 Kassel"],
               recipient=["Universität Kassel", "Fachgebiet Kunststofftechnik", f"z. Hd. {c.who}", "34121 Kassel"],
               refs=[("Angebotsnummer:", "RCK-2027-0544"), ("Angebotsdatum:", "14.04.2027")], heading="Flugangebot",
               items=[["Hinflug FRA &#8594; YVR, 25.07.2027, Economy", "1", "&#8212;", e(470), e(470)],
                      ["Rückflug YVR &#8594; FRA, 30.07.2027, Economy", "1", "&#8212;", e(470), e(470)]],
               sums=[("Summe", e(940))], notes=["Günstigste zumutbare Verbindung in der Economy-Klasse; Vergleich mit "
                                                 "Umsteigeverbindung über Amsterdam 1.012,00 &#8364;."])
    return c


def c2_trip():
    c = c2_conference_trip(201, "angenommen", date(2027, 8, 30), "Vollständiger, rund zehn Wochen vor Reisebeginn gestellter Antrag.")
    trip_trail(c, "3381041201", "Fr 03.09.2027 08:12", "Vollständiger Antrag, rechtzeitig vor Reiseantritt gestellt.")
    c = c2_conference_trip(202, "abgelehnt", date(2027, 11, 12),
                           "Der Antrag ist erst am 12.11.2027 gestellt, die Reise begann am 08.11.2027; eine Genehmigung vor Reiseantritt liegt nicht vor.")
    trip_trail(c, "3381041202", "Mo 15.11.2027 09:30", "Ihr Antrag ist am 12.11.2027 eingegangen, die Reise nach Gent hat "
               "nach Ihren Angaben am 08.11.2027 begonnen. Dienstreisen sind vor Reiseantritt zu genehmigen; ein Antrag auf "
               "nachträgliche Genehmigung im Ausnahmeverfahren liegt nicht vor.")
    c = c2_grant_trip(203, "abgelehnt", False, "Das Stipendium deckt Flug und Unterkunft bis 1.000 EUR, der Antrag beantragt "
                      "die Kosten trotzdem voll aus dem Lehrstuhlbudget: Doppelfinanzierung.")
    trip_trail(c, "3381041303", "Do 22.04.2027 10:31", "Ihrem Antrag liegt eine Stipendienzusage über bis zu 1.000 EUR für "
               "Flug und Unterkunft bei; beantragt ist gleichwohl die volle Übernahme durch das Lehrstuhlbudget. Dieselben "
               "Kostenpositionen können nicht zweimal erstattet werden.")
    c = c2_grant_trip(204, "angenommen", True, "Das Stipendium ist mitgeteilt und in der Kostenaufstellung angerechnet; "
                      "beantragt ist nur der Restbetrag.")
    trip_trail(c, "3381041304", "Do 22.04.2027 10:35", "Die Leistung von dritter Seite ist vor Reiseantritt mitgeteilt und angerechnet.")


def c2_receipt(number, label, noted, why):
    """Built on task-2-expense-reimbursement-spot-check/auslagenerstattung-02; only the handwritten keyword differs."""
    c = Case("coverage", "exp", number, label, "C2", "E01", SRC_FIN,
             "Paar zu exp-02: Kassenbon nur mit Artikelnummern, " + ("Stichwort vermerkt" if noted else "ohne Stichwort"),
             why, who="Nils Achterkamp-Oyelowo", mailbox="n.achterkamp@uni-wernstadt.de")
    receipt(c, "beleg-1.pdf", ["BAUZENTRUM FALKENRATH", "Leipziger Straße 61", "36037 Fulda", "Tel. 0661 48 20 917", "",
                               "ART 220871", "  3 ST x 2,79             8,37", "ART 640114", "  1 ST x 5,49             5,49",
                               "ART 118302", "  2 ST x 3,15             6,30", "", "SUMME EUR                20,16",
                               "BAR                      25,00", "RÜCKGELD                  4,84",
                               "MWST 19% NETTO 16,94 MWST 3,22", "BON 7712 KASSE 01 09.06.27 08:12", "VIELEN DANK"],
            note=["Isolierband + Lüsterklemmen", "für Prüfstand Labor B 1.04", "(N. Achterkamp-Oyelowo)"] if noted else None)
    exp_trail(c, "Mi 16.06.2027 10:40", why)


def c2_proforma(number, label, final, why):
    """Built on auslagenerstattung-04; only whether the document is the final invoice differs."""
    c = Case("coverage", "exp", number, label, "C2", "E02", SRC_FIN,
             "Paar zu exp-04: Laborbedarf, " + ("endgültige Rechnung" if final else "nur Pro-forma-Rechnung"), why,
             who="Dr. Ingrid Vahlenkamp", mailbox="i.vahlenkamp@uni-wernstadt.de")
    shop_invoice(c, "rechnung-laborbedarf.pdf", vendor="Laborversand Ehrhorn & Kühl", addr=["Hafenstraße 31", "18055 Rostock",
                                                                                           "USt-IdNr. DE 301 772 418"],
                 recipient=wern("Fachgebiet Zellbiologie", "Frau Dr. Ingrid Vahlenkamp"),
                 number="RE-27-55180" if final else "PF-27-1180", day=date(2027, 7, 6),
                 rows=[("Zellkulturflaschen T75, 100 Stück", 2, 48.20, 0.19), ("Serologische Pipetten 10 ml, 200 Stück", 1, 31.40, 0.19)],
                 heading="Rechnung" if final else "Pro-forma-Rechnung", payment="Vorkasse, BEZAHLT 07.07.2027 Überw.",
                 notes=["Ware geliefert am 09.07.2027." if final else
                        "Dieses Dokument ist keine Rechnung im umsatzsteuerlichen Sinn. Die Rechnung erhalten Sie mit der Lieferung."])
    exp_trail(c, "Di 20.07.2027 09:10", why)


def c2_tea(number, label, guests, why):
    """Built on auslagenerstattung-07; only whether external guests were served differs."""
    c = Case("coverage", "exp", number, label, "C2", "E07", SRC_FIN,
             "Paar zu exp-07: Kaffee, Tee, Gebäck, Wasser " + ("für externe Gäste mit Teilnehmerliste" if guests else "für die Teeküche"),
             why, who="Henrike Lammers-Abebe", mailbox="h.lammers@uni-wernstadt.de")
    shop_invoice(c, "rechnung-verpflegung.pdf", vendor="Warenhafen Marktplatz", addr=["Verkauf durch: Feinkost Brüning KG",
                                                                                     "Stader Straße 9", "21614 Buxtehude"],
                 recipient=wern("Lehrstuhl für Automatisierungstechnik", "Frau Henrike Lammers-Abebe",
                                [] if guests else ["Teeküche Geb. D, 2. OG"]),
                 number="WH-DE-27-8821473", day=date(2027, 10, 11), order="WH-7714-220-0181",
                 rows=[("Kaffee gemahlen, 500 g", 2, 8.49, 0.07), ("Schwarztee, 50 Beutel", 1, 3.99, 0.07),
                       ("Butterkekse, 6 x 200 g", 1, 9.90, 0.07), ("Mineralwasser 0,5 l, 12 Flaschen", 2, 6.48, 0.19)],
                 payment="Online-Bezahldienst, bezahlt",
                 notes=["Für die Bewirtung der externen Gäste beim Projekttreffen ROBUST am 14.10.2027 (handschriftlich)"]
                 if guests else [])
    if guests:
        c.write("teilnehmerliste.pdf", "participant_list", [
            Paragraph("Teilnehmerliste Projekttreffen ROBUST, 14.10.2027, Raum D 2.11", ms.H1), Spacer(1, 8),
            ms.grid([[Paragraph(x, P) for x in row] for row in [
                ["Name", "Einrichtung", "Gast / intern"], ["Dr. Ewa Malinowska", "Fraunhofer IWU Chemnitz", "Gast"],
                ["Jeroen Smits", "Smits Automation B.V.", "Gast"], ["Katrin Oehlschläger", "Bosch Rexroth AG", "Gast"],
                ["Henrike Lammers-Abebe", "Universität Wernstadt", "intern"], ["Prof. Dr. Theo Brakel", "Universität Wernstadt", "intern"]]],
                [5.5 * cm, 6.5 * cm, 3.0 * cm], header=True)])
    exp_trail(c, "Mo 18.10.2027 13:15", why)


def c2_direct_award(number, label, qty, why):
    """Built on task-2-procurement-spot-check/beschaffungsantrag-02; only one quantity differs."""
    c = Case("coverage", "proc", number, label, "C2", "P01", SRC_CATER,
             f"Paar zu proc-02: Direktauftrag mit einem Angebot, {qty} Messverstärker", why,
             who="Ole Brinkhaus-Mensah", mailbox="o.brinkhaus@uni-wernstadt.de")
    fg = "Fachgebiet Mechatronik"
    items = [("Messverstärker 4 Kanäle, Brückenschaltung", qty, 236.00), ("Kalibrierwiderstand-Set", 1, 54.00)]
    (_, _, _, net, gross), = write_offers(c, fg, [("Messtechnik Ruland e.K.", ["Am Wasserturm 6", "66111 Saarbrücken"],
                                                               "MR-A-2207", "04.05.2027", items)])
    lines = "<br/>".join(f"{q} &#215; {d}, je {e(u)} netto" for d, q, u in items)
    mail(c, "email-beschaffungsantrag.pdf", kassel=False, subject="Direktauftrag Messverstärker FG Mechatronik",
         sender=f"Ole Brinkhaus-Mensah &lt;{c.mailbox}&gt;", sent="Mo 10.05.2027 09:41", to="beschaffung@uni-wernstadt.de",
         cc="Prof. Dr. Katharina Ewald &lt;katharina.ewald@uni-wernstadt.de&gt;", doc_type="application",
         body=["Sehr geehrte Damen und Herren,", "für den Prüfstand bitte ich um Bestellung bei Messtechnik Ruland e.K. "
               "gemäß beiliegendem Angebot MR-A-2207 vom 04.05.2027:", lines,
               f"Summe {e(net)} netto, {e(gross)} brutto. Ich habe nur dieses eine Angebot eingeholt (Direktvergabe).",
               "Kostenstelle 71 4655, Auftrag 2140330. Frau Prof. Ewald ist in Kopie und hat die Bestellung beauftragt.",
               "Mit freundlichen Grüßen<br/>Ole Brinkhaus-Mensah"])
    proc_trail(c, "Mi 12.05.2027 10:05", why)


def c2_webshop(number, label, monitors, why):
    """Built on beschaffungsantrag-03; only the ninth position differs."""
    c = Case("coverage", "proc", number, label, "C2", "P02", SRC_FRAME,
             "Paar zu proc-03: Sammelbestellung aus Webshops, Position 9 " + ("zwei Monitore" if monitors else "zwei Labortischleuchten"),
             why, who="Svenja Kröger-Mbeki", mailbox="svenja.kroeger@uni-wernstadt.de")
    rows = [("Steckbrett-Set, 400 Kontakte", 8, 6.90, "https://www.bauteilkiste-sauerland.de/a/SB400"),
            ("Jumper-Kabel-Set, 120-teilig", 5, 5.49, "https://www.bauteilkiste-sauerland.de/a/JK120"),
            ("Entwicklungsboard 32 Bit mit Funkmodul", 10, 12.90, "https://www.bauteilkiste-sauerland.de/a/EB32W"),
            ("Digitalmultimeter Auto-Range", 4, 34.90, "https://shop.messbar-lausitz.de/p/22014"),
            ("USB-Oszilloskop 2 Kanäle", 1, 119.00, "https://shop.messbar-lausitz.de/p/22977"),
            ("Lötdraht bleifrei 0,8 mm, 250 g", 4, 13.50, "https://shop.messbar-lausitz.de/p/30120"),
            ("ESD-Armband mit Kabel", 6, 7.95, "https://shop.messbar-lausitz.de/p/30401"),
            ("Pinzetten-Set antistatisch", 3, 11.40, "https://www.bauteilkiste-sauerland.de/a/PZ6"),
            ("Monitor 24 Zoll, Full HD, höhenverstellbar", 2, 149.00, "https://www.displayshop-erzgebirge.de/produkt/24-fhd-hv-1102")
            if monitors else ("LED-Labortischleuchte mit Lupe", 2, 89.00, "https://shop.messbar-lausitz.de/p/40770")]
    total = round(sum(q * u for _, q, u, _ in rows), 2)
    body = ["Liebes Team der Zentralen Beschaffung,", "für das Praktikumslabor des Fachgebiets Digitaltechnik bitte ich um die "
            "folgende Sammelbestellung (Preise laut Webshop inkl. MwSt.):"]
    body += [f"{i}. {q} &#215; {d}, je {e(u)} brutto = {e(round(q * u, 2))}<br/>{url}" for i, (d, q, u, url) in enumerate(rows, 1)]
    body += [f"Gesamtsumme: {e(total)} brutto. Kostenstelle 71 4540, Auftrag 2140219.", "Viele Grüße<br/>Svenja Kröger-Mbeki<br/>"
             "Sekretariat Fachgebiet Digitaltechnik"]
    mail(c, "email-beschaffungsantrag.pdf", kassel=False, subject="Sammelbestellung Praktikumslabor Digitaltechnik",
         sender=f"Svenja Kröger-Mbeki &lt;{c.mailbox}&gt;", sent="Di 13.04.2027 10:02", to="beschaffung@uni-wernstadt.de",
         cc="Prof. Dr. Bastian Oldewurtel &lt;bastian.oldewurtel@uni-wernstadt.de&gt;", doc_type="application", body=body)
    proc_trail(c, "Do 15.04.2027 11:20", why)


def c2_sum(number, label, stated, why):
    """Built on beschaffungsantrag-04; only the stated net total of the request differs."""
    c = Case("coverage", "proc", number, label, "C2", "P04", SRC_PROC,
             "Paar zu proc-04: drei Angebote, Summe netto im Antrag " + ("weicht von den Positionen ab" if stated else "stimmt"),
             why, who="Dr. Rasmus Feldhaus", mailbox="r.feldhaus@uni-wernstadt.de")
    fg = "Fachgebiet Hochfrequenztechnik"
    a = [("Vektorieller Netzwerkanalysator 2 Tore, 6 GHz", 1, 2580.00), ("Kalibrierkit SMA", 1, 380.00)]
    bids = write_offers(c, fg, [
        ("HF-Messgeräte Lindner GmbH", ["Siemensring 4", "47877 Willich"], "HL-270611", "11.06.2027", a),
        ("Radiowave Instruments KG", ["Am Funkturm 2", "14055 Berlin"], "RI-A-27-302", "14.06.2027",
         [(a[0][0], 1, 2690.00), (a[1][0], 1, 395.00)]),
        ("Mikrowellentechnik Saalfeld", ["Bahnhofstraße 70", "07318 Saalfeld"], "MS 27/0418", "15.06.2027",
         [(a[0][0], 1, 2745.00), (a[1][0], 1, 410.00)])])
    proc_form(c, number="ZB-2027-0547", date="18.06.2027", fachgebiet=fg, phone="0561 7390-4760",
              kostenstelle="71 4760 / Auftrag 2140377", holder="Prof. Dr. Edda Hinrichsen", category="Anlage", framework=False,
              procedure="Preisvergleich, drei schriftliche Angebote", offers=3, supplier="HF-Messgeräte Lindner GmbH (Angebot HL-270611)",
              items=a, stated_net=stated, begruendung="Netzwerkanalysator für das Antennenlabor; günstigstes der drei Angebote.")
    c.write("vergabevermerk.pdf", "award_note", ms.award_note(
        number="V-27-0412", antrag="ZB-2027-0547", subject="Vektorieller Netzwerkanalysator mit Kalibrierkit",
        bids=[(v, n, d, net, gross, rank) for rank, (v, n, d, net, gross) in enumerate(bids, 1)],
        winner=f"HF-Messgeräte Lindner GmbH, {ms.eur(bids[0][3])} netto", reason="Alle Geräte erfüllen das Leistungsverzeichnis; "
        "das Angebot der HF-Messgeräte Lindner GmbH ist das wirtschaftlichste.", date="19.06.2027", clerk="Jasper Wollenweber"))
    proc_trail(c, "Di 22.06.2027 09:55", why)


def c2_exp_proc():
    c2_receipt(205, "angenommen", True, "Kassenbon ohne Artikelbezeichnung, aber mit Stichwort zum Verwendungszweck, wie vorgesehen.")
    c2_receipt(206, "abgelehnt", False, "Der Kassenbon weist nur Artikelnummern aus; das erforderliche Stichwort zum Verwendungszweck fehlt.")
    c2_proforma(207, "abgelehnt", False, "Eingereicht ist nur eine Pro-forma-Rechnung; sie belegt weder Lieferung noch endgültigen Betrag.")
    c2_proforma(208, "angenommen", True, "Endgültige Rechnung an das Fachgebiet mit Artikeln, bezahlt.")
    c2_tea(209, "abgelehnt", False, "Kaffee, Tee, Gebäck und Wasser für die Teeküche ohne externe Gäste sind nicht erstattungsfähig.")
    c2_tea(210, "angenommen", True, "Übliche Gesten der Höflichkeit gegenüber externen Gästen, Teilnehmerliste liegt bei: Betriebsaufwand.")
    c2_direct_award(211, "angenommen", 2, "Auftragswert 526,00 € netto unter 1.000 €: Direktvergabe mit einem Angebot zulässig.")
    c2_direct_award(212, "abgelehnt", 5, "Auftragswert 1.234,00 € netto ab 1.000 €: drei Angebote sind erforderlich, es liegt nur eines vor.")
    c2_webshop(213, "abgelehnt", True, "Position 9 sind Monitore aus einem Webshop; Monitore sind Rahmenvertragsprodukte und "
               "ausschließlich beim Rahmenvertragspartner zu bestellen, unabhängig vom Betrag.")
    c2_webshop(214, "angenommen", False, "Sammelbestellung unter 1.000 € ohne Rahmenvertragsprodukte; Direktvergabe zulässig.")
    c2_sum(215, "abgelehnt", 4140.00, "Die Positionen ergeben 2.960,00 € netto, der Antrag nennt 4.140,00 € netto; unklar, welcher "
           "Betrag beauftragt wird.")
    c2_sum(216, "angenommen", None, "Drei Angebote, günstigstes gewählt, Antrag, Angebot und Vergabevermerk stimmen überein.")


# =========================================================================== #
#       C3  file complexity: threads, contradictions, partial invoices        #
# =========================================================================== #

def synth_trip(c, *, rnr, pnr, fg, changed, allgemein, verlauf, kosten, finanzierung, begruendung, antragsdatum, hinweis=None):
    c.write("antrag-dienstreisegenehmigung.pdf", "trip_form", ms.trip_form(
        reisenummer=rnr, name=c.who, fachgebiet=fg, personalnummer=pnr, geaendert=changed, allgemein=allgemein,
        verlauf=verlauf, kosten=kosten, finanzierung=finanzierung, begruendung=begruendung, antragsdatum=antragsdatum,
        hinweis=hinweis))


def thread(c, name, *, subject, messages, doc_type="correspondence", kassel=True):
    """An e-mail print-out whose newest message quotes the earlier ones; messages oldest first: (from, sent, to, body)."""
    *older, (sender, sent, to, body) = messages
    quoted = [{"from": f, "sent": s, "to": t, "subject": subject, "body": b} for f, s, t, b in reversed(older)]
    c.write(name, doc_type, ms.email(mailbox=c.mailbox, url=OWA_KASSEL + "C" if kassel else OWA_WERN, subject=f"AW: {subject}",
                                     sender=sender, sent=sent, to=to, body=body, quoted=quoted))


RKS = "Reisekostenstelle, Universität Kassel &lt;dienstreisegenehmigung@uni-kassel.de&gt;"


def c3_trip():
    # 301 abgelehnt: form says 3 nights, hotel booking 4 nights
    c = Case("coverage", "trip", 301, "abgelehnt", "C3", "T02", SRC_TRIP,
             "Formular 3 Nächte und Reisebeginn 14.03., Hotelbuchung 4 Nächte ab 13.03.",
             "Antrag und Hotelbuchung widersprechen sich (3 gegen 4 Nächte, Anreise 14.03. gegen 13.03.); Reiseverlauf und Kosten stehen nicht fest.",
             who="Dr. Viktor Nakamura-Bach", mailbox="v.nakamura@uni-kassel.de")
    synth_trip(c, rnr="3381042301", pnr="051186", fg="Fachgebiet Werkstoffe des Bauwesens", changed="11. Januar 2027",
               allgemein=[("Reiseziel:", "Aachen"), ("Anlass:", "Aachener Baustofftage 2027"), ("Grund der Reise:", "Vortrag"),
                          ("Reise ins Ausland:", "[ ] ja &#160; [X] nein"), ("Verkehrsmittel:", "Bahn, 2. Klasse"),
                          ("Datum der Antragstellung:", "11.01.2027")],
               verlauf=[("Start:", "Sonntag, 14. März 2027, 15:20 Uhr"), ("Ende:", "Mittwoch, 17. März 2027, 19:45 Uhr"),
                        ("Beginn Dienstgeschäft:", "15.03.2027, 09:00 Uhr"), ("Ende Dienstgeschäft:", "17.03.2027, 13:00 Uhr"),
                        ("priv. Aufenthalt:", "keiner"), ("Arbeitstage:", "3")],
               kosten=[("Tagungsgebühr", "1", 310.00), ("Bahn Kassel–Aachen, Hin- und Rückfahrt", "1", 128.00),
                       ("Übernachtung, 3 Nächte à 76,00 €", "3", 228.00)],
               finanzierung="Fachgebietsbudget, Kostenstelle 4520-03", begruendung="Vortrag; Programm liegt bei.",
               antragsdatum="11.01.2027")
    hotel(c, vendor="Hotel Lousberg", addr=["Kupferstraße 5", "52070 Aachen"], nights=4, rate=76.00,
          period="Anreise 13.03.2027, Abreise 17.03.2027", booked=date(2027, 1, 10))
    trip_trail(c, "3381042301", "Do 14.01.2027 10:20", "Laut Antrag beginnt die Reise am 14.03.2027 mit drei Übernachtungen, "
               "die beigefügte Hotelbuchung umfasst aber vier Nächte ab dem 13.03.2027. Reiseverlauf und Übernachtungskosten "
               "sind damit widersprüchlich.")

    # 302 angenommen / 303 abgelehnt: query about the missing programme, answered with / without evidence
    for number, label, answered in ((302, "angenommen", True), (303, "abgelehnt", False)):
        why = ("Auf die Rückfrage wurden Einladung und Programm nachgereicht; das dienstliche Interesse ist belegt." if answered else
               "Auf die Rückfrage wurde kein Programm und keine Einladung nachgereicht; das dienstliche Interesse ist nicht belegt.")
        c = Case("coverage", "trip", number, label, "C3", "T12", SRC_TRIP,
                 "Rückfrage der Reisekostenstelle nach Programm; Antwort " + ("mit" if answered else "ohne") + " Nachweis", why,
                 who="Dr. Amelie Grothe-Yilmaz", mailbox="a.grothe@uni-kassel.de")
        synth_trip(c, rnr=f"338104{number}", pnr="048830", fg="Fachgebiet Grünlandökologie", changed="2. Februar 2027",
                   allgemein=[("Reiseziel:", "Göttingen"), ("Anlass:", "Arbeitstreffen Forschungsverbund"),
                              ("Grund der Reise:", "Abstimmung Feldversuche"), ("Reise ins Ausland:", "[ ] ja &#160; [X] nein"),
                              ("Verkehrsmittel:", "Bahn, 2. Klasse"), ("Datum der Antragstellung:", "02.02.2027")],
                   verlauf=[("Start:", "Dienstag, 16. März 2027, 07:40 Uhr"), ("Ende:", "Dienstag, 16. März 2027, 18:30 Uhr"),
                            ("Beginn Dienstgeschäft:", "16.03.2027, 10:00 Uhr"), ("Ende Dienstgeschäft:", "16.03.2027, 16:00 Uhr"),
                            ("priv. Aufenthalt:", "keiner"), ("Arbeitstage:", "1")],
                   kosten=[("Bahn Kassel–Göttingen, Hin- und Rückfahrt", "1", 38.00), ("Tagegeld", "1", 14.00)],
                   finanzierung="Drittmittelprojekt GrasKlima, Kostenstelle 6633-02", begruendung="Arbeitstreffen.",
                   antragsdatum="02.02.2027")
        reply = (["Sehr geehrte Frau Delfs,", "anbei die Einladung des Verbundkoordinators mit der Tagesordnung des Treffens "
                  "am 16.03.2027 in Göttingen (Agrarwissenschaftliche Fakultät, Raum 1.104, 10&#8211;16 Uhr).",
                  "Viele Grüße<br/>Amelie Grothe-Yilmaz"] if answered else
                 ["Sehr geehrte Frau Delfs,", "ein Programm gibt es für das Treffen nicht, und eine schriftliche Einladung habe "
                  "ich nicht bekommen; wir haben das Treffen telefonisch vereinbart. Ich bitte trotzdem um Genehmigung.",
                  "Viele Grüße<br/>Amelie Grothe-Yilmaz"])
        thread(c, "email-rueckfrage-programm.pdf", subject="Ihr Dienstreiseantrag " + f"338104{number}" + " – Unterlagen",
               messages=[(RKS, "Fr 05.02.2027 09:12", f"{c.who} &lt;{c.mailbox}&gt;",
                          ["Sehr geehrte Frau Dr. Grothe-Yilmaz,", "Ihrem Antrag liegen keine Unterlagen bei, aus denen das "
                           "dienstliche Interesse sowie Ort und Dauer hervorgehen. Bitte reichen Sie Einladung oder Programm nach.",
                           "Mit freundlichen Grüßen<br/>i. A. Corinna Delfs"]),
                         (f"{c.who} &lt;{c.mailbox}&gt;", "Mo 08.02.2027 14:05", RKS, reply)])
        if answered:
            mail(c, "einladung-verbundtreffen.pdf", subject="Einladung Verbundtreffen GrasKlima, 16.03.2027",
                 sender="Prof. Dr. Henning Obermeyer &lt;h.obermeyer@agrar.uni-goettingen.example&gt;", sent="Mi 13.01.2027 11:00",
                 body=["Liebe Verbundpartner,", "hiermit lade ich zum Arbeitstreffen am 16. März 2027, 10&#8211;16 Uhr, in "
                       "Göttingen ein. Tagesordnung: 1. Stand der Feldversuche, 2. Messkampagne Sommer 2027, 3. Zwischenbericht.",
                       "Herzliche Grüße<br/>Henning Obermeyer"])
        trip_trail(c, f"338104{number}", "Mi 10.02.2027 08:44", why)

    # 304 angenommen / 305 abgelehnt: private stay of more than 5 working days, costs separated or not
    for number, label, separated in ((304, "angenommen", True), (305, "abgelehnt", False)):
        why = ("Privataufenthalt von 8 Arbeitstagen; beantragt sind nur die dienstlich notwendigen Kosten, der Preisvergleich "
               "für den Rückflug direkt nach dem Dienstgeschäft liegt bei." if separated else
               "Privataufenthalt von 8 Arbeitstagen; beantragt sind auch die Hotelnächte des Urlaubs und der Rückflug nach dem "
               "Urlaub ohne Preisvergleich, der Universität entstehen Mehrkosten.")
        c = Case("coverage", "trip", number, label, "C3", "T15", SRC_TRIP,
                 "Konferenz in Kyoto plus 8 Arbeitstage Urlaub, private Kosten " + ("getrennt" if separated else "nicht getrennt"),
                 why, who="Prof. Dr. Gerrit Imhoff-Sato", mailbox="g.imhoff@uni-kassel.de")
        kosten = [("Flug Frankfurt–Osaka, Hinflug", "1", 520.00),
                  ("Rückflug Osaka–Frankfurt " + ("zum Vergleichstarif 22.10.2027" if separated else "am 03.11.2027"), "1",
                   505.00 if separated else 590.00),
                  ("Konferenzgebühr", "1", 610.00),
                  ("Hotel Kyoto, 3 Nächte à 118,00 € (Konferenztarif)" if separated else "Hotel Kyoto, 13 Nächte à 118,00 €",
                   "3" if separated else "13", 354.00 if separated else 1534.00)]
        synth_trip(c, rnr=f"338104{number}", pnr="029941", fg="Fachgebiet Robotik und Autonome Systeme", changed="12. Juli 2027",
                   allgemein=[("Reiseziel:", "Kyoto, JAPAN"), ("Anlass:", "IEEE/RSJ IROS 2027"), ("Grund der Reise:", "Keynote"),
                              ("Reise ins Ausland:", "[X] ja &#160; [ ] nein"), ("Verkehrsmittel:", "Flug (Economy)"),
                              ("Datum der Antragstellung:", "12.07.2027")],
                   verlauf=[("Start:", "Montag, 18. Oktober 2027, 11:05 Uhr"), ("Ende:", "Mittwoch, 3. November 2027, 17:30 Uhr"),
                            ("Beginn Dienstgeschäft:", "19.10.2027, 09:00 Uhr"), ("Ende Dienstgeschäft:", "21.10.2027, 18:00 Uhr"),
                            ("priv. Aufenthalt:", "22.10.–03.11.2027 (8 Arbeitstage, Urlaub beantragt)"), ("Arbeitstage:", "4 dienstlich")],
                   kosten=kosten, finanzierung="Professurbudget, Kostenstelle 4680-00", begruendung="Eingeladene Keynote.",
                   antragsdatum="12.07.2027",
                   hinweis=("Private Nächte (22.10.–03.11.) und Mehrpreis des späteren Rückflugs (85,00 €) trage ich selbst; "
                            "Preisvergleich des Reisebüros anbei.") if separated else None)
        if separated:
            vendor_doc(c, "preisvergleich-rueckflug.pdf", "price_comparison", vendor="Reisebüro Campus Kassel GmbH",
                       vendor_addr=["Königsplatz 47", "34117 Kassel"], recipient=["Universität Kassel", f"z. Hd. {c.who}"],
                       refs=[("Datum:", "09.07.2027")], heading="Preisvergleich Rückflug",
                       items=[["Rückflug KIX&#8211;FRA am 22.10.2027 (direkt nach Dienstgeschäft)", "1", "&#8212;", e(505), e(505)],
                              ["Rückflug KIX&#8211;FRA am 03.11.2027 (gebucht, privat verlängert)", "1", "&#8212;", e(590), e(590)]],
                       sums=[("Mehrpreis privat", e(85))])
        mail(c, "einladung-keynote.pdf", subject="IROS 2027 &#8211; Keynote invitation",
             sender="IROS 2027 General Chairs &lt;chairs@iros2027.example&gt;", sent="Mi 02.06.2027 03:12",
             body=["Dear Professor Imhoff-Sato,", "we are honoured to invite you to give a keynote at IROS 2027 in Kyoto on 20 "
                   "October 2027. Registration is waived for keynote speakers except for the workshop day fee (610 EUR).",
                   "Sincerely,<br/>General Chairs"])
        trip_trail(c, f"338104{number}", "Fr 16.07.2027 11:00", why)


def c3_expense():
    # 306 abgelehnt / 307 angenommen: partial cancellation with credit note, claim = total or balance
    for number, label, claim in ((306, "abgelehnt", 186.40), (307, "angenommen", 139.80)):
        why = (f"Geltend gemacht sind {ms.eur(claim)}, nach Abzug der Gutschrift über 46,60 € beträgt der getragene Saldo 139,80 €."
               if label == "abgelehnt" else "Geltend gemacht ist genau der Saldo aus Rechnung und Gutschrift (139,80 €).")
        c = Case("coverage", "exp", number, label, "C3", "E06", SRC_FIN,
                 f"Rechnung 186,40 € und Gutschrift 46,60 € für einen Rückläufer, geltend gemacht {ms.eur(claim)}", why,
                 who="Dr. Mathis Oyelaran-Kluge", mailbox="m.oyelaran@uni-wernstadt.de")
        rows = [("Akku-Lötkolben 8 W", 2, 46.60, 0.19), ("Lötspitzen-Set", 2, 19.90, 0.19), ("Platinenhalter", 1, 53.00, 0.19)]
        shop_invoice(c, "rechnung.pdf", vendor="Elektronikversand Haverkamp", addr=["Gildestraße 6", "49477 Ibbenbüren"],
                     recipient=wern("Lehrstuhl für Elektronische Bauelemente", c.who), number="EH-27-77104", day=date(2027, 5, 10),
                     rows=rows, payment="Kreditkarte, bezahlt", notes=[f"Zur Erstattung: {ms.eur(claim)} (handschriftlich, M. O.-K.)"])
        items, sums, _ = retail([("Rückgabe: Akku-Lötkolben 8 W", 1, 46.60, 0.19)])
        vendor_doc(c, "gutschrift.pdf", "credit_note", vendor="Elektronikversand Haverkamp", vendor_addr=["Gildestraße 6", "49477 Ibbenbüren"],
                   recipient=wern("Lehrstuhl für Elektronische Bauelemente", c.who),
                   refs=[("Gutschrift Nr.", "GS-27-0418"), ("zu Rechnung", "EH-27-77104"), ("Datum", "21.05.2027")],
                   heading="Gutschrift", items=items, sums=sums, notes=["Der Betrag wird auf die Kreditkarte zurückgebucht."])
        exp_trail(c, "Do 03.06.2027 10:00", why)

    # 308 angenommen: query (only pro-forma) answered with the final invoice
    c = Case("coverage", "exp", 308, "angenommen", "C3", "E02", SRC_FIN,
             "Rückfrage der Finanzbuchhaltung zur Pro-forma-Rechnung, endgültige Rechnung nachgereicht",
             "Die zunächst nur vorliegende Pro-forma-Rechnung ist durch die nachgereichte endgültige Rechnung ersetzt.",
             who="Paulina Hagemeister", mailbox="p.hagemeister@uni-wernstadt.de")
    rows = [("Pufferlösung pH 7, 500 ml", 4, 12.30, 0.19), ("Messkolben 100 ml, Klasse A", 6, 9.85, 0.19)]
    shop_invoice(c, "proforma-laborhandel.pdf", vendor="Laborhandel Ostfriesland GmbH", addr=["Am Delft 12", "26721 Emden"],
                 recipient=wern("Fachgebiet Analytische Chemie", c.who), number="PF-27-2207", day=date(2027, 8, 2), rows=rows,
                 heading="Pro-forma-Rechnung", payment="Vorkasse, bezahlt 03.08.2027", doc_type="proforma_invoice",
                 notes=["Dieses Dokument ist keine Rechnung. Die Rechnung erhalten Sie mit der Lieferung."])
    thread(c, "email-rueckfrage-finanzbuchhaltung.pdf", kassel=False, subject="Erstattung Laborbedarf PF-27-2207",
           messages=[("Finanzbuchhaltung &lt;kostenerstattung@uni-wernstadt.de&gt;", "Di 10.08.2027 09:30", f"{c.who} &lt;{c.mailbox}&gt;",
                      ["Sehr geehrte Frau Hagemeister,", "eingereicht ist nur eine Pro-forma-Rechnung. Bitte reichen Sie die "
                       "Rechnung nach, die mit der Lieferung kommt.", "Mit freundlichen Grüßen<br/>Finanzbuchhaltung"]),
                     (f"{c.who} &lt;{c.mailbox}&gt;", "Do 12.08.2027 15:22", "Finanzbuchhaltung &lt;kostenerstattung@uni-wernstadt.de&gt;",
                      ["Sehr geehrte Damen und Herren,", "die Ware ist am 11.08. gekommen, anbei die Rechnung RE-27-80915.",
                       "Viele Grüße<br/>Paulina Hagemeister"])])
    shop_invoice(c, "rechnung-laborhandel.pdf", vendor="Laborhandel Ostfriesland GmbH", addr=["Am Delft 12", "26721 Emden"],
                 recipient=wern("Fachgebiet Analytische Chemie", c.who), number="RE-27-80915", day=date(2027, 8, 11), rows=rows,
                 payment="bezahlt per Vorkasse am 03.08.2027", notes=["Bezug: Pro-forma-Rechnung PF-27-2207. Lieferung am 11.08.2027."])
    exp_trail(c, "Mo 16.08.2027 08:50", "Die endgültige Rechnung liegt jetzt vor.")

    # 309 abgelehnt / 310 angenommen: business lunch with guests, without / with the required evidence
    for number, label, complete in ((309, "abgelehnt", False), (310, "angenommen", True)):
        why = ("Bewirtungsbeleg ohne Anlass, ohne Teilnehmerliste und nicht auf die Universität ausgestellt; die Nachweise der "
               "Bewirtungskostenrichtlinie fehlen." if not complete else
               "Bewirtung von Industriepartnern im Drittmittelprojekt, Anlass und Teilnehmerliste liegen bei, Beleg an die "
               "Universität, unter 60 € je Person.")
        c = Case("coverage", "exp", number, label, "C3", "E15", SRC_FIN,
                 "Arbeitsessen mit 2 Industriepartnern, " + ("Nachweise vollständig" if complete else "ohne Anlass und Teilnehmerliste"),
                 why, who="Dr. Elias Brandstätter", mailbox="e.brandstaetter@uni-wernstadt.de")
        recipient = wern("Lehrstuhl für Verfahrenstechnik", c.who) if complete else [c.who, "Gartenweg 14", "35287 Amöneburg"]
        shop_invoice(c, "bewirtungsbeleg.pdf", vendor="Restaurant Lahnterrasse", addr=["Uferstraße 2", "35291 Wernstadt",
                                                                                      "St.-Nr. 031/244/50918"],
                     recipient=recipient, number="RG 2027-1188", day=date(2027, 6, 23),
                     rows=[("Mittagsmenü", 4, 24.50, 0.19), ("Mineralwasser 0,75 l", 2, 6.90, 0.19), ("Kaffee", 4, 2.80, 0.19)],
                     payment="EC-Karte, bezahlt", heading="Bewirtungsbeleg",
                     notes=["Tisch 12, 23.06.2027, 12:40 Uhr"] + (["Anlass: Projekttreffen KatProzess mit Industriepartnern "
                                                                   "(Drittmittel, Auftrag 2140910)"] if complete else []))
        if complete:
            c.write("teilnehmerliste.pdf", "participant_list", [
                Paragraph("Bewirtung am 23.06.2027 &#8211; Teilnehmerliste", ms.H1), Spacer(1, 6),
                Paragraph("Anlass: Projekttreffen KatProzess (Drittmittelprojekt, Auftrag 2140910); Einladung vom 01.06.2027 anbei.", P),
                Spacer(1, 8),
                ms.grid([[Paragraph(x, P) for x in row] for row in [
                    ["Name", "Einrichtung", "Gast / intern"], ["Dr. Helga Pietsch", "Evonik Operations GmbH", "Gast"],
                    ["Marco Lentini", "BASF SE", "Gast"], ["Dr. Elias Brandstätter", "Universität Wernstadt", "intern"],
                    ["Prof. Dr. Ute Kaltwasser", "Universität Wernstadt", "intern"]]], [5.5 * cm, 6.5 * cm, 3.0 * cm], header=True),
                Spacer(1, 14), Paragraph("Bewirtende Person: Dr. Elias Brandstätter (unterschrieben)", P)])
        exp_trail(c, "Fr 02.07.2027 09:15", why)


def c3_procurement():
    fg = "Fachgebiet Fluidsystemtechnik"
    # 311 angenommen / 312 abgelehnt: down payment plus final invoice equal to / above the offer
    for number, label, extra in ((311, "angenommen", None), (312, "abgelehnt", ("Expresszuschlag Lieferung", 1, 346.00))):
        why = ("Anzahlung und Schlussrechnung ergeben zusammen genau die Angebotssumme." if extra is None else
               "Die Schlussrechnung enthält einen nicht beauftragten Expresszuschlag; Anzahlung und Schlussrechnung übersteigen "
               "das beauftragte Angebot.")
        c = Case("coverage", "proc", number, label, "C3", "P07", SRC_PROC,
                 "Anzahlung 30 % und Schlussrechnung zum beauftragten Angebot" + ("" if extra is None else ", Schlussrechnung mit Expresszuschlag"),
                 why, who="Dr. Friederike Ommen", mailbox="f.ommen@uni-wernstadt.de")
        items = [("Hydraulikaggregat 7,5 kW, 160 bar", 1, 4200.00), ("Proportionalventil mit Ansteuerelektronik", 2, 690.00)]
        bids = write_offers(c, fg, [
            ("Hydrotechnik Saalbach GmbH", ["Talstraße 33", "57250 Netphen"], "HS-27-1931", "01.03.2027", items),
            ("Fluidpower Keller KG", ["Am Ring 1", "86381 Krumbach"], "FK-27-0228", "02.03.2027", [(items[0][0], 1, 4390.00), (items[1][0], 2, 705.00)]),
            ("Ölhydraulik Brunsen", ["Hafenstraße 9", "26789 Leer"], "OB-0311", "03.03.2027", [(items[0][0], 1, 4475.00), (items[1][0], 2, 720.00)])])
        net, gross = proc_form(c, number=f"ZB-2027-0{number}", date="05.03.2027", fachgebiet=fg, phone="0561 7390-4811",
                               kostenstelle="71 4811 / Auftrag 2140702", holder="Prof. Dr. Joachim Venhaus", category="Anlage",
                               framework=False, procedure="Preisvergleich, drei schriftliche Angebote", offers=3,
                               supplier="Hydrotechnik Saalbach GmbH (Angebot HS-27-1931)", items=items,
                               begruendung="Aggregat für den Ventilprüfstand; günstigstes der drei Angebote. Anzahlung 30 % laut Angebot.")
        down = round(gross * 0.3, 2)
        st, _ = ms.invoice(vendor="Hydrotechnik Saalbach GmbH", vendor_lines=["Talstraße 33", "57250 Netphen"],
                           recipient=ms.recip(fg, c.who), refs=[("Rechnung Nr.", "HS-AR-27-0410"), ("Datum:", "15.03.2027")],
                           items=[("Anzahlung 30 % auf Angebot HS-27-1931", 1, round(down / 1.19, 2))], heading="Anzahlungsrechnung")
        c.write("rechnung-anzahlung.pdf", "invoice", st)
        rest = [(f"Lieferung gemäß Angebot HS-27-1931: {d}", q, u) for d, q, u in items] + ([extra] if extra else [])
        rest.append(("abzgl. Anzahlung (Rechnung HS-AR-27-0410)", 1, -round(down / 1.19, 2)))
        st, _ = ms.invoice(vendor="Hydrotechnik Saalbach GmbH", vendor_lines=["Talstraße 33", "57250 Netphen"],
                           recipient=ms.recip(fg, c.who), refs=[("Rechnung Nr.", "HS-SR-27-0688"), ("Datum:", "28.04.2027")],
                           items=rest, heading="Schlussrechnung")
        c.write("rechnung-schluss.pdf", "invoice", st + [Paragraph("sachlich richtig, F. Ommen", HAND)])
        proc_trail(c, "Mo 03.05.2027 10:30", why)

    # 313 angenommen / 314 abgelehnt: query about missing third offer, answered with / without it
    fg = "Fachgebiet Umweltverfahrenstechnik"
    for number, label, third in ((313, "angenommen", True), (314, "abgelehnt", False)):
        why = ("Auf die Rückfrage wurde das dritte Angebot nachgereicht; das gewählte ist das günstigste." if third else
               "Auftragswert 1.640 € netto, nur zwei Angebote; auf die Rückfrage wurde kein drittes Angebot und keine "
               "Begründung (z. B. Alleinstellung) nachgereicht.")
        c = Case("coverage", "proc", number, label, "C3", "P01", SRC_PROC,
                 "Rückfrage Einkauf: nur zwei Angebote bei 1.640 € netto; drittes Angebot " + ("nachgereicht" if third else "nicht nachgereicht"),
                 why, who="Dr. Yusuf Bertram-Klee", mailbox="y.bertram@uni-wernstadt.de")
        pump = [("Peristaltikpumpe 4 Kanäle, drehzahlgeregelt", 2, 820.00)]
        quotes = [("Labortechnik Wiesmoor GmbH", ["Hauptstraße 4", "26639 Wiesmoor"], "LW-27-0912", "06.09.2027", pump),
                  ("Fluidlab Dörnberg", ["Am Habichtswald 9", "34289 Zierenberg"], "FD-A-27-77", "07.09.2027", [(pump[0][0], 2, 865.00)])]
        if third:
            quotes.append(("Pumpenhaus Ritter KG", ["Ritterstraße 20", "95444 Bayreuth"], "PR-27-3310", "16.09.2027", [(pump[0][0], 2, 899.00)]))
        write_offers(c, fg, quotes)
        proc_form(c, number=f"ZB-2027-0{number}", date="08.09.2027", fachgebiet=fg, phone="0561 7390-4830",
                  kostenstelle="71 4830 / Auftrag 2140733", holder="Prof. Dr. Sabine Wohlrab", category="Anlage", framework=False,
                  procedure="Preisvergleich", offers=2, supplier="Labortechnik Wiesmoor GmbH (Angebot LW-27-0912)", items=pump,
                  begruendung="Pumpen für die Säulenversuche; günstigstes Angebot.")
        thread(c, "email-rueckfrage-einkauf.pdf", kassel=False, subject="Beschaffungsantrag " + f"ZB-2027-0{number}" + " – Angebote",
               messages=[("Zentrale Beschaffung &lt;beschaffung@uni-wernstadt.de&gt;", "Fr 10.09.2027 08:30", f"{c.who} &lt;{c.mailbox}&gt;",
                          ["Sehr geehrter Herr Dr. Bertram-Klee,", "bei einem Auftragswert von 1.640,00 &#8364; netto sind "
                           "grundsätzlich drei Angebote einzuholen; Ihrem Antrag liegen zwei bei. Bitte reichen Sie ein drittes "
                           "Angebot nach.", "Mit freundlichen Grüßen<br/>Zentrale Beschaffung"]),
                         (f"{c.who} &lt;{c.mailbox}&gt;", "Do 16.09.2027 17:02", "Zentrale Beschaffung &lt;beschaffung@uni-wernstadt.de&gt;",
                          ["Sehr geehrte Damen und Herren,", "anbei das dritte Angebot der Pumpenhaus Ritter KG über 1.798,00 "
                           "&#8364; netto; es bleibt bei Labortechnik Wiesmoor.", "Viele Grüße<br/>Yusuf Bertram-Klee"] if third else
                          ["Sehr geehrte Damen und Herren,", "ein drittes Angebot war leider nicht zu bekommen. Ich bitte, die "
                           "Bestellung trotzdem auszulösen, die Pumpen werden dringend gebraucht.", "Viele Grüße<br/>Yusuf Bertram-Klee"])])
        proc_trail(c, "Mo 20.09.2027 09:10", why)

    # 315 abgelehnt: award to the second-cheapest without reason and request not signed
    fg = "Fachgebiet Thermodynamik"
    c = Case("coverage", "proc", 315, "abgelehnt", "C3", "P06+P03", SRC_PROC,
             "Zuschlag an das zweitgünstigste Angebot ohne Begründung, Antrag nicht von der Kostenstellenbevollmächtigten unterschrieben",
             "Zwei Mängel: Das gewählte Angebot ist ohne Begründung nicht das günstigste, und die Beauftragung durch die "
             "Kostenstellenbevollmächtigte fehlt.", who="Lea Wiechmann-Ochieng", mailbox="l.wiechmann@uni-wernstadt.de")
    cam = [("Wärmebildkamera 640 x 480, 30 Hz", 1, 5480.00)]
    bids = write_offers(c, fg, [
        ("Infrarot Systeme Barth GmbH", ["Am Flugplatz 3", "18356 Barth"], "ISB-27-0144", "12.04.2027", cam),
        ("Thermografie Kessler KG", ["Bergweg 12", "87435 Kempten"], "TK-27-0391", "13.04.2027", [(cam[0][0], 1, 5790.00)]),
        ("IR-Messtechnik Pohl", ["Kantstraße 50", "10627 Berlin"], "IRP-0415", "14.04.2027", [(cam[0][0], 1, 5995.00)])])
    proc_form(c, number="ZB-2027-0315", date="19.04.2027", fachgebiet=fg, phone="0561 7390-4850", kostenstelle="71 4850 / Auftrag 2140760",
              holder="Prof. Dr. Margit Feuerhahn", category="Anlage", framework=False, procedure="Preisvergleich, drei schriftliche Angebote",
              offers=3, supplier="Thermografie Kessler KG (Angebot TK-27-0391)", items=[(cam[0][0], 1, 5790.00)], signed=False,
              begruendung="Wärmebildkamera für die Wärmeübergangsversuche.")
    c.write("vergabevermerk.pdf", "award_note", ms.award_note(
        number="V-27-0255", antrag="ZB-2027-0315", subject="Wärmebildkamera", winner="Thermografie Kessler KG, 5.790,00 netto",
        bids=[(v, n, d, net, gross, rank) for rank, (v, n, d, net, gross) in enumerate(bids, 1)],
        reason="Zuschlag an Thermografie Kessler KG.", date="20.04.2027", clerk="Ruben Kramm"))
    proc_trail(c, "Do 22.04.2027 13:00", "Der Zuschlag soll an das zweitgünstigste Angebot gehen, eine Begründung fehlt; außerdem "
               "ist der Antrag nicht von der Kostenstellenbevollmächtigten unterschrieben.")

    # 316 angenommen: second-cheapest chosen with a documented economic reason
    fg = "Fachgebiet Messtechnik und Sensorik"
    c = Case("coverage", "proc", 316, "angenommen", "C3", "P06", SRC_PROC,
             "Zweitgünstigstes Angebot gewählt, weil das günstigste erst nach dem Praktikum liefern kann; im Vergabevermerk begründet",
             "Die Abweichung vom günstigsten Angebot ist im Vergabevermerk nachvollziehbar begründet (Liefertermin vor Praktikumsbeginn).",
             who="Dr. Simon Achenbach", mailbox="s.achenbach@uni-wernstadt.de")
    kit = [("Praktikumsset Sensorik (Messbox, Sensoren, Software)", 6, 410.00)]
    bids = write_offers(c, fg, [
        ("Lehrmittel Danneberg GmbH", ["Weserstraße 77", "37603 Holzminden"], "LD-27-0870", "02.08.2027", kit),
        ("Didaktik-Technik Rehm", ["Messeplatz 4", "04356 Leipzig"], "DTR-27-114", "03.08.2027", [(kit[0][0], 6, 428.00)]),
        ("EduLab Systems Fink KG", ["Am Bach 7", "79098 Freiburg"], "ELS-0322", "04.08.2027", [(kit[0][0], 6, 455.00)])])
    proc_form(c, number="ZB-2027-0316", date="06.08.2027", fachgebiet=fg, phone="0561 7390-4870", kostenstelle="71 4870 / Auftrag 2140781",
              holder="Prof. Dr. Volker Strassheim", category="GWG", framework=False, procedure="Preisvergleich, drei schriftliche Angebote",
              offers=3, supplier="Didaktik-Technik Rehm (Angebot DTR-27-114)", items=[(kit[0][0], 6, 428.00)],
              begruendung="Sets für das Pflichtpraktikum ab 04.10.2027. Das günstigste Angebot nennt eine Lieferzeit von 14 Wochen; "
                          "Didaktik-Technik Rehm liefert verbindlich in 3 Wochen.")
    c.write("vergabevermerk.pdf", "award_note", ms.award_note(
        number="V-27-0611", antrag="ZB-2027-0316", subject="Sechs Praktikumssets Sensorik", winner="Didaktik-Technik Rehm, 2.568,00 netto",
        bids=[(v, n, d, net, gross, rank) for rank, (v, n, d, net, gross) in enumerate(bids, 1)],
        criterion="Preis (netto) und Liefertermin vor Praktikumsbeginn am 04.10.2027 (Ausschlusskriterium)",
        reason="Lehrmittel Danneberg kann erst Mitte November liefern und erfüllt das Ausschlusskriterium nicht. Unter den "
               "geeigneten Angeboten ist Didaktik-Technik Rehm das wirtschaftlichste.", date="09.08.2027", clerk="Jasper Wollenweber"))
    proc_trail(c, "Mi 11.08.2027 09:00", "Die Abweichung vom günstigsten Angebot ist im Vergabevermerk begründet.")


# =========================================================================== #
#             C4  inconspicuous acceptances: suspicious but correct            #
# =========================================================================== #

def c4_trip():
    # 401: heavy pseudonymisation traces on a regular trip
    c = Case("coverage", "trip", 401, "angenommen", "C4", "G01", SRC_TRIP,
             "Regulärer Antrag mit starken Pseudonymisierungsspuren (fremde PLZ, seltsame Nummer, Wort in anderer Schrift, geschwärzte Unterschrift)",
             "Vollständiger, rechtzeitiger Antrag; die Auffälligkeiten sind Pseudonymisierungsspuren und kein Mangel.",
             who="Dr. Wenzel Opoku-Brandt", mailbox="w.opoku@uni-kassel.de")
    orga_trip(c, rnr="3381044401", pnr="04-4471/B9", fg="Fachgebiet Signalverarbeitung 77-0193", ziel="Erlangen", ausland=False,
              anlass=f"{odd_font('Kolloquium')} Audiosignalverarbeitung 2027", grund="Vortrag", verkehr="Bahn, 2. Klasse",
              antrag=date(2027, 3, 8), start=(date(2027, 4, 20), "07:05"), ende=(date(2027, 4, 21), "19:30"),
              bstart=(date(2027, 4, 20), "13:00"), bend=(date(2027, 4, 21), "15:00"), arbeitstage="2",
              kosten=[("Bahn Kassel&#8211;Erlangen, Hin- und Rückfahrt", 1, 118.00), ("Übernachtung, 1 Nacht", 1, 76.00)],
              finanzierung="Fachgebietsbudget, Kostenstelle 4691-07",
              begruendung=f"Vortrag im {odd_font('Kolloquium')}; die Einladung liegt bei.")
    mail(c, "einladung.pdf", subject=f"Einladung zum {odd_font('Kolloquium')} am 20./21. April 2027",
         sender="Lehrstuhl für Audiotechnik &lt;sekretariat@audio.fau-erlangen.example&gt;", sent="Do 18.02.2027 10:30",
         to=f"{c.who} &lt;k.brandt-rehm@uni-kassel.de&gt;",
         body=["Sehr geehrter Herr Dr. Opoku-Brandt,", "wir laden Sie zu einem Vortrag in unserem Kolloquium am 20. April 2027, "
               "16:00 Uhr, ein. Ein Honorar ist nicht vorgesehen.", "Mit freundlichen Grüßen<br/>i. A. " + REDACTED])
    hotel(c, vendor="Hotel Altstadt Erlangen", addr=["Hauptstraße 72", "18055 Erlangen"], nights=1, rate=76.00,
          period="20.04.&#8211;21.04.2027", booked=date(2027, 3, 7),
          recipient=["Universität Kassel", "Fachbereich 16", f"Gast: {c.who}", "Wilhelmshöher Allee 71-73", "18055 Kassel"])
    trip_trail(c, "3381044401", "Fr 12.03.2027 08:15", "Vollständiger Antrag, Übernachtung innerhalb von 80,00 &#8364;.")

    # 402: organiser pays the hotel, declared and not claimed
    c = Case("coverage", "trip", 402, "angenommen", "C4", "T09", SRC_TRIP,
             "Veranstalter übernimmt das Hotel, im Antrag mitgeteilt und nicht beantragt",
             "Leistung von dritter Seite vor Reiseantritt mitgeteilt; beantragt sind nur die übrigen Kosten.",
             who="Dr. Charlotte Weißgerber", mailbox="c.weissgerber@uni-kassel.de")
    orga_trip(c, rnr="3381044402", pnr="040066", fg="Fachgebiet Nachhaltiges Bauen", ziel="Zürich, SCHWEIZ", ausland=True,
              anlass="Expertenworkshop Kreislaufwirtschaft im Bauwesen, ETH Zürich", grund="Eingeladene Expertin",
              verkehr="Bahn, 2. Klasse", antrag=date(2027, 2, 22), start=(date(2027, 5, 3), "06:50"), ende=(date(2027, 5, 4), "21:40"),
              bstart=(date(2027, 5, 3), "13:00"), bend=(date(2027, 5, 4), "16:00"), arbeitstage="2",
              a1="beantragt am 22.02.2027 (Vorlauf &gt; 8 Wochen)",
              kosten=[("Bahn Kassel&#8211;Zürich, Hin- und Rückfahrt", 1, 172.00), ("Übernachtung: wird vom Veranstalter direkt bezahlt", 1, 0.00)],
              finanzierung="Fachgebietsbudget, Kostenstelle 4530-01; Hotel trägt die ETH Zürich (Leistung Dritter, siehe Einladung)",
              begruendung="Expertenworkshop auf Einladung; die Übernachtung bucht und bezahlt der Veranstalter.")
    mail(c, "einladung-eth.pdf", subject="Expert workshop circular construction &#8211; invitation and accommodation",
         sender="Dr. Fabienne Égli &lt;f.egli@ethz.example&gt;", sent="Mo 08.02.2027 13:40",
         body=["Dear Dr. Weißgerber,", "we are delighted that you will join our expert workshop on 3&#8211;4 May 2027.",
               "We will book and pay one night at the Hotel Rigiblick for you directly. Travel costs cannot be covered.",
               "Best regards,<br/>Fabienne Égli"])
    trip_trail(c, "3381044402", "Do 25.02.2027 09:20", "Die vom Veranstalter getragene Übernachtung ist mitgeteilt und nicht beantragt.")

    # 403: private stay of exactly 5 working days
    c = Case("coverage", "trip", 403, "angenommen", "C4", "T15", SRC_TRIP,
             "Privataufenthalt von genau 5 Arbeitstagen nach der Konferenz, Rückflug ohne Mehrkosten",
             "Bei einem Privataufenthalt von höchstens 5 Arbeitstagen wird abgerechnet, als habe nur die Dienstreise stattgefunden; Mehrkosten entstehen nicht.",
             who="Dr. Jonas Meyerhoff-Kim", mailbox="j.meyerhoff@uni-kassel.de")
    orga_trip(c, rnr="3381044403", pnr="055290", fg="Fachgebiet Komplexe Systeme", ziel="Barcelona, SPANIEN", ausland=True,
              anlass="Conference on Complex Systems 2027", grund="Vortrag", verkehr="Flug (Economy)", antrag=date(2027, 6, 7),
              start=(date(2027, 9, 13), "06:30"), ende=(date(2027, 9, 24), "22:10"), bstart=(date(2027, 9, 14), "09:00"),
              bend=(date(2027, 9, 16), "18:00"), privat="17.09.&#8211;24.09.2027 (5 Arbeitstage, Urlaub beantragt)",
              arbeitstage="4 dienstlich", a1="beantragt am 07.06.2027",
              kosten=[("Flug Frankfurt&#8211;Barcelona, Hin- und Rückflug (Rückflug zum Vergleichstarif 17.09.)", 1, 236.00),
                      ("Konferenzgebühr", 1, 450.00), ("Unterkunft, 4 Nächte (Konferenzzeitraum)", 4, 384.00)],
              finanzierung="Fachgebietsbudget, Kostenstelle 4677-01",
              begruendung="Vortrag; Annahmebestätigung liegt bei. Der Rückflug am 24.09. kostet laut Preisvergleich nicht mehr als am 17.09.")
    vendor_doc(c, "preisvergleich-flug.pdf", "price_comparison", vendor="Reisebüro am Königsplatz", vendor_addr=["Königsplatz 37", "34117 Kassel"],
               recipient=["Universität Kassel", f"z. Hd. {c.who}"], refs=[("Datum:", "04.06.2027")], heading="Preisvergleich",
               items=[["FRA&#8211;BCN 13.09. / BCN&#8211;FRA 17.09.2027 (direkt nach Dienstgeschäft)", "1", "&#8212;", e(236), e(236)],
                      ["FRA&#8211;BCN 13.09. / BCN&#8211;FRA 24.09.2027 (gebucht)", "1", "&#8212;", e(229), e(229)]],
               sums=[("Beantragt (niedrigerer Vergleichswert)", e(236))])
    trip_trail(c, "3381044403", "Fr 11.06.2027 10:05", "Privataufenthalt von 5 Arbeitstagen; abgerechnet wird wie eine reine Dienstreise.")

    # 404: conference dinner offered but not claimed
    c = Case("coverage", "trip", 404, "angenommen", "C4", "T18", SRC_TRIP,
             "Programm mit Conference Dinner und inkludiertem Mittagessen, Dinner nicht gebucht und nicht beantragt",
             "Das optionale Dinner ist nicht beantragt; die Tagungspauschale mit Mittagessen ist eine notwendige Pauschale.",
             who="Annika Holtkamp-Reyes", mailbox="a.holtkamp@uni-kassel.de")
    orga_trip(c, rnr="3381044404", pnr="061877", fg="Fachgebiet Didaktik der Informatik", ziel="Dortmund", ausland=False,
              anlass="GI-Fachtagung Informatik und Schule 2027", grund="Workshopleitung", verkehr="Bahn, 2. Klasse",
              antrag=date(2027, 7, 12), start=(date(2027, 9, 27), "07:20"), ende=(date(2027, 9, 28), "20:15"),
              bstart=(date(2027, 9, 27), "10:00"), bend=(date(2027, 9, 28), "16:30"), arbeitstage="2",
              kosten=[("Tagungsgebühr inkl. Mittagessen (Tagungspauschale)", 1, 190.00), ("Bahn Kassel&#8211;Dortmund, Hin- und Rückfahrt", 1, 86.00),
                      ("Übernachtung, 1 Nacht", 1, 79.00)],
              finanzierung="Fachgebietsbudget, Kostenstelle 4699-02", begruendung="Leitung eines Workshops; Programm liegt bei.")
    vendor_doc(c, "anmeldung-tagung.pdf", "booking", vendor="Gesellschaft für Informatik e.V.", vendor_addr=["Wissenschaftszentrum", "Ahrstraße 45", "53175 Bonn"],
               recipient=["Universität Kassel", f"z. Hd. {c.who}", "34121 Kassel"], refs=[("Anmeldung:", "INFOS27-0388"), ("Datum:", "10.07.2027")],
               heading="Anmeldebestätigung", items=[["Tagungsgebühr inkl. Mittagessen beider Tage", "1", "19 %", e(159.66), e(190)]],
               sums=[("Summe", e(190))], notes=["Das Conference Dinner am 27.09.2027 (55,00 EUR) wurde nicht gebucht."])
    trip_trail(c, "3381044404", "Do 15.07.2027 08:00", "Das Conference Dinner ist nicht beantragt; die Tagungspauschale ist erstattungsfähig.")

    # 405: hotel exactly 80 EUR
    c = Case("coverage", "trip", 405, "angenommen", "C4", "T06", SRC_TRIP, "Inland, Hotel genau 80,00 €/Nacht",
             "80,00 € je Nacht liegen genau auf der Höchstgrenze und sind ohne Begründung erstattungsfähig.",
             who="Dr. Mareen Albers-Tchami", mailbox="m.albers@uni-kassel.de")
    orga_trip(c, rnr="3381044405", pnr="047212", fg="Fachgebiet Biomechanik", ziel="Köln", ausland=False,
              anlass="Jahrestagung Biomechanik 2027", grund="Posterbeitrag", verkehr="Bahn, 2. Klasse", antrag=date(2027, 8, 2),
              start=(date(2027, 10, 6), "07:00"), ende=(date(2027, 10, 8), "19:00"), bstart=(date(2027, 10, 6), "12:00"),
              bend=(date(2027, 10, 8), "13:00"), arbeitstage="3",
              kosten=[("Tagungsgebühr", 1, 240.00), ("Bahn Kassel&#8211;Köln, Hin- und Rückfahrt", 1, 108.00),
                      ("Übernachtung, 2 Nächte à 80,00 &#8364;", 2, 160.00)],
              finanzierung="Fachgebietsbudget, Kostenstelle 4612-04", begruendung="Posterbeitrag; Annahme liegt bei.")
    hotel(c, vendor="Hotel am Rheinpark", addr=["Auenweg 18", "50679 Köln"], nights=2, rate=80.00, period="06.10.&#8211;08.10.2027",
          booked=date(2027, 8, 1))
    trip_trail(c, "3381044405", "Fr 06.08.2027 09:40", "Übernachtung genau auf der Höchstgrenze von 80,00 &#8364;.")


def c4_expense():
    # 406: English invoice c/o university, mismatching e-mail and invalid IBAN
    c = Case("coverage", "exp", 406, "angenommen", "C4", "E03", SRC_FIN,
             "Englische Rechnung an Person c/o Universität, abweichende E-Mail-Adresse, ungültige IBAN",
             "Rechnung über ein Fachbuch an die Person c/o Lehrstuhl: dienstlicher Bezug belegt; Adresse und IBAN sind Pseudonymisierungsspuren.",
             who="Dr. Sanna Lindgren-Okeke", mailbox="s.lindgren@uni-wernstadt.de")
    vendor_doc(c, "invoice.pdf", "invoice", vendor="Ravenhill Academic Books Ltd", vendor_addr=["12 Mill Lane", "Oxford OX1 2JD",
                                                                                              "United Kingdom", "VAT GB 344 9081 22"],
               recipient=["Dr. Sanna Lindgren-Okeke", "c/o University of Wernstadt", "Chair of Control Engineering",
                          "Am Lindenhang 40", "35291 Wernstadt", "Germany", "Email: s.okeke-lind@mailbox.example"],
               refs=[("Invoice no.", "RAB-27-55710"), ("Date", "14 Jan 2027")], heading="Invoice",
               items=[["Robust Control of Uncertain Systems (hardcover)", "1", "0 % (books)", e(68.00), e(68.00)],
                      ["Shipping EU", "1", "0 %", e(6.50), e(6.50)]],
               sums=[("Total", e(74.50))], payment=[("Paid", "credit card, 14 Jan 2027"), ("IBAN", "DE00 0000 1234 5678 9000 12")])
    exp_trail(c, "Di 26.01.2027 11:10", "Originalrechnung über ein Fachbuch, dienstlicher Bezug über die c/o-Anschrift belegt.")

    # 407: USD invoice with card statement
    c = Case("coverage", "exp", 407, "angenommen", "C4", "E08", SRC_FIN,
             "Software-Lizenz in USD, Kreditkartenabrechnung belegt den Euro-Betrag",
             "Fremdwährungsbeleg mit Kartenabrechnung; der Euro-Betrag ist belegt.", who="Dr. Mikkel Østergaard-Vogt",
             mailbox="m.ostergaard@uni-wernstadt.de")
    vendor_doc(c, "receipt-usd.pdf", "invoice", vendor="PlotLab Software Inc.", vendor_addr=["400 Market Street", "San Francisco, CA 94111", "USA"],
               recipient=["Dr. Mikkel Østergaard-Vogt", "University of Wernstadt, Institute of Fluid Mechanics"],
               refs=[("Receipt no.", "PL-27-118400"), ("Date", "03/02/2027")], heading="Receipt",
               items=[["PlotLab Academic, single-user licence, 12 months", "1", "&#8212;", "USD 89.00", "USD 89.00"]],
               sums=[("Total paid", "USD 89.00")], payment=[("Paid", "Visa ****4417")])
    o.bank_receipt_pdf(c.path("kreditkartenabrechnung.pdf", "bank_statement"), bic="WERNDEF1XXX", iban="DE12 5135 0025 0007 7120 44",
                       holder="Mikkel Østergaard-Vogt", queried="Mikkel Østergaard-Vogt", date="28.02.2027", time="09:12:40",
                       rows=[("Umsatz", "PLOTLAB SOFTWARE SAN FRANCISCO"), ("Buchungstag", "04.02.2027"),
                             ("Betrag", "-82,47 EUR (USD 89,00, Kurs 1,0792)"), ("Auslandseinsatzentgelt", "-1,44 EUR"), ("Karte", "Visa ****4417")],
                       bank_footer="Kreditkartenabrechnung Februar 2027 &#8211; Auszug. Seite 1 von 1")
    exp_trail(c, "Mo 08.03.2027 10:30", "Fremdwährungsbeleg mit Kartenabrechnung; erstattet werden 83,91 &#8364;.")

    # 408: guest gift exactly 30 EUR
    c = Case("coverage", "exp", 408, "angenommen", "C4", "E12", SRC_FIN, "Gastgeschenk genau 30,00 € bei einer Dienstreise nach Graz",
             "Gastgeschenke bis 30,00 € sind übernahmefähig; 30,00 € übersteigen die Grenze nicht.", who="Prof. Dr. Regine Hallström",
             mailbox="r.hallstroem@uni-wernstadt.de")
    shop_invoice(c, "rechnung-gastgeschenk.pdf", vendor="Manufaktur Lahnkeramik", addr=["Töpfergasse 3", "35291 Wernstadt"],
                 recipient=wern("Lehrstuhl für Werkstoffe der Elektrotechnik", c.who), number="LK-27-0088", day=date(2027, 4, 9),
                 rows=[("Keramikschale mit Universitätswappen", 1, 30.00, 0.19)], payment="EC-Karte, bezahlt",
                 notes=["Gastgeschenk für die Gastgeber an der TU Graz, Dienstreise 12.&#8211;14.04.2027 (handschriftlich)"])
    exp_trail(c, "Mi 21.04.2027 08:35", "Gastgeschenk bei einer Dienstreise, Wert genau 30,00 &#8364;.")

    # 409: product line replaced by a person's name on a receipt
    c = Case("coverage", "exp", 409, "angenommen", "C4", "G01", SRC_FIN,
             "Laborbedarf, eine Position trägt statt der Produktbezeichnung einen Personennamen (Pseudonymisierung), Zweck vermerkt",
             "Beleg mit Artikeln und Zweckvermerk; der Personenname in einer Position ist eine Pseudonymisierungsspur.",
             who="Theresa Kamau-Lindner", mailbox="t.kamau@uni-wernstadt.de")
    receipt(c, "kassenbon-laborbedarf.pdf", ["CHEMIEHANDEL ROSSBACH", "Bahnhofstraße 50", "35390 Gießen", "",
                                            "ISOPROPANOL 1L          2 x 7,90", "NITRIL-HANDSCHUHE M      1 x 9,49",
                                            "BRANDT-KOWALCZYK 500ML   1 x 6,20", "", "SUMME EUR               31,49",
                                            "EC-KARTE                31,49", "MWST 19% NETTO 26,46 MWST 5,03", "BON 0917 KASSE 01 07.05.27 11:20"],
            note=["Reinigungsmittel und Handschuhe für Labor C 0.12", "(T. Kamau-Lindner)"])
    exp_trail(c, "Fr 14.05.2027 09:05", "Originalbeleg mit Artikeln und Zweckvermerk.")


def c4_procurement():
    # 410: gross above, net below 1,000 EUR, one offer
    c = Case("coverage", "proc", 410, "angenommen", "C4", "P01", SRC_CATER,
             "Direktvergabe mit einem Angebot: 990,00 € netto, 1.178,10 € brutto",
             "Maßgeblich ist der Nettoauftragswert; 990,00 € liegen unter 1.000 €, die Direktvergabe ist zulässig.",
             who="Bjarne Holtermann", mailbox="b.holtermann@uni-wernstadt.de")
    fg = "Fachgebiet Elektrische Antriebe"
    items = [("Frequenzumrichter 2,2 kW", 2, 395.00), ("Bremswiderstand 200 Ohm", 2, 100.00)]
    write_offers(c, fg, [("Antriebstechnik Grabowski", ["Werner-von-Siemens-Str. 5", "49124 Georgsmarienhütte"], "AG-27-0447", "03.05.2027", items)])
    proc_form(c, number="ZB-2027-0410", date="05.05.2027", fachgebiet=fg, phone="0561 7390-4521", kostenstelle="71 4521 / Auftrag 2140410",
              holder="Prof. Dr. Sven Aldag", category="GWG", framework=False, procedure="Direktvergabe (unter 1.000 € netto)",
              offers=1, supplier="Antriebstechnik Grabowski (Angebot AG-27-0447)", items=items,
              begruendung="Umrichter für den Praktikumsversuch; Auftragswert netto unter 1.000 €, daher ein Angebot.")
    proc_trail(c, "Fr 07.05.2027 10:00", "Nettoauftragswert 990,00 &#8364; unter 1.000 &#8364;: Direktvergabe zulässig.")

    # 411: notebooks from the WPS framework catalogue, no offers
    c = Case("coverage", "proc", 411, "angenommen", "C4", "P02", SRC_FRAME,
             "Notebooks und Monitore für 4.812 € netto aus dem WPS-Katalog, keine Vergleichsangebote",
             "Abruf aus dem Rahmenvertrag IT-Arbeitsplatzgeräte über WPS; Vergleichsangebote entfallen unabhängig vom Betrag.",
             who="Imke Sörensen-Adu", mailbox="i.soerensen@uni-wernstadt.de")
    fg = "Fachgebiet Softwaretechnik"
    wps = [("BE-NB14-G7", "Notebook 14 Zoll, 32 GB RAM, 1 TB SSD", 4, 1023.00), ("BE-MON27-Q", "Monitor 27 Zoll QHD", 4, 180.00)]
    cart, _ = ms.wps_cart(number="WK-0027-22411", catalog="Rahmenvertrag IT-Arbeitsplatzgeräte", supplier="Bechtle GmbH & Co. KG, Darmstadt",
                          created="18.10.2027", buyer=c.who, account="71 4560 / Auftrag 2140810", items=wps)
    c.write("warenkorb.pdf", "framework_cart", cart)
    proc_form(c, number="ZB-2027-0411", date="18.10.2027", fachgebiet=fg, phone="0561 7390-4560", kostenstelle="71 4560 / Auftrag 2140810",
              holder="Prof. Dr. Anja Tegtmeyer", category="Anlage", framework=True, procedure="Abruf Rahmenvertrag (WPS)", offers=0,
              supplier="Bechtle GmbH & Co. KG (Rahmenvertragspartner)", items=[(d, q, u) for _, d, q, u in wps],
              begruendung="Arbeitsplätze für vier neue Doktorand:innen; Warenkorb aus dem Rahmenvertrag anbei.")
    proc_trail(c, "Mi 20.10.2027 08:30", "Abruf aus dem Rahmenvertrag über WPS.")

    # 412: envelopes - currently no framework contract
    c = Case("coverage", "proc", 412, "angenommen", "C4", "P09", SRC_FRAME,
             "Briefhüllen und Versandtaschen für 1.180 € netto mit drei Angeboten (derzeit kein Rahmenvertrag)",
             "Für Briefhüllen und Versandtaschen besteht derzeit kein Rahmenvertrag; drei Angebote, günstigstes gewählt.",
             who="Gesine Wittkamp", mailbox="g.wittkamp@uni-wernstadt.de")
    fg = "Dekanat Fachbereich 71"
    env = [("Briefhülle DIN lang mit Fenster, 1.000 Stück", 8, 42.00), ("Versandtasche C4, 250 Stück", 12, 70.33)]
    write_offers(c, fg, [("Kuvertfabrik Lennestadt GmbH", ["Industriestraße 8", "57368 Lennestadt"], "KL-27-0912", "01.09.2027", env),
                         ("Bürowelt Nordhessen", ["Holländische Str. 90", "34127 Kassel"], "BN-A-27-3321", "02.09.2027",
                          [(env[0][0], 8, 45.10), (env[1][0], 12, 72.90)]),
                         ("Papyrus Versand KG", ["Am Speicher 2", "28217 Bremen"], "PV-0902", "02.09.2027",
                          [(env[0][0], 8, 46.80), (env[1][0], 12, 74.20)])])
    proc_form(c, number="ZB-2027-0412", date="06.09.2027", fachgebiet=fg, phone="0561 7390-4000", kostenstelle="71 4000 / Auftrag 2140001",
              holder="Prof. Dr. Ralf Ebbinghaus (Dekan)", category="Verbrauchsmaterial", framework=False,
              procedure="Preisvergleich, drei schriftliche Angebote", offers=3, supplier="Kuvertfabrik Lennestadt GmbH (Angebot KL-27-0912)",
              items=env, begruendung="Jahresbedarf Versandmaterial für Prüfungsamt und Dekanat; derzeit kein Rahmenvertrag für "
                                     "Briefhüllen, günstigstes von drei Angeboten.")
    proc_trail(c, "Fr 10.09.2027 09:25", "Kein Rahmenvertrag für Briefhüllen; drei Angebote, günstigstes gewählt.")

    # 413: budget holder approves by replying in the thread
    c = Case("coverage", "proc", 413, "angenommen", "C4", "P03", SRC_PROC,
             "Bestellung per E-Mail, die Kostenstellenbevollmächtigte antwortet im Verlauf mit 'beauftragt'",
             "Die Beauftragung durch die Kostenstellenbevollmächtigte liegt schriftlich im E-Mail-Verlauf vor; Auftragswert unter 1.000 € netto.",
             who="Karim Wendland-Haddou", mailbox="k.wendland@uni-wernstadt.de")
    fg = "Fachgebiet Optoelektronik"
    items = [("Laserdiodentreiber mit TEC-Regler", 1, 640.00), ("Fasergekoppelte Laserdiode 1550 nm", 1, 245.00)]
    write_offers(c, fg, [("Photonics Supply Meerbusch", ["Kaarster Str. 11", "40667 Meerbusch"], "PSM-27-1188", "22.06.2027", items)])
    thread(c, "email-bestellung.pdf", kassel=False, doc_type="application", subject="Bestellung Laserdiodentreiber FG Optoelektronik",
           messages=[(f"{c.who} &lt;{c.mailbox}&gt;", "Do 24.06.2027 10:12", "beschaffung@uni-wernstadt.de; Prof. Dr. Nadja Firouzi",
                      ["Sehr geehrte Damen und Herren,", "bitte bestellen Sie gemäß Angebot PSM-27-1188 einen Laserdiodentreiber "
                       "(640,00 &#8364; netto) und eine Laserdiode (245,00 &#8364; netto), zusammen 885,00 &#8364; netto. "
                       "Kostenstelle 71 4612.", "Viele Grüße<br/>Karim Wendland-Haddou"]),
                     ("Prof. Dr. Nadja Firouzi &lt;n.firouzi@uni-wernstadt.de&gt;", "Do 24.06.2027 11:40", "beschaffung@uni-wernstadt.de",
                      ["Hiermit beauftragt (Kostenstellenbevollmächtigte 71 4612).", "N. Firouzi"])])
    proc_trail(c, "Mo 28.06.2027 08:40", "Beauftragung durch die Kostenstellenbevollmächtigte im E-Mail-Verlauf; Direktvergabe unter 1.000 &#8364;.")

    # 414: projector and screen, not a framework product
    c = Case("coverage", "proc", 414, "angenommen", "C4", "P02", SRC_FRAME,
             "Beamer und Leinwand für den Seminarraum mit drei Angeboten (kein Rahmenvertragsprodukt)",
             "Beamer und Leinwände gehören nicht zu den Rahmenvertragssortimenten; drei Angebote, günstigstes gewählt.",
             who="Dr. Hauke Petersen-Nyambura", mailbox="h.petersen@uni-wernstadt.de")
    fg = "Fachgebiet Elektrische Netze"
    av = [("Laser-Beamer WUXGA, 5.000 Lumen", 1, 1490.00), ("Rahmenleinwand 16:10, 240 cm", 1, 385.00)]
    write_offers(c, fg, [("Medientechnik Schwalm GmbH", ["Am Markt 2", "34613 Schwalmstadt"], "MS-27-0731", "12.07.2027", av),
                         ("AV-Systeme Brakel", ["Ostheimer Weg 4", "33034 Brakel"], "AVB-27-188", "13.07.2027",
                          [(av[0][0], 1, 1560.00), (av[1][0], 1, 399.00)]),
                         ("Konferenztechnik Hesse KG", ["Frankfurter Str. 120", "35392 Gießen"], "KTH-0715", "14.07.2027",
                          [(av[0][0], 1, 1615.00), (av[1][0], 1, 410.00)])])
    proc_form(c, number="ZB-2027-0414", date="16.07.2027", fachgebiet=fg, phone="0561 7390-4590", kostenstelle="71 4590 / Auftrag 2140414",
              holder="Prof. Dr. Lutz Oppermann", category="Anlage", framework=False, procedure="Preisvergleich, drei schriftliche Angebote",
              offers=3, supplier="Medientechnik Schwalm GmbH (Angebot MS-27-0731)", items=av,
              begruendung="Ausstattung Seminarraum E 1.03; günstigstes von drei Angeboten.")
    proc_trail(c, "Di 20.07.2027 10:45", "Kein Rahmenvertragsprodukt; drei Angebote, günstigstes gewählt.")

    # 415: TH Sallstedt, two offers as required by its own rule quoted in the correspondence
    c = Case("coverage", "proc", 415, "angenommen", "C4", "G02", SRC_PROC,
             "TH Sallstedt: 1.460 € netto mit zwei Angeboten, die interne Wertgrenze der TH steht in der Korrespondenz",
             "Für die TH Sallstedt gilt anderes Landesrecht; nach der in der Korrespondenz zitierten Vorgabe der TH genügen zwei Angebote bis 5.000 €.",
             who="Dr. Wilma Stöcklein-Ayo", mailbox="w.stoecklein@th-sallstedt.de")
    rec = ["Technische Hochschule Sallstedt", "Fakultät Maschinenbau", "Labor Werkzeugmaschinen", f"z. Hd. {c.who}",
           "Hochschulring 3", "29410 Sallstedt"]
    spindle = [("Messtaster für CNC-Fräse, Funkübertragung", 1, 1460.00)]
    for i, (vendor, lines, number, day, amount) in enumerate([("Präzisionstechnik Ahlers", ["Hafenweg 2", "21680 Stade"], "PA-27-0315", "15.03.2027", 1460.00),
                                                            ("Messtechnik Uelzen GmbH", ["Gewerbestr. 5", "29525 Uelzen"], "MU-27-112", "16.03.2027", 1535.00)], 1):
        story, _, _ = ms.offer(vendor=vendor, vendor_lines=lines, recipient=rec, number=number, date=day, valid="30 Tage",
                               items=[(spindle[0][0], 1, amount)])
        c.write(f"angebot-{i}.pdf", "offer", story)
    thread(c, "email-bestellanforderung.pdf", kassel=False, doc_type="application", subject="Bestellanforderung Messtaster Labor WZM",
           messages=[(f"{c.who} &lt;{c.mailbox}&gt;", "Mi 17.03.2027 09:20", "einkauf@th-sallstedt.de",
                      ["Liebes Einkaufsteam,", "bitte bestellen Sie den Messtaster bei Präzisionstechnik Ahlers (Angebot PA-27-0315, "
                       "1.460,00 &#8364; netto). Ein zweites Angebot liegt bei. Prof. Dr. Ulf Hagedorn hat als Laborleiter freigegeben.",
                       "Viele Grüße<br/>Wilma Stöcklein-Ayo"]),
                     ("Einkauf TH Sallstedt &lt;einkauf@th-sallstedt.de&gt;", "Mi 17.03.2027 14:02", f"{c.who} &lt;{c.mailbox}&gt;",
                      ["Liebe Frau Dr. Stöcklein-Ayo,", "nach unserer Vergaberichtlinie (Nr. 4.2) genügen bei Aufträgen bis 5.000 "
                       "&#8364; netto zwei Vergleichsangebote. Die Unterlagen sind vollständig, wir bestellen.", "Ihr Einkauf"])])
    proc_trail(c, "Do 18.03.2027 08:00", "Nach der Vergaberichtlinie der TH genügen zwei Angebote; die Unterlagen sind vollständig.")


# =========================================================================== #
#             C5  free text written by another LLM than the solver             #
# =========================================================================== #

C5_MODEL = "mistralai/mistral-small-3.2-24b-instruct"
# id -> (instruction for the writer, facts that must appear verbatim). The label never comes from the writer.
C5_SPECS = {
    "c501": ("Schreibe die E-Mail eines Veranstalters (Fachforum Wasserstoffwirtschaft in Magdeburg, 9. Juni 2027) an Dr. Ruth "
             "Engelhardt-Mwangi von der Universität Kassel. Er bestätigt ihren Vortrag und nennt ein Honorar von 600 Euro, das "
             "nach der Veranstaltung gegen Rechnung gezahlt wird. Reisekosten übernimmt er nicht. Schreibe außerdem die "
             "Kurzbegründung ihres Dienstreiseantrags (2 Sätze, ohne das Honorar zu erwähnen).",
             ["600", "Honorar", "Magdeburg"], ["einladung", "begruendung"]),
    "c502": ("Schreibe die E-Mail des Doktoranden Felix Adomako-Rausch an die Finanzbuchhaltung der Universität Wernstadt. Er "
             "hat für Messungen in der nächsten Woche kurzfristig ein Notebook für 899,00 Euro in einem Elektronikmarkt gekauft, "
             "privat bezahlt, und bittet um Erstattung; die Rechnung lautet auf den Lehrstuhl.",
             ["Notebook", "899,00"], ["anschreiben"]),
    "c503": ("Schreibe die E-Mail von Prof. Dr. Ines Wahlberg an die Finanzbuchhaltung der Universität Wernstadt. Sie bittet um "
             "Erstattung eines Gastgeschenks (Bildband und regionaler Honig) für ihre Gastgeber an der TalTech in Tallinn, "
             "überreicht bei ihrer Dienstreise im Mai 2027, Kosten 52,40 Euro.",
             ["Tallinn", "52,40", "Gastgeschenk"], ["anschreiben"]),
    "c504": ("Schreibe die Bestell-E-Mail des Doktoranden Pavel Szabo-Riedl an die Zentrale Beschaffung der Universität "
             "Wernstadt: drei Angebote für einen Laborkühlschrank liegen bei, der günstigste kostet 1.380,00 Euro netto. Seine "
             "Professorin, Prof. Dr. Dorothea Lenz, ist als Kostenstellenbevollmächtigte auf einer Forschungsreise und nicht "
             "erreichbar; er bittet, trotzdem schon zu bestellen, sie werde später zustimmen.",
             ["1.380,00", "nicht erreichbar"], ["email"]),
    "c505": ("Schreibe die E-Mail von Dr. Jana Okafor-Lindemann an die Finanzbuchhaltung der Universität Wernstadt. Sie hat an "
             "einem Seminar teilgenommen, das ausschließlich online stattfand, die Teilnahmegebühr von 145,00 Euro privat "
             "bezahlt und bittet um Erstattung als privat verauslagte Kosten.",
             ["online", "145,00"], ["anschreiben"]),
    "c506": ("Schreibe die E-Mail von Martina Kühn-Asare an die Finanzbuchhaltung der Universität Wernstadt. Für eine "
             "Delegation der Universität Tartu (vier externe Gäste) hat sie Kaffee, Tee, Mineralwasser und Gebäck gekauft; die "
             "Teilnehmerliste liegt bei. Sie bittet um Erstattung von 38,60 Euro.",
             ["Tartu", "Gäste", "38,60"], ["anschreiben"]),
    "c507": ("Schreibe die Annahme-E-Mail des Programmkomitees der Tagung 'Digitale Lehre 2027' in Lübeck (23.–24. September "
             "2027) an Dr. Bastian Kolb-Nnamdi von der Universität Kassel: sein Beitrag wurde angenommen, Teilnahmegebühr "
             "180 Euro, kein Honorar. Schreibe außerdem die Kurzbegründung seines Dienstreiseantrags (2 Sätze).",
             ["Lübeck", "angenommen", "180"], ["einladung", "begruendung"]),
}


def generate_c5_texts(path):
    """Ask the writer model for each C5 text, check that every required fact is in it, retry up to five times."""
    import os
    import urllib.request
    key = os.environ["OPENROUTER_API_KEY"]
    texts = {}
    for case_id, (instruction, facts, keys) in C5_SPECS.items():
        prompt = (f"{instruction}\nAntworte nur mit einem JSON-Objekt mit den Schlüsseln {keys}; jeder Wert ist der reine Text "
                  "ohne Betreffzeile, Absätze durch \\n getrennt. Schreibe natürlich, wie ein echter Mensch, nicht formelhaft, "
                  "und erfinde konkrete Titel, Namen und Einrichtungen statt Platzhaltern.")
        for attempt in range(5):
            request = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", headers={
                "Authorization": f"Bearer {key}", "Content-Type": "application/json"}, data=json.dumps({
                    "model": C5_MODEL, "temperature": 0.9, "response_format": {"type": "json_object"},
                    "messages": [{"role": "user", "content": prompt}]}).encode())
            answer = json.loads(urllib.request.urlopen(request, timeout=120).read())["choices"][0]["message"]["content"]
            try:
                values = json.loads(answer[answer.find("{"):answer.rfind("}") + 1])
            except json.JSONDecodeError:
                continue
            joined = " ".join(str(values.get(k, "")) for k in keys)
            # Placeholders such as "[Titel einfügen]" or "XYZ" would give the text away as generated.
            placeholder = "[" in joined or "XYZ" in joined or "einfügen" in joined
            if all(k in values for k in keys) and all(fact in joined for fact in facts) and not placeholder:
                texts[case_id] = {"model": C5_MODEL, **{k: str(values[k]) for k in keys}}
                break
        else:
            raise RuntimeError(f"{case_id}: no text with all facts {facts} after 5 attempts")
        print(case_id, "ok after", attempt + 1)
    path.write_text(json.dumps(texts, ensure_ascii=False, indent=1), encoding="utf-8")


def paras(text):
    from xml.sax.saxutils import escape
    return [escape(p.strip()) for p in text.split("\n") if p.strip()]


def c5_cases():
    t = C5_TEXTS
    # 501 abgelehnt: fee mentioned in the organiser's free-text e-mail
    c = Case("coverage", "trip", 501, "abgelehnt", "C5", "T10", SRC_TRIP, "Vortrag, Honorar 600 € nur in der frei formulierten Veranstalter-E-Mail",
             "Laut E-Mail des Veranstalters erhält die Referentin ein Honorar von 600 Euro: Nebentätigkeit, keine Dienstreise.",
             who="Dr. Ruth Engelhardt-Mwangi", mailbox="r.engelhardt@uni-kassel.de")
    orga_trip(c, rnr="3381045501", pnr="052006", fg="Fachgebiet Thermische Energietechnik", ziel="Magdeburg", ausland=False,
              anlass="Fachforum Wasserstoffwirtschaft 2027", grund="Fachvortrag", verkehr="Bahn, 2. Klasse", antrag=date(2027, 4, 26),
              start=(date(2027, 6, 9), "06:40"), ende=(date(2027, 6, 9), "20:55"), bstart=(date(2027, 6, 9), "10:00"),
              bend=(date(2027, 6, 9), "17:00"), arbeitstage="1",
              kosten=[("Bahn Kassel&#8211;Magdeburg, Hin- und Rückfahrt", 1, 94.00), ("Tagegeld", 1, 14.00)],
              finanzierung="Fachgebietsbudget, Kostenstelle 4655-01", begruendung=" ".join(paras(t["c501"]["begruendung"])))
    mail(c, "email-veranstalter.pdf", subject="Ihr Vortrag beim Fachforum Wasserstoffwirtschaft am 9. Juni 2027",
         sender="Fachforum Wasserstoffwirtschaft &lt;team@h2-forum-md.example&gt;", sent="Mi 14.04.2027 10:17", body=paras(t["c501"]["einladung"]))
    trip_trail(c, "3381045501", "Fr 30.04.2027 09:00", "Laut Veranstalter erhalten Sie ein Honorar; das deutet auf eine "
               "Nebentätigkeit hin, eine Dienstreisegenehmigung ist dann grundsätzlich nicht möglich.")

    # 502 abgelehnt: notebook bought privately, explained in free text
    c = Case("coverage", "exp", 502, "abgelehnt", "C5", "E10", SRC_FRAME, "Notebook für 899 € privat gekauft, frei formulierte Begründung",
             "Notebooks sind Rahmenvertragsprodukte und ausschließlich beim Rahmenvertragspartner zu bestellen, auch bei Eile.",
             who="Felix Adomako-Rausch", mailbox="f.adomako@uni-wernstadt.de")
    shop_invoice(c, "rechnung.pdf", vendor="MediaPunkt Elektronik GmbH", addr=["Westring 88", "35394 Gießen"],
                 recipient=wern("Lehrstuhl für Strömungsmechanik", c.who), number="MP-27-660871", day=date(2027, 3, 11),
                 rows=[("Notebook 15,6 Zoll, 16 GB RAM, 1 TB SSD", 1, 899.00, 0.19)], payment="EC-Karte, bezahlt")
    mail(c, "anschreiben.pdf", kassel=False, subject="Erstattung Notebook", sender=f"{c.who} &lt;{c.mailbox}&gt;",
         to="Finanzbuchhaltung &lt;kostenerstattung@uni-wernstadt.de&gt;", sent="Fr 12.03.2027 08:02", body=paras(t["c502"]["anschreiben"]))
    exp_trail(c, "Di 16.03.2027 10:30", "Notebooks sind über den Rahmenvertrag zu bestellen; eine Erstattung ist nicht möglich.")

    # 503 abgelehnt: guest gift above 30 EUR, explained in free text
    c = Case("coverage", "exp", 503, "abgelehnt", "C5", "E12", SRC_FIN, "Gastgeschenk 52,40 € für Gastgeber in Tallinn, frei formuliert",
             "Gastgeschenke sind nur bis 30,00 € übernahmefähig.", who="Prof. Dr. Ines Wahlberg", mailbox="i.wahlberg@uni-wernstadt.de")
    receipt(c, "kassenbon.pdf", ["BUCH & HONIG LADEN", "Marktgasse 3", "35291 Wernstadt", "", "BILDBAND LAHNTAL      1 x 34,90",
                                 "WALDHONIG 500G       1 x 17,50", "", "SUMME EUR             52,40", "EC-KARTE              52,40",
                                 "BON 0311 KASSE 1 18.05.27 16:02"])
    mail(c, "anschreiben.pdf", kassel=False, subject="Erstattung Gastgeschenk Dienstreise Tallinn", sender=f"{c.who} &lt;{c.mailbox}&gt;",
         to="Finanzbuchhaltung &lt;kostenerstattung@uni-wernstadt.de&gt;", sent="Mo 31.05.2027 11:45", body=paras(t["c503"]["anschreiben"]))
    exp_trail(c, "Do 03.06.2027 09:20", "Gastgeschenke können nur bis zu einem Wert von 30,00 &#8364; übernommen werden.")

    # 504 abgelehnt: budget holder unreachable, order placed anyway
    c = Case("coverage", "proc", 504, "abgelehnt", "C5", "P03", SRC_PROC, "Bestellung durch Doktorand, Kostenstellenbevollmächtigte nicht erreichbar",
             "Die Bestellung ist nicht von der Kostenstellenbevollmächtigten beauftragt; ihre spätere Zustimmung ersetzt das nicht.",
             who="Pavel Szabo-Riedl", mailbox="p.szabo@uni-wernstadt.de")
    fg, fridge = "Fachgebiet Biotechnologie", "Laborkühlschrank 360 l, explosionsgeschützter Innenraum"
    write_offers(c, fg, [("Kältetechnik Wenzel GmbH", ["Am Kühlhaus 1", "27572 Bremerhaven"], "KW-27-0921", "09.09.2027", [(fridge, 1, 1380.00)]),
                         ("Laborgeräte Imhof", ["Rathausplatz 4", "88212 Ravensburg"], "LGI-27-443", "10.09.2027", [(fridge, 1, 1455.00)]),
                         ("Medlab Cooling KG", ["Ringstraße 9", "06108 Halle"], "MC-0913", "10.09.2027", [(fridge, 1, 1490.00)])])
    mail(c, "email-bestellung.pdf", kassel=False, doc_type="application", subject="Bestellung Laborkühlschrank",
         sender=f"{c.who} &lt;{c.mailbox}&gt;", to="beschaffung@uni-wernstadt.de", sent="Mo 13.09.2027 08:55", body=paras(t["c504"]["email"]))
    proc_trail(c, "Mi 15.09.2027 10:10", "Bestellungen müssen von der/dem Kostenstellenbevollmächtigten beauftragt werden; das ist nicht geschehen.")

    # 505 angenommen: online seminar fee
    c = Case("coverage", "exp", 505, "angenommen", "C5", "E09", SRC_TRIP, "Gebühr eines reinen Online-Seminars, frei formuliert",
             "Online-Veranstaltungen sind über privat verauslagte Kosten abzurechnen; Rechnung an das Fachgebiet.",
             who="Dr. Jana Okafor-Lindemann", mailbox="j.okafor@uni-wernstadt.de")
    shop_invoice(c, "rechnung-seminar.pdf", vendor="Akademie für Datenanalyse gGmbH", addr=["Spreeufer 5", "10178 Berlin"],
                 recipient=wern("Fachgebiet Statistik", c.who), number="AD-27-1902", day=date(2027, 2, 18),
                 rows=[("Online-Seminar 'Bayessche Statistik in der Praxis', 03.&#8211;04.03.2027", 1, 145.00, 0.19)], payment="Kreditkarte, bezahlt")
    mail(c, "anschreiben.pdf", kassel=False, subject="Erstattung Seminargebühr", sender=f"{c.who} &lt;{c.mailbox}&gt;",
         to="Finanzbuchhaltung &lt;kostenerstattung@uni-wernstadt.de&gt;", sent="Fr 05.03.2027 14:30", body=paras(t["c505"]["anschreiben"]))
    exp_trail(c, "Mi 10.03.2027 09:00", "Teilnahmegebühr einer Online-Veranstaltung als privat verauslagte Kosten.")

    # 506 angenommen: courtesy for an external delegation
    c = Case("coverage", "exp", 506, "angenommen", "C5", "E07", SRC_FIN, "Kaffee, Tee, Wasser, Gebäck für eine Delegation aus Tartu, frei formuliert",
             "Übliche Gesten der Höflichkeit gegenüber externen Gästen, Teilnehmerliste liegt bei.", who="Martina Kühn-Asare",
             mailbox="m.kuehn@uni-wernstadt.de")
    receipt(c, "kassenbon.pdf", ["SUPERMARKT LINDENHOF", "Lindenstraße 40", "35291 Wernstadt", "", "KAFFEE 500G          2 x 7,99",
                                 "TEE SORTIMENT        1 x 3,50", "MINERALWASSER 6X1L   2 x 4,74", "GEBAECK-MISCHUNG     2 x 4,82", "",
                                 "SUMME EUR             38,60", "BAR                   40,00", "BON 4410 KASSE 3 06.10.27 08:10"])
    mail(c, "anschreiben.pdf", kassel=False, subject="Erstattung Bewirtung Delegation Tartu", sender=f"{c.who} &lt;{c.mailbox}&gt;",
         to="Finanzbuchhaltung &lt;kostenerstattung@uni-wernstadt.de&gt;", sent="Do 07.10.2027 09:40", body=paras(t["c506"]["anschreiben"]))
    c.write("teilnehmerliste.pdf", "participant_list", [
        Paragraph("Besuch der Universität Tartu, 06.10.2027 &#8211; Teilnehmende", ms.H1), Spacer(1, 8),
        ms.grid([[Paragraph(x, P) for x in row] for row in [
            ["Name", "Einrichtung", "Gast / intern"], ["Prof. Kadri Tamm", "Universität Tartu", "Gast"], ["Dr. Mihkel Saar", "Universität Tartu", "Gast"],
            ["Liis Kask", "Universität Tartu", "Gast"], ["Jaan Oja", "Universität Tartu", "Gast"], ["Martina Kühn-Asare", "Universität Wernstadt", "intern"]]],
            [5.5 * cm, 6.5 * cm, 3.0 * cm], header=True)])
    exp_trail(c, "Di 12.10.2027 08:30", "Bewirtung externer Gäste im Rahmen üblicher Höflichkeit.")

    # 507 angenommen: regular trip, free-text acceptance and reason
    c = Case("coverage", "trip", 507, "angenommen", "C5", "T01", SRC_TRIP, "Regulärer Antrag, Annahme-E-Mail und Begründung frei formuliert",
             "Rechtzeitiger, vollständiger Antrag; Beitrag angenommen, kein Honorar.", who="Dr. Bastian Kolb-Nnamdi",
             mailbox="b.kolb@uni-kassel.de")
    orga_trip(c, rnr="3381045507", pnr="058400", fg="Fachgebiet Hochschuldidaktik", ziel="Lübeck", ausland=False,
              anlass="Tagung Digitale Lehre 2027", grund="Vortrag", verkehr="Bahn, 2. Klasse", antrag=date(2027, 7, 5),
              start=(date(2027, 9, 22), "14:10"), ende=(date(2027, 9, 24), "21:00"), bstart=(date(2027, 9, 23), "09:00"),
              bend=(date(2027, 9, 24), "15:00"), arbeitstage="3",
              kosten=[("Teilnahmegebühr", 1, 180.00), ("Bahn Kassel&#8211;Lübeck, Hin- und Rückfahrt", 1, 136.00),
                      ("Übernachtung, 2 Nächte à 74,00 &#8364;", 2, 148.00)],
              finanzierung="Fachgebietsbudget, Kostenstelle 4701-02", begruendung=" ".join(paras(t["c507"]["begruendung"])))
    mail(c, "email-annahme.pdf", subject="Digitale Lehre 2027 &#8211; Ihr Beitrag", sender="Programmkomitee Digitale Lehre 2027 &lt;pk@digitale-lehre-2027.example&gt;",
         sent="Mo 28.06.2027 17:30", body=paras(t["c507"]["einladung"]))
    trip_trail(c, "3381045507", "Do 08.07.2027 08:10", "Vollständiger Antrag; Beitrag angenommen.")


# =========================================================================== #
#        Holdout H: a second pair for a quarter of the rules, other surface    #
# =========================================================================== #

def h_trip(c, *, rnr, fg, ziel, ausland, anlass, grund, verkehr, antrag, start, ende, kosten, finanzierung, begruendung,
           hinweis=None, a1=None):
    allgemein = [("Reiseziel:", ziel), ("Anlass:", anlass), ("Grund der Reise:", grund),
                 ("Reise ins Ausland:", "[X] ja &#160; [ ] nein" if ausland else "[ ] ja &#160; [X] nein"),
                 ("Verkehrsmittel:", verkehr), ("Datum der Antragstellung:", de(antrag))]
    verlauf = [("Start:", long_de(start[0], start[1])), ("Ende:", long_de(ende[0], ende[1])),
               ("Beginn Dienstgeschäft:", de(start[0])), ("Ende Dienstgeschäft:", de(ende[0])), ("priv. Aufenthalt:", "keiner"),
               ("Arbeitstage:", str((ende[0] - start[0]).days + 1))] + ([("A1-Bescheinigung:", a1)] if a1 else [])
    synth_trip(c, rnr=rnr, pnr=ref(c, 6), fg=fg, changed=changed_de(antrag), allgemein=allgemein, verlauf=verlauf,
               kosten=[(p, str(q), a) for p, q, a in kosten], finanzierung=finanzierung, begruendung=begruendung,
               antragsdatum=de(antrag), hinweis=hinweis)


def holdout_trip():
    # h01 abgelehnt / h02 angenommen: excluded country vs EU country (T05)
    c = Case("holdout", "trip", "01", "abgelehnt", "H", "T05", SRC_TRIP, "Konferenz in Tel Aviv (Israel), Einladung im E-Mail-Verlauf",
             "Dienstreisen nach Israel werden bis auf Weiteres nicht genehmigt.", who="Dr. Noam Lichtenberg", mailbox="n.lichtenberg@uni-kassel.de")
    h_trip(c, rnr="3381046001", fg="Fachgebiet Kryptographie", ziel="Tel Aviv, ISRAEL", ausland=True, anlass="Cyber Week 2027",
           grund="Vortrag", verkehr="Flug (Economy)", antrag=date(2027, 3, 15), start=(date(2027, 6, 21), "06:00"),
           ende=(date(2027, 6, 24), "23:00"), a1="nicht erforderlich",
           kosten=[("Flug FRA&#8211;TLV, Hin- und Rückflug", 1, 389.00), ("Unterkunft, 3 Nächte", 3, 405.00)],
           finanzierung="Fachgebietsbudget, Kostenstelle 4626-01", begruendung="Vortrag; Einladung und Flugpreisvergleich liegen bei.")
    thread(c, "email-einladung.pdf", subject="Cyber Week 2027 talk", messages=[
        ("Dr. Tamar Levi &lt;t.levi@cyberweek.example&gt;", "So 07.03.2027 09:00", f"{c.who} &lt;{c.mailbox}&gt;",
         ["Dear Noam,", "we would love to have you speak at Cyber Week in Tel Aviv, 22&#8211;23 June 2027. No honorarium, sorry.", "Tamar"]),
        (f"{c.who} &lt;{c.mailbox}&gt;", "Mo 08.03.2027 10:12", "Dr. Tamar Levi &lt;t.levi@cyberweek.example&gt;",
         ["Dear Tamar,", "happy to accept, I will apply for the trip now. Flights FRA&#8211;TLV are 389 EUR, the alternative via Vienna 412 EUR.", "Noam"])])
    c = Case("holdout", "trip", "02", "angenommen", "H", "T05", SRC_TRIP, "Tagung in Nikosia (Zypern), A1 beantragt",
             "Zypern ist nicht ausgeschlossen; Auslandsfeld und A1-Bescheinigung korrekt.", who="Dr. Elena Papadakis-Thiel",
             mailbox="e.papadakis@uni-kassel.de")
    h_trip(c, rnr="3381046002", fg="Fachgebiet Solarenergie", ziel="Nikosia, ZYPERN", ausland=True, anlass="Mediterranean Solar Conference 2027",
           grund="Vortrag", verkehr="Flug (Economy)", antrag=date(2027, 2, 1), start=(date(2027, 5, 10), "05:40"),
           ende=(date(2027, 5, 13), "22:30"), a1="beantragt am 01.02.2027",
           kosten=[("Flug FRA&#8211;LCA, Hin- und Rückflug", 1, 312.00), ("Konferenzgebühr", 1, 380.00), ("Unterkunft, 3 Nächte", 3, 285.00)],
           finanzierung="Drittmittelprojekt SunMed, Kostenstelle 6670-02", begruendung="Vortrag; Annahme und Preisvergleich (Alternative über Athen 351 €) liegen bei.")

    # h03 abgelehnt / h04 angenommen: fee in a speaker agreement vs none (T10)
    c = Case("holdout", "trip", "03", "abgelehnt", "H", "T10", SRC_TRIP, "Referentenvereinbarung mit Vortragshonorar 750 € als Anlage",
             "Die Referentenvereinbarung sieht ein Honorar von 750 € vor: Nebentätigkeit, keine Dienstreise.", who="Prof. Dr. Ulrike Asmussen",
             mailbox="u.asmussen@uni-kassel.de")
    h_trip(c, rnr="3381046003", fg="Fachgebiet Arbeitsrecht", ziel="Düsseldorf", ausland=False, anlass="Personalrätekonferenz NRW 2027",
           grund="Fachvortrag", verkehr="Bahn, 2. Klasse", antrag=date(2027, 8, 16), start=(date(2027, 10, 14), "07:10"),
           ende=(date(2027, 10, 14), "20:40"), kosten=[("Bahn Kassel&#8211;Düsseldorf, Hin- und Rückfahrt", 1, 112.00)],
           finanzierung="Professurbudget, Kostenstelle 4105-00", begruendung="Vortrag; Vereinbarung liegt bei.")
    c.write("referentenvereinbarung.pdf", "agreement", ms.letter(
        vendor="Bildungswerk Mitbestimmung e.V.", vendor_lines=["Kaiserswerther Str. 70", "40477 Düsseldorf"],
        recipient=["Prof. Dr. Ulrike Asmussen", "Universität Kassel", "Fachgebiet Arbeitsrecht", "34109 Kassel"],
        refs=[("Datum:", "02.08.2027")], heading="Referentenvereinbarung",
        intro="§ 1 Frau Prof. Dr. Asmussen hält am 14.10.2027 einen Vortrag (60 Minuten) zum Thema &#8222;Mitbestimmung bei KI-Systemen&#8220;.<br/>"
              "§ 2 Für den Vortrag erhält die Referentin ein Honorar von 750,00 &#8364; zuzüglich gesetzlicher Umsatzsteuer.<br/>"
              "§ 3 Reisekosten werden nicht erstattet.", closing="Für das Bildungswerk"))
    c = Case("holdout", "trip", "04", "angenommen", "H", "T10", SRC_TRIP, "Englische Einladung zu einem Gastvortrag, ausdrücklich ohne Honorar",
             "Kein Honorar; dienstliches Interesse durch die Einladung belegt.", who="Dr. Kofi Mensah-Behrens", mailbox="k.mensah@uni-kassel.de")
    h_trip(c, rnr="3381046004", fg="Fachgebiet Wasserbau", ziel="Delft, NIEDERLANDE", ausland=True, anlass="Guest lecture TU Delft",
           grund="Gastvortrag", verkehr="Bahn, 2. Klasse", antrag=date(2027, 9, 6), start=(date(2027, 11, 16), "06:30"),
           ende=(date(2027, 11, 17), "21:00"), a1="beantragt am 06.09.2027",
           kosten=[("Bahn Kassel&#8211;Delft, Hin- und Rückfahrt", 1, 172.00), ("Unterkunft, 1 Nacht", 1, 95.00)],
           finanzierung="Fachgebietsbudget, Kostenstelle 4318-02", begruendung="Gastvortrag; Einladung liegt bei.")
    c.write("invitation.pdf", "correspondence", ms.email(mailbox=c.mailbox, url=OWA_KASSEL + "H", subject="Guest lecture in Delft",
            sender="Prof. Marijke de Vries &lt;m.devries@tudelft.example&gt;", sent="Tue 31.08.2027 15:00", to=f"{c.who} &lt;{c.mailbox}&gt;",
            body=["Dear Dr. Mensah-Behrens,", "we would be glad if you could give a guest lecture on 16 November 2027 in our "
                  "hydraulic engineering seminar. We are unfortunately not able to offer an honorarium.", "Kind regards,<br/>Marijke de Vries"]))

    # h05 abgelehnt / h06 angenommen: domestic flight without vs with documented reason (T14)
    c = Case("holdout", "trip", "05", "abgelehnt", "H", "T14", SRC_TRIP, "Inlandsflug Köln/Bonn–Berlin 248 €, Bahn 132 €, keine Gründe",
             "Inlandsflug teurer als die Bahn ohne dargelegte dienstliche Gründe.", who="Dr. Bettina Kowalczyk-Ruiz", mailbox="b.kowalczyk@uni-kassel.de")
    h_trip(c, rnr="3381046005", fg="Fachgebiet Stadtplanung", ziel="Berlin", ausland=False, anlass="Sitzung Beirat Stadtentwicklung",
           grund="Beiratssitzung", verkehr="Flug Köln/Bonn&#8211;Berlin", antrag=date(2027, 4, 12), start=(date(2027, 5, 18), "05:30"),
           ende=(date(2027, 5, 18), "22:00"), kosten=[("Flug CGN&#8211;BER&#8211;CGN", 1, 248.00), ("Bahn Kassel&#8211;Köln/Bonn Flughafen", 1, 72.00)],
           finanzierung="Fachgebietsbudget, Kostenstelle 4410-01", begruendung="Beiratssitzung 10&#8211;16 Uhr.",
           hinweis="Zum Vergleich: Bahn Kassel&#8211;Berlin Hin- und Rückfahrt 132,00 €.")
    c = Case("holdout", "trip", "06", "angenommen", "H", "T14", SRC_TRIP, "Inlandsflug teurer als die Bahn, Arbeitszeitersparnis in einer Anlage dargelegt",
             "Besondere dienstliche Gründe (wesentliche Einsparung von Arbeitszeit, Prüfungstermin am Vormittag) sind in einer Anlage dargelegt.",
             who="Prof. Dr. Henrik Solberg", mailbox="h.solberg@uni-kassel.de")
    h_trip(c, rnr="3381046006", fg="Fachgebiet Verkehrsplanung", ziel="Rostock", ausland=False, anlass="Berufungskommission Universität Rostock",
           grund="Externes Kommissionsmitglied", verkehr="Flug Frankfurt&#8211;Rostock", antrag=date(2027, 1, 18),
           start=(date(2027, 2, 24), "05:20"), ende=(date(2027, 2, 24), "21:30"),
           kosten=[("Flug FRA&#8211;RLG&#8211;FRA", 1, 214.00), ("Bahn Kassel&#8211;Frankfurt Flughafen", 1, 58.00)],
           finanzierung="Professurbudget, Kostenstelle 4440-00", begruendung="Mitwirkung in der Berufungskommission; Begründung des Flugs in der Anlage.")
    c.write("anlage-begruendung-flug.pdf", "justification", [
        Paragraph("Anlage zum Dienstreiseantrag 3381046006: Begründung der Flugnutzung", ms.H1), Spacer(1, 8),
        Paragraph("Die Sitzung der Berufungskommission beginnt am 24.02.2027 um 08:30 Uhr mit den Probevorträgen. Mit der Bahn "
                  "(Kassel ab 04:52 Uhr, Rostock an 11:24 Uhr, Bahn 176,00 €) wäre eine Teilnahme erst ab Mittag möglich; eine "
                  "Anreise am Vortag kostet zusätzlich eine Übernachtung. Der Flug ab Frankfurt (06:55 Uhr, an 08:05 Uhr) spart "
                  "rund drei Stunden Reisezeit je Richtung und ermöglicht die Teilnahme an allen Vorträgen.", P)])

    # h19 abgelehnt / h20 angenommen: online-only programme vs on-site hybrid (T11)
    c = Case("holdout", "trip", "19", "abgelehnt", "H", "T11", SRC_TRIP, "Antrag nennt Berlin, laut Programm findet die Tagung ausschließlich digital statt",
             "Die Veranstaltung findet laut Programm ausschließlich digital statt; Online-Tagungen sind keine Dienstreisen.",
             who="Dr. Oskar Lindahl-Mbeki", mailbox="o.lindahl@uni-kassel.de")
    h_trip(c, rnr="3381046019", fg="Fachgebiet Berufspädagogik", ziel="Berlin", ausland=False, anlass="Forum Berufliche Bildung 2027",
           grund="Teilnahme", verkehr="Bahn, 2. Klasse", antrag=date(2027, 1, 25), start=(date(2027, 3, 9), "06:15"),
           ende=(date(2027, 3, 10), "20:00"), kosten=[("Teilnahmegebühr", 1, 90.00), ("Bahn Kassel&#8211;Berlin", 1, 132.00),
                                                       ("Übernachtung, 1 Nacht", 1, 78.00)],
           finanzierung="Fachgebietsbudget, Kostenstelle 4210-03", begruendung="Teilnahme am Forum; Programm liegt bei.")
    c.write("programm-forum.pdf", "programme", ms.letter(vendor="Forum Berufliche Bildung", vendor_lines=["Geschäftsstelle", "10117 Berlin"],
            recipient=["Programm 9.&#8211;10. März 2027"], refs=[("Stand:", "15.01.2027")], heading="Programm",
            intro="Das Forum findet 2027 <b>ausschließlich digital</b> statt. Die Zugangsdaten erhalten Sie nach der Anmeldung. "
                  "Teilnahmegebühr 90 EUR."))
    c = Case("holdout", "trip", "20", "angenommen", "H", "T11", SRC_TRIP, "Hybride Tagung in Leipzig, Vortrag vor Ort laut Programm",
             "Teilnahme und Vortrag vor Ort; die Tagung ist hybrid, nicht online.", who="Dr. Ida Kronberg-Asante", mailbox="i.kronberg@uni-kassel.de")
    h_trip(c, rnr="3381046020", fg="Fachgebiet Sportwissenschaft", ziel="Leipzig", ausland=False, anlass="Sportwissenschaftlicher Hochschultag 2027 (hybrid)",
           grund="Vortrag vor Ort", verkehr="Bahn, 2. Klasse", antrag=date(2027, 6, 14), start=(date(2027, 9, 15), "07:30"),
           ende=(date(2027, 9, 16), "19:50"), kosten=[("Tagungsgebühr Präsenz", 1, 160.00), ("Bahn Kassel&#8211;Leipzig", 1, 98.00),
                                                        ("Übernachtung, 1 Nacht", 1, 77.00)],
           finanzierung="Fachgebietsbudget, Kostenstelle 4810-01", begruendung="Vortrag; Programm liegt bei.")
    c.write("programm.pdf", "programme", ms.letter(vendor="dvs Hochschultag 2027", vendor_lines=["Universität Leipzig", "04109 Leipzig"],
            recipient=["Programmauszug"], refs=[("Stand:", "01.06.2027")], heading="Programm",
            intro="Hybride Durchführung: Präsenz im Hörsaalgebäude Augustusplatz mit Übertragung. Vorträge finden vor Ort statt.<br/>"
                  "15.09.2027, 14:00 Uhr, Hörsaal 9: Kronberg-Asante, &#8222;Belastungssteuerung im Nachwuchsleistungssport&#8220;."))


def h_receipt_case(number, label, rule, source, pattern, why, who, mailbox, lines, note):
    c = Case("holdout", "exp", number, label, "H", rule, source, pattern, why, who=who, mailbox=mailbox)
    receipt(c, "beleg.pdf", lines, note=note)
    exp_trail(c, "Mo 01.03.2027 09:00", why)
    return c


def holdout_expense():
    c = Case("holdout", "exp", "07", "abgelehnt", "H", "E10", SRC_FRAME, "Bürodrehstuhl online privat gekauft und eingereicht",
             "Für Bürodrehstühle besteht ein verbindlicher Rahmenvertrag; ein privater Kauf wird nicht erstattet.",
             who="Ute Brockhaus-Sallah", mailbox="u.brockhaus@uni-wernstadt.de")
    c.write("rechnung.pdf", "invoice", ms.invoice(vendor="Sitzwelt Online GmbH", vendor_lines=["Möbelring 3", "32052 Herford"],
            recipient=["Universität Wernstadt", "Prüfungsamt FB 71", "z. Hd. Ute Brockhaus-Sallah", *ms.WERN_ADDR],
            refs=[("Rechnung Nr.", "SW-27-30018"), ("Datum:", "11.01.2027")], items=[("Bürodrehstuhl ergonomisch, Synchronmechanik", 1, 259.00)],
            notes=["Bezahlt per PayPal."])[0])
    exp_trail(c, "Do 21.01.2027 10:00", "Bürodrehstühle sind über den Rahmenvertrag zu bestellen.")
    h_receipt_case("08", "angenommen", "E10", SRC_FRAME, "Akku-Bohrschrauber für die Werkstatt, Zweck vermerkt",
                   "Kein Rahmenvertragsprodukt, kleine Anschaffung mit Zweckvermerk.", "Arne Feddersen", "a.feddersen@uni-wernstadt.de",
                   ["WERKZEUG KAISER", "Kasseler Str. 9", "35091 Cölbe", "", "AKKU-BOHRSCHRAUBER 18V 1 x 119,00", "BIT-SET 32TLG       1 x 12,90",
                    "", "SUMME EUR           131,90", "EC-KARTE            131,90", "BON 7781 KASSE 2 03.02.27 09:14"],
                   ["Für Werkstatt Fachgebiet Fertigungstechnik, Halle 2", "(A. Feddersen)"])
    h_receipt_case("09", "abgelehnt", "E12", SRC_FIN, "Gastgeschenk 34,90 € bei einer Dienstreise nach Brno",
                   "Gastgeschenke bis 30,00 €; 34,90 € liegen darüber.", "Dr. Petr Hladik-Brenner", "p.hladik@uni-wernstadt.de",
                   ["FEINKOST LAHNTAL", "Marktplatz 2", "35291 Wernstadt", "", "PRAESENTKORB KLEIN  1 x 34,90", "", "SUMME EUR            34,90",
                    "EC-KARTE             34,90", "BON 2208 KASSE 1 05.04.27 17:02"],
                   ["Gastgeschenk für Gastgeber TU Brno,", "Dienstreise 07.-08.04.2027 (P. Hladik-Brenner)"])
    h_receipt_case("10", "angenommen", "E12", SRC_FIN, "Gastgeschenk 19,90 € bei einer Dienstreise nach Wrocław",
                   "Gastgeschenk unter 30,00 € bei einer Dienstreise.", "Dr. Agnieszka Brandt", "a.brandt@uni-wernstadt.de",
                   ["FEINKOST LAHNTAL", "Marktplatz 2", "35291 Wernstadt", "", "WERNSTAEDTER SENF-SET 1 x 19,90", "", "SUMME EUR             19,90",
                    "BAR                   20,00", "BON 2391 KASSE 1 12.04.27 12:40"],
                   ["Gastgeschenk für Gastgeber TU Breslau,", "Dienstreise 14.-15.04.2027 (A. Brandt)"])
    h_receipt_case("11", "abgelehnt", "E11", SRC_FIN, "Blumenschmuck und Tischdekoration für ein Institutsjubiläum",
                   "Schmuck- und Dekorationsartikel sind nicht erstattungsfähig.", "Ingeborg Matthiesen", "i.matthiesen@uni-wernstadt.de",
                   ["BLUMEN WEBER", "Lindenallee 1", "35291 Wernstadt", "", "TISCHGESTECK         4 x 18,50", "DEKO-STREUTEILE      2 x 4,90",
                    "", "SUMME EUR             83,80", "EC-KARTE              83,80", "BON 0081 KASSE 1 24.06.27 10:12"],
                   ["Deko für 25-Jahr-Feier Institut", "(I. Matthiesen)"])
    h_receipt_case("12", "angenommen", "E11", SRC_FIN, "Moderationsmaterial für einen Workshop",
                   "Arbeitsmaterial mit dienstlichem Zweck, keine Dekoration.", "Dr. Leonard Abiodun-Weiss", "l.abiodun@uni-wernstadt.de",
                   ["BUEROMARKT HESSEN", "Gutenbergstr. 4", "35037 Marburg", "", "MODERATIONSKARTEN 500 1 x 14,90",
                    "PINNWANDPAPIER 10 BG 1 x 12,40", "FILZSTIFTE 10ER      2 x 8,95", "", "SUMME EUR             45,20",
                    "EC-KARTE              45,20", "BON 6620 KASSE 4 02.03.27 15:45"],
                   ["Für Strategieworkshop Lehrstuhl am 03.03.", "(L. Abiodun-Weiss)"])


def holdout_procurement():
    fg = "Fachgebiet Kältetechnik"
    c = Case("holdout", "proc", "13", "abgelehnt", "H", "P03", SRC_PROC, "Kostenstellenbevollmächtigte im Ausland und nicht erreichbar, Antrag ohne Beauftragung",
             "Die Bestellung ist nicht von der Kostenstellenbevollmächtigten beauftragt.", who="Dr. Raphael Okonkwo-Stein",
             mailbox="r.okonkwo@uni-wernstadt.de")
    item = [("Kältemittel-Absauggerät", 1, 1640.00)]
    write_offers(c, fg, [("Kälte-Service Nordhorn", ["Am Kanal 3", "48529 Nordhorn"], "KSN-27-202", "03.05.2027", item),
                         ("Klimatechnik Eder", ["Bergstr. 5", "83278 Traunstein"], "KE-27-0505", "04.05.2027", [(item[0][0], 1, 1715.00)]),
                         ("Frigotec Halle", ["Saalestr. 8", "06108 Halle"], "FH-0410", "04.05.2027", [(item[0][0], 1, 1760.00)])])
    proc_form(c, number="ZB-2027-1013", date="06.05.2027", fachgebiet=fg, phone="0561 7390-4910", kostenstelle="71 4910 / Auftrag 2141013",
              holder="Prof. Dr. Astrid Thorsen", category="Anlage", framework=False, procedure="Preisvergleich, drei schriftliche Angebote",
              offers=3, supplier="Kälte-Service Nordhorn (Angebot KSN-27-202)", items=item, signed=False,
              begruendung="Gerät für die Wartung der Prüfstände. Prof. Thorsen ist bis Juni im Ausland und nicht erreichbar; ich "
                          "stelle den Antrag, damit das Angebot nicht verfällt.")
    c = Case("holdout", "proc", "14", "angenommen", "H", "P03", SRC_PROC, "Bestellung per E-Mail, Kostenstellenbevollmächtigte in Kopie hat beauftragt",
             "Die Kostenstellenbevollmächtigte ist in Kopie und hat beauftragt; Direktvergabe unter 1.000 €.", who="Merle Thiessen",
             mailbox="m.thiessen@uni-wernstadt.de")
    item = [("Thermoelement-Messmodul 8 Kanäle", 2, 389.00)]
    write_offers(c, fg, [("Datalog Systeme Kiel", ["Werftstraße 1", "24143 Kiel"], "DSK-27-0711", "05.07.2027", item)])
    mail(c, "email-bestellung.pdf", kassel=False, doc_type="application", subject="Direktauftrag Messmodule", sender=f"Merle Thiessen &lt;{c.mailbox}&gt;",
         to="beschaffung@uni-wernstadt.de", cc="Prof. Dr. Astrid Thorsen &lt;a.thorsen@uni-wernstadt.de&gt;", sent="Mi 07.07.2027 09:30",
         body=["Sehr geehrte Damen und Herren,", "bitte bestellen Sie gemäß Angebot DSK-27-0711 zwei Thermoelement-Messmodule zu je "
               "389,00 &#8364; netto (778,00 &#8364; netto). Unter 1.000 &#8364; habe ich nur ein Angebot eingeholt.",
               "Frau Prof. Thorsen ist in Kopie und hat die Bestellung beauftragt. Kostenstelle 71 4910.", "Viele Grüße<br/>Merle Thiessen"])

    fg = "Fachgebiet Tieftemperaturphysik"
    c = Case("holdout", "proc", "15", "abgelehnt", "H", "P08", SRC_FRAME, "Flüssigstickstoff beim örtlichen Lieferanten mit drei Angeboten",
             "Für Flüssigstickstoff besteht ein Rahmenvertrag mit Linde; Bestellung bei Dritten ist unzulässig.", who="Dr. Sören Valentin-Achebe",
             mailbox="s.valentin@uni-wernstadt.de")
    ln2 = [("Stickstoff flüssig, Lieferung in Kryobehälter", 1800, 0.62)]
    write_offers(c, fg, [("Kryo-Service Gießen", ["Am Urnenfeld 4", "35396 Gießen"], "KSG-27-118", "10.02.2027", ln2),
                         ("Gasversorgung Vogelsberg", ["Industriestr. 2", "36304 Alsfeld"], "GV-27-0213", "11.02.2027", [(ln2[0][0], 1800, 0.66)]),
                         ("TechGas Hanau", ["Kinzigstr. 7", "63450 Hanau"], "TGH-0212", "12.02.2027", [(ln2[0][0], 1800, 0.69)])])
    proc_form(c, number="ZB-2027-1015", date="15.02.2027", fachgebiet=fg, phone="0561 7390-4930", kostenstelle="71 4930 / Auftrag 2141015",
              holder="Prof. Dr. Kai Brömmelhaus", category="Verbrauchsmaterial", framework=False, procedure="Preisvergleich, drei schriftliche Angebote",
              offers=3, supplier="Kryo-Service Gießen (Angebot KSG-27-118)", items=ln2, begruendung="Kühlung der Kryostaten im Sommersemester.")
    c = Case("holdout", "proc", "16", "angenommen", "H", "P08", SRC_FRAME, "Argon aus dem WPS-Katalog Rahmenvertrag Flaschengase",
             "Abruf aus dem Rahmenvertrag über WPS.", who="Hanna Krüger-Oduya", mailbox="h.krueger@uni-wernstadt.de")
    gas = [("LG-AR46-50", "Argon 4.6, Flasche 50 l, Füllung", 4, 118.70)]
    cart, _ = ms.wps_cart(number="WK-0027-30416", catalog="Rahmenvertrag Flaschengase (außer Helium)", supplier="Linde GmbH, Pullach",
                          created="22.03.2027", buyer=c.who, account="71 4930 / Auftrag 2141016", items=gas)
    c.write("warenkorb.pdf", "framework_cart", cart)
    proc_form(c, number="ZB-2027-1016", date="22.03.2027", fachgebiet=fg, phone="0561 7390-4931", kostenstelle="71 4930 / Auftrag 2141016",
              holder="Prof. Dr. Kai Brömmelhaus", category="Verbrauchsmaterial", framework=True, procedure="Abruf Rahmenvertrag (WPS)",
              offers=0, supplier="Linde GmbH (Rahmenvertragspartner)", items=[(d, q, u) for _, d, q, u in gas],
              begruendung="Schutzgas für die Probenpräparation; Warenkorb aus dem Rahmenvertrag anbei.")

    fg = "Fachgebiet Akustik"
    for number, label, units, why in (("17", "abgelehnt", 3, "Auftragswert 1.050,00 € netto: drei Angebote erforderlich, nur eines liegt vor."),
                                      ("18", "angenommen", 2, "Auftragswert 960,00 € netto unter 1.000 €: Direktvergabe mit einem Angebot.")):
        c = Case("holdout", "proc", number, label, "H", "P01", SRC_CATER, f"Ein Angebot über {units} Messmikrofone", why,
                 who="Dr. Julian Ebersbach", mailbox="j.ebersbach@uni-wernstadt.de")
        mics = [("Messmikrofon Klasse 1 mit Vorverstärker", units, 330.00 if units == 3 else 420.00), ("Kalibrator 94 dB", 1, 60.00 if units == 3 else 120.00)]
        write_offers(c, fg, [("Akustiktechnik Rinteln", ["Weserstr. 3", "31737 Rinteln"], "AR-27-0606", "07.06.2027", mics)])
        proc_form(c, number=f"ZB-2027-10{number}", date="09.06.2027", fachgebiet=fg, phone="0561 7390-4950", kostenstelle="71 4950 / Auftrag 2141017",
                  holder="Prof. Dr. Grete Wallin", category="GWG", framework=False, procedure="Direktvergabe", offers=1,
                  supplier="Akustiktechnik Rinteln (Angebot AR-27-0606)", items=mics, begruendung="Messmikrofone für das Raumakustik-Praktikum.")


# --------------------------------------------------------------------------- #

def main():
    global OUT
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--corpora", type=Path, default=DEFAULT_CORPORA)
    parser.add_argument("--generate-c5", action="store_true", help="write the C5 texts with the writer model (needs OPENROUTER_API_KEY)")
    args = parser.parse_args()
    OUT = args.out
    texts_path = OUT / "c5-texts.json"
    if args.generate_c5:
        generate_c5_texts(texts_path)
    C5_TEXTS.update(json.loads(texts_path.read_text(encoding="utf-8")))
    rl_config.invariant = 1  # byte-identical PDFs on every run
    for set_name in ("coverage", "holdout"):
        for suffix, _ in KINDS.values():
            for part in ("inputs", "decision-trail"):
                shutil.rmtree(OUT / f"{set_name}-{suffix}" / part, ignore_errors=True)
    for build in (c1_trip, c1_expense, c1_procurement, c2_trip, c2_exp_proc, c3_trip, c3_expense, c3_procurement, c4_trip,
                  c4_expense, c4_procurement, c5_cases, holdout_trip, holdout_expense, holdout_procurement):
        build()
    for set_name in ("coverage", "holdout"):
        rows = [c.record for c in CASES if c.record["dataset"].startswith(set_name)]
        with open(OUT / f"cases-{set_name}.jsonl", "w", encoding="utf-8", newline="\n") as f:
            f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
        for suffix, _ in KINDS.values():
            dataset = f"{set_name}-{suffix}"
            subset = [r for r in rows if r["dataset"] == dataset]
            with open(OUT / dataset / "ground-truth.jsonl", "w", encoding="utf-8", newline="\n") as f:
                f.writelines(json.dumps({"antrag": r["antrag"], "result": r["label"]}) + "\n" for r in subset)
            if args.corpora.is_dir():
                link_corpora(args.corpora, OUT / dataset / "inputs" / "retrieval-corpora")
            print(f"{dataset}: {len(subset)} cases, {sum(r['label'] == 'angenommen' for r in subset)} angenommen")


if __name__ == "__main__":
    main()
