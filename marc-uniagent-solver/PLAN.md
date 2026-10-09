# Entwicklungsplan: UniAgent 2026 – Task 2 (Solving)

> Dieser Plan ist so geschrieben, dass er direkt mit **Claude Code** abgearbeitet werden kann.
> Leg ihn als `PLAN.md` ins Projekt-Root und starte jede Phase mit dem dort angegebenen Prompt.

---

## 0. Rahmenbedingungen (Stand 07.10.2026)

| Punkt | Fakt |
|---|---|
| **Abgabe Systeme** | **20. Oktober 2026 (AoE)** → ab heute ca. **13 Tage** |
| Registrierung | Schloss am 03.10. – bitte bei Dr. Aarzoo bestätigen lassen, dass das Team registriert ist |
| Bewertung | **Accuracy** der Entscheidung `angenommen` / `abgelehnt` gegen Sachbearbeiter-Entscheidung. Effizienz (Laufzeit, Tokens) fließt zusätzlich ein |
| Laufzeit-Limits | 5 min pro Fall, 4 h gesamt, ~50 Testfälle, 4 CPU, 40 GB RAM, **kein Internet** |
| LLM im Sandbox | `gpt-oss-20b`, `Qwen2.5-7B-Instruct` über OpenAI-kompatible REST-API, Zugang per Env-Vars `OPENAI_BASE_URL`, `OPENAI_API_KEY`, `OPENAI_MODEL` (optional `OPENAI_REASONING_EFFORT`) |
| Abgabe | Code-Submission via TIRA (Docker-Image), max. 5 priorisierte Runs |
| Pflicht-Outputs | `predictions.jsonl` (eine Zeile pro Fall: `antrag`, `result`, `begruendung`) + `run-trace.jsonl.log.gz` gemäß Event-Logging-Contract |

### Was die Spot-Check-Daten verraten (21 Fälle insgesamt)

| Datensatz | Fälle | angenommen / abgelehnt | Typische Ablehnungsgründe |
|---|---|---|---|
| `business-trip-spot-check` (`dienstreiseantrag-*`) | 5 | 2 / 3 | Antrag nach Reiseantritt gestellt; Rückreise fehlt / Summen offen; Doppelfinanzierung (Stipendium deckt Kosten bereits) |
| `task-2-procurement-spot-check` (`beschaffungsantrag-*`) | 8 | 4 / 4 | < 3 Vergleichsangebote ab 1.000 € netto; Rahmenvertragsprodukt außerhalb Rahmenvertrag gekauft; Rechenfehler Summe; Vergabevermerk mit falschem Betrag → falscher Zuschlag |
| `task-2-expense-reimbursement-spot-check` (`auslagenerstattung-*`) | 8 | 4 / 4 | Rechnung privat adressiert ohne Dienstbezug; nur Pro-forma-Rechnung; Doppeleinreichung derselben Bestellung; nicht erstattungsfähige Positionen (Teeküche/Kaffee) |

**Kernerkenntnis:** Fast alle Entscheidungen hängen an **prüfbaren Fakten** (Datumsvergleiche, Summen, Anzahl Angebote, Schwellenwerte, Adressat, Duplikate) plus einer überschaubaren Menge an **Regeln der Uni Kassel / HRKG**. Ein 20B-Modell, das frei „Agent spielt“, scheitert genau an Arithmetik und Datumslogik. Deshalb:

> **Architekturprinzip: LLM extrahiert, Python prüft, LLM entscheidet nur mit vorgekauten Befunden.**

Weitere wichtige Details aus den Dataset-READMEs:
- Fälle der **„Universität Wernstadt“** folgen den Regeln der Uni Kassel + Hessisches Reisekostengesetz (beides in den Korpora).
- Fälle der **„TH Sallstedt“** unterliegen einem anderen Landesrecht, das **nicht** im Korpus ist → nur anhand der Dokumente entscheiden, Kassel-spezifische Schwellen nicht blind anwenden.
- Pseudonymisierungs-Artefakte (falsche PLZ, ungültige IBAN, geschwärzte Unterschriften, andere Schriftart) **entscheiden nie** einen Fall → explizit im Prompt ausschließen.
- Die Testdaten können zusätzliche Korpora (z. B. Intranet) enthalten → Korpora zur Laufzeit entdecken, nicht hart codieren.

