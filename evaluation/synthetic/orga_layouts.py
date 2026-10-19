"""Document layouts of the organisers' business-trip example generator, for the coverage cases (family C1).

Copied, not imported, from `uniagent-code/cikm26/datasets/business-trip-spot-check/make_examples.py` (lines 9-282):
that file has no `__main__` guard and writes its PDFs into `uniagent-code` on import. Changes: the module-level
output paths and the `print` after each build are removed; the layouts and styles are unchanged.
"""
import os

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

GREY = colors.HexColor("#666666")
LIGHT = colors.HexColor("#efefef")
LINE = colors.HexColor("#b4b4b4")

P = ParagraphStyle("p", fontName="Helvetica", fontSize=9, leading=12)
PS = ParagraphStyle("ps", parent=P, fontSize=7.5, leading=9.5, textColor=GREY)
PB = ParagraphStyle("pb", parent=P, fontName="Helvetica-Bold")
H1 = ParagraphStyle("h1", parent=P, fontName="Helvetica-Bold", fontSize=14, leading=18)
H2 = ParagraphStyle("h2", parent=P, fontName="Helvetica-Bold", fontSize=10, leading=14,
                    spaceBefore=8, spaceAfter=3)
RIGHT = ParagraphStyle("r", parent=P, alignment=2)
RIGHTS = ParagraphStyle("rs", parent=PS, alignment=2)


def _doc(path, top=2.0 * cm, bottom=1.8 * cm):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return SimpleDocTemplate(
        path, pagesize=A4, leftMargin=2.2 * cm, rightMargin=2.0 * cm,
        topMargin=top, bottomMargin=bottom, title=os.path.basename(path),
        author="", subject="", creator="",
    )


def kv_table(rows, widths=(5.4 * cm, 11.0 * cm), bold_keys=()):
    data = []
    for k, v in rows:
        ks = PB if k in bold_keys else P
        data.append([Paragraph(k, ks), Paragraph(v, PB if k in bold_keys else P)])
    t = Table(data, colWidths=list(widths))
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 1.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("LINEBELOW", (0, 0), (-1, -2), 0.25, colors.HexColor("#e2e2e2")),
    ]))
    return t


def money_table(rows, total=None, widths=(10.6 * cm, 3.0 * cm, 2.8 * cm)):
    data = [[Paragraph("<b>Position</b>", P), Paragraph("<b>Menge</b>", RIGHT),
             Paragraph("<b>Betrag</b>", RIGHT)]]
    for pos, qty, amount in rows:
        data.append([Paragraph(pos, P), Paragraph(qty, RIGHT), Paragraph(amount, RIGHT)])
    if total:
        data.append([Paragraph("<b>%s</b>" % total[0], P), Paragraph("", RIGHT),
                     Paragraph("<b>%s</b>" % total[1], RIGHT)])
    t = Table(data, colWidths=list(widths))
    style = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.black),
        ("LINEBELOW", (0, 1), (-1, -2), 0.25, colors.HexColor("#e2e2e2")),
        ("BACKGROUND", (0, 0), (-1, 0), LIGHT),
    ]
    if total:
        style.append(("LINEABOVE", (0, -1), (-1, -1), 0.6, colors.black))
    t.setStyle(TableStyle(style))
    return t


# --------------------------------------------------------------------------- #
# 1. Dienstreiseantrag (SAP/ESS-style travel request form)
# --------------------------------------------------------------------------- #

FB16 = ["Universität Kassel", "Fachbereich 16", "Elektrotechnik / Informatik",
        "Wilhelmshöher Allee 71-73", "34121 Kassel"]


