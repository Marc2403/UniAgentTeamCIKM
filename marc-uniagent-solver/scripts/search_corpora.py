#!/usr/bin/env python3
"""Search the retrieval corpora of an input directory, to find rule sources for knowledge/*.yaml.

Example: scripts/search_corpora.py --input /data/task-2-procurement-spot-check/inputs "Rahmenvertrag Monitore"
         scripts/search_corpora.py --input ... --show university-kassel-public-de:<doc_id>
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from solver.discovery import discover_corpora  # noqa: E402
from solver.retrieval import Retriever  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--k", type=int, default=8)
    parser.add_argument("--corpus", action="append", help="restrict to these corpora")
    parser.add_argument("--show", action="append", default=[], help="corpus:doc_id to print in full")
    parser.add_argument("queries", nargs="*")
    args = parser.parse_args()

    started = time.monotonic()
    retriever = Retriever.build(discover_corpora(args.input))
    print(f"# index built in {time.monotonic() - started:.1f} s", flush=True)
    for query in args.queries:
        print(f"\n## {query}")
        for hit in retriever.search(query, args.k, args.corpus):
            print(f"{hit.score:7.2f} {hit.corpus}:{hit.doc_id} | {hit.title[:80]} | {hit.url}\n        {hit.passage[:300]}")
    for reference in args.show:
        corpus, doc_id = reference.split(":", 1)
        document = retriever.get(corpus, doc_id)
        print(f"\n## {reference}\n{document.get('title')}\n{document.get('url')}\n{document.get('text') or document.get('content')}" if document else f"\n## {reference}: not found")


if __name__ == "__main__":
    main()
