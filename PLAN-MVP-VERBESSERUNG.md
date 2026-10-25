# Entwicklungsplan: Marcs MVP mit synthetischen Fällen verbessern

> Für Claude Code geschrieben. Vorher lesen: `AGENTS.md`, `txt.txt` (TIRA-Abgabe und Fehler, die schon passiert
> sind), `UniAgentTeamCIKM/marc-uniagent-solver/CLAUDE.md` (Arbeitsregeln), `.../RESULTS.md`,
> `UniAgentTeamCIKM/evaluation/synthetic/README.md` und `RESULTS.md`.
>
> Start-Prompt für einen neuen Chat:
> ```
> Lies PLAN-MVP-VERBESSERUNG.md und setze ihn von Phase 1 bis Phase 6 komplett um. Halte nur vor der echten
> TIRA-Submission an.
> ```

## 0. Arbeitsmodus

- **Der Plan wird von vorne bis hinten ohne Zwischenfreigabe umgesetzt.** Nach jeder Phase kurz den Stand melden
  (eine Zeile plus Tabelle) und ohne Warten weitermachen. Lange Läufe im Hintergrund starten.
- **Einziger Haltepunkt:** vor dem Merge auf `main`, dem Push und der echten TIRA-Submission (Phase 6). Dort
  Ergebnis zeigen und auf Marcs OK warten.
- **Vorab freigegeben** (gilt als Rückfrage nach AGENTS.md): `reportlab==4.2.5` als reine Generator-Abhängigkeit
  (wird schon von `make_synthetic.py` verwendet, nicht im Solver-Image). `json-repair` im Solver, falls Phase 4d es
  braucht (wird schon vom Team-Solver verwendet). LLM-Aufrufe über OpenRouter mit dem Key aus `CIKM/.env`
  (`API_KEY`), auch für den Textgenerator in C5. Alles andere Neue: nicht hinzufügen, sondern im Abschlussbericht
  als Vorschlag nennen.
- **Unsichere Labels** entscheidet nicht Marc, sondern sie werden mit (?) markiert und **aus dem Gate
  herausgerechnet** (getrennt berichtet). Es wird nicht auf sie getunt.
- Commits laufend auf dem Branch `marc-mvp-v2` im Repo `UniAgentTeamCIKM`. Kein Force-Push, nichts löschen außer
  eigenen Run-Artefakten. `uniagent-code` wird nur gelesen.
- AGENTS.md "nach zwei Fehlversuchen die Annahme hinterfragen" heißt hier: Eine Solver-Änderung, die nach zwei
  Anläufen das Gate nicht besteht, wird zurückgenommen und im Bericht notiert.

## 1. Ziel und Rahmen

**Ziel:** Marcs MVP (`UniAgentTeamCIKM/marc-uniagent-solver`, auf TIRA als `several-step`, Commit `13618cf`) deckt
mehr Fallmuster ab, ohne auf bisher richtigen Fällen schlechter zu werden.

**Deadline:** Systemabgabe **20.10.2026 AoE** (= 21.10.2026, 13:59 Uhr MESZ). Die verbesserte Version wird als
**zusätzliche** Submission abgegeben, `several-step` bleibt. Grober Zeitplan: Phase 1–3 am 19.10., Phase 4 bis
20.10. mittags, Phase 5 bis 20.10. abends, dann der Haltepunkt. Wird die Zeit knapp, Phase 4 nach Schritt 4a oder 4b
abbrechen und mit dem letzten Stand, der das Gate bestanden hat, zu Phase 6 gehen. Hat nichts das Gate bestanden,
wird nichts abgegeben.

**Bewertung auf TIRA:** Die Organisatoren starten die Läufe mit `openai/gpt-oss-20b`, `openai/gpt-oss-120b` und
`Qwen/Qwen2.5-7B-Instruct` (vLLM, Standardparameter, kein Tool-Calling). Lokal über OpenRouter mit
`openai/gpt-oss-20b` (Hauptmodell), `openai/gpt-oss-120b` und `qwen/qwen-2.5-7b-instruct` testen. Mit Qwen erreichte
der MVP auf den Spot-Checks nur 18/21 (RESULTS.md, R5).

