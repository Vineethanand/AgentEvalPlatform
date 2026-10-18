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
    "skills": ["invoice-format"], "memory": {"mode": "off"},
}
MEMORY_TASKS = ["m1-teach-units", "m1-use-units", "m2-teach-checks", "m2-use-checks"]


def call(method: str, path: str, body=None):
    r = requests.request(method, f"{API}{path}", json=body, timeout=60)
    if not r.ok:
        sys.exit(f"{method} {path} failed: {r.status_code} {r.text}")
    return r.json()


def config(name: str, harness: str, model: str, memory: str) -> str:
    """Create the config, or add a version to an existing one with the same name. Returns the version id."""
    settings = {**BASE_SETTINGS, "memory": {"mode": memory}}
    existing = next((c for c in call("GET", "/configs") if c["name"] == name), None)
    if existing:
        return call("POST", f"/configs/{existing['id']}/versions", {"harness": harness, "modelAlias": model, "settings": settings})["id"]
    return call("POST", "/configs", {"name": name, "harness": harness, "modelAlias": model, "settings": settings})["version"]["id"]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("axis", choices=["memory", "models", "harness"])
    p.add_argument("--harness", default="hermes")
    p.add_argument("--harness-b")
    p.add_argument("--model", required=True)
    p.add_argument("--model-b")
    p.add_argument("--n", type=int, default=10)
    p.add_argument("--memory-n", type=int, default=20, help="trials for memory-chain tasks (few tasks carry the hypothesis)")
    p.add_argument("--name")
    p.add_argument("--seed", type=int, default=1234)
    a = p.parse_args()

    print("syncing tasks:", call("POST", "/tasks/sync"))
    if a.axis == "memory":
        A = config(f"{a.harness}-{a.model}-mem-off", a.harness, a.model, "off")
        B = config(f"{a.harness}-{a.model}-mem-carry", a.harness, a.model, "carry")
        hyp = "Memory on raises pass rate on the memory tasks and does not change the other tasks; it costs 10-25% more tokens."
    elif a.axis == "models":
        if not a.model_b:
            sys.exit("--model-b is required")
        A = config(f"{a.harness}-{a.model}", a.harness, a.model, "off")
        B = config(f"{a.harness}-{a.model_b}", a.harness, a.model_b, "off")
        hyp = f"{a.model_b} vs {a.model} in {a.harness}: difference in pass rate and cost."
    else:
        if not a.harness_b:
            sys.exit("--harness-b is required")
        A = config(f"{a.harness}-{a.model}", a.harness, a.model, "off")
        B = config(f"{a.harness_b}-{a.model}", a.harness_b, a.model, "off")
        hyp = f"{a.harness_b} vs {a.harness} with {a.model}: difference in pass rate and cost."

    overrides = {t: a.memory_n for t in MEMORY_TASKS} if a.axis == "memory" else {}
    res = call("POST", "/experiments", {
        "name": a.name or f"{a.axis}: A vs B", "hypothesis": hyp, "configVersionIds": [A, B],
        "nTrials": a.n, "nOverrides": overrides, "seed": a.seed,
    })
    print(f"launched experiment {res['experiment']['id']} with {res['trials']} trials")
    print(f"open http://localhost:5173/experiments/{res['experiment']['id']}")


if __name__ == "__main__":
    main()
