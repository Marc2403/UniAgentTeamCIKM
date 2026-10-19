# Synthetic Task 2 cases

36 invented cases, 12 per case type, 6 `angenommen` / 6 `abgelehnt` each, in the format of the official spot-check
sets: same folder prefixes, PDFs with a text layer, the same three retrieval corpora, `ground-truth.jsonl` for the
official evaluator. Purpose: measure how the solvers generalise beyond the 21 spot-check cases their rules were
written on.

About half the cases are **new patterns**: rules from the University of Kassel intranet pages in
`university-kassel-public-de` that no spot-check case tests. The other half are **variants** of spot-check patterns
with new surface forms. Format variations the hidden set may contain: file names without a type hint
(`Anlage_1.pdf`), several receipts or attachments in one scanned PDF, English vendor documents, foreign currency,
reverse-charge offers, and TH Sallstedt cases (other state law, decided on the documents alone).

**The labels are our reading of the corpus rules, not organiser gold.** Cases marked (?) below are the ones where
a reviewer could reasonably decide the other way; check them before tuning on them.

## Generate

```bash
pip install reportlab==4.2.5            # generator only, not a solver dependency
python evaluation/synthetic/make_synthetic.py
```

Writes `datasets/<name>/inputs/` (PDFs, retrieval corpora as hard links to `uniagent-code`), `ground-truth.jsonl`,
and `datasets/cases.jsonl` (label, pattern, rule, corpus `doc_id`, new or variant). The cases are committed; the
retrieval corpora are git-ignored, so run the generator once (with `uniagent-code` next to this repo) before a run.

## Run and score

```bash
export OPENAI_BASE_URL=https://openrouter.ai/api/v1 OPENAI_API_KEY=... OPENAI_MODEL=openai/gpt-oss-20b
export DATASETS_DIR=evaluation/synthetic/datasets
export DATASETS="synthetic-business-trip synthetic-procurement synthetic-expense-reimbursement"
evaluation/run-mvp.sh team team-solver evaluation/runs/synthetic/gpt-oss-20b bridge -- python3 /app/predict.py
```

## Cases

Sources: `DRM` Dienstreisemanagement `8f78f05e…`, `FIN` Finanzbuchhaltung und Steuern `df8a9f54…`,
`BES` Beschaffung `8521d5be…`, `RV` Rahmenverträge `aef7cd6c…`, `CAT` Nachhaltiges Catering `08143d1c…`
(1,000 EUR direct-award limit).

### `synthetic-business-trip` (University of Kassel, FB 16)

| Case | Result | Kind | Pattern | Rule (source) |
|---|---|---|---|---|
| 01 | angenommen | variant | Domestic talk, hotel 78 EUR addressed to the university, on time | regular case (DRM) |
| 02 | abgelehnt | new | Domestic hotel 139 EUR/night, no reason given | > 80 EUR only with written reason at application (DRM) |
| 03 | angenommen | new, trap | Hotel 118 EUR/night during a trade fair, necessity argued and search printout attached | same rule, satisfied (DRM) |
| 04 | abgelehnt | new | Complete trip to Beirut, Lebanon | trips to Lebanon are not approved until further notice (DRM) |
| 05 | abgelehnt | new | Invited talk; the invitation (not the form) offers an 800 EUR fee | a fee indicates a side activity, no business trip (DRM) |
| 06 | angenommen | variant, trap | Organiser pays the hotel, declared and not claimed; attachments in one scanned PDF | third-party benefits declared and offset (DRM) |
| 07 | abgelehnt | new | Domestic flight Frankfurt–Berlin, no reason, no price comparison | domestic flights only if cheaper or justified (DRM) |
| 08 | angenommen | variant | Summer school in Vienna, A1 applied 10 weeks ahead, English documents | complete foreign trip (DRM) |
| 09 | abgelehnt | new | Online conference submitted as a business trip with daily allowance | online events are no business trips (DRM) |
| 10 | angenommen | new | Day trip by private car at 0.21 EUR/km, no parking claimed | mileage without compelling reason (DRM) |
| 11 | abgelehnt | new | Funding field empty, purpose "Abstimmung", no invitation or programme | forms complete, evidence of official purpose attached (DRM) |
| 12 | angenommen | variant | Training course, private BahnCard 50 used, files named `Anlage_N.pdf` | own BahnCard must be used (DRM) |