**Harte Regeln** (aus `marc-uniagent-solver/CLAUDE.md`):
- Keine Case-IDs, Personen-, Firmennamen oder Beträge aus irgendeinem Datensatz im Solver-Code. Regeln kommen aus
  den **Korpora** (jede zitiert eine `doc_id`), nie aus einem Fall-Label.
- `ground-truth.jsonl` und `decision-trail/` liest nur die Evaluation, nie der Solver.
- Alles in Docker (4 CPU, 40 GB), LF-Zeilenenden, kein Internet zur Laufzeit außer `OPENAI_BASE_URL`.
- Pseudonymisierungsspuren entscheiden nie einen Fall. TH-Sallstedt-Fälle: keine Kassel-spezifischen Schwellen.

## 2. Datenlage (Stand 19.10.2026)

| Set | Ort | Fälle | Stand MVP (gpt-oss-20b) |
|---|---|---|---|
| **S** Spot-Checks (offiziell) | `uniagent-code/cikm26/datasets/{business-trip,task-2-procurement,task-2-expense-reimbursement}-spot-check` | 21 (5/8/8) | 21/21 (Trainingsgenauigkeit) |
| **A** Synthetisch, Marc | `UniAgentTeamCIKM/evaluation/synthetic/datasets/synthetic-*` | 36 (12/12/12) | 29/36, alle 7 Fehler falsch `angenommen` |
| **B** Synthetisch, Rajesh | `UniAgentTeamCIKM/rajesh-uniagent-solver/synthetic/synthetic/synthetic_cases` | 18 | nie gelaufen (Klartext mit `.pdf`-Endung, `pdftotext` liest das nicht) |
| **C** Neu | Phase 3 | ca. 60–80 | – |
| **H** Holdout | Phase 3 | ca. 20 | – |

Fehler des MVP auf A (alle neue Muster, Regel fehlt in `solver/knowledge/*.yaml`): Honorar für Vortrag =
Nebentätigkeit, Online-Konferenz als Dienstreise, unvollständiges Formular ohne Zweck-Nachweis, Citavi
(Campuslizenz), Monitor (Rahmenvertragsprodukt) als Auslage, Gastgeschenk > 30 EUR, Dekoration. Befund aus
`evaluation/synthetic/RESULTS.md`: *"the model accepts when no check fails"*.

**Wichtige Quelle, die bisher niemand genutzt hat:** `uniagent-code/cikm26/datasets/business-trip-spot-check/make_examples.py`
ist der **Generator der Organisatoren** (1.055 Zeilen, reportlab). Er imitiert die Dokumenttypen echter Akten
(SAP-Reiseantrag, Outlook-Ausdrucke, Händlerrechnungen, Kontoauszüge) und schreibt zu jedem Fall einen
`decision-trail/` (z. B. `genehmigt.pdf`, `email-rueckfrage-reisekostenstelle.pdf`, `korrekturbedarf.pdf`,
`bestellfreigabe.pdf`). Laut Dataset-READMEs sind die Spot-Checks den echten, pseudonymisierten Fällen des Testsets
in Struktur und Qualität nachgebildet: Dokumente aus vielen verschiedenen Systemen, Händler in ganz Deutschland,
typische Pseudonymisierungsspuren (PLZ einer anderen Region, seltsame Nummern in Institutsangaben, ein ersetztes
Wort in anderer Schrift, entfernte Logos, geschwärzte Unterschriften, eine Produktlinie, die zum Namen wurde).

## 3. Phasen

### Phase 1: Einheitliche Evaluation und Baseline

1. Set B in das Format von Set A überführen: `evaluation/synthetic/datasets/rajesh-{business-trip,expense-reimbursement,procurement}/`
   mit `inputs/<fall>/*.pdf` (echte PDFs mit Textlayer, Text unverändert, gerendert mit den Helfern aus
   `make_synthetic.py`), `ground-truth.jsonl`, Korpora wie `link_corpora` in `make_synthetic.py`. Kategorie und
   Begründung aus `categories.jsonl` in eine `cases.jsonl` übernehmen. Fallnamen behalten.
