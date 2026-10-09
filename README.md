# UniAgent Team CIKM – MVP-Vergleich

Jedes Teammitglied legt sein MVP in einen eigenen Ordner `<name>-<projekt>/` im Repo-Root.
Jeder Ordner ist eigenständig (eigene README, Abhängigkeiten, `.gitignore`).

| Ordner | Autor | Ansatz |
|---|---|---|
| [`marc-uniagent-solver/`](marc-uniagent-solver/) | Marc M (@Marc2403) | Task 2 (Solving): LLM extrahiert, Python prüft Regeln, LLM entscheidet; BM25-Retrieval. Ergebnisse: [`RESULTS.md`](marc-uniagent-solver/RESULTS.md) |

## Eigenes MVP hinzufügen

1. Repo klonen und Branch anlegen: `git checkout -b <name>-mvp`
2. MVP nach `<name>-<projekt>/` kopieren, ohne Secrets (`.env`, API-Keys) und Laufartefakte
3. Zeile in der Tabelle oben ergänzen
4. Pushen und Pull Request gegen `main` öffnen
