"""Check an LLM judge against human-labelled answers.

For a task with an llm_judge primary grader, tasks/<id>/labels/labels.json holds answers with a
yes/no label per rubric criterion. This script runs the judge on every answer and reports:
  - per-criterion agreement with the labels
  - overall pass/fail agreement (pass = every "must" criterion is yes)
  - false passes: the judge passed an answer the labels fail (the dangerous direction)
and writes docs/judge-calibration.md.

Needs the gateway (GATEWAY_URL, LITELLM_MASTER_KEY, JUDGE_MODEL), like validate_tasks.py --with-judge,
or JUDGE_BACKEND=claude-cli to judge through the Claude Code CLI instead.

Usage:  python scripts/calibrate_judge.py [task_id]
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "workers"))   # lets this script import the worker's judge without installing it
# pylint: disable=wrong-import-position
from evalworker.graders import GradeInput
from evalworker.graders.llm_judge import llm_judge


def load_env() -> None:
    """Load KEY=VALUE lines from the repo's .env into the environment (existing variables win)."""
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())
    os.environ.setdefault("GATEWAY_URL", "http://localhost:4000")


def pct(agree: int, total: int) -> str:
    """Format a share as "75% (3/4)", or "n/a" when there is nothing to count."""
    return f"{100 * agree / total:.0f}% ({agree}/{total})" if total else "n/a"


def calibrate(tid: str) -> tuple[list[str], int]:
    """Run the judge over one task's labelled answers. Returns (report lines, number of answers it failed on).

    For every labelled answer the judge's per-criterion verdicts are compared with the human labels. Overall
    pass/fail follows the same rule as the grader: pass when every "must" criterion is yes. A false pass
    (judge passes what the labels fail) is the dangerous direction, since it would inflate a config's score.
    """
    task_dir = ROOT / "tasks" / tid
    task = yaml.safe_load((task_dir / "task.yaml").read_text(encoding="utf-8"))
    spec = next(g for g in task["graders"] if g.get("primary"))
    must = {c["id"] for c in spec["rubric"] if c.get("must", True)}
    items = json.loads((task_dir / "labels" / "labels.json").read_text(encoding="utf-8"))
    per = {c["id"]: [0, 0] for c in spec["rubric"]}     # criterion -> [agreements, total]
    overall = [0, 0]
    false_pass, false_fail, rows = [], [], []
    bad = 0
    judge_model = "?"
    for it in items:
        try:
            with tempfile.TemporaryDirectory() as tmp:
                g = llm_judge(GradeInput(task, task_dir, Path(tmp), it["answer"]), spec)
        except Exception as e:  # pylint: disable=broad-exception-caught  # e.g. the gateway dropped the connection
            g = {"raw": {"ungraded": True}, "reasoning": repr(e)}
        if (g.get("raw") or {}).get("ungraded"):
            print(f"judge failed on {it['id']}: {g['reasoning']}")
            bad += 1
            continue
        judge_model = g["raw"].get("judge_model", judge_model)
        got = {c["name"]: c["passed"] for c in g["raw"]["checks"]}
        diff = []
        for cid, human in it["labels"].items():
            per[cid][1] += 1
            per[cid][0] += got.get(cid) == human
            if got.get(cid) != human:
                diff.append(f"{cid}: human={'yes' if human else 'no'} judge={'yes' if got.get(cid) else 'no'}")
        h_pass = all(it["labels"][c] for c in must)
        overall[1] += 1
        overall[0] += g["passed"] == h_pass
        if g["passed"] and not h_pass:
            false_pass.append(it["id"])
        if h_pass and not g["passed"]:
            false_fail.append(it["id"])
        rows.append((it["id"], h_pass, g["passed"], "; ".join(diff) or "-"))
    lines = [f"## {tid}\n", f"Judge model: `{judge_model}`. {len(items)} answers with manual labels.\n",
             f"- **Pass/fail agreement:** {pct(*overall)}",
             f"- **False passes** (judge passed, labels fail): {len(false_pass)} {false_pass or ''}",
             f"- **False fails** (judge failed, labels pass): {len(false_fail)} {false_fail or ''}\n",
             "| Criterion | Agreement |", "|---|---|"]
    lines += [f"| {c} | {pct(*v)} |" for c, v in per.items()]
    lines += ["", "| Answer | Labels pass | Judge pass | Disagreements |", "|---|---|---|---|"]
    lines += [f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} |" for r in rows]
    print(f"{tid}: pass/fail agreement {pct(*overall)}, false passes {len(false_pass)}, "
          f"false fails {len(false_fail)}")
    for c, v in per.items():
        print(f"  {c:14s} {pct(*v)}")
    return lines, bad


def main(argv: list[str]) -> int:
    """Calibrate the named tasks (default: postmortem-from-logs) and write docs/judge-calibration.md."""
    load_env()
    ids = [a for a in argv if not a.startswith("--")] or ["postmortem-from-logs"]
    lines = [f"# Judge calibration\n\nRun {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC.\n"]
    bad = 0
    for tid in ids:
        task_lines, task_bad = calibrate(tid)
        lines += task_lines
        bad += task_bad
    (ROOT / "docs" / "judge-calibration.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
