# Entwicklungsplan: UniAgent 2026 – Task 1 (Retrieval)

Team DAIM (University of Hull) · Stand: 27.09.2026 · Abgabe der Systeme: **15.10.2026 (AoE)**

Dieser Plan ist so geschrieben, dass er Phase für Phase an Claude Code übergeben werden kann. Jede Phase hat ein Ziel, konkrete Schritte und eine „Definition of Done“. Abschnitt 9 enthält fertige Prompts für Claude Code.

---

## 1. Was das Repo tatsächlich vorgibt (Befunde)

Quelle: `github.com/uniagent-webis-de/uniagent-code`, Ordner `cikm26/`.

### Datensätze (Task 1)

| Datensatz | Dokumente | Queries | Qrels |
|---|---|---|---|
| `retrieval-de-spot-check` | 30.983 Seiten uni-kassel.de (DE), Median ~1.200 Zeichen | 25 | 1 relevantes Dok. pro Query |
| `retrieval-en-spot-check` | 24.171 Seiten uni-kassel.de (EN), Median ~1.100 Zeichen | 25 | 1 relevantes Dok. pro Query |
| `retrieval-hessian-law-de-spot-check` | 2.829 Dokumente hessenrecht (Urteile, Verordnungen, Beschlüsse, Gesetze), Median ~13.500 Zeichen, p90 ~59.000 | 15 | 1 relevantes Dok. pro Query |

- Format pro Datensatz: `queries.jsonl`, `documents.jsonl.gz`, `qrels.txt`. Geladen wird über `tira.third_party_integrations.ir_datasets.load(<pfad oder tira-id>)`.
- Query-Felder: `qid`, `query` (Keyword-Query), `original_query.{language, description, narrative}`. **Description und Narrative sind Teil des Inputs** und dürfen genutzt werden (nur Qrels sind Ground Truth).
- Dokument-Felder Web: `doc_id, url, language, title, content, text`. Law zusätzlich: `document_type, court, decision_date, file_number, ecli`.
- **Jeder Datensatz ist einsprachig** (Baselines brechen ab, wenn Sprachen gemischt sind). Pro Datensatz ein Run.
- Spot-Check-Queries und -Qrels sind **synthetisch (LLM-generiert)**, laut README ist die Aussagekraft unklar. Das Testset enthält zusätzlich **Intranet-Dokumente**, und bei Law **alle** hessenrecht-Dokumente (deutlich größer als 2.829).

### Besonderheiten der Law-Collection (wichtig)
- Gesetze sind **pro Paragraph** gespeichert (`jlr-…NN0000000000X`), Titel z. B. `§ 6 HBeihVO | Landesnorm Hessen | … | gültig ab: … | gültig bis: …`.
- **Derselbe Paragraph existiert in mehreren Fassungen** (unterschiedliche „gültig ab“). Die Qrels zeigen auf eine bestimmte Fassung → Versions-Handling ist ein echter Hebel.
- Queries nutzen **Abkürzungen** („HRKG“), die Dokumente z. T. ausgeschrieben („Hessisches Reisekostengesetz“) → Abkürzungs-Expansion aus den Titeln der Collection ableiten.

### Evaluation
- Offizielles Maß im Evaluator (`cikm26/evaluation/evaluate_submission.py`): **nDCG@10** (trectools). Zusätzlich wird der Run-Trace auf `valid_log_lines`/`invalid_log_lines` geprüft.
- `cikm26/dataset-construction/` zeigt, wie Qrels entstehen: **Pooling der Runs (`create_pool.py`) + LLM-Relevanzurteile mit UMBRELA und `gpt-oss-20b`, Grade 0–3, Tiefe `--k 10`.** Sehr wahrscheinlich werden die finalen Qrels genauso aus den eingereichten Runs gebaut.
  → Konsequenz: **Nur die Top-10 zählen**, und „relevant“ heißt „ein UMBRELA-Prompt mit gpt-oss-20b gibt eine hohe Note“. Ein Reranker, der genau diese Beurteilung nachahmt, ist gut ausgerichtet.
  → Offizielle Bestätigung bei den Organisatoren einholen (TIRA-Forum).

