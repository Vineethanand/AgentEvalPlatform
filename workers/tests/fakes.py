"""Test doubles: a scripted OpenAI-compatible model server and an in-memory API."""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable


class FakeModelServer:
    """Serves /v1/chat/completions. `script(messages) -> assistant message dict` decides each reply."""

    def __init__(self, script: Callable[[list[dict]], dict]):
        self.script = script
        self.requests: list[dict] = []
        outer = self

        class H(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                outer.requests.append(body)
                msg = outer.script(body["messages"])
                out = {"choices": [{"message": {"role": "assistant", **msg}}],
                       "usage": {"prompt_tokens": 100, "completion_tokens": 20}}
                data = json.dumps(out).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *a):
                pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()


def tool_call(name: str, args: dict, id_: str = "c1") -> dict:
    return {"content": None, "tool_calls": [{"id": id_, "type": "function",
                                             "function": {"name": name, "arguments": json.dumps(args)}}]}


class FakeApi:
    """Stands in for the NestJS internal endpoints."""

    def __init__(self, trials: dict[str, dict]):
        self.trials = trials          # trial_id -> spec dict as GET /spec returns it
        self.completed: dict[str, dict] = {}
        self.event_log: dict[str, list] = {}

    def spec(self, tid):
        return self.trials[tid]

    def start(self, tid):
        self.trials[tid]["trial"]["attempt"] += 1
        return {"skip": False, "attempt": self.trials[tid]["trial"]["attempt"]}

    def events(self, tid, attempt, events):  # noqa: F811 - method name mirrors ApiClient
        self.event_log.setdefault(tid, []).extend(events)

    def complete(self, tid, body):
        self.completed[tid] = body
        return {"ok": True}


class NoGateway:
    """Gateway double: no per-trial keys, so usage falls back to harness-reported tokens."""

    def __init__(self, base: str):
        self.base = base
        self.master = "sk-test"

    def mint_key(self, *a, **k):
        return None

    def usage(self, *a, **k):
        return None

    def delete_key(self, *a, **k):
        pass
