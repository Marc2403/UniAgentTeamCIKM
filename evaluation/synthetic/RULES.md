# Regelkatalog Task 2 und Abdeckung

Eine Zeile pro Regel. Quellen (Korpus `university-kassel-public-de`, sofern nicht anders angegeben):
`DRM` Dienstreisemanagement `8f78f05e-61f4-4f5f-ba79-35b18e2c4a0f`, `FIN` Finanzbuchhaltung und Steuern
`df8a9f54-11b5-4f4f-b15e-146d3bca69d3`, `BES` Beschaffung `8521d5be-7a95-4cad-aaf4-3b2a76860857`, `RV` Rahmenverträge
`aef7cd6c-7609-4ac8-84ec-228bc79e5a4e`, `CAT` Nachhaltiges Catering `08143d1c-7e2f-4f9c-b6e0-42969f36852f`;
`hessian-law-de`: `HRKG` (§ 2 `jlr-NNLHE0000518BNN00000000004`, § 4 `jlr-NNLHE0000518BNN00000000008`, § 8
`jlr-NNLHE0000518BNN00000000016`) und `VV-HRKG` `VVHE-VVHE000013868`.

Spalten: **prüfbar als** Python-Check (Fakten sicher extrahierbar) oder LLM-Urteil. **im MVP** Check-ID (Stand
`13618cf`), *nur YAML* (Regeltext in `solver/knowledge/rules_*.yaml`, kein Check) oder *fehlt*. **Testfälle**
`Set:Fall` getrennt nach Ablehnung / Annahme; S Spot-Checks, A `synthetic-*`, B `rajesh-*`, C `coverage-*`
(H wird hier nicht aufgeführt). **Relevanz** hoch = kommt in Spot-Checks oder Decision-Trails vor oder steht auf der
Kassel-Seite als Pflicht, Frist oder häufiger Fehler. (?) = Quelle unklar oder widersprüchlich; solche Regeln
entscheiden im Gate nichts.

Kurzformen der Fälle: `trip-NN` = `dienstreiseantrag-NN`, `exp-NN` = `auslagenerstattung-NN`,
`proc-NN` = `beschaffungsantrag-NN`.

## Dienstreiseantrag