---

## 1. Zielarchitektur

```
predict.py --input $inputDataset --output $outputDir
│
├─ 1. Discover      Fälle (dienstreiseantrag-*, beschaffungsantrag-*, auslagenerstattung-*) + Korpora
├─ 2. Index         BM25 über alle retrieval-corpora/*/documents.jsonl.gz (einmal pro Run)
│
└─ pro Fall (Timeout-Guard 4:00 min, harte Grenze 5:00):
   ├─ 3. Parse      pdftotext -layout (Fallback pdfplumber) → Text je PDF
   ├─ 4. Classify   Dokumenttyp je PDF (Antrag, Angebot, Rechnung, Pro-forma, Gutschrift,
   │                Kontoauszug, Vergabevermerk, Warenkorb, E-Mail, Stipendium, …)
   ├─ 5. Extract    LLM → strikt validiertes JSON (Pydantic) je Dokumenttyp:
   │                Beträge netto/brutto, Daten, Adressat, Positionen, Institution,
   │                Bestellnr., Kostenstelle, Finanzierung, Reisezeitraum, Hotelpreis …
   ├─ 6. Check      Deterministische Regelprüfungen in Python je Falltyp
   │                → Liste von Befunden {rule_id, status: pass|fail|unclear, detail, quelle}
   ├─ 7. Retrieve   Kuratierte Regelbasis (YAML mit Korpus-doc_id-Zitaten)
   │                + BM25-Nachschlag für „unclear“-Befunde
   ├─ 8. Decide     LLM-Urteil mit Befunden + Regeln → JSON {result, begruendung, belege}
   │                optional Self-Consistency (3 Samples, Mehrheit) wenn Zeit reicht
   └─ 9. Log/Write  predictions.jsonl + run-trace.jsonl.log.gz (Contract-konform)
```

Warum so:
- **Accuracy:** Die häufigsten Ablehnungsgründe (Rechenfehler, Datum, Anzahl Angebote, Duplikat) werden zuverlässig von Code gefunden statt vom 20B-Modell geraten.
- **Effizienz:** Wenige, kurze, strukturierte LLM-Calls statt langer smolagents-Schleifen → weniger Tokens, schneller (fließt in die Bewertung ein).
- **Paper-Story:** „Modest model + gutes Systemdesign“ ist genau, was im Einladungsschreiben gefordert wird, und gibt saubere Ablationen (Regeln an/aus, Retrieval an/aus, Self-Consistency an/aus).

---

## 2. Projektstruktur

```
uniagent-solver/
├── CLAUDE.md                  # Kontext + Regeln für Claude Code (siehe Abschnitt 6)
├── PLAN.md                    # dieses Dokument
├── Dockerfile                 # basiert auf Baseline-Image (pyterrier) oder python:3.11-slim + bm25s
├── requirements.txt
├── predict.py                 # Entry-Point, CLI identisch zur Baseline
├── solver/
│   ├── config.py              # Env-Vars, Timeouts, Feature-Flags (für Ablationen)
│   ├── discovery.py           # Fälle + Korpora finden, case_type_for()
│   ├── pdf.py                 # Textextraktion + Cache
│   ├── classify.py            # Dokumenttyp (Dateiname + Keywords, LLM nur als Fallback)
│   ├── schemas.py             # Pydantic-Modelle je Dokumenttyp + Fall-Fakten
│   ├── extract.py             # LLM-Extraktion mit JSON-Validierung + Retry
│   ├── checks/
│   │   ├── common.py          # Datums-/Betragsparser (deutsches Format!), Summenprüfung, Duplikate
│   │   ├── business_trip.py
│   │   ├── procurement.py
│   │   └── expense.py
│   ├── knowledge/
│   │   ├── rules_business_trip.yaml
│   │   ├── rules_procurement.yaml
│   │   └── rules_expense.yaml
│   ├── retrieval.py           # BM25-Index über Korpora, zur Laufzeit entdeckt
│   ├── llm.py                 # OpenAI-kompatibler Client, Token-Zählung, Retries, Timeouts
│   ├── decide.py              # Entscheidungsprompt, Self-Consistency, Fallback-Logik
│   └── event_log.py           # Contract-konformes Logging (angelehnt an Baseline event_logging.py)
├── scripts/
│   ├── evaluate_local.py      # Accuracy je Falltyp, Konfusionsmatrix, Fehleranalyse
│   ├── run_all_spot_checks.sh # alle 3 Datensätze im Docker laufen lassen + evaluieren
│   └── validate_trace.py      # prüft run-trace.jsonl.log.gz gegen den Contract
├── data/                      # Spot-Check-Datensätze (Kopie aus uniagent-code/cikm26/datasets)
└── tests/
```

