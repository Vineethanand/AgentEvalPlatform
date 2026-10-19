"""Minimal OpenAI-compatible chat client (stdlib only, runs inside the sandbox).

Every model is reached through the gateway with the same request shape, so no
harness contains provider-specific code.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any

# HTTP statuses worth retrying: request timeout, rate limit, and transient server/gateway errors.
RETRYABLE_STATUSES = (408, 429, 500, 502, 503, 504)


class LLMError(RuntimeError):
    """The gateway call failed for good (a non-retryable HTTP error, or the retries ran out)."""


def chat(base_url: str, api_key: str, model: str, messages: list[dict], tools: list[dict] | None = None,
         temperature: float = 0.7, seed: int | None = None, timeout: float = 120.0,
         retries: int = 3) -> dict[str, Any]:
    """POST one chat-completions request to the gateway and return the parsed JSON response.

    Retries with exponential backoff (1 s, 2 s, 4 s, ... capped at 30 s) on rate limits, timeouts and server
    errors. Any other HTTP error (bad key, bad request) is raised at once, since retrying cannot help.
    """
    body: dict[str, Any] = {"model": model, "messages": messages, "temperature": temperature}
    if tools:
        body["tools"] = tools
        body["tool_choice"] = "auto"
    if seed is not None:
        body["seed"] = seed
    data = json.dumps(body).encode()
    url = base_url.rstrip("/") + "/v1/chat/completions"
    last: Exception | None = None
    for i in range(retries + 1):
        req = urllib.request.Request(url, data=data, method="POST", headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        })
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:500]
            last = LLMError(f"HTTP {e.code}: {detail}")
            if e.code not in RETRYABLE_STATUSES:
                raise last from e
        except (urllib.error.URLError, TimeoutError) as e:
            last = LLMError(str(e))
        time.sleep(min(30, 2 ** i))
    raise last or LLMError("unknown error")