| Regel-ID | Typ | Wortlaut kurz | Quelle | prüfbar als | im MVP | Testfälle reject / accept | Relevanz |
|---|---|---|---|---|---|---|---|
| T01 | Frist | Antrag vor Reiseantritt; nachträglich nur im Ausnahmeverfahren | DRM; VV-HRKG zu § 2 Nr. 1.3; HRKG § 2 | Python | `TRIP_SUBMITTED_BEFORE_START` | S:trip-01, B:trip-r01, B:trip-r03, C:trip-c202 / S:trip-02, A:trip-01, C:trip-c201, C:trip-c507 | hoch |
| T02 | Form | Reiseverlauf widerspruchsfrei (Beginn ≤ Dienstgeschäft ≤ Rückkehr) | allgemein (S:trip-03 Trail) | Python | `TRIP_DATES_CONSISTENT` | S:trip-03, B:trip-r02, B:trip-r04, C:trip-c301 / S:trip-02 | hoch |
| T03 | Form | Hin- und Rückreise und alle Kosten beziffert, Gesamtsumme steht fest | allgemein (S:trip-03 Trail) | Python | `TRIP_COSTS_COMPLETE` | S:trip-03 / S:trip-02 | hoch |
| T04 | Pflichtfeld | Feld „Reise ins Ausland“ ausgefüllt; A1-Bescheinigung für EU/EWR/CH beantragen (8 Wochen empfohlen) | DRM | Python | `TRIP_FOREIGN_TRAVEL` | S:trip-03 / S:trip-02, A:trip-08 | hoch |
| T05 | Ausschluss | Keine Genehmigung für Russland, Ukraine, Belarus, Moldau (Gebiete an der Ukraine), Niger, Iran, Israel, Palästinensische Gebiete, Libanon | DRM | Python (Land) | fehlt | A:trip-04, C:trip-c101 / C:trip-c102 | hoch |
| T06 | Schwelle | Hotel Inland ≤ 80,00 €/Nacht; darüber nur mit schriftlicher Begründung bei Antragstellung (Messe, Ballungsraum, Unvorhersehbarkeit) | DRM; VV-HRKG zu § 8 Nr. 2.1 | Python + LLM (Begründung) | `TRIP_HOTEL_RATE` (soft) | A:trip-02, C:trip-c103 / A:trip-01, A:trip-03, S:trip-02, C:trip-c104, C:trip-c405 | hoch |
| T07 | Schwelle | Hotel Ausland bis ARV-Satz; darüber begründen | DRM | LLM (ARV nicht im Korpus) | `TRIP_HOTEL_RATE` (unclear) | – / S:trip-04 | mittel |
| T08 | Beleg | Hotelrechnung muss die Universität als Adressat nennen (bei der Abrechnung) | DRM | LLM | nur YAML (in `TRIP_HOTEL_RATE`) | – / A:trip-01 | mittel |
| T09 | Finanzierung | Leistungen Dritter vor Reiseantritt mitteilen und anrechnen; keine Doppelfinanzierung | DRM; HRKG § 4 Abs. 3 | Python | `TRIP_THIRD_PARTY_FUNDING` | S:trip-05, C:trip-c203 / A:trip-06, C:trip-c204, C:trip-c402 | hoch |
| T10 | Ausschluss | Honorar (z. B. für Vortrag) deutet auf Nebentätigkeit; Dienstreisegenehmigung grundsätzlich nicht möglich | DRM | LLM | fehlt | A:trip-05, C:trip-c105, C:trip-c501 / C:trip-c106 | hoch |
| T11 | Ausschluss | Online-Konferenzen sind keine Dienstreisen; Gebühr über „Privat verauslagte Kosten“ | DRM | LLM | nur YAML (nur Auslagen) | A:trip-09, C:trip-c107 / C:trip-c108 | hoch |
| T12 | Form | Anträge vollständig ausfüllen; Einladung/Programm beifügen, aus denen dienstliches Interesse, Ort und Dauer hervorgehen | DRM | LLM | fehlt | A:trip-11, C:trip-c303 / C:trip-c302 | hoch |
| T13 | Beleg | Bei Flugreisen Preisvergleich beifügen (auch Rückflug direkt nach Dienstgeschäft) | DRM | LLM | nur YAML | C:trip-c109 / S:trip-04, A:trip-04, C:trip-c110 | hoch |
| T14 | Schwelle | Inlandsflug nur, wenn günstiger als Bahn oder besondere dienstliche Gründe; in Anlage darlegen; nur Economy | DRM | LLM | fehlt | A:trip-07, C:trip-c111 / C:trip-c112 | hoch |
| T15 | Kosten | Privataufenthalt ≤ 5 Arbeitstage: Abrechnung wie reine Dienstreise; > 5: nur dienstlich notwendige Kosten; keine Mehrkosten | DRM; VV-HRKG zu § 14 | Python + LLM | `TRIP_PRIVATE_STAY` (soft) | C:trip-c305 / S:trip-04, C:trip-c304, C:trip-c403 | hoch |
| T16 | Kosten | Private BahnCard 25/50 ist für Dienstreisen einzusetzen | DRM; VV-HRKG zu § 5 Nr. 2.1 | LLM | fehlt | – / A:trip-12 | mittel |
| T17 | Schwelle | Privat-Kfz 0,21 €/km; 0,35 €/km und Parkgebühren nur mit triftigem Grund und vorheriger Genehmigung | DRM; HRKG § 6 | Python (Satz) + LLM | fehlt | – / A:trip-10 | mittel |
| T18 | Kosten | Verpflegung ist mit dem Tagegeld abgegolten; Begleit-/Abendprogramm (Conference Dinner) nicht erstattungsfähig | DRM; S:trip-02 Trail | LLM | fehlt | C:trip-c113 / S:trip-02, C:trip-c404 | mittel |
| T19 | Kosten | Taxi/Mietwagen nur mit triftigem Grund, sonst Kosten des regelmäßigen Verkehrsmittels | DRM | LLM | fehlt | – / – | niedrig |
| T20 | Kosten | CO2-Kompensation, Auslandskrankenversicherung, Impfkosten nicht erstattungsfähig | DRM | LLM | fehlt | – / – | niedrig |
| T21 | Ausnahme | Professor:innen: Inlandsdienstreisen bis 7 Tage qua Amt genehmigt (Präsidiumsbeschluss 656) | DRM | LLM | fehlt | – / – | niedrig (?) |

