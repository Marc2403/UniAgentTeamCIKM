#!/usr/bin/env python3
"""OpenAI-compatible stand-in that misbehaves on purpose: MODE=garbage|slow|error|truncated.

garbage: 200 with prose instead of JSON; slow: never answers within the solver's deadlines;
error: HTTP 500; truncated: JSON cut off mid-string, as at a token limit.
"""

import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MODE = os.environ.get("MODE", "garbage")
ANSWERS = {
    "garbage": "Ich kann diese Anfrage leider nicht im gewünschten Format beantworten.",
    "truncated": '{"result": "abgelehnt", "begruendung": "Die Summe der Positionen weicht',
}


class Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        if MODE == "slow":
            time.sleep(3600)
        if MODE == "error":
            self.send_response(500)
            self.end_headers()
            return
        body = json.dumps({
            "id": "mock", "object": "chat.completion", "created": 0, "model": "mock",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": ANSWERS[MODE]}, "finish_reason": "length"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


ThreadingHTTPServer(("0.0.0.0", 8000), Handler).serve_forever()