### Baseline-Ergebnisse (selbst nachgerechnet aus den mitgelieferten Runs, nDCG@10)

| Modell | DE | EN |
|---|---|---|
| BM25 | 0.698 | 0.763 |
| DPH | **0.738** | **0.860** |
| DFIZ | 0.711 | 0.859 |
| LGD | 0.706 | 0.856 |
| PL2 | 0.675 | 0.740 |

Recall@100 liegt fast überall bei 1.0 → **das Problem ist das Ranking in den Top-10, nicht der Recall** (zumindest auf den Spot-Checks). Für Law gibt es keine mitgelieferten Runs → selbst messen.

### Ausführungsumgebung (TIRA)
- Docker-Image aus Code (`tira-cli code-submission`), **kein Internet** im Sandbox-Lauf → alle Modelle (Embedding/Cross-Encoder) müssen im Image liegen.
- 4 CPU-Kerne, 40 GB RAM, **keine GPU**. Zeitlimit 4 h pro Gesamtlauf.
- LLM: `gpt-oss-20b` (u. a.) über OpenAI-kompatible REST-API. Env-Variablen wie in den Baselines: `OPENAI_BASE_URL`, `OPENAI_API_KEY`, `OPENAI_MODEL` (via `--forward-environment-variable`).
- Effizienz (Laufzeit, Input-/Output-Tokens) soll mit bewertet werden → Tokenverbrauch loggen und im Griff behalten.
- Pflicht: `run.txt.gz` (TREC-Format) im Output-Verzeichnis; bei LLM-/Tool-Nutzung zusätzlich `run-trace.jsonl.log.gz` nach `cikm26/event-logging-contract/README.md`.
- Bis zu 5 priorisierte Submissions pro Team.

---

## 2. Zielarchitektur

Mehrstufige Pipeline, jede Stufe einzeln abschaltbar (für Ablationen und als Fallback):

```
Query (query + description + narrative)
  │
  ├─ [A] Query-Aufbereitung
  │     • Sprach-/Collection-Erkennung (web-de | web-en | law-de)
  │     • Abkürzungs-Expansion (aus Law-Titeln automatisch gebaut)
  │     • optional LLM-Query-Expansion (gpt-oss-20b, 1 Call/Query, gecacht)
  │
  ├─ [B] Kandidaten (Recall, Top-100…200)
  │     • Lexikalisch: PyTerrier DPH/BM25, Felder title/url/content, deutsches
  │       Decompounding, Varianten mit/ohne description
  │     • optional Dense: multilinguales Embedding-Modell auf CPU (nur wenn Zeitbudget passt)
  │     • Fusion via Reciprocal Rank Fusion (RRF)
  │
  ├─ [C] Nachbearbeitung
  │     • Law: Fassungs-Handling (Versionen desselben § gruppieren, aktuelle Fassung bevorzugen)
  │     • Web: Near-Duplicate-Kollaps (MinHash zur Laufzeit), URL-/Titel-Priors
  │
  └─ [D] Reranking der Top-k (k ≈ 20–30)
        • Cross-Encoder (CPU) und/oder
        • LLM-Reranking mit UMBRELA-artigem Prompt (0–3), gpt-oss-20b
        • finale Score-Fusion, Top-1000 schreiben
  │
  └─ run.txt.gz + run-trace.jsonl.log.gz
```

Leitprinzip (aus der Einladungsmail): ein kleines Modell durch gutes System-Design stark machen. Jede Stufe muss auf dem Dev-Set messbar etwas bringen, sonst fliegt sie raus.

---

## 3. Projektstruktur

Eigenes Repo (z. B. `daim-uniagent-retrieval`), Struktur an die Baseline `retrieval-baseline-pyterrier-smolagent` angelehnt:

```
daim-uniagent-retrieval/
├── CLAUDE.md                 # Kontext + Regeln für Claude Code (Abschnitt 8)
├── PLAN.md                   # diese Datei
├── Dockerfile                # FROM ghcr.io/uniagent-webis-de/uniagent-pyterrier-baseline:dev-0.0.1
├── requirements.txt
├── retrieve.py               # CLI-Einstieg: --dataset --output --config
├── configs/                  # YAML je Variante (bm25.yaml, hybrid.yaml, full.yaml …)
├── uniretrieval/
│   ├── data.py               # Laden via ir_datasets, Feldzugriff, Spracherkennung
│   ├── text.py               # Normalisierung, Decompounding, Stoppwörter
│   ├── lexical.py            # PyTerrier-Index + Retrieval (mehrere Modelle/Felder)
│   ├── dense.py              # optional: Embeddings + FAISS/NumPy-Suche
│   ├── fusion.py             # RRF, gewichtete Fusion
│   ├── law.py                # Abkürzungen, Fassungs-Gruppierung
│   ├── dedup.py              # MinHash-Near-Duplicates
│   ├── rerank_ce.py          # Cross-Encoder
│   ├── rerank_llm.py         # LLM-Reranker (UMBRELA-Stil)
│   ├── query_expansion.py    # LLM-Expansion
│   ├── llm.py                # OpenAI-Client, Retries, Timeouts, Token-Zählung, Cache
│   ├── event_logging.py      # aus der Baseline übernommen, vertragskonform
│   └── budget.py             # Zeitbudget-Wächter + Fallbacks
├── eval/
│   ├── evaluate.py           # nDCG@10, nDCG@20, MRR, Recall@100, per-query
│   ├── compare.py            # Tabelle über alle Runs/Varianten
│   └── devsets/              # eigene zusätzliche Dev-Queries + Qrels
├── scripts/                  # Modelle downloaden, Benchmarks, Batch-Experimente
└── tests/                    # pytest, laufen im Docker-Build
```

---

## 4. Phasen und Zeitplan

Heute ist Sonntag, 27.09. Bis zur Abgabe bleiben ~18 Tage. Da jede:r im Team zuerst ein eigenes System baut, ist der Plan so geschnitten, dass nach Phase 2 schon ein vergleichbares, abgabefähiges System existiert.

| Phase | Zeitraum | Ergebnis |
|---|---|---|
| 0 Setup & Harness | 28.–29.09. | Repo, Docker läuft, Evaluator reproduziert Baseline-Zahlen |
| 1 Starke lexikalische Basis | 30.09.–02.10. | Getunte Lexik + Fusion, abgabefähig, **Team-Vergleich möglich** |
| 2 Korpus-spezifische Tricks | 02.–04.10. | Law-Fassungen, Abkürzungen, Dedup, Priors |
| 3 Eigenes Dev-Set | parallel ab 30.09. | 60–100 zusätzliche realistische Queries mit Qrels |
| 4 Neuronale Stufen | 05.–09.10. | Dense/Cross-Encoder/LLM-Rerank, gemessen gegen Budget |
| 5 Logging, Robustheit, Effizienz | 09.–11.10. | Vertragskonformer Trace, Fallbacks, Zeitwächter |
| 6 TIRA-Submission | 11.–14.10. | bis zu 5 Varianten eingereicht (1 Tag Puffer) |
| 7 Notebook Paper | nach 15.10. | Ablationen, Beschreibung |

---

### Phase 0 – Setup & Evaluations-Harness

Ziel: Messbarkeit von Tag 1 an.

1. Repo anlegen, `uniagent-code` als Referenz daneben klonen (nicht als Abhängigkeit).
2. Docker-Entwicklungsumgebung: Basis `ghcr.io/uniagent-webis-de/uniagent-pyterrier-baseline:dev-0.0.1` (Java + PyTerrier + tira bereits drin). Laut `AGENTS.md`: **alles in Docker ausführen, kein ad-hoc venv**.
3. `eval/evaluate.py`: liest `run.txt(.gz)` + `qrels.txt`, gibt nDCG@10 (Hauptmaß), nDCG@20, MRR@10, Recall@100/1000 und eine per-Query-Tabelle aus. Gegenprüfen mit dem offiziellen Evaluator-Image (`cikm26/evaluation`, `--task retrieval`).
4. Baseline reproduzieren: BM25 und DPH auf allen drei Spot-Checks. Erwartung DE/EN siehe Tabelle oben; Law-Werte neu festhalten.
5. `eval/compare.py`: Ergebnis-Tabelle über alle Varianten (Markdown/CSV), damit Experimente vergleichbar bleiben.
6. LLM-Zugang für die Entwicklung klären (siehe offene Fragen): `gpt-oss-20b` über einen OpenAI-kompatiblen Endpoint. Für Tests ein **Mock-LLM** bauen, damit Unit-Tests offline laufen.

