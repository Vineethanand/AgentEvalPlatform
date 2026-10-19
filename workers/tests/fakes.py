"""Test doubles: a scripted OpenAI-compatible model server and an in-memory API."""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable


class FakeModelServer:
    """Serves /v1/chat/completions. `script(messages) -> assistant message dict` decides each reply."""

    def __init__(self, script: Callable[[list[dict]], dict]):
        """Start the server on a free local port in a background thread; ``url`` is where to point the worker."""
        self.script = script
        self.requests: list[dict] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            """Answers every POST with the next scripted message and fixed usage (100 in / 20 out tokens)."""

            def do_POST(self):  # pylint: disable=invalid-name  # name required by BaseHTTPRequestHandler
                """Read the chat request, ask the script for the reply, and send it back as chat-completions JSON."""
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

            def log_message(self, *args):  # pylint: disable=arguments-differ
                """Silence the per-request log lines."""

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        """Stop the server."""
        self.httpd.shutdown()


def tool_call(name: str, args: dict, id_: str = "c1") -> dict:
    """Build an assistant message that asks for one tool call, in the OpenAI tool-calls format."""
    return {"content": None, "tool_calls": [{"id": id_, "type": "function",
                                             "function": {"name": name, "arguments": json.dumps(args)}}]}


class FakeApi:
    """Stands in for the NestJS internal endpoints."""

    def __init__(self, trials: dict[str, dict]):
        """``trials`` maps trial id to the spec dict that GET /spec would return."""
        self.trials = trials
        self.completed: dict[str, dict] = {}
        self.event_log: dict[str, list] = {}

    def spec(self, tid):
        """Return the stored spec for the trial."""
        return self.trials[tid]

    def start(self, tid):
        """Count one more attempt for the trial and never skip it."""
        self.trials[tid]["trial"]["attempt"] += 1
        return {"skip": False, "attempt": self.trials[tid]["trial"]["attempt"]}

    def events(self, tid, _attempt, events):
        """Keep the posted trace events so tests can inspect them."""
        self.event_log.setdefault(tid, []).extend(events)

    def complete(self, tid, body):
        """Keep the posted result so tests can inspect it."""
        self.completed[tid] = body
        return {"ok": True}


class NoGateway:
    """Gateway double: no per-trial keys, so usage falls back to harness-reported tokens."""

    def __init__(self, base: str):
        """``base`` is the fake model server's URL, used as the gateway address."""
        self.base = base
        self.master = "sk-test"

    def mint_key(self, *_args, **_kwargs):
        """Refuse to create a key (the runner then uses the master key)."""
        return None

    def usage(self, *_args, **_kwargs):
        """Report no spend log, so token counts come from the harness."""
        return None

    def delete_key(self, *_args, **_kwargs):
        """Nothing to delete."""