2. `evaluation/run-mvp.sh` wiederverwenden (unterstützt `DATASETS_DIR`/`DATASETS`, wertet mit dem offiziellen
   Evaluator-Image `cikm26-evaluation` aus; falls das Image fehlt: `docker build -t cikm26-evaluation
   ../uniagent-code/cikm26/evaluation`). Neu nur `evaluation/compare_runs.py`: liest Baseline- und Kandidaten-Runs
   und gibt je Set und Fall `ok`/**A**/**R**, Flips und die Gate-Auswertung (Phase 5) aus.
3. **Baseline** = Code von `13618cf`, Image `marc-baseline`: 2 Läufe gpt-oss-20b auf S, A, B; 1 Lauf Qwen auf S.
   Runs nach `evaluation/runs/baseline/` (git-ignored), Tabelle in `evaluation/IMPROVEMENT.md`.
4. Fälle, die zwischen den zwei Läufen wechseln, als **instabil** markieren.

### Phase 2: Regelkatalog und Abdeckungsmatrix

1. Quellen durchgehen (mit `marc-uniagent-solver/scripts/search_corpora.py`): Dienstreisemanagement (`8f78f05e…`),
   Finanzbuchhaltung und Steuern (`df8a9f54…`), Beschaffung (`8521d5be…`), Rahmenverträge (`aef7cd6c…`),
   Nachhaltiges Catering (`08143d1c…`), HRKG und VV-HRKG im Korpus `hessian-law-de`, weitere Kassel-Seiten zu
   Reisekosten, Beschaffung, Auslagen. Zusätzlich die `begruendung` der 21 Spot-Check-Fälle, die Arten der
   `decision-trail`-Dokumente (Rückfrage, Korrekturbedarf, Freigabe), Rajeshs Regeln (T1, T2, E1–E4, P1, L1–L6)
   und Gareths Checks.
2. Ergebnis `evaluation/synthetic/RULES.md`, eine Zeile pro Regel:
   `Regel-ID | Typ | Wortlaut kurz | Quelle doc_id | prüfbar als (Python-Check / LLM-Urteil) | im MVP (Check-ID /
   nur YAML / fehlt) | Testfälle reject / accept (Set:Fall) | Relevanz (hoch/mittel/niedrig)`.
   Relevanz = wie wahrscheinlich die Regel in echten Akten vorkommt: hoch, wenn sie in Spot-Checks oder
   Decision-Trails vorkommt oder auf den Kassel-Seiten als Pflicht, Frist oder häufiger Fehler steht.
3. Pro Typ alle **Grenzfälle** aufführen: genau auf Schwellenwerten (1.000 EUR netto, 80 EUR Hotel, 30 EUR
   Gastgeschenk, 10 EUR Give-away, Fristen), brutto/netto, Fremdwährung, Reverse Charge.
4. Regeln mit unklarer oder widersprüchlicher Quelle mit (?) markieren.

### Phase 3: Set C und Holdout H nach neuen Erzeugungsprinzipien

**Was es schon gibt und nicht wiederholt wird:**

| Set | Erzeugungsprinzip |
|---|---|
| B (Rajesh) | Ein Klartext-Dokument pro Fall, eine Regel pro Fall, Auslösung über Schlüsselwörter ("Messe", "Großstadt"), Fokus auf die eigenen Regel-IDs und den Datumsparser |
| A (Marc) | Eigene reportlab-Vorlagen, mehrere saubere Dokumente pro Fall, genau ein Problem pro Fall, Regel von einer Kassel-Seite, Formatvarianten (neutrale Dateinamen, Bündel-Scan, Englisch, GBP, Sallstedt) |
| Gareth | Kein eigener synthetischer Datensatz: nur die offiziellen Spot-Checks und Mock-LLM-Unit-Tests |