## Auslagenerstattung

| Regel-ID | Typ | Wortlaut kurz | Quelle | prüfbar als | im MVP | Testfälle reject / accept | Relevanz |
|---|---|---|---|---|---|---|---|
| E01 | Beleg | Erstattungsformular mit Originalquittung; ohne Artikel ein Stichwort zum Zweck | FIN | Python | `EXP_REAL_INVOICE` | A:exp-06, C:exp-c206 / S:exp-02, A:exp-01, A:exp-12, C:exp-c205 | hoch |
| E02 | Beleg | Pro-forma-Rechnung, Angebot oder Warenkorb ist kein Beleg | FIN; S:exp-04 | Python | `EXP_REAL_INVOICE` | S:exp-04, B:exp-r01, C:exp-c207 / C:exp-c208, C:exp-c308 | hoch |
| E03 | Bezug | Dienstlicher Bezug erkennbar (Rechnung an Universität/Einrichtung oder vermerkter dienstlicher Zweck) | FIN | Python | `EXP_SERVICE_REFERENCE` | S:exp-03, B:exp-r02 / S:exp-01, C:exp-c406 | hoch |
| E04 | Weg | Beschaffungen über SAP; privat verauslagt nur kleinere, zeitlich dringende Anschaffungen | FIN | LLM | nur YAML (in `EXP_SERVICE_REFERENCE`) | C:exp-c114 / S:exp-02, C:exp-c115 | hoch |
| E05 | Doppelt | Dieselbe Bestellung nur einmal erstatten | allgemein; S:exp-06 | Python | `EXP_DUPLICATE` | S:exp-06, B:exp-r03 / B:exp-r04 | hoch |
| E06 | Kosten | Gutschriften/Stornos abziehen; nur Saldo erstattungsfähig | allgemein; S:exp-05 | Python | `EXP_CREDIT_NOTES` | C:exp-c306 / S:exp-05, C:exp-c307 | hoch |
| E07 | Bewirtung | Bewirtung nur mit externen Gästen; Kaffee/Tee/Wasser/Gebäck nur als Geste gegenüber Gästen | FIN | Python + LLM | `EXP_HOSPITALITY` | S:exp-07, C:exp-c209 / A:exp-03, C:exp-c210, C:exp-c506 | hoch |
| E08 | Beleg | Fremdwährung: Konto-/Kartenauszug belegt den Euro-Betrag | allgemein; S:exp-08 | Python | `EXP_FOREIGN_CURRENCY` (soft) | – / S:exp-08, A:exp-05, C:exp-c407 | hoch |
| E09 | Weg | Online-Konferenzgebühren sind als privat verauslagte Kosten einzureichen (kein Dienstreiseantrag) | DRM | LLM | nur YAML | – / S:exp-08, C:exp-c116, C:exp-c505 | hoch |
| E10 | Ausschluss | Rahmenvertragsprodukte (PCs, Notebooks, Monitore, Büromaterial, Bürostühle, Microsoft …) nur beim Rahmenvertragspartner, nicht privat kaufen | RV; BES | Python (Produktgruppe) | fehlt (nur `PROC_FRAMEWORK_CONTRACT`) | A:exp-07, C:exp-c117, C:exp-c502 / C:exp-c118 | hoch |
| E11 | Ausschluss | Schmuck- und Dekorationsartikel (z. B. Weihnachtsbaum) nicht erstattungsfähig | FIN | LLM | fehlt | A:exp-11, C:exp-c119 / – | mittel |
| E12 | Schwelle | Gastgeschenke bei Dienstreisen bis 30,00 €; Geschenke an eigene Bedienstete nie | FIN | Python (Betrag) + LLM | fehlt | A:exp-09, C:exp-c120, C:exp-c503 / C:exp-c121, C:exp-c408 | mittel |
| E13 | Schwelle | Give-aways auf Messen/Kongressen bis 10,00 € (je Stück) | FIN | Python (Betrag) + LLM | fehlt | C:exp-c122 / A:exp-08, C:exp-c123 | mittel |
| E14 | Ausschluss | Keine Bewirtung bei geselligen Anlässen (Weihnachts-, Geburtstagsfeier, Verabschiedung), Arbeitsessen, Trinkgeld, Pfand | FIN | LLM | fehlt (teilw. `EXP_HOSPITALITY`) | C:exp-c124 / – | mittel |
| E15 | Nachweis | Bewirtung: Anlass, Teilnehmerliste (Gäste gekennzeichnet), Beleg an Universität | FIN | LLM | fehlt | C:exp-c309 / A:exp-03, C:exp-c310 | mittel |
| E16 | Schwelle | Bewirtung höchstens 60 € pro Person und Veranstaltungstag | FIN | Python | fehlt | – / – | niedrig |
| E17 | Ausschluss | Für mehrere Personen verauslagte Kosten nicht an die verauslagende Person allein | DRM | LLM | fehlt | (?) A:exp-04 / – | mittel (?) |
| E18 | Ausschluss | Campuslizenzen (Sophos, Citavi) werden zentral getragen | RV | LLM | fehlt | (?) A:exp-02 / – | mittel (?) |
| E19 | Schwelle | Hotel > 80 € ohne Begründung (als Auslage eingereicht) | DRM; VV-HRKG zu § 8 Nr. 2.1 | Python + LLM | fehlt | (?) B:exp-r05 / B:exp-s02, B:exp-s03, B:exp-e01 | mittel (?) |
| E20 | Ausschluss | Impf-, Arzt-, Auslandskrankenversicherungskosten nicht erstattungsfähig | DRM | LLM | fehlt | – / – | niedrig |