### `synthetic-expense-reimbursement` (Wernstadt, case 10 Sallstedt)

| Case | Result | Kind | Pattern | Rule (source) |
|---|---|---|---|---|
| 01 | angenommen | variant | Hardware-store receipt with article names and purpose note | original receipt, purpose visible (FIN) |
| 02 | abgelehnt | new (?) | Private Citavi licence | Citavi is a campus licence paid centrally (RV) |
| 03 | angenommen | new, trap | Coffee, water, pastries for a meeting with 4 external guests, participant list | courtesy for guests is operating expense (FIN) |
| 04 | abgelehnt | new (?) | One person paid and claims the workshop fees of three colleagues | costs advanced for several people are not refunded to the payer alone (DRM) |
| 05 | angenommen | variant | English GBP invoice for a standard, card statement shows EUR | foreign currency proven by statement |
| 06 | abgelehnt | variant | Till receipt with article numbers only, no keyword, no university link | receipt without articles needs a keyword (FIN) |
| 07 | abgelehnt | new | Monitor bought in a web shop and claimed as expense | monitors only via the framework partner in WPS (RV) |
| 08 | angenommen | new | 250 logo pens at 0.84 EUR for the university's trade-fair stand | give-aways up to 10 EUR at fairs (FIN) |
| 09 | abgelehnt | new | Guest gift for a partner university, 64.90 EUR | guest gifts on trips up to 30 EUR (FIN) |
| 10 | angenommen | variant | Sallstedt: urgent lab chemicals, invoice to the university | documents complete (other state law) |
| 11 | abgelehnt | new | Christmas tree and decoration for the institute foyer | decoration items not reimbursable (FIN) |
| 12 | angenommen | new, trap | Three receipts from three shops in one scan, summary adds up to 98.15 EUR | original receipts with articles and purpose (FIN) |

### `synthetic-procurement` (Wernstadt, cases 10–11 Sallstedt)

| Case | Result | Kind | Pattern | Rule (source) |
|---|---|---|---|---|
| 01 | angenommen | variant | Three offers (one in English), cheapest chosen, form and award note agree | three offers (BES) |
| 02 | abgelehnt | new | Award to the second-cheapest offer, no reason | award to the most economical offer |
| 03 | angenommen | new, trap | Not the cheapest: the cheapest reaches only -40 °C, -80 °C is required and documented | most economical suitable offer |
| 04 | abgelehnt | new (?) | Two 940 EUR direct awards for identical printers, explicitly to stay below the limit | direct award below 1,000 EUR (CAT); splitting to avoid it |
| 05 | angenommen | new, trap (?) | Direct award at 948 EUR net / 1,128.12 EUR gross | limit applies to the net order value (CAT) |
| 06 | abgelehnt | new | Microsoft Office licences from a reseller | framework contract for Microsoft software (RV) |
| 07 | abgelehnt | new | Office swivel chairs with three offers from furniture dealers | framework contract for office swivel chairs (RV) |
| 08 | angenommen | new | Bottled gases from the WPS framework catalogue, 2,142.96 EUR net, no offers | framework catalogue bottled gases (RV) |
| 09 | abgelehnt | new | Budget holder did not sign; e-mail says the professor is unreachable | orders must be commissioned by the budget holder (BES) |
| 10 | angenommen | variant | Sallstedt: three offers in a thread, invoice equals the offer, signed as correct | documents complete |
| 11 | abgelehnt | new | Sallstedt: invoice adds an unordered 285 EUR installation flat rate | invoices must match the ordered offer |
| 12 | angenommen | new, trap | Cheapest offer is a Dutch quotation without German VAT (reverse charge), net comparison | award to the cheapest offer (net) |

(?) Reasons for doubt: Citavi (02) and several payers (04) apply rules from other contexts (campus licence page,
business-trip page) to expense claims; splitting (04) is general procurement law, not stated on the Kassel pages;
whether the 1,000 EUR limit is net (05) is not stated on the Kassel pages, net is the procurement-law convention.