**Neue Prinzipien für C.** Jede Familie hat einen eigenen Generator bzw. Abschnitt, jeder Fall trägt in
`cases.jsonl` die Felder `family`, `rule`, `source_doc_id`, `doc_types`, `label`, `uncertain`.

| Familie | Prinzip | Warum sie im Testset vorkommen kann | Anteil |
|---|---|---|---|
| **C1 Orga-Stil** | Layout-Funktionen aus `make_examples.py` der Organisatoren übernehmen (`antrag_pdf`, `email_pdf`, `invoice_pdf`, `bank_receipt_pdf`, `kv_table`, `money_table`, Styles). **Nicht importieren:** Die Datei hat keinen `__main__`-Schutz und schreibt beim Import PDFs nach `uniagent-code`. Stattdessen die Funktionen nach `evaluation/synthetic/orga_layouts.py` kopieren, mit Quellangabe im Modul-Docstring. Damit: SAP-Antragsformular, Outlook-Ausdruck, Händlerrechnung, Kontoauszug. Dazu Pseudonymisierungsspuren wie in den READMEs beschrieben und **zu jedem Fall ein Decision-Trail-Dokument** (Freigabe / Rückfrage / Korrekturbedarf), das das Label begründet. | Testset und Spot-Checks stammen aus demselben Prozess. Näher kommt man an die echten Akten nicht. | ca. 30 % |
| **C2 Kontrafaktische Paare** | Offizielle Spot-Check-Fälle als Vorlage: Text der PDFs auslesen und im gleichen Aufbau neu rendern, dabei **genau einen Fakt** ändern (Antragsdatum nach Reisebeginn, Betrag über die Schwelle, fehlende Unterschrift, private Adresse, drittes Angebot entfernt). In beide Richtungen: angenommene Fälle kippen zu abgelehnt, abgelehnte werden geheilt. Andere Namen, Beträge, Orte. | Prüft, ob die Entscheidung am richtigen Fakt hängt und nicht an Oberfläche. Niemand hat bisher Paare erzeugt. | ca. 20 % |
| **C3 Echte Aktenkomplexität** | Mehrere Probleme in einem Fall. Widersprüche zwischen Dokumenten (Formular 3 Nächte, Hotelrechnung 4). Korrespondenzverläufe: Rückfrage, Antwort mit nachgereichtem Beleg (wird angenommen) bzw. ohne (abgelehnt). Korrigierte Angebote, Teilstornierung, Gutschrift, Anzahlung plus Schlussrechnung. | Echte Akten bestehen aus Verläufen, nicht aus einem sauberen Dokument. | ca. 20 % |
| **C4 Unauffällige Annahmen** | Fälle, die verdächtig **aussehen**, aber korrekt sind: starke Pseudonymisierungsspuren, Wort in anderer Schrift, fremde PLZ, geschwärzte Unterschrift neben gültiger, "Genehmigt von: ---" im Antragsstadium, englische Rechnung, Brutto über / Netto unter Schwelle, Rahmenvertrag ohne Angebote. | Falsche Ablehnungen sind das Hauptrisiko, sobald mehr Regeln dazukommen. A und B haben kaum solche Fälle. | ca. 20 % |
| **C5 Fremd formuliert** | Aus einer strukturierten Fallbeschreibung (Fakten, Regel, Label) schreibt ein **anderes LLM** als der Solver (über OpenRouter, z. B. ein Claude-, Mistral- oder Llama-Modell) die frei formulierten Texte: E-Mails, Begründungen, Zweckangaben. Das Label kommt aus der Beschreibung, nicht vom LLM. Ein Skript prüft, dass jeder Pflichtfakt wörtlich im Text steht. Sonst wird neu generiert. | Echte Antragsteller schreiben nicht im Stil des Generator-Autors. Bricht die Formulierungs-Monokultur von A und B. | ca. 10 % |

**Auswahl der Regeln für C:** zuerst Regeln mit Relevanz hoch aus `RULES.md`, die weder Check noch Testfall haben,
dann hoch mit nur YAML, dann mittel. Pro Regel mindestens 1 Ablehnung und 1 passende Annahme, pro Schwellenwert
zusätzlich 1 Fall genau auf der Grenze. Ungefähr die Hälfte angenommen.

