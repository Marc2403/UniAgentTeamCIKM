"""Render the synthetic Task 2 cases (business trip, expense, procurement) as PDFs.

Everything here is invented. Layouts follow the official spot-check sets; the rules come from the
University of Kassel pages in `university-kassel-public-de` (doc_ids in `cases.jsonl`).

    python make_synthetic.py [--out datasets] [--corpora <dir with hessian-law-de/ ...>]

Writes per dataset: inputs/<case>/*.pdf, inputs/retrieval-corpora/ (hard links) and ground-truth.jsonl;
next to the datasets cases.jsonl (label, pattern, rule, source, whether the pattern is new to the spot-checks).
"""
import argparse
import json
import os
import shutil
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

HERE = Path(__file__).resolve().parent
DEFAULT_CORPORA = HERE.parents[2] / "uniagent-code/cikm26/datasets/business-trip-spot-check/inputs/retrieval-corpora"

TRIP = "synthetic-business-trip"
EXPENSE = "synthetic-expense-reimbursement"
PROCUREMENT = "synthetic-procurement"

SRC_TRIP = "8f78f05e-61f4-4f5f-ba79-35b18e2c4a0f"  # Dienstreisemanagement - INTERN
SRC_FIN = "df8a9f54-11b5-4f4f-b15e-146d3bca69d3"  # Finanzbuchhaltung und Steuern - INTERN
SRC_PROC = "8521d5be-7a95-4cad-aaf4-3b2a76860857"  # Beschaffung - INTERN
SRC_FRAME = "aef7cd6c-7609-4ac8-84ec-228bc79e5a4e"  # Rahmenverträge - INTERN
SRC_CATER = "08143d1c-7e2f-4f9c-b6e0-42969f36852f"  # Nachhaltiges Catering - INTERN (1.000-EUR-Grenze)

GREY = colors.HexColor("#666666")
LIGHT = colors.HexColor("#efefef")
LINE = colors.HexColor("#b4b4b4")
RED = colors.HexColor("#b3261e")
BLUE = colors.HexColor("#1f3c88")

P = ParagraphStyle("p", fontName="Helvetica", fontSize=9, leading=12)
PS = ParagraphStyle("ps", parent=P, fontSize=7.5, leading=9.5, textColor=GREY)
PB = ParagraphStyle("pb", parent=P, fontName="Helvetica-Bold")
H1 = ParagraphStyle("h1", parent=P, fontName="Helvetica-Bold", fontSize=14, leading=18)
H2 = ParagraphStyle("h2", parent=P, fontName="Helvetica-Bold", fontSize=10, leading=14, spaceBefore=8, spaceAfter=3)
RIGHT = ParagraphStyle("r", parent=P, alignment=2)
RIGHTS = ParagraphStyle("rs", parent=PS, alignment=2)
MONO = ParagraphStyle("mono", fontName="Courier", fontSize=8.5, leading=10.5)
HAND = ParagraphStyle("hand", fontName="Helvetica-Oblique", fontSize=10, leading=13, textColor=BLUE)
STAMP = ParagraphStyle("stamp", fontName="Helvetica-Bold", fontSize=10, leading=12, textColor=RED, alignment=1)

CASES = []  # one record per case, written to cases.jsonl
OUT = HERE / "datasets"


def eur(x, sign="€"):
    s = f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{s} {sign}" if sign else s


def case(dataset, number, result, pattern, rule, source, new, uncertain=False):
    prefix = {TRIP: "dienstreiseantrag", EXPENSE: "auslagenerstattung", PROCUREMENT: "beschaffungsantrag"}[dataset]
    case_id = f"{prefix}-{number:02d}"
    CASES.append({"dataset": dataset, "antrag": case_id, "result": result, "pattern": pattern,
                  "rule": rule, "source_doc_id": source, "new_pattern": new, "uncertain": uncertain})
    return OUT / dataset / "inputs" / case_id