## Set B: Rajesh's cases in this format

`convert_rajesh.py` renders the 18 plain-text cases of `rajesh-uniagent-solver/synthetic/synthetic/synthetic_cases`
(text files with a `.pdf` extension that `pdftotext` cannot read) as real PDFs, text unchanged, into
`datasets/rajesh-{business-trip,expense-reimbursement,procurement}`. Labels, Rajesh's category and reason are in
`datasets/cases-rajesh.jsonl`. Marked (?): `dienstreiseantrag-s01-clean-trip` (form without costs or means of
transport), `dienstreiseantrag-k01-private-weekend` (a two-day private extension is allowed and claims nothing),
`auslagenerstattung-r05-hotel-over-cap` (hotel bill without trip context claimed as an expense).

## Set C (coverage) and holdout H

`make_coverage.py` writes 83 coverage cases and 20 holdout cases into `datasets/coverage-*` and `datasets/holdout-*`,
with a decision-trail document per case outside `inputs/` (C1 to C5 and H: the e-mail of the approving office that
explains the label). Every case records `family`, `rule` (IDs of [`RULES.md`](RULES.md)), `source_doc_id`,
`doc_types` and `label` in `datasets/cases-{coverage,holdout}.jsonl`. Principles, different from A and B:

| Family | Principle | Cases |
|---|---|---|
| C1 | Layout functions of the organisers' generator (`orga_layouts.py`, copied from `make_examples.py`), decision trail per case | 29 |
| C2 | Counterfactual pairs on spot-check cases (trip-02, trip-05, exp-02, exp-04, exp-07, proc-02, proc-03, proc-04): same structure, other names and amounts, exactly one fact changed | 16 |
| C3 | File complexity: contradictions between documents, query and answer threads, credit notes, down payment plus final invoice, several defects | 16 |
| C4 | Look suspicious, are correct: pseudonymisation traces, values exactly on a threshold, gross above / net below 1,000 EUR, framework cart without offers, no framework contract for envelopes, Sallstedt | 15 |
| C5 | Free text (e-mails, reasons) written by `mistralai/mistral-small-3.2-24b-instruct`, not by the solver's model; the label comes from the case description, and the generator checks that every required fact is in the text (`--generate-c5`, cached in `datasets/c5-texts.json`) | 7 |

47 of the 83 cases are `angenommen`. The holdout H has 20 cases (10 `angenommen`): a second pair for ten rules of C,
with another family and surface. It is not looked at during development and is scored once, as a sum.

```bash
python evaluation/synthetic/convert_rajesh.py
python evaluation/synthetic/make_coverage.py            # --generate-c5 re-asks the writer model (OPENROUTER_API_KEY)
python evaluation/compare_runs.py --baseline <run> <run> --candidate <run> <run> --sets S A B C
```

### `coverage-business-trip` (University of Kassel, FB 16)

