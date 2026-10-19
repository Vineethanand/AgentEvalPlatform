"""HTTP clients for the platform API and the LiteLLM gateway."""
from __future__ import annotations

import logging
import os
import time
from typing import Any

import requests

log = logging.getLogger(__name__)


class TrialGone(Exception):
    """The trial no longer exists (its experiment was stopped and the unstarted trials deleted)."""


class ApiClient:
    """Talks to the NestJS API's internal endpoints. Retries on network errors."""

    def __init__(self, base: str | None = None, token: str | None = None):
        self.base = (base or os.environ.get("API_URL", "http://localhost:3000")).rstrip("/")
        self.s = requests.Session()
        self.s.headers["x-internal-token"] = token or os.environ.get("INTERNAL_TOKEN", "")

    def _req(self, method: str, path: str, **kw) -> Any:
        last: Exception | None = None
        for i in range(5):
            try:
                r = self.s.request(method, f"{self.base}/internal/trials{path}", timeout=60, **kw)
                if r.status_code == 404:
                    raise TrialGone(path)
                r.raise_for_status()
                return r.json() if r.content else {}
            except requests.RequestException as e:
                last = e
                time.sleep(2 ** i)
        raise RuntimeError(f"API call failed: {method} {path}: {last}")

    def spec(self, trial_id: str) -> dict:
        return self._req("GET", f"/{trial_id}/spec")

    def start(self, trial_id: str) -> dict:
        return self._req("POST", f"/{trial_id}/start")

    def events(self, trial_id: str, attempt: int, events: list[dict]) -> None:
        for i in range(0, len(events), 200):
            self._req("POST", f"/{trial_id}/events", json={"attempt": attempt, "events": events[i:i + 200]})

    def complete(self, trial_id: str, body: dict) -> dict:
        return self._req("POST", f"/{trial_id}/complete", json=body)


class GatewayClient:
    """Per-trial virtual keys on the LiteLLM proxy.

    Each trial gets its own key with a dollar budget. After the run we read that key's
    spend logs, so token and cost numbers come from the gateway, not from the harness:
    a harness that under-reports usage cannot look cheaper.
    """

    def __init__(self, base: str | None = None, master_key: str | None = None):
        self.base = (base or os.environ.get("GATEWAY_URL", "http://localhost:4000")).rstrip("/")
        self.master = master_key or os.environ.get("LITELLM_MASTER_KEY", "")
        self.h = {"Authorization": f"Bearer {self.master}"}

    def mint_key(self, trial_id: str, model_alias: str, max_budget_usd: float) -> str | None:
        try:
            r = requests.post(f"{self.base}/key/generate", headers=self.h, timeout=20, json={
                "models": [model_alias], "max_budget": round(max_budget_usd, 4), "duration": "6h",
                "metadata": {"trial_id": trial_id},
            })
            r.raise_for_status()
            return r.json()["key"]
        except Exception as e:  # noqa: BLE001 - fall back to the master key, usage from the harness
            log.warning("could not mint gateway key (%s); using master key", e)
            return None

    def usage(self, key: str, wait_s: float = 20.0) -> dict[str, float] | None:
        """Sum the key's spend logs. LiteLLM writes logs in batches, so poll briefly."""
        deadline = time.time() + wait_s
        while True:
            try:
                r = requests.get(f"{self.base}/spend/logs", headers=self.h, params={"api_key": key}, timeout=20)
                r.raise_for_status()
                logs = r.json() or []
                if logs:
                    return {
                        "tokens_in": sum(int(x.get("prompt_tokens") or 0) for x in logs),
                        "tokens_out": sum(int(x.get("completion_tokens") or 0) for x in logs),
                        "cost_usd": sum(float(x.get("spend") or 0) for x in logs),
                        "calls": len(logs),
                    }
            except Exception as e:  # noqa: BLE001
                log.warning("spend lookup failed: %s", e)
            if time.time() > deadline:
                return None
            time.sleep(3)

    def delete_key(self, key: str) -> None:
        try:
            requests.post(f"{self.base}/key/delete", headers=self.h, json={"keys": [key]}, timeout=20)
        except Exception:  # noqa: BLE001
            pass