---

## 3. Phasen mit Claude-Code-Prompts

Jede Phase hat ein **Abnahmekriterium**. Erst weitermachen, wenn es erfüllt ist.

### Phase 0 – Setup & Baseline-Messung (Tag 1, 07.–08.10.)

Aufgaben:
1. `git clone https://github.com/uniagent-webis-de/uniagent-code` neben das Projekt.
2. Spot-Check-Daten nach `data/` kopieren (inkl. `ground-truth.jsonl`, nur für Evaluation!).
3. Vorhandene gpt-oss-API aus deinem Ordner anbinden: Env-Vars `OPENAI_BASE_URL`, `OPENAI_API_KEY`, `OPENAI_MODEL=gpt-oss-20b` in `.env` (nicht committen).
4. Baselines `solving-always-rejected` und `solving-smolagents-with-retrieval` laufen lassen und Accuracy je Datensatz notieren → das ist die Messlatte für den Teamvergleich.
5. `scripts/evaluate_local.py` schreiben (Accuracy gesamt + je Falltyp, Liste falscher Fälle mit Gold-Begründung).

> **Prompt für Claude Code:**
> „Lies `PLAN.md` Abschnitt 0–3 und `../uniagent-code/AGENTS.md`. Richte das Projekt nach Abschnitt 2 ein (nur Gerüst, leere Module). Kopiere die drei Task-2-Spot-Check-Datensätze nach `data/`. Schreibe `scripts/evaluate_local.py`, das eine `predictions.jsonl` gegen `ground-truth.jsonl` auswertet (Accuracy gesamt und je Präfix, Liste der Fehler mit Gold-`begruendung`). Baue danach das Docker-Image der Baseline `solving-smolagents-with-retrieval`, lasse es mit meinen Env-Vars gegen alle drei Datensätze laufen und trage die Ergebnisse in `RESULTS.md` ein.“

✅ Abnahme: `RESULTS.md` enthält Baseline-Accuracy für alle 3 Datensätze; LLM-Endpoint erreichbar aus Docker (`--network host` oder Host-IP).

### Phase 1 – Parsing, Klassifikation, Datenmodell (Tag 2–3)

Aufgaben:
- `pdf.py`: `pdftotext -layout`, Fallback `pdfplumber`; Text je Seite behalten (für Zitate mit Seitenangabe im Log).
- `classify.py`: Dokumenttyp zuerst über Dateiname (`angebot-*`, `rechnung-*`, `kontoauszug*`, `vergabevermerk*`, `email-*`, `antrag-*`, `gutschrift-*`), dann Keyword-Regeln im Text („Pro-forma“, „Gutschrift“, „Warenkorb“, „Stipendium“). LLM nur, wenn beides nichts findet.
- `schemas.py`: Pydantic-Modelle, z. B.
  - `Money(net, gross, vat_rate, currency)`
  - `Invoice(number, date, issuer, recipient_name, recipient_is_institution, items[], total, is_proforma, order_number)`
  - `Offer(vendor, number, date, net_total, items[])`
  - `ProcurementRequest(number, date, items[], stated_net_total, num_offers_stated, framework_contract_ref)`
  - `TravelRequest(submitted_date, trip_start, trip_end, destination, purpose, costs{...}, hotel_rate_per_night, private_extension_days, funding_source)`
  - `CaseFacts(case_id, case_type, institution: wernstadt|sallstedt|unknown, documents[], …)`
