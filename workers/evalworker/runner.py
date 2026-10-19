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
    """Executes trials end to end. All collaborators are injectable so tests can use fakes."""

    def __init__(self, api: ApiClient | None = None, gateway: GatewayClient | None = None, sandbox=None,
                 trials_dir: str | None = None, tasks_dir: str | None = None):
        """Use the given collaborators, or build real ones from environment variables."""
        self.api = api or ApiClient()
        self.gw = gateway or GatewayClient()
        self.sandbox = sandbox or make_sandbox()
        self.trials_dir = Path(trials_dir or os.environ.get("TRIALS_DIR", "./data/trials")).resolve()
        self.tasks_dir = Path(tasks_dir or os.environ.get("TASKS_DIR", "../tasks")).resolve()
        self.sandbox_gateway = os.environ.get("SANDBOX_GATEWAY_URL", self.gw.base)

    def run_job(self, trial_ids: list[str]) -> None:
        """Run the trials of one queue job in order.

        A job with several trials is a memory chain (teach task, then use task). They share one harness home
        folder, which is only actually used when the config's memory mode is "carry", and which is deleted when
        the chain ends. A failure in one trial is recorded as an infrastructure error and the chain continues.
        """
        chain_home = self.trials_dir / "chains" / f"{trial_ids[0]}-{uuid.uuid4().hex[:8]}" / "home"
        for tid in trial_ids:
            try:
                self.run_trial(tid, chain_home if len(trial_ids) > 1 else None)
            except TrialGone:
                log.info("trial %s was removed (experiment stopped), skipping", tid)
            except Exception as e:  # pylint: disable=broad-exception-caught  # mark it and move on; /resume re-runs it
                log.exception("trial %s failed with an infrastructure error", tid)
                try:
                    spec = self.api.spec(tid)
                    self.api.complete(tid, {"attempt": spec["trial"]["attempt"], "status": "infra_error",
                                            "error": repr(e), "failureCategory": "infra_error"})
                except Exception:  # pylint: disable=broad-exception-caught
                    log.exception("could not report infra error for %s", tid)
        shutil.rmtree(chain_home.parent, ignore_errors=True)

    def _prepare_folders(self, task: dict, settings: dict, tdir: Path) -> tuple[Path, Path]:
        """Create the trial's fresh workspace and skills folder. Returns (workspace, skills_src).

        The workspace is built in layers: the task's shared fixtures (``fixtures_from``) first, then the task's own
        ``fixtures/`` on top, so a task can override a shared file. Skills are copied into the trial folder so the
        sandbox only needs to mount that folder, not the whole tasks directory.
        """
        shutil.rmtree(tdir, ignore_errors=True)
        workspace = tdir / "workspace"
        workspace.mkdir(parents=True)
        if task.get("fixtures_from"):
            shutil.copytree(self.tasks_dir / task["fixtures_from"], workspace, dirs_exist_ok=True)
        if (self.tasks_dir / task["id"] / "fixtures").exists():
            shutil.copytree(self.tasks_dir / task["id"] / "fixtures", workspace, dirs_exist_ok=True)
        skills_src = tdir / "skills_src"
        skills_src.mkdir()
        for s in settings.get("skills") or []:
            name = s.split("@")[0]  # "name@version" -> "name"
            if (self.tasks_dir / "_skills" / name).exists():
                shutil.copytree(self.tasks_dir / "_skills" / name, skills_src / name)
        return workspace, skills_src

    @staticmethod
    def _cost(usage: dict | None, result: dict, tokens_in: int, tokens_out: int, p_in: float, p_out: float) -> float:
        """Cost of the model calls, using the best source that has data.

        1. the gateway's spend log for this trial's key (real provider usage, priced by the provider);
        2. the cost the harness reports itself (the Claude Code CLI's ``total_cost_usd``);
        3. tokens times the price snapshot stored with the config (an estimate; the only source when there is
           no API credit, which is what makes cost figures from local models and Claude Code approximate).
        ``p_in`` / ``p_out`` are prices in USD per single token.
        """
        if usage and usage["cost_usd"] > 0:
            return usage["cost_usd"]
        if result.get("cost_usd"):
            return float(result["cost_usd"])
        return tokens_in * p_in + tokens_out * p_out

    @staticmethod
    def _grade(task: dict, task_dir: Path, workspace: Path, final_answer: str,
               events: list[dict]) -> tuple[list[dict[str, Any]], bool]:
        """Run every grader on the finished trial. Returns (grades, passed), where passed is the primary verdict.

        The judge's token prices are attached to each grader spec (as ``_judge_prices``) so an LLM judge can
        report what its own calls cost; they come from environment variables because the judge model is not
        part of the config under test.
        """
        judge_prices = {"in": float(os.environ.get("JUDGE_PRICE_IN", 0.4)),
                        "out": float(os.environ.get("JUDGE_PRICE_OUT", 1.6))}
        task_for_grading = {**task, "graders": [{**g, "_judge_prices": judge_prices} for g in task.get("graders", [])]}
        grades = grade_all(GradeInput(task_for_grading, task_dir, workspace, final_answer, events))
        p = primary(grades)
        return grades, bool(p and p["passed"])

    def run_trial(self, trial_id: str, chain_home: Path | None) -> None:  # pylint: disable=too-many-locals
        """Run one trial from "queued" to a posted result. Raises on infrastructure problems.

        Steps: fetch the spec and claim the trial (a stopped experiment makes this skip it), build the workspace,
        mint a budget-capped gateway key, start the sandbox, read back what the harness wrote, compute usage and
        cost, grade, classify the failure, and post the events and the result to the API.
        """
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
        direct = config["harness"] in DIRECT   # harnesses that bypass the gateway (no key, no spend log)

        tdir = self.trials_dir / trial_id / f"attempt-{attempt}"
        workspace, skills_src = self._prepare_folders(task, settings, tdir)

        # Memory: in "carry" mode every trial of a chain uses the chain's shared home; otherwise a private one.
        memory_mode = (settings.get("memory") or {}).get("mode", "off")
        home = chain_home if (chain_home and memory_mode == "carry") else tdir / "home"
        home.mkdir(parents=True, exist_ok=True)

        # Per-trial gateway key. Its dollar budget is the worst case for max_tokens_total tokens at the dearer of
        # the two prices, plus 20 % headroom, with a 5 cent floor so free models still get a usable key.
        snap = config.get("modelSnapshot") or {}
        p_in = float(snap.get("priceInputPerMtok") or 0) / 1e6
        p_out = float(snap.get("priceOutputPerMtok") or 0) / 1e6
        budget_usd = max(0.05, int(settings.get("max_tokens_total", 200_000)) * max(p_in, p_out) * 1.2)
        key = None if direct else self.gw.mint_key(trial_id, config["modelAlias"], budget_usd)

        timeout_s = int(task.get("timeout_s") or settings.get("timeout_s") or 600)
        ctx = TrialContext(
            trial_id=trial_id, attempt=attempt, prompt=task["prompt"], workspace=workspace, home=home,
            trial_dir=tdir, model=config["modelAlias"], gateway_url=self.sandbox_gateway,
            api_key="" if direct else (key or self.gw.master), seed=int(trial["seed"]), settings=settings,
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
            status = "infra_error"       # the sandbox itself failed (could not start, killed, ...)
        elif stop_reason == "harness_error":
            status = "harness_error"     # the harness ran but crashed or could not reach the model
        else:
            status = "done"

        # Token counts: the gateway's numbers win over the harness's own, so a harness cannot under-report.
        usage = self.gw.usage(key) if key else None
        tokens_in = usage["tokens_in"] if usage else int(result.get("tokens_in") or 0)
        tokens_out = usage["tokens_out"] if usage else int(result.get("tokens_out") or 0)
        cost = self._cost(usage, result, tokens_in, tokens_out, p_in, p_out)

        grades: list[dict[str, Any]] = []
        passed = None
        final_answer = result.get("final_answer", "")
        if status == "done":   # a trial that never ran properly is not graded
            grades, passed = self._grade(task, task_dir, workspace, final_answer, events)
        category = classify(status=status, stop_reason=stop_reason, passed=passed, events=events, task=task,
                            grades=grades, max_steps=int(settings.get("max_steps", 25)), final_answer=final_answer)

        self.api.events(trial_id, attempt, events)
        p = primary(grades) if grades else None
        self.api.complete(trial_id, {
            "attempt": attempt, "status": status, "stopReason": stop_reason, "finalAnswer": final_answer,
            "passed": passed, "score": p["score"] if p else None,
            "tokensIn": tokens_in, "tokensOut": tokens_out,
            "costUsd": cost + sum(g.get("judgeCostUsd", 0) for g in grades),
            "latencyMs": latency_ms, "steps": int(result.get("steps") or 0),
            "error": result.get("error") or (None if outcome.ok else outcome.detail),
            "failureCategory": category,
            "grades": [dict(g) for g in grades],
        })
        log.info("trial %s finished: %s, %s", trial_id, status, "PASS" if passed else "FAIL")
        if key:
            self.gw.delete_key(key)
        if os.environ.get("KEEP_TRIAL_FILES") != "1":
            shutil.rmtree(workspace, ignore_errors=True)


def _read_json(p: Path) -> dict | None:
    """Parse a JSON file, or return None if it is missing or malformed (the sandbox may have died before writing)."""
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _read_jsonl(p: Path) -> list[dict]:
    """Read a JSON-lines file, skipping unparseable lines (a killed process can leave a half-written last line)."""
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return out
