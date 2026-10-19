"""Create two configs that differ on ONE axis and launch an experiment, via the API.

Examples
  # Hermes memory off vs carry (the report experiment)
  python scripts/run_experiment.py memory --harness hermes --model claude-sonnet --n 10

  # Same harness, two models
  python scripts/run_experiment.py models --harness hermes --model claude-sonnet --model-b qwen-open --n 10

  # Same model, two harnesses
  python scripts/run_experiment.py harness --harness baseline --harness-b hermes --model claude-sonnet --n 10

  # Small pilot first (N=3) to measure variance and token use
  python scripts/run_experiment.py memory --harness hermes --model gpt-mini --n 3 --name pilot

  # See which tasks the platform supports
  python scripts/run_experiment.py --list-tasks

  # Run only some tasks (unknown names are skipped with a warning; if none are known it exits with an error)
  python scripts/run_experiment.py models --harness hermes --model claude-haiku --model-b gpt-mini \
      --tasks csv-aggregate tile-defect
"""
from __future__ import annotations

import argparse
import os
import sys

import requests

API = os.environ.get("API_URL", "http://localhost:3000").rstrip("/")
BASE_SETTINGS = {
    "temperature": 0.7, "max_steps": 25, "max_tokens_total": 200000, "timeout_s": 600,
    "tools": ["bash", "read_file", "write_file", "list_dir"],
    "skills": ["invoice-format", "changelog-format"], "memory": {"mode": "off"},
}
# Tasks that form memory chains (teach then use). Only a few tasks carry the memory hypothesis, so they get
# their own, larger trial count (--memory-n) when the experiment varies memory.
MEMORY_TASKS = ["m1-teach-units", "m1-use-units", "m2-teach-checks", "m2-use-checks", "m3-teach-ids", "m3-use-ids"]


def call(method: str, path: str, body=None):
    """Call the platform API and return the parsed JSON; exit with the server's message on an error status."""
    r = requests.request(method, f"{API}{path}", json=body, timeout=60)
    if not r.ok:
        sys.exit(f"{method} {path} failed: {r.status_code} {r.text}")
    return r.json()


def supported_tasks() -> dict[str, dict]:
    """Task id -> task row, for every task the platform currently knows about."""
    return {t["id"]: t for t in call("GET", "/tasks")}


def print_tasks(tasks: dict[str, dict]) -> None:
    """Print one line per task: id, title and tags, with the ids padded to line up."""
    width = max((len(i) for i in tasks), default=0)
    print(f"{len(tasks)} supported task(s):")
    for tid, t in sorted(tasks.items()):
        print(f"  {tid:<{width}}  {t.get('title', '')}  [{', '.join(t.get('tags') or [])}]")


def select_tasks(requested: list[str], tasks: dict[str, dict]) -> list[str]:
    """Keep the supported names (in the order given, no repeats). Warn about the rest; exit if nothing is left."""
    names = list(dict.fromkeys(n.strip() for item in requested for n in item.split(",") if n.strip()))
    known = [n for n in names if n in tasks]
    unknown = [n for n in names if n not in tasks]
    if not known:
        sys.exit(f"error: none of the requested tasks are supported: {', '.join(unknown)}. "
                 "Run with --list-tasks to see the supported tasks.")
    if unknown:
        print(f"warning: these tasks are not supported and will not run: {', '.join(unknown)}. "
              f"Running the rest: {', '.join(known)}", file=sys.stderr)
    return known


def config(name: str, harness: str, model: str, memory: str) -> str:
    """Create the config, or add a version to an existing one with the same name. Returns the version id.

    Reusing a name adds a new version instead of a duplicate config, so repeated runs of this script keep one
    config per setup and its history shows in the UI.
    """
    settings = {**BASE_SETTINGS, "memory": {"mode": memory}}
    existing = next((c for c in call("GET", "/configs") if c["name"] == name), None)
    body = {"harness": harness, "modelAlias": model, "settings": settings}
    if existing:
        return call("POST", f"/configs/{existing['id']}/versions", body)["id"]
    return call("POST", "/configs", {"name": name, **body})["version"]["id"]