- `checks/common.py`: robuste Parser für deutsche Zahlen (`2.667,00 €`) und Datumsformate (`20.10.2026`, `20. Oktober 2026`, englische Belege).

> **Prompt für Claude Code:**
> „Implementiere Phase 1 aus `PLAN.md`: `pdf.py`, `classify.py`, `schemas.py`, `checks/common.py`. Schreibe ein Skript `scripts/dump_cases.py`, das für alle 21 Spot-Check-Fälle Dokumenttyp und extrahierten Text in `debug/` schreibt. Unit-Tests für Zahl- und Datumsparser mit Beispielen aus den echten PDFs. Noch keine LLM-Calls.“

✅ Abnahme: Jede der ~70 PDFs bekommt einen plausiblen Dokumenttyp; Parser-Tests grün.

### Phase 2 – LLM-Extraktion (Tag 3–4)

Aufgaben:
- `llm.py`: OpenAI-kompatibler Client (`openai`-Paket), Timeout pro Call, 1 Retry, Token-Usage aus Response mitloggen, `reasoning_effort` aus Env.
- `extract.py`: pro Dokument ein Prompt mit dem passenden Schema als JSON-Schema; Antwort per Pydantic validieren; bei Fehler 1 Korrektur-Retry mit Fehlermeldung. Deterministische Felder (Summen, Daten) zusätzlich per Regex gegenprüfen.
- Lange Dokumente kürzen (Kopf + relevante Abschnitte), damit 20B-Kontext und Zeitlimit passen.

> **Prompt für Claude Code:**
> „Implementiere Phase 2: `llm.py` und `extract.py`. Für jeden Dokumenttyp ein knapper deutscher Extraktions-Prompt, Ausgabe strikt als JSON gegen das Pydantic-Schema. Erzeuge `debug/<case>/facts.json` für alle 21 Fälle und zeige mir 3 Beispiele. Logge jeden LLM-Call schon jetzt über `event_log.py` (Contract: `../uniagent-code/cikm26/event-logging-contract/README.md`).“

✅ Abnahme: Für ≥ 90 % der Dokumente stimmen Beträge und Daten mit manueller Stichprobe überein; < 60 s pro Fall.

### Phase 3 – Regelprüfungen + Regelbasis (Tag 4–7, Kern des Systems)

**3a. Regelbasis kuratieren** (`knowledge/*.yaml`): Für jede Regel ein Eintrag

```yaml
- id: PROC_3_OFFERS
  text: "Ab 1.000 € netto sind grundsätzlich drei schriftliche Vergleichsangebote einzuholen; darunter Direktvergabe möglich."
  applies_to: [wernstadt]
  source: {corpus: university-kassel-public-de, doc_id: "<per BM25 suchen und eintragen>"}
```

Die `doc_id`s sucht Claude Code mit BM25 in den Korpora (Uni-Kassel-Seiten „Beschaffung“, „Rahmenverträge“, „Finanzbuchhaltung und Steuern / Kostenerstattung“, HRKG §§ zu Genehmigung, Übernachtung, Verbindung mit Privatreise).

**3b. Checks je Falltyp** (jeder Check liefert `pass | fail | unclear` + Detail + Quelle):

