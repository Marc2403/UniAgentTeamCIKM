#!/usr/bin/env python3
"""Split one mixed run for the official evaluator; write local development results."""
import csv
import gzip
import json
import os
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parent
run_name = os.environ.get('RUN_NAME', 'local-qwen-3b-pipeline-06')
run = root / 'runs' / run_name
rows = [json.loads(line) for line in (run/'predictions.jsonl').read_text().splitlines()]
with gzip.open(run/'run-trace.jsonl.log.gz', 'rt') as stream:
    events = [json.loads(line) for line in stream]
summaries = []
for dataset, prefix in [('business-trip-spot-check', 'dienstreiseantrag-'), ('task-2-expense-reimbursement-spot-check', 'auslagenerstattung-'), ('task-2-procurement-spot-check', 'beschaffungsantrag-')]:
    dest = run/dataset
    dest.mkdir(exist_ok=True)
    selected = sorted((row for row in rows if row['antrag'].startswith(prefix)), key=lambda row: row['antrag'])
    truths = {row['antrag']: row['result'] for row in map(json.loads,
        (root/'cikm26'/'datasets'/dataset/'ground-truth.jsonl').read_text().splitlines())}
    if len(selected) != len(truths) or {row['antrag'] for row in selected} != set(truths):
        raise RuntimeError(f'{dataset}: missing, duplicate or unexpected application IDs')
    id_accuracy = sum(row['result'] == truths[row['antrag']] for row in selected) / len(selected)
    (dest/'predictions.jsonl').write_text(''.join(json.dumps(row, ensure_ascii=False)+'\n' for row in selected))
    with gzip.open(dest/'run-trace.jsonl.log.gz', 'wt') as stream:
        for event in events:
            if event['case_id'].startswith(prefix):
                stream.write(json.dumps(event, ensure_ascii=False)+'\n')
    docker = os.environ.get('DOCKER_CLI', '/Applications/Docker.app/Contents/Resources/bin/docker')
    report = subprocess.run([docker,'run','--rm','--volume',f'{dest}:/predictions:ro','--volume',f'{root}/cikm26/datasets/{dataset}:/truths:ro','gareth-uniagent-evaluator','--predictions','/predictions','--task','solving','--truths','/truths'],check=True,capture_output=True,text=True)
    decoder = json.JSONDecoder()
    metrics = None
    for position, character in enumerate(report.stdout):
        if character == '{':
            try:
                candidate, _ = decoder.raw_decode(report.stdout[position:])
            except json.JSONDecodeError:
                continue
            if isinstance(candidate, dict) and 'accuracy' in candidate:
                metrics = candidate
                break
    if metrics is None:
        raise RuntimeError(f'No evaluator metrics in output: {report.stdout}')
    if abs(metrics['accuracy'] - id_accuracy) > 1e-9:
        raise RuntimeError(f'{dataset}: evaluator accuracy disagrees with ID-matched labels')
    (dest/'evaluation.json').write_text(json.dumps(metrics, indent=2))
    errors = sum(event['event_type']=='decision' and event['status']=='error' for event in events if event['case_id'].startswith(prefix))
    summaries.append(dict(dataset=dataset,cases=len(selected),decision_errors=errors,**metrics))
(run/'summary.json').write_text(json.dumps(summaries,indent=2))
(root/'results').mkdir(exist_ok=True)
with (root/'results'/f'{run_name}.csv').open('w') as stream:
    fields=['run','build_assistant','runtime_model','dataset','cases','accuracy','invalid_log_lines','decision_errors']
    writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
    for row in summaries:
        writer.writerow(dict(run=run_name,build_assistant='ChatGPT Codex',runtime_model=row['model'],**{key:row[key] for key in fields[3:]}))
print(json.dumps(summaries,indent=2))
