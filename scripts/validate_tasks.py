"""Validate every task's grader before it is used in an experiment.

For each task:
  - reference/  (a known-good solution) MUST pass the primary grader
  - negatives/* (known-bad solutions)   MUST fail it
A grader that passes everything or nothing is the most common eval bug; this catches it.

Layout of a solution folder: workspace/ (final files), answer.txt (final answer, optional),
events.jsonl (trace, optional, for trace_check graders).

Usage:  python scripts/validate_tasks.py [task_id ...] [--with-judge]
LLM-judge tasks are skipped unless --with-judge (needs the gateway running).
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "workers"))
from evalworker.graders import GradeInput, grade_all, primary  # noqa: E402


def run(task: dict, task_dir: Path, sol: Path, with_judge: bool) -> dict | None:
    ws = sol / "workspace"
    answer = (sol / "answer.txt").read_text() if (sol / "answer.txt").exists() else ""
    events = [json.loads(l) for l in (sol / "events.jsonl").read_text().splitlines() if l.strip()] \
        if (sol / "events.jsonl").exists() else []
    with tempfile.TemporaryDirectory() as tmp:
        if not ws.exists():
            ws = Path(tmp)
        grades = grade_all(GradeInput(task, task_dir, ws, answer, events), skip_judge=not with_judge)
    return primary(grades)


def main(argv: list[str]) -> int:
    with_judge = "--with-judge" in argv
    only = [a for a in argv if not a.startswith("--")]
    failures, checked = 0, 0
    for task_dir in sorted((ROOT / "tasks").iterdir()):
        if not (task_dir / "task.yaml").exists() or (only and task_dir.name not in only):
            continue
        task = yaml.safe_load((task_dir / "task.yaml").read_text())
        ptype = next((g for g in task["graders"] if g.get("primary")), task["graders"][0])["type"]
        if ptype == "llm_judge" and not with_judge:
            print(f"SKIP  {task_dir.name:26s} (llm_judge; use --with-judge)")
            continue
        sols = [("reference", task_dir / "reference", True)] + \
               [(f"negatives/{n.name}", n, False) for n in sorted((task_dir / "negatives").glob("*"))]
        if not (task_dir / "reference").exists():
            print(f"FAIL  {task_dir.name:26s} has no reference/ solution")
            failures += 1
            continue
        if len(sols) == 1:
            print(f"WARN  {task_dir.name:26s} has no negatives/: grader is only checked one way")
        for label, sol, should_pass in sols:
            g = run(task, task_dir, sol, with_judge)
            checked += 1
            ok = g is not None and g["passed"] == should_pass
            failures += not ok
            print(f"{'ok  ' if ok else 'FAIL'}  {task_dir.name:26s} {label:28s} "
                  f"expected {'pass' if should_pass else 'fail'}, got {'pass' if g and g['passed'] else 'fail'}"
                  + ("" if ok else f"  ({g['reasoning'] if g else 'no grade'})"))
    print(f"\n{checked} solution(s) checked, {failures} problem(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