**Plausibilitätsregel:** Jeder Fall muss in einer echten Kassel- bzw. Wernstadt-Akte vorkommen können. Nur
Dokumenttypen, die in den Spot-Checks oder auf den Kassel-Seiten vorkommen. Keine exotischen Konstruktionen, nur um
eine Regel abzuhaken.

**Holdout H:** Für ca. ein Viertel der C-Regeln wird ein zweites Paar mit anderer Familie und anderer Oberfläche
erzeugt. H wird in Phase 4 **weder angeschaut noch verwendet**, nur einmal in Phase 5.

**Umsetzung:** neuer Generator `evaluation/synthetic/make_coverage.py`. Er nutzt die Helfer von `make_synthetic.py`
und `orga_layouts.py` (siehe C1). Ausgabe nach `datasets/coverage-{business-trip,expense-reimbursement,procurement}`
und `datasets/holdout-*`, gleiches Format wie A. `README.md` in `evaluation/synthetic/` um die Falltabelle von C
ergänzen (Fall, Familie, Label, Regel, Quelle, (?)), H nur mit Anzahl. Danach die Baseline auf C und H laufen lassen
und in `IMPROVEMENT.md` eintragen (für H nur die Summe, keine Einzelfälle ansehen).

### Phase 4: Solver verbessern

Reihenfolge nach Hebel. Nach **jedem** Schritt: Gate (Phase 5, Punkte 1–5) auf S + A + B + C mit gpt-oss-20b. Besteht
der Schritt, wird committet und weitergemacht. Sonst ein zweiter Anlauf, danach zurücknehmen und weiter mit dem
nächsten Schritt.

**4a. Fehlende Regeln in die Wissensbasis.** Für jede Regel ohne MVP-Abdeckung einen Eintrag in
`solver/knowledge/rules_*.yaml` (gleiches Schema, mit `doc_id`). Beispiele: Honorar = Nebentätigkeit,
Online-Veranstaltung keine Dienstreise (heute nur `EXP_ONLINE_CONFERENCE`), Pflichtangaben im Formular und
Zweck-Nachweis, Campuslizenzen, Rahmenvertragsprodukte auch als Auslage (heute nur `PROC_FRAMEWORK_CONTRACT`),
Gastgeschenk ≤ 30 EUR, Give-away ≤ 10 EUR, Dekoration, private Verlängerung mit Kostentrennung. Prüfen, dass die
Regeln im Prompt landen (`_rules_block` in `solver/decide.py`) und das Prompt-Budget halten.

**4b. Deterministische Checks**, wo die Fakten sicher extrahierbar sind (Schwellenwerte, Länder-Ausschluss,
Datumslogik, Rahmenvertrags-Produktgruppen, Widersprüche zwischen Dokumenten). Muster der vorhandenen Checks in
`solver/checks/*.py` (`pass | fail | unclear`). `hard` nur, wenn der Check auf keinem angenommenen Fall in S, A, B, C
anschlägt. Schema-Felder in `solver/schemas.py` nur ergänzen, wenn ein Check sie braucht. Jeder neue Check bekommt
Unit-Tests in `tests/test_units.py` (Mock-LLM).

**4c. Entscheidungsprompt.** Wenn das Modell trotz passender Regel noch annimmt: Im Prompt festhalten, dass eine
klar verletzte Regel aus dem Regelblock auch ohne fehlgeschlagenen Check zur Ablehnung führt. Gegenprobe auf alle
angenommenen Fälle, besonders C4.

**4d. Qwen-Robustheit.** Ein Lauf mit `qwen/qwen-2.5-7b-instruct` auf S und A. Scheitert Qwen am Format
(JSON-Parsing, `reasoning_effort`), das gezielt beheben. Für JSON `json-repair` wie im Team-Solver übernehmen (siehe
`team-uniagent-solver/ABLATIONS.md`).

