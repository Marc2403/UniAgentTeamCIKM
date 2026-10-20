# Projekt: DAIM-Submission UniAgent 2026, Task 1 (Retrieval)

- Referenz-Repo: ../uniagent-code (nur lesen). Wichtig: AGENTS.md-Regeln,
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