**Done:** `docker build` läuft inkl. Tests; ein Befehl erzeugt Runs für alle drei Datensätze und die Vergleichstabelle; Baseline-Zahlen stimmen mit Abschnitt 1 überein.

---

### Phase 1 – Starke lexikalische Basis

Ziel: das Beste ohne neuronale Modelle herausholen. Das ist zugleich der Fallback für jede spätere Stufe.

1. **Query-Formulierung:** Varianten vergleichen: nur `query`; `query + description`; `query + description + narrative` (Narrative-Formulierungen wie „Relevant sind Dokumente…“ vorher entfernen). Gewichtung der Teile testen (z. B. query-Terme doppelt).
2. **Dokument-Repräsentation:** Titel und URL-Pfad-Tokens (z. B. `/verwaltung/reisekosten/`) zusätzlich zum Content indexieren; Varianten: (a) alles in ein Feld mit Titel-Wiederholung, (b) Multi-Feld (BM25F bzw. separate Indizes + Fusion).
3. **Deutsch:** Decompounding für DE-Collections (z. B. `charsplit`/`compound-split` oder ein einfacher wörterbuchbasierter Splitter aus dem Korpus-Vokabular) – „Übernachtungskosten“ ↔ „Übernachtung Kosten“. Mit/ohne vergleichen. Umlaut-Normalisierung (ä↔ae) prüfen.
4. **Modellwahl & Tuning:** DPH, BM25 (k1, b per Grid), DirichletLM, PL2; Pseudo-Relevance-Feedback (RM3/Bo1/KL) mit/ohne.
5. **Fusion:** RRF über 2–4 Rankings (z. B. DPH-Content, BM25-Titel, DPH+Bo1). Fusion ist meist robust und billig.
6. **Passagen für lange Dokumente (v. a. Law):** Dokumente in Passagen (~200–300 Wörter, Overlap) aufteilen, Dokument-Score = max/Top-k-Summe der Passagen. Mit Volldokument vergleichen.

Wichtig: Nicht auf 25 synthetische Queries mit je 1 Relevanten übertunen. Parameter nur übernehmen, wenn sie auf **DE, EN, Law und dem eigenen Dev-Set (Phase 3)** nicht schlechter werden.

**Done:** Config `lexical-best.yaml`, die auf allen Sets ≥ DPH-Baseline liegt; Laufzeit pro Datensatz notiert; erste TIRA-Dry-Run-Submission möglich.

---

### Phase 2 – Korpus-spezifische Verbesserungen