| Falltyp | Checks (aus den Gold-Begründungen abgeleitet) |
|---|---|
| Dienstreise | Antrag **vor** Reiseantritt gestellt · Hin- **und** Rückreise belegt, Gesamtsumme bestimmt · Übernachtungssatz ≤ Höchstgrenze · Privatverlängerung korrekt abgegrenzt (nur dienstlich veranlasste Kosten beantragt) · keine Doppelfinanzierung (Stipendium/Dritte decken Posten) · dienstliches Interesse belegt (Einladung, Annahmebestätigung) · Bahn/Flug-Preisvergleich bei Flug · Pflichtangaben vollständig |
| Beschaffung | Netto-Summe ≥ 1.000 € ⇒ ≥ 3 Angebote (oder dokumentierte Ausnahme / Nachreichung) · Positionen × Menge = Summe in Antrag, Angebot, Vergabevermerk · Vergabevermerk-Beträge = Angebotsbeträge, Zuschlag an günstigstes Angebot · Artikel unter Rahmenvertrag ⇒ über Rahmenvertrag/Katalog bestellt · Beauftragung durch Kostenstellenverantwortliche |
| Auslagenerstattung | Echte Rechnung (keine Pro-forma) · Dienstbezug erkennbar (Adressat Uni/Lehrstuhl oder dienstlicher Vermerk) · Artikel benannt oder Stichwort ergänzt · keine Doppeleinreichung (gleiche Bestellnr./Beträge/Positionen) · Positionen erstattungsfähig (keine privaten Bewirtungs-/Teeküchenartikel) · Gutschriften verrechnet · Fremdwährung + Auslandsgebühr plausibel |

Wichtig: Für **Sallstedt-Fälle** Kassel-spezifische Schwellen auf `unclear` statt `fail` setzen und die Entscheidung dem LLM mit den Dokumenten überlassen.

> **Prompt für Claude Code:**
> „Implementiere Phase 3. (a) Baue `retrieval.py` (BM25 über alle `retrieval-corpora/*/documents.jsonl.gz`, Korpora zur Laufzeit entdecken, Sprache aus `-de`/`-en`-Suffix). Suche damit die Belegstellen für die Regeln in PLAN.md Abschnitt 3b und schreibe `knowledge/*.yaml` mit echten `doc_id`s. (b) Implementiere die Checks je Falltyp in `checks/`. Jeder Check ist eine kleine reine Funktion `CaseFacts -> Finding` mit Unit-Test. Verwende die Gold-Begründungen nur, um Regeln zu verstehen – **keine fallspezifischen Sonderregeln, keine Case-IDs im Code**. Gib am Ende eine Tabelle Fall × Check aus.“

✅ Abnahme: Für jeden der 11 abgelehnten Spot-Check-Fälle schlägt mindestens ein Check mit dem inhaltlich richtigen Grund an; für die 10 angenommenen Fälle gibt es kein `fail` (oder es ist erklärbar).

### Phase 4 – Entscheidung (Tag 7–8)

- `decide.py`: Prompt bekommt (1) Falltyp + Institution, (2) kompakte Fakten, (3) Check-Befunde, (4) relevante Regeltexte mit Quelle, (5) Hinweis „Pseudonymisierungsspuren ignorieren“. Ausgabe: `{"result": "angenommen|abgelehnt", "begruendung": "...", "belege": [...]}`.
- **Entscheidungslogik (hybrid):**
  - Mind. ein harter `fail` mit hoher Sicherheit ⇒ `abgelehnt` (LLM schreibt nur Begründung).
  - Nur `pass` ⇒ LLM bestätigt; nur bei starkem Gegenargument kippen.
  - `unclear` ⇒ LLM entscheidet, optional mit 3 Samples und Mehrheitsentscheid.
- Fallback bei Fehler/Timeout: Entscheidung nur aus Checks; wenn gar nichts da ist: Mehrheitsklasse (aktuell ausgeglichen, `abgelehnt` wie Baseline).
- Feature-Flags in `config.py` (`USE_CHECKS`, `USE_RETRIEVAL`, `SELF_CONSISTENCY_N`, `HARD_FAIL_OVERRIDE`) für Ablationen.