def antrag_pdf(path, *, reisenummer, name, fachgebiet, personalnummer, status,
               geaendert_am, genehmigt_von, allgemein, verlauf, kosten,
               kosten_total, finanzierung, begruendung, antragsdatum,
               hinweis=None, pages_note="Seite 1 von 1"):
    doc = _doc(path, top=1.4 * cm)
    st = []

    hdr = Table([[
        Paragraph("<br/>".join(["<b>%s</b>" % name, fachgebiet,
                                "Personalnummer %s" % personalnummer]), P),
        Paragraph("<br/>".join(FB16), RIGHTS),
    ]], colWidths=[8.4 * cm, 8.0 * cm])
    hdr.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                             ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    st += [hdr, Spacer(1, 6)]

    meta = Table([[
        Paragraph(pages_note, PS),
        Paragraph("<br/>".join([
            "Zuletzt geändert am: %s" % geaendert_am,
            "Status: %s" % status,
            "Genehmigt von: %s" % genehmigt_von,
        ]), RIGHTS),
    ]], colWidths=[8.4 * cm, 8.0 * cm])
    meta.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                              ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    st += [meta, Spacer(1, 10)]

    st += [Paragraph("ANTRAG AUF DIENSTREISEGENEHMIGUNG", H1),
           Paragraph("vor Antritt der Reise einzureichen &#183; Reisenummer %s"
                     % reisenummer, PS),
           Spacer(1, 10)]

    st += [Paragraph("Allgemeine Daten", H2), kv_table(allgemein)]
    st += [Paragraph("Reiseverlauf", H2), kv_table(verlauf)]
    st += [Paragraph("Voraussichtliche Kosten (Schätzung)", H2),
           money_table(kosten, kosten_total)]
    st += [Spacer(1, 4), kv_table([("Finanzierung:", finanzierung)])]

    st += [Paragraph("Kurzbegründung", H2), Paragraph(begruendung, P)]
    if hinweis:
        st += [Spacer(1, 6),
               Paragraph("<b>Hinweis der/des Antragsteller:in:</b> %s" % hinweis, P)]

    sig = Table([[
        Paragraph("Datum: %s" % antragsdatum, P),
        Paragraph("Unterschrift Antragsteller:in: %s" % name, RIGHT),
    ]], colWidths=[6.0 * cm, 10.4 * cm])
    sig.setStyle(TableStyle([("LINEABOVE", (0, 0), (-1, 0), 0.5, LINE),
                             ("TOPPADDING", (0, 0), (-1, -1), 6),
                             ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    st += [Spacer(1, 18), sig, Spacer(1, 14),
           Paragraph("Erstellt durch ESS-Reisemanagement &#183; Universität Kassel",
                     PS)]
    doc.build(st)


# --------------------------------------------------------------------------- #
# 2. E-Mail print-out (Outlook-web style, as in the real corpus)
# --------------------------------------------------------------------------- #

def email_pdf(path, *, mailbox, url, subject, sender, sent, to, body, cc=None,
              folder=None, printed="16.06.26, 15:42"):
    doc = _doc(path, top=2.4 * cm, bottom=2.2 * cm)

    def deco(canv, _d):
        canv.saveState()
        canv.setFont("Helvetica", 6.5)
        canv.setFillColor(GREY)
        canv.drawString(2.2 * cm, A4[1] - 1.2 * cm, "E-Mail – %s" % mailbox)
        canv.drawRightString(A4[0] - 2.0 * cm, A4[1] - 1.2 * cm, url)
        canv.setStrokeColor(colors.HexColor("#dddddd"))
        canv.line(2.2 * cm, A4[1] - 1.35 * cm, A4[0] - 2.0 * cm, A4[1] - 1.35 * cm)
        canv.drawString(2.2 * cm, 1.3 * cm, "%d von %d" % (canv.getPageNumber(),
                                                           canv.getPageNumber()))
        canv.drawRightString(A4[0] - 2.0 * cm, 1.3 * cm, printed)
        canv.restoreState()

    st = [Paragraph(subject, H1), Spacer(1, 8), Paragraph("<b>%s</b>" % sender, P),
          Paragraph(sent, PS), Spacer(1, 4)]
    if folder:
        st += [Paragraph(folder, PS), Spacer(1, 2)]
    st += [Paragraph("An: %s" % to, PS)]
    if cc:
        st += [Paragraph("Cc: %s" % cc, PS)]
    st += [Spacer(1, 12)]
    for para in body:
        if para == "---":
            st += [Spacer(1, 6),
                   Table([[""]], colWidths=[16.4 * cm],
                         style=[("LINEABOVE", (0, 0), (-1, 0), 0.5, LINE)]),
                   Spacer(1, 6)]
        else:
            st += [Paragraph(para, P), Spacer(1, 6)]
    doc.build(st, onFirstPage=deco, onLaterPages=deco)


# --------------------------------------------------------------------------- #
# 3. Vendor invoice / booking confirmation
# --------------------------------------------------------------------------- #

def invoice_pdf(path, *, vendor, vendor_addr, recipient, refs, heading, intro=None,
                items=None, sums=None, payment=None, closing=None, notes=None):
    doc = _doc(path)
    st = []

    hdr = Table([[
        Paragraph("<br/>".join(recipient), P),
        Paragraph("<br/>".join(["<b>%s</b>" % vendor] + vendor_addr), RIGHTS),
    ]], colWidths=[9.4 * cm, 7.0 * cm])
    hdr.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                             ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    st += [hdr, Spacer(1, 14)]

    ref = Table([[Paragraph("", P),
                  Paragraph("<br/>".join("%s %s" % (k, v) for k, v in refs), RIGHTS)]],
                colWidths=[9.4 * cm, 7.0 * cm])
    ref.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    st += [ref, Spacer(1, 14), Paragraph(heading, H1)]
    if intro:
        st += [Spacer(1, 2), Paragraph(intro, PS)]
    st += [Spacer(1, 10)]

    if items:
        data = [[Paragraph("<b>%s</b>" % c, RIGHT if i else P)
                 for i, c in enumerate(["Beschreibung", "Menge", "MwSt", "netto",
                                        "brutto"])]]
        for row in items:
            data.append([Paragraph(row[0], P)] +
                        [Paragraph(c, RIGHT) for c in row[1:]])
        t = Table(data, colWidths=[7.4 * cm, 1.6 * cm, 1.9 * cm, 2.7 * cm, 2.8 * cm])
        t.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BACKGROUND", (0, 0), (-1, 0), LIGHT),
            ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.black),
            ("LINEBELOW", (0, 1), (-1, -1), 0.25, colors.HexColor("#e2e2e2")),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        st += [t, Spacer(1, 8)]

    if sums:
        data = [[Paragraph(k, RIGHT), Paragraph(v, RIGHT)] for k, v in sums]
        t = Table(data, colWidths=[13.6 * cm, 2.8 * cm])
        t.setStyle(TableStyle([
            ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("LINEABOVE", (0, -1), (-1, -1), 0.6, colors.black),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ]))
        st += [t, Spacer(1, 14)]

    if payment:
        st += [Paragraph("Zahlungsinformationen", H2), kv_table(payment), Spacer(1, 10)]
    if notes:
        for n in notes:
            st += [Paragraph(n, PS), Spacer(1, 4)]
    if closing:
        st += [Spacer(1, 8), Paragraph(closing, P), Paragraph(vendor, P)]
    doc.build(st)


# --------------------------------------------------------------------------- #
# 4. Bank statement extract (Kontoauszug / payment proof)
# --------------------------------------------------------------------------- #

def bank_receipt_pdf(path, *, bic, iban, holder, queried, date, time, rows,
                     bank_footer):
    doc = _doc(path)
    top = Table([
        [Paragraph("BIC", PS), Paragraph(bic, P), Paragraph("Datum", PS),
         Paragraph(date, P)],
        [Paragraph("IBAN", PS), Paragraph(iban, P), Paragraph("Uhrzeit", PS),
         Paragraph(time, P)],
        [Paragraph("Kontoinhaber", PS), Paragraph(holder, P),
         Paragraph("Abgefragt von", PS), Paragraph(queried, P)],
    ], colWidths=[2.6 * cm, 6.4 * cm, 2.9 * cm, 4.5 * cm])
    top.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                             ("LEFTPADDING", (0, 0), (-1, -1), 0),
                             ("TOPPADDING", (0, 0), (-1, -1), 2),
                             ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
    st = [top, Spacer(1, 22), kv_table(rows, widths=(5.2 * cm, 11.2 * cm)),
          Spacer(1, 26), Paragraph(bank_footer, PS)]
    doc.build(st)
