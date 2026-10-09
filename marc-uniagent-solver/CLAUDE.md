# Projekt: UniAgent 2026 Task 2 (Solving) – DAIM-Team, University of Hull

## Ziel
Agent, der Verwaltungsfälle der Uni Kassel (Dienstreiseantrag, Beschaffungsantrag,
Auslagenerstattung) als `angenommen`/`abgelehnt` entscheidet. Metrik: Accuracy, dazu Effizienz.
Abgabe via TIRA bis 20.10.2026 AoE. Plan: PLAN.md. Ergebnisse: RESULTS.md.

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
- Alles in Docker testen (scripts/docker-run.sh, scripts/run_all_spot_checks.sh).
- Nach jeder Änderung an der Entscheidungslogik: alle 3 Spot-Checks laufen lassen,
  Ergebnis in RESULTS.md eintragen.
- Deutsche Zahlen-/Datumsformate beachten (2.667,00 €, 20.10.2026).
- Pseudonymisierungsspuren (PLZ, ungültige IBAN, Schwärzungen) entscheiden nie einen Fall.
- Dateien mit LF-Zeilenenden speichern (TIRA startet `/app/predict.py` über das Shebang).