| Case | Family | Result | Rule | Pattern | Source |
|---|---|---|---|---|---|
| c101 | C1 | abgelehnt | T05 | Workshop in Kyjiw (Ukraine), sonst vollständig | DRM |
| c102 | C1 | angenommen | T05 | Tagung in Amman (Jordanien), Land nicht auf der Ausschlussliste, vollständig | DRM |
| c103 | C1 | abgelehnt | T06 | Inland, Hotel 112 €/Nacht ohne Begründung | DRM |
| c104 | C1 | angenommen | T06 | Hotel 109 €/Nacht in München zur Messezeit, Notwendigkeit im Antrag begründet, Recherche beigefügt | VV-HRKG |
| c105 | C1 | abgelehnt | T10 | Eingeladener Vortrag, Einladung nennt Honorar 500 €, Reisekosten beantragt | DRM |
| c106 | C1 | angenommen | T10 | Eingeladener Vortrag an einer Universität, ausdrücklich ohne Honorar | DRM |
| c107 | C1 | abgelehnt | T11 | Ausschließlich virtuelle Tagung als Dienstreise mit Tagegeld beantragt | DRM |
| c108 | C1 | angenommen | T11 | Hybride Tagung, Teilnahme vor Ort in Bremen mit Vortrag | DRM |
| c109 | C1 | abgelehnt | T13 | Flugreise nach Lissabon ohne Preisvergleich | DRM |
| c110 | C1 | angenommen | T13 | Flugreise nach Porto mit Preisvergleich des Reisebüros | DRM |
| c111 | C1 | abgelehnt | T14 | Inlandsflug Frankfurt–Hamburg teurer als die Bahn, keine dienstlichen Gründe | DRM |
| c112 | C1 | angenommen | T14 | Inlandsflug Paderborn–München günstiger als die Bahn, Vergleich beigefügt | DRM |
| c113 | C1 | abgelehnt | T18 | Conference Dinner 85 € in der Kostenaufstellung beantragt | DRM |
| c201 | C2 | angenommen | T01 | Paar zu trip-02: Konferenzreise nach Gent, Antrag am 30.08.2027 | DRM |
| c202 | C2 | abgelehnt | T01 | Paar zu trip-02: Konferenzreise nach Gent, Antrag am 12.11.2027 | DRM |
| c203 | C2 | abgelehnt | T09 | Paar zu trip-05: Reisestipendium für Flug und Unterkunft nicht angerechnet | DRM |
| c204 | C2 | angenommen | T09 | Paar zu trip-05: Reisestipendium für Flug und Unterkunft angerechnet | DRM |
| c301 | C3 | abgelehnt | T02 | Formular 3 Nächte und Reisebeginn 14.03., Hotelbuchung 4 Nächte ab 13.03. | DRM |
| c302 | C3 | angenommen | T12 | Rückfrage der Reisekostenstelle nach Programm; Antwort mit Nachweis | DRM |
| c303 | C3 | abgelehnt | T12 | Rückfrage der Reisekostenstelle nach Programm; Antwort ohne Nachweis | DRM |
| c304 | C3 | angenommen | T15 | Konferenz in Kyoto plus 8 Arbeitstage Urlaub, private Kosten getrennt | DRM |
| c305 | C3 | abgelehnt | T15 | Konferenz in Kyoto plus 8 Arbeitstage Urlaub, private Kosten nicht getrennt | DRM |
| c401 | C4 | angenommen | G01 | Regulärer Antrag mit starken Pseudonymisierungsspuren (fremde PLZ, seltsame Nummer, Wort in anderer Schrift, geschwärzte Unterschrift) | DRM |
| c402 | C4 | angenommen | T09 | Veranstalter übernimmt das Hotel, im Antrag mitgeteilt und nicht beantragt | DRM |
| c403 | C4 | angenommen | T15 | Privataufenthalt von genau 5 Arbeitstagen nach der Konferenz, Rückflug ohne Mehrkosten | DRM |
| c404 | C4 | angenommen | T18 | Programm mit Conference Dinner und inkludiertem Mittagessen, Dinner nicht gebucht und nicht beantragt | DRM |
| c405 | C4 | angenommen | T06 | Inland, Hotel genau 80,00 €/Nacht | DRM |
| c501 | C5 | abgelehnt | T10 | Vortrag, Honorar 600 € nur in der frei formulierten Veranstalter-E-Mail | DRM |
| c507 | C5 | angenommen | T01 | Regulärer Antrag, Annahme-E-Mail und Begründung frei formuliert | DRM |

### `coverage-expense-reimbursement` (Wernstadt)