**Nicht machen:** neue Architektur, Regeln ohne Korpusquelle, Tuning auf (?)-Fälle oder auf H.

### Phase 5: Gate

Eine Änderung besteht nur, wenn **alle** Punkte erfüllt sind (gpt-oss-20b, 2 Läufe, zusammen gewertet, (?)-Fälle
herausgerechnet):

1. **Spot-Checks S:** kein Fall, der in beiden Baseline-Läufen richtig war, ist in beiden neuen Läufen falsch.
2. **Keine Regression auf A, B, C:** kein stabil richtiger Baseline-Fall wird stabil falsch. Instabile Fälle zählen
   nicht als Regression, werden aber aufgeführt.
3. **Gesamtgenauigkeit** auf A + B + C steigt oder bleibt gleich.
4. **Falsche Ablehnungen** (**R**) steigen nicht. Das wiegt schwerer als zusätzliche richtige Ablehnungen.
5. Unit-Tests grün (`docker build` führt sie aus), Traces gültig (`scripts/validate_trace.py`), 0 ungültige
   Log-Zeilen, max. Sekunden pro Fall < 240.

**Vor dem Haltepunkt zusätzlich (Endstand):**
6. **Holdout H** einmal: Genauigkeit mindestens so hoch wie die Baseline auf H.
7. **Qwen** auf S nicht schlechter als die Qwen-Baseline. **gpt-oss-120b** auf S und A je 1 Lauf ohne Absturz.

Jeder Gate-Lauf kommt nach `evaluation/IMPROVEMENT.md`: Datum, Commit, Tabelle je Set und Familie, Flips gegenüber
der Baseline.

### Phase 6: Abgabe vorbereiten, Haltepunkt, abgeben

1. `marc-uniagent-solver/RESULTS.md` aktualisieren: Endstand-Tabelle, Hinweis "Trainingsgenauigkeit auf eigenen
   Labels". Abschlussbericht in `evaluation/IMPROVEMENT.md`: was geändert wurde, was zurückgenommen wurde, offene
   (?)-Fälle, Vorschläge.
2. Dry-Run nach `txt.txt` aus dem Branch-Stand (`--dry-run`, mit `MSYS_NO_PATHCONV=1 PYTHONUTF8=1`).
3. **HALTEPUNKT:** Marc Gate-Tabelle, Holdout, Qwen und Dry-Run zeigen und auf OK warten.
4. Nach OK: Branch auf `main` mergen, pushen. `git status --porcelain --untracked-files=all` muss leer sein
   (sonst bricht `tira-cli` ab). Danach die echte Submission nach `txt.txt`.
5. Marc den neuen Software-Namen auf TIRA nennen. Das Team legt fest, welche der bis zu fünf Submissions zählen.
   In der TIRA-Oberfläche nicht auf "Run" klicken, die Läufe startet die Orga.

## 4. Risiken

| Risiko | Gegenmaßnahme |
|---|---|
| Labels der synthetischen Sets sind unsere Lesart, nicht Orga-Gold | (?)-Fälle aus dem Gate herausrechnen, nicht darauf tunen; C1 begründet jedes Label mit einem Decision-Trail-Dokument |
| Overfitting auf eigene Fälle | Regeln nur mit Korpusquelle, Holdout H, keine Namen/Beträge im Code, fünf verschiedene Erzeugungsprinzipien |
| Mehr Regeln führen zu falschen Ablehnungen echter Fälle | Familie C4, Gate-Punkt 4, `hard` nur bei eindeutigen Fakten |
| C2 baut auf Spot-Checks auf, auf denen der MVP entwickelt wurde | C2 nur mit geänderten Namen, Beträgen, Orten; Ergebnisse je Familie getrennt berichten |
| OpenRouter nicht deterministisch | 2 Läufe, instabile Fälle getrennt |
| Qwen2.5-7B schwächer und formatanfälliger | Phase 4d, Gate-Punkt 7 |
| Zeit bis zur Deadline | Abbruchregel in Abschnitt 1; abgegeben wird nur ein Stand, der das Gate bestanden hat, sonst bleibt `several-step` |