1. **Law – Abkürzungen:** Aus allen Law-Titeln automatisch ein Mapping `Abkürzung → Langname` bauen (Titelmuster `§ n ABK | Landesnorm Hessen | Langtitel …`). Query-Terme, die einer Abkürzung entsprechen, um den Langnamen erweitern (und umgekehrt). Zur Laufzeit aus der tatsächlich gemounteten Collection bauen, nicht hart kodieren.
2. **Law – Paragraph-Matching:** Wenn die Query `§ n` + Gesetz nennt, exakte Treffer im Titel stark boosten.
3. **Law – Fassungen:** Dokumente mit gleichem Gesetz+§ gruppieren; in den Top-10 nur **eine** Fassung zeigen (standardmäßig die aktuell gültige, also jüngstes „gültig ab“ ohne abgelaufenes „gültig bis“); andere Fassungen direkt dahinter. Messen, ob die Qrels eher die aktuelle Fassung wollen.
4. **Law – Dokumenttyp-Prior:** Bei Fragen nach Regelungen („Wie hoch…“, „Wann…“) Normen (Gesetz/Verordnung) vor Urteilen; bei Fragen nach Rechtsprechung umgekehrt. Einfacher Regel- oder LLM-Klassifikator auf der Query.
5. **Web – Near-Duplicates:** Die Organisatoren liefern CopyCat-Duplikatlisten nur für die Spot-Check-Korpora; das Testkorpus ist anders → zur Laufzeit MinHash/LSH (`datasketch`) über die Kandidaten der Top-100 rechnen und Duplikate aus den Top-10 verdrängen (mehr unterschiedliche Dokumente in den Top-10 = mehr Chancen auf relevante Urteile im Pool).
6. **Web – Priors:** Leere/Navigationsseiten, News-Detailseiten, Sitemaps abwerten (Heuristiken über URL/Content-Länge), Verwaltungs-/Service-Seiten nicht. Nur behalten, wenn messbar hilfreich.
7. **Intranet-Robustheit:** Code darf nicht an URL-Mustern von `www.uni-kassel.de` hängen; unbekannte Felder tolerieren.

**Done:** Jede Maßnahme als Schalter in der Config, Ablationstabelle vorhanden.

---

### Phase 3 – Eigenes Dev-Set (parallel)

Die Spot-Checks sind zu klein und zu synthetisch (1 Relevantes pro Query). Ohne besseres Dev-Set ist jede Tuning-Entscheidung Rauschen.

1. 60–100 Queries im Stil echter Verwaltungsanfragen formulieren (Dienstreise, Hotelkosten-Grenzen, Privatverlängerung, Auslagenerstattung, Beschaffung/Bestellung, Beihilfe, Trennungsgeld …), jeweils `query`, `description`, `narrative`, Sprache. Die PDFs im `business-trip-spot-check` liefern realistische Themen. Idealerweise mit Dr Aarzoo/Dr Zekun abstimmen.
2. Pools aus mehreren eigenen Varianten + Baselines bilden (`cikm26/dataset-construction/create_pool.py`) und mit **UMBRELA + gpt-oss-20b** urteilen lassen (`create_qrels.py`) – genau wie die Organisatoren. Stichprobenartig manuell prüfen.
3. Dev-Set in `eval/devsets/` im selben Format ablegen; strikt als Dev nutzen, ein kleiner Teil als Held-out.

**Done:** Dev-Set mit Qrels (Grade 0–3) für alle drei Collections; `compare.py` wertet es mit aus.

---

### Phase 4 – Neuronale Stufen (gegen Zeit- und Tokenbudget)

Rahmen: 4 CPU-Kerne, kein GPU, Gesamtlimit 4 h, Testkorpus größer als Spot-Check. **Zuerst Laufzeit messen, dann entscheiden.** Script `scripts/benchmark_throughput.py` misst Docs/s für Embedding und Paare/s für Cross-Encoder auf 4 Kernen (`taskset -c 0-3`) und hochrechnet auf z. B. 100k und 300k Dokumente.

**4a – LLM-Reranking (höchste Priorität, weil zur Qrel-Erzeugung passend)**
- Pointwise, UMBRELA-artiger Prompt: Query + description/narrative + Dokument-Titel + Top-Passage (gekürzt, z. B. 400 Tokens) → Note 0–3 als JSON. Auf Top-20…30 der Stufe B/C.
- Finaler Score = Note als Hauptschlüssel, lexikalischer/Fusions-Score als Tie-Breaker (oder gewichtete Kombination, auf Dev bestimmt).
- Alternativ testen: listwise (ein Prompt mit 10–20 Kandidaten, Permutation zurück) – weniger Tokens, aber fehleranfälliger mit einem 20B-Modell.
- Parallele Requests (z. B. 4–8 gleichzeitig), Timeout + Retry, Antwort-Cache.
- Tokenbudget messen: z. B. 50 Queries × 25 Kandidaten × ~600 Tokens ≈ 750k Input-Tokens pro Datensatz. Mit k=10/20/30 vergleichen (nDCG vs. Tokens), da Effizienz mitbewertet wird.