| Case | Family | Result | Rule | Pattern | Source |
|---|---|---|---|---|---|
| c114 | C1 | abgelehnt | E04 | Oszilloskop für 1.249 € privat im Webshop gekauft und als Auslage eingereicht | FIN |
| c115 | C1 | angenommen | E04 | Batterien und Kabeltrommel für eine Feldmessung am Folgetag im Baumarkt gekauft, Zweck vermerkt | FIN |
| c116 | C1 | angenommen | E09 | Gebühr einer reinen Online-Tagung als privat verauslagte Kosten eingereicht | DRM |
| c117 | C1 | abgelehnt | E10 | Notebook im Elektronikmarkt privat gekauft, Rechnung an den Lehrstuhl | RV |
| c118 | C1 | angenommen | E10 | Netzwerk-Kabeltester für das Labor, kein Rahmenvertragsprodukt | RV |
| c119 | C1 | abgelehnt | E11 | Adventsdekoration für das Institutsfoyer | FIN |
| c120 | C1 | abgelehnt | E12 | Gastgeschenk 48,80 € bei einer Dienstreise nach Krakau | FIN |
| c121 | C1 | angenommen | E12 | Gastgeschenk 27,50 € bei einer Dienstreise nach Lyon | FIN |
| c122 | C1 | abgelehnt | E13 | 120 USB-Sticks à 12,90 € als Give-aways für den Messestand | FIN |
| c123 | C1 | angenommen | E13 | 200 Notizblöcke à 1,95 € als Give-aways für die Messe | FIN |
| c124 | C1 | abgelehnt | E14 | Catering der Weihnachtsfeier des Fachgebiets | FIN |
| c205 | C2 | angenommen | E01 | Paar zu exp-02: Kassenbon nur mit Artikelnummern, Stichwort vermerkt | FIN |
| c206 | C2 | abgelehnt | E01 | Paar zu exp-02: Kassenbon nur mit Artikelnummern, ohne Stichwort | FIN |
| c207 | C2 | abgelehnt | E02 | Paar zu exp-04: Laborbedarf, nur Pro-forma-Rechnung | FIN |
| c208 | C2 | angenommen | E02 | Paar zu exp-04: Laborbedarf, endgültige Rechnung | FIN |
| c209 | C2 | abgelehnt | E07 | Paar zu exp-07: Kaffee, Tee, Gebäck, Wasser für die Teeküche | FIN |
| c210 | C2 | angenommen | E07 | Paar zu exp-07: Kaffee, Tee, Gebäck, Wasser für externe Gäste mit Teilnehmerliste | FIN |
| c306 | C3 | abgelehnt | E06 | Rechnung 186,40 € und Gutschrift 46,60 € für einen Rückläufer, geltend gemacht 186,40 € | FIN |
| c307 | C3 | angenommen | E06 | Rechnung 186,40 € und Gutschrift 46,60 € für einen Rückläufer, geltend gemacht 139,80 € | FIN |
| c308 | C3 | angenommen | E02 | Rückfrage der Finanzbuchhaltung zur Pro-forma-Rechnung, endgültige Rechnung nachgereicht | FIN |
| c309 | C3 | abgelehnt | E15 | Arbeitsessen mit 2 Industriepartnern, ohne Anlass und Teilnehmerliste | FIN |
| c310 | C3 | angenommen | E15 | Arbeitsessen mit 2 Industriepartnern, Nachweise vollständig | FIN |
| c406 | C4 | angenommen | E03 | Englische Rechnung an Person c/o Universität, abweichende E-Mail-Adresse, ungültige IBAN | FIN |
| c407 | C4 | angenommen | E08 | Software-Lizenz in USD, Kreditkartenabrechnung belegt den Euro-Betrag | FIN |
| c408 | C4 | angenommen | E12 | Gastgeschenk genau 30,00 € bei einer Dienstreise nach Graz | FIN |
| c409 | C4 | angenommen | G01 | Laborbedarf, eine Position trägt statt der Produktbezeichnung einen Personennamen (Pseudonymisierung), Zweck vermerkt | FIN |
| c502 | C5 | abgelehnt | E10 | Notebook für 899 € privat gekauft, frei formulierte Begründung | RV |
| c503 | C5 | abgelehnt | E12 | Gastgeschenk 52,40 € für Gastgeber in Tallinn, frei formuliert | FIN |
| c505 | C5 | angenommen | E09 | Gebühr eines reinen Online-Seminars, frei formuliert | DRM |
| c506 | C5 | angenommen | E07 | Kaffee, Tee, Wasser, Gebäck für eine Delegation aus Tartu, frei formuliert | FIN |

### `coverage-procurement` (Wernstadt, case c415 Sallstedt)

