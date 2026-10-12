# Team solver – UniAgent 2026, Task 2 (Solving)

Work in progress on branch `team-mvp`. Base: Marc's MVP (`../marc-uniagent-solver/`), chosen in
[`../evaluation/EVALUATION.md`](../evaluation/EVALUATION.md), plus compliance fixes: per-case watchdog,
deadline-aware PDF reading, a prediction for every case directory (also without PDFs), and the
`decision`/`answer`/`evidence` fields of the event-logging contract on every decision event.

```bash
docker build --tag team-solver .      # runs the tests
OPENAI_BASE_URL=... OPENAI_API_KEY=... OPENAI_MODEL=... \
  ../evaluation/run-mvp.sh team team-solver ../evaluation/runs/team bridge -- python3 /app/predict.py
```
