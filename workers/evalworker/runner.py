"""Runs one queue job: a single trial, or a memory chain of trials in order.

Lifecycle per trial:
  start (attempt+1) -> fresh workspace from fixtures -> per-trial gateway key
  -> run harness in sandbox -> read events/result -> usage from gateway
  -> grade -> classify failure -> post events + result -> clean up key.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import time
import uuid
from pathlib import Path
from typing import Any

from .adapters.base import TrialContext
from .clients import ApiClient, GatewayClient, TrialGone
from .failure_rules import classify
from .graders import GradeInput, grade_all, primary
from .sandbox import DIRECT, make_sandbox

log = logging.getLogger(__name__)


class Runner:
    def __init__(self, api: ApiClient | None = None, gateway: GatewayClient | None = None, sandbox=None,
                 trials_dir: str | None = None, tasks_dir: str | None = None):
        self.api = api or ApiClient()
        self.gw = gateway or GatewayClient()
        self.sandbox = sandbox or make_sandbox()
        self.trials_dir = Path(trials_dir or os.environ.get("TRIALS_DIR", "./data/trials")).resolve()
        self.tasks_dir = Path(tasks_dir or os.environ.get("TASKS_DIR", "../tasks")).resolve()
        self.sandbox_gateway = os.environ.get("SANDBOX_GATEWAY_URL", self.gw.base)

    def run_job(self, trial_ids: list[str]) -> None:
        # A memory chain shares one harness home when memory mode is "carry".
        chain_home = self.trials_dir / "chains" / f"{trial_ids[0]}-{uuid.uuid4().hex[:8]}" / "home"
        for tid in trial_ids:
            try:
                self.run_trial(tid, chain_home if len(trial_ids) > 1 else None)
            except TrialGone:
                log.info("trial %s was removed (experiment stopped), skipping", tid)
            except Exception as e:  # noqa: BLE001 - mark it and move on; /resume re-runs it
                log.exception("trial %s failed with an infrastructure error", tid)
                try:
                    spec = self.api.spec(tid)
                    self.api.complete(tid, {"attempt": spec["trial"]["attempt"], "status": "infra_error",
                                            "error": repr(e), "failureCategory": "infra_error"})
                except Exception:  # noqa: BLE001
                    log.exception("could not report infra error for %s", tid)
        shutil.rmtree(chain_home.parent, ignore_errors=True)

    def run_trial(self, trial_id: str, chain_home: Path | None) -> None:
        spec = self.api.spec(trial_id)
        started = self.api.start(trial_id)
        if started.get("skip"):
            return
        attempt = started["attempt"]
        trial, task, config = spec["trial"], spec["task"], spec["config"]
        log.info("trial %s started: task %s, trial index %s, attempt %s, %s / %s", trial_id, task["id"],
                 trial.get("trialIndex"), attempt, config.get("harness"), config.get("modelAlias"))
        settings = config["settings"]
        task_dir = self.tasks_dir / task["id"]

        # Fresh trial dir: workspace = copy of fixtures; skills copied in so the sandbox needs no tasks mount.
        tdir = self.trials_dir / trial_id / f"attempt-{attempt}"
        shutil.rmtree(tdir, ignore_errors=True)
        workspace = tdir / "workspace"
        if (task_dir / "fixtures").exists():
            shutil.copytree(task_dir / "fixtures", workspace)
        else:
            workspace.mkdir(parents=True)
        skills_src = tdir / "skills_src"
        skills_src.mkdir()
        for s in settings.get("skills") or []:
            name = s.split("@")[0]
            if (self.tasks_dir / "_skills" / name).exists():
                shutil.copytree(self.tasks_dir / "_skills" / name, skills_src / name)

        memory_mode = (settings.get("memory") or {}).get("mode", "off")
        home = chain_home if (chain_home and memory_mode == "carry") else tdir / "home"
        home.mkdir(parents=True, exist_ok=True)

        snap = config.get("modelSnapshot") or {}
        p_in = float(snap.get("priceInputPerMtok") or 0) / 1e6
        p_out = float(snap.get("priceOutputPerMtok") or 0) / 1e6
        budget_usd = max(0.05, int(settings.get("max_tokens_total", 200_000)) * max(p_in, p_out) * 1.2)
        key = None if config["harness"] in DIRECT else self.gw.mint_key(trial_id, config["modelAlias"], budget_usd)

        timeout_s = int(task.get("timeout_s") or settings.get("timeout_s") or 600)
        ctx = TrialContext(
            trial_id=trial_id, attempt=attempt, prompt=task["prompt"], workspace=workspace, home=home,
            trial_dir=tdir, model=config["modelAlias"], gateway_url=self.sandbox_gateway,
            api_key="" if config["harness"] in DIRECT else (key or self.gw.master), seed=int(trial["seed"]), settings=settings,
            skills_dir=skills_src, deadline=time.time() + timeout_s,
        )
        ctx_path = tdir / "ctx.json"
        ctx.dump(ctx_path)

        t0 = time.time()
        # A carry chain shares one memory home that lives outside this trial's folder: mount just that too.
        shared = () if home.resolve().is_relative_to(tdir.resolve()) else (home,)
        outcome = self.sandbox.run(config["harness"], ctx_path, workspace, timeout_s, extra_rw=shared)
        latency_ms = int((time.time() - t0) * 1000)

        result = _read_json(tdir / "result.json") or {}
        events = _read_jsonl(tdir / "events.jsonl")
        stop_reason = "timeout" if outcome.timed_out else result.get("stop_reason", "harness_error")
        if not outcome.ok:
            status = "infra_error"
        elif stop_reason == "harness_error":
            status = "harness_error"
        else:
            status = "done"

        usage = self.gw.usage(key) if key else None
        tokens_in = usage["tokens_in"] if usage else int(result.get("tokens_in") or 0)
        tokens_out = usage["tokens_out"] if usage else int(result.get("tokens_out") or 0)
        # Cost, best source first: the gateway's spend log for this trial's key (real provider usage), then the
        # cost the harness itself reports (Claude Code CLI), then tokens x the price snapshot in the config.
        if usage and usage["cost_usd"] > 0:
            cost = usage["cost_usd"]
        elif result.get("cost_usd"):
            cost = float(result["cost_usd"])
        else:
            cost = tokens_in * p_in + tokens_out * p_out

        grades: list[dict[str, Any]] = []
        passed = None
        final_answer = result.get("final_answer", "")
        if status == "done":
            judge_prices = {"in": float(os.environ.get("JUDGE_PRICE_IN", 0.4)), "out": float(os.environ.get("JUDGE_PRICE_OUT", 1.6))}
            task_for_grading = {**task, "graders": [{**g, "_judge_prices": judge_prices} for g in task.get("graders", [])]}
            grades = grade_all(GradeInput(task_for_grading, task_dir, workspace, final_answer, events))
            p = primary(grades)
            passed = bool(p and p["passed"])
        category = classify(status=status, stop_reason=stop_reason, passed=passed, events=events, task=task,
                            grades=grades, max_steps=int(settings.get("max_steps", 25)), final_answer=final_answer)

        self.api.events(trial_id, attempt, events)
        p = primary(grades) if grades else None
        self.api.complete(trial_id, {
            "attempt": attempt, "status": status, "stopReason": stop_reason, "finalAnswer": final_answer,
            "passed": passed, "score": p["score"] if p else None,
            "tokensIn": tokens_in, "tokensOut": tokens_out, "costUsd": cost + sum(g.get("judgeCostUsd", 0) for g in grades),
            "latencyMs": latency_ms, "steps": int(result.get("steps") or 0),
            "error": result.get("error") or (None if outcome.ok else outcome.detail),
            "failureCategory": category,
            "grades": [{k: v for k, v in g.items()} for g in grades],
        })
        log.info("trial %s finished: %s, %s", trial_id, status, "PASS" if passed else "FAIL")
        if key:
            self.gw.delete_key(key)
        if os.environ.get("KEEP_TRIAL_FILES") != "1":
            shutil.rmtree(workspace, ignore_errors=True)


def _read_json(p: Path) -> dict | None:
    try:
        return json.loads(p.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def _read_jsonl(p: Path) -> list[dict]:
    if not p.exists():
        return []
    out = []
    for line in p.read_text().splitlines():
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return out
