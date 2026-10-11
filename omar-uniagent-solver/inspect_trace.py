import gzip
import json
import sys

path = sys.argv[1]
keep = {"error", "decision"}
with gzip.open(path, "rt", encoding="utf-8") as fh:
    for line in fh:
        line = line.strip()
        if not line:
            continue
        e = json.loads(line)
        if e.get("event_type") in keep:
            print(json.dumps(e, ensure_ascii=False))