def parse_args() -> tuple[argparse.ArgumentParser, argparse.Namespace]:
    """Define and parse the command line. Returns the parser too, so main() can report usage errors."""
    p = argparse.ArgumentParser()
    p.add_argument("axis", nargs="?", choices=["memory", "models", "harness"])
    p.add_argument("--harness", default="hermes")
    p.add_argument("--harness-b")
    p.add_argument("--model")
    p.add_argument("--model-b")
    p.add_argument("--n", type=int, default=10)
    p.add_argument("--memory-n", type=int, default=20,
                   help="trials for memory-chain tasks (few tasks carry the hypothesis)")
    p.add_argument("--name")
    p.add_argument("--seed", type=int, default=1234)
    p.add_argument("--tasks", nargs="+", metavar="TASK",
                   help="run only these task ids (space or comma separated); default is all tasks")
    p.add_argument("--list-tasks", action="store_true", help="print the supported tasks and exit")
    return p, p.parse_args()


def build_configs(a: argparse.Namespace) -> tuple[str, str, str]:
    """Create configs A and B for the chosen axis. Returns (version id A, version id B, hypothesis text).

    The two configs differ only on the axis being tested, which is what makes the comparison fair.
    """
    if a.axis == "memory":
        cfg_a = config(f"{a.harness}-{a.model}-mem-off", a.harness, a.model, "off")
        cfg_b = config(f"{a.harness}-{a.model}-mem-carry", a.harness, a.model, "carry")
        hyp = ("Memory on raises pass rate on the memory tasks and does not change the other tasks; "
               "it costs 10-25% more tokens.")
    elif a.axis == "models":
        if not a.model_b:
            sys.exit("--model-b is required")
        cfg_a = config(f"{a.harness}-{a.model}", a.harness, a.model, "off")
        cfg_b = config(f"{a.harness}-{a.model_b}", a.harness, a.model_b, "off")
        hyp = f"{a.model_b} vs {a.model} in {a.harness}: difference in pass rate and cost."
    else:
        if not a.harness_b:
            sys.exit("--harness-b is required")
        cfg_a = config(f"{a.harness}-{a.model}", a.harness, a.model, "off")
        cfg_b = config(f"{a.harness_b}-{a.model}", a.harness_b, a.model, "off")
        hyp = f"{a.harness_b} vs {a.harness} with {a.model}: difference in pass rate and cost."
    return cfg_a, cfg_b, hyp


def main() -> None:
    """Sync tasks, then either list them or create the two configs and launch the experiment."""
    p, a = parse_args()

    print("syncing tasks:", call("POST", "/tasks/sync"))
    tasks = supported_tasks()
    if a.list_tasks:
        print_tasks(tasks)
        return
    if not a.axis or not a.model:
        p.error("axis and --model are required (or use --list-tasks)")
    task_ids = select_tasks(a.tasks, tasks) if a.tasks else None
    cfg_a, cfg_b, hyp = build_configs(a)

    # Per-task trial counts: memory-chain tasks get --memory-n trials when memory is the axis under test.
    overrides = {t: a.memory_n for t in MEMORY_TASKS if task_ids is None or t in task_ids} \
        if a.axis == "memory" else {}
    res = call("POST", "/experiments", {
        "name": a.name or f"{a.axis}: A vs B", "hypothesis": hyp, "configVersionIds": [cfg_a, cfg_b],
        "nTrials": a.n, "nOverrides": overrides, "seed": a.seed,
        **({"taskIds": task_ids} if task_ids else {}),
    })
    print(f"launched experiment {res['experiment']['id']} with {res['trials']} trials")
    print(f"open http://localhost:5173/experiments/{res['experiment']['id']}")


if __name__ == "__main__":
    main()