def write(path, *stories, pagesize=A4, margins=(2.2 * cm, 2.0 * cm, 2.0 * cm, 1.8 * cm)):
    """One PDF; several stories become consecutive pages (a scanned bundle)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    left, right, top, bottom = margins
    doc = SimpleDocTemplate(str(path), pagesize=pagesize, leftMargin=left, rightMargin=right, topMargin=top,
                            bottomMargin=bottom, title=path.name, author="", subject="", creator="")
    flow = []
    for i, story in enumerate(stories):
        if i:
            flow.append(PageBreak())
        flow += story
    doc.build(flow)


def grid(rows, widths, header=False, style=()):
    t = Table(rows, colWidths=list(widths))
    base = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 1.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5)]
    if header:
        base += [("BACKGROUND", (0, 0), (-1, 0), LIGHT), ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.black),
                 ("LINEBELOW", (0, 1), (-1, -1), 0.25, colors.HexColor("#e2e2e2")),
                 ("LEFTPADDING", (0, 0), (-1, -1), 3), ("TOPPADDING", (0, 0), (-1, -1), 3),
                 ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]
    t.setStyle(TableStyle(base + list(style)))
    return t


def kv(rows, widths=(5.4 * cm, 11.0 * cm)):
    return grid([[Paragraph(k, P), Paragraph(v, P)] for k, v in rows], widths,
                style=[("LINEBELOW", (0, 0), (-1, -2), 0.25, colors.HexColor("#e2e2e2"))])


def stamp(*lines):
    return grid([[Paragraph("<br/>".join(lines), STAMP)]], [6.0 * cm],
                style=[("BOX", (0, 0), (-1, -1), 1.2, RED), ("TOPPADDING", (0, 0), (-1, -1), 4),
                       ("BOTTOMPADDING", (0, 0), (-1, -1), 4), ("LEFTPADDING", (0, 0), (-1, -1), 4)])


# --------------------------------------------------------------------------- #
# Document types
# --------------------------------------------------------------------------- #

FB16 = ["Universität Kassel", "Fachbereich 16", "Elektrotechnik / Informatik", "Wilhelmshöher Allee 71-73",
        "34121 Kassel"]


def trip_form(*, reisenummer, name, fachgebiet, personalnummer, geaendert, allgemein, verlauf, kosten,
              finanzierung, begruendung, antragsdatum, hinweis=None):
    total = sum(amount for _, _, amount in kosten)
    st = [grid([[Paragraph("<br/>".join([f"<b>{name}</b>", fachgebiet, f"Personalnummer {personalnummer}"]), P),
                 Paragraph("<br/>".join(FB16), RIGHTS)]], [8.4 * cm, 8.0 * cm]), Spacer(1, 6),
          grid([[Paragraph("Seite 1 von 1", PS),
                 Paragraph(f"Zuletzt geändert am: {geaendert}<br/>Status: Antrag eingereicht<br/>Genehmigt von: ---",
                           RIGHTS)]], [8.4 * cm, 8.0 * cm]), Spacer(1, 10),
          Paragraph("ANTRAG AUF DIENSTREISEGENEHMIGUNG", H1),
          Paragraph(f"vor Antritt der Reise einzureichen &#183; Reisenummer {reisenummer}", PS), Spacer(1, 10),
          Paragraph("Allgemeine Daten", H2), kv(allgemein), Paragraph("Reiseverlauf", H2), kv(verlauf),
          Paragraph("Voraussichtliche Kosten (Schätzung)", H2)]
    rows = [[Paragraph("<b>Position</b>", P), Paragraph("<b>Menge</b>", RIGHT), Paragraph("<b>Betrag</b>", RIGHT)]]
    rows += [[Paragraph(pos, P), Paragraph(qty, RIGHT), Paragraph(eur(amount), RIGHT)] for pos, qty, amount in kosten]
    rows += [[Paragraph("<b>Summe (Schätzung)</b>", P), Paragraph("", P), Paragraph(f"<b>{eur(total)}</b>", RIGHT)]]
    st += [grid(rows, [10.6 * cm, 3.0 * cm, 2.8 * cm], header=True,
                style=[("LINEABOVE", (0, -1), (-1, -1), 0.6, colors.black)]),
           Spacer(1, 4), kv([("Finanzierung:", finanzierung)]),
           Paragraph("Kurzbegründung", H2), Paragraph(begruendung, P)]
    if hinweis:
        st += [Spacer(1, 6), Paragraph(f"<b>Hinweis der/des Antragsteller:in:</b> {hinweis}", P)]
    st += [Spacer(1, 18),
           grid([[Paragraph(f"Datum: {antragsdatum}", P), Paragraph(f"Unterschrift Antragsteller:in: {name}", RIGHT)]],
                [6.0 * cm, 10.4 * cm], style=[("LINEABOVE", (0, 0), (-1, 0), 0.5, LINE),
                                              ("TOPPADDING", (0, 0), (-1, -1), 6)]),
           Spacer(1, 14), Paragraph("Erstellt durch ESS-Reisemanagement &#183; Universität Kassel", PS)]
    return st


def email(*, mailbox, url, subject, sender, sent, to, body, cc=None, quoted=(), printed=None):
    st = [grid([[Paragraph(f"E-Mail – {mailbox}", PS), Paragraph(url, RIGHTS)]], [8.0 * cm, 8.4 * cm],
               style=[("LINEBELOW", (0, 0), (-1, 0), 0.4, colors.HexColor("#dddddd"))]), Spacer(1, 10),
          Paragraph(subject, H1), Spacer(1, 8), Paragraph(f"<b>{sender}</b>", P), Paragraph(sent, PS), Spacer(1, 4),
          Paragraph(f"An: {to}", PS)]
    if cc:
        st.append(Paragraph(f"Cc: {cc}", PS))
    st.append(Spacer(1, 12))
    st += [x for para in body for x in (Paragraph(para, P), Spacer(1, 6))]
    for q in quoted:
        st += [Spacer(1, 4), grid([[""]], [16.4 * cm], style=[("LINEABOVE", (0, 0), (-1, 0), 0.5, LINE)]),
               Paragraph("<br/>".join([f"<b>Von:</b> {q['from']}", f"<b>Gesendet:</b> {q['sent']}",
                                       f"<b>An:</b> {q['to']}"] + ([f"<b>Cc:</b> {q['cc']}"] if q.get("cc") else [])
                                      + [f"<b>Betreff:</b> {q['subject']}"]), PS), Spacer(1, 6)]
        st += [x for para in q["body"] for x in (Paragraph(para, P), Spacer(1, 6))]
    st += [Spacer(1, 10), Paragraph(f"Seite 1 &#160;&#160;&#160; {printed or sent[3:]}", PS)]
    return st


def letter(*, vendor, vendor_lines, recipient, refs, heading, intro=None, table=None, sums=None, notes=(),
           closing=None, footer=None, extra=()):
    """Vendor document (offer, invoice, booking, confirmation) with free-form item table."""
    st = [grid([[Paragraph("<br/>".join(recipient), P),
                 Paragraph("<br/>".join([f"<b>{vendor}</b>"] + vendor_lines), RIGHTS)]], [9.4 * cm, 7.0 * cm]),
          Spacer(1, 12),
          grid([[Paragraph("", P), Paragraph("<br/>".join(f"{k} {v}" for k, v in refs), RIGHTS)]],
               [9.4 * cm, 7.0 * cm]), Spacer(1, 12), Paragraph(heading, H1)]
    if intro:
        st += [Spacer(1, 2), Paragraph(intro, P)]
    st.append(Spacer(1, 10))
    if table:
        head, rows, widths = table
        data = [[Paragraph(f"<b>{c}</b>", RIGHT if i else P) for i, c in enumerate(head)]]
        data += [[Paragraph(str(c), RIGHT if i else P) for i, c in enumerate(r)] for r in rows]
        st += [grid(data, widths, header=True), Spacer(1, 8)]
    if sums:
        st += [grid([[Paragraph(k, RIGHT), Paragraph(v, RIGHT)] for k, v in sums], [13.4 * cm, 3.0 * cm],
                    style=[("LINEABOVE", (0, -1), (-1, -1), 0.6, colors.black),
                           ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold")]), Spacer(1, 12)]
    for n in notes:
        st += [Paragraph(n, PS), Spacer(1, 4)]
    st += list(extra)
    if closing:
        st += [Spacer(1, 8), Paragraph(closing, P), Paragraph(vendor, P)]
    if footer:
        st += [Spacer(1, 16), Paragraph(footer, PS)]
    return st


def priced(items, vat=0.19):
    """Item rows (desc, qty, unit net) -> table rows, net, vat, gross."""
    rows, net = [], 0.0
    for desc, qty, unit in items:
        line = round(qty * unit, 2)
        net = round(net + line, 2)
        rows.append([desc, str(qty), eur(unit), eur(line)])
    tax = round(net * vat, 2)
    return rows, net, tax, round(net + tax, 2)


ITEM_HEAD = (["Bezeichnung", "Menge", "EP netto", "GP netto"], [9.6 * cm, 1.6 * cm, 2.6 * cm, 2.6 * cm])


def offer(*, vendor, vendor_lines, recipient, number, date, valid, items, heading="Angebot", vat=0.19,
          notes=(), lang="de"):
    rows, net, tax, gross = priced(items, vat)
    if lang == "en":
        refs = [("Quotation no.", number), ("Date", date), ("Valid until", valid)]
        head = (["Description", "Qty", "Unit net", "Total net"], ITEM_HEAD[1])
        sums = [("Total net", eur(net)), (f"VAT {int(vat * 100)} %" if vat else "VAT (reverse charge)", eur(tax)),
                ("Total", eur(gross))]
        intro, closing = "Thank you for your enquiry. We are pleased to quote as follows:", "Kind regards,"
    else:
        refs = [("Angebot Nr.", number), ("Datum:", date), ("Bindefrist:", valid)]
        head = ITEM_HEAD
        sums = [("Summe netto", eur(net)), (f"zzgl. {int(vat * 100)} % USt.", eur(tax)),
                ("Angebotssumme brutto", eur(gross))]
        intro, closing = "Wir danken für Ihre Anfrage und bieten Ihnen freibleibend an:", "Mit freundlichen Grüßen"
    return letter(vendor=vendor, vendor_lines=vendor_lines, recipient=recipient, refs=refs, heading=heading,
                  intro=intro, table=(head[0], rows, head[1]), sums=sums, notes=notes, closing=closing), net, gross


def invoice(*, vendor, vendor_lines, recipient, refs, items, vat=0.19, heading="Rechnung", notes=(), extra=(),
            closing="Mit freundlichen Grüßen", footer=None):
    rows, net, tax, gross = priced(items, vat)
    sums = [("Summe netto", eur(net)), (f"zzgl. USt {int(round(vat * 100))} %", eur(tax)), ("Rechnungsbetrag", eur(gross))]
    return letter(vendor=vendor, vendor_lines=vendor_lines, recipient=recipient, refs=refs, heading=heading,
                  table=(ITEM_HEAD[0], rows, ITEM_HEAD[1]), sums=sums, notes=notes, extra=extra, closing=closing,
                  footer=footer), gross


def till_receipt(lines, note=None):
    st = [Paragraph(line.replace(" ", "&#160;") if line else "&#160;", MONO) for line in lines]
    if note:
        st += [Spacer(1, 10)] + [Paragraph(n, HAND) for n in note]
    return st


RECEIPT_PAGE = (8.5 * cm, 21 * cm)
RECEIPT_MARGINS = (0.6 * cm, 0.6 * cm, 0.8 * cm, 0.8 * cm)


def statement(*, bank, title, bic, iban, holder, rows, footer):
    data = [["Buchungstag", "Vorgang / Verwendungszweck", "Betrag"]] + rows
    return [grid([[Paragraph(f"<b>{bank}</b>", P), Paragraph(title, RIGHT)]], [9.0 * cm, 7.4 * cm]), Spacer(1, 6),
            Paragraph(f"BIC {bic} &#160;&#160; IBAN {iban}", PS), Paragraph(f"Kontoinhaber: {holder}", PS),
            Spacer(1, 12),
            grid([[Paragraph(str(c), RIGHT if i == 2 else P) for i, c in enumerate(r)] for r in data],
                 [2.6 * cm, 10.8 * cm, 3.0 * cm], header=True), Spacer(1, 16), Paragraph(footer, PS)]


WERN = ["Universität Wernstadt", "Fachbereich 71 Elektrotechnik und Informatik"]
WERN_ADDR = ["Am Lindenhang 40", "35291 Wernstadt"]


def proc_form(*, number, date, fachgebiet, requester, phone, kostenstelle, holder, category, framework, procedure,
              offers, supplier, items, begruendung, signed=True, place="Wernstadt", stated_net=None):
    """stated_net: a net total that differs from the positions (a calculation error in the request)."""
    rows, net, tax, gross = priced(items)
    if stated_net is not None:
        net, tax = stated_net, round(stated_net * 0.19, 2)
        gross = round(net + tax, 2)
    check = lambda on: "[X]" if on else "[ ]"  # noqa: E731
    cat = " ".join(f"{check(category == c)} {c}" for c in ("Verbrauchsmaterial", "GWG", "Anlage"))
    sign = (f"Beauftragt: Kostenstellenbevollmächtigte:r<br/>{holder}" if signed else
            "Beauftragt: Kostenstellenbevollmächtigte:r<br/>________________________ (nicht unterschrieben)")
    st = [grid([[Paragraph("<b>Universität Wernstadt</b><br/>Zentrale Beschaffung", P),
                 Paragraph(f"Antrag Nr. <b>{number}</b><br/>Datum: {date}<br/>Eingang über: beschaffung@uni-wernstadt.de",
                           RIGHT)]], [8.4 * cm, 8.0 * cm]), Spacer(1, 10),
          Paragraph("Beschaffungsantrag / Bestellanforderung", H1), Spacer(1, 6),
          Paragraph("1. Bedarfsstelle", H2),
          kv([("Organisationseinheit", f"Fachbereich 71 Elektrotechnik und Informatik, {fachgebiet}"),
              ("Antragsteller:in", requester), ("Telefon", phone), ("Kostenstelle / Auftrag", kostenstelle),
              ("Kostenstellenbevollmächtigte:r", holder)]),
          Paragraph("2. Einordnung", H2),
          kv([("Kategorie", cat), ("Rahmenvertragsprodukt", f"{check(framework)} ja {check(not framework)} nein"),
              ("Vergabeart", procedure), ("Eingeholte Angebote", str(offers)), ("Vorgesehener Lieferant", supplier)]),
          Paragraph("3. Positionen", H2),
          grid([[Paragraph(f"<b>{c}</b>", RIGHT if i > 1 else P) for i, c in
                 enumerate(["Pos.", "Bezeichnung", "Menge", "EP netto", "GP netto"])]] +
               [[Paragraph(str(i + 1), P)] + [Paragraph(c, RIGHT if j else P) for j, c in enumerate(r)]
                for i, r in enumerate(rows)],
               [1.0 * cm, 8.6 * cm, 1.6 * cm, 2.6 * cm, 2.6 * cm], header=True), Spacer(1, 4),
          grid([[Paragraph(k, RIGHT), Paragraph(v, RIGHT)] for k, v in
                [("Summe netto", eur(net)), ("zzgl. 19 % USt.", eur(tax)), ("Gesamtbetrag brutto", eur(gross))]],
               [13.8 * cm, 2.6 * cm]),
          Paragraph("4. Begründung des Bedarfs und der Lieferantenauswahl", H2), Paragraph(begruendung, P),
          Spacer(1, 22),
          grid([[Paragraph(f"{place}, {date}<br/>Antragsteller:in<br/>{requester}", P), Paragraph(sign, RIGHT)]],
               [8.2 * cm, 8.2 * cm], style=[("LINEABOVE", (0, 0), (-1, 0), 0.5, LINE),
                                            ("TOPPADDING", (0, 0), (-1, -1), 6)]),
          Spacer(1, 16), Paragraph("Formular ZB-3 &#183; Beschaffungsantrag &#183; Stand 01/2027 &#183; Seite 1", PS)]
    return st, net, gross


def award_note(*, number, antrag, subject, bids, winner, reason, date, clerk, criterion=None):
    """bids: (bidder, offer no, date, net, gross, rank)."""
    rows = [["Bieter", "Angebot", "vom", "netto", "brutto", "Rang"]]
    rows += [[b, n, d, eur(net), eur(gross), str(r)] for b, n, d, net, gross, r in bids]
    return [Paragraph("Vergabevermerk", H1),
            Paragraph(f"Universität Wernstadt &#183; Vorgang {number} &#183; zum Beschaffungsantrag {antrag}", PS),
            Spacer(1, 10),
            kv([("Gegenstand", subject), ("Verfahren", "Preisvergleich durch Einholung schriftlicher Angebote"),
                ("Wertung", criterion or "Preis (netto), bei gleicher technischer Eignung")]),
            Spacer(1, 8), Paragraph("Eingegangene Angebote", H2),
            grid([[Paragraph(str(c), RIGHT if 2 < i < 6 else P) for i, c in enumerate(r)] for r in rows],
                 [5.2 * cm, 2.6 * cm, 2.0 * cm, 2.4 * cm, 2.4 * cm, 1.2 * cm], header=True), Spacer(1, 8),
            kv([("Zuschlag an", winner)]), Paragraph("Begründung der Vergabeentscheidung", H2), Paragraph(reason, P),
            Spacer(1, 18), Paragraph(f"Wernstadt, {date}<br/>{clerk}, Zentrale Beschaffung", P)]


def wps_cart(*, number, catalog, supplier, created, buyer, account, items):
    rows, net, tax, gross = priced(wps_items(items))
    return [grid([[Paragraph("WPS Warenbestellsystem &#183; Universität Wernstadt", PS),
                   Paragraph(f"Druckansicht {created}", RIGHTS)]], [10 * cm, 6.4 * cm]), Spacer(1, 8),
            Paragraph(f"Warenkorb {number}", H1), Spacer(1, 6),
            kv([("Katalog", catalog), ("Lieferant (Rahmenvertragspartner)", supplier), ("Angelegt", created),
                ("Besteller:in", buyer), ("Kontierung", account), ("Status", "zur Freigabe an Zentrale Beschaffung")]),
            Spacer(1, 10),
            grid([[Paragraph(f"<b>{c}</b>", RIGHT if i > 1 else P) for i, c in
                   enumerate(["Artikelnr.", "Bezeichnung", "Menge", "Preis netto", "Summe netto"])]] +
                 [[Paragraph(art, P)] + [Paragraph(c, RIGHT if j else P) for j, c in enumerate(r)]
                  for (art, _, _, _), r in zip(items, rows)],
                 [2.8 * cm, 7.0 * cm, 1.4 * cm, 2.6 * cm, 2.6 * cm], header=True), Spacer(1, 6),
            grid([[Paragraph(k, RIGHT), Paragraph(v, RIGHT)] for k, v in
                  [("Warenwert netto", eur(net)), ("USt. 19 %", eur(tax)), ("Gesamt brutto", eur(gross))]],
                 [13.8 * cm, 2.6 * cm]), Spacer(1, 10),
            Paragraph("Katalogpreise gemäß Rahmenvertrag. Vergleichsangebote sind für Rahmenvertragsartikel nicht "
                      "erforderlich.", PS)], net


def wps_items(items):
    """WPS rows carry an article number in front: (art, desc, qty, unit) -> priced() input."""
    return [(desc, qty, unit) for _, desc, qty, unit in items]


def owa(mailbox):
    return f"https://owa.uni-wernstadt.de/owa/#path=/mail/inbox" if "wernstadt" in mailbox else \
        "https://outlook.office.example/mail/inbox" if "kassel" in mailbox else \
        "https://webmail.th-sallstedt.de/?_task=mail&amp;_mbox=INBOX"


# =========================================================================== #
#                          BUSINESS TRIP (Kassel, FB 16)                       #
# =========================================================================== #

def trip_cases():
    # 01 angenommen: domestic conference, hotel within 80 EUR, addressed to the university
    d = case(TRIP, 1, "angenommen", "Inland, Vortrag, Hotel 78 € an Universität adressiert, rechtzeitig",
             "Regelfall vollständig", SRC_TRIP, False)
    write(d / "antrag-dienstreisegenehmigung.pdf", trip_form(
        reisenummer="3381031107", name="Dr. Annika Pröbstel", fachgebiet="Fachgebiet Messtechnik",
        personalnummer="050318", geaendert="14. April 2027",
        allgemein=[("Reiseziel:", "Dresden"), ("Anlass:", "DACH-Tagung Messtechnik 2027"),
                   ("Grund der Reise:", "Vortrag „Rauscharme Ladungsverstärker für MEMS-Sensoren“ (angenommen)"),
                   ("Reise ins Ausland:", "[ ] ja &#160; [X] nein"), ("Verkehrsmittel:", "Bahn, 2. Klasse"),
                   ("Datum der Antragstellung:", "14.04.2027")],
        verlauf=[("Start:", "Dienstag, 1. Juni 2027, 07:42 Uhr (Abreise vom Dienstort)"),
                 ("Ende:", "Donnerstag, 3. Juni 2027, 19:10 Uhr (Rückkehr zum Dienstort)"),
                 ("Beginn Dienstgeschäft:", "01.06.2027, 13:00 Uhr"), ("Ende Dienstgeschäft:", "03.06.2027, 13:30 Uhr"),
                 ("priv. Aufenthalt:", "keiner"), ("Arbeitstage:", "3")],
        kosten=[("Tagungsgebühr (Frühbucher)", "1", 290.00), ("Bahn Kassel–Dresden, Hin- und Rückfahrt", "1", 119.80),
                ("Übernachtung Hotel am Zwinger, 2 Nächte à 78,00 €", "2", 156.00)],
        finanzierung="Fachgebietsbudget Messtechnik, Kostenstelle 4612-01",
        begruendung="Vorstellung der Ergebnisse aus dem Arbeitspaket 2; Programm und Annahmebestätigung liegen bei.",
        antragsdatum="14.04.2027"))
    write(d / "tagungsprogramm.pdf", email(
        mailbox="annika.proebstel@uni-kassel.de", url=owa("kassel"),
        subject="DACH-Tagung Messtechnik 2027 – Annahme Ihres Beitrags und vorläufiges Programm",
        sender="Tagungsbüro DACH-Messtechnik &lt;tagung@dach-messtechnik.example&gt;", sent="Mi 07.04.2027 10:15",
        to="Annika Pröbstel &lt;annika.proebstel@uni-kassel.de&gt;",
        body=["Sehr geehrte Frau Dr. Pröbstel,",
              "Ihr Beitrag „Rauscharme Ladungsverstärker für MEMS-Sensoren“ wurde für einen Vortrag angenommen. "
              "Die Tagung findet vom 1. bis 3. Juni 2027 im Internationalen Congress Center Dresden statt.",
              "Ihr Vortrag ist für Mittwoch, 2. Juni 2027, 10:20 Uhr in Session B3 eingeplant (20 Minuten).",
              "Die Frühbuchergebühr von 290,00 EUR gilt bis 30. April 2027.",
              "Mit freundlichen Grüßen<br/>Ihr Tagungsbüro"]))
    write(d / "hotel-reservierung.pdf", letter(
        vendor="Hotel am Zwinger GmbH", vendor_lines=["Ostra-Allee 9", "01067 Dresden", "USt-IdNr. DE 281 450 662"],
        recipient=["Universität Kassel", "Fachbereich 16 · Fachgebiet Messtechnik", "Gast: Dr. Annika Pröbstel",
                   "Wilhelmshöher Allee 71-73", "34121 Kassel"],
        refs=[("Reservierungsnr.:", "HZ-27-55120"), ("Datum:", "15.04.2027")], heading="Reservierungsbestätigung",
        table=(["Leistung", "Nächte", "Preis/Nacht", "Gesamt"],
               [["Einzelzimmer Standard, 01.06.–03.06.2027, ohne Frühstück", "2", eur(78), eur(156)]],
               [9.6 * cm, 1.6 * cm, 2.6 * cm, 2.6 * cm]),
        notes=["Rechnungsanschrift: Universität Kassel, wie oben. Kostenfreie Stornierung bis 18 Uhr am Anreisetag."],
        closing="Wir freuen uns auf Ihren Besuch."))
    write(d / "bahn-buchung.pdf", letter(
        vendor="Nordbahn Fernverkehr AG", vendor_lines=["Gleisfeld 4", "60329 Frankfurt am Main"],
        recipient=["Dr. Annika Pröbstel", "c/o Universität Kassel", "Fachbereich 16", "34121 Kassel"],
        refs=[("Auftragsnummer:", "004527710844"), ("Buchungsdatum:", "15.04.2027")], heading="Buchungsbestätigung",
        table=(["Verbindung", "Menge", "brutto"],
               [["Kassel-Wilhelmshöhe – Dresden Hbf, 01.06.2027, 07:42 Uhr, 2. Klasse, Flexpreis Business", "1", eur(59.90)],
                ["Dresden Hbf – Kassel-Wilhelmshöhe, 03.06.2027, 14:58 Uhr, 2. Klasse, Flexpreis Business", "1", eur(59.90)]],
               [12.0 * cm, 1.6 * cm, 2.8 * cm]),
        sums=[("Summe (brutto)", eur(119.80))], notes=["Firmenkundenrabatt des Landes Hessen berücksichtigt."],
        closing="Gute Reise wünscht"))

    # 02 abgelehnt: hotel 139 EUR/night domestic, no reason given
    d = case(TRIP, 2, "abgelehnt", "Inland, Hotel 139 €/Nacht ohne Begründung der Notwendigkeit",
             "Übernachtung Inland max. 80 € ohne schriftliche Begründung", SRC_TRIP, True)
    write(d / "antrag-dienstreisegenehmigung.pdf", trip_form(
        reisenummer="3381031215", name="Lennart Okafor-Brinck", fachgebiet="Fachgebiet Software Engineering",
        personalnummer="057733", geaendert="3. Mai 2027",
        allgemein=[("Reiseziel:", "München"), ("Anlass:", "Software Quality Days München 2027"),
                   ("Grund der Reise:", "Teilnahme, Weiterbildung Testautomatisierung"),
                   ("Reise ins Ausland:", "[ ] ja &#160; [X] nein"), ("Verkehrsmittel:", "Bahn, 2. Klasse"),
                   ("Datum der Antragstellung:", "03.05.2027")],
        verlauf=[("Start:", "Montag, 21. Juni 2027, 06:55 Uhr"), ("Ende:", "Donnerstag, 24. Juni 2027, 20:30 Uhr"),
                 ("Beginn Dienstgeschäft:", "21.06.2027, 13:00 Uhr"), ("Ende Dienstgeschäft:", "24.06.2027, 15:00 Uhr"),
                 ("priv. Aufenthalt:", "keiner"), ("Arbeitstage:", "4")],
        kosten=[("Teilnahmegebühr", "1", 480.00), ("Bahn Kassel–München, Hin- und Rückfahrt", "1", 158.00),
                ("Übernachtung Hotel Isarblick, 3 Nächte à 139,00 €", "3", 417.00)],
        finanzierung="Fachgebietsbudget Software Engineering, Kostenstelle 4655-02",
        begruendung="Die Tagung bietet Workshops zu Testautomatisierung, die für das Praktikum im Wintersemester "
                    "unmittelbar verwertbar sind.", antragsdatum="03.05.2027"))
    write(d / "hotel-buchung.pdf", letter(
        vendor="Hotel Isarblick München", vendor_lines=["Zweibrückenstraße 14", "80331 München"],
        recipient=["Universität Kassel", "z. Hd. Lennart Okafor-Brinck", "Wilhelmshöher Allee 71-73", "34121 Kassel"],
        refs=[("Buchungsnr.:", "IB-0627-3381"), ("Datum:", "02.05.2027")], heading="Buchungsbestätigung",
        table=(["Leistung", "Nächte", "Preis/Nacht", "Gesamt"],
               [["Superior-Doppelzimmer zur Einzelnutzung, Isarseite, inkl. Frühstück", "3", eur(139), eur(417)]],
               [9.6 * cm, 1.6 * cm, 2.6 * cm, 2.6 * cm]), closing="Herzliche Grüße"))
    write(d / "anmeldung-tagung.pdf", letter(
        vendor="SQD Konferenz GmbH", vendor_lines=["Leopoldstraße 88", "80802 München"],
        recipient=["Universität Kassel", "Lennart Okafor-Brinck", "34121 Kassel"],
        refs=[("Anmeldenr.:", "SQD27-1180"), ("Datum:", "02.05.2027")], heading="Anmeldebestätigung",
        table=(["Leistung", "Menge", "netto", "brutto"],
               [["Konferenzticket 21.–24.06.2027 inkl. 2 Workshops", "1", eur(403.36), eur(480.00)]],
               [9.6 * cm, 1.6 * cm, 2.6 * cm, 2.6 * cm]), closing="Viele Grüße"))

    # 03 angenommen (trap): hotel above 80 EUR, but necessity documented before the trip
    d = case(TRIP, 3, "angenommen", "Falle: Hotel 118 €/Nacht während Messe, Notwendigkeit vorab begründet und belegt",
             "Übernachtung > 80 € nur mit Begründung bei Antragstellung", SRC_TRIP, True)
    write(d / "antrag-dienstreisegenehmigung.pdf", trip_form(
        reisenummer="3381031288", name="Merve Lindqvist", fachgebiet="Fachgebiet Regenerative Energien",
        personalnummer="049902", geaendert="19. Juli 2027",
        allgemein=[("Reiseziel:", "Hamburg"), ("Anlass:", "WindEnergy Hamburg 2027, Fachmesse und Konferenz"),
                   ("Grund der Reise:", "Posterbeitrag im BMWK-Projekt „RotorSense“, Projekttreffen am Messestand"),
                   ("Reise ins Ausland:", "[ ] ja &#160; [X] nein"), ("Verkehrsmittel:", "Bahn, 2. Klasse"),
                   ("Datum der Antragstellung:", "19.07.2027")],
        verlauf=[("Start:", "Dienstag, 21. September 2027, 06:20 Uhr"),
                 ("Ende:", "Donnerstag, 23. September 2027, 21:05 Uhr"),
                 ("Beginn Dienstgeschäft:", "21.09.2027, 10:00 Uhr"), ("Ende Dienstgeschäft:", "23.09.2027, 17:00 Uhr"),
                 ("priv. Aufenthalt:", "keiner"), ("Arbeitstage:", "3")],
        kosten=[("Fachbesucherticket inkl. Konferenz", "1", 210.00), ("Bahn Kassel–Hamburg, Hin- und Rückfahrt", "1", 98.00),
                ("Übernachtung, 2 Nächte à 118,00 €", "2", 236.00)],
        finanzierung="Drittmittelprojekt RotorSense, Kostenstelle 6631-14 (Reisemittel)",
        begruendung="Vorstellung des Posters „Akustische Schadensfrüherkennung an Rotorblättern“; Treffen mit den "
                    "Industriepartnern des Projekts am Stand des Konsortiums.",
        hinweis="Begründung Übernachtungskosten: Wegen der parallel stattfindenden Messe waren am 18.07.2027 in "
                "Hamburg und im Umkreis von 30 km keine Unterkünfte unter 80,00 € verfügbar, auch nicht in den "
                "Vertragshotels. Die Rechercheausdrucke liegen bei; gebucht ist das günstigste verfügbare Zimmer.",
        antragsdatum="19.07.2027"))
    write(d / "unterkunftsrecherche.pdf", [
        Paragraph("hotelvergleich.example &#183; Suchergebnis &#183; Ausdruck 18.07.2027, 16:42", PS), Spacer(1, 6),
        Paragraph("Hamburg + 30 km &#183; 21.09.–23.09.2027 &#183; 1 Erwachsener &#183; Einzelzimmer &#183; "
                  "sortiert nach Preis (aufsteigend)", P), Spacer(1, 10),
        grid([[Paragraph(c, P) for c in r] for r in [
            ["Unterkunft", "Ort", "Preis/Nacht", "Status"],
            ["Hostel Elbbrücken (Mehrbettzimmer)", "Hamburg-Rothenburgsort", "54 €", "ausgebucht"],
            ["Hotel Wandsbeker Hof", "Hamburg-Wandsbek", "79 €", "ausgebucht"],
            ["Gästehaus Pinneberg", "Pinneberg", "84 €", "ausgebucht"],
            ["Hotel Hafenkante Harburg", "Hamburg-Harburg", "118 €", "verfügbar"],
            ["CityLodge Altona", "Hamburg-Altona", "126 €", "verfügbar"],
            ["Hotel Alstertor", "Hamburg-Mitte", "164 €", "verfügbar"]]],
             [6.0 * cm, 4.4 * cm, 2.6 * cm, 3.4 * cm], header=True), Spacer(1, 10),
        Paragraph("Hinweis des Portals: Wegen einer Großveranstaltung ist die Verfügbarkeit im gewählten Zeitraum "
                  "stark eingeschränkt.", PS)])
    write(d / "hotel-buchung.pdf", letter(
        vendor="Hotel Hafenkante Harburg", vendor_lines=["Schellerdamm 21", "21079 Hamburg"],
        recipient=["Universität Kassel", "Gast: Merve Lindqvist", "Wilhelmshöher Allee 71-73", "34121 Kassel"],
        refs=[("Buchungsnr.:", "HH-H-77104"), ("Datum:", "18.07.2027")], heading="Buchungsbestätigung",
        table=(["Leistung", "Nächte", "Preis/Nacht", "Gesamt"],
               [["Einzelzimmer, 21.09.–23.09.2027, ohne Frühstück", "2", eur(118), eur(236)]],
               [9.6 * cm, 1.6 * cm, 2.6 * cm, 2.6 * cm]), closing="Mit freundlichen Grüßen"))

    # 04 abgelehnt: destination on the list of countries for which trips are not approved
    d = case(TRIP, 4, "abgelehnt", "Auslandsreise nach Beirut (Libanon), sonst vollständig",
             "Dienstreisen in den Libanon werden bis auf Weiteres nicht genehmigt", SRC_TRIP, True)
    write(d / "antrag-dienstreisegenehmigung.pdf", trip_form(
        reisenummer="3381031340", name="Prof. Dr. Samir Haddad-Kessler", fachgebiet="Fachgebiet Wasserbau",
        personalnummer="033187", geaendert="2. Februar 2027",
        allgemein=[("Reiseziel:", "Beirut, LIBANON"),
                   ("Anlass:", "Workshop „Urban Water Resilience in the Eastern Mediterranean“"),
                   ("Grund der Reise:", "Eingeladene Keynote und Planung eines gemeinsamen DAAD-Antrags"),
                   ("Reise ins Ausland:", "[X] ja &#160; [ ] nein"), ("Verkehrsmittel:", "Flug (Economy)"),
                   ("Datum der Antragstellung:", "02.02.2027")],
        verlauf=[("Start:", "Montag, 12. April 2027, 05:40 Uhr"), ("Ende:", "Donnerstag, 15. April 2027, 23:10 Uhr"),
                 ("Beginn Dienstgeschäft:", "13.04.2027, 09:00 Uhr"), ("Ende Dienstgeschäft:", "14.04.2027, 18:00 Uhr"),
                 ("priv. Aufenthalt:", "keiner"), ("Arbeitstage:", "4"),
                 ("A1-Bescheinigung:", "nicht erforderlich (kein EU/EWR-Staat)")],
        kosten=[("Flug FRA–BEY–FRA, Economy", "1", 486.00), ("Hotel, 3 Nächte (Satz laut ARV)", "3", 345.00),
                ("Tagegeld Libanon", "1", 168.00)],
        finanzierung="Professurbudget Wasserbau, Kostenstelle 4320-00",
        begruendung="Keynote auf Einladung der American University of Beirut; Vorbereitung eines gemeinsamen "
                    "Antrags im DAAD-Programm „Hochschuldialog mit Südeuropa und dem Nahen Osten“.",
        antragsdatum="02.02.2027"))
    write(d / "einladung-workshop.pdf", email(
        mailbox="haddad-kessler@uni-kassel.de", url=owa("kassel"),
        subject="Invitation: Keynote at the Urban Water Resilience Workshop, Beirut, 13–14 April 2027",
        sender="Prof. Rania Khoury &lt;r.khoury@aub-water.example&gt;", sent="Mo 18.01.2027 09:02",
        to="Samir Haddad-Kessler &lt;haddad-kessler@uni-kassel.de&gt;",
        body=["Dear Samir,", "on behalf of the organising committee I am delighted to invite you to give the opening "
              "keynote of our workshop at the American University of Beirut on 13–14 April 2027.",
              "We will cover accommodation-related questions in a separate e-mail; unfortunately we cannot cover travel "
              "or hotel costs.", "Best wishes,<br/>Rania"]))
    write(d / "flug-angebot.pdf", letter(
        vendor="Reisebüro am Königsplatz", vendor_lines=["Königsplatz 37", "34117 Kassel"],
        recipient=["Universität Kassel", "z. Hd. Prof. Dr. Samir Haddad-Kessler", "34121 Kassel"],
        refs=[("Angebotsnummer:", "RK-2027-0217"), ("Datum:", "01.02.2027")], heading="Flugangebot",
        table=(["Verbindung", "Klasse", "Preis"],
               [["12.04.2027 FRA 06:55 – BEY 12:10, Nordluft NL 6120", "Economy", eur(243)],
                ["15.04.2027 BEY 17:20 – FRA 20:55, Nordluft NL 6121", "Economy", eur(243)]],
               [10.8 * cm, 2.8 * cm, 2.8 * cm]), sums=[("Gesamt", eur(486))],
        notes=["Preisvergleich: Alternative Verbindung über Istanbul 512,00 €; das Angebot ist das günstigste."],
        closing="Mit freundlichen Grüßen"))

    # 05 abgelehnt: invited talk with a fee -> side activity, not a business trip
    d = case(TRIP, 5, "abgelehnt", "Vortrag mit Honorar 800 € (nur in der Einladung), Reisekosten aus Fachgebiet beantragt",
             "Honorar deutet auf Nebentätigkeit; Dienstreisegenehmigung grundsätzlich nicht möglich", SRC_TRIP, True)
    write(d / "antrag-dienstreisegenehmigung.pdf", trip_form(
        reisenummer="3381031402", name="Dr. Theresa Wolkenhauer", fachgebiet="Fachgebiet Kommunikationstechnik",
        personalnummer="046611", geaendert="8. März 2027",
        allgemein=[("Reiseziel:", "Leipzig"), ("Anlass:", "Mitteldeutscher Fachtag Funknetze 2027"),
                   ("Grund der Reise:", "Eingeladener Fachvortrag „Private 5G-Campusnetze in der Praxis“"),
                   ("Reise ins Ausland:", "[ ] ja &#160; [X] nein"), ("Verkehrsmittel:", "Bahn, 2. Klasse"),
                   ("Datum der Antragstellung:", "08.03.2027")],
        verlauf=[("Start:", "Donnerstag, 22. April 2027, 06:48 Uhr"), ("Ende:", "Donnerstag, 22. April 2027, 21:15 Uhr"),
                 ("Beginn Dienstgeschäft:", "22.04.2027, 10:00 Uhr"), ("Ende Dienstgeschäft:", "22.04.2027, 16:30 Uhr"),
                 ("priv. Aufenthalt:", "keiner"), ("Arbeitstage:", "1")],
        kosten=[("Bahn Kassel–Leipzig, Hin- und Rückfahrt", "1", 92.00), ("Tagegeld (Abwesenheit > 8 Std.)", "1", 14.00)],
        finanzierung="Fachgebietsbudget Kommunikationstechnik, Kostenstelle 4688-03",
        begruendung="Der Fachtag ist ein wichtiges Transferformat in die regionale Industrie; die Einladung liegt bei.",
        antragsdatum="08.03.2027"))
    write(d / "einladung-fachtag.pdf", letter(
        vendor="Verband Mitteldeutscher Netzbetreiber e.V.", vendor_lines=["Querstraße 16", "04103 Leipzig"],
        recipient=["Universität Kassel", "Fachgebiet Kommunikationstechnik", "Frau Dr. Theresa Wolkenhauer",
                   "Wilhelmshöher Allee 71-73", "34121 Kassel"],
        refs=[("Leipzig,", "24.02.2027")], heading="Einladung zum Mitteldeutschen Fachtag Funknetze 2027",
        intro="Sehr geehrte Frau Dr. Wolkenhauer,<br/><br/>wir freuen uns, Sie als Referentin für unseren Fachtag am "
              "22. April 2027 in Leipzig zu gewinnen. Wir bitten Sie um einen Vortrag von 45 Minuten zum Thema "
              "„Private 5G-Campusnetze in der Praxis“.<br/><br/>Für Ihren Vortrag zahlen wir Ihnen ein Honorar von "
              "800,00 EUR. Bitte senden Sie uns dazu nach der Veranstaltung eine Honorarrechnung. Reisekosten können "
              "wir leider nicht übernehmen.<br/><br/>Wir freuen uns auf Ihre Zusage.",
        closing="Mit freundlichen Grüßen"))

    # 06 angenommen (trap): third-party benefit (hotel paid by organiser) declared and deducted; one scanned bundle
    d = case(TRIP, 6, "angenommen", "Falle: Veranstalter zahlt Hotel direkt, im Antrag offengelegt und nicht beantragt; "
             "Anlagen als ein Scan-PDF", "Leistungen Dritter vor Reiseantritt mitteilen und anrechnen", SRC_TRIP, False)
    write(d / "antrag-dienstreisegenehmigung.pdf", trip_form(
        reisenummer="3381031466", name="Dr. Jakob Feuerabend", fachgebiet="Fachgebiet Theoretische Elektrotechnik",
        personalnummer="052204", geaendert="11. Januar 2027",
        allgemein=[("Reiseziel:", "Bonn"), ("Anlass:", "DFG-Rundgespräch „Numerische Feldberechnung“"),
                   ("Grund der Reise:", "Eingeladener Teilnehmer, Kurzvortrag zum Stand der Methoden"),
                   ("Reise ins Ausland:", "[ ] ja &#160; [X] nein"), ("Verkehrsmittel:", "Bahn, 2. Klasse"),
                   ("Datum der Antragstellung:", "11.01.2027")],
        verlauf=[("Start:", "Mittwoch, 3. März 2027, 08:10 Uhr"), ("Ende:", "Freitag, 5. März 2027, 18:40 Uhr"),
                 ("Beginn Dienstgeschäft:", "03.03.2027, 13:00 Uhr"), ("Ende Dienstgeschäft:", "05.03.2027, 13:00 Uhr"),
                 ("priv. Aufenthalt:", "keiner"), ("Arbeitstage:", "3")],
        kosten=[("Bahn Kassel–Bonn, Hin- und Rückfahrt", "1", 88.00),
                ("Übernachtung 2 Nächte: trägt der Veranstalter direkt (s. Einladung)", "0", 0.00),
                ("Tagegeld, gekürzt um gestellte Mahlzeiten", "1", 22.40)],
        finanzierung="Fachgebietsbudget Theoretische Elektrotechnik, Kostenstelle 4602-00",
        begruendung="Einladung durch die DFG-Geschäftsstelle als Experte für das Rundgespräch.",
        hinweis="Leistungen von dritter Seite: Unterkunft (2 Nächte) und Mittag-/Abendessen am 03. und 04.03. werden vom "
                "Veranstalter gestellt und sind hier nicht beantragt; das Tagegeld ist entsprechend gekürzt.",
        antragsdatum="11.01.2027"))
    write(d / "scan-anlagen.pdf",
          email(mailbox="jakob.feuerabend@uni-kassel.de", url=owa("kassel"),
                subject="Einladung DFG-Rundgespräch Numerische Feldberechnung, 3.–5. März 2027",
                sender="DFG-Geschäftsstelle, Gruppe Ingenieurwissenschaften &lt;rundgespraech@dfg.example&gt;",
                sent="Di 05.01.2027 14:22", to="Jakob Feuerabend &lt;jakob.feuerabend@uni-kassel.de&gt;",
                body=["Sehr geehrter Herr Dr. Feuerabend,",
                      "wir laden Sie herzlich zum Rundgespräch „Numerische Feldberechnung“ vom 3. bis 5. März 2027 im "
                      "Wissenschaftszentrum Bonn ein.",
                      "Die Unterkunft im Tagungshotel (2 Nächte) sowie Mittag- und Abendessen am 3. und 4. März werden "
                      "von uns übernommen und direkt mit dem Hotel abgerechnet. Die Anreise bitten wir Sie über Ihre "
                      "Einrichtung abzurechnen.", "Mit freundlichen Grüßen<br/>Gruppe Ingenieurwissenschaften"]),
          letter(vendor="Nordbahn Fernverkehr AG", vendor_lines=["Gleisfeld 4", "60329 Frankfurt am Main"],
                 recipient=["Dr. Jakob Feuerabend", "c/o Universität Kassel", "34121 Kassel"],
                 refs=[("Auftragsnummer:", "004527120933"), ("Buchungsdatum:", "12.01.2027")],
                 heading="Buchungsbestätigung",
                 table=(["Verbindung", "Menge", "brutto"],
                        [["Kassel-Wilhelmshöhe – Bonn Hbf, 03.03.2027, 08:10 Uhr, 2. Klasse", "1", eur(44)],
                         ["Bonn Hbf – Kassel-Wilhelmshöhe, 05.03.2027, 14:05 Uhr, 2. Klasse", "1", eur(44)]],
                        [12.0 * cm, 1.6 * cm, 2.8 * cm]),
                 sums=[("Summe (brutto)", eur(88))], closing="Gute Reise wünscht"))

    # 07 abgelehnt: domestic flight without justification
    d = case(TRIP, 7, "abgelehnt", "Inlandsflug Frankfurt–Berlin ohne Begründung, Bahn wäre günstiger",
             "Inlandsflug nur bei geringeren Kosten oder dargelegten dienstlichen Gründen", SRC_TRIP, True)
    write(d / "antrag-dienstreisegenehmigung.pdf", trip_form(
        reisenummer="3381031519", name="Kilian Abendroth", fachgebiet="Fachgebiet Datenbanken",
        personalnummer="058840", geaendert="22. Februar 2027",
        allgemein=[("Reiseziel:", "Berlin"), ("Anlass:", "Projekttreffen BMBF-Verbund „OpenDataSpaces“"),
                   ("Grund der Reise:", "Teilnahme am Konsortialtreffen, Bericht AP 4"),
                   ("Reise ins Ausland:", "[ ] ja &#160; [X] nein"),
                   ("Verkehrsmittel:", "Flug Frankfurt–Berlin (Economy), Bahn Kassel–Frankfurt Flughafen"),
                   ("Datum der Antragstellung:", "22.02.2027")],
        verlauf=[("Start:", "Dienstag, 16. März 2027, 05:30 Uhr"), ("Ende:", "Dienstag, 16. März 2027, 22:40 Uhr"),
                 ("Beginn Dienstgeschäft:", "16.03.2027, 10:00 Uhr"), ("Ende Dienstgeschäft:", "16.03.2027, 17:00 Uhr"),
                 ("priv. Aufenthalt:", "keiner"), ("Arbeitstage:", "1")],
        kosten=[("Flug FRA–BER–FRA, Economy Flex", "1", 289.00), ("Bahn Kassel–Frankfurt Flughafen, Hin und zurück", "1", 76.00),
                ("Tagegeld", "1", 14.00)],
        finanzierung="Drittmittelprojekt OpenDataSpaces, Kostenstelle 6640-22",
        begruendung="Teilnahme am halbjährlichen Konsortialtreffen; Bericht zum Arbeitspaket 4.",
        antragsdatum="22.02.2027"))
    write(d / "flugbuchung.pdf", letter(
        vendor="Nordluft Airlines", vendor_lines=["Flughafenring 2", "60549 Frankfurt am Main"],
        recipient=["Kilian Abendroth", "Universität Kassel", "34121 Kassel"],
        refs=[("Buchungscode:", "NL7Q2K"), ("Datum:", "21.02.2027")], heading="Reservierung",
        table=(["Flug", "Klasse", "Preis"],
               [["NL 2101 FRA 07:05 – BER 08:15, 16.03.2027", "Economy Flex", eur(144.50)],
                ["NL 2118 BER 19:30 – FRA 20:40, 16.03.2027", "Economy Flex", eur(144.50)]],
               [10.8 * cm, 2.8 * cm, 2.8 * cm]), sums=[("Gesamt", eur(289))], closing="Ihr Nordluft-Team"))
    write(d / "einladung-konsortialtreffen.pdf", email(
        mailbox="kilian.abendroth@uni-kassel.de", url=owa("kassel"),
        subject="OpenDataSpaces – Konsortialtreffen 16.03.2027 in Berlin",
        sender="Projektkoordination OpenDataSpaces &lt;koordination@opendataspaces.example&gt;",
        sent="Mo 01.02.2027 11:30", to="Konsortium &lt;konsortium@opendataspaces.example&gt;",
        body=["Liebe Partner,", "unser Konsortialtreffen findet am 16. März 2027 von 10 bis 17 Uhr im Haus der "
              "Forschung, Berlin-Mitte (5 Minuten vom Hauptbahnhof), statt.",
              "Bitte bereitet je Arbeitspaket einen 15-minütigen Statusbericht vor.", "Viele Grüße<br/>Koordination"]))

    # 08 angenommen: EU training course with A1 lead time, English documents
    d = case(TRIP, 8, "angenommen", "Fortbildung in Wien, A1 mit > 8 Wochen Vorlauf, Unterlagen englisch",
             "Auslandsreise vollständig, A1 rechtzeitig", SRC_TRIP, False)
    write(d / "antrag-dienstreisegenehmigung.pdf", trip_form(
        reisenummer="3381031577", name="Nele Hagedorn-Sy", fachgebiet="Fachgebiet Mensch-Maschine-Systeme",
        personalnummer="060127", geaendert="4. Mai 2027",
        allgemein=[("Reiseziel:", "Wien, ÖSTERREICH"), ("Anlass:", "Summer School „Human Factors in Automation“"),
                   ("Grund der Reise:", "Fortbildung (Promotionsthema), Zertifikatskurs 4 Tage"),
                   ("Reise ins Ausland:", "[X] ja &#160; [ ] nein"), ("Verkehrsmittel:", "Bahn, 2. Klasse"),
                   ("Datum der Antragstellung:", "04.05.2027")],
        verlauf=[("Start:", "Sonntag, 18. Juli 2027, 08:15 Uhr"), ("Ende:", "Freitag, 23. Juli 2027, 21:40 Uhr"),
                 ("Beginn Dienstgeschäft:", "19.07.2027, 09:00 Uhr"), ("Ende Dienstgeschäft:", "22.07.2027, 17:00 Uhr"),
                 ("priv. Aufenthalt:", "keiner"), ("Arbeitstage:", "5"),
                 ("A1-Bescheinigung:", "beantragt am 04.05.2027 (Vorlauf 10 Wochen); Geschäftsort: TU-Campus "
                                       "Getreidemarkt 9, 1060 Wien")],
        kosten=[("Kursgebühr", "1", 350.00), ("Bahn Kassel–Wien, Hin- und Rückfahrt (Sparpreis Europa)", "1", 139.80),
                ("Unterkunft Gästehaus, 5 Nächte à 72,00 €", "5", 360.00), ("Tagegeld Österreich (ARV)", "1", 220.00)],
        finanzierung="Graduiertenprogramm FB 16, Kostenstelle 4699-10 (Fortbildungsmittel)",
        begruendung="Die Summer School vermittelt Methoden, die für das Promotionsvorhaben unmittelbar benötigt werden; "
                    "Zertifikat 5 ECTS.", antragsdatum="04.05.2027"))
    write(d / "acceptance-letter.pdf", email(
        mailbox="nele.hagedorn-sy@uni-kassel.de", url=owa("kassel"),
        subject="HFA Summer School 2027 – Admission and programme",
        sender="HFA Summer School Office &lt;office@hfa-summerschool.example&gt;", sent="Fr 30.04.2027 16:05",
        to="Nele Hagedorn-Sy &lt;nele.hagedorn-sy@uni-kassel.de&gt;",
        body=["Dear Ms Hagedorn-Sy,", "we are happy to confirm your admission to the Summer School “Human Factors in "
              "Automation”, 19–22 July 2027, Vienna. Daily sessions run from 9:00 to 17:00.",
              "The course fee of EUR 350 is payable by 30 June 2027; an invoice addressed to your university will "
              "follow. Participants receive a certificate (5 ECTS).", "Best regards,<br/>Summer School Office"]))
    write(d / "unterkunft-gaestehaus.pdf", letter(
        vendor="Gästehaus Mariahilf", vendor_lines=["Gumpendorfer Straße 81", "1060 Wien, Österreich"],
        recipient=["Universität Kassel", "Gast: Nele Hagedorn-Sy", "Wilhelmshöher Allee 71-73", "34121 Kassel, Deutschland"],
        refs=[("Reservierung:", "GM-27-3317"), ("Datum:", "05.05.2027")], heading="Reservierungsbestätigung",
        table=(["Leistung", "Nächte", "Preis/Nacht", "Gesamt"],
               [["Einzelzimmer, 18.07.–23.07.2027", "5", eur(72), eur(360)]],
               [9.6 * cm, 1.6 * cm, 2.6 * cm, 2.6 * cm]), closing="Mit freundlichen Grüßen"))

    # 09 abgelehnt: online conference submitted as business trip
    d = case(TRIP, 9, "abgelehnt", "Online-Konferenz als Dienstreise beantragt (inkl. Tagegeld)",
             "Online-Konferenzen sind keine Dienstreisen; Gebühr über „Privat verauslagte Kosten“", SRC_TRIP, True)
    write(d / "antrag-dienstreisegenehmigung.pdf", trip_form(
        reisenummer="3381031630", name="Ole Rasmussen-Tietz", fachgebiet="Fachgebiet Intelligente Systeme",
        personalnummer="061455", geaendert="6. September 2027",
        allgemein=[("Reiseziel:", "online (Teilnahme vom Arbeitsplatz Kassel)"),
                   ("Anlass:", "EuroML Virtual 2027"), ("Grund der Reise:", "Vortrag des angenommenen Workshop-Beitrags"),
                   ("Reise ins Ausland:", "[ ] ja &#160; [X] nein"), ("Verkehrsmittel:", "entfällt"),
                   ("Datum der Antragstellung:", "06.09.2027")],
        verlauf=[("Start:", "Dienstag, 12. Oktober 2027, 08:00 Uhr"), ("Ende:", "Mittwoch, 13. Oktober 2027, 18:00 Uhr"),
                 ("Beginn Dienstgeschäft:", "12.10.2027, 09:00 Uhr"), ("Ende Dienstgeschäft:", "13.10.2027, 17:30 Uhr"),
                 ("priv. Aufenthalt:", "keiner"), ("Arbeitstage:", "2")],
        kosten=[("Registrierung (online, Student Author)", "1", 160.00), ("Tagegeld 2 Tage", "2", 28.00)],
        finanzierung="Fachgebietsbudget Intelligente Systeme, Kostenstelle 4673-01",
        begruendung="Präsentation des Workshop-Papers „Calibrated Uncertainty for Tabular Models“.",
        antragsdatum="06.09.2027"))
    write(d / "registration.pdf", letter(
        vendor="EuroML Virtual 2027", vendor_lines=["c/o Conference Systems Ltd", "4 Harbour Road", "Dublin D02, Ireland"],
        recipient=["Ole Rasmussen-Tietz", "University of Kassel", "34121 Kassel, Germany"],
        refs=[("Registration ID:", "EMLV27-0918"), ("Date:", "05.09.2027")], heading="Registration confirmation",
        intro="EuroML Virtual 2027 takes place fully online, 12–13 October 2027. Streaming links follow by e-mail.",
        table=(["Item", "Qty", "Amount"], [["Online registration, student author", "1", eur(160)]],
               [11.6 * cm, 2.0 * cm, 2.8 * cm]), closing="Kind regards,"))

    # 10 angenommen: private car, standard rate, no parking claimed
    d = case(TRIP, 10, "angenommen", "Tagesreise Fulda mit Privat-Pkw zu 0,21 €/km, keine Parkgebühren beantragt",
             "Wegstreckenentschädigung ohne triftigen Grund 0,21 €/km", SRC_TRIP, True)
    write(d / "antrag-dienstreisegenehmigung.pdf", trip_form(
        reisenummer="3381031702", name="Hannes Vierling", fachgebiet="Fachgebiet Elektrische Antriebe",
        personalnummer="047390", geaendert="2. November 2027",
        allgemein=[("Reiseziel:", "Fulda"), ("Anlass:", "Abnahme Prüfstand bei der Firma Rhönmotoren GmbH"),
                   ("Grund der Reise:", "Werksabnahme des Antriebsprüfstands (Auftrag 4500321177)"),
                   ("Reise ins Ausland:", "[ ] ja &#160; [X] nein"),
                   ("Verkehrsmittel:", "privater Pkw (ohne triftigen Grund, kleine Wegstreckenentschädigung)"),
                   ("Datum der Antragstellung:", "02.11.2027")],
        verlauf=[("Start:", "Mittwoch, 17. November 2027, 07:00 Uhr"), ("Ende:", "Mittwoch, 17. November 2027, 16:30 Uhr"),
                 ("Beginn Dienstgeschäft:", "17.11.2027, 09:00 Uhr"), ("Ende Dienstgeschäft:", "17.11.2027, 14:30 Uhr"),
                 ("priv. Aufenthalt:", "keiner"), ("Arbeitstage:", "1")],
        kosten=[("Wegstreckenentschädigung 2 × 105 km à 0,21 €", "210 km", 44.10), ("Tagegeld (Abwesenheit > 8 Std.)", "1", 14.00)],
        finanzierung="Investitionsmittel Prüfstand, Kostenstelle 4631-90",
        begruendung="Die Werksabnahme ist vertraglich vor Auslieferung vorgesehen (Einladung liegt bei).",
        antragsdatum="02.11.2027"))
    write(d / "einladung-werksabnahme.pdf", email(
        mailbox="hannes.vierling@uni-kassel.de", url=owa("kassel"), subject="Werksabnahme Antriebsprüfstand – Termin",
        sender="Projektleitung Rhönmotoren GmbH &lt;projekte@rhoenmotoren.example&gt;", sent="Fr 29.10.2027 13:12",
        to="Hannes Vierling &lt;hannes.vierling@uni-kassel.de&gt;",
        body=["Sehr geehrter Herr Vierling,", "wie im Auftrag 4500321177 vereinbart, laden wir Sie zur Werksabnahme des "
              "Antriebsprüfstands am 17.11.2027 um 9:00 Uhr in unser Werk, Am Kreuzberg 3, 36043 Fulda, ein.",
              "Die Abnahme dauert voraussichtlich bis 14:30 Uhr.", "Mit freundlichen Grüßen<br/>Projektleitung"]))

    # 11 abgelehnt: form incomplete, no evidence of the official purpose
    d = case(TRIP, 11, "abgelehnt", "Finanzierung leer, Anlass vage, kein Programm/Einladung beigefügt",
             "Anträge vollständig ausfüllen; Unterlagen zum dienstlichen Interesse beifügen", SRC_TRIP, True)
    write(d / "antrag-dienstreisegenehmigung.pdf", trip_form(
        reisenummer="3381031755", name="Benedikt Sauerwald", fachgebiet="Fachgebiet Mikroelektronik",
        personalnummer="059914", geaendert="7. Juni 2027",
        allgemein=[("Reiseziel:", "Stuttgart"), ("Anlass:", "Arbeitstreffen"), ("Grund der Reise:", "Abstimmung"),
                   ("Reise ins Ausland:", "[ ] ja &#160; [X] nein"), ("Verkehrsmittel:", "Bahn"),
                   ("Datum der Antragstellung:", "07.06.2027")],
        verlauf=[("Start:", "Montag, 5. Juli 2027, 06:10 Uhr"), ("Ende:", "Dienstag, 6. Juli 2027, 20:00 Uhr"),
                 ("Beginn Dienstgeschäft:", ""), ("Ende Dienstgeschäft:", ""), ("priv. Aufenthalt:", "keiner"),
                 ("Arbeitstage:", "2")],
        kosten=[("Bahnfahrt", "1", 134.00), ("Hotel", "1", 79.00)], finanzierung="",
        begruendung="Abstimmung mit Partnern.", antragsdatum="07.06.2027"))
    write(d / "bahn-ticket.pdf", letter(
        vendor="Nordbahn Fernverkehr AG", vendor_lines=["Gleisfeld 4", "60329 Frankfurt am Main"],
        recipient=["Benedikt Sauerwald", "Kassel"], refs=[("Auftragsnummer:", "004527944107"), ("Datum:", "06.06.2027")],
        heading="Rechnung",
        table=(["Verbindung", "Menge", "brutto"],
               [["Kassel-Wilhelmshöhe – Stuttgart Hbf, 05.07.2027, Sparpreis, 2. Klasse", "1", eur(67)],
                ["Stuttgart Hbf – Kassel-Wilhelmshöhe, 06.07.2027, Sparpreis, 2. Klasse", "1", eur(67)]],
               [12.0 * cm, 1.6 * cm, 2.8 * cm]), sums=[("Summe (brutto)", eur(134))],
        notes=["Bezahlt mit Kreditkarte am 06.06.2027.", "Dieses Dokument berechtigt nicht zur Fahrt."]))

    # 12 angenommen: training course with BahnCard 50 used, neutral file names
    d = case(TRIP, 12, "angenommen", "Fortbildung Inland, private BahnCard 50 eingesetzt, Dateinamen ohne Typhinweis",
             "Vorhandene BahnCard ist für Dienstreisen einzusetzen", SRC_TRIP, False)
    write(d / "Anlage_1.pdf", trip_form(
        reisenummer="3381031811", name="Ilse Kronberger", fachgebiet="Fachgebiet Technische Informatik (Sekretariat)",
        personalnummer="038826", geaendert="15. August 2027",
        allgemein=[("Reiseziel:", "Hannover"), ("Anlass:", "Seminar „Reisekosten- und Beschaffungsrecht an Hochschulen“"),
                   ("Grund der Reise:", "Fortbildung, Teilnahme auf Anordnung der Fachgebietsleitung"),
                   ("Reise ins Ausland:", "[ ] ja &#160; [X] nein"),
                   ("Verkehrsmittel:", "Bahn, 2. Klasse, mit privater BahnCard 50"),
                   ("Datum der Antragstellung:", "15.08.2027")],
        verlauf=[("Start:", "Mittwoch, 29. September 2027, 07:05 Uhr"),
                 ("Ende:", "Donnerstag, 30. September 2027, 18:20 Uhr"),
                 ("Beginn Dienstgeschäft:", "29.09.2027, 10:00 Uhr"), ("Ende Dienstgeschäft:", "30.09.2027, 15:00 Uhr"),
                 ("priv. Aufenthalt:", "keiner"), ("Arbeitstage:", "2")],
        kosten=[("Seminargebühr inkl. Tagungspauschale", "1", 395.00),
                ("Bahn Kassel–Hannover, Hin- und Rückfahrt (BahnCard-50-Preis)", "1", 41.80),
                ("Übernachtung inkl. Frühstück", "1", 74.00)],
        finanzierung="Weiterbildungsbudget Abteilung Personal und Organisation (Zusage vom 10.08.2027)",
        begruendung="Fortbildung zu den Neuerungen im Reisekosten- und Beschaffungsrecht für Sekretariate.",
        antragsdatum="15.08.2027"))
    write(d / "Anlage_2.pdf", letter(
        vendor="Hochschulforum Verwaltung e.V.", vendor_lines=["Lister Meile 12", "30161 Hannover"],
        recipient=["Universität Kassel", "Fachgebiet Technische Informatik", "Frau Ilse Kronberger",
                   "Wilhelmshöher Allee 71-73", "34121 Kassel"],
        refs=[("Seminar-Nr.:", "HFV-27-14"), ("Datum:", "12.08.2027")], heading="Anmeldebestätigung und Programm",
        table=(["Programmpunkt", "Tag", "Zeit"],
               [["Neuerungen im Reisekostenrecht der Länder", "29.09.", "10:00–12:30"],
                ["Vergabe unterhalb der Schwellenwerte", "29.09.", "13:30–17:00"],
                ["Praxisfälle Auslagenerstattung", "30.09.", "09:00–15:00"]],
               [10.0 * cm, 2.4 * cm, 4.0 * cm]),
        sums=[("Seminargebühr inkl. Tagungspauschale (Mittagessen, Getränke)", eur(395))],
        notes=["Rechnung an die Universität Kassel folgt nach dem Seminar."], closing="Mit freundlichen Grüßen"))
    write(d / "Anlage_3.pdf", letter(
        vendor="Nordbahn Fernverkehr AG", vendor_lines=["Gleisfeld 4", "60329 Frankfurt am Main"],
        recipient=["Ilse Kronberger", "c/o Universität Kassel", "34121 Kassel"],
        refs=[("Auftragsnummer:", "004528016652"), ("Buchungsdatum:", "16.08.2027")], heading="Buchungsbestätigung",
        table=(["Verbindung", "Ermäßigung", "brutto"],
               [["Kassel-Wilhelmshöhe – Hannover Hbf, 29.09.2027, 07:05 Uhr", "BahnCard 50", eur(20.90)],
                ["Hannover Hbf – Kassel-Wilhelmshöhe, 30.09.2027, 16:31 Uhr", "BahnCard 50", eur(20.90)]],
               [11.2 * cm, 2.4 * cm, 2.8 * cm]), sums=[("Summe (brutto)", eur(41.80))], closing="Gute Reise wünscht"))


# =========================================================================== #
#                  EXPENSE REIMBURSEMENT (Wernstadt / Sallstedt)               #
# =========================================================================== #

def expense_cases():
    # 01 angenommen: hardware-store receipt with articles and a written purpose
    d = case(EXPENSE, 1, "angenommen", "Baumarkt-Kassenbon mit Artikelbezeichnungen und Zweckvermerk",
             "Originalquittung; dienstlicher Zweck erkennbar", SRC_FIN, False)
    write(d / "kassenbon-baumarkt.pdf", till_receipt([
        "    HOLZ- UND BAUMARKT KESSLING", "      Ostring 41, 37269 Eschwege", "      Tel. 05651 33 08 12", "",
        "SCHLEIFPAPIER K120 5ER         4,99", "SCHLEIFPAPIER K240 5ER         4,99", "HOLZLEIM D3 250G               5,49",
        "ABDECKKLEBEBAND 30MM           3,29", "2 ST x 2,35", "SCHRAUBZWINGE 150MM            4,70", "",
        "SUMME EUR                     23,46", "EC-KARTE                      23,46", "",
        "MWST 19%  NETTO 19,71  MWST 3,75", "BON 8812  KASSE 02  09.03.27 16:05", "St.-Nr. 25/247/30118"],
        note=["Material für Probenhalter, Prüfstand Labor 2.04,", "Lehrstuhl Werkstofftechnik – T. Brinkhoff"]),
        pagesize=RECEIPT_PAGE, margins=RECEIPT_MARGINS)

    # 02 abgelehnt: Citavi licence although it is a central campus licence
    d = case(EXPENSE, 2, "abgelehnt", "Citavi-Einzellizenz privat gekauft, obwohl Campuslizenz zentral getragen",
             "Citavi: Campuslizenz, Kosten werden zentral getragen", SRC_FRAME, True, uncertain=True)
    st, _ = invoice(
        vendor="Literatursoft Vertrieb GmbH", vendor_lines=["Kaiserstraße 61", "76133 Karlsruhe", "USt-IdNr. DE 301 552 418"],
        recipient=WERN + ["Lehrstuhl für Mediendidaktik", "z. Hd. Dr. Fenja Tiedtke"] + WERN_ADDR,
        refs=[("Rechnung Nr.", "LS-27-004812"), ("Datum:", "18.01.2027"), ("Zahlungsart:", "Kreditkarte, bezahlt")],
        items=[("Citavi 7 Einzelplatzlizenz Pro, Laufzeit 12 Monate (Download)", 1, 100.00)],
        notes=["Lizenzschlüssel wurde per E-Mail an fenja.tiedtke@uni-wernstadt.de versandt."])
    write(d / "rechnung-literaturverwaltung.pdf", st + [
        Spacer(1, 10), Paragraph("Bitte um Erstattung, benötigt für das Promotionskolleg. F. Tiedtke", HAND)])

    # 03 angenommen (trap): coffee, water and pastries for external guests
    d = case(EXPENSE, 3, "angenommen", "Falle: Kaffee/Wasser/Gebäck für Projekttreffen mit externen Gästen, "
             "Teilnehmerliste liegt bei", "Übliche Gesten der Höflichkeit gegenüber Gästen sind Betriebsaufwand",
             SRC_FIN, True)
    st, _ = invoice(
        vendor="Bäckerei & Konditorei Hollmann", vendor_lines=["Marktstraße 3", "35291 Wernstadt", "St.-Nr. 026 812 44071"],
        recipient=WERN + ["Lehrstuhl für Fluidsystemtechnik", "Prof. Dr. Magnus Ellerbrock"] + WERN_ADDR,
        refs=[("Rechnung Nr.", "H-27-0391"), ("Datum:", "11.05.2027"), ("Lieferung:", "11.05.2027, Geb. D, Raum 1.12")],
        items=[("Kaffee, Thermoskanne 2 l", 2, 9.80), ("Mineralwasser 0,75 l, Glasflasche", 6, 1.25),
               ("Gebäckplatte gemischt (12 Stück)", 1, 13.50)], vat=0.07, notes=["Bar bezahlt bei Abholung."])
    write(d / "rechnung-baeckerei.pdf", st)
    write(d / "teilnehmerliste-projekttreffen.pdf", [
        Paragraph("Teilnehmerliste", H1),
        Paragraph("Projekttreffen „HydroValve“ (Verbundprojekt mit Industriepartnern) &#183; 11.05.2027, 10:00–13:00 Uhr "
                  "&#183; Universität Wernstadt, Geb. D, Raum 1.12", P), Spacer(1, 10),
        grid([[Paragraph(c, P) for c in r] for r in [
            ["Name", "Einrichtung", "Gast/intern"], ["Dr. Ulrike Saalfeld", "Ventiltechnik Saalfeld GmbH, Gießen", "Gast"],
            ["Jonas Preuß", "Ventiltechnik Saalfeld GmbH, Gießen", "Gast"],
            ["Dipl.-Ing. Katrin Odenwald", "Hydraulik Nord AG, Bremen", "Gast"],
            ["Dr. Mehmet Arslan", "Fraunhofer-Institut (Projektträger-Begleitung)", "Gast"],
            ["Prof. Dr. Magnus Ellerbrock", "Universität Wernstadt", "intern"],
            ["Lea Brünninghaus", "Universität Wernstadt", "intern"]]],
             [5.4 * cm, 7.4 * cm, 3.6 * cm], header=True), Spacer(1, 12),
        Paragraph("Bewirtung: Kaffee, Wasser, Gebäck. Anlass: Arbeitstreffen mit den Verbundpartnern (Einwerbung des "
                  "Folgeprojekts). M. Ellerbrock", P)])

    # 04 abgelehnt: one person paid the fees of three colleagues and claims all of it
    d = case(EXPENSE, 4, "abgelehnt", "Online-Workshop-Gebühren für drei Personen von einer Person bezahlt und "
             "komplett eingereicht", "Für mehrere Personen verauslagte Kosten nicht nur an die verauslagende Person",
             SRC_TRIP, True, uncertain=True)
    st, _ = invoice(
        vendor="Akademie für Datenkompetenz gGmbH", vendor_lines=["Schillerstraße 9", "99423 Weimar"],
        recipient=WERN + ["Lehrstuhl für Statistik", "Dr. Pauline Wechsler"] + WERN_ADDR,
        refs=[("Rechnung Nr.", "ADK-27-1166"), ("Datum:", "03.03.2027"), ("Veranstaltung:", "Online-Workshop R-Shiny, 15.–16.03.2027")],
        items=[("Teilnahme Dr. Pauline Wechsler", 1, 180.00), ("Teilnahme Tobias Fennhoff", 1, 180.00),
               ("Teilnahme Hanna Okonkwo", 1, 180.00)], vat=0.0,
        notes=["Umsatzsteuerfrei nach § 4 Nr. 22a UStG.", "Bezahlt per Kreditkarte (Visa ****2290) am 03.03.2027."])
    write(d / "rechnung-workshop.pdf", st)
    write(d / "kreditkartenabrechnung.pdf", statement(
        bank="Kreissparkasse Wernstadt, Visa-Abrechnung", title="Abrechnung vom 31.03.2027", bic="KSWEDEF1XXX",
        iban="DE71 9512 0034 0019 4471 05", holder="Dr. Pauline Wechsler",
        rows=[["03.03.2027", "AKADEMIE FUER DATENKOMPETENZ WEIMAR", "-540,00 EUR"],
              ["14.03.2027", "Tankstelle Wernstadt-Süd", "-61,24 EUR"]],
        footer="Visa ****2290. Der Saldo wird am 10.04.2027 vom Referenzkonto eingezogen."))

    # 05 angenommen: GBP invoice for a standard, card statement shows EUR
    d = case(EXPENSE, 5, "angenommen", "Englische Rechnung in GBP für Norm-PDF, Kartenabrechnung belegt EUR-Betrag",
             "Fremdwährung: Kontoauszug belegt Euro-Betrag", SRC_FIN, False)
    write(d / "invoice-standard.pdf", letter(
        vendor="Normstore Publishing Ltd", vendor_lines=["12 Chiswick Park", "London W4 5YA, United Kingdom",
                                                          "VAT GB 318 4410 72"],
        recipient=["Bill to: Universität Wernstadt", "Chair of Power Electronics, Dr. Emeric Pfannstiel",
                   "Am Lindenhang 40", "35291 Wernstadt, Germany"],
        refs=[("Invoice no.", "NS-INV-2027-77102"), ("Date", "14 June 2027"), ("Order", "NS-ORD-55190")],
        heading="Invoice",
        table=(["Description", "Qty", "Unit", "Amount"],
               [["IEC 61000-4-2:2027, PDF, single user licence (EMC – electrostatic discharge immunity test)", "1",
                 "GBP 212.00", "GBP 212.00"]], [9.6 * cm, 1.6 * cm, 2.6 * cm, 2.6 * cm]),
        sums=[("Subtotal", "GBP 212.00"), ("VAT (export of services, outside scope)", "GBP 0.00"), ("Total paid", "GBP 212.00")],
        notes=["Paid by credit card ending 7714 on 14 June 2027. Download licence for the named user only."],
        closing="Thank you for your order."))
    write(d / "kontoauszug.pdf", statement(
        bank="Hainbuchen Bank AG, Kreditkartenabrechnung", title="Kontoauszug vom 30.06.2027", bic="HNBUDEF9XXX",
        iban="DE58 9506 1230 0388 1204 77", holder="Dr. Emeric Pfannstiel",
        rows=[["14.06.2027", "NORMSTORE PUBLISHING LONDON GB<br/>GBP 212,00 Kurs 0,8571", "-247,35 EUR"],
              ["14.06.2027", "Auslandseinsatzentgelt 1,75 % von 247,35 EUR", "-4,33 EUR"]],
        footer="Abrechnung Visa ****7714."))

    # 06 abgelehnt: till receipt with article numbers only and no keyword
    d = case(EXPENSE, 6, "abgelehnt", "Kassenbon nur mit Artikelnummern, kein Stichwort zum Zweck, kein Unibezug",
             "Ohne Artikel auf der Quittung muss ein Stichwort dazugeschrieben werden", SRC_FIN, False)
    write(d / "beleg-1.pdf", till_receipt([
        "      ELEKTRO-FACHMARKT VOGELSANG", "      Bahnhofstraße 22, 34613 Schwalmstadt", "",
        "ART 112093", "2 ST x 6,49                   12,98", "ART 450771", "1 ST x 18,90                  18,90",
        "ART 303318", "3 ST x 2,79                    8,37", "", "SUMME EUR                     40,25",
        "BAR                           50,00", "RUECKGELD                      9,75", "",
        "MWST 19%  NETTO 33,82  MWST 6,43", "BON 2207  KASSE 01  22.06.27 11:18"]),
        pagesize=RECEIPT_PAGE, margins=RECEIPT_MARGINS)

    # 07 abgelehnt: monitor bought in a web shop and claimed as expense although it is a framework product
    d = case(EXPENSE, 7, "abgelehnt", "Monitor im Webshop privat gekauft und zur Erstattung eingereicht",
             "Monitore: Rahmenvertrag, ausschließlich beim Rahmenvertragspartner über WPS", SRC_FRAME, True)
    st, _ = invoice(
        vendor="Bildschirmlager Vogtland e.K.", vendor_lines=["Bahnhofstraße 50", "08523 Plauen", "USt-IdNr. DE 277 019 334"],
        recipient=WERN + ["Lehrstuhl für Robotik", "Mats Høiberg"] + WERN_ADDR,
        refs=[("Rechnung Nr.", "BV-27-22918"), ("Datum:", "02.08.2027"), ("Bestellung:", "Webshop, 01.08.2027")],
        items=[("Monitor 27 Zoll, WQHD, IPS, höhenverstellbar", 1, 150.42)],
        notes=["Bezahlt per Online-Bezahldienst am 01.08.2027."])
    write(d / "rechnung-monitor.pdf", st + [
        Spacer(1, 8), Paragraph("Dringend für neuen Mitarbeiter, WPS-Lieferung hätte 3 Wochen gedauert. M. Høiberg", HAND)])

    # 08 angenommen: give-aways for a trade fair below 10 EUR each
    d = case(EXPENSE, 8, "angenommen", "Give-aways (Kugelschreiber 0,84 €/Stück) für Messestand der Universität",
             "Give-aways auf Messen bis 10 € je Stück übernahmefähig", SRC_FIN, True)
    st, _ = invoice(
        vendor="Werbemittel Brandtner GmbH", vendor_lines=["Industriestraße 7", "86899 Landsberg am Lech"],
        recipient=WERN + ["Transferstelle / Lehrstuhl für Automatisierung", "Dr. Ronja Weidlich"] + WERN_ADDR,
        refs=[("Rechnung Nr.", "WB-27-3105"), ("Datum:", "21.03.2027"), ("Lieferung an:", "Universität Wernstadt, Geb. A")],
        items=[("Kugelschreiber Metall, einfarbig bedruckt mit Logo „Universität Wernstadt – Automatisierung“", 250, 0.84),
               ("Druckvorlagenerstellung (einmalig)", 1, 25.00)],
        notes=["Bezahlt per Überweisung am 22.03.2027 (Vorkasse)."])
    write(d / "rechnung-werbemittel.pdf", st + [
        Spacer(1, 8), Paragraph("Give-aways für den Stand der Uni auf der Hannover Messe 2027 (Halle 2, "
                                "Gemeinschaftsstand Hessen). R. Weidlich", HAND)])

    # 09 abgelehnt: guest gift above 30 EUR
    d = case(EXPENSE, 9, "abgelehnt", "Gastgeschenk für Partneruniversität 64,90 €",
             "Gastgeschenke bei Dienstreisen nur bis 30 €", SRC_FIN, True)
    st, _ = invoice(
        vendor="Kunsthandwerk am Dom", vendor_lines=["Domplatz 5", "35291 Wernstadt"],
        recipient=WERN + ["Lehrstuhl für Bauphysik", "Prof. Dr. Gunda Rehfeldt"] + WERN_ADDR,
        refs=[("Rechnung Nr.", "KD-27-0418"), ("Datum:", "07.10.2027")],
        items=[("Bildband „Wernstadt im Wandel der Zeit“, Hardcover", 1, 36.90),
               ("Glaskaraffe mundgeblasen, Geschenkverpackung", 1, 28.00)], vat=0.0,
        notes=["Kleinunternehmer gem. § 19 UStG, keine Umsatzsteuer ausgewiesen.", "Bezahlt mit EC-Karte."])
    write(d / "rechnung-gastgeschenk.pdf", st + [
        Spacer(1, 8), Paragraph("Gastgeschenk für Prof. Dvorak bei der Dienstreise an die Partneruniversität Brno, "
                                "12.10.2027. G. Rehfeldt", HAND)])

    # 10 angenommen: Sallstedt, urgent lab chemicals, documents only
    d = case(EXPENSE, 10, "angenommen", "TH Sallstedt: dringender Laborbedarf aus Chemikalienhandel, Rechnung an Hochschule",
             "Nach Aktenlage vollständig (anderes Landesrecht)", "", False)
    st, _ = invoice(
        vendor="Chemikalienhandel Reusch OHG", vendor_lines=["Industriepark 4", "99610 Sömmerda"],
        recipient=["Technische Hochschule Sallstedt", "Labor Verfahrenstechnik", "z. Hd. Dipl.-Ing. Arne Moosleitner",
                   "Brühlstraße 7", "99643 Sallstedt"],
        refs=[("Rechnung Nr.", "RE-27-55821"), ("Datum:", "16.11.2027"), ("Abholung:", "16.11.2027, Ladengeschäft")],
        items=[("2-Propanol p.a., 5 l Kanister", 1, 38.90), ("Aceton technisch, 2,5 l", 2, 14.20),
               ("Nitril-Handschuhe Gr. L, 100 Stück", 1, 7.90)],
        notes=["Bezahlt mit EC-Karte am 16.11.2027."])
    write(d / "rechnung-laborchemikalien.pdf", st + [
        Spacer(1, 8), Paragraph("Für Praktikumsversuch V3 am 17.11., Lieferung über den Einkauf nicht mehr rechtzeitig "
                                "möglich. A. Moosleitner", HAND)])

    # 11 abgelehnt: Christmas tree and decoration
    d = case(EXPENSE, 11, "abgelehnt", "Weihnachtsbaum und Dekoration für das Institutsfoyer",
             "Schmuck- und Dekorationsartikel (z. B. Weihnachtsbäume) nicht erstattungsfähig", SRC_FIN, True)
    st, _ = invoice(
        vendor="Gartencenter Lohmühle", vendor_lines=["An der Lohmühle 2", "35291 Wernstadt"],
        recipient=WERN + ["Institut für Elektrische Energietechnik", "Sekretariat, Frau Gesine Maltritz"] + WERN_ADDR,
        refs=[("Rechnung Nr.", "GL-27-12044"), ("Datum:", "01.12.2027")],
        items=[("Nordmanntanne 2,0–2,2 m, mit Netz", 1, 49.00), ("LED-Lichterkette 20 m, außen", 1, 29.90),
               ("Christbaumkugeln Glas, 24er-Set", 1, 18.90), ("Christbaumständer", 1, 14.90)],
        notes=["Bezahlt mit EC-Karte."])
    write(d / "rechnung-gartencenter.pdf", st + [
        Spacer(1, 8), Paragraph("Für das Foyer Geb. B (Adventsaktion des Instituts). G. Maltritz", HAND)])

    # 12 angenommen (trap): three receipts in one scan, summary sheet adds up
    d = case(EXPENSE, 12, "angenommen", "Falle: drei Belege verschiedener Läden in einem Scan, Zusammenstellung "
             "rechnet richtig", "Originalbelege mit Artikel und Zweck", SRC_FIN, True)
    write(d / "scan-belege.pdf",
          till_receipt(["      BÜRO-WELT WERNSTADT", "      Marktstraße 18", "",
                        "MODERATIONSKARTEN 100ST         8,95", "PINNADELN 100ST                 3,49",
                        "FLIPCHARTMARKER 4ER             6,46", "", "SUMME EUR                      18,90",
                        "EC                             18,90", "BON 7712  14.04.27 09:12"]),
          till_receipt(["      COPYSHOP KAHLERT", "      Universitätsstraße 2", "",
                        "PLAKAT A1 FARBE  2 x 12,90     25,80", "LAMINIEREN A1 (2 ST)            6,65", "",
                        "SUMME EUR                      32,45", "BAR                            32,45",
                        "BELEG 0441  14.04.27 10:31"]),
          till_receipt(["      HOLZ- UND BAUMARKT KESSLING", "      Ostring 41", "",
                        "STELLWANDFUSS STAHL 2 x 15,90  31,80", "KABELBINDER 200ST               4,99",
                        "DOPPELKLEBEBAND                 10,01", "", "SUMME EUR                      46,80",
                        "EC-KARTE                       46,80", "BON 9011  14.04.27 12:47"]),
          [Paragraph("Zusammenstellung der Belege", H1), Spacer(1, 8),
           Paragraph("Workshop „Studieninformationstag Elektrotechnik“ am 15.04.2027, Stellwände und "
                     "Moderationsmaterial für den Stand des Fachbereichs.", HAND), Spacer(1, 8),
           Paragraph("Büro-Welt 18,90 € + Copyshop 32,45 € + Baumarkt 46,80 € = 98,15 €", HAND), Spacer(1, 8),
           Paragraph("Lehrstuhl für Hochspannungstechnik, Universität Wernstadt – Malte Ostendorp", HAND)])


# =========================================================================== #
#                       PROCUREMENT (Wernstadt / Sallstedt)                    #
# =========================================================================== #

def recip(fachgebiet, person):
    return WERN + [fachgebiet, f"z. Hd. {person}"] + WERN_ADDR


def bid(vendor, number, date, net, gross, rank):
    return vendor, number, date, net, gross, rank


def procurement_cases():
    # 01 angenommen: three offers, cheapest wins
    d = case(PROCUREMENT, 1, "angenommen", "Drei Angebote, günstigstes gewählt, Antrag und Vergabevermerk stimmig",
             "Regelfall drei Angebote", SRC_PROC, False)
    who, fg = "Dr. Saskia Brennecke", "Fachgebiet Bioverfahrenstechnik"
    items = [("Kühlzentrifuge, 4 x 750 ml Ausschwingrotor, -10 bis +40 °C", 1, 6890.00), ("Adaptersatz 50 ml Röhrchen", 4, 96.00)]
    o1, n1, g1 = offer(vendor="Laborgeräte Wiesenthal GmbH", vendor_lines=["Robert-Bosch-Str. 12", "68723 Schwetzingen"],
                       recipient=recip(fg, who), number="LW-27-1180", date="02.03.2027", valid="02.04.2027", items=items)
    o2, n2, g2 = offer(vendor="Zentrifugen-Service Haldorf KG", vendor_lines=["Am Wasserturm 3", "34117 Kassel"],
                       recipient=recip(fg, who), number="ZH 2027/089", date="04.03.2027", valid="30.04.2027",
                       items=[("Kühlzentrifuge mit Ausschwingrotor 4 x 750 ml", 1, 7240.00), ("Adapter 50 ml (Satz)", 4, 89.00)])
    o3, n3, g3 = offer(vendor="BIOTEC Handel Ostwald AG", vendor_lines=["Elbchaussee 410", "22609 Hamburg"],
                       recipient=recip(fg, who), number="BO-A-55120", date="05.03.2027", valid="05.04.2027",
                       items=[("Refrigerated centrifuge, swing-out rotor 4 x 750 ml", 1, 7015.00), ("Adapter set 50 ml", 4, 104.00)])
    form, _, _ = proc_form(number="ZB-2027-0211", date="09.03.2027", fachgebiet=fg, requester=who, phone="0561 7390-4180",
                           kostenstelle="71 4290 / Auftrag 2140188", holder="Prof. Dr. Torben Ahlgrimm", category="Anlage",
                           framework=False, procedure="Preisvergleich, drei schriftliche Angebote", offers=3,
                           supplier="Laborgeräte Wiesenthal GmbH, Schwetzingen (Angebot LW-27-1180)", items=items,
                           begruendung="Ersatz der defekten Zentrifuge (Baujahr 2009) im S1-Labor. Drei Angebote "
                                       "eingeholt; das Angebot der Laborgeräte Wiesenthal GmbH ist das günstigste.")
    write(d / "angebot-1.pdf", o1), write(d / "angebot-2.pdf", o2), write(d / "angebot-3.pdf", o3)
    write(d / "beschaffungsantrag.pdf", form)
    write(d / "vergabevermerk.pdf", award_note(
        number="V-27-0131", antrag="ZB-2027-0211", subject="Kühlzentrifuge mit Adaptern",
        bids=[bid("Laborgeräte Wiesenthal GmbH", "LW-27-1180", "02.03.2027", n1, g1, 1),
              bid("Zentrifugen-Service Haldorf KG", "ZH 2027/089", "04.03.2027", n2, g2, 3),
              bid("BIOTEC Handel Ostwald AG", "BO-A-55120", "05.03.2027", n3, g3, 2)],
        winner=f"Laborgeräte Wiesenthal GmbH, {eur(n1)} netto",
        reason="Alle Geräte erfüllen die Anforderungen. Zuschlag an das günstigste Angebot.",
        date="10.03.2027", clerk="Wiebke Schallenberg"))

    # 02 abgelehnt: award to the second cheapest without any reason
    d = case(PROCUREMENT, 2, "abgelehnt", "Zuschlag an das zweitgünstigste Angebot ohne Begründung",
             "Zuschlag an das wirtschaftlichste Angebot; Abweichung begründen", SRC_PROC, True)
    who, fg = "Dr. Levin Szymanski", "Fachgebiet Optische Technologien"
    o1, n1, g1 = offer(vendor="Photonik-Vertrieb Ambrosius GmbH", vendor_lines=["Carl-Zeiss-Ring 8", "07745 Jena"],
                       recipient=recip(fg, who), number="PA-27-0442", date="12.04.2027", valid="12.05.2027",
                       items=[("Optischer Tisch 1500 x 900 mm, passiv gedämpft", 1, 3980.00), ("Montageset M6", 1, 145.00)])
    o2, n2, g2 = offer(vendor="Laseroptik Brandau KG", vendor_lines=["Feldstraße 55", "24105 Kiel"],
                       recipient=recip(fg, who), number="LB-1907", date="13.04.2027", valid="13.05.2027",
                       items=[("Optical table 1500 x 900 mm, passive damping", 1, 4310.00), ("Mounting kit M6", 1, 160.00)])
    items2 = [("Optical table 1500 x 900 mm, passive damping", 1, 4310.00), ("Mounting kit M6", 1, 160.00)]
    o3, n3, g3 = offer(vendor="Schwingungstechnik Udenbach GmbH", vendor_lines=["Hafenweg 9", "48155 Münster"],
                       recipient=recip(fg, who), number="SU-A-3371", date="15.04.2027", valid="15.06.2027",
                       items=[("Schwingungsisolierter Labortisch 1,5 x 0,9 m", 1, 4590.00), ("Montagezubehör", 1, 120.00)])
    form, _, _ = proc_form(number="ZB-2027-0276", date="19.04.2027", fachgebiet=fg, requester=who, phone="0561 7390-4377",
                           kostenstelle="71 4555 / Auftrag 2140233", holder="Prof. Dr. Clementine Faber", category="Anlage",
                           framework=False, procedure="Preisvergleich, drei schriftliche Angebote", offers=3,
                           supplier="Laseroptik Brandau KG, Kiel (Angebot LB-1907)", items=items2,
                           begruendung="Aufbau eines zweiten interferometrischen Messplatzes. Bestellung bei der "
                                       "Laseroptik Brandau KG.")
    write(d / "angebot-1.pdf", o1), write(d / "angebot-2.pdf", o2), write(d / "angebot-3.pdf", o3)
    write(d / "beschaffungsantrag.pdf", form)
    write(d / "vergabevermerk.pdf", award_note(
        number="V-27-0177", antrag="ZB-2027-0276", subject="Optischer Tisch mit Montageset",
        bids=[bid("Photonik-Vertrieb Ambrosius GmbH", "PA-27-0442", "12.04.2027", n1, g1, 1),
              bid("Laseroptik Brandau KG", "LB-1907", "13.04.2027", n2, g2, 2),
              bid("Schwingungstechnik Udenbach GmbH", "SU-A-3371", "15.04.2027", n3, g3, 3)],
        winner=f"Laseroptik Brandau KG, {eur(n2)} netto", reason="Zuschlag an die Laseroptik Brandau KG.",
        date="20.04.2027", clerk="Ruben Kramm"))

    # 03 angenommen (trap): not the cheapest, but the cheapest misses a documented requirement
    d = case(PROCUREMENT, 3, "angenommen", "Falle: nicht das günstigste Angebot, günstigstes erfüllt Anforderung "
             "(-80 °C) nachweislich nicht", "Wirtschaftlichstes geeignetes Angebot; Abweichung begründet", SRC_PROC, True)
    who, fg = "Dr. Wanda Kerschbaumer", "Fachgebiet Biosensorik"
    o1, n1, g1 = offer(vendor="Kältetechnik Rautmann GmbH", vendor_lines=["Lindenallee 4", "30159 Hannover"],
                       recipient=recip(fg, who), number="KR-27-215", date="03.05.2027", valid="03.06.2027",
                       items=[("Tiefkühlschrank 400 l, Temperaturbereich -20 bis -40 °C", 1, 3150.00)])
    items = [("Ultratiefkühlschrank 400 l, Temperaturbereich -50 bis -86 °C, Alarmmodul", 1, 4820.00)]
    o2, n2, g2 = offer(vendor="Cryolab Seidenstücker KG", vendor_lines=["Saarstraße 21", "55122 Mainz"],
                       recipient=recip(fg, who), number="CS 27-0388", date="04.05.2027", valid="30.06.2027", items=items)
    o3, n3, g3 = offer(vendor="Laborkälte Meinhold GmbH", vendor_lines=["Bergstraße 77", "01069 Dresden"],
                       recipient=recip(fg, who), number="LM-A-11807", date="06.05.2027", valid="06.06.2027",
                       items=[("ULT-Gefrierschrank 400 l, -86 °C, mit Fernalarm", 1, 5190.00)])
    form, _, _ = proc_form(number="ZB-2027-0330", date="10.05.2027", fachgebiet=fg, requester=who, phone="0561 7390-4920",
                           kostenstelle="71 4930 / Auftrag 2140291", holder="Prof. Dr. Ansgar Liebetrau", category="Anlage",
                           framework=False, procedure="Preisvergleich, drei schriftliche Angebote", offers=3,
                           supplier="Cryolab Seidenstücker KG, Mainz (Angebot CS 27-0388)", items=items,
                           begruendung="Lagerung von Enzymproben bei mindestens -80 °C (Leistungsverzeichnis Punkt 1). "
                                       "Das Angebot KR-27-215 erreicht nur -40 °C und scheidet aus; von den geeigneten "
                                       "Angeboten ist Cryolab Seidenstücker das günstigste.")
    write(d / "angebot-1.pdf", o1), write(d / "angebot-2.pdf", o2), write(d / "angebot-3.pdf", o3)
    write(d / "beschaffungsantrag.pdf", form)
    write(d / "vergabevermerk.pdf", award_note(
        number="V-27-0204", antrag="ZB-2027-0330", subject="Ultratiefkühlschrank 400 l, mindestens -80 °C",
        criterion="Preis (netto) der Angebote, die das Leistungsverzeichnis erfüllen",
        bids=[bid("Kältetechnik Rautmann GmbH", "KR-27-215", "03.05.2027", n1, g1, "–"),
              bid("Cryolab Seidenstücker KG", "CS 27-0388", "04.05.2027", n2, g2, 1),
              bid("Laborkälte Meinhold GmbH", "LM-A-11807", "06.05.2027", n3, g3, 2)],
        winner=f"Cryolab Seidenstücker KG, {eur(n2)} netto",
        reason="Angebot KR-27-215 ist ausgeschlossen: Temperaturbereich nur bis -40 °C, gefordert sind mindestens "
               "-80 °C. Von den geeigneten Angeboten ist das der Cryolab Seidenstücker KG das günstigste.",
        date="11.05.2027", clerk="Hiltrud Nopper"))

    # 04 abgelehnt: order split into two direct awards to stay below 1,000 EUR
    d = case(PROCUREMENT, 4, "abgelehnt", "Auftragsteilung: zwei Direktaufträge à 940 € beim selben Händler",
             "Direktvergabe nur unter 1.000 € Auftragswert; Teilung zur Umgehung unzulässig", SRC_CATER, True,
             uncertain=True)
    o1, _, _ = offer(vendor="3D-Druck Fabrik Ehlers", vendor_lines=["Kanalstraße 9", "44147 Dortmund"],
                     recipient=recip("Fachgebiet Produktionstechnik", "Finn Ahrendt"), number="FE-27-0612",
                     date="07.06.2027", valid="07.07.2027",
                     items=[("FDM-3D-Drucker, Bauraum 300 x 300 x 400 mm, Doppelextruder", 2, 940.00)])
    write(d / "angebot-1.pdf", o1)
    write(d / "email-beschaffungsantrag.pdf", email(
        mailbox="finn.ahrendt@uni-wernstadt.de", url=owa("wernstadt"), subject="Zwei Direktaufträge 3D-Drucker",
        sender="Finn Ahrendt &lt;finn.ahrendt@uni-wernstadt.de&gt;", sent="Mi 09.06.2027 09:40",
        to="beschaffung@uni-wernstadt.de", cc="Prof. Dr. Hartwig Lammers &lt;hartwig.lammers@uni-wernstadt.de&gt;",
        body=["Hallo zusammen,", "wir benötigen für das Projektlabor zwei baugleiche 3D-Drucker laut beiliegendem Angebot "
              "FE-27-0612 (je 940,00 € netto).",
              "Bitte lösen Sie dazu zwei getrennte Direktaufträge aus, einen heute und einen nächste Woche, jeweils über "
              "einen Drucker. So bleiben wir je Auftrag unter der Wertgrenze von 1.000 € und brauchen keine "
              "Vergleichsangebote.", "Kostenstelle 71 4405, Auftrag 2140315. Prof. Lammers hat die Bestellung beauftragt.",
              "Viele Grüße<br/>Finn Ahrendt"]))

    # 05 angenommen (trap): direct award, net below 1,000 EUR although gross is above
    d = case(PROCUREMENT, 5, "angenommen", "Falle: Direktvergabe mit 948 € netto (1.128,12 € brutto), ein Angebot",
             "Direktvergabe unter 1.000 € Auftragswert (netto)", SRC_CATER, True, uncertain=True)
    o1, _, _ = offer(vendor="Messtechnik Hagenah e.K.", vendor_lines=["Lange Straße 40", "26122 Oldenburg"],
                     recipient=recip("Fachgebiet Elektrische Messtechnik", "Kasimir Treppner"), number="MH-27-1104",
                     date="14.06.2027", valid="14.07.2027",
                     items=[("Funktionsgenerator 2 Kanäle, 60 MHz", 1, 812.00), ("BNC-Kabelsatz, 10-teilig", 2, 68.00)])
    write(d / "angebot-1.pdf", o1)
    write(d / "email-beschaffungsantrag.pdf", email(
        mailbox="k.dorfmeister@uni-wernstadt.de", url=owa("wernstadt"),
        subject="Direktauftrag Funktionsgenerator Praktikum", sender="Kasimir Treppner &lt;k.dorfmeister@uni-wernstadt.de&gt;",
        sent="Do 17.06.2027 14:05", to="beschaffung@uni-wernstadt.de",
        cc="Prof. Dr. Folasade Eichelkraut &lt;folasade.eichelkraut@uni-wernstadt.de&gt;",
        body=["Sehr geehrte Damen und Herren,", "für das Grundlagenpraktikum bitte ich um Bestellung gemäß Angebot "
              "MH-27-1104 der Messtechnik Hagenah e.K.: 1 × Funktionsgenerator (812,00 € netto) und 2 × BNC-Kabelsatz "
              "(je 68,00 € netto).", "Summe 948,00 € netto, 1.128,12 € brutto. Direktvergabe, da der Auftragswert unter "
              "1.000 € liegt.", "Kostenstelle 71 4630, Auftrag 2140112. Frau Prof. Eichelkraut ist in Kopie und hat die "
              "Bestellung beauftragt.", "Mit freundlichen Grüßen<br/>Kasimir Treppner"]))

    # 06 abgelehnt: Microsoft licences from a reseller instead of the framework partner
    d = case(PROCUREMENT, 6, "abgelehnt", "Microsoft-Office-Lizenzen bei einem Webshop-Händler (ein Angebot)",
             "Rahmenvertrag für Microsoft-Software verbindlich", SRC_FRAME, True)
    items = [("Microsoft Office LTSC Standard 2024, Volumenlizenz", 5, 249.00)]
    o1, _, _ = offer(vendor="Softwarepoint Lindemann GmbH", vendor_lines=["Hansaring 40", "50670 Köln"],
                     recipient=recip("Fachgebiet Wirtschaftsinformatik", "Greta Vahldiek"), number="SPL-A-88130",
                     date="05.07.2027", valid="19.07.2027", items=items)
    form, _, _ = proc_form(number="ZB-2027-0466", date="06.07.2027", fachgebiet="Fachgebiet Wirtschaftsinformatik",
                           requester="Greta Vahldiek", phone="0561 7390-5302", kostenstelle="71 5110 / Auftrag 2140377",
                           holder="Prof. Dr. Ingmar Rautenstrauch", category="Verbrauchsmaterial", framework=False,
                           procedure="Direktauftrag", offers=1, supplier="Softwarepoint Lindemann GmbH, Köln",
                           items=items, begruendung="Office-Lizenzen für die fünf neuen Rechner im Seminarraum. Der "
                                                    "Händler bietet die Lizenzen günstig und sofort an.")
    write(d / "angebot-1.pdf", o1), write(d / "beschaffungsantrag.pdf", form)

    # 07 abgelehnt: office chairs with three offers, but office swivel chairs have a framework contract
    d = case(PROCUREMENT, 7, "abgelehnt", "Bürodrehstühle mit drei Angeboten beim Möbelhandel statt Rahmenvertrag",
             "Rahmenvertrag Bürodrehstühle; drei Angebote heilen das nicht", SRC_FRAME, True)
    who, fg = "Heike Tammen-Schulz", "Fachgebiet Nachrichtentechnik (Sekretariat)"
    items = [("Bürodrehstuhl Synchronmechanik, Lordosenstütze, Armlehnen 4D", 4, 389.00)]
    o1, n1, g1 = offer(vendor="Büromöbel Ostermann GmbH", vendor_lines=["Gewerbering 11", "33602 Bielefeld"],
                       recipient=recip(fg, who), number="BO-27-7781", date="10.08.2027", valid="10.09.2027", items=items)
    o2, n2, g2 = offer(vendor="Sitz &amp; Raum Handelsges. mbH", vendor_lines=["Poststraße 2", "20354 Hamburg"],
                       recipient=recip(fg, who), number="SR-4410", date="11.08.2027", valid="11.09.2027",
                       items=[("Ergonomischer Drehstuhl mit Synchronmechanik", 4, 412.00)])
    o3, n3, g3 = offer(vendor="Office Comfort Wendt KG", vendor_lines=["Am Markt 6", "34117 Kassel"],
                       recipient=recip(fg, who), number="OCW 27-118", date="12.08.2027", valid="12.09.2027",
                       items=[("Drehstuhl ergonomisch, Armlehnen verstellbar", 4, 436.50)])
    form, _, _ = proc_form(number="ZB-2027-0512", date="16.08.2027", fachgebiet=fg, requester=who, phone="0561 7390-4011",
                           kostenstelle="71 4380 / Auftrag 2140402", holder="Prof. Dr. Raphael Ochsenreiter", category="GWG",
                           framework=False, procedure="Preisvergleich, drei schriftliche Angebote", offers=3,
                           supplier="Büromöbel Ostermann GmbH, Bielefeld (Angebot BO-27-7781)", items=items,
                           begruendung="Ersatz von vier verschlissenen Stühlen in den Mitarbeiterbüros. Drei Angebote "
                                       "eingeholt, Zuschlag an das günstigste.")
    write(d / "angebot-1.pdf", o1), write(d / "angebot-2.pdf", o2), write(d / "angebot-3.pdf", o3)
    write(d / "beschaffungsantrag.pdf", form)
    write(d / "vergabevermerk.pdf", award_note(
        number="V-27-0301", antrag="ZB-2027-0512", subject="Vier Bürodrehstühle",
        bids=[bid("Büromöbel Ostermann GmbH", "BO-27-7781", "10.08.2027", n1, g1, 1),
              bid("Sitz &amp; Raum Handelsges. mbH", "SR-4410", "11.08.2027", n2, g2, 2),
              bid("Office Comfort Wendt KG", "OCW 27-118", "12.08.2027", n3, g3, 3)],
        winner=f"Büromöbel Ostermann GmbH, {eur(n1)} netto", reason="Zuschlag an das günstigste Angebot.",
        date="17.08.2027", clerk="Ruben Kramm"))

    # 08 angenommen: bottled gases from the framework catalogue via WPS, no offers needed
    d = case(PROCUREMENT, 8, "angenommen", "Flaschengase aus WPS-Rahmenvertragskatalog, 2.142,96 € netto ohne Vergleichsangebote",
             "Rahmenvertrag Flaschengase über WPS; Vergleichsangebote entfallen", SRC_FRAME, True)
    cart = [("RV-FG-AR50", "Argon 5.0, Flasche 50 l, 200 bar", 6, 185.00),
            ("RV-FG-N250", "Stickstoff 5.0, Flasche 50 l, 200 bar", 6, 132.50),
            ("RV-FG-MIET", "Flaschenmiete je Flasche und Quartal", 12, 19.83)]
    cart_st, net = wps_cart(number="WK-0027-21407", catalog="Rahmenvertrag Flaschengase (außer Helium) der hessischen "
                            "Hochschulen", supplier="Gasversorgung Rheintal GmbH (Rahmenvertragspartner)",
                            created="2027-09-06", buyer="Dr. Bettina Holtfreter", account="71 4815 / Auftrag 2140430",
                            items=cart)
    form, _, _ = proc_form(number="ZB-2027-0587", date="06.09.2027", fachgebiet="Fachgebiet Plasmatechnik",
                           requester="Dr. Bettina Holtfreter", phone="0561 7390-4815",
                           kostenstelle="71 4815 / Auftrag 2140430", holder="Prof. Dr. Volkmar Ehrhardt",
                           category="Verbrauchsmaterial", framework=True,
                           procedure="Abruf aus Rahmenvertrag über WPS (Warenkorb WK-0027-21407)", offers=0,
                           supplier="Gasversorgung Rheintal GmbH", items=wps_items(cart),
                           begruendung="Prozessgase für die Plasmabeschichtungsanlage im Wintersemester. Alle Artikel "
                                       "aus dem Rahmenvertragskatalog Flaschengase.")
    write(d / "beschaffungsantrag.pdf", form), write(d / "wps-warenkorb.pdf", cart_st)

    # 09 abgelehnt: not commissioned by the budget holder
    d = case(PROCUREMENT, 9, "abgelehnt", "Kostenstellenbevollmächtigte:r hat nicht beauftragt (Unterschrift fehlt, "
             "nicht in Kopie)", "Bestellungen müssen vom Kostenstellenbevollmächtigten beauftragt werden", SRC_PROC, True)
    who, fg = "Aylin Demirtas-Holm", "Fachgebiet Akustik"
    items = [("Messmikrofon 1/2 Zoll, Klasse 1, mit Vorverstärker", 2, 1180.00), ("Akustischer Kalibrator 94/114 dB", 1, 640.00)]
    o1, n1, g1 = offer(vendor="Akustiktechnik Feddersen GmbH", vendor_lines=["Wallstraße 9", "24103 Kiel"],
                       recipient=recip(fg, who), number="AF-27-0991", date="13.09.2027", valid="13.10.2027", items=items)
    o2, n2, g2 = offer(vendor="Schall &amp; Messung Ruppert KG", vendor_lines=["Rheinallee 30", "55118 Mainz"],
                       recipient=recip(fg, who), number="SMR-2207", date="14.09.2027", valid="14.10.2027",
                       items=[("Messmikrofon Kl. 1 inkl. Vorverstärker", 2, 1245.00), ("Kalibrator Kl. 1", 1, 615.00)])
    o3, n3, g3 = offer(vendor="Audiomesstechnik Lenzen GmbH", vendor_lines=["Industriestraße 3", "52068 Aachen"],
                       recipient=recip(fg, who), number="AL 27/406", date="15.09.2027", valid="15.11.2027",
                       items=[("Free-field measurement microphone 1/2\" class 1 with preamp", 2, 1299.00),
                              ("Sound calibrator class 1", 1, 598.00)])
    form, _, _ = proc_form(number="ZB-2027-0601", date="17.09.2027", fachgebiet=fg, requester=f"{who} (Doktorandin)",
                           phone="0561 7390-4744", kostenstelle="71 4744 / Auftrag 2140447",
                           holder="Prof. Dr. Sebald Overbeck", category="Anlage", framework=False,
                           procedure="Preisvergleich, drei schriftliche Angebote", offers=3,
                           supplier="Akustiktechnik Feddersen GmbH, Kiel (Angebot AF-27-0991)", items=items, signed=False,
                           begruendung="Messkette für den neuen reflexionsarmen Raum. Drei Angebote; Feddersen ist das "
                                       "günstigste.")
    write(d / "angebot-1.pdf", o1), write(d / "angebot-2.pdf", o2), write(d / "angebot-3.pdf", o3)
    write(d / "beschaffungsantrag.pdf", form)
    write(d / "email-antrag.pdf", email(
        mailbox="aylin.demirtas-holm@uni-wernstadt.de", url=owa("wernstadt"), subject="Beschaffungsantrag ZB-2027-0601 Messmikrofone",
        sender="Aylin Demirtas-Holm &lt;aylin.demirtas-holm@uni-wernstadt.de&gt;", sent="Fr 17.09.2027 18:22",
        to="beschaffung@uni-wernstadt.de",
        body=["Guten Abend,", "anbei Antrag und drei Angebote für die Messmikrofone. Prof. Overbeck ist bis Ende Oktober "
              "im Forschungssemester und nicht erreichbar; ich reiche den Antrag deshalb schon einmal ohne seine "
              "Unterschrift ein, damit die Mikrofone vor Semesterbeginn da sind.", "Viele Grüße<br/>Aylin Demirtas-Holm"]))

    # 10 angenommen: Sallstedt, three offers in an e-mail thread, invoice matches the order
    d = case(PROCUREMENT, 10, "angenommen", "TH Sallstedt: drei Angebote im Mailverlauf, günstigstes, Rechnung = Angebot",
             "Nach Aktenlage vollständig (anderes Landesrecht)", "", False)
    rec = ["Technische Hochschule Sallstedt", "Labor Fertigungstechnik", "z. Hd. Prof. Dr. Ruth Kalinke", "Brühlstraße 7",
           "99643 Sallstedt"]
    items = [("Digitaler Messschieber 0–300 mm, IP67", 6, 189.00), ("Bügelmessschraube 0–25 mm, digital", 6, 142.00)]
    o1, n1, _ = offer(vendor="Präzisionswerkzeuge Ahrens GmbH", vendor_lines=["Talstraße 14", "98527 Suhl"],
                      recipient=rec, number="PA-27-3318", date="04.10.2027", valid="04.11.2027", items=items)
    o2, n2, _ = offer(vendor="Messzeug Kolbe OHG", vendor_lines=["Neumarkt 2", "04109 Leipzig"], recipient=rec,
                      number="K-27-882", date="06.10.2027", valid="06.11.2027",
                      items=[("Messschieber digital 300 mm", 6, 198.00), ("Mikrometer digital 0–25 mm", 6, 149.50)])
    o3, n3, _ = offer(vendor="Werkstattbedarf Lüdtke KG", vendor_lines=["Hafenstraße 81", "18055 Rostock"], recipient=rec,
                      number="WL-5512", date="07.10.2027", valid="07.12.2027",
                      items=[("Digital-Messschieber 300 mm", 6, 205.00), ("Digital-Bügelmessschraube 25 mm", 6, 139.00)])
    write(d / "angebot-1.pdf", o1), write(d / "angebot-2.pdf", o2), write(d / "angebot-3.pdf", o3)
    write(d / "email-korrespondenz.pdf", email(
        mailbox="ruth.kalinke@th-sallstedt.de", url=owa("sallstedt"), subject="Bestellung Messmittel Labor Fertigungstechnik",
        sender="Prof. Dr. Ruth Kalinke &lt;ruth.kalinke@th-sallstedt.de&gt;", sent="Mo 11.10.2027 08:50",
        to="Einkauf &lt;einkauf@th-sallstedt.de&gt;",
        body=["Sehr geehrte Damen und Herren,", f"für das Labor Fertigungstechnik bitte ich um Bestellung bei der "
              f"Präzisionswerkzeuge Ahrens GmbH gemäß Angebot PA-27-3318 über {eur(n1)} netto. Die Vergleichsangebote "
              f"K-27-882 (Messzeug Kolbe, {eur(n2)}) und WL-5512 (Werkstattbedarf Lüdtke, {eur(n3)}) liegen bei; Ahrens "
              f"ist das günstigste.", "Haushaltsstelle 0712.51104, Projekt LF-27-02.",
              "Mit freundlichen Grüßen<br/>Ruth Kalinke"]))
    inv, _ = invoice(vendor="Präzisionswerkzeuge Ahrens GmbH", vendor_lines=["Talstraße 14", "98527 Suhl"], recipient=rec,
                     refs=[("Rechnung Nr.", "RE-27-20155"), ("Datum:", "25.10.2027"),
                           ("Ihre Bestellung:", "EK-2027-5120 vom 12.10.2027"), ("Angebot:", "PA-27-3318")],
                     items=items, notes=["Zahlbar innerhalb von 30 Tagen ohne Abzug."],
                     extra=[stamp("SACHLICH RICHTIG", "TH Sallstedt / Labor FT", "27.10.2027 R. Kalinke")])
    write(d / "rechnung.pdf", inv)

    # 11 abgelehnt: Sallstedt, invoice exceeds the accepted offer by an unordered item
    d = case(PROCUREMENT, 11, "abgelehnt", "TH Sallstedt: Rechnung enthält nicht beauftragte Montagepauschale "
             "(+285 € netto über Angebot)", "Rechnungen müssen dem beauftragten Angebot entsprechen", "", True)
    rec = ["Technische Hochschule Sallstedt", "Medienlabor", "z. Hd. Dr. Ilka Sonnabend-Rüger", "Brühlstraße 7",
           "99643 Sallstedt"]
    items = [("Akustikabsorber 120 x 60 cm, Wandmontage", 16, 98.00), ("Deckensegel 120 x 120 cm", 4, 153.00)]
    o1, n1, _ = offer(vendor="Raumakustik Pohlmann GmbH", vendor_lines=["Klosterstraße 3", "99084 Erfurt"],
                      recipient=rec, number="RP-27-0715", date="01.07.2027", valid="01.08.2027", items=items)
    write(d / "angebot-1.pdf", o1)
    write(d / "email-korrespondenz.pdf", email(
        mailbox="einkauf@th-sallstedt.de", url=owa("sallstedt"), subject="AW: Bestellung Akustikelemente Medienlabor",
        sender="Thore Mählmann &lt;einkauf@th-sallstedt.de&gt;", sent="Fr 09.07.2027 10:12",
        to="Dr. Ilka Sonnabend-Rüger &lt;ilka.sonnabend-rueger@th-sallstedt.de&gt;",
        body=["Sehr geehrte Frau Dr. Sonnabend-Rüger,", f"die Bestellung EK-2027-3390 über {eur(n1)} netto gemäß "
              "Angebot RP-27-0715 ist an die Raumakustik Pohlmann GmbH gegangen (Direktauftrag nach Preisabfrage, "
              "Vermerk liegt in der Akte). Die Montage übernimmt der Hausdienst.", "Freundliche Grüße<br/>Thore Mählmann"],
        quoted=[{"from": "Dr. Ilka Sonnabend-Rüger", "sent": "Mi 07.07.2027 15:40", "to": "einkauf@th-sallstedt.de",
                 "subject": "Bestellung Akustikelemente Medienlabor",
                 "body": ["bitte bestellen Sie die Akustikelemente laut Angebot RP-27-0715 ohne Montage."]}]))
    inv, _ = invoice(vendor="Raumakustik Pohlmann GmbH", vendor_lines=["Klosterstraße 3", "99084 Erfurt"], recipient=rec,
                     refs=[("Rechnung Nr.", "RP-R-27-1021"), ("Datum:", "02.08.2027"),
                           ("Ihre Bestellung:", "EK-2027-3390 vom 09.07.2027")],
                     items=items + [("Montagepauschale vor Ort (2 Monteure, 1 Tag)", 1, 285.00)],
                     notes=["Zahlbar innerhalb von 14 Tagen."])
    write(d / "rechnung.pdf", inv + [Spacer(1, 8), Paragraph("Bitte sachlich richtig zeichnen und anweisen. I. S.-R.", HAND)])

    # 12 angenommen (trap): cheapest offer is a foreign English quotation without German VAT (reverse charge)
    d = case(PROCUREMENT, 12, "angenommen", "Falle: günstigstes Angebot englisch aus NL ohne USt (Reverse Charge), "
             "Wertung netto korrekt", "Zuschlag an das günstigste Angebot (netto)", SRC_PROC, True)
    who, fg = "Dr. Helmut Quandt-Obi", "Fachgebiet Hochspannungstechnik"
    items = [("High-voltage probe 40 kV, 1000:1, 50 MHz", 2, 1460.00), ("Differential probe 1.5 kV, 100 MHz", 2, 890.00)]
    o1, n1, g1 = offer(vendor="Voltix Instruments B.V.", vendor_lines=["Science Park 402", "1098 XH Amsterdam, NL",
                                                                       "VAT NL 8611.04.522.B01"],
                       recipient=recip(fg, who), number="VX-Q-27-0233", date="1 Feb 2027", valid="3 Mar 2027",
                       items=items, vat=0.0, lang="en",
                       notes=["Intra-Community supply, reverse charge (Art. 196 VAT Directive). VAT to be accounted for "
                              "by the customer."])
    o2, n2, g2 = offer(vendor="Hochspannungs-Messtechnik Gerdes GmbH", vendor_lines=["Weserstraße 30", "28199 Bremen"],
                       recipient=recip(fg, who), number="HG-27-0094", date="02.02.2027", valid="02.03.2027",
                       items=[("Hochspannungstastkopf 40 kV, 1000:1", 2, 1520.00), ("Differenztastkopf 1,5 kV", 2, 905.00)])
    o3, n3, g3 = offer(vendor="Elektromess Tannhäuser KG", vendor_lines=["Rosenheimer Straße 12", "81669 München"],
                       recipient=recip(fg, who), number="ET 27/0311", date="04.02.2027", valid="04.04.2027",
                       items=[("HV-Tastkopf 40 kV", 2, 1495.00), ("Differenztastkopf 1500 V", 2, 948.00)])
    form, _, _ = proc_form(number="ZB-2027-0098", date="08.02.2027", fachgebiet=fg, requester=who, phone="0561 7390-4566",
                           kostenstelle="71 4566 / Auftrag 2140074", holder="Prof. Dr. Gerlinde Wassermann",
                           category="Anlage", framework=False, procedure="Preisvergleich, drei schriftliche Angebote",
                           offers=3, supplier="Voltix Instruments B.V., Amsterdam (Angebot VX-Q-27-0233)", items=items,
                           begruendung="Tastköpfe für die Teilentladungsmessung. Wertung netto; das Angebot der Voltix "
                                       "Instruments B.V. ist das günstigste (innergemeinschaftliche Lieferung, die "
                                       "Erwerbsteuer führt die Universität ab).")
    write(d / "angebot-1.pdf", o1), write(d / "angebot-2.pdf", o2), write(d / "angebot-3.pdf", o3)
    write(d / "beschaffungsantrag.pdf", form)
    write(d / "vergabevermerk.pdf", award_note(
        number="V-27-0061", antrag="ZB-2027-0098", subject="Hochspannungs- und Differenztastköpfe",
        bids=[bid("Voltix Instruments B.V.", "VX-Q-27-0233", "01.02.2027", n1, round(n1 * 1.19, 2), 1),
              bid("Hochspannungs-Messtechnik Gerdes GmbH", "HG-27-0094", "02.02.2027", n2, g2, 2),
              bid("Elektromess Tannhäuser KG", "ET 27/0311", "04.02.2027", n3, g3, 3)],
        winner=f"Voltix Instruments B.V., {eur(n1)} netto",
        reason="Wertung netto. Für das Angebot aus den Niederlanden ist der Bruttowert einschließlich der von der "
               "Universität abzuführenden Erwerbsteuer (19 %) angegeben. Zuschlag an das günstigste Angebot.",
        date="09.02.2027", clerk="Wiebke Schallenberg"))


# --------------------------------------------------------------------------- #

def link_corpora(corpora, target):
    """Hard links keep the 100 MB corpora out of the disk budget; copy where linking fails."""
    for src in sorted(corpora.glob("*/documents.jsonl.gz")):
        dst = target / src.parent.name / src.name
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists():
            continue
        try:
            os.link(src, dst)
        except OSError:
            shutil.copy2(src, dst)


def main():
    global OUT
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--corpora", type=Path, default=DEFAULT_CORPORA)
    args = parser.parse_args()
    OUT = args.out
    for dataset in (TRIP, EXPENSE, PROCUREMENT):
        shutil.rmtree(OUT / dataset / "inputs", ignore_errors=True)
    trip_cases(), expense_cases(), procurement_cases()
    # Outside the dataset folders: the evaluator reads every *.jsonl in a truths folder.
    with open(OUT / "cases.jsonl", "w", encoding="utf-8") as f:
        f.writelines(json.dumps(c, ensure_ascii=False) + "\n" for c in CASES)
    for dataset in (TRIP, EXPENSE, PROCUREMENT):
        rows = [c for c in CASES if c["dataset"] == dataset]
        with open(OUT / dataset / "ground-truth.jsonl", "w", encoding="utf-8") as f:
            f.writelines(json.dumps({"antrag": c["antrag"], "result": c["result"]}, ensure_ascii=False) + "\n" for c in rows)
        if args.corpora.is_dir():
            link_corpora(args.corpora, OUT / dataset / "inputs" / "retrieval-corpora")
        labels = [c["result"] for c in rows]
        print(f"{dataset}: {len(rows)} cases, {labels.count('angenommen')} angenommen, {labels.count('abgelehnt')} abgelehnt")


if __name__ == "__main__":
    main()