| Case | Family | Result | Rule | Pattern | Source |
|---|---|---|---|---|---|
| c125 | C1 | abgelehnt | P02 | 40 Kartons Kopierpapier beim örtlichen Händler mit drei Angeboten statt über WPS | RV |
| c126 | C1 | abgelehnt | P03 | Antrag ohne Unterschrift der Kostenstellenbevollmächtigten, 'wird nachgereicht' | BES |
| c127 | C1 | angenommen | P03 | Beauftragung des Kostenstellenbevollmächtigten per separater E-Mail statt Unterschrift | BES |
| c128 | C1 | abgelehnt | P08 | Argon-Flaschen beim regionalen Gashändler mit drei Angeboten statt aus dem WPS-Katalog Flaschengase | RV |
| c129 | C1 | angenommen | P08 | Stickstoff-Flaschen aus dem WPS-Katalog Rahmenvertrag Flaschengase, keine Vergleichsangebote | RV |
| c211 | C2 | angenommen | P01 | Paar zu proc-02: Direktauftrag mit einem Angebot, 2 Messverstärker | CAT |
| c212 | C2 | abgelehnt | P01 | Paar zu proc-02: Direktauftrag mit einem Angebot, 5 Messverstärker | CAT |
| c213 | C2 | abgelehnt | P02 | Paar zu proc-03: Sammelbestellung aus Webshops, Position 9 zwei Monitore | RV |
| c214 | C2 | angenommen | P02 | Paar zu proc-03: Sammelbestellung aus Webshops, Position 9 zwei Labortischleuchten | RV |
| c215 | C2 | abgelehnt | P04 | Paar zu proc-04: drei Angebote, Summe netto im Antrag weicht von den Positionen ab | BES |
| c216 | C2 | angenommen | P04 | Paar zu proc-04: drei Angebote, Summe netto im Antrag stimmt | BES |
| c311 | C3 | angenommen | P07 | Anzahlung 30 % und Schlussrechnung zum beauftragten Angebot | BES |
| c312 | C3 | abgelehnt | P07 | Anzahlung 30 % und Schlussrechnung zum beauftragten Angebot, Schlussrechnung mit Expresszuschlag | BES |
| c313 | C3 | angenommen | P01 | Rückfrage Einkauf: nur zwei Angebote bei 1.640 € netto; drittes Angebot nachgereicht | BES |
| c314 | C3 | abgelehnt | P01 | Rückfrage Einkauf: nur zwei Angebote bei 1.640 € netto; drittes Angebot nicht nachgereicht | BES |
| c315 | C3 | abgelehnt | P06+P03 | Zuschlag an das zweitgünstigste Angebot ohne Begründung, Antrag nicht von der Kostenstellenbevollmächtigten unterschrieben | BES |
| c316 | C3 | angenommen | P06 | Zweitgünstigstes Angebot gewählt, weil das günstigste erst nach dem Praktikum liefern kann; im Vergabevermerk begründet | BES |
| c410 | C4 | angenommen | P01 | Direktvergabe mit einem Angebot: 990,00 € netto, 1.178,10 € brutto | CAT |
| c411 | C4 | angenommen | P02 | Notebooks und Monitore für 4.812 € netto aus dem WPS-Katalog, keine Vergleichsangebote | RV |
| c412 | C4 | angenommen | P09 | Briefhüllen und Versandtaschen für 1.180 € netto mit drei Angeboten (derzeit kein Rahmenvertrag) | RV |
| c413 | C4 | angenommen | P03 | Bestellung per E-Mail, die Kostenstellenbevollmächtigte antwortet im Verlauf mit 'beauftragt' | BES |
| c414 | C4 | angenommen | P02 | Beamer und Leinwand für den Seminarraum mit drei Angeboten (kein Rahmenvertragsprodukt) | RV |
| c415 | C4 | angenommen | G02 | TH Sallstedt: 1.460 € netto mit zwei Angeboten, die interne Wertgrenze der TH steht in der Korrespondenz | BES |
| c504 | C5 | abgelehnt | P03 | Bestellung durch Doktorand, Kostenstellenbevollmächtigte nicht erreichbar | BES |