**4b – Cross-Encoder (CPU)**
- Kandidaten: `BAAI/bge-reranker-v2-m3` (multilingual, stark, aber langsam) vs. ein kleineres multilinguales Modell (z. B. `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`). Top-30…50, max. 512 Tokens.
- Kann LLM-Reranking ersetzen (keine Tokens) oder vorfiltern (CE auf Top-50 → LLM auf Top-15).

**4c – Dense Retrieval (nur wenn Budget passt)**
- Multilinguales Embedding-Modell, z. B. `intfloat/multilingual-e5-small` oder `-base`; Titel + erster Abschnitt, bei Law passagenweise.
- Zur Laufzeit ganze Collection zu embedden ist auf 4 CPUs der Engpass → nur einsetzen, wenn Hochrechnung für das Testkorpus < ~50 % des Zeitbudgets. Alternative: Dense nur als Reranking-Signal auf Top-200 der Lexik (billig, trotzdem hilfreich).
- In RRF mit der Lexik fusionieren.

**4d – LLM-Query-Expansion**
- 1 Call pro Query: Synonyme, Fachbegriffe, deutsche/englische Verwaltungsbegriffe, relevante Gesetzesnamen; optional kurzes hypothetisches Antwortdokument (query2doc). Als zusätzliches lexikalisches Ranking in die Fusion geben.

Für jede Stufe: Ablation auf allen Dev-Sets, Laufzeit und Tokens festhalten.

**Done:** Tabelle nDCG@10 × Laufzeit × Tokens für alle Kombinationen; Auswahl von max. 5 Submission-Kandidaten.

---

### Phase 5 – Logging, Robustheit, Effizienz

1. **Event-Logging** nach `cikm26/event-logging-contract/README.md`, `event_logging.py` aus `baselines/retrieval-baseline-pyterrier-smolagent/` übernehmen:
   - Pflichtfelder in jedem Event: `case_id` (= qid), `event_id`, `parent_event_id`, `timestamp`, `event_type`, `model` (nie null; ohne LLM `"-"`), `tool`, `input`, `output`, `status`, `error`.
   - Pro Query: `input` → `tool_call` (Retrieval, Rerank) → `model_call` (mit Prompt, Antwort, Token-Usage) → `observation` (Top-Dok-IDs) → abschließend `decision` (finale Top-10 mit Begründung/Noten).
   - Fehler als Event mit `status: "error"` loggen, bevor weitergemacht wird.
   - Prüfen mit dem offiziellen Evaluator: `invalid_log_lines == 0`.
   - Prompts im Log kürzen (Dokumenttexte nicht vollständig), damit die Datei klein bleibt.
2. **Zeitwächter (`budget.py`):** Startzeit festhalten; Stufen nur ausführen, wenn Restbudget reicht; bei Knappheit LLM-Rerank für restliche Queries auslassen und lexikalisch/CE-Ranking schreiben. Immer zuerst einen vollständigen lexikalischen Run schreiben, dann überschreiben.
3. **Fehlertoleranz vs. „fail loudly“:** Fehlende Env-Variablen → sofortiger Abbruch mit klarer Meldung (wie Baseline). Einzelne fehlgeschlagene LLM-Calls → Retry, dann Fallback auf vorherige Stufe **und** Error-Event. Kaputtes JSON vom Modell robust parsen.
4. **Format:** `run.txt.gz` mit `qid Q0 docno rank score tag`, pro Query bis 1000 Dokumente, keine Duplikate, absteigende Scores, jede Query vorhanden (sonst Dummy-Fallback).
5. **Ressourcen:** Speicher bei großen Collections (Dokumente streamen, nur benötigte Texte im RAM), Threads auf 4 begrenzen.

**Done:** Offizieller Evaluator läuft sauber durch; simulierte LLM-Ausfälle und künstlich knappes Zeitbudget liefern trotzdem einen gültigen Run.

---

### Phase 6 – TIRA-Submission