## Beschaffungsantrag

| Regel-ID | Typ | Wortlaut kurz | Quelle | prüfbar als | im MVP | Testfälle reject / accept | Relevanz |
|---|---|---|---|---|---|---|---|
| P01 | Schwelle | Ab 1.000 € Auftragswert drei Angebote; unter 1.000 € Direktvergabe mit einem Angebot | BES; CAT | Python | `PROC_COMPARISON_OFFERS` | S:proc-06, B:proc-r01, C:proc-c212, C:proc-c314 / S:proc-01, S:proc-02, B:proc-e01, C:proc-c211, C:proc-c313, C:proc-c410 | hoch |
| P02 | Ausschluss | Rahmenvertragsprodukte ausschließlich beim Rahmenvertragspartner (WPS), unabhängig vom Betrag; dafür keine Vergleichsangebote | RV; BES | Python | `PROC_FRAMEWORK_CONTRACT` | S:proc-03, A:proc-06, A:proc-07, C:proc-c125, C:proc-c213 / S:proc-05, A:proc-08, C:proc-c214, C:proc-c411, C:proc-c414 | hoch |
| P03 | Freigabe | Bestellung von der/dem Kostenstellenbevollmächtigten beauftragt | BES | Python + LLM | nur YAML | A:proc-09, C:proc-c126, C:proc-c315, C:proc-c504 / S:proc-01, C:proc-c127, C:proc-c413 | hoch |
| P04 | Rechnung | Summe im Antrag = Summe der Positionen | allgemein; S:proc-04 | Python | `PROC_TOTAL_MATCHES_ITEMS` | S:proc-04, C:proc-c215 / S:proc-01, C:proc-c216 | hoch |
| P05 | Rechnung | Vergabevermerk gibt Angebotsbeträge richtig wieder | allgemein; S:proc-07 | Python | `PROC_AWARD_MATCHES_OFFERS` | S:proc-07 / S:proc-01 | hoch |
| P06 | Vergabe | Zuschlag an das wirtschaftlichste (meist günstigste) geeignete Angebot; Abweichung begründen | allgemein; S:proc-07 | Python + LLM | `PROC_CHEAPEST_OFFER` (soft) | A:proc-02, C:proc-c315 / A:proc-03, A:proc-12, C:proc-c316 | hoch |
| P07 | Rechnung | Rechnungen (auch Teilrechnungen) entsprechen dem beauftragten Angebot | allgemein; S:proc-08 | Python | `PROC_INVOICES_MATCH_OFFER` (soft) | A:proc-11, C:proc-c312 / S:proc-08, C:proc-c311 | hoch |
| P08 | Rahmenvertrag | Flaschengase (außer Helium), Helium, Flüssigstickstoff: Rahmenvertrag Linde über WPS | RV | Python (Produktgruppe) | fehlt (Regex ohne Gase) | C:proc-c128 / A:proc-08, C:proc-c129 | mittel |
| P09 | Rahmenvertrag | Briefhüllen/Versandtaschen: derzeit **kein** Rahmenvertrag | RV | LLM | fehlt | – / C:proc-c412 | mittel |
| P10 | Vergabe | Auftragsteilung zur Umgehung der 1.000-€-Grenze unzulässig | Vergaberecht (nicht auf den Kassel-Seiten) | LLM | fehlt | (?) A:proc-04 / – | mittel (?) |
| P11 | Kategorie | GWG 250–800 € netto, Anlage ab 800,01 € Nettoeinzelpreis; Zuordnung bei Bestellung | BES | Python | fehlt | – / – | niedrig |
| P12 | Vergabe | Drittmittelprojekte: andere Wertgrenzen laut Bewilligungsbescheid | CAT | LLM | fehlt | – / – | niedrig (?) |
| P13 | Rahmenvertrag | Catering für eigene Veranstaltungen über Rahmenvertrag nachhaltiges Catering; konventionelles Catering ohne Rahmenvertrag (drei Angebote ab 1.000 €) | CAT; RV | LLM | fehlt | – / – | niedrig (?) |