> **Prompt für Claude Code:**
> „Implementiere Phase 4 (`decide.py`, `predict.py`). `predict.py` hat dieselbe CLI wie die Baseline (`--input`, `--output`), schreibt `predictions.jsonl` und `run-trace.jsonl.log.gz`, jede Zeile mit `antrag`, `result`, `begruendung`. Pro Fall harter Timeout 4 min mit Fallback. Lasse alle drei Spot-Checks laufen, evaluiere mit `scripts/evaluate_local.py` und trage Accuracy, Laufzeit pro Fall und Tokens in `RESULTS.md` ein.“

✅ Abnahme: Accuracy auf allen 21 Fällen deutlich über Baseline; jede Fall-Laufzeit < 4 min.

### Phase 5 – Robustheit, Logging, Docker (Tag 9)

- `scripts/validate_trace.py`: jedes Event hat alle Pflichtfelder, `model` nie null, jede `case_id` endet mit `decision`, `parent_event_id` verkettet, Fehler geloggt.
- Robustheits-Tests: leerer Ordner, kaputte PDF, unbekannter Dokumenttyp, LLM liefert Müll, LLM nicht erreichbar → es muss trotzdem für **jeden** Fall genau eine Zeile entstehen.
- Docker: Image im Netz-abgeschotteten Modus testen (`--network none` + nur LLM-Endpoint erreichbar), damit nichts zur Laufzeit nachlädt (kein `pip install`, keine HuggingFace-Downloads, Stopwortlisten im Image).
- Index-Bau: Laufzeit messen (≈ 90 MB gz, ~31k + ~3k Dokumente). Wenn > 5 min, auf `bm25s` (reines Python, schnell) wechseln oder Index für bekannte Korpora im Image vorbauen und nur unbekannte zur Laufzeit indexieren.

> **Prompt für Claude Code:**
> „Phase 5: Schreibe `scripts/validate_trace.py` und Robustheitstests. Baue das Docker-Image, starte es mit `--network none` (LLM-Endpoint nur über explizit freigegebenen Host) gegen alle drei Spot-Checks und prüfe Trace und Predictions. Miss die Index-Bauzeit und schlage Optimierungen vor, falls > 3 min.“

### Phase 6 – Erste TIRA-Abgabe (Tag 10, spätestens 16.10.)

```bash
tira-cli code-submission \
  --path . \
  --task uniagent-2026 \
  --dataset business-trip-spot-check-20260907-training \
  --forward-environment-variable OPENAI_API_KEY OPENAI_BASE_URL OPENAI_MODEL \
  --command '/app/predict.py --input $inputDataset --output $outputDir' \
  --dry-run
```
Erst `--dry-run` für alle drei Datensätze, dann ohne `--dry-run`. Mit Dr. Aarzoo / Dr. Zekun abstimmen, welcher Team-Account einreicht.

✅ Abnahme: Ein valider Run ist in TIRA sichtbar. **Ab hier gibt es immer eine gültige Abgabe.**

### Phase 7 – Verbesserung & Varianten (Tag 11–13, bis 20.10.)

- Fehleranalyse aller falschen Fälle; nur **generalisierende** Regeln ergänzen.
- Bis zu 5 Submissions als Ablationen (gleichzeitig Material für das Notebook-Paper):

| Run | Konfiguration |
|---|---|
| R1 | Volles System, gpt-oss-20b, Self-Consistency an |
| R2 | Volles System, ohne Self-Consistency (Effizienz) |
| R3 | Ohne Retrieval (nur kuratierte Regeln) |
| R4 | Nur LLM ohne deterministische Checks (zeigt Wert der Checks) |
| R5 | Volles System mit Qwen2.5-7B-Instruct |

- `RESULTS.md` sauber halten (Konfiguration, Accuracy je Falltyp, Sekunden/Fall, Tokens/Fall) → Grundlage für Paper und Teamvergleich.

---

## 4. Risiken & Gegenmaßnahmen