1. Alle Modellgewichte im Docker-Build herunterladen (`scripts/download_models.py`), Umgebung offline setzen (`HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`).
2. Lokal testen **ohne Netzwerk**: `docker run --network none …` gegen alle drei Spot-Checks.
3. Dry-Run nach Vorlage der Baseline:
   ```bash
   tira-cli code-submission \
     --path . \
     --task uniagent-2026 \
     --dataset retrieval-de-spot-check-20260816-training \
     --forward-environment-variable OPENAI_API_KEY OPENAI_BASE_URL OPENAI_MODEL \
     --command '/app/retrieve.py --dataset $inputDataset --output $outputDir --config /app/configs/full.yaml' \
     --dry-run
   ```
4. Auf allen drei Spot-Check-Datensätzen in TIRA laufen lassen und Ergebnisse gegen lokale Werte prüfen.
5. Bis zu 5 Varianten einreichen und priorisieren, z. B.:
   1. Volle Pipeline (Lexik-Fusion + Law/Dedup + CE + LLM-Rerank)
   2. Wie 1, aber LLM-Rerank nur Top-10/15 (effizient)
   3. Ohne LLM: Lexik-Fusion + Cross-Encoder
   4. Nur Lexik-Fusion + korpus-spezifische Tricks
   5. Beste Variante mit LLM-Query-Expansion
   Varianten unterscheiden sich idealerweise nur über die Config (gleiches Image, andere `--config`).

**Done:** Mindestens eine Submission am 13.10. erfolgreich in TIRA gelaufen; Rest bis 14.10.

---

### Phase 7 – Notebook Paper (Vorbereitung)

Laufend festhalten: Configs, Ablationstabellen (nDCG@10, Laufzeit, Tokens), Fehleranalyse per Query (welche Query-Typen scheitern, warum), Beispiele aus dem Log. Das macht das Paper nach dem 15.10. schnell schreibbar.

---

## 5. Experiment-Regeln

- Jeder Lauf erzeugt einen Ordner `runs/<datensatz>/<config-name>/` mit `run.txt.gz`, `run-trace.jsonl.log.gz`, `metrics.json` (Scores, Laufzeit, Tokens) und der verwendeten Config.
- Kein Parameter wird aufgrund nur eines Datensatzes gewählt.
- Signifikanz: bei gleichen Queries gepaarter t-Test oder Randomisierungstest; bei 15–25 Queries sind Unterschiede < 0.03 nDCG praktisch Rauschen.
- LLM-Antworten cachen (Hash aus Modell + Prompt), damit Wiederholungen nichts kosten; Cache nicht ins Docker-Image packen.

## 6. Risiken

| Risiko | Gegenmaßnahme |
|---|---|
| Testkorpus viel größer → Laufzeit sprengt 4 h | Budget-Wächter, Dense nur optional, zuerst lexikalischen Run schreiben |
| Kein/instabiler LLM-Zugang zum Entwickeln | Mock für Tests, Cross-Encoder-Variante ohne LLM als vollwertige Submission |
| Overfitting auf synthetische Spot-Checks | Eigenes Dev-Set, Held-out-Teil, konservative Parameterwahl |
| Intranet-Dokumente mit anderem Aufbau | Feldzugriff defensiv, keine URL-Hardcodes |
| Log ungültig → schlechter Eindruck/Abzug | Offizieller Evaluator in CI, `invalid_log_lines == 0` als Test |
| gpt-oss-20b liefert unparsebare Ausgaben | Strenges JSON-Format im Prompt, Regex-Fallback, Retry, dann Fallback-Score |

## 7. Offene Fragen (an Organisatoren bzw. Dr Aarzoo/Dr Zekun)

1. Welcher LLM-Endpoint steht uns **während der Entwicklung** zur Verfügung (TIRA-gehostet, eigener vLLM/Ollama-Server mit gpt-oss-20b, Claude-Account nur für Coding)?
2. Werden die finalen Qrels per Pooling der Teilnehmer-Runs + UMBRELA/gpt-oss-20b erzeugt? Bis zu welcher Tiefe?
3. Welche Test-Datensätze gibt es genau (weiterhin getrennt nach web-de / web-en / law-de, plus Intranet)? Wie groß sind sie ungefähr?
4. Sind die Test-Queries ebenfalls kurze Keyword-Queries mit description/narrative, oder echte Nutzeranfragen?
5. Gilt das 4-h-Limit pro Datensatz oder für alles zusammen? Wird Indexieren mitgezählt?
6. Wie wird Effizienz konkret gewichtet?