## Übergreifend

| Regel-ID | Typ | Wortlaut kurz | Quelle | prüfbar als | im MVP | Testfälle reject / accept | Relevanz |
|---|---|---|---|---|---|---|---|
| G01 | Pseudonymisierung | Spuren (fremde PLZ, ungültige IBAN, Schwärzungen, andere Schrift, Name statt Produkt) entscheiden nie | Dataset-READMEs | – (Prompt) | Prompt-Grundsatz 3 | – / C:trip-c401, C:exp-c409 | hoch |
| G02 | Geltung | TH Sallstedt: anderes Landesrecht, keine Kassel-Schwellen | Dataset-READMEs | Python (Scope) | `rules_scope` | A:proc-11 / A:exp-10, A:proc-10, C:proc-c415 | hoch |
| G03 | Status | „Genehmigt von: ---“, Status „eingereicht“, offene Zahlung sind im Antragsstadium normal | S-Fälle | – (Prompt) | Prompt-Grundsatz 4 | – / S:trip-02 | hoch |

## Grenzfälle

**Dienstreise**
- Hotel genau 80,00 €/Nacht (annehmen) gegen 80,01 € ohne Begründung (ablehnen); Begründung erst in der Hotelbuchung
  statt im Antrag (Rajesh B:exp-s02); Ausland nach ARV (Satz nicht im Korpus, nur LLM-Urteil).
- Privataufenthalt genau 5 Arbeitstage (wie reine Dienstreise) gegen 6 (nur notwendige Kosten).
- Antragsdatum gleich Reisetag (?), einen Tag nach Abreise (ablehnen).
- A1: Vorlauf unter 8 Wochen ist eine Empfehlung, kein Ablehnungsgrund.
- Inlandsflug günstiger als die Bahn (annehmen) gegen teurer ohne Gründe (ablehnen).
- Kfz 0,21 €/km ohne Begründung (annehmen) gegen 0,35 €/km ohne vorherige Genehmigung.

**Auslagen**
- Gastgeschenk genau 30,00 € (annehmen) gegen 30,01 €; Brutto ist der Wert des Geschenks.
- Give-away genau 10,00 € je Stück; Stückpreis netto unter, brutto über 10 € (?).
- Fremdwährung mit und ohne Kartenabrechnung (ohne: soft `unclear`, kein Ablehnungsgrund allein).
- Bewirtung genau 60 € pro Person und Tag.

**Beschaffung**
- Auftragswert 999,99 € netto (Direktvergabe) gegen genau 1.000,00 € netto (nicht „unter“ 1.000: drei Angebote) (?).
- Brutto über, netto unter 1.000 € (Direktvergabe, A:proc-05 (?), B:proc-e01).
- Reverse Charge: ausländisches Angebot ohne USt, Wertung netto (A:proc-12).
- Zwei Angebote plus Begründung der Alleinstellung (soft `unclear`, LLM-Urteil).
- Rahmenvertragsprodukt unter 1.000 € (bleibt gebunden, S:proc-03).
- GWG-Grenze 800,00 / 800,01 € (nur Einordnung, kein Ablehnungsgrund).