| Risiko | Gegenmaßnahme |
|---|---|
| **Overfitting auf 21 Fälle** (Testset ~50 unbekannte, echte Fälle) | Keine Case-IDs/Firmennamen im Code; Regeln nur aus Korpus + Gold-Begründungen generalisieren; Leave-one-dataset-out-Gedankenprobe: Würde die Regel auch einen anders formulierten Fall treffen? |
| Echte Testfälle sind „unordentlicher“ als Spot-Checks | Klassifikation mit Fallbacks, `unclear` statt Absturz, LLM als letzte Instanz |
| 20B-Modell liefert kein valides JSON | Pydantic-Validierung + 1 Korrektur-Retry + deterministischer Fallback |
| Zeitlimit 5 min / Fall | Harte Timeouts, Index nur einmal bauen, Dokumente kürzen, Self-Consistency nur bei `unclear` |
| Lokales LLM ≠ TIRA-LLM (Version/Quantisierung) | Nichts auf exakte Formulierungen tunen; `temperature` niedrig; `OPENAI_MODEL` nie hart codieren |
| Sallstedt-Fälle mit fremdem Landesrecht | Institution erkennen, Kassel-Schwellen dort nicht hart anwenden |
| Deadline | Phase 6 (gültige Abgabe) hat Vorrang vor allen Verbesserungen |

---

## 5. Gemeinsamer Vergleich im Team

Damit eure MVPs vergleichbar sind, im Team vereinbaren:
- gleiche Auswertung: `scripts/evaluate_local.py` (oder `tira-cli evaluate`) auf allen drei Spot-Checks,
- gleiche Kennzahlen: Accuracy gesamt + je Falltyp, Sekunden/Fall, Tokens/Fall,
- gleiches Modell für den Vergleich (`gpt-oss-20b`, gleiche `reasoning_effort`).

---

## 6. Inhalt für `CLAUDE.md`

```markdown
# Projekt: UniAgent 2026 Task 2 (Solving) – DAIM-Team, University of Hull

## Ziel
Agent, der Verwaltungsfälle der Uni Kassel (Dienstreiseantrag, Beschaffungsantrag,
Auslagenerstattung) als `angenommen`/`abgelehnt` entscheidet. Metrik: Accuracy, dazu Effizienz.
Abgabe via TIRA bis 20.10.2026 AoE. Plan: PLAN.md.

## Harte Constraints
- Kein Internet zur Laufzeit. LLM nur über OPENAI_BASE_URL / OPENAI_API_KEY / OPENAI_MODEL.
- 5 min pro Fall, 4 h gesamt, 4 CPU, 40 GB RAM.
- Output: `predictions.jsonl` (antrag, result, begruendung) + `run-trace.jsonl.log.gz`
  gemäß ../uniagent-code/cikm26/event-logging-contract/README.md.
- Für jeden Fall genau eine Prediction-Zeile, auch bei Fehlern.

## Arbeitsregeln
- Architektur: LLM extrahiert -> Python prüft -> LLM entscheidet mit Befunden.
- Keine Case-IDs, Firmen- oder Personennamen aus den Spot-Checks im Code (Overfitting).
- `ground-truth.jsonl` nur in scripts/evaluate_local.py lesen, nie im Solver.
- Alles in Docker testen (siehe ../uniagent-code/AGENTS.md).
- Nach jeder Änderung an der Entscheidungslogik: alle 3 Spot-Checks laufen lassen,
  Ergebnis in RESULTS.md eintragen.
- Deutsche Zahlen-/Datumsformate beachten (2.667,00 €, 20.10.2026).
- Pseudonymisierungsspuren (PLZ, ungültige IBAN, Schwärzungen) entscheiden nie einen Fall.
```

---

## 7. Zeitplan auf einen Blick

| Datum | Phase |
|---|---|
| Mi 07.10. – Do 08.10. | 0 Setup, Baselines messen |
| Fr 09.10. – Sa 10.10. | 1 Parsing/Klassifikation · 2 Extraktion |
| So 11.10. – Mi 14.10. | 3 Regelbasis + Checks |
| Do 15.10. | 4 Entscheidung, 5 Robustheit/Docker |
| **Fr 16.10.** | **6 Erste gültige TIRA-Abgabe** |
| Sa 17.10. – Di 20.10. | 7 Fehleranalyse, Ablations-Runs, Priorisierung der 5 Runs |