---

## 8. Vorlage für `CLAUDE.md`

```markdown
# Projekt: DAIM-Submission UniAgent 2026, Task 1 (Retrieval)

- Referenz-Repo: ../uniagent-code (nur lesen). Wichtig: cikm26/AGENTS.md-Regeln,
  cikm26/baselines/retrieval-baseline-pyterrier(-smolagent)/, cikm26/evaluation/,
  cikm26/event-logging-contract/README.md, cikm26/dataset-construction/.
- Plan: PLAN.md. Immer nur die aktuell beauftragte Phase umsetzen.
- Alles in Docker ausführen (Basis-Image uniagent-pyterrier-baseline:dev-0.0.1), kein lokales venv.
- Hauptmetrik: nDCG@10. Nach jeder Änderung: eval/compare.py auf allen drei Spot-Checks
  und dem Dev-Set laufen lassen und die Tabelle zeigen.
- Keine Parameter nur auf einem Datensatz tunen.
- Ausgabe: run.txt.gz (TREC) + run-trace.jsonl.log.gz nach Logging-Vertrag; model nie null.
- Keine Netzwerkzugriffe zur Laufzeit außer OPENAI_BASE_URL; alle Modelle im Image.
- Jede neue Stufe hinter einen Config-Schalter; Tests mit Mock-LLM in tests/.
- Keine Hardcodes auf URLs/Doc-IDs der Spot-Check-Korpora.
```

---

## 9. Prompts für Claude Code (je Phase)

**Phase 0:**
> Lies CLAUDE.md, PLAN.md (Abschnitte 1–3 und Phase 0) sowie in ../uniagent-code die Dateien AGENTS.md, cikm26/baselines/retrieval-baseline-pyterrier/ und cikm26/evaluation/. Setze Phase 0 um: Projektstruktur, Dockerfile, retrieve.py mit BM25/DPH als erste Config, eval/evaluate.py und eval/compare.py. Reproduziere die Baseline-Zahlen aus PLAN.md und zeige die Tabelle.

**Phase 1:**
> Setze Phase 1 aus PLAN.md um. Jede Variante (Query-Formulierung, Felder, Decompounding, Modelle, PRF, RRF, Passagen) als Config-Schalter. Führe die Ablationen auf allen drei Spot-Checks aus und schlage die beste Config vor. Begründe mit der Tabelle.

**Phase 2:**
> Setze Phase 2 um (law.py: Abkürzungen, §-Matching, Fassungen, Dokumenttyp-Prior; dedup.py: MinHash; Web-Priors). Alles zur Laufzeit aus der gemounteten Collection ableiten. Ablationstabelle.

**Phase 3:**
> Hilf mir, ein Dev-Set nach PLAN.md Phase 3 aufzubauen: schlage 80 Queries im Format von queries.jsonl vor (ich prüfe sie), dann Pooling mit create_pool.py und Urteile mit create_qrels.py (UMBRELA, OPENAI_*-Variablen).

**Phase 4:**
> Setze Phase 4 um. Zuerst scripts/benchmark_throughput.py auf 4 Kernen und Hochrechnung. Dann rerank_llm.py (UMBRELA-Prompt, parallel, Cache, Token-Zählung), rerank_ce.py, optional dense.py und query_expansion.py. Tabelle nDCG@10 × Laufzeit × Tokens.

**Phase 5:**
> Setze Phase 5 um: event_logging.py vertragskonform, budget.py, Fallbacks, Formatprüfung. Prüfe mit dem offiziellen Evaluator-Image, dass invalid_log_lines == 0. Teste LLM-Ausfall und knappes Zeitbudget.

**Phase 6:**
> Bereite die TIRA-Submission vor: Modelle im Image, Offline-Test mit --network none, tira-cli code-submission --dry-run für die fünf Configs aus PLAN.md Phase 6.
