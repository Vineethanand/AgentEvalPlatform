"""Deterministic graders: exact_match, unit_test, state_check, trace_check."""
from __future__ import annotations

import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from . import GradeInput


def _result(checks: list[dict[str, Any]]) -> dict[str, Any]:
    """All 'must' checks must pass; score = share of checks passed."""
    must = [c for c in checks if c.get("must", True)]
    passed = all(c["passed"] for c in must) if must else False
    score = sum(c["passed"] for c in checks) / len(checks) if checks else 0.0
    failed = [f"{c['name']}: {c.get('detail', '')}".strip() for c in checks if not c["passed"]]
    return {"score": score, "passed": passed,
            "reasoning": "all checks passed" if not failed else "failed: " + "; ".join(failed),
            "raw": {"checks": checks}}


# ---------------------------------------------------------------- exact_match
def _normalise(s: str, steps: list[str]) -> str:
    s = s or ""
    if "last_line" in steps:
        lines = [x for x in s.strip().splitlines() if x.strip()]
        s = lines[-1] if lines else ""
    if "trim" in steps:
        s = s.strip()
    if "lower" in steps:
        s = s.lower()
    if "strip_punct" in steps:
        s = re.sub(r"[^\w\s.,-]", "", s).strip(" .")
    if "collapse_ws" in steps:
        s = re.sub(r"\s+", " ", s)
    return s


def exact_match(inp: "GradeInput", spec: dict[str, Any]) -> dict[str, Any]:
    """spec: expected (str or list of accepted strings), normalize (list), mode: equals | contains | number"""
    steps = spec.get("normalize", ["trim", "lower", "collapse_ws"])
    mode = spec.get("mode", "equals")
    answer = _normalise(inp.final_answer, steps)
    expected = spec["expected"] if isinstance(spec["expected"], list) else [spec["expected"]]
    ok = False
    if mode == "number":
        tol = float(spec.get("tolerance", 1e-6))
        nums = [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", answer.replace(",", ""))]
        ok = any(abs(n - float(e)) <= tol for n in nums for e in expected)
    else:
        for e in expected:
            e2 = _normalise(str(e), steps)
            ok = ok or (e2 in answer if mode == "contains" else answer == e2)
    return _result([{"name": f"answer {mode} expected", "passed": ok,
                     "detail": "" if ok else f"got {answer[:120]!r}, expected one of {expected}"}])


# ---------------------------------------------------------------- unit_test
def unit_test(inp: "GradeInput", spec: dict[str, Any]) -> dict[str, Any]:
    """Copies hidden tests (grader/tests by default) next to a COPY of the workspace and runs unittest.
    The agent never saw these tests."""
    tests_dir = inp.task_dir / spec.get("tests", "grader/tests")
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / "ws"
        shutil.copytree(inp.workspace, work)
        shutil.copytree(tests_dir, work / "_hidden_tests")
        p = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "_hidden_tests", "-t", "."],
                           cwd=work, capture_output=True, text=True, timeout=int(spec.get("timeout_s", 120)))
    out = p.stderr + p.stdout
    m = re.search(r"Ran (\d+) tests?", out)
    ran = int(m.group(1)) if m else 0
    fails = re.search(r"FAILED \((?:failures=(\d+))?(?:, )?(?:errors=(\d+))?", out)
    bad = (int(fails.group(1) or 0) + int(fails.group(2) or 0)) if fails else (0 if p.returncode == 0 else ran or 1)
    checks = [{"name": "all hidden tests pass", "passed": p.returncode == 0 and ran > 0,
               "detail": f"{ran - bad}/{ran} passed" + ("" if p.returncode == 0 else f"\n{out[-1500:]}")}]
    res = _result(checks)
    res["score"] = (ran - bad) / ran if ran else 0.0
    return res


# ---------------------------------------------------------------- state_check
def state_check(inp: "GradeInput", spec: dict[str, Any]) -> dict[str, Any]:
    """Runs the task's own check script: def check(workspace: Path, final_answer: str) -> list[dict]
    Each dict: {name, passed, detail?, must? (default True)}."""
    script = inp.task_dir / spec.get("script", "grader/check.py")
    mod_name = f"_check_{inp.task.get('id', 'task').replace('-', '_')}"
    s = importlib.util.spec_from_file_location(mod_name, script)
    mod = importlib.util.module_from_spec(s)
    assert s and s.loader
    s.loader.exec_module(mod)
    return _result(mod.check(Path(inp.workspace), inp.final_answer or ""))


# ---------------------------------------------------------------- trace_check
def trace_check(inp: "GradeInput", spec: dict[str, Any]) -> dict[str, Any]:
    """Assertions about what the agent DID, read from the normalised trace.
    spec.assert: list of {tool_used: name} | {tool_not_used: name} | {event: type}
                 | {command_contains: text} (any bash command containing text)"""
    calls = [e for e in inp.events if e.get("type") == "tool_call"]
    tool_names = [e["payload"].get("tool") for e in calls]
    checks = []
    for a in spec.get("assert", []):
        if "tool_used" in a:
            ok = a["tool_used"] in tool_names
            checks.append({"name": f"used tool {a['tool_used']}", "passed": ok})
        elif "tool_not_used" in a:
            ok = a["tool_not_used"] not in tool_names
            checks.append({"name": f"did not use {a['tool_not_used']}", "passed": ok})
        elif "event" in a:
            ok = any(e.get("type") == a["event"] for e in inp.events)
            checks.append({"name": f"trace has {a['event']}", "passed": ok})
        elif "command_contains" in a:
            text = a["command_contains"]
            ok = any(text in json.dumps(e["payload"].get("arguments", "")) for e in calls)
            checks.append({"name": f"ran a command containing {text!r}", "passed": ok})
    return _result(checks)